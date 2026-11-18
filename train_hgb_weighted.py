"""20 万全量 + 来源权重的梯度几何树：让棋谱静局面主导，同时保留战术样本。"""
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
z = np.load(HERE / "data/value45_cache_200k.npz", allow_pickle=True)
X, y = z["X"], z["y"]
rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
w = np.array([4.0 if r["src"] in {"pgn", "pgn_mirror", "result"} else
              (0.5 if r["src"] == "selfplay" else
               (0.25 if r["src"] == "battle_log" else 1.0)) for r in rows])
n = len(y); idx = np.random.default_rng(20261116).permutation(n)
tr, te = idx[:int(n * .9)], idx[int(n * .9):]
m = HistGradientBoostingRegressor(max_iter=600, learning_rate=.12, max_leaf_nodes=63,
                                  l2_regularization=1.0, random_state=0).fit(X[tr], y[tr], sample_weight=w[tr])
p = m.predict(X[te])
print("weighted all MAE", round(float(np.mean(np.abs(y[te] - p))), 1),
      "R2", round(float(1 - ((y[te] - p) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum()), 3))
pickle.dump({"model": m, "metrics": {"mae": round(float(np.mean(np.abs(y[te] - p))), 1), "n": n}},
            open(HERE / "model_value_hgb_w.pkl", "wb"))
print("saved")
