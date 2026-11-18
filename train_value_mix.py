"""深标签 + 实战标签混合训练：保留深标签的战术感，同时校正实战分布。"""
import io, json, pickle, pathlib, argparse
import numpy as np
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", default="data/value45_cache.npz")
    ap.add_argument("--battle", default="data/feat45_cache.npz")
    ap.add_argument("--weight", type=float, default=3.0)
    ap.add_argument("--k", type=int, default=64)
    ap.add_argument("--out", default="model_mix.json")
    ap.add_argument("--model", default="model_triple.json")
    args = ap.parse_args()
    zd = np.load(HERE / args.deep, allow_pickle=True)
    zb = np.load(HERE / args.battle, allow_pickle=True)
    Xd, yd = zd["X"], np.clip(zd["y"], -1500, 1500)
    Xb, yb = zb["X"], np.clip(zb["y"], -1500, 1500)
    w = max(1, int(round(args.weight)))
    X = np.vstack([Xd] + [Xb] * w)
    y = np.concatenate([yd] + [yb] * w)
    print("混合样本", X.shape, "deep", len(Xd), "battle×", w, flush=True)
    rng = np.random.default_rng(20261116)
    idx = rng.permutation(len(y)); ntr = int(len(y) * 0.9)
    trn, tst = idx[:ntr], idx[ntr:]
    et = TreeExpert(k=args.k, h=3.5).fit(X[trn], y[trn])
    p = et.predict(et.sc.transform(X[tst]))
    m = metrics(y[tst], p, 150)
    print("留出", m, flush=True)
    final = TreeExpert(k=args.k, h=3.5).fit(X, y)
    M = json.load(io.open(HERE / args.model, encoding="utf-8"))
    M["tree"]["model"] = final.export()
    M["tree"]["features"] = "45"
    M["tree"]["k"] = args.k
    M["tree"]["metrics"] = m
    M["tree"]["samples"] = int(len(y))
    M["tree"]["source"] = f"pika-depth8-45+battle×{w}"
    json.dump(M, io.open(HERE / args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("写入", args.out, flush=True)


if __name__ == "__main__":
    main()
