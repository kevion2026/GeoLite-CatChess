"""按标签区间/来源拆新模型留出误差，定位 MAE 的主要来源。"""
import io
import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.preprocessing import StandardScaler

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
cache = np.load(HERE / "data/value45_cache_200k.npz", allow_pickle=True)
X, y = cache["X"], cache["y"]
M = json.load(io.open(HERE / "model_value200.json", encoding="utf-8"))
t = M["tree"]["model"]

mu = np.array(t["mean"]); sd = np.array(t["std"])
Z = (X - mu) / sd
centers = np.array(t["centers"])
W = np.exp(-((Z[:, None, :] - centers[None, :, :]) ** 2).sum(-1) / (2 * t["h"] ** 2))
W /= W.sum(1, keepdims=True)
loc = np.stack([Z @ np.array(c["w"]) + c["b"] for c in t["local"]], 1)
tree = (W * loc).sum(1)
glob = Z @ np.array(t["glob"]["w"]) + t["glob"]["b"]
p = t["lam"] * tree + (1 - t["lam"]) * glob

n = len(y); rng = np.random.default_rng(20261116)
idx = rng.permutation(n); ntr = int(n * 0.9); tst = idx[ntr:]
err = np.abs(y[tst] - p[tst])
print("holdout", len(tst), "MAE", round(err.mean(), 1))
for lo, hi in [(0,150),(150,400),(400,800),(800,1500)]:
    m = (np.abs(y[tst]) >= lo) & (np.abs(y[tst]) < hi)
    print(f"|y| {lo}-{hi}: n={m.sum()} MAE={err[m].mean():.1f}")
for label, fn in [("mate>1500", lambda v: np.abs(v) > 1500), ("quiet<=150", lambda v: np.abs(v) <= 150)]:
    m = fn(y[tst]); print(label, m.sum(), round(err[m].mean(), 1))
rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
from collections import Counter
src = np.array([rows[i]["src"] for i in tst])
for s in sorted(set(src.tolist())):
    m = src == s
    print("src", s, m.sum(), round(err[m].mean(), 1))
