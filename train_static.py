"""在 200k 棋子平面上拟合 Pikafish NNUE 静态评估。"""
import json
import pickle
import numpy as np
from pathlib import Path
from scipy.sparse import csr_matrix
from sklearn.linear_model import Ridge

HERE = Path(__file__).parent
X = np.load(HERE / "data/planes_200k.npy")
rows = pickle.load(open(HERE / "data/pika_static_200k.pkl", "rb"))
y = np.array([max(-1500, min(1500, int(r[1]))) for r in rows], dtype=np.float32)
n = len(y)
X = csr_matrix(X.reshape(n, -1).astype(np.float32))
cut = int(n * 0.85)
best = None
for alpha in (0.1, 1.0, 10.0, 100.0):
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=300)
    m.fit(X[:cut], y[:cut])
    pred = m.predict(X[cut:])
    mae = float(np.mean(np.abs(pred - y[cut:])))
    r2 = float(1 - np.sum((pred - y[cut:]) ** 2) / np.sum((y[cut:] - y[cut:].mean()) ** 2))
    print(f"alpha={alpha} MAE={mae:.1f} R2={r2:.3f}", flush=True)
    if best is None or mae < best[0]:
        best = (mae, r2, alpha, m)
mae, r2, alpha, m = best
w = m.coef_.reshape(14, 10, 9).astype(np.float32)
b = float(m.intercept_)
np.savez(HERE / "data/linear_static.npz", w=w, b=b)
print(json.dumps({"alpha": alpha, "mae": mae, "r2": r2, "bias": b}, ensure_ascii=False))
