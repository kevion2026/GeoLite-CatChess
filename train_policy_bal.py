"""策略头：按局面分组切分 + 正样本过采样，解决 1:8 类别不平衡导致的“全预测负样本”。"""
import io, json, pickle, time
from pathlib import Path

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
z = np.load(HERE / "data/policy_rows.npz")
X, y = z["X"], z["y"]
block = 9
groups = np.arange(len(y)) // block
valg = (groups % 10 == 0)
tr = ~valg
# 正样本复制 8 次，让正负比例接近 1:1
pos = np.where(tr & (y == 1))[0]
tr_idx = np.concatenate([np.where(tr)[0], np.repeat(pos, 8)])
sc = StandardScaler().fit(X[tr_idx])
Xtr = sc.transform(X[tr_idx]).astype(np.float32)
Xte = sc.transform(X[valg]).astype(np.float32)
yte = y[valg]
print("train", Xtr.shape, "val", Xte.shape, "pos", int(yte.sum()), flush=True)
t0 = time.time()
m = MLPClassifier(hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                  alpha=1e-4, batch_size=256, learning_rate_init=1e-3,
                  max_iter=20, early_stopping=False, random_state=0, verbose=True)
m.fit(Xtr, y[tr_idx])
p = m.predict_proba(Xte)[:, 1]
hit = 0; tot = 0
for i in range(0, len(p), block):
    b = p[i:i + block]
    if len(b) < 2: continue
    tot += 1
    if b[0] >= b[1:].max(): hit += 1
acc = float(((p >= .5) == yte).mean())
print("policy acc", round(acc, 3), "top1", round(hit / max(1, tot), 3),
      "iters", m.n_iter_, "sec", round(time.time() - t0, 1), flush=True)
pickle.dump({"model": m, "scaler": sc, "metrics": {"acc": acc, "top1": hit / max(1, tot)}},
            open(HERE / "model_policy_bal.pkl", "wb"))
layers = [{"w": [round(float(x), 6) for x in w.ravel()],
           "b": [round(float(x), 6) for x in b]} for w, b in zip(m.coefs_, m.intercepts_)]
json.dump({"kind": "policy", "in": int(Xtr.shape[1]), "layers": layers,
           "mean": [round(float(x), 6) for x in sc.mean_],
           "std": [round(float(x), 6) for x in sc.scale_],
           "metrics": {"acc": acc, "top1": hit / max(1, tot)}},
          io.open(HERE / "model_policy.json", "w", encoding="utf-8"), ensure_ascii=False)
print("saved model_policy.json", flush=True)
