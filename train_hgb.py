"""训练梯度提升几何树（HGB），并保存模型与同口径指标。"""
import argparse
import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def load(src):
    z = np.load(HERE / "data/value45_cache_200k.npz", allow_pickle=True)
    X, y = z["X"], z["y"]
    rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
    if src:
        mask = np.array([r["src"] in src for r in rows])
        X, y = X[mask], y[mask]
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="")
    ap.add_argument("--out", default="model_value_hgb.pkl")
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--lr", type=float, default=0.12)
    ap.add_argument("--leaves", type=int, default=63)
    args = ap.parse_args()
    srcs = set(s.strip() for s in args.src.split(",") if s.strip()) if args.src else None
    X, y = load(srcs)
    n = len(y); idx = np.random.default_rng(20261116).permutation(n)
    tr, te = idx[:int(n * .9)], idx[int(n * .9):]
    m = HistGradientBoostingRegressor(max_iter=args.iters, learning_rate=args.lr,
                                      max_leaf_nodes=args.leaves, l2_regularization=1.0,
                                      random_state=0).fit(X[tr], y[tr])
    p = m.predict(X[te])
    met = dict(mae=round(float(np.mean(np.abs(y[te] - p))), 1),
               r2=round(float(1 - ((y[te] - p) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum()), 3),
               n=int(n), test=int(len(te)))
    print(met, flush=True)
    pickle.dump({"model": m, "metrics": met, "src": args.src}, open(HERE / args.out, "wb"))
    print("写入", args.out, flush=True)


if __name__ == "__main__":
    main()
