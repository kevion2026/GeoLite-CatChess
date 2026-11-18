"""45 维几何特征重训：K=64，按局切分，写入 tree45。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np

from feats45 import feats45
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=["data/battle_labels.pkl", "data/pika_labels.pkl"])
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--k", type=int, default=64)
    ap.add_argument("--blend", type=float, default=0.0)
    args = ap.parse_args()

    M = json.load(io.open(args.model, encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])
    cache = HERE / "data" / "feat45_cache.npz"
    if cache.exists():
        d = np.load(cache, allow_pickle=True)
        X, y, gid = d["X"], d["y"], d["gid"]
    else:
        X, y, gid = [], [], []
        for f in args.data:
            d = pickle.load(open(HERE / f, "rb"))
            for i, r in enumerate(d["rows"]):
                X.append(feats45(r["board"], r["side"], *AC))
                y.append(float(np.clip(r["score"], -1500, 1500)))
                gid.append(str(r.get("game", i)))
        X, y, gid = np.asarray(X, float), np.asarray(y), np.asarray(gid)
        np.savez(cache, X=X, y=y, gid=gid)
    print("45 维样本", X.shape, flush=True)

    games = sorted(set(gid))
    rng = np.random.default_rng(0)
    gtr = set(rng.choice(games, size=int(len(games) * 0.75), replace=False).tolist())
    trn = np.array([i for i, g in enumerate(gid) if g in gtr])
    tst = np.array([i for i, g in enumerate(gid) if g not in gtr])

    et = TreeExpert(k=args.k, h=3.5).fit(X[trn], y[trn])
    p = et.predict(et.sc.transform(X[tst]))
    m = metrics(y[tst], p, 150)
    print("45 维留出", m, flush=True)
    final = TreeExpert(k=args.k, h=3.5).fit(X, y)
    M["tree"]["model"] = final.export()
    M["tree"]["features"] = "45"
    M["tree"]["k"] = args.k
    M["tree"]["metrics"] = m
    M["tree"]["samples"] = int(len(X))
    M["tree"]["source"] = "45-geometry"
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入 45 维树", flush=True)


if __name__ == "__main__":
    main()
