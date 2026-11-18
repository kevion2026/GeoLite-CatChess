"""残局专项对打：从给定的残局局面开局，比较两个引擎的残局功力。

用法：
  python duel_endgame.py --a CatChess-v2.0.exe --b CatChess-v2.1.exe --games 40 --ms 100
起手局面取自 data/pika_values_endgame.pkl 里「均势但仍有子力」的样本，
两边轮换先后手，开局相同，差异只来自引擎。

胜负判定：无合法着法者负（象棋困毙也算负）；超过 --max-ply 判和。
"""
import argparse
import json
import pathlib
import pickle
import random
import statistics

import board as B
from bench_cpp import Cpp
from cloud_label import fen_of

HERE = pathlib.Path(__file__).resolve().parent
MATV = {1: 0, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}


def pick_starts(path, n, seed, lo_mat, hi_mat, max_abs_cp, min_abs_cp=0):
    rows = pickle.load(open(HERE / path, "rb"))
    cand = []
    for r in rows:
        if r.get("cp") is None:
            continue
        m = sum(MATV[abs(p)] for p in r["board"] if p)
        if not (lo_mat <= m <= hi_mat):
            continue
        if abs(r["cp"]) > max_abs_cp:
            continue
        cand.append(r)
    random.Random(seed).shuffle(cand)
    # 按子力分档轮取，保证覆盖而不是集中在一档
    bands = {}
    for r in cand:
        m = sum(MATV[abs(p)] for p in r["board"] if p)
        b = 0 if m < 900 else 1 if m < 1500 else 2 if m < 2300 else 3
        bands.setdefault(b, []).append(r)
    out = []
    k = 0
    while len(out) < n and any(bands.values()):
        b = k % 4
        k += 1
        if bands.get(b):
            out.append(bands[b].pop())
    return out


def play(a, b, start, a_is_red, ms, max_ply):
    board = list(start)
    side = B.RED
    for ply in range(max_ply):
        lg = B.gen_legal(board, side)
        if not lg:
            loser_is_a = (side == B.RED) == a_is_red
            return ("loss" if loser_is_a else "win"), ply
        arm = a if (side == B.RED) == a_is_red else b
        mv, _ = arm.best(board, side, 0, ms)
        codes = [f * 100 + t for (f, t) in lg]
        if mv not in codes:
            mv = codes[0]
        B.apply_move(board, (mv // 100, mv % 100))
        side = -side
    return "draw", max_ply


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="CatChess-v2.0.exe")
    ap.add_argument("--b", default="CatChess-v2.0.exe")
    ap.add_argument("--pos", default="data/pika_values_endgame.pkl")
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--ms", type=int, default=100)
    ap.add_argument("--max-ply", type=int, default=160)
    ap.add_argument("--lo-mat", type=int, default=800)
    ap.add_argument("--hi-mat", type=int, default=2600)
    ap.add_argument("--max-cp", type=int, default=260)
    ap.add_argument("--min-cp", type=int, default=0)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    starts = pick_starts(args.pos, (args.games + 1) // 2, args.seed,
                         args.lo_mat, args.hi_mat, args.max_cp, args.min_cp)
    print("起手残局 %d 个" % len(starts), flush=True)
    ea, eb = Cpp(args.a), Cpp(args.b)
    rows = []
    try:
        for i in range(args.games):
            st = starts[i // 2]
            a_is_red = (i % 2 == 0)
            res, plies = play(ea, eb, st["board"], a_is_red, args.ms, args.max_ply)
            m = sum(MATV[abs(p)] for p in st["board"] if p)
            rows.append({"game": i + 1, "a_red": a_is_red, "res": res,
                         "plies": plies, "mat": m, "cp0": st["cp"]})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    finally:
        ea.close()
        eb.close()

    w = sum(1 for r in rows if r["res"] == "win")
    d = sum(1 for r in rows if r["res"] == "draw")
    l = sum(1 for r in rows if r["res"] == "loss")
    s = {"a": args.a, "b": args.b, "ms": args.ms, "games": len(rows),
         "a_w": w, "draw": d, "a_l": l,
         "score": round((w + 0.5 * d) / len(rows), 3),
         "avg_plies": round(statistics.mean(r["plies"] for r in rows), 1)}
    print(json.dumps({"summary": s}, ensure_ascii=False))
    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps({"summary": s, "rows": rows}, ensure_ascii=False, indent=1),
            encoding="utf-8")


if __name__ == "__main__":
    main()
