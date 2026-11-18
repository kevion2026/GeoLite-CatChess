"""从随机残局起步，让皮卡鱼对走十几步，途中采样训练局面。

为什么不在随机摆法上直接打标签：
  随机摆子会产生大量「一步杀 / 白吃一车」局面，皮卡鱼标签清一色 ±29000，
  静态评估根本学不到东西（实测教科书残局 8 个随机摆法里 5 个是绝杀分）。
  让引擎先把这些战术噪音走掉，采到的局面才是「静态评估该负责」的局面。

每个起点走 --plies 步，在 keep 指定的 ply 采样，一个起点产出 4 个局面。

输出 data/endgame_plays.pkl：[{"board": [...], "side": 1/-1, "cfg": str}]
"""
import argparse
import collections
import pathlib
import pickle
import random
import time
from concurrent.futures import ProcessPoolExecutor

import board as B
import gen_endgames as G
from gen_pika_values2 import Engine, fen_of
from match_pikafish import uci_to_mv

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "data" / "endgame_plays.pkl"


class SafeEngine:
    """引擎可能因异常局面直接退出，这里负责重建。"""

    def __init__(self):
        self.eng = None
        self.restarts = 0

    def get(self):
        if self.eng is None:
            self.eng = Engine()
        return self.eng

    def drop(self):
        if self.eng is not None:
            try:
                self.eng.close()
            except Exception:
                pass
        self.eng = None
        self.restarts += 1


def playout(eng, b, side, plies, nodes, keep):
    b = list(b)
    out = []
    for ply in range(1, plies + 1):
        mvlist = B.gen_legal(b, side)
        if not mvlist:
            return out, "mate"
        u = eng.get().best(fen_of(b, side), nodes=nodes)
        mv = uci_to_mv(u or "")
        if mv is None:
            return out, "badmove"
        mv = (mv // 100, mv % 100)
        if mv not in mvlist:
            return out, "illegal"
        B.apply_move(b, mv)
        side = -side
        if ply in keep and B.gen_legal(b, side):
            out.append((list(b), side))
    return out, "ok"


def make_start(rng):
    """按 CONFIGS 权重抽一个子力配置，摆出一个合法残局起点。"""
    r = rng.random() * WEIGHT_SUM
    i = 0
    while CUM[i] < r:
        i += 1
    mr, mb = G.CONFIGS[i][0], G.CONFIGS[i][1]
    if rng.random() < 0.5:
        mr, mb = mb, mr
    for _ in range(40):
        got = G.make(rng, mr, mb)
        if got:
            return got, "%s|%s" % ("".join(map(str, mr)), "".join(map(str, mb)))
    return None, None


CUM, WEIGHT_SUM = [], 0
for _c in G.CONFIGS:
    WEIGHT_SUM += _c[2]
    CUM.append(WEIGHT_SUM)


def worker(args):
    lo, hi, seed, plies, nodes, keep = args
    rng = random.Random(seed * 1000003 + lo)
    eng = SafeEngine()
    rows = []
    stats = collections.Counter()
    t0 = time.time()
    try:
        for gi in range(lo, hi):
            got, cfg = make_start(rng)
            if not got:
                stats["nostart"] += 1
                continue
            try:
                pos, why = playout(eng, got[0], got[1], plies, nodes, keep)
            except RuntimeError:
                eng.drop()
                stats["crash"] += 1
                continue
            stats[why] += 1
            for b, s in pos:
                rows.append({"board": b, "side": s, "cfg": cfg})
            if (gi - lo + 1) % 500 == 0:
                print("  [%d-%d] %d/%d  %.0fs  %s"
                      % (lo, hi, gi - lo + 1, hi - lo, time.time() - t0,
                         dict(stats)), flush=True)
    finally:
        try:
            eng.get().close()
        except Exception:
            pass
    return rows, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--starts", type=int, default=60000)
    ap.add_argument("--plies", type=int, default=12)
    ap.add_argument("--nodes", type=int, default=6000)
    ap.add_argument("--keep", default="3,6,9,12")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    keep = set(int(x) for x in args.keep.split(",") if x.strip())
    n = args.starts
    per = (n + args.workers - 1) // args.workers
    tasks = []
    for i in range(0, n, per):
        tasks.append((i, min(i + per, n), args.seed, args.plies, args.nodes, keep))

    t0 = time.time()
    allrows, stats = [], collections.Counter()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for rows, st in ex.map(worker, tasks):
            allrows.extend(rows)
            stats.update(st)
    print("对走完成：%d 局面，%.0fs，%s" % (len(allrows), time.time() - t0, dict(stats)),
          flush=True)

    seen = set()
    uniq = []
    for r in allrows:
        k = (tuple(r["board"]), r["side"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    print("去重后 %d（原始 %d）" % (len(uniq), len(allrows)), flush=True)

    V = {1: 0, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}
    bands = collections.Counter()
    for r in uniq:
        m = sum(V[abs(p)] for p in r["board"] if p)
        if m < 400:
            bands["<400"] += 1
        elif m < 800:
            bands["400-800"] += 1
        elif m < 1400:
            bands["800-1400"] += 1
        elif m < 2200:
            bands["1400-2200"] += 1
        elif m < 3200:
            bands["2200-3200"] += 1
        else:
            bands["3200+"] += 1
    print("子力分布", dict(bands), flush=True)
    print("配置覆盖", len(set(r["cfg"] for r in uniq)), flush=True)
    pickle.dump(uniq, open(args.out, "wb"))
    print("写入", args.out, flush=True)


if __name__ == "__main__":
    main()
