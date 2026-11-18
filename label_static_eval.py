"""用 Pikafish 的 NNUE 静态评估（eval 命令）给 200k 局面打标签。"""
import pickle
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
sys.path.insert(0, str(HERE))
from gen_pika_values2 import fen_of, load_rows

PF = HERE / "pikafish" / "Pikafish-Windows-x86-64-universal.exe"
OUT = HERE / "data" / "pika_static_200k.pkl"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    rows = load_rows(HERE / "data" / "positions_200k.pkl")
    if args.limit:
        rows = rows[:args.limit]
    done = []
    if out.exists():
        try:
            done = pickle.load(open(out, "rb"))
        except Exception:
            done = []
    p = subprocess.Popen([str(PF)], cwd=str(HERE / "pikafish"), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, encoding="utf-8", bufsize=1)
    p.stdin.write("uci\nisready\n")
    p.stdin.flush()
    while True:
        line = p.stdout.readline()
        if not line:
            raise RuntimeError("engine closed")
        if "readyok" in line:
            break
    t0 = time.time()
    k = len(done)
    while k < len(rows):
        b, s, _src = rows[k]
        fen = fen_of(b, s) + " - - 0 1"
        p.stdin.write("position fen " + fen + "\neval\n")
        p.stdin.flush()
        val = 0.0
        while True:
            line = p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed at %d" % k)
            if "Final evaluation" in line:
                try:
                    val = float(line.split("Final evaluation")[1].split()[0])
                except Exception:
                    val = 0.0
                break
        cp = int(round(val * 100.0))
        if s < 0:
            cp = -cp
        done.append((k, max(-30000, min(30000, cp))))
        k += 1
        if k % 2000 == 0 or k == len(rows):
            tmp = str(out) + ".tmp"
            pickle.dump(done, open(tmp, "wb"))
            pathlib.Path(tmp).replace(out)
            print(f"{k}/{len(rows)} {time.time()-t0:.0f}s rate {k/(time.time()-t0):.0f}/s", flush=True)
    p.stdin.write("quit\n")
    p.stdin.flush()
    print("DONE", len(done), flush=True)


if __name__ == "__main__":
    main()
