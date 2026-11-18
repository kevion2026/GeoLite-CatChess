"""生成策略头训练数据：局面平面 + 候选着法平面 + 45 维几何 → 皮卡鱼是否选这步。
每个局面取 1 个正样本（皮卡鱼 movetime=50 的 bestmove）和最多 8 个负样本。
"""
import argparse, json, pickle, random, time
from pathlib import Path

import numpy as np

import board as B
from build_planes_200k import planes
from cloud_label import fen_of
from feats45 import feats45
from match_pikafish import Pika, mv_to_uci

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
COORDS = json.load(open(HERE / "model_value.json", encoding="utf-8"))
AC = (COORDS["coords3a"], COORDS["coords3b"], COORDS["coords3c"])


def move_planes(mv):
    a = np.zeros((2, 10, 9), np.uint8)
    f, t = mv // 100, mv % 100
    a[0, f // 9, f % 9] = 1
    a[1, t // 9, t % 9] = 1
    return a.reshape(-1)


def one(b, side, mv):
    return np.concatenate([planes(b, side).reshape(-1), move_planes(mv),
                           feats45(b, side, *AC).astype(np.float32)]).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--neg", type=int, default=8)
    ap.add_argument("--out", default="data/policy_rows.npz")
    args = ap.parse_args()
    rows = pickle.load(open(HERE / "data/positions_200k.pkl", "rb"))
    stride = max(1, len(rows) // args.n)
    sample = rows[::stride][:args.n]
    pika = Pika(limit_kind="movetime", limit=50)
    X, y = [], []
    t0 = time.time()
    for i, (b, side, src) in enumerate(sample):
        if len(B.gen_legal(b, side)) < 2:
            continue
        best, cp, dep = pika.best(fen_of(b, side))
        mv = None
        if best:
            from match_pikafish import uci_to_mv
            mv = uci_to_mv(best)
        if mv is None:
            continue
        legal = [f * 100 + t for f, t in B.gen_legal(b, side)]
        if mv not in legal:
            continue
        X.append(one(b, side, mv)); y.append(1)
        negs = [m for m in legal if m != mv]
        random.Random(20261117 + i).shuffle(negs)
        for m in negs[:args.neg]:
            X.append(one(b, side, m)); y.append(0)
        if (i + 1) % 200 == 0:
            print(f"policy {i+1}/{len(sample)} rows {len(y)} {time.time()-t0:.0f}s", flush=True)
    pika.close()
    X = np.stack(X); y = np.array(y, np.int8)
    np.savez(HERE / args.out, X=X, y=y)
    print("saved", args.out, X.shape, "pos", int(y.sum()), "sec", round(time.time() - t0, 1), flush=True)


if __name__ == "__main__":
    main()
