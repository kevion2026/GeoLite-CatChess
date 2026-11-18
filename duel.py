"""两套引擎配置互相对打，用来做 A/B：胜平负 + 手数 + 单步耗时。

用法：
  python duel.py --a model_triple.json:pro --b model_triple.json:base --games 60

两个 arm 各自常驻一个 node 进程，开局由固定种子的随机序列决定，双方共用同一局开局，
先后手交替，因此差异只来自引擎本身。
"""

import argparse
import json
import os
import pathlib
import random
import subprocess
import sys

import board as B

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


class Arm:
    def __init__(self, spec, seed):
        model, _, mode = spec.partition(":")
        mode = mode or "default"
        env = dict(os.environ)
        env["GEO_SEED"] = str(seed)
        self.p = subprocess.Popen(
            ["node", str(SERVER), str(HERE / model), str(ENGINE), mode],
            cwd=str(HERE), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1, env=env)
        self.name = spec

    def best(self, mvs):
        self.p.stdin.write(json.dumps({"mvs": mvs}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            err = self.p.stderr.read() if self.p.stderr else ""
            raise RuntimeError(f"{self.name} 无输出: {err[:800]}")
        return json.loads(line)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def one_game(a, b, a_is_red, seed, open_plies, max_ply):
    rng = random.Random(seed * 7919 + 11)
    seq = list(OPENINGS[seed % len(OPENINGS)])
    probe = B.initial_board()
    side = B.RED
    for mv in [(f * 9 + fy, t * 9 + ty) for (f, fy, t, ty) in seq]:
        B.apply_move(probe, mv)
        side = -side
    for _ in range(open_plies):
        lg = B.gen_legal(probe, side)
        mv = rng.choice(lg)
        seq.append((mv[0] % 9, mv[0] // 9, mv[1] % 9, mv[1] // 9))
        B.apply_move(probe, mv)
        side = -side

    bd = B.initial_board()
    side = B.RED
    mvs, reps = [], {}
    ms = {"a": [], "b": []}
    caps = {"a": 0, "b": 0}
    res = "draw"
    plies = 0
    for ply in range(max_ply):
        lg = B.gen_legal(bd, side)
        if not lg:
            res = "loss_a" if side == (B.RED if a_is_red else B.BLACK) else "loss_b"
            break
        codes = [f * 100 + t for (f, t) in lg]
        ours = (side == B.RED) == a_is_red
        if ply < len(seq):
            a_, c_, d_, e_ = seq[ply]
            mv = sqm(a_, c_, d_, e_)
            if mv not in codes:
                mv = codes[0]
        else:
            arm = a if ours else b
            r = arm.best(mvs)
            ms["a" if ours else "b"].append(r.get("ms", 0))
            mv = r.get("mv")
            if not mv or mv not in codes:
                res = "illegal_a" if ours else "illegal_b"
                break
        if B.is_capture(bd, (mv // 100, mv % 100)):
            caps["a" if ours else "b"] += 1
        B.apply_move(bd, (mv // 100, mv % 100))
        mvs.append(mv)
        side = -side
        plies = ply + 1
        fen = B.fen_like(bd) + ("w" if side == B.RED else "b")
        reps[fen] = reps.get(fen, 0) + 1
        if reps[fen] >= 3:
            res = "draw"
            break
    return {
        "res": res, "plies": plies, "caps": caps,
        "ms_a": round(sum(ms["a"]) / max(1, len(ms["a"])), 1),
        "ms_b": round(sum(ms["b"]) / max(1, len(ms["b"])), 1),
        "tail": mvs[-12:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="model_triple.json:default")
    ap.add_argument("--b", default="model_triple.json:base")
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--open-plies", type=int, default=3)
    ap.add_argument("--max-ply", type=int, default=220)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    a = Arm(args.a, args.seed)
    b = Arm(args.b, args.seed + 977)
    rows = []
    try:
        for i in range(args.games):
            a_is_red = (i % 2 == 0)
            r = one_game(a, b, a_is_red, args.seed + i, args.open_plies, args.max_ply)
            r["game"] = i + 1
            r["a_red"] = a_is_red
            rows.append(r)
            w = sum(1 for x in rows if x["res"] in ("loss_b", "illegal_b"))
            l = sum(1 for x in rows if x["res"] in ("loss_a", "illegal_a"))
            d = len(rows) - w - l
            print(json.dumps({"g": i + 1, "res": r["res"], "plies": r["plies"],
                              "capsA": r["caps"]["a"], "capsB": r["caps"]["b"],
                              "msA": r["ms_a"], "msB": r["ms_b"],
                              "W-L-D": f"{w}-{l}-{d}"}, ensure_ascii=False), flush=True)
    finally:
        a.close()
        b.close()

    w = sum(1 for x in rows if x["res"] in ("loss_b", "illegal_b"))
    l = sum(1 for x in rows if x["res"] in ("loss_a", "illegal_a"))
    d = len(rows) - w - l
    summary = {
        "a": args.a, "b": args.b, "games": len(rows),
        "a_win": w, "draw": d, "a_loss": l,
        "score": round((w + 0.5 * d) / max(1, len(rows)), 3),
        "avg_plies": round(sum(x["plies"] for x in rows) / max(1, len(rows)), 1),
        "median_plies": sorted(x["plies"] for x in rows)[len(rows) // 2] if rows else 0,
        "avg_ms_a": round(sum(x["ms_a"] for x in rows) / max(1, len(rows)), 1),
        "avg_ms_b": round(sum(x["ms_b"] for x in rows) / max(1, len(rows)), 1),
        "avg_caps_a": round(sum(x["caps"]["a"] for x in rows) / max(1, len(rows)), 1),
        "avg_caps_b": round(sum(x["caps"]["b"] for x in rows) / max(1, len(rows)), 1),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    if args.out:
        pathlib.Path(HERE / args.out).write_text(
            json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
