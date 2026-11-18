"""测试几何特征上的梯度提升树，判断 45 维几何是否足以把留出 MAE 压到 100 以下。"""
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
z = np.load(HERE / "data/value45_cache_200k.npz", allow_pickle=True)
X, y = z["X"], z["y"]
rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
mask = np.array([r["src"] in {"pgn", "pgn_mirror", "result"} for r in rows])
X, y = X[mask], y[mask]
n = len(y); rng = np.random.default_rng(20261116); idx = rng.permutation(n)
tr, te = idx[:int(n * .9)], idx[int(n * .9):]
for lr in (0.05, 0.1):
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=lr, max_leaf_nodes=31,
                                      l2_regularization=1.0, random_state=0)
    m.fit(X[tr], y[tr])
    p = m.predict(X[te])
    print("lr", lr, "MAE", round(float(np.mean(np.abs(y[te] - p))), 1),
          "R2", round(float(1 - ((y[te] - p) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum()), 3))
