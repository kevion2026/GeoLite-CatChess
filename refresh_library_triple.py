"""按类均衡重算三空间模型的状态库（每类 500，共 3000）。"""

import json
import pickle

import numpy as np

import train
import triple3d

D = json.load(open("model_triple.json", encoding="utf-8"))
A, Bt, Ct = D["coords3a"], D["coords3b"], D["coords3c"]

d = pickle.load(open("data/pgn_positions.pkl", "rb"))
pos = d["positions"]
labels = [train.situation(b, s) for (b, s) in pos]
by = {}
for i, l in enumerate(labels):
    by.setdefault(l, []).append(i)

rng = np.random.default_rng(42)
idx = []
for c in train.CLASSES:
    pool = by.get(c, [])
    idx.extend(int(i) for i in rng.choice(pool, size=min(500, len(pool)), replace=False))
print("库样本", len(idx))

lib = {}
for layer in range(11):
    rows = []
    for i in idx:
        b, s = pos[i]
        v, _ = triple3d.state_triple(b, s, A, Bt, Ct, layers=layer)
        rows.append([round(float(x), 3) for x in v])
    lib[str(layer)] = rows

D["library"] = {"states": lib, "labels": [train.CLASSES.index(labels[i]) for i in idx]}
json.dump(D, open("model_triple.json", "w", encoding="utf-8"), ensure_ascii=False)
print("已更新 model_triple.json 的 library")
