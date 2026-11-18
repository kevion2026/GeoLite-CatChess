"""训练 ±400 截断的几何价值头（位置评估），全 20 万样本。"""
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
z = np.load(HERE / "data/value45_cache_200k.npz", allow_pickle=True)
X = z["X"]; y = np.clip(z["y"], -400, 400)
n = len(y); idx = np.random.default_rng(20261116).permutation(n)
tr, te = idx[:int(n * .9)], idx[int(n * .9):]
m = HistGradientBoostingRegressor(max_iter=600, learning_rate=.12, max_leaf_nodes=63,
                                  l2_regularization=1.0, random_state=0).fit(X[tr], y[tr])
p = m.predict(X[te])
print("clip400 MAE", round(float(np.mean(np.abs(y[te] - p))), 1),
      "R2", round(float(1 - ((y[te] - p) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum()), 3))
pickle.dump({"model": m, "metrics": {"mae": round(float(np.mean(np.abs(y[te] - p))), 1), "n": n}},
            open(HERE / "model_value_hgb_clip400.pkl", "wb"))
print("saved")
