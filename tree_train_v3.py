"""阶段三（扩量版）：合并皮卡鱼自对弈 + 枷锁战报 + 战术样本，重训激活树。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np

from trap_mine import feats39
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def load_sets(paths):
    X, y, gid = [], [], []
    n = 0
    for p in paths:
        d = pickle.load(open(HERE / p, "rb"))
        rows = d["rows"]
        A = None
        for i, r in enumerate(rows):
            if "x" in r:
                continue
            X.append(feats39(r["board"], r["side"], *AC))
            y.append(float(np.clip(r["score"], -1500, 1500)))
            gid.append(str(r.get("game", i)))
        n += len(rows)
        print("载入", p, len(rows), flush=True)
    return np.asarray(X, float), np.asarray(y, float), np.asarray(gid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=["data/battle_labels.pkl", "data/pika_labels.pkl"])
    ap.add_argument("--tactical", default="data/tactical_bulk.pkl")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--thr", type=int, default=150)
    ap.add_argument("--radius", type=float, default=0.55)
    ap.add_argument("--penalty", type=float, default=900.0)
    ap.add_argument("--trap-w", type=float, default=2.0)
    ap.add_argument("--force-k", type=int, default=0)
    args = ap.parse_args()

    global AC
    M = json.load(io.open(args.model, encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])

    X, y, gid = load_sets(args.data)
    t = pickle.load(open(HERE / args.tactical, "rb"))["rows"]
    TX = np.asarray([r["x"] for r in t], float)
    Ty = np.asarray([r["y"] for r in t], float)
    Tw = np.asarray([args.trap_w if r["tag"] == "死亡陷阱" else 1.0 for r in t], float)
    print("回归样本", len(X), "战术样本", len(TX), flush=True)

    games = sorted(set(gid))
    rng = np.random.default_rng(0)
    gtr = set(rng.choice(games, size=max(1, int(len(games) * 0.75)), replace=False).tolist())
    trn = np.array([i for i, g in enumerate(gid) if g in gtr])
    tst = np.array([i for i, g in enumerate(gid) if g not in gtr])

    results = {}
    for k in (24, 64, 128, 256):
        if k > len(trn):
            continue
        et = TreeExpert(k=k, h=3.5).fit(np.vstack([X[trn], TX]), np.concatenate([y[trn], Ty]),
                                        np.concatenate([np.ones(len(trn)), Tw]))
        p = et.predict(et.sc.transform(X[tst]))
        m = metrics(y[tst], p, args.thr)
        results[k] = m
        print(f"K={k:3d}  MAE {m['mae']:6.1f}  R² {m['r2']:5.2f}  ρ {m['spearman']:5.2f}  三类 {m['acc3']*100:5.1f}%", flush=True)

    best_k = args.force_k or min(results, key=lambda k: results[k]["mae"])
    print("采用 K", best_k, flush=True)
    final = TreeExpert(k=best_k, h=3.5).fit(np.vstack([X, TX]), np.concatenate([y, Ty]),
                                            np.concatenate([np.ones(len(X)), Tw]))
    trap_rows = [r for r in t if r["tag"] == "死亡陷阱"]
    XT = np.asarray([r["x"] for r in trap_rows], float) if trap_rows else np.zeros((0, 39))
    zT = final.sc.transform(XT) if len(XT) else np.zeros((0, 39))
    pt = final.predict(final.sc.transform(XT)) if len(XT) else np.array([])

    M["tree"] = {
        "features": "39", "k": best_k, "h": final.h, "lam": final.lam, "model": final.export(),
        "metrics": results[best_k], "samples": int(len(X) + len(TX)),
        "source": "pikafish-selfplay+battle-logs+tactics", "grid": {str(k): results[k] for k in results},
        "traps": [{"x": [round(float(v), 4) for v in z], "r": args.radius, "k": args.penalty} for z in zT],
        "trap_meta": {"count": len(trap_rows), "pred_mean": round(float(pt.mean()), 1) if len(pt) else None},
        "tactical_counts": {tag: sum(1 for r in t if r["tag"] == tag) for tag in {r["tag"] for r in t}},
        "offline": True,
    }
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("陷阱预测均值", M["tree"]["trap_meta"]["pred_mean"], flush=True)
    print("已写入 tree 段", flush=True)


AC = None

if __name__ == "__main__":
    main()
