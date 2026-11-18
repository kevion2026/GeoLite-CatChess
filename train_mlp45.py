"""用 numpy 手写的小型 MLP 训练 45 维几何特征的价值模型。

为什么换掉 RBF 局部线性：
  45 维标准化空间里，到最近中心的 d² 中位数约 20，而核宽 h·hScale=8.75，
  导致「有效专家数」接近 K 本身——门控失效，模型退化成全局线性。
  实测 K 从 64 加到 256、核宽从 1.5 调到 2.5，验证集 MAE 几乎不动，证实了这一点。

结构：45 → H1 → H2 → 1，ReLU，Huber 损失，Adam，样本可按 |y| 加权。
导出时把权重写成 C++ 可用的定长数组。
"""
import argparse
import json
import pathlib
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent


def init_w(rng, fan_in, fan_out):
    # He 初始化
    return (rng.standard_normal((fan_in, fan_out)) * np.sqrt(2.0 / fan_in)).astype(np.float32)


class MLP:
    def __init__(self, dims, seed=0):
        rng = np.random.default_rng(seed)
        self.W = [init_w(rng, dims[i], dims[i + 1]) for i in range(len(dims) - 1)]
        self.b = [np.zeros(dims[i + 1], np.float32) for i in range(len(dims) - 1)]
        self.dims = dims

    def forward(self, X):
        acts = [X]
        h = X
        for i in range(len(self.W) - 1):
            h = np.maximum(h @ self.W[i] + self.b[i], 0)
            acts.append(h)
        out = h @ self.W[-1] + self.b[-1]
        acts.append(out)
        return acts

    def predict(self, X, bs=8192):
        if len(X) > bs:
            return np.concatenate([self.predict(X[i:i + bs], bs) for i in range(0, len(X), bs)]).ravel()
        return self.forward(X)[-1].ravel()


def huber_grad(pred, y, delta):
    d = pred - y
    a = np.abs(d)
    g = np.where(a <= delta, d, delta * np.sign(d))
    return g.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/value45_cache_200k.npz")
    ap.add_argument("--h1", type=int, default=128)
    ap.add_argument("--h2", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--delta", type=float, default=200.0)
    ap.add_argument("--weight", default="focus", choices=["even", "focus"])
    ap.add_argument("--val", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--add-plane", action="store_true", help="把平面评估分作为第 46 维拼进输入")
    ap.add_argument("--mirror", action="store_true", help="数据集是原样本+镜像副本，切分要按原索引成对进行")
    ap.add_argument("--out", default="model_mlp45.json")
    args = ap.parse_args()

    z = np.load(HERE / args.cache)
    X, y = z["X"].astype(np.float32), z["y"].astype(np.float32)
    if args.add_plane:
        pl = np.load(HERE / "data/heads_200k.npz")["plane"].astype(np.float32)
        if len(pl) * 2 == len(X):
            pl = np.concatenate([pl, pl])      # 镜像副本与原件同分
        X = np.hstack([X, (pl / 200.0)[:, None]])
    n = len(y)
    rng = np.random.default_rng(1234)
    if args.mirror:
        # 原样本在 [0, n/2)，镜像副本在 [n/2, n)；同一局面的两份必须同侧
        h = n // 2
        base = rng.permutation(h)
        nval = int(h * args.val)
        va, ta = base[:nval], base[nval:]
        vi = np.concatenate([va, va + h])
        ti = np.concatenate([ta, ta + h])
    else:
        perm = rng.permutation(n)
        nval = int(n * args.val)
        vi, ti = perm[:nval], perm[nval:]
    Xtr, ytr, Xva, yva = X[ti], y[ti], X[vi], y[vi]

    mu = Xtr.mean(0)
    sd = Xtr.std(0)
    sd[sd < 1e-6] = 1.0
    Ztr = np.clip((Xtr - mu) / sd, -8, 8).astype(np.float32)
    Zva = np.clip((Xva - mu) / sd, -8, 8).astype(np.float32)

    if args.weight == "focus":
        v = (1.0 / (1.0 + np.abs(ytr) / 200.0)).astype(np.float32)
        v *= len(v) / v.sum()

    din = X.shape[1]
    net = MLP([din, args.h1, args.h2, 1], seed=args.seed)
    m = [np.zeros_like(w) for w in net.W] + [np.zeros_like(b) for b in net.b]
    s = [np.zeros_like(w) for w in net.W] + [np.zeros_like(b) for b in net.b]
    b1, b2, eps = 0.9, 0.999, 1e-8
    step = 0
    nb = (len(Ztr) + args.batch - 1) // args.batch
    rng2 = np.random.default_rng(args.seed + 1)
    best = (1e18, None, None)
    t0 = time.time()
    for ep in range(args.epochs):
        idx = rng2.permutation(len(Ztr))
        tot = 0.0
        for k in range(nb):
            bi = idx[k * args.batch:(k + 1) * args.batch]
            xb, yb = Ztr[bi], ytr[bi]
            vb = v[bi] if args.weight == "focus" else None
            acts = net.forward(xb)
            pred = acts[-1].ravel()
            g = huber_grad(pred, yb, args.delta)
            if vb is not None:
                g = g * vb
            g = g[:, None] / len(bi)
            tot += float(np.mean(np.abs(pred - yb)))
            gW, gb = [], []
            for i in range(len(net.W) - 1, -1, -1):
                gW.append(acts[i].T @ g)
                gb.append(g.sum(0))
                if i > 0:
                    g = (g @ net.W[i].T) * (acts[i] > 0)
            gW = gW[::-1]; gb = gb[::-1]
            step += 1
            pars = net.W + net.b
            grads = gW + gb
            for j, (p, gr) in enumerate(zip(pars, grads)):
                m[j] = b1 * m[j] + (1 - b1) * gr
                s[j] = b2 * s[j] + (1 - b2) * gr * gr
                mh = m[j] / (1 - b1 ** step)
                sh = s[j] / (1 - b2 ** step)
                p -= (args.lr * mh / (np.sqrt(sh) + eps)).astype(np.float32)
        pv = net.predict(Zva)
        mae = float(np.mean(np.abs(pv - yva)))
        calm = np.abs(yva) < 150
        mc = float(np.mean(np.abs(pv[calm] - yva[calm])))
        if mae < best[0]:
            best = (mae, [w.copy() for w in net.W], [b.copy() for b in net.b])
        print("epoch %2d  train MAE %6.1f  val MAE %6.1f  val 均势 %6.1f  %.0fs"
              % (ep + 1, tot / nb, mae, mc, time.time() - t0), flush=True)

    net.W, net.b = best[1], best[2]
    pv = net.predict(Zva)
    calm = np.abs(yva) < 150
    print("最佳 val MAE %.1f  均势 %.1f  (旧 RBF 树：306.6 / 86.8)"
          % (np.mean(np.abs(pv - yva)), np.mean(np.abs(pv[calm] - yva[calm]))))
    out = {
        "dims": net.dims,
        "mean": mu.tolist(), "std": sd.tolist(),
        "W": [w.tolist() for w in net.W], "b": [b.tolist() for b in net.b],
        "metrics": {"val_mae": round(float(np.mean(np.abs(pv - yva))), 2),
                    "val_mae_calm": round(float(np.mean(np.abs(pv[calm] - yva[calm]))), 2),
                    "r2": round(float(1 - np.sum((pv - yva) ** 2) / np.sum((yva - yva.mean()) ** 2)), 4)},
        "train": {"n": int(len(ti)), "epochs": args.epochs, "h1": args.h1, "h2": args.h2,
                  "weight": args.weight, "delta": args.delta},
    }
    p = HERE / args.out
    p.write_text(json.dumps(out), encoding="utf-8")
    print("saved", p, "%.1f MB" % (p.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
