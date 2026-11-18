"""训练策略头：局面平面 + 候选着法平面 + 几何 → 皮卡鱼是否选这步。"""
import io, json, pickle, time
from pathlib import Path

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
z = np.load(HERE / "data/policy_rows.npz")
X, y = z["X"], z["y"]
idx = np.random.default_rng(20261118).permutation(len(y))
tr, te = idx[:int(len(y) * .9)], idx[int(len(y) * .9):]
sc = StandardScaler().fit(X[tr])
Xtr = sc.transform(X[tr]).astype(np.float32)
Xte = sc.transform(X[te]).astype(np.float32)
print("train", Xtr.shape, "pos", int(y[tr].sum()), flush=True)

t0 = time.time()
m = MLPClassifier(hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                  alpha=1e-4, batch_size=256, learning_rate_init=1e-3,
                  max_iter=30, early_stopping=True, validation_fraction=0.1,
                  n_iter_no_change=5, random_state=0, verbose=True)
m.fit(Xtr, y[tr])
p = m.predict_proba(Xte)[:, 1]
# 同一局面的正样本是否排在负样本之前
groups = len(y[te]) // 9
hit = 0; tot = 0
for g in range(groups):
    block = p[g * 9:(g + 1) * 9]
    if len(block) < 2: continue
    tot += 1
    if block[0] >= block[1:].max(): hit += 1
acc = float((p >= .5).mean() == 1) if False else float(((p >= .5) == y[te]).mean())
print("policy acc", round(acc, 3), "top1", round(hit / max(1, tot), 3),
      "iters", m.n_iter_, "sec", round(time.time() - t0, 1), flush=True)

pickle.dump({"model": m, "scaler": sc, "metrics": {"acc": acc, "top1": hit / max(1, tot)}},
            open(HERE / "model_policy.pkl", "wb"))
layers = []
for w, b in zip(m.coefs_, m.intercepts_):
    layers.append({"w": [round(float(x), 6) for x in w.ravel()], "b": [round(float(x), 6) for x in b]})
json.dump({"kind": "policy", "in": int(Xtr.shape[1]), "layers": layers,
           "mean": [round(float(x), 6) for x in sc.mean_],
           "std": [round(float(x), 6) for x in sc.scale_],
           "metrics": {"acc": acc, "top1": hit / max(1, tot)}},
          io.open(HERE / "model_policy.json", "w", encoding="utf-8"), ensure_ascii=False)
print("saved model_policy.json", flush=True)
