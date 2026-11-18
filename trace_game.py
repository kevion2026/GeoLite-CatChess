"""逐手轨迹：把一局棋的皮卡鱼评分、我方子力差、我方着法全部打印出来，
用来定位「分数在哪一手、以什么方式崩掉」。"""
import argparse
import json
import random
import sys

import board as B
from bench_pika import Ours, OPENINGS, sqm
from cloud_label import fen_of
from match_pikafish import Pika, mv_to_uci

MV = {2: 200, 3: 200, 4: 400, 5: 900, 6: 450, 7: 100}


def material(b, side):
    s = 0
    for q in b:
        if not q:
            continue
        v = MV.get(abs(q), 0)
        s += v if (q > 0) == (side > 0) else -v
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="cls")
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--limit", default="movetime:10")
    args = ap.parse_args()
    kind, val = args.limit.split(":")
    pika = Pika(kind, int(val))
    ours = Ours("model_triple.json", args.mode, args.seed)
    for gi in range(args.games):
        seed = args.seed + gi
        rng = random.Random(seed * 7919 + 11)
        seq = list(OPENINGS[seed % len(OPENINGS)])
        probe = B.initial_board()
        side = B.RED
        for (fx, fy, tx, ty) in seq:
            B.apply_move(probe, (fy * 9 + fx, ty * 9 + tx))
            side = -side
        for _ in range(3):
            lg = B.gen_legal(probe, side)
            mv = rng.choice(lg)
            seq.append((mv[0] % 9, mv[0] // 9, mv[1] % 9, mv[1] // 9))
            B.apply_move(probe, mv)
            side = -side

        b = B.initial_board()
        side = B.RED
        ours_red = gi % 2 == 0
        mvs, uci_hist = [], []
        init_fen = fen_of(b, B.RED)
        print(f"\n===== 第 {gi+1} 局  我方执{'红' if ours_red else '黑'} =====")
        print(f"{'ply':>4} {'方':>2} {'cp(皮卡鱼)':>10} {'子力差':>7}  着法")
        for ply in range(120):
            lg = B.gen_legal(b, side)
            if not lg:
                print("终局：无合法着法")
                break
            codes = [f * 100 + t for (f, t) in lg]
            if ply < len(seq):
                a_, c_, d_, e_ = seq[ply]
                mv = sqm(a_, c_, d_, e_)
                if mv not in codes:
                    mv = codes[0]
                tag = "开局"
            elif side == (B.RED if ours_red else B.BLACK):
                r = ours.best(mvs)
                mv = r.get("mv")
                if not mv or mv not in codes:
                    print("非法着法", mv)
                    break
                tag = f"我 {r.get('ms',0)}ms {r.get('by','')}"
            else:
                u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
                mv = next((c for c in codes if mv_to_uci(c) == u), None)
                if mv is None:
                    mv = codes[0]
                tag = ""
                print(f"{ply:>4} {('红' if side>0 else '黑'):>2} {str(cp):>10} {material(b, B.RED if ours_red else B.BLACK):>7}  {tag}")
                B.apply_move(b, (mv // 100, mv % 100))
                mvs.append(mv)
                uci_hist.append(mv_to_uci(mv))
                side = -side
                continue
            B.apply_move(b, (mv // 100, mv % 100))
            mvs.append(mv)
            uci_hist.append(mv_to_uci(mv))
            side = -side
    ours.close()
    pika.close()


if __name__ == "__main__":
    main()
