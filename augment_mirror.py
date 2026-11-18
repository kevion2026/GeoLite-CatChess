"""左右镜像数据增强：象棋左右对称，镜像后评估值不变。

把 20 万局面扩成 40 万，是免费的正则化——模型不该学出左右偏向。
镜像必须与原始样本落在同一侧（训练/验证切分在增强前按原索引做）。

用法：
  python augment_mirror.py --out data/value45_cache_400k.npz
"""
import argparse
import json
import pathlib
import pickle
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from feats45 import feats45


def mirror_board(board, side):
    nb = [0] * 90
    for y in range(10):
        row = y * 9
        for x in range(9):
            nb[row + x] = -int(board[row + (8 - x)])
    return nb, side


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/pika_values_200k.pkl")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--out", default="data/value45_cache_400k.npz")
    args = ap.parse_args()

    rows = pickle.load(open(HERE / args.src, "rb"))
    M = json.load(open(HERE / args.model, encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])
    n = len(rows)
    X = np.zeros((2 * n, 45))
    y = np.zeros(2 * n)
    t0 = time.time()
    for i, r in enumerate(rows):
        b, s = r["board"], r["side"]
        X[i] = feats45(b, s, *AC)
        y[i] = float(np.clip(r["cp"], -1500, 1500))
        mb, ms = mirror_board(b, s)
        X[n + i] = feats45(mb, ms, *AC)
        y[n + i] = y[i]
        if (i + 1) % 20000 == 0:
            print("  %d/%d %.0fs" % (i + 1, n, time.time() - t0), flush=True)
    np.savez(HERE / args.out, X=X, y=y, n_orig=n)
    d = X[n:] - X[:n]
    print("镜像前后特征最大差 %.4f（接近 0 说明特征本身对称）" % np.abs(d).max())
    print("saved", args.out, X.shape)


if __name__ == "__main__":
    main()
