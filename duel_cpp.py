"""C++ 引擎 / JS 引擎互相对打（A/B）。

用法：
  python duel_cpp.py --a cpp:xq16.exe:7 --b cpp:xq17.exe:7 --games 20
  python duel_cpp.py --a js:default --b cpp:xq17.exe:7 --games 16

spec 形式：cpp:<exe>:<depth>  或  cpp:<exe>:ms<毫秒>  或  js:<mode>
开局用固定种子的随机着法序列，双方共用同一开局、先后手交替，差异只来自引擎本身。
"""
import argparse
import json
import pathlib
import random
import statistics
import sys

import board as B
from bench_cpp import Cpp
from bench_positions import Srv


class Arm:
    def __init__(self, spec):
        parts = spec.split(":")
        self.kind = parts[0]
        if self.kind == "cpp":
            self.exe = parts[1]
            lim = parts[2] if len(parts) > 2 else "7"
            self.depth = 0 if lim.startswith("ms") else int(lim)
            self.ms = int(lim[2:]) if lim.startswith("ms") else 0
            self.eng = Cpp(self.exe)
        else:
            self.mode = parts[1] if len(parts) > 1 else "default"
            self.eng = Srv(self.mode)

    def best(self, board, side):
        if self.kind == "cpp":
            mv, _ = self.eng.best(board, side, self.depth, self.ms)
            return mv
        r = self.eng.best(board, side)
        return r.get("mv")

    def close(self):
        self.eng.close()


def play(a, b, a_is_red, max_ply, rng, open_plies):
    board = B.initial_board()
    side = B.RED
    plies = 0
    while plies < max_ply:
        lg = B.gen_legal(board, side)
        if not lg:
            # 无着可走：走子方负
            loser_is_a = (side == B.RED) == a_is_red
            return ("loss" if loser_is_a else "win"), plies
        codes = [f * 100 + t for (f, t) in lg]
        if plies < open_plies:
            mv = rng.choice(codes)
        else:
            arm = a if (side == B.RED) == a_is_red else b
            mv = arm.best(board, side)
            if mv not in codes:
                mv = codes[0]
        B.apply_move(board, (mv // 100, mv % 100))
        side = -side
        plies += 1
    return "draw", plies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="cpp:xq16.exe:7")
    ap.add_argument("--b", default="cpp:xq17.exe:7")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--open-plies", type=int, default=4)
    ap.add_argument("--max-ply", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    a, b = Arm(args.a), Arm(args.b)
    rows = []
    try:
        for i in range(args.games):
            rng = random.Random(args.seed * 1000 + i)
            a_is_red = (i % 2 == 0)
            res, plies = play(a, b, a_is_red, args.max_ply, rng, args.open_plies)
            rows.append({"game": i + 1, "a_side": "red" if a_is_red else "black", "res": res, "plies": plies})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    finally:
        a.close(); b.close()

    w = sum(1 for r in rows if r["res"] == "win")
    d = sum(1 for r in rows if r["res"] == "draw")
    l = sum(1 for r in rows if r["res"] == "loss")
    s = {"a": args.a, "b": args.b, "games": len(rows), "a_w": w, "draw": d, "a_l": l,
         "score": round((w + 0.5 * d) / len(rows), 3),
         "avg_plies": round(statistics.mean(r["plies"] for r in rows), 1)}
    print(json.dumps({"summary": s}, ensure_ascii=False))
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps({"summary": s, "rows": rows}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")


if __name__ == "__main__":
    main()
