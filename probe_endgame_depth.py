"""探测：皮卡鱼在残局局面上的标签随深度/节点的稳定性。

结论用于决定「残局标签打多深」。输出各档位之间的相关系数、MAD，
以及若干教科书残局（单车对士象全等）在各档位下的评分。
"""
import argparse
import pickle
import random
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from gen_pika_values2 import Engine, fen_of

# (名称, 红方(车,炮,马,象,士,兵), 黑方, 短标签)
BOOK = [
    ("单车对士象全（理论例和）", (1, 0, 0, 0, 2, 0), (0, 0, 0, 2, 2, 0), "R-A2B2"),
    ("单车对双士（例胜）", (1, 0, 0, 0, 2, 0), (0, 0, 0, 0, 2, 0), "R-A2"),
    ("单车对单象（例胜）", (1, 0, 0, 0, 0, 0), (0, 0, 0, 1, 0, 0), "R-B1"),
    ("车兵对士象全（例胜）", (1, 0, 0, 0, 0, 1), (0, 0, 0, 2, 2, 0), "RP-A2B2"),
    ("马对士象全（例和）", (0, 0, 1, 0, 2, 0), (0, 0, 0, 2, 2, 0), "N-A2B2"),
    ("炮对双士（例和）", (0, 1, 0, 0, 2, 0), (0, 0, 0, 0, 2, 0), "C-A2"),
    ("车马对车士象全", (1, 0, 1, 0, 2, 0), (1, 0, 0, 2, 2, 0), "RN-RA2B2"),
]

SPECS = [
    {"tag": "d10", "depth": 10}, {"tag": "d12", "depth": 12},
    {"tag": "d14", "depth": 14}, {"tag": "d16", "depth": 16},
    {"tag": "n50k", "nodes": 50000}, {"tag": "n200k", "nodes": 200000},
    {"tag": "n800k", "nodes": 800000},
]


def book_positions(seed=7, per=8):
    import gen_endgames as G
    rng = random.Random(seed)
    out = []
    for name, red, blk, tag in BOOK:
        cand = []
        for _ in range(600):
            got = G.make(rng, red, blk)
            if got:
                cand.append(got)
            if len(cand) >= per:
                break
        out.append((name, tag, cand))
    return out


def work(args):
    allpos, specs = args
    eng = Engine()
    out = {}
    try:
        for sp in specs:
            vals = []
            for b, s in allpos:
                vals.append(eng.label(fen_of(b, s), sp.get("depth", 0),
                                      0, sp.get("nodes", 0)))
            out[sp["tag"]] = vals
    finally:
        eng.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pos", default="data/_eg_test.pkl")
    ap.add_argument("--no-book", action="store_true")
    args = ap.parse_args()

    rows = pickle.load(open(args.pos, "rb"))
    random.Random(11).shuffle(rows)
    rows = rows[:args.n]

    books = [] if args.no_book else book_positions()
    bookpos = []
    owner = []
    for name, tag, cand in books:
        for b, s in cand:
            bookpos.append((b, s))
            owner.append(tag)

    allpos = [(r["board"], r["side"]) for r in rows] + bookpos
    nrow = len(rows)

    t0 = time.time()
    # 每个 worker 都跑全部档位，但只负责一段局面
    n = len(allpos)
    per = (n + args.workers - 1) // args.workers
    chunks = []
    for i in range(0, n, per):
        chunks.append((allpos[i:i + per], SPECS))
    parts = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(work, chunks):
            parts.append(r)

    got = {sp["tag"]: [] for sp in SPECS}
    for r in parts:
        for k, v in r.items():
            got[k].extend(v)
    print("采样 %d + 教科书 %d 局面 × %d 档，用时 %.0fs"
          % (nrow, len(bookpos), len(SPECS), time.time() - t0), flush=True)

    ref = np.array(got["n800k"][:nrow], float)
    print("\n=== 相对 n800k 的稳定性（%d 个随机残局）===" % nrow)
    for sp in SPECS[:-1]:
        v = np.array(got[sp["tag"]][:nrow], float)
        d = np.abs(v - ref)
        print("%6s  corr %.4f  MAD %6.1f  p90 %6.1f  同号 %.1f%%  极值 %.1f%%"
              % (sp["tag"], np.corrcoef(v, ref)[0, 1], d.mean(),
                 np.percentile(d, 90), 100 * np.mean(np.sign(v) == np.sign(ref)),
                 100 * np.mean(np.abs(v) > 2000)))

    print("\n=== 教科书残局（红方视角 cp，正=红优）===")
    for name, tag, cand in books:
        idx = [i for i, o in enumerate(owner) if o == tag]
        print("\n" + name)
        for sp in SPECS:
            vv = [got[sp["tag"]][nrow + i] for i in idx]
            print("  %6s  %s   中位 %6d" % (sp["tag"], " ".join("%6d" % x for x in vv),
                                            int(np.median(vv))))


if __name__ == "__main__":
    main()
