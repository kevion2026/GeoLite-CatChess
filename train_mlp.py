"""神经网络辅助：用小型 MLP 学习 39 维几何特征到 cp 的映射，导出给引擎做前向推理。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np
from sklearn.neural_network import MLPRegressor

from trap_mine import feats39
from tree_winprob import metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def build_features(M, files):
    A = (M["coords3a"], M["coords3b"], M["coords3c"])
    X, y, gid = [], [], []
    for f in files:
        d = pickle.load(open(HERE / f, "rb"))
        for i, r in enumerate(d["rows"]):
            X.append(feats39(r["board"], r["side"], *A))
            y.append(float(np.clip(r["score"], -1500, 1500)))
            gid.append(str(r.get("game", i)))
    return np.asarray(X, float), np.asarray(y, float), np.asarray(gid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=["data/battle_labels.pkl", "data/pika_labels.pkl"])
    ap.add_argument("--tactical", default="data/tactical_bulk.pkl")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--blend", type=float, default=0.6, help="推理时 MLP 占比")
    ap.add_argument("--hidden", default="64,32")
    args = ap.parse_args()

    M = json.load(io.open(args.model, encoding="utf-8"))
    cache = HERE / "data" / "feat_cache.npz"
    if cache.exists():
        d = np.load(cache, allow_pickle=True)
        X, y, gid = d["X"], d["y"], d["gid"]
        print("缓存特征", X.shape, flush=True)
    else:
        X, y, gid = build_features(M, args.data)
        np.savez(cache, X=X, y=y, gid=gid)
        print("特征", X.shape, flush=True)

    t = pickle.load(open(HERE / args.tactical, "rb"))["rows"]
    TX = np.asarray([r["x"] for r in t], float)
    Ty = np.asarray([r["y"] for r in t], float)
    Tw = np.asarray([2.0 if r["tag"] == "死亡陷阱" else 1.0 for r in t], float)

    games = sorted(set(gid))
    rng = np.random.default_rng(0)
    gtr = set(rng.choice(games, size=max(1, int(len(games) * 0.75)), replace=False).tolist())
    trn = np.array([i for i, g in enumerate(gid) if g in gtr])
    tst = np.array([i for i, g in enumerate(gid) if g not in gtr])

    Xtr = np.vstack([X[trn], TX])
    ytr = np.concatenate([y[trn], Ty])
    wtr = np.concatenate([np.ones(len(trn)), Tw])

    hidden = tuple(int(v) for v in args.hidden.split(","))
    from sklearn.neural_network import MLPClassifier
    cls = np.where(y > 150, 2, np.where(y < -150, 0, 1))
    clf = MLPClassifier(hidden_layer_sizes=hidden, activation="relu", alpha=1e-4,
                        learning_rate_init=1e-3, max_iter=4000, random_state=0)
    clf.fit(Xtr, np.concatenate([cls[trn], np.full(len(TX), 0)]))
    prob = clf.predict_proba(X[tst])
    acc = float((prob.argmax(1) == cls[tst]).mean())
    base = float(np.bincount(cls[tst]).max() / len(tst))
    print("MLP 三类准确率", round(acc * 100, 1), "% 基线", round(base * 100, 1), "%", flush=True)
    ptrap = clf.predict_proba(TX)
    print("陷阱判死概率均值", round(float(ptrap[:, 0].mean()), 2), flush=True)

    mean = X.mean(0); std = X.std(0); std[std == 0] = 1
    M["tree"]["mlp"] = {"kind": "clf", "W": [w.tolist() for w in clf.coefs_],
                        "b": [b.tolist() for b in clf.intercepts_],
                        "mean": mean.tolist(), "std": std.tolist(),
                        "blend": args.blend, "hidden": list(hidden),
                        "metrics": {"acc3": acc, "base": base}}
    print("已写入 mlp 段", flush=True)


if __name__ == "__main__":
    main()
