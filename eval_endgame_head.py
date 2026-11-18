"""在残局局面集上评估价值头：整体 MAE / 分桶 / 子力档 / 符号准确率。

用法：
  python eval_endgame_head.py --pos data/pika_values_endgame.pkl --model model_mlp46_xs.json
不带 --model 时只跑平面分和几何基准，用来定位缺口在哪个环节。
"""
import argparse
import collections
import io
import json
import pickle

import numpy as np

import diag_heads as D
from diag_plane import plane_score
from feats45 import feats45

MATV = {1: 0, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}


def mlp_forward(model, X46):
    W = [np.array(w, np.float32) for w in model["W"]]
    b = [np.array(x, np.float32) for x in model["b"]]
    mu = np.array(model["mean"], np.float32)
    sd = np.array(model["std"], np.float32)
    Z = np.clip((X46 - mu) / sd, -8, 8).astype(np.float32)
    h = Z
    for i in range(len(W) - 1):
        h = np.maximum(h @ W[i] + b[i], 0)
    return (h @ W[-1] + b[-1]).ravel()


def build(rows):
    M = json.load(io.open("model_value.json", encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])
    n = len(rows)
    X = np.zeros((n, 45), np.float32)
    pl = np.zeros(n, np.float32)
    y = np.zeros(n, np.float32)
    mat = np.zeros(n, np.float32)
    adv = np.zeros(n, np.float32)
    for i, r in enumerate(rows):
        X[i] = feats45(r["board"], r["side"], *AC)
        pl[i] = plane_score(r["board"], r["side"])
        y[i] = float(np.clip(r["cp"], -1500, 1500))
        mat[i] = sum(MATV[abs(p)] for p in r["board"] if p)
        s = 1 if r["side"] > 0 else -1
        adv[i] = sum(MATV[abs(p)] * (1 if (p > 0) == (s > 0) else -1)
                     for p in r["board"] if p)
    return X, pl, y, mat, adv


def report(name, pred, y, mat, bins=True):
    d = pred - y
    print("\n=== %s ===" % name)
    print("n=%d  MAE %.1f  RMSE %.1f  corr %.4f  R2 %.3f  同号 %.1f%%"
          % (len(y), np.abs(d).mean(), np.sqrt((d ** 2).mean()),
             np.corrcoef(pred, y)[0, 1],
             1 - np.sum(d ** 2) / np.sum((y - y.mean()) ** 2),
             100 * np.mean(np.sign(pred) == np.sign(y))))
    if not bins:
        return
    print("  |y| 分桶:")
    for lo, hi in [(0, 150), (150, 400), (400, 800), (800, 1500), (1500, 1e9)]:
        m = (np.abs(y) >= lo) & (np.abs(y) < hi)
        if m.sum() == 0:
            continue
        print("    %5d-%5d  n=%6d  MAE %6.1f  平均偏差 %+7.1f"
              % (lo, hi, m.sum(), np.abs(d[m]).mean(), d[m].mean()))
    print("  子力档:")
    for lo, hi in [(0, 800), (800, 1400), (1400, 2200), (2200, 3200), (3200, 1e9)]:
        m = (mat >= lo) & (mat < hi)
        if m.sum() == 0:
            continue
        print("    %5d-%5d  n=%6d  MAE %6.1f  平均偏差 %+7.1f"
              % (lo, hi, m.sum(), np.abs(d[m]).mean(), d[m].mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pos", default="data/pika_values_endgame.pkl")
    ap.add_argument("--model", default="")
    ap.add_argument("--scale", type=float, default=1.0, help="MLP 输出缩放（线上默认 0.75）")
    ap.add_argument("--save", default="")
    args = ap.parse_args()

    rows = pickle.load(open(args.pos, "rb"))
    rows = [r for r in rows if r.get("cp") is not None]
    print("评估局面", len(rows))
    X, pl, y, mat, adv = build(rows)

    report("平面评估（LW+WF）", pl, y, mat)
    g = D.load_geo()
    report("45 维几何树", D.geo_scores(X, g), y, mat)

    if args.model:
        m = json.load(io.open(args.model, encoding="utf-8"))
        X46 = np.hstack([X, (pl / 200.0)[:, None]]).astype(np.float32)
        pred = mlp_forward(m, X46) * args.scale
        report("%s  (scale %.2f)" % (args.model, args.scale), pred, y, mat)

    if args.save:
        np.savez(args.save, y=y, mat=mat, plane=pl, X=X, adv=adv)
        print("已存", args.save)


if __name__ == "__main__":
    main()
