"""用皮卡鱼节点梯子给 CatChess-v1.0pro-preview 定级。

做法：同一模型（固定时限）对皮卡鱼不同节点上限逐档对打，统计得分率，
按 Elo 差公式换算 dElo = -400 * log10(1/score - 1)。

  - 开局：双方共用同一随机着法序列（默认 4 手），先后手交替
  - 送全历史着法给双方（避免转移表残留与重复局面误判）
  - 判和：同一局面出现 3 次 / 超过 max_ply；无合法着法判负
  - 中国象棋的长将判负在这里简化为「重复即和」，偏向防守方，读数略保守

用法：
  python calibrate_elo.py --ladder 100,200,400,800 --games 12 --ms 300
"""
import argparse
import json
import math
import pathlib
import random
import subprocess
import sys

import board as B
from cloud_label import fen_of
from match_pikafish import Pika

HERE = pathlib.Path(__file__).resolve().parent
START = fen_of(B.initial_board(), B.RED)
ILLEGAL = 0


class Cal:
    """CatChess 的最小 UCI 封装：只关心 bestmove。"""

    def __init__(self, exe):
        self.p = subprocess.Popen(
            [str(HERE / exe)], cwd=str(HERE), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.ms = 300
        self.send("uci")
        self.wait("uciok")
        self.send("isready")
        self.wait("readyok")

    def send(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def wait(self, token):
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("CatChess 提前退出")
            if token in line:
                return line

    def best(self, hist):
        pos = "position startpos" + (" moves " + " ".join(hist) if hist else "")
        self.send(pos)
        self.send(f"go movetime {self.ms}")
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("CatChess 无输出")
            if line.startswith("bestmove"):
                u = line.split()[1]
                return u if len(u) >= 4 and u[0].isalpha() else None

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def elo_diff(score):
    """得分率 → Elo 差（正数表示比对手强）。截断到 0.02/0.98 防止发散。"""
    s = min(max(score, 0.02), 0.98)
    return -400.0 * math.log10(1.0 / s - 1.0)


def elo_ci(score, n):
    """得分率的正态近似 → Elo 差 95% 区间。"""
    se = math.sqrt(max(score * (1 - score), 1e-9) / n)
    return elo_diff(max(score - 1.96 * se, 0.02)), elo_diff(min(score + 1.96 * se, 0.98))


def play(me, opp, me_is_red, rng, open_plies, max_ply):
    bd = B.initial_board()
    side = B.RED
    hist = []
    reps = {fen_of(bd, side): 1}
    while len(hist) < max_ply:
        lg = B.gen_legal(bd, side)
        if not lg:
            me_lost = (side == B.RED) == me_is_red
            return ("loss" if me_lost else "win"), len(hist)
        f = t = None
        if len(hist) < open_plies:
            f, t = rng.choice(lg)
        elif (side == B.RED) == me_is_red:
            u = me.best(hist)
            if u:
                f = "abcdefghi".index(u[0]); t = "abcdefghi".index(u[2])
                f, t = (9 - int(u[1])) * 9 + f, (9 - int(u[3])) * 9 + t
        else:
            u = opp.best(START, hist=hist or None, init_fen=START)[0]
            if u and u not in ("0000", "(none)"):
                f = "abcdefghi".index(u[0]); t = "abcdefghi".index(u[2])
                f, t = (9 - int(u[1])) * 9 + f, (9 - int(u[3])) * 9 + t
        if (f, t) not in lg:            # 引擎给非法着法或没给着法：退回首着，计数后继续
            if f is not None:
                global ILLEGAL
                ILLEGAL += 1
            f, t = lg[0]
        B.apply_move(bd, (f, t))
        mvs = ("%s%d%s%d" % ("abcdefghi"[f % 9], 9 - f // 9,
                            "abcdefghi"[t % 9], 9 - t // 9))
        hist.append(mvs)
        side = -side
        k = fen_of(bd, side)
        reps[k] = reps.get(k, 0) + 1
        if reps[k] >= 3:
            return "draw", len(hist)
    return "draw", len(hist)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="CatChess-v1.0pro-preview.exe")
    ap.add_argument("--ms", type=int, default=300)
    ap.add_argument("--ladder", default="100,200,400,800")
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--open-plies", type=int, default=4)
    ap.add_argument("--max-ply", type=int, default=160)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/calibrate_elo.json")
    args = ap.parse_args()

    me = Cal(args.exe)
    me.ms = args.ms
    rows = []
    try:
        for nodes in [int(x) for x in args.ladder.split(",")]:
            opp = Pika(limit_kind="nodes", limit=nodes)
            w = d = l = 0
            for i in range(args.games):
                rng = random.Random(args.seed * 100003 + nodes * 17 + i)
                me_is_red = (i % 2 == 0)
                res, plies = play(me, opp, me_is_red, rng, args.open_plies, args.max_ply)
                w += res == "win"; d += res == "draw"; l += res == "loss"
                print(json.dumps({"nodes": nodes, "game": i + 1,
                                  "me_side": "red" if me_is_red else "black",
                                  "res": res, "plies": plies}, ensure_ascii=False), flush=True)
            score = (w + 0.5 * d) / args.games
            lo, hi = elo_ci(score, args.games)
            rows.append({"pika_nodes": nodes, "games": args.games, "w": w, "d": d, "l": l,
                         "score": round(score, 3), "elo_diff": round(elo_diff(score), 0),
                         "elo_lo": round(lo, 0), "elo_hi": round(hi, 0)})
            print(json.dumps({"ladder": rows[-1]}, ensure_ascii=False), flush=True)
            opp.close()
    finally:
        me.close()

    pathlib.Path(args.out).write_text(
        json.dumps({"exe": args.exe, "ms": args.ms, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(json.dumps({"done": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
