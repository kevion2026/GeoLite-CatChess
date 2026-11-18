"""测试：几何树 + 小型残差 MLP（仍只用 45 维几何输入）能否压低留出 MAE。"""
import io
import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def tree_pred(model_path, X):
    M = json.load(io.open(model_path, encoding="utf-8")); t = M["tree"]["model"]
    Z = (X - np.array(t["mean"])) / np.array(t["std"])
    W = np.exp(-((Z[:, None, :] - np.array(t["centers"])[None, :, :]) ** 2).sum(-1) / (2 * t["h"] ** 2))
    W /= W.sum(1, keepdims=True)
    loc = np.stack([Z @ np.array(c["w"]) + c["b"] for c in t["local"]], 1)
    tree = (W * loc).sum(1); glob = Z @ np.array(t["glob"]["w"]) + t["glob"]["b"]
    return t["lam"] * tree + (1 - t["lam"]) * glob


z = np.load(HERE / "data/value45_cache_200k.npz", allow_pickle=True)
X, y = z["X"], z["y"]
rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
mask = np.array([r["src"] in {"pgn", "pgn_mirror", "result"} for r in rows])
X, y = X[mask], y[mask]
base = tree_pred(HERE / "model_value_pgn.json", X)
n = len(y); rng = np.random.default_rng(20261116); idx = rng.permutation(n)
tr, te = idx[:int(n * .9)], idx[int(n * .9):]
print("n", n, "base test MAE", round(float(np.mean(np.abs(y[te] - base[te]))), 1))
sc = StandardScaler().fit(X[tr])
mlp = MLPRegressor(hidden_layer_sizes=(128, 64), alpha=1e-4, learning_rate_init=1e-3, max_iter=300,
                   early_stopping=True, n_iter_no_change=15, random_state=0)
mlp.fit(sc.transform(X[tr]), y[tr] - base[tr])
res = mlp.predict(sc.transform(X[te]))
p = base[te] + np.clip(res, -600, 600)
print("mlp test MAE", round(float(np.mean(np.abs(y[te] - p))), 1),
      "R2", round(float(1 - ((y[te] - p) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum()), 3))
print("res mean/std", round(float(res.mean()), 1), round(float(res.std()), 1))
