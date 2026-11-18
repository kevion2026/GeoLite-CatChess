"""在 200k 棋子平面上：线性模型 + 小梯度提升树残差，导出 C++ 头文件。"""
import json
import pickle
import numpy as np
from pathlib import Path
from scipy.sparse import csr_matrix
from sklearn.ensemble import GradientBoostingRegressor

HERE = Path(__file__).parent
X = np.load(HERE / "data/planes_200k.npy").reshape(200000, -1)
rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
y = np.array([max(-400, min(400, int(r["cp"]))) for r in rows], dtype=np.float32)
X = csr_matrix(X.astype(np.float32))

d = np.load(HERE / "data/linear_planes.npz")
w = d["w"].astype(np.float32).reshape(-1)
b = float(d["b"])
pred = X @ w + b
res = y - pred

cut = int(len(y) * 0.85)
tr, te = slice(0, cut), slice(cut, len(y))
gbr = GradientBoostingRegressor(n_estimators=80, max_depth=3, learning_rate=0.08,
                                subsample=0.6, random_state=7)
gbr.fit(X[tr], res[tr])
r_te = gbr.predict(X[te])
final = pred[te] + r_te
mae = float(np.mean(np.abs(final - y[te])))
r2 = float(1 - np.sum((final - y[te]) ** 2) / np.sum((y[te] - y[te].mean()) ** 2))
print(json.dumps({"mae": mae, "r2": r2, "trees": len(gbr.estimators_)}, ensure_ascii=False))

# 导出树
feat, thr, left, right, val, roots = [], [], [], [], [], []
for est in gbr.estimators_[:, 0]:
    t = est.tree_
    root = len(feat)
    roots.append(root)
    for i in range(t.node_count):
        feat.append(int(t.feature[i]))
        thr.append(float(t.threshold[i]))
        left.append(int(t.children_left[i]) + root if t.children_left[i] >= 0 else -1)
        right.append(int(t.children_right[i]) + root if t.children_right[i] >= 0 else -1)
        val.append(float(t.value[i][0][0]))

np.savez(HERE / "data/gbr_residual.npz", feat=feat, thr=thr, left=left, right=right,
         val=val, roots=roots)
print("nodes", len(feat), "roots", len(roots))
