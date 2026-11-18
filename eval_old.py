"""把新树放到旧 98k 留出集上评测（同口径对比）。"""
import io
import json
from pathlib import Path

import numpy as np

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def pred(model_path, X):
    M = json.load(io.open(model_path, encoding="utf-8"))
    t = M["tree"]["model"]
    mu = np.array(t["mean"]); sd = np.array(t["std"])
    Z = (X - mu) / sd
    centers = np.array(t["centers"])
    W = np.exp(-((Z[:, None, :] - centers[None, :, :]) ** 2).sum(-1) / (2 * t["h"] ** 2))
    W /= W.sum(1, keepdims=True)
    loc = np.stack([Z @ np.array(c["w"]) + c["b"] for c in t["local"]], 1)
    tree = (W * loc).sum(1)
    glob = Z @ np.array(t["glob"]["w"]) + t["glob"]["b"]
    return t["lam"] * tree + (1 - t["lam"]) * glob


for cache_name in ("value45_cache.npz", "value45_cache_200k.npz"):
    z = np.load(HERE / "data" / cache_name, allow_pickle=True)
    X, y = z["X"], z["y"]
    n = len(y); rng = np.random.default_rng(20261116); idx = rng.permutation(n)
    tst = idx[int(n * 0.9):]
    print(cache_name, "n", n, "test", len(tst))
    for model in ("model_value.json", "model_value200.json", "model_value200_k128.json"):
        p = pred(HERE / model, X[tst])
        mae = np.mean(np.abs(y[tst] - p))
        r2 = 1 - ((y[tst] - p) ** 2).sum() / ((y[tst] - y[tst].mean()) ** 2).sum()
        print(" ", model, "MAE", round(float(mae), 1), "R2", round(float(r2), 3))
