"""用皮卡鱼 movetime/depth 给扩充后的 20 万局面打价值标签。"""
import argparse
import json
import pickle
import pathlib
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
EXE = str(HERE / "pikafish" / "Pikafish-Windows-x86-64-universal.exe")
CWD = str(HERE / "pikafish")


def fen_of(b, side):
    rows = []
    for y in range(10):
        empty = 0
        row = ""
        for x in range(9):
            p = int(b[y * 9 + x])
            if p == 0:
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            t = abs(p)
            ch = "kabnrcp"[t - 1]
            row += ch.upper() if p > 0 else ch
        if empty:
            row += str(empty)
        rows.append(row)
    return "/".join(rows) + (" w" if side > 0 else " b") + " - - 0 1"


class Engine:
    def __init__(self):
        self.p = subprocess.Popen(
            [EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, cwd=CWD)
        self.send("uci")
        self.wait("uciok")
        self.send("setoption name Threads value 1")
        self.send("setoption name Hash value 32")
        self.send("setoption name Move Overhead value 0")
        self.send("isready")
        self.wait("readyok")

    def send(self, s):
        self.p.stdin.write(s + "\n")
        self.p.stdin.flush()

    def wait(self, token):
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed")
            if line.strip() == token:
                return

    def label(self, fen, depth=8, movetime=0, nodes=0):
        self.send("position fen " + fen)
        if nodes:
            self.send(f"go nodes {nodes}")
        elif movetime:
            self.send(f"go movetime {movetime}")
        else:
            self.send(f"go depth {depth}")
        cp = 0
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed")
            if "score cp" in line:
                try:
                    cp = int(line.split("score cp")[1].split()[0])
                except Exception:
                    pass
            elif "score mate" in line:
                try:
                    n = int(line.split("score mate")[1].split()[0])
                    cp = (30000 if n > 0 else -30000) - n * 100
                except Exception:
                    pass
            if line.startswith("bestmove"):
                return cp

    def best(self, fen, depth=0, movetime=0, nodes=0):
        """只要 bestmove 字符串，用于让引擎实际走子。"""
        self.send("position fen " + fen)
        if nodes:
            self.send(f"go nodes {nodes}")
        elif movetime:
            self.send(f"go movetime {movetime}")
        else:
            self.send(f"go depth {depth}")
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed")
            if line.startswith("bestmove"):
                p = line.split()
                return p[1] if len(p) > 1 else None

    def probe(self, fen, depth=0, movetime=0, nodes=0):
        """一次搜索同时取回 (cp, bestmove uci)，给基准脚本做参考分用。"""
        self.send("position fen " + fen)
        if nodes:
            self.send(f"go nodes {nodes}")
        elif movetime:
            self.send(f"go movetime {movetime}")
        else:
            self.send(f"go depth {depth}")
        cp, u = 0, None
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed")
            if "score cp" in line:
                try:
                    cp = int(line.split("score cp")[1].split()[0])
                except Exception:
                    pass
            elif "score mate" in line:
                try:
                    n = int(line.split("score mate")[1].split()[0])
                    cp = (30000 if n > 0 else -30000) - n * 100
                except Exception:
                    pass
            if line.startswith("bestmove"):
                p = line.split()
                if len(p) > 1 and p[1][0].isalpha():
                    u = p[1]
                return cp, u

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=3)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass
        for name in ("stdin", "stdout", "stderr"):
            try:
                s = getattr(self.p, name)
                if s:
                    s.close()
            except Exception:
                pass


def worker(args):
    boards, sides, depth, movetime, nodes = args
    eng = Engine()
    out = []
    t0 = time.time()
    try:
        for k, (b, s) in enumerate(zip(boards, sides)):
            cp = eng.label(fen_of(b, s), depth, movetime, nodes)
            out.append(max(-30000, min(30000, cp)))
            if (k + 1) % 500 == 0:
                print(f"  shard: {k+1}/{len(boards)} {time.time()-t0:.0f}s", flush=True)
    finally:
        eng.close()
    return out


def load_rows(path):
    p = pathlib.Path(path)
    rows = []
    if p.suffix == ".jsonl":
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            rows.append((list(d["b"]), int(d["s"]), d.get("src", "selfplay")))
    else:
        x = pickle.load(open(p, "rb"))
        if isinstance(x, dict) and "positions" in x:
            for b, s in x["positions"]:
                rows.append((list(b), int(s), "pgn"))
        elif isinstance(x, dict) and "rows" in x:
            for r in x["rows"]:
                rows.append((list(r[0]), int(r[1]), r[2] if len(r) > 2 else "pgn"))
        else:
            for r in x:
                if isinstance(r, dict):
                    rows.append((list(r["board"]), int(r["side"]), r.get("src", "pgn")))
                else:
                    rows.append((list(r[0]), int(r[1]), r[2] if len(r) > 2 else "pgn"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", default="data/positions_200k.pkl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--movetime", type=int, default=0)
    ap.add_argument("--nodes", type=int, default=0, help="按节点数限深（优先于 depth/movetime）")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="data/pika_values_200k.pkl")
    args = ap.parse_args()

    rows = load_rows(HERE / args.positions)
    if args.limit:
        rows = rows[:args.limit]
    print("总局面", len(rows), "depth", args.depth, "movetime", args.movetime, flush=True)

    n = len(rows)
    per = (n + args.workers - 1) // args.workers
    tasks = []
    for i in range(0, n, per):
        chunk = rows[i:i + per]
        tasks.append(([r[0] for r in chunk], [r[1] for r in chunk], args.depth, args.movetime, args.nodes))
    got = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(worker, tasks):
            got.extend(res)
    rows2 = [{"board": rows[i][0], "side": rows[i][1], "cp": got[i], "src": rows[i][2]}
             for i in range(n)]
    pickle.dump(rows2, open(HERE / args.out, "wb"))
    print("写入", args.out, len(rows2), flush=True)


if __name__ == "__main__":
    main()
