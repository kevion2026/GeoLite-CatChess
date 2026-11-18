"""固定标尺测评：同一批开局、同一套随机种子，把不同引擎配置逐一对上皮卡鱼。

用法：
  python bench_pika.py --mode pro3 --games 60
  python bench_pika.py --mode base --limit movetime:10 --games 60

输出胜平负、平均手数、≤30 手速败、≤20 手速败、单步耗时、被吃子数。
与 duel.py 的区别：对手固定（皮卡鱼），不会被对称改进互相抵消。
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
    mvs, uci_hist = [], []
    init_fen = fen_of(b, B.RED)
    ours_ms, caps_against, reps = [], 0, {}
    cp_track = {}
    res, plies = "draw", 0
    for ply in range(max_ply):
        lg = B.gen_legal(b, side)
        if not lg:
            res = "loss" if side == (B.RED if ours_red else B.BLACK) else "win"
            break
        codes = [f * 100 + t for (f, t) in lg]
        if ply < len(seq):
            a_, c_, d_, e_ = seq[ply]
            mv = sqm(a_, c_, d_, e_)
            if mv not in codes:
                mv = codes[0]
        elif side == (B.RED if ours_red else B.BLACK):
            r = ours.best(mvs)
            ours_ms.append(r.get("ms", 0))
            mv = r.get("mv")
            if not mv or mv not in codes:
                res = "illegal"
                break
        else:
            u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
            mv = next((c for c in codes if mv_to_uci(c) == u), None)
            if mv is None:
                mv = codes[0]
            if cp is not None:
                cp_track[ply] = cp          # 皮卡鱼视角：正数=它占优
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
        """取最接近 target 手的那次皮卡鱼评分（它自己的视角）。"""
        if not cp_track:
            return None
        best = min(cp_track, key=lambda p: abs(p - target))
        return cp_track[best]

    return {"res": res, "plies": plies,
            "ms": round(sum(ours_ms) / max(1, len(ours_ms)), 1),
            "cp10": cp_at(10), "cp20": cp_at(20), "cp30": cp_at(30), "cp_end": cp_track.get(plies - 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--mode", default="pro3")
    ap.add_argument("--limit", default="movetime:10")
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--open-plies", type=int, default=3)
    ap.add_argument("--max-ply", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    kind, val = args.limit.split(":")
    pika = Pika(kind, int(val))
    ours = Ours(args.model, args.mode, args.seed)
    rows = []
    t0 = time.time()
    try:
        for i in range(args.games):
            r = one_game(ours, pika, i % 2 == 0, args.seed + i, args.open_plies, args.max_ply)
            r["game"] = i + 1
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    finally:
        ours.close()
        pika.close()

    n = len(rows)
    w = sum(1 for r in rows if r["res"] == "win")
    d = sum(1 for r in rows if r["res"] == "draw")
    l = sum(1 for r in rows if r["res"] == "loss")
    fast = sum(1 for r in rows if r["res"] == "loss" and r["plies"] <= 30)
    vfast = sum(1 for r in rows if r["res"] == "loss" and r["plies"] <= 20)

    def avg_cp(key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(v) / len(v), 1) if v else None

    s = {
        "mode": args.mode, "limit": args.limit, "games": n,
        "w": w, "d": d, "l": l,
        "avg_plies": round(sum(r["plies"] for r in rows) / n, 1),
        "max_plies": max(r["plies"] for r in rows),
        "fast30": fast, "fast20": vfast,
        "cp20": avg_cp("cp20"), "cp30": avg_cp("cp30"),
        "avg_ms": round(sum(r["ms"] for r in rows) / n, 1),
        "secs": round(time.time() - t0, 1),
    }
    print(json.dumps(s, ensure_ascii=False, indent=1), flush=True)
    if args.out:
        pathlib.Path(HERE / args.out).write_text(
            json.dumps({"summary": s, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
