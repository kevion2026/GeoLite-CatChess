"""带枷锁的实战采样：皮卡鱼限时 10ms 或 depth 1，双方脱谱，从合理开局起步。

每局保存：PGN 文本、逐着 FEN、皮卡鱼视角 cp、GeoLite 的路线与耗时。
"""

import argparse
import json
import pathlib
import random
import time

import board as B
from cloud_label import fen_of
from match_pikafish import Pika, Ours, mv_to_uci

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
LOGS = HERE / "data" / "battle_logs"

# 脱谱开局：红先合理着法 + 黑方常见应手（坐标取自 sq(x,y)=y*9+x）
OPENINGS = [
    ("炮二平五", [(1, 7, 4, 7), (7, 2, 4, 2)]),      # 中炮对列炮
    ("马八进七", [(7, 9, 6, 7), (1, 0, 2, 2)]),      # 起马对起马
    ("兵七进一", [(6, 6, 6, 5), (3, 3, 3, 4)]),      # 仙人指路对挺卒
    ("相三进五", [(6, 9, 4, 7), (2, 0, 4, 2)]),      # 飞相对金钩炮
]


def sqm(a, b, c, d):
    return (b * 9 + a) * 100 + (d * 9 + c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--kind", default="movetime")
    ap.add_argument("--value", type=int, default=10)
    ap.add_argument("--max-ply", type=int, default=200)
    ap.add_argument("--tag", default="run1")
    ap.add_argument("--minutes", type=float, default=0)
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--ours", default="_our_server.js")
    ap.add_argument("--engine", choices=["js", "cpp"], default="js")
    ap.add_argument("--exe", default="xq.exe")
    ap.add_argument("--our-ms", type=int, default=10000)
    ap.add_argument("--our-depth", type=int, default=0)
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    pika = Pika(args.kind, args.value)
    if args.engine == "cpp":
        from match_pikafish import OursCpp
        ours = OursCpp(ms=args.our_ms, depth=args.our_depth, exe=args.exe)
    else:
        ours = Ours(args.model, args.ours)
    summary = []
    t0 = time.time()
    try:
        for gi in range(args.games):
            if args.minutes and time.time() - t0 > args.minutes * 60:
                print(json.dumps({"stop": "time-limit", "games": len(summary)}, ensure_ascii=False), flush=True)
                break
            name, seq = OPENINGS[gi % len(OPENINGS)]
            rng = random.Random(gi * 7919 + 3)
            b = B.initial_board()
            side = B.RED
            ours_side = B.RED if gi % 2 == 0 else B.BLACK
            mvs, keys, uci_hist = [], [], []
            init_fen = fen_of(b, B.RED)
            plies = []
            result = "unfinished"
            rep = {}
            for ply in range(args.max_ply):
                lg = B.gen_legal(b, side)
                if not lg:
                    result = "loss" if side == ours_side else "win"
                    break
                fen_now = fen_of(b, side) + " - - 0 1"
                rep[fen_now] = rep.get(fen_now, 0) + 1
                if rep[fen_now] >= 3:
                    result = "draw"
                    break
                codes = [f * 100 + t for (f, t) in lg]
                cp = None
                if ply < len(seq):
                    a, c, d, e = seq[ply]
                    mv = sqm(a, c, d, e)
                    if mv not in codes:
                        mv = rng.choice(codes)
                elif side == ours_side:
                    r = ours.best(mvs, keys)
                    mv = r["mv"] if r["mv"] in codes else codes[0]
                else:
                    u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
                    mv = next((c for c in codes if mv_to_uci(c) == u), codes[0])
                plies.append({"ply": ply, "side": "red" if side == B.RED else "black",
                              "by": "pika" if side != ours_side else "geo",
                              "uci": mv_to_uci(mv),
                              "fen": fen_of(b, side) + " - - 0 1", "cp": cp, "board": list(b)})
                B.apply_move(b, (mv // 100, mv % 100))
                mvs.append(mv)
                uci_hist.append(mv_to_uci(mv))
                keys.append(hash(fen_of(b, -side)))
                side = -side
            if result == "unfinished":
                result = "draw"
            row = {"game": gi + 1, "opening": name, "ours": "red" if ours_side == B.RED else "black",
                   "res": result, "plies": len(plies), "limit": f"{args.kind}:{args.value}", "moves": plies}
            summary.append({k: row[k] for k in ("game", "opening", "ours", "res", "plies", "limit")})
            (LOGS / f"{args.tag}_g{gi + 1:03d}.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            # PGN 文本（UCI 着法，附皮卡鱼 cp 注释）
            pgn = [f'[Event "GeoLite vs Pikafish ({args.kind}:{args.value})"]',
                   f'[Game "{gi + 1}"]', f'[Opening "{name}"]',
                   f'[Result "{result}"]', ""]
            body, line = [], []
            for p in plies:
                line.append(p["uci"] + (f" {{cp {p['cp']}}}" if p["cp"] is not None else ""))
                if len(line) >= 6:
                    body.append(" ".join(line)); line = []
            if line:
                body.append(" ".join(line))
            pgn += body
            (LOGS / f"{args.tag}_g{gi + 1:03d}.pgn").write_text("\n".join(pgn), encoding="utf-8")
            print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
    finally:
        ours.close()
        pika.close()
    (LOGS / f"{args.tag}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(summary)
    print(json.dumps({"games": n, "w": sum(1 for r in summary if r['res'] == 'win'),
                      "d": sum(1 for r in summary if r['res'] == 'draw'),
                      "l": sum(1 for r in summary if r['res'] == 'loss'),
                      "avg_plies": round(sum(r['plies'] for r in summary) / n, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
