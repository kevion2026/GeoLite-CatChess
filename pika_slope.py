"""皮卡鱼自身节点梯子的 Elo 斜率标定。

作用：把「节点数」翻译成「Elo」。有了斜率，才能把
「本模型 ≈ 皮卡鱼 N 节点」换算成与满血皮卡鱼的 Elo 差距。

用法：
  python pika_slope.py --pairs 100:800,100:3200 --games 12
"""
import argparse
import json
import math
import pathlib
import random
import sys

import board as B
from cloud_label import fen_of
from match_pikafish import Pika

HERE = pathlib.Path(__file__).resolve().parent
START = fen_of(B.initial_board(), B.RED)


def elo_diff(score):
    s = min(max(score, 0.02), 0.98)
    return -400.0 * math.log10(1.0 / s - 1.0)


def play(hi, lo, hi_is_red, rng, open_plies, max_ply):
    bd = B.initial_board()
    side = B.RED
    hist = []
    reps = {fen_of(bd, side): 1}
    while len(hist) < max_ply:
        lg = B.gen_legal(bd, side)
        if not lg:
            hi_lost = (side == B.RED) == hi_is_red
            return ("loss" if hi_lost else "win"), len(hist)
        f = t = None
        if len(hist) < open_plies:
            f, t = rng.choice(lg)
        else:
            eng = hi if (side == B.RED) == hi_is_red else lo
            u = eng.best(START, hist=hist or None, init_fen=START)[0]
            if u and u not in ("0000", "(none)"):
                f = "abcdefghi".index(u[0]); t = "abcdefghi".index(u[2])
                f, t = (9 - int(u[1])) * 9 + f, (9 - int(u[3])) * 9 + t
        if (f, t) not in lg:
            f, t = lg[0]
        B.apply_move(bd, (f, t))
        hist.append("%s%d%s%d" % ("abcdefghi"[f % 9], 9 - f // 9,
                                  "abcdefghi"[t % 9], 9 - t // 9))
        side = -side
        k = fen_of(bd, side)
        reps[k] = reps.get(k, 0) + 1
        if reps[k] >= 3:
            return "draw", len(hist)
    return "draw", len(hist)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="100:800")
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--open-plies", type=int, default=4)
    ap.add_argument("--max-ply", type=int, default=160)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default="data/pika_slope.json")
    args = ap.parse_args()

    rows = []
    for pair in args.pairs.split(","):
        na, nb = [int(x) for x in pair.split(":")]
        hi, lo = Pika(limit_kind="nodes", limit=na), Pika(limit_kind="nodes", limit=nb)
        w = d = l = 0
        try:
            for i in range(args.games):
                rng = random.Random(args.seed * 7919 + na * 31 + nb * 7 + i)
                hi_is_red = (i % 2 == 0)
                res, plies = play(hi, lo, hi_is_red, rng, args.open_plies, args.max_ply)
                w += res == "win"; d += res == "draw"; l += res == "loss"
                print(json.dumps({"hi": na, "lo": nb, "game": i + 1,
                                  "hi_side": "red" if hi_is_red else "black",
                                  "res": res, "plies": plies}), flush=True)
        finally:
            hi.close(); lo.close()
        score = (w + 0.5 * d) / args.games
        el = elo_diff(score)
        per_dbl = el / math.log2(na / nb)
        rows.append({"hi_nodes": na, "lo_nodes": nb, "w": w, "d": d, "l": l,
                     "score": round(score, 3), "elo_gap": round(el, 0),
                     "elo_per_doubling": round(per_dbl, 1)})
        print(json.dumps({"pair": rows[-1]}), flush=True)

    pathlib.Path(args.out).write_text(json.dumps({"rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps({"done": str(args.out)}))


if __name__ == "__main__":
    main()
