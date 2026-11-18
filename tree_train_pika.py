"""用皮卡鱼自对弈评分 + 速败陷阱特征训练分支激活树，并把陷阱坐标写进模型当黑洞。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np
from sklearn.model_selection import train_test_split

import triple3d
from trap_mine import feats39
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/pika_labels.pkl")
    ap.add_argument("--traps", default="data/traps.pkl")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--thr", type=int, default=150)
    ap.add_argument("--trap-y", type=float, default=-500.0)
    ap.add_argument("--trap-w", type=float, default=3.0)
    ap.add_argument("--radius", type=float, default=0.55)
    ap.add_argument("--penalty", type=float, default=600.0)
    args = ap.parse_args()

    M = json.load(io.open(args.model, encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]

    d = pickle.load(open(HERE / args.data, "rb"))
    rows = d["rows"]
    print("皮卡鱼样本", len(rows), "局数", len(d.get("games", [])), flush=True)
    X = np.asarray([feats39(r["board"], r["side"], A, Bt, Ct) for r in rows])
    y = np.clip(np.asarray([r["score"] for r in rows], float), -1500, 1500)

    tr = pickle.load(open(HERE / args.traps, "rb")) if pathlib.Path(HERE / args.traps).exists() else {"traps": []}
    T = np.asarray([t["x"] for t in tr["traps"]], float) if tr["traps"] else np.zeros((0, X.shape[1]))
    print("陷阱样本", T.shape, flush=True)

    Xall = np.vstack([X, T]) if len(T) else X
    yall = np.concatenate([y, np.full(len(T), args.trap_y)]) if len(T) else y
    wall = np.concatenate([np.ones(len(X)), np.full(len(T), args.trap_w)]) if len(T) else np.ones(len(X))

    # 按整局切分，避免同一局相邻局面同时落进训练与留出，造成虚高
    games = sorted({r["game"] for r in rows})
    rng = np.random.default_rng(0)
    gtr = set(int(g) for g in rng.choice(games, size=max(1, int(len(games) * 0.75)), replace=False))
    trn = np.array([i for i, r in enumerate(rows) if r["game"] in gtr])
    tst = np.array([i for i, r in enumerate(rows) if r["game"] not in gtr])

    Xtr_all = np.vstack([X[trn], T]) if len(T) else X[trn]
    ytr_all = np.concatenate([y[trn], np.full(len(T), args.trap_y)]) if len(T) else y[trn]
    eval_tree = TreeExpert(k=24, h=3.5).fit(Xtr_all, ytr_all, np.concatenate([np.ones(len(trn)), np.full(len(T), args.trap_w)]))
    p_te = eval_tree.predict(eval_tree.sc.transform(X[tst]))
    m = metrics(y[tst], p_te, args.thr)
    print("留出集（按局切分，皮卡鱼）", m, flush=True)

    sc = TreeExpert(k=24, h=3.5).fit(Xall, yall, wall)

    pt = sc.predict(sc.sc.transform(T)) if len(T) else np.array([])
    print("陷阱预测均值", round(float(pt.mean()), 1), "最低", round(float(pt.min()), 1), flush=True)

    # 陷阱中心换到标准化空间，供引擎按距离施加排斥
    zT = sc.sc.transform(T) if len(T) else np.zeros((0, X.shape[1]))
    model = sc.export()
    M["tree"] = {
        "features": "39", "k": sc.k, "h": sc.h, "lam": sc.lam,
        "model": model, "metrics": m, "samples": int(len(Xall)),
        "source": "pikafish-selfplay",
        "traps": [{"x": [round(float(v), 4) for v in z], "r": args.radius, "k": args.penalty} for z in zT],
        "trap_meta": {"count": int(len(T)), "y": args.trap_y, "w": args.trap_w,
                      "pred_mean": round(float(pt.mean()), 1) if len(pt) else None},
        "offline": True,
    }
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("已更新 tree 段（皮卡鱼样本 + 黑洞）", flush=True)


if __name__ == "__main__":
    main()
