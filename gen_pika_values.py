"""用皮卡鱼 depth 8 给大量局面打价值标签（离线，仅用于训练，不参与对局）。

输入：data/pgn_positions.pkl（真实棋谱局面，board/side）+ data/battle_ds.json（实战局面）
输出：data/pika_values.pkl  {board, side, cp, src}
"""
import argparse, json, pickle, pathlib, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
EXE = str(HERE / "pikafish" / "Pikafish-Windows-x86-64-universal.exe")
CWD = str(HERE / "pikafish")
FILES = "abcdefghi"


def fen_of(b, side):
    rows = []
    for y in range(10):
        empty = 0; row = ""
        for x in range(9):
            p = int(b[y * 9 + x])
            if p == 0:
                empty += 1; continue
            if empty: row += str(empty); empty = 0
            t = abs(p); ch = "kabnrcp"[t - 1]
            row += ch.upper() if p > 0 else ch
        if empty: row += str(empty)
        rows.append(row)
    return "/".join(rows) + (" w" if side > 0 else " b") + " - - 0 1"


class Engine:
    def __init__(self):
        self.p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, encoding="utf-8", bufsize=1, cwd=CWD)
        self.send("uci")
        self.wait("uciok")
        self.send("setoption name Threads value 1")
        self.send("setoption name Hash value 32")
        self.send("isready")
        self.wait("readyok")

    def send(self, s):
        self.p.stdin.write(s + "\n"); self.p.stdin.flush()

    def wait(self, token):
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed")
            if line.strip() == token:
                return

    def label(self, fen, depth):
        self.send("position fen " + fen)
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

    def close(self):
        try:
            self.send("quit"); self.p.wait(timeout=3)
        except Exception:
            self.p.kill()


def worker(args):
    idxs, boards, sides, depth = args
    eng = Engine()
    out = []
    t0 = time.time()
    try:
        for k, i in enumerate(idxs):
            cp = eng.label(fen_of(boards[i], sides[i]), depth)
            out.append((i, max(-30000, min(30000, cp))))
            if (k + 1) % 500 == 0:
                print(f"  shard {idxs[0]}: {k+1}/{len(idxs)} {time.time()-t0:.0f}s", flush=True)
    finally:
        eng.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="data/pika_values.pkl")
    args = ap.parse_args()

    pos = pickle.load(open(HERE / "data" / "pgn_positions.pkl", "rb"))["positions"]
    rows = [(list(p[0]), int(p[1]), "pgn") for p in pos]
    # 实战局面（我方对局），单独加权来源
    try:
        ds = json.load(open(HERE / "data" / "battle_ds.json", encoding="utf-8"))
        for g in ds.get("games", []):
            for r in g.get("rows", []):
                rows.append((list(r[0]), int(r[1]), "battle"))
    except Exception as e:
        print("battle_ds skip", e)
    if args.limit:
        rows = rows[:args.limit]
    print("总局面", len(rows), "depth", args.depth, flush=True)

    boards = [r[0] for r in rows]; sides = [r[1] for r in rows]
    n = len(rows); per = (n + args.workers - 1) // args.workers
    tasks = [(list(range(i, min(n, i + per))), boards, sides, args.depth)
             for i in range(0, n, per)]
    got = [None] * n
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(worker, tasks):
            for i, cp in res:
                got[i] = cp
    rows2 = [{"board": rows[i][0], "side": rows[i][1], "cp": got[i], "src": rows[i][2]}
             for i in range(n)]
    pickle.dump(rows2, open(HERE / args.out, "wb"))
    print("写入", args.out, len(rows2), flush=True)


if __name__ == "__main__":
    main()
