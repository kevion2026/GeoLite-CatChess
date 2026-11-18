"""在 200k 棋子平面上训练线性价值模型，标签来自 Pikafish depth=16。"""
import glob
import json
import pickle
import numpy as np
from pathlib import Path
from scipy.sparse import csr_matrix
from sklearn.linear_model import Ridge

HERE = Path(__file__).parent
X = np.load(HERE / "data/planes_200k.npy")
n = X.shape[0]
y = np.zeros(n, dtype=np.float32)
seen = np.zeros(n, dtype=bool)
for fp in sorted(glob.glob(str(HERE / "data/pika_d16_shard*.pkl"))):
    try:
        rows = pickle.load(open(fp, "rb"))
    except Exception as e:
        print("skip", fp, e)
        continue
    for idx, cp in rows:
        y[idx] = max(-600, min(600, int(cp)))
        seen[idx] = True
print("labeled", int(seen.sum()), "/", n, flush=True)
idx = np.where(seen)[0]
X = csr_matrix(X[idx].reshape(len(idx), -1).astype(np.float32))
y = y[idx]
cut = int(len(idx) * 0.85)
tr, te = slice(0, cut), slice(cut, len(idx))

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
np.savez(HERE / "data/linear_planes_d16.npz", w=w, b=b)
print(json.dumps({"alpha": alpha, "mae": mae, "r2": r2, "bias": b}, ensure_ascii=False))
