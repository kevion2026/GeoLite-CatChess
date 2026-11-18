"""实战数据采集：本引擎 vs 皮卡鱼，逐手记录局面、双方着法与皮卡鱼评分。

为什么不复用 bench_pika.py 的产物：它只存每局的汇总（手数、cp20），
而"知彼"要学的是**对手在被给定局面下实际走了哪一步**，必须保留完整轨迹。

产出 data/battle_ds.json：
  {"meta": {...}, "games": [{"ours_red": bool, "res": str,
                             "rows": [[board90, side, mv, who, cp], ...]}, ...]}
  who: 1=我方走, 0=皮卡鱼走；cp 仅在皮卡鱼走子时有值（皮卡鱼视角，正=它占优）。

用法：
  python collect_battle.py --games 120 --out data/battle_ds.json
"""

import argparse
import json
import os
import pathlib
import random
import subprocess
import time

import board as B
from cloud_label import fen_of
from match_pikafish import Pika, mv_to_uci

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE / "engine3d.js"
SERVER = HERE / "_our_server.js"

OPENINGS = [
    [(1, 7, 4, 7), (7, 2, 4, 2)],
    [(7, 9, 6, 7), (1, 0, 2, 2)],
    [(6, 6, 6, 5), (3, 3, 3, 4)],
    [(6, 9, 4, 7), (2, 0, 4, 2)],
]


def sqm(a, b, c, d):
    return (b * 9 + a) * 100 + (d * 9 + c)


class Ours:
    def __init__(self, model, mode, seed):
        env = dict(os.environ)
        env["GEO_SEED"] = str(seed)
        self.p = subprocess.Popen(
            ["node", str(SERVER), str(HERE / model), str(ENGINE), mode],
            cwd=str(HERE), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1, env=env)

    def best(self, mvs):
        self.p.stdin.write(json.dumps({"mvs": mvs}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError((self.p.stderr.read() or "")[:800])
        return json.loads(line)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def one_game(ours, pika, ours_red, seed, open_plies, max_ply):
    """一局对局，返回完整逐手轨迹。"""
    rng = random.Random(seed * 7919 + 11)
    seq = list(OPENINGS[seed % len(OPENINGS)])
    probe = B.initial_board()
    side = B.RED
    for (fx, fy, tx, ty) in seq:
        B.apply_move(probe, (fy * 9 + fx, ty * 9 + tx))
        side = -side
    for _ in range(open_plies):
        lg = B.gen_legal(probe, side)
        mv = rng.choice(lg)
        seq.append((mv[0] % 9, mv[0] // 9, mv[1] % 9, mv[1] // 9))
        B.apply_move(probe, mv)
        side = -side

    b = B.initial_board()
    side = B.RED
    mvs, uci_hist, rows = [], [], []
    reps = {}
    init_fen = fen_of(b, B.RED)
    ours_side = B.RED if ours_red else B.BLACK
    res, plies = "draw", 0
    cp_track = {}

    for ply in range(max_ply):
        lg = B.gen_legal(b, side)
        if not lg:
            res = "loss" if side == ours_side else "win"
            break
        codes = [f * 100 + t for (f, t) in lg]
        if ply < len(seq):
            a_, c_, d_, e_ = seq[ply]
            mv = sqm(a_, c_, d_, e_)
            if mv not in codes:
                mv = codes[0]
            who, cp = 0, None
        elif side == ours_side:
            r = ours.best(mvs)
            mv = r.get("mv")
            if not mv or mv not in codes:
                res = "illegal"
                break
            who, cp = 1, None
        else:
            u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
            mv = next((c for c in codes if mv_to_uci(c) == u), None)
            if mv is None:
                mv = codes[0]
            who = 0
            if cp is not None:
                cp_track[ply] = cp      # 皮卡鱼视角：正数=它占优

        rows.append([list(b), side, mv, who, cp])
        B.apply_move(b, (mv // 100, mv % 100))
        mvs.append(mv)
        uci_hist.append(mv_to_uci(mv))
        side = -side
        plies = ply + 1
        k = fen_of(b, side)
        reps[k] = reps.get(k, 0) + 1
        if reps[k] >= 3:
            res = "draw"
            break

    def cp_at(target):
        if not cp_track:
            return None
        best = min(cp_track, key=lambda p: abs(p - target))
        return cp_track[best]

    return {"res": res, "plies": plies, "ours_red": ours_red, "rows": rows,
            "cp10": cp_at(10), "cp20": cp_at(20), "cp30": cp_at(30)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--mode", default="default")
    ap.add_argument("--limit", default="movetime:10")
    ap.add_argument("--games", type=int, default=120)
    ap.add_argument("--open-plies", type=int, default=0)
    ap.add_argument("--max-ply", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="data/battle_ds.json")
    args = ap.parse_args()

    kind, val = args.limit.split(":")
    pika = Pika(kind, int(val))
    ours = Ours(args.model, args.mode, args.seed)
    games = []
    t0 = time.time()
    try:
        for i in range(args.games):
            g = one_game(ours, pika, i % 2 == 0, args.seed + i, args.open_plies, args.max_ply)
            g["game"] = i + 1
            games.append(g)
            if (i + 1) % 10 == 0:
                print("  %d/%d  %.0fs" % (i + 1, args.games, time.time() - t0), flush=True)
    finally:
        ours.close()
        pika.close()

    n = len(games)
    w = sum(1 for g in games if g["res"] == "win")
    d = sum(1 for g in games if g["res"] == "draw")
    l = sum(1 for g in games if g["res"] == "loss")
    s = {
        "mode": args.mode, "limit": args.limit, "games": n,
        "w": w, "d": d, "l": l,
        "avg_plies": round(sum(g["plies"] for g in games) / n, 1),
        "fast30": sum(1 for g in games if g["res"] == "loss" and g["plies"] <= 30),
        "fast20": sum(1 for g in games if g["res"] == "loss" and g["plies"] <= 20),
        "positions": sum(len(g["rows"]) for g in games),
        "secs": round(time.time() - t0, 1),
    }
    out = HERE / args.out
    out.write_text(json.dumps({"meta": s, "games": games}, ensure_ascii=False,
                              separators=(",", ":")), encoding="utf-8")
    print(json.dumps(s, ensure_ascii=False), flush=True)
    print("写入", out, "%.1f MB" % (out.stat().st_size / 1048576), flush=True)


if __name__ == "__main__":
    main()
