"""重训 45 维几何树：加权局部线性回归 + 可调核宽 + 训练/验证切分。

与旧版（tree_train_v3）的差别：
  1. 样本权重 w(y)：可以让模型专注均势局面（棋力主要由它决定），而不是被 ±1500 的大比分样本主导
  2. 核宽 h·hScale 与专家数 K 都做网格搜索，用验证集选，不再沿用旧参数
  3. 全流程闭式解（固定中心时是凸问题），无随机初始化、可复现

用法：
  python train_geo_v2.py --k 128 --hscale 2.5 --weight focus --out model_geo_v2.json
"""
import argparse
import json
import pathlib
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
DIM, STRIDE = 45, 48


def kmeans(Z, K, iters=30, seed=0):
    rng = np.random.default_rng(seed)
    n = len(Z)
    idx = rng.choice(n, K, replace=False)
    C = Z[idx].copy()
    for it in range(iters):
        d2 = (Z ** 2).sum(1)[:, None] - 2 * Z @ C.T + (C ** 2).sum(1)[None, :]
        lab = d2.argmin(1)
        newC = np.zeros_like(C)
        cnt = np.bincount(lab, minlength=K)
        np.add.at(newC, lab, Z)
        empty = cnt == 0
        newC[~empty] /= cnt[~empty, None]
        if empty.any():
            newC[empty] = Z[rng.choice(n, int(empty.sum()), replace=False)]
        shift = float(np.abs(newC - C).max())
        C = newC
        if shift < 1e-4:
            break
    return C


def local_fit(Z, y, v, wts, alpha):
    """加权最小二乘：每个专家一套 (b, w)，权重 = 核权重 × 样本权重。"""
    n, d = Z.shape
    A = np.empty((n, d + 1))
    A[:, 0] = 1.0
    A[:, 1:] = Z
    K = wts.shape[1]
    B = np.zeros(K)
    Wm = np.zeros((K, d))
    I = np.eye(d + 1)
    I[0, 0] = 0.0                      # 不惩罚偏置
    for k in range(K):
        u = wts[:, k] * v
        AW = A * u[:, None]
        M = A.T @ AW + alpha * I
        rhs = AW.T @ y
        try:
            th = np.linalg.solve(M, rhs)
        except np.linalg.LinAlgError:
            th = np.linalg.lstsq(M, rhs, rcond=None)[0]
        B[k] = th[0]
        Wm[k] = th[1:]
    return Wm, B


def kernel_wts(Z, C, h, hscale):
    inv = 1.0 / (2 * h * h * hscale * hscale)
    zn = (Z ** 2).sum(1)
    cn = (C ** 2).sum(1)
    d2 = np.maximum(zn[:, None] - 2 * Z @ C.T + cn[None, :], 0)
    return np.exp(-d2 * inv)


def predict(Z, C, Wm, B, gw, gb, lam, h, hscale):
    W = kernel_wts(Z, C, h, hscale)
    sw = np.maximum(W.sum(1), 1e-9)
    tree = (W * (B[None, :] + Z @ Wm.T)).sum(1) / sw
    glob = gb + Z @ gw
    return lam * tree + (1 - lam) * glob


def report(name, pred, y, mask=None):
    if mask is None:
        mask = np.ones(len(y), bool)
    e = np.abs(pred[mask] - y[mask])
    r2 = 1 - np.sum((pred[mask] - y[mask]) ** 2) / np.sum((y[mask] - y[mask].mean()) ** 2)
    print("  %-18s MAE %6.1f  R2 %.3f  n=%d" % (name, e.mean(), r2, mask.sum()))
    return float(e.mean()), float(r2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/value45_cache_200k.npz")
    ap.add_argument("--k", type=int, default=128)
    ap.add_argument("--h", type=float, default=3.5)
    ap.add_argument("--hscale", type=float, default=2.5)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--weight", default="even", choices=["even", "focus", "focus2"])
    ap.add_argument("--val", type=float, default=0.12)
    ap.add_argument("--lam", default="auto")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="model_geo_v2.json")
    args = ap.parse_args()

    z = np.load(HERE / args.cache)
    X, y = z["X"], z["y"]
    n = len(y)
    rng = np.random.default_rng(1234)
    perm = rng.permutation(n)
    nval = int(n * args.val)
    vi, ti = perm[:nval], perm[nval:]
    Xtr, ytr = X[ti], y[ti]
    Xva, yva = X[vi], y[vi]
    print("train %d val %d  K=%d h=%.2f hScale=%.2f alpha=%.2f weight=%s"
          % (len(ti), len(vi), args.k, args.h, args.hscale, args.alpha, args.weight))

    mu = Xtr.mean(0)
    sd = Xtr.std(0)
    sd[sd < 1e-6] = 1.0          # 常量维：z 保持 0，避免 1/sd 爆炸
    Ztr = (Xtr - mu) / sd
    Zva = (Xva - mu) / sd

    if args.weight == "even":
        v = np.ones(len(ytr))
    elif args.weight == "focus":
        v = 1.0 / (1.0 + np.abs(ytr) / 200.0)
    else:
        v = 1.0 / (1.0 + (np.abs(ytr) / 200.0) ** 2)
    v = v * len(v) / v.sum()

    t0 = time.time()
    C = kmeans(Ztr, args.k, seed=args.seed)
    print("kmeans %.1fs" % (time.time() - t0), flush=True)

    t0 = time.time()
    Wtr = kernel_wts(Ztr, C, args.h, args.hscale)
    Wm, B = local_fit(Ztr, ytr, v, Wtr, args.alpha)
    print("local fit %.1fs" % (time.time() - t0), flush=True)

    A = np.hstack([Ztr, np.ones((len(Ztr), 1))])
    gw_full = np.linalg.lstsq(A, ytr, rcond=None)[0]
    gw, gb = gw_full[:-1], gw_full[-1]

    best = None
    for lam in ([1.0] if args.lam != "auto" else [0.6, 0.7, 0.8, 0.9, 0.95, 1.0]):
        pv = predict(Zva, C, Wm, B, gw, gb, lam, args.h, args.hscale)
        mae = float(np.mean(np.abs(pv - yva)))
        print("  lam=%.2f val MAE %.1f" % (lam, mae), flush=True)
        if best is None or mae < best[0]:
            best = (mae, lam)
    lam = best[1]
    print("选定 lam=%.2f" % lam)

    pv = predict(Zva, C, Wm, B, gw, gb, lam, args.h, args.hscale)
    print("验证集：")
    report("all", pv, yva)
    report("|y|<150 均势", pv, yva, np.abs(yva) < 150)
    report("|y|>600 大优", pv, yva, np.abs(yva) > 600)

    pad = lambda a: np.concatenate([a, np.zeros((len(a), STRIDE - DIM) if a.ndim == 2 else STRIDE - DIM)])
    model = {
        "k": args.k, "h": args.h, "lam": lam, "alpha": args.alpha,
        "mean": mu.tolist(), "std": sd.tolist(),
        "centers": [pad(c).tolist() for c in C],
        "local": [{"w": pad(w).tolist(), "b": float(b)} for w, b in zip(Wm, B)],
        "glob": {"w": pad(gw).tolist(), "b": float(gb)},
        "metrics": {"val_mae": round(float(np.mean(np.abs(pv - yva))), 2),
                    "val_r2": round(float(1 - np.sum((pv - yva) ** 2) / np.sum((yva - yva.mean()) ** 2)), 4),
                    "val_mae_calm": round(float(np.mean(np.abs(pv[np.abs(yva) < 150] - yva[np.abs(yva) < 150]))), 2),
                    "lam": lam, "weight": args.weight, "train_n": int(len(ti))},
        "hScale": args.hscale,
    }
    out = HERE / args.out
    out.write_text(json.dumps(model), encoding="utf-8")
    print("saved", out, "%.1f MB" % (out.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
