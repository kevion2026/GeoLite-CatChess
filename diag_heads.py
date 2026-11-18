"""诊断脚本：把 C++ 的两套评估在 20 万局面上分别算出来，看各自与最优融合的效果。

输出：
  - 平面模型（LW+WF）的 MAE / R2
  - 45 维几何树（geo45.h）的 MAE / R2
  - 各种融合比例的 MAE，以及线性 stack 的最优解
  - 残差诊断：几何分能否解释平面分的误差
"""
import argparse
import io
import json
import pathlib
import re

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
VAL_RE = re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?")


def parse_array(text, name):
    m = re.search(r"static const float\s+" + name + r"\s*\[[^\]]*\]\s*=\s*\{(.*?)\};", text, re.S)
    if not m:
        raise KeyError(name)
    return np.array([float(x) for x in VAL_RE.findall(m.group(1))], dtype=np.float64)


def load_geo(path=HERE / "geo45.h"):
    t = io.open(path, encoding="utf-8").read()
    g = {}
    for k in ("GEO_MEAN", "GEO_STD", "GEO_CN", "GEO_LW", "GEO_LB", "GEO_GW"):
        g[k] = parse_array(t, k)
    for k in ("GEO_K", "GEO_DIM", "GEO_STRIDE"):
        m = re.search(r"static const int\s+" + k + r"\s*=\s*(\d+)", t)
        g[k] = int(m.group(1))
    for k in ("GEO_H", "GEO_HSCALE", "GEO_LAM", "GEO_GB"):
        m = re.search(r"static const float\s+" + k + r"\s*=\s*([-+0-9.eE]+)", t)
        g[k] = float(m.group(1))
    K, S, D = g["GEO_K"], g["GEO_STRIDE"], g["GEO_DIM"]
    g["CN"] = g["GEO_CN"].reshape(K, S)
    g["LWk"] = g["GEO_LW"].reshape(K, S)
    g["LBk"] = g["GEO_LB"].reshape(K)
    g["GW"] = g["GEO_GW"].reshape(S)
    g["mean"] = g["GEO_MEAN"].reshape(S)[:D]
    g["std"] = g["GEO_STD"].reshape(S)[:D]
    return g


def load_plane(path=HERE / "linear_weight_aug.h"):
    t = io.open(path, encoding="utf-8").read()
    LW = np.array([float(x) for x in VAL_RE.findall(
        re.search(r"static const float LW\[14\]\[90\]\s*=\s*\{(.*?)\};", t, re.S).group(1))])
    WF = np.array([float(x) for x in VAL_RE.findall(
        re.search(r"static const float WF\[8\]\s*=\s*\{(.*?)\};", t, re.S).group(1))])
    LB = float(re.search(r"static const float LB\s*=\s*([-+0-9.eE]+)", t).group(1))
    return LW.reshape(14, 90), WF, LB


def geo_scores(X, g):
    D, S, K = g["GEO_DIM"], g["GEO_STRIDE"], g["GEO_K"]
    z = np.zeros((X.shape[0], S))
    z[:, :D] = (X - g["mean"]) / g["std"]
    zn = (z ** 2).sum(1)
    cn2 = (g["CN"] ** 2).sum(1)
    dot = z @ g["CN"].T                      # n×K
    d2 = np.maximum(zn[:, None] - 2 * dot + cn2[None, :], 0)
    inv = 1.0 / (2 * g["GEO_H"] ** 2 * g["GEO_HSCALE"] ** 2)
    W = np.exp(-d2 * inv)
    sw = W.sum(1)
    lb = g["LBk"][None, :] + z @ g["LWk"].T   # n×K
    tree = (W * lb).sum(1) / sw
    glob = g["GEO_GB"] + z @ g["GW"]
    lam = g["GEO_LAM"]
    return lam * tree + (1 - lam) * glob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/value45_cache_200k.npz")
    ap.add_argument("--labels", default="data/pika_values_200k.pkl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="data/diag_heads.json")
    args = ap.parse_args()

    g = load_geo()
    print("geo K=%d dim=%d stride=%d h=%.2f hScale=%.2f lam=%.2f gb=%.2f"
          % (g["GEO_K"], g["GEO_DIM"], g["GEO_STRIDE"], g["GEO_H"], g["GEO_HSCALE"],
             g["GEO_LAM"], g["GEO_GB"]))

    z = np.load(HERE / args.cache)
    X, y = z["X"], z["y"]
    if args.limit:
        X, y = X[:args.limit], y[:args.limit]
    print("样本", X.shape)

    gs = geo_scores(X, g)
    print("geo 分：mean %.1f sd %.1f  min %.1f max %.1f" % (gs.mean(), gs.std(), gs.min(), gs.max()))

    mae_g = float(np.mean(np.abs(gs - y)))
    r2_g = float(1 - np.sum((gs - y) ** 2) / np.sum((y - y.mean()) ** 2))
    print("geo  MAE %.1f  R2 %.3f  corr %.3f" % (mae_g, r2_g, np.corrcoef(gs, y)[0, 1]))

    # 线性回归 geo → y：看动态范围
    A = np.vstack([gs, np.ones_like(gs)]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    print("回归 y ≈ %.3f·geo + %.1f" % (coef[0], coef[1]))

    out = {"n": int(len(y)), "geo_mae": mae_g, "geo_r2": r2_g,
           "geo_slope": float(coef[0]), "geo_intercept": float(coef[1])}
    pathlib.Path(HERE / args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("saved", args.out)


if __name__ == "__main__":
    main()
