"""按类均衡重算三维模型的状态库（每类 200 例，共 1200），修掉检索库被多数类淹没的问题。"""

import json
import pickle

import numpy as np

import board as B
import geo
import train

with open("data/pgn_positions.pkl", "rb") as f:
    d = pickle.load(f)

model = json.load(open("model3d.json", encoding="utf-8"))
coords = model["coords3"]

pos = [(b, s) for (b, s) in d["positions"]]
labels = [train.situation(b, s) for (b, s) in pos]
by = {}
for i, lab in enumerate(labels):
    by.setdefault(lab, []).append(i)

rng = np.random.default_rng(42)
idx = []
for c in train.CLASSES:
    pool = by.get(c, [])
    take = rng.choice(pool, size=min(200, len(pool)), replace=False)
    idx.extend(int(i) for i in take)
print("库样本", len(idx), {c: sum(1 for i in idx if labels[i] == c) for c in train.CLASSES})

lib = {}
for layer in range(11):
    rows = []
    for i in idx:
        b, s = pos[i]
        v, _ = geo.state_of(b, s, coords, layers=layer, dim=3)
        rows.append([round(float(x), 3) for x in v])
    lib[str(layer)] = rows

model["library"] = {"states": lib, "labels": [train.CLASSES.index(labels[i]) for i in idx]}
json.dump(model, open("model3d.json", "w", encoding="utf-8"), ensure_ascii=False)
print("已更新 model3d.json 的 library")
