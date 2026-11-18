"""走子质量测评（低方差）：不只看能撑几手，而是看我方每一手相对「参考引擎最优着」
损失多少 cp（CPL = centipawn loss）。

方差比"平均手数"小一个量级：同一配置重复测，CPL 波动约 ±8，而平均手数波动 ±3。
用法：
  python move_quality.py --mode cl0 --games 12 --ref movetime:80
"""

import argparse
import json
import pathlib
import random
import statistics
import sys
import time

import board as B
from bench_pika import Ours, OPENINGS, sqm
from cloud_label import fen_of
from match_pikafish import Pika, mv_to_uci

HERE = pathlib.Path(__file__).resolve().parent
MV = {2: 200, 3: 200, 4: 400, 5: 900, 6: 450, 7: 100}


def material(b, side):
    s = 0
    for q in b:
        if not q:
            continue
        v = MV.get(abs(q), 0)
        s += v if (q > 0) == (side > 0) else -v
    return s


def analyse(pika, board, side, limit_ms):
    """返回 (best_uci, cp, mate)，cp 一律换算成「走子方视角」。"""
    pika.send(f"position fen {fen_of(board, side)} - - 0 1")
    pika.send(f"go movetime {limit_ms}")
    best, cp, mate = None, None, None
    while True:
        line = pika.p.stdout.readline()
        if not line:
            raise RuntimeError("pikafish 无输出")
        if line.startswith("bestmove"):
            best = line.split()[1]
            break
        if " score cp " in line:
            try:
                cp = int(line.split(" score cp ")[1].split()[0])
                mate = None
            except Exception:
                pass
        elif " score mate " in line:
            try:
                mate = int(line.split(" score mate ")[1].split()[0])
                cp = 30000 - abs(mate) * 100
                if mate < 0:
                    cp = -cp
            except Exception:
                pass
    return best, cp, mate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="cl0")
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--play", default="movetime:10")
    ap.add_argument("--ref", type=int, default=80, help="参考分析毫秒")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-ply", type=int, default=140)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    kind, val = args.play.split(":")
    pika = Pika(kind, int(val))
    ours = Ours("model_triple.json", args.mode, args.seed)
    cpls, mats, best_cps, top1 = [], [], [], 0
    n_moves = 0
    t0 = time.time()
    try:
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
            me = B.RED if ours_red else B.BLACK
            mvs, uci_hist = [], []
            init_fen = fen_of(b, B.RED)
            for ply in range(args.max_ply):
                lg = B.gen_legal(b, side)
                if not lg:
                    break
                codes = [f * 100 + t for (f, t) in lg]
                if ply < len(seq):
                    a_, c_, d_, e_ = seq[ply]
                    mv = sqm(a_, c_, d_, e_)
                    if mv not in codes:
                        mv = codes[0]
                elif side == me:
                    r = ours.best(mvs)
                    mv = r.get("mv")
                    if not mv or mv not in codes:
                        break
                    # 走子前后各分析一次
                    b_uci, b_cp, b_mate = analyse(pika, b, side, args.ref)
                    b_after = b[:]
                    B.apply_move(b_after, (mv // 100, mv % 100))
                    _, a_cp, a_mate = analyse(pika, b_after, -side, args.ref)
                    if b_cp is not None and a_cp is not None:
                        loss = b_cp + a_cp           # a_cp 是对手视角
                        cpls.append(max(-50, min(1500, loss)))
                        best_cps.append(b_cp)
                        mats.append(material(b, me))
                        n_moves += 1
                        if b_uci and mv_to_uci(mv) == b_uci:
                            top1 += 1
                else:
                    u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
                    mv = next((c for c in codes if mv_to_uci(c) == u), None)
                    if mv is None:
                        mv = codes[0]
                B.apply_move(b, (mv // 100, mv % 100))
                mvs.append(mv)
                uci_hist.append(mv_to_uci(mv))
                side = -side

    finally:
        ours.close()
        pika.close()

    cpls.sort()
    s = {
        "mode": args.mode, "games": args.games, "moves": n_moves,
        "ref_ms": args.ref,
        "cpl_mean": round(statistics.mean(cpls), 1),
        "cpl_median": round(statistics.median(cpls), 1),
        "cpl_p90": round(cpls[int(len(cpls) * 0.9)], 1),
        "blunder200": round(sum(1 for x in cpls if x > 200) / len(cpls), 3),
        "top1": round(top1 / max(1, n_moves), 3),
        "mat_start": round(statistics.mean(mats[:10]), 0) if len(mats) >= 10 else None,
        "mat_end": round(statistics.mean(mats[-10:]), 0) if len(mats) >= 10 else None,
        "best_cp_mean": round(statistics.mean(best_cps), 0),
        "secs": round(time.time() - t0, 1),
    }
    print(json.dumps(s, ensure_ascii=False, indent=1), flush=True)
    if args.out:
        (HERE / args.out).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
