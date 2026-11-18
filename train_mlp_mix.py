"""中局 20 万 + 残局合成数据的混合训练。

和 train_mlp45.py 的区别：
  1. 两个数据集各自切验证集，分别报 MAE，避免残局样本被中局淹没后看不出来；
  2. 残局样本可单独加权（--eg-weight），因为残局只占总量三成左右但正是缺口所在；
  3. 选模型用两个验证 MAE 之和，防止「残局变好、中局变差」的隐性回归。

中局验证集切分与 train_mlp45.py 完全一致（seed 1234 / 12%），数字可直接对比。
"""
import argparse
import json
import pathlib
import time

import numpy as np

from train_mlp45 import MLP, huber_grad

HERE = pathlib.Path(__file__).resolve().parent


def load_mid(cache, plane_cache):
    z = np.load(HERE / cache)
    X, y = z["X"].astype(np.float32), z["y"].astype(np.float32)
    pl = np.load(HERE / plane_cache)["plane"].astype(np.float32)
    assert len(pl) == len(X), (len(pl), len(X))
    return X, y, pl


def split_mid(n, val):
    rng = np.random.default_rng(1234)
    perm = rng.permutation(n)
    nval = int(n * val)
    return perm[nval:], perm[:nval]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/value45_cache_200k.npz")
    ap.add_argument("--plane", default="data/heads_200k.npz")
    ap.add_argument("--eg-cache", default="data/eg_cache.npz")
    ap.add_argument("--h1", type=int, default=64)
    ap.add_argument("--h2", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--delta", type=float, default=200.0)
    ap.add_argument("--weight", default="focus", choices=["even", "focus", "soft"])
    ap.add_argument("--eg-weight", type=float, default=1.0)
    ap.add_argument("--mid-weight", type=float, default=1.0)
    ap.add_argument("--focus-k", type=float, default=600.0)
    ap.add_argument("--mid-focus", action="store_true",
                    help="只对中局样本做 |y| 衰减（残局保持等权）")
    ap.add_argument("--val", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="model_mlp46_eg.json")
    args = ap.parse_args()

    Xm, ym, plm = load_mid(args.cache, args.plane)
    Xe, ye, ple = load_mid(args.eg_cache, args.eg_cache)
    n_mid, n_eg = len(ym), len(ye)
    print("中局 %d  残局 %d" % (n_mid, n_eg), flush=True)

    Xm = np.hstack([Xm, (plm / 200.0)[:, None]])
    Xe = np.hstack([Xe, (ple / 200.0)[:, None]])

    ti_m, vi_m = split_mid(n_mid, args.val)
    rng = np.random.default_rng(99)
    perm = rng.permutation(n_eg)
    nval = int(n_eg * args.val)
    ti_e, vi_e = perm[nval:], perm[:nval]

    Xtr = np.vstack([Xm[ti_m], Xe[ti_e]])
    ytr = np.concatenate([ym[ti_m], ye[ti_e]])
    wtr = np.ones(len(ytr), np.float32)
    if args.weight == "focus":
        wtr = (1.0 / (1.0 + np.abs(ytr) / 200.0)).astype(np.float32)
    elif args.weight == "soft":
        wtr = (1.0 / (1.0 + np.abs(ytr) / args.focus_k)).astype(np.float32)
    wtr[:len(ti_m)] *= args.mid_weight
    wtr[len(ti_m):] *= args.eg_weight
    if args.mid_focus:
        wk = (1.0 / (1.0 + np.abs(ytr[:len(ti_m)]) / 200.0)).astype(np.float32)
        wtr[:len(ti_m)] *= wk
    wtr *= len(wtr) / wtr.sum()

    Xva_m, yva_m = Xm[vi_m], ym[vi_m]
    Xva_e, yva_e = Xe[vi_e], ye[vi_e]

    mu = Xtr.mean(0)
    sd = Xtr.std(0)
    sd[sd < 1e-6] = 1.0

    def norm(A):
        return np.clip((A - mu) / sd, -8, 8).astype(np.float32)

    Ztr = norm(Xtr)
    Zm, Ze = norm(Xva_m), norm(Xva_e)

    din = Xtr.shape[1]
    net = MLP([din, args.h1, args.h2, 1], seed=args.seed)
    m = [np.zeros_like(w) for w in net.W] + [np.zeros_like(b) for b in net.b]
    s = [np.zeros_like(w) for w in net.W] + [np.zeros_like(b) for b in net.b]
    b1, b2, eps = 0.9, 0.999, 1e-8
    step = 0
    nb = (len(Ztr) + args.batch - 1) // args.batch
    rng2 = np.random.default_rng(args.seed + 1)
    best = (1e18, None, None, None)
    t0 = time.time()
    print("训练集 %d（中局 %d + 残局 %d）  验证 中局 %d / 残局 %d"
          % (len(ytr), len(ti_m), len(ti_e), len(yva_m), len(yva_e)), flush=True)
    for ep in range(args.epochs):
        idx = rng2.permutation(len(Ztr))
        tot = 0.0
        for k in range(nb):
            bi = idx[k * args.batch:(k + 1) * args.batch]
            xb, yb, vb = Ztr[bi], ytr[bi], wtr[bi]
            acts = net.forward(xb)
            pred = acts[-1].ravel()
            g = huber_grad(pred, yb, args.delta) * vb
            g = g[:, None] / len(bi)
            tot += float(np.mean(np.abs(pred - yb)))
            gW, gb = [], []
            for i in range(len(net.W) - 1, -1, -1):
                gW.append(acts[i].T @ g)
                gb.append(g.sum(0))
                if i > 0:
                    g = (g @ net.W[i].T) * (acts[i] > 0)
            gW = gW[::-1]
            gb = gb[::-1]
            step += 1
            for j, (p, gr) in enumerate(zip(net.W + net.b, gW + gb)):
                m[j] = b1 * m[j] + (1 - b1) * gr
                s[j] = b2 * s[j] + (1 - b2) * gr * gr
                mh = m[j] / (1 - b1 ** step)
                sh = s[j] / (1 - b2 ** step)
                p -= (args.lr * mh / (np.sqrt(sh) + eps)).astype(np.float32)
        pm = net.predict(Zm)
        pe = net.predict(Ze)
        mam = float(np.mean(np.abs(pm - yva_m)))
        mae = float(np.mean(np.abs(pe - yva_e)))
        calm = np.abs(yva_m) < 150
        mc = float(np.mean(np.abs(pm[calm] - yva_m[calm])))
        ecalm = np.abs(yva_e) < 150
        ec = float(np.mean(np.abs(pe[ecalm] - yva_e[ecalm]))) if ecalm.sum() else float("nan")
        if mam + mae < best[0]:
            best = (mam + mae, [w.copy() for w in net.W], [b.copy() for b in net.b],
                    (ep + 1, mam, mae))
        print("ep %2d  train %6.1f | 中局 %6.1f (均势 %5.1f) | 残局 %6.1f (均势 %5.1f)  %.0fs"
              % (ep + 1, tot / nb, mam, mc, mae, ec, time.time() - t0), flush=True)

    net.W, net.b = best[1], best[2]
    pm = net.predict(Zm)
    pe = net.predict(Ze)
    mam = float(np.mean(np.abs(pm - yva_m)))
    mae = float(np.mean(np.abs(pe - yva_e)))
    print("最佳 ep %d：中局 MAE %.1f  残局 MAE %.1f" % (best[3][0], mam, mae))
    out = {
        "dims": net.dims,
        "mean": mu.tolist(), "std": sd.tolist(),
        "W": [w.tolist() for w in net.W], "b": [b.tolist() for b in net.b],
        "metrics": {"val_mae": round(mam, 2),
                    "val_mae_calm": round(float(np.mean(
                        np.abs(pm[np.abs(yva_m) < 150] - yva_m[np.abs(yva_m) < 150]))), 2),
                    "eg_mae": round(mae, 2),
                    "r2": round(float(1 - np.sum((pm - yva_m) ** 2)
                                      / np.sum((yva_m - yva_m.mean()) ** 2)), 4)},
        "train": {"n": int(len(ytr)), "n_mid": int(len(ti_m)), "n_eg": int(len(ti_e)),
                  "epochs": best[3][0], "h1": args.h1, "h2": args.h2,
                  "weight": args.weight, "eg_weight": args.eg_weight,
                  "delta": args.delta},
    }
    p = HERE / args.out
    p.write_text(json.dumps(out), encoding="utf-8")
    print("saved", p, "%.1f MB" % (p.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
