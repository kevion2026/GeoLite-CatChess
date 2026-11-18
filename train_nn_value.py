"""训练神经价值头：10×9×14 棋子平面 + 45 维几何特征 → 皮卡鱼 cp。
几何特征作为显式输入，保证几何在神经评估里仍有一席之地。
"""
import io, json, pickle, time
from pathlib import Path

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
ROWS = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
PLANES = np.load(HERE / "data/planes_200k.npy")
GEO = np.load(HERE / "data/value45_cache_200k.npz")["X"].astype(np.float32)
Y = np.array([np.clip(float(r["cp"]), -1500, 1500) / 1000.0 for r in ROWS], np.float32)
assert len(PLANES) == len(GEO) == len(Y)

rng = np.random.default_rng(20261117)
idx = rng.permutation(len(Y))
tr = idx[:120000]
te = idx[120000:150000]
Xtr = np.concatenate([PLANES[tr].astype(np.float32), GEO[tr]], axis=1)
Xte = np.concatenate([PLANES[te].astype(np.float32), GEO[te]], axis=1)
sc = StandardScaler().fit(Xtr)
Xtr = sc.transform(Xtr).astype(np.float32)
Xte = sc.transform(Xte).astype(np.float32)
print("train", Xtr.shape, "val", Xte.shape, flush=True)

t0 = time.time()
m = MLPRegressor(hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                 alpha=1e-4, batch_size=512, learning_rate_init=1e-3,
                 max_iter=25, early_stopping=True, validation_fraction=0.1,
                 n_iter_no_change=5, random_state=0, verbose=True)
m.fit(Xtr, Y[tr])
p = m.predict(Xte) * 1000.0
yt = Y[te] * 1000.0
mae = float(np.mean(np.abs(p - yt)))
r2 = float(1 - ((p - yt) ** 2).sum() / ((yt - yt.mean()) ** 2).sum())
print("NN value MAE", round(mae, 1), "R2", round(r2, 3), "iters", m.n_iter_, "sec", round(time.time() - t0, 1), flush=True)

pickle.dump({"model": m, "scaler": sc, "metrics": {"mae": mae, "r2": r2}}, open(HERE / "model_value_nn.pkl", "wb"))
layers = []
for w, b in zip(m.coefs_, m.intercepts_):
    layers.append({"w": [round(float(x), 6) for x in w.ravel()], "b": [round(float(x), 6) for x in b]})
out = {"kind": "mlp", "in": int(Xtr.shape[1]), "layers": layers,
       "mean": [round(float(x), 6) for x in sc.mean_],
       "std": [round(float(x), 6) for x in sc.scale_],
       "out_scale": 1000.0, "metrics": {"mae": mae, "r2": r2},
       "hidden": [128, 64]}
json.dump(out, io.open(HERE / "model_value_nn.json", "w", encoding="utf-8"), ensure_ascii=False)
print("saved model_value_nn.json", flush=True)
