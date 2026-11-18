"""线性棋子平面 + 8 个几何特征，拟合 Pikafish NNUE 静态评估。"""
import pickle
import numpy as np
from pathlib import Path
from scipy.sparse import csr_matrix, hstack
from sklearn.linear_model import Ridge

HERE = Path(__file__).parent
X = np.load(HERE / "data/planes_200k.npy")
n = X.shape[0]
X = X.reshape(n, 14, 10, 9)
rows = pickle.load(open(HERE / "data/pika_static_200k.pkl", "rb"))
y = np.array([max(-1500, min(1500, int(r[1]))) for r in rows], dtype=np.float32)
n = len(y)

DX = (1, -1, 0, 0)
DY = (0, 0, 1, -1)
HX = (1, 2, 2, 1, -1, -2, -2, -1)
HY = (2, 1, -1, -2, -2, -1, 1, 2)


def feats(ch):
    occ = (ch.sum(axis=0) > 0)
    own_k = np.argwhere(ch[0] > 0)
    f = np.zeros(8, dtype=np.float32)
    if len(own_k) == 0:
        return f
    ky, kx = own_k[0]
    for d in range(4):
        cx, cy = kx, ky
        seen = 0
        while True:
            cx += DX[d]; cy += DY[d]
            if not (0 <= cx < 9 and 0 <= cy < 10):
                break
            if not occ[cy, cx]:
                continue
            if seen == 0:
                if ch[11][cy, cx] > 0:
                    f[0] += 1
                seen = 1
            else:
                if ch[12][cy, cx] > 0:
                    f[1] += 1
                break
    for k in range(8):
        cx, cy = kx + HX[k], ky + HY[k]
        if 0 <= cx < 9 and 0 <= cy < 10 and ch[10][cy, cx] > 0:
            f[2] += 1
    for d in range(4):
        cx, cy = kx + DX[d], ky + DY[d]
        if 0 <= cx < 9 and 0 <= cy < 10 and ch[13][cy, cx] > 0:
            f[3] += 1
    f[4] = ch[1].sum()
    f[5] = ch[2].sum()
    for ry, rx in np.argwhere(ch[4] > 0):
        mob = 0
        for d in range(4):
            cx, cy = rx, ry
            while True:
                cx += DX[d]; cy += DY[d]
                if not (0 <= cx < 9 and 0 <= cy < 10):
                    break
                if occ[cy, cx]:
                    break
                mob += 1
        f[6] += min(mob, 14)
    pb = ch[13].sum(axis=0) > 0
    for ry, rx in np.argwhere(ch[6] > 0):
        lo = max(0, rx - 1); hi = min(8, rx + 1)
        if not pb[lo:hi + 1].any():
            f[7] += 1
    return f


F = np.zeros((n, 8), dtype=np.float32)
for i in range(n):
    F[i] = feats(X[i])
print("feat done", flush=True)
Xs = csr_matrix(X.reshape(n, -1).astype(np.float32))
Xa = hstack([Xs, csr_matrix(F)]).tocsr()
cut = int(n * 0.85)
best = None
for alpha in (0.1, 1.0, 10.0):
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=300)
    m.fit(Xa[:cut], y[:cut])
    pred = m.predict(Xa[cut:])
    mae = float(np.mean(np.abs(pred - y[cut:])))
    r2 = float(1 - np.sum((pred - y[cut:]) ** 2) / np.sum((y[cut:] - y[cut:].mean()) ** 2))
    print(f"alpha={alpha} MAE={mae:.1f} R2={r2:.3f}", flush=True)
    if best is None or mae < best[0]:
        best = (mae, r2, alpha, m)
mae, r2, alpha, m = best
w = m.coef_[:1260].reshape(14, 10, 9).astype(np.float32)
wf = np.array(m.coef_[1260:], dtype=np.float32)
b = float(m.intercept_)
np.savez(HERE / "data/linear_static_aug.npz", w=w, wf=wf, b=b)
print("saved", mae, r2, alpha, "wf", wf.round(2).tolist())
