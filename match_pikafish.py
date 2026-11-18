"""用 Pikafish 测 GeoLite 的棋艺：UCI 对局，逐着比对合法性，统计胜负与耗时。"""

import argparse
import json
import pathlib
import subprocess
import sys
import time

import random

import board as B
from cloud_label import fen_of

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
PF_DIR = HERE / "pikafish"
PF_EXE = PF_DIR / "Pikafish-Windows-x86-64-universal.exe"
PF_NNUE = PF_DIR / "pikafish.nnue"
FILES = "abcdefghi"


def mv_to_uci(mv):
    f, t = mv // 100, mv % 100
    fx, fy = f % 9, f // 9
    tx, ty = t % 9, t // 9
    return f"{FILES[fx]}{9 - fy}{FILES[tx]}{9 - ty}"


def uci_to_mv(u):
    if len(u) < 4:
        return None
    fx = FILES.index(u[0]); fy = 9 - int(u[1])
    tx = FILES.index(u[2]); ty = 9 - int(u[3])
    return (fy * 9 + fx) * 100 + (ty * 9 + tx)


class Pika:
    def __init__(self, limit_kind="nodes", limit=1000):
        self.p = subprocess.Popen(
            [str(PF_EXE)], cwd=str(PF_DIR), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.send("uci")
        self.limit_kind, self.limit = limit_kind, limit
        self.wait_for("uciok")
        self.send(f"setoption name EvalFile value {PF_NNUE}")
        self.send("setoption name Threads value 1")
        self.send("setoption name Hash value 64")
        self.send("isready")
        self.wait_for("readyok")

    def send(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def wait_for(self, token):
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("pikafish 提前结束")
            if token in line:
                return line

    def best(self, fen, depth_cap=64, hist=None, init_fen=None):
        if hist:
            self.send(f"position fen {init_fen} - - 0 1 moves {' '.join(hist)}")
        else:
            self.send(f"position fen {fen} - - 0 1")
        if self.limit_kind == "nodes":
            self.send(f"go nodes {self.limit}")
        elif self.limit_kind == "depth":
            self.send(f"go depth {self.limit}")
        else:
            self.send(f"go movetime {self.limit}")
        best, cp, dep = None, None, None
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("pikafish 无输出")
            if line.startswith("info") and " score cp " in line and " pv " in line:
                try:
                    cp = int(line.split(" score cp ")[1].split()[0])
                    dep = int(line.split(" depth ")[1].split()[0]) if " depth " in line else dep
                except Exception:
                    pass
            if line.startswith("bestmove"):
                best = line.split()[1]
                break
        return best, cp, dep

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class Ours:
    def __init__(self, model="model_triple.json", script="_our_server.js"):
        self.p = subprocess.Popen(
            ["node", script, model, "engine3d.js"], cwd=str(HERE),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1)
        self.mvs = []
        self.keys = []

    def best(self, mvs, keys):
        self.p.stdin.write(json.dumps({"mvs": mvs, "history": keys}) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class OursCpp:
    """C++ 引擎 xq.exe 的 UCI 适配器，接口与 Ours 一致。"""

    BOOK_RED = ["h2e2", "b0c2", "h0g2", "a0b0"]
    BOOK_BLACK = ["h9g7", "b9c7", "a9b9", "h7e7"]

    def __init__(self, exe="xq.exe", ms=10000, depth=0):
        self.ms, self.depth = ms, depth
        self.p = subprocess.Popen(
            [str(HERE / exe)], cwd=str(HERE),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1)
        self.send("uci")
        self.wait_for("uciok")
        self.send("isready")
        self.wait_for("readyok")

    def send(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def wait_for(self, token):
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("xq 提前结束")
            if token in line:
                return line

    def _book_move(self, mvs):
        import board as B
        b = B.initial_board()
        side = B.RED
        for m in mvs:
            B.apply_move(b, (m // 100, m % 100))
            side = -side
        if not hasattr(self, "book"):
            try:
                self.book = json.load(open(HERE / "data" / "book.json", encoding="utf-8"))
            except Exception:
                self.book = {}
        u = self.book.get(fen_of(b, side))
        if u:
            for (f, t) in B.gen_legal(b, side):
                if mv_to_uci(f * 100 + t) == u:
                    return f * 100 + t
        seq = self.BOOK_RED if side == B.RED else self.BOOK_BLACK
        k = len(mvs) // 2
        if k >= len(seq):
            return None
        mv = uci_to_mv(seq[k])
        codes = {f * 100 + t for (f, t) in B.gen_legal(b, side)}
        return mv if mv in codes else None

    def best(self, mvs, keys=None):
        bm = self._book_move(mvs)
        if bm is not None:
            return {"mv": bm, "ms": 0}
        t0 = time.time()
        hist = " ".join(mv_to_uci(m) for m in mvs)
        cmd = "position startpos" + (f" moves {hist}" if hist else "")
        self.send(cmd)
        self.send(f"go depth {self.depth}" if self.depth else f"go movetime {self.ms}")
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("xq 无输出")
            if line.startswith("bestmove"):
                u = line.split()[1]
                try:
                    mv = uci_to_mv(u)
                except ValueError:
                    mv = None
                return {"mv": mv, "ms": int((time.time() - t0) * 1000)}

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def play(ours_side, pika, limit_text, rand_open=0, seed=0):
    rng = random.Random(seed)
    b = B.initial_board()
    side = B.RED
    mvs, keys, uci_hist = [], [], []
    init_fen = fen_of(b, B.RED)
    rep = {}
    our_ms, pf_ms, cap = [], [], 0
    last_cp = None
    res = None
    for ply in range(240):
        lg = B.gen_legal(b, side)
        if not lg:
            res = "loss" if side == ours_side else "win"
            break
        codes = [f * 100 + t for (f, t) in lg]
        fen = fen_of(b, side) + " - - 0 1"
        rep[fen] = rep.get(fen, 0) + 1
        if rep[fen] >= 3:
            res = "draw"
            break
        if rand_open and ply < rand_open:
            mv = rng.choice(codes)
            mvs.append(mv)
            keys.append(hash(fen))
            B.apply_move(b, (mv // 100, mv % 100))
            uci_hist.append(mv_to_uci(mv))
            side = -side
            continue
        if side == ours_side:
            r = ours_proc.best(mvs, keys)
            mv = r["mv"]
            if not mv or mv not in codes:
                mv = codes[0]
            our_ms.append(r["ms"])
            mvs.append(mv)
            keys.append(hash(fen))
        else:
            u, cp, dep = pika.best(fen, hist=uci_hist, init_fen=init_fen)
            mv = uci_to_mv(u)
            if mv is None or mv not in codes:
                res = f"illegal-by-pika:{u}"
                break
            pf_ms.append(0)
            last_cp = cp
            mvs.append(mv)
        if B.is_capture(b, (mv // 100, mv % 100)):
            cap += 1
        B.apply_move(b, (mv // 100, mv % 100))
        uci_hist.append(mv_to_uci(mv))
        side = -side
    if res is None:
        res = "draw"
    return dict(res=res, plies=ply + 1, caps=cap, our_ms=round(sum(our_ms) / max(1, len(our_ms)), 1),
                pf_cp=last_cp, limit=limit_text)


def main():
    global ours_proc
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--rand-open", type=int, default=4)
    ap.add_argument("--limit", default="nodes:1000")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--cpp", action="store_true", help="用 C++ 引擎 xq*.exe 代替 JS 引擎")
    ap.add_argument("--exe", default="xq.exe")
    ap.add_argument("--depth", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--ms", type=int, default=0, help="C++ 引擎单步毫秒（depth 为 0 时生效）")
    args = ap.parse_args()
    kind, val = args.limit.split(":")
    pika = Pika(kind, int(val))
    ours_proc = OursCpp(args.exe, ms=args.ms or 1000, depth=args.depth) if args.cpp else Ours(args.model)
    tag = args.tag or (args.exe if args.cpp else "js")
    rows = []
    try:
        for i in range(args.games):
            ours_side = B.RED if i % 2 == 0 else B.BLACK
            r = play(ours_side, pika, args.limit, args.rand_open, seed=i * 7919 + 13)
            r["ours_side"] = "red" if ours_side == B.RED else "black"
            r["game"] = i + 1
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    finally:
        ours_proc.close()
        pika.close()
    w = sum(1 for r in rows if r["res"] == "win")
    d = sum(1 for r in rows if r["res"] == "draw")
    l = sum(1 for r in rows if r["res"] == "loss")
    print(json.dumps({"summary": {"games": len(rows), "w": w, "d": d, "l": l,
                                  "avg_plies": round(sum(r["plies"] for r in rows) / len(rows), 1),
                                  "avg_caps": round(sum(r["caps"] for r in rows) / len(rows), 1),
                                  "avg_our_ms": round(sum(r["our_ms"] for r in rows) / len(rows), 1)},
                      "rows": rows}, ensure_ascii=False))
    pathlib.Path(HERE / "data" / f"pikafish_match_{args.limit.replace(':', '_')}_{tag}.json").write_text(
        json.dumps({"limit": args.limit, "engine": tag, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
