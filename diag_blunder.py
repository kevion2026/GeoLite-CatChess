"""失着归因：把我方每一手的 CPL 与「候选集是否包含参考最优着」对照，
判断棋力损失是来自候选生成（看不见）还是估值排序（看见了但不选）。

用法：python diag_blunder.py --mode cl0 --games 16 --ref 60
"""

import argparse
import json
import random
import statistics
import time

import board as B
from bench_pika import Ours, OPENINGS, sqm
from cloud_label import fen_of
from match_pikafish import Pika, mv_to_uci
from move_quality import analyse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="cl0")
    ap.add_argument("--games", type=int, default=16)
    ap.add_argument("--ref", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-ply", type=int, default=120)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    pika = Pika("movetime", 10)
    ours = Ours("model_triple.json", args.mode, args.seed)
    rows = []
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
            me = B.RED if gi % 2 == 0 else B.BLACK
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
                    if r.get("by") == "book":
                        B.apply_move(b, (mv // 100, mv % 100))
                        mvs.append(mv)
                        uci_hist.append(mv_to_uci(mv))
                        side = -side
                        continue
                    b_uci, b_cp, b_mate = analyse(pika, b, side, args.ref)
                    b_after = b[:]
                    B.apply_move(b_after, (mv // 100, mv % 100))
                    _, a_cp, a_mate = analyse(pika, b_after, -side, args.ref)
                    if b_cp is not None and a_cp is not None:
                        cpl = max(-50, min(1500, b_cp + a_cp))
                        best_mv = None
                        if b_uci:
                            for c in codes:
                                if mv_to_uci(c) == b_uci:
                                    best_mv = c
                                    break
                        cands = r.get("cands") or []
                        rows.append({"ply": ply, "cpl": cpl,
                                     "in_cand": bool(best_mv and best_mv in cands),
                                     "rank": (cands.index(mv) if mv in cands else -1),
                                     "is_top": r.get("top") == mv,
                                     "chosen_is_capture": B.is_capture(b, (mv // 100, mv % 100)),
                                     "best_is_capture": bool(best_mv and B.is_capture(b, (best_mv // 100, best_mv % 100))),
                                     "mat": None})
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

    def stat(key, val):
        v = [r["cpl"] for r in rows if r[key] == val]
        return (len(v), round(statistics.mean(v), 1)) if v else (0, None)

    n = len(rows)
    hit = sum(1 for r in rows if r["in_cand"])
    print(json.dumps({
        "mode": args.mode, "moves": n,
        "cpl_all": round(statistics.mean([r["cpl"] for r in rows]), 1),
        "best_in_candidates": round(hit / n, 3),
        "cpl_when_hit": stat("in_cand", True)[1],
        "cpl_when_miss": stat("in_cand", False)[1],
        "miss_count": n - hit,
        "blunders": sum(1 for r in rows if r["cpl"] > 200),
        "blunders_missed_best": sum(1 for r in rows if r["cpl"] > 200 and not r["in_cand"]),
        "top1_rate": round(sum(1 for r in rows if r["is_top"]) / n, 3),
        "secs": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1))
    if args.out:
        import pathlib
        pathlib.Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
