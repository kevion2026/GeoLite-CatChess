"""量出 depth8 标签的噪声：同一批局面用 depth8 / depth12 / depth16 分别标注，看差异。

如果 depth8 与 depth16 的分歧很大，说明训练标签本身就是瓶颈，
重标（更深的皮卡鱼）比改模型结构更值得。
"""
import argparse
import json
import pathlib
import pickle
import random
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen_pika_values2 import Engine, fen_of


def work(args):
    boards, sides, depths = args
    outs = {d: [] for d in depths}
    eng = Engine()
    try:
        for b, s in zip(boards, sides):
            fen = fen_of(b, s)
            for d in depths:
                outs[d].append(eng.label(fen, depth=d, movetime=0))
    finally:
        eng.close()
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--depths", default="8,12,16")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default="data/label_noise.json")
    args = ap.parse_args()

    rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
    rng = random.Random(args.seed)
    pick = rng.sample(range(len(rows)), args.n)
    boards = [rows[i]["board"] for i in pick]
    sides = [rows[i]["side"] for i in pick]
    old = np.array([rows[i]["cp"] for i in pick], dtype=float)
    depths = [int(x) for x in args.depths.split(",")]

    per = (args.n + args.workers - 1) // args.workers
    tasks = [(boards[i:i + per], sides[i:i + per], depths) for i in range(0, args.n, per)]
    got = {d: [] for d in depths}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for part in ex.map(work, tasks):
            for d in depths:
                got[d].extend(part[d])
    res = {d: np.array(got[d], dtype=float) for d in depths}

    ref = res[max(depths)]
    out = {"n": args.n, "depths": depths, "old_label": "stored"}
    print("同批 %d 局面：" % args.n)
    print("  存储标签 vs depth%-3d: MAD %6.1f  corr %.4f  bias %+.1f"
          % (max(depths), np.mean(np.abs(np.clip(old, -1500, 1500) - np.clip(ref, -1500, 1500))),
             np.corrcoef(np.clip(old, -1500, 1500), np.clip(ref, -1500, 1500))[0, 1],
             np.mean(old - ref)))
    for d in depths:
        if d == max(depths):
            continue
        a, b = np.clip(res[d], -1500, 1500), np.clip(ref, -1500, 1500)
        mad = float(np.mean(np.abs(a - b)))
        print("  depth%-3d vs depth%-3d: MAD %6.1f  corr %.4f  |diff|>100 占 %.1f%%"
              % (d, max(depths), mad, np.corrcoef(a, b)[0, 1], 100 * np.mean(np.abs(a - b) > 100)))
        out["d%d_vs_d%d" % (d, max(depths))] = {"mad": mad, "corr": float(np.corrcoef(a, b)[0, 1])}
    calm = np.abs(np.clip(ref, -1500, 1500)) < 150
    print("  均势子集 n=%d：" % calm.sum())
    for d in depths:
        if d == max(depths):
            continue
        a, b = np.clip(res[d][calm], -1500, 1500), np.clip(ref[calm], -1500, 1500)
        if len(a) > 10:
            print("    depth%-3d vs depth%-3d: MAD %6.1f  corr %.4f"
                  % (d, max(depths), np.mean(np.abs(a - b)), np.corrcoef(a, b)[0, 1]))
    pathlib.Path(HERE / args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
