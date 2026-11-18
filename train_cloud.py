"""把云库评分并入训练：云库是“强引擎视角”的胜率数据，可校正自对弈标签的偏负分布。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np

import geo
import triple3d
from dual_winprob import shape_feats
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
from matfeat import mat_feats


def feats39(board_, side, A, Bt, Ct):
    v, _ = triple3d.state_triple(board_, side, A, Bt, Ct, layers=0)
    toks = geo.position_tokens(board_, side)
    pa = [(t[3], A[t[0]]) for t in toks if t[0] in A]
    pb = [(t[3], Bt[t[0]]) for t in toks if t[0] in Bt]
    pc = [(t[3], Ct[t[0]]) for t in toks if t[0] in Ct]
    sh = (shape_feats(v[:7], pa) + shape_feats(v[7:14], pb) + shape_feats(v[14:21], pc))
    return np.asarray(list(v) + list(sh) + mat_feats(board_, side), dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--k", type=int, default=64)
    ap.add_argument("--cloud-w", type=float, default=1.0)
    ap.add_argument("--cloud-only", action="store_true")
    args = ap.parse_args()
    M = json.load(io.open(args.model, encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])

    X, y, gid = [], [], []
    d = np.load(HERE / "data" / "feat_cache.npz", allow_pickle=True)
    X.append(d["X"]); y.append(d["y"]); gid.append(d["gid"])
    rows = pickle.load(open(HERE / "data" / "cloud_labels.pkl", "rb"))["rows"]
    cx, cy = [], []
    for r in rows:
        s = float(r["score"])
        if abs(s) >= 20000:  # 绝杀分不进回归，交给战术叶子
            continue
        cx.append(feats39(np.array(r["board"], float), int(r["side"]), *AC))
        cy.append(np.clip(s * int(r["side"]), -1500, 1500))
    cx, cy = np.asarray(cx, float), np.asarray(cy)
    print("云库样本", cx.shape, "均值", round(float(cy.mean()), 1))

    X = cx if args.cloud_only else np.vstack([X[0], cx])
    y = cy if args.cloud_only else np.concatenate([y[0], cy])
    gid = np.array([f"cloud{j}" for j in range(len(cy))]) if args.cloud_only else np.concatenate([gid[0], np.array([f"cloud{j}" for j in range(len(cy))])])

    games = sorted(set(gid))
    rng = np.random.default_rng(7)
    gtr = set(rng.choice(games, size=int(len(games) * 0.75), replace=False).tolist())
    trn = np.array([i for i, g in enumerate(gid) if g in gtr])
    tst = np.array([i for i, g in enumerate(gid) if g not in gtr])
    w = np.ones(len(X))
    if not args.cloud_only:
        w[len(d["X"]):] = args.cloud_w
    et = TreeExpert(k=args.k, h=3.5).fit(X[trn], y[trn], w[trn])
    m = metrics(y[tst], et.predict(et.sc.transform(X[tst])), 150)
    print("云库混合留出", m)

    final = TreeExpert(k=args.k, h=3.5).fit(X, y, w)
    M["tree"]["model"] = final.export()
    M["tree"]["features"] = "39"
    M["tree"]["k"] = args.k
    M["tree"]["metrics"] = m
    M["tree"]["samples"] = int(len(X))
    M["tree"]["source"] = "39-geometry+cloud"
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入云库混合树")


if __name__ == "__main__":
    main()
