"""阶段三：把 24 专家扩到多专家（24/64/128/256 对比），并注入避雷针权重。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np

from tree_train_pika import *  # noqa: F401,F403  复用 feats39/metrics 之外的工具
from trap_mine import feats39
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/pika_labels.pkl")
    ap.add_argument("--tactical", default="data/tactical.pkl")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--thr", type=int, default=150)
    ap.add_argument("--radius", type=float, default=0.55)
    ap.add_argument("--penalty", type=float, default=900.0)
    ap.add_argument("--train-trap-w", type=float, default=1.0)
    ap.add_argument("--force-k", type=int, default=0)
    args = ap.parse_args()

    M = json.load(io.open(args.model, encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]
    d = pickle.load(open(HERE / args.data, "rb"))
    rows = d["rows"]
    X = np.asarray([feats39(r["board"], r["side"], A, Bt, Ct) for r in rows])
    y = np.clip(np.asarray([r["score"] for r in rows], float), -1500, 1500)

    t = pickle.load(open(HERE / args.tactical, "rb"))["rows"]
    TX = np.asarray([r["x"] for r in t], float)
    Ty = np.asarray([r["y"] for r in t], float)
    Tw = np.asarray([r["w"] for r in t], float)
    print("皮卡鱼样本", len(X), "战术样本", len(TX), flush=True)

    Xall = np.vstack([X, TX])
    yall = np.concatenate([y, Ty])
    wall = np.concatenate([np.ones(len(X)), np.full(len(Tw), args.train_trap_w)])

    games = sorted({r["game"] for r in rows})
    rng = np.random.default_rng(0)
    gtr = set(int(g) for g in rng.choice(games, size=max(1, int(len(games) * 0.75)), replace=False))
    trn = np.array([i for i, r in enumerate(rows) if r["game"] in gtr])
    tst = np.array([i for i, r in enumerate(rows) if r["game"] not in gtr])

    results = {}
    for k in (24, 64, 128, 256):
        et = TreeExpert(k=k, h=3.5).fit(np.vstack([X[trn], TX]), np.concatenate([y[trn], Ty]),
                                        np.concatenate([np.ones(len(trn)), np.full(len(Tw), args.train_trap_w)]))
        p = et.predict(et.sc.transform(X[tst]))
        m = metrics(y[tst], p, args.thr)
        results[k] = m
        print(f"K={k:3d}  留出 MAE {m['mae']:6.1f}  R² {m['r2']:5.2f}  ρ {m['spearman']:5.2f}  三类 {m['acc3']*100:5.1f}%", flush=True)

    best_k = args.force_k if args.force_k else min(results, key=lambda k: results[k]["mae"])
    print("最优 K", best_k, flush=True)

    final = TreeExpert(k=best_k, h=3.5).fit(Xall, yall, wall)
    trap_rows = [r for r in t if r["tag"] == "死亡陷阱"]
    zT = final.sc.transform(np.asarray([r["x"] for r in trap_rows], float)) if trap_rows else np.zeros((0, X.shape[1]))
    pt = final.predict(final.sc.transform(np.asarray([r["x"] for r in trap_rows], float))) if trap_rows else np.array([])
    print("陷阱预测均值", round(float(pt.mean()), 1) if len(pt) else None, flush=True)

    M["tree"] = {
        "features": "39", "k": best_k, "h": final.h, "lam": final.lam, "model": final.export(),
        "metrics": results[best_k], "samples": int(len(Xall)), "source": "pikafish-selfplay+tactics",
        "grid": {str(k): results[k] for k in results},
        "traps": [{"x": [round(float(v), 4) for v in z], "r": args.radius, "k": args.penalty} for z in zT],
        "trap_meta": {"count": len(trap_rows), "pred_mean": round(float(pt.mean()), 1) if len(pt) else None},
        "tactical_counts": {tag: sum(1 for r in t if r["tag"] == tag) for tag in {r["tag"] for r in t}},
        "offline": True,
    }
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入 tree 段", flush=True)


if __name__ == "__main__":
    main()
