"""在 200k 棋子平面上训练线性价值模型（等价于学习到的子力+PST）。"""
import json
import pickle
import numpy as np
from pathlib import Path
from scipy.sparse import csr_matrix
from sklearn.linear_model import Ridge

HERE = Path(__file__).parent
X = np.load(HERE / "data/planes_200k.npy")
rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
y = np.array([max(-400, min(400, int(r["cp"]))) for r in rows], dtype=np.float32)
n = len(y)
X = csr_matrix(X.reshape(n, -1).astype(np.float32))
cut = int(n * 0.85)
tr, te = slice(0, cut), slice(cut, n)

best = None
for alpha in (0.1, 1.0, 10.0):
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=200)
    m.fit(X[tr], y[tr])
    pred = m.predict(X[te])
    mae = float(np.mean(np.abs(pred - y[te])))
    r2 = float(1 - np.sum((pred - y[te]) ** 2) / np.sum((y[te] - y[te].mean()) ** 2))
    print(f"alpha={alpha} MAE={mae:.1f} R2={r2:.3f}", flush=True)
    if best is None or mae < best[0]:
        best = (mae, r2, alpha, m)

mae, r2, alpha, m = best
w = m.coef_.reshape(14, 10, 9).astype(np.float32)
b = float(m.intercept_)
np.savez(HERE / "data/linear_planes.npz", w=w, b=b)
print(json.dumps({"alpha": alpha, "mae": mae, "r2": r2, "bias": b}, ensure_ascii=False))
