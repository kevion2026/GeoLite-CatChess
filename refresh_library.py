"""只重算前端检索库（按类别均衡抽样），保留其余训练结果。

检索库只影响页面里“最近邻命中了哪些态势”，不参与五折指标；
按类别均衡抽样可以避免库被多数类（攻王压迫）淹没。
"""

import io
import json
import pickle
import random

import numpy as np

import board as B
import geo
import train

PER_CLASS = 200


def main():
    with open("model.json", encoding="utf-8") as f:
        m = json.load(f)
    coords = {k: tuple(v) for k, v in m["coords2"].items()}
    classes = m["meta"]["classes"]

    positions = train.build_corpus(200)
    with open("data/pgn_positions.pkl", "rb") as f:
        real = pickle.load(f)["positions"]
    positions.extend((b, s, train.situation(b, s)) for (b, s) in real)

    by_cls = {c: [] for c in classes}
    for p in positions:
        by_cls[p[2]].append(p)
    rng = random.Random(11)
    picked = []
    for c in classes:
        v = by_cls[c]
        picked.extend(rng.sample(v, min(PER_CLASS, len(v))))
    print("库样本", len(picked), {c: len(v) for c, v in by_cls.items()})

    lib = {}
    labels = [classes.index(p[2]) for p in picked]
    for layer in range(11):
        rows = []
        for b, s, _ in picked:
            v, _ = geo.state_of(b, s, coords, layers=layer)
            rows.append([round(float(x), 3) for x in v])
        lib[str(layer)] = rows
        print("layer", layer, "ok", flush=True)

    m["library"] = {"states": lib, "labels": labels, "per_class": PER_CLASS}
    with io.open("model.json", "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)
    print("已更新检索库")


if __name__ == "__main__":
    main()
