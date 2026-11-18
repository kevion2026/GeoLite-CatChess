"""C++ 引擎的固定局面基准：与 bench_positions.py 用同一局面集、同一份皮卡鱼参考分。

用法：
  python bench_cpp.py --exes xq16.exe,xq17.exe --depth 6
  python bench_cpp.py --exes xq17.exe --movetime 800
"""
import argparse
import json
import pathlib
import statistics
import subprocess
import sys

import board as B
from match_pikafish import Pika, mv_to_uci
from cloud_label import fen_of
from move_quality import analyse

HERE = pathlib.Path(__file__).resolve().parent
POS = HERE / "data" / "pos_set.json"
REF = HERE / "data" / "pos_ref.json"
MREF_DEFAULT = HERE / "data" / "pos_move_ref.json"


class Cpp:
    def __init__(self, exe):
        self.p = subprocess.Popen(
            [str(HERE / exe)], cwd=str(HERE), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        self.send("uci")
        while "uciok" not in self.p.stdout.readline():
            pass

    def send(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def best(self, board, side, depth=0, ms=0, nodes=0):
        self.send("position fen " + fen_of(board, side) + " - - 0 1")
        if nodes:
            self.send(f"go nodes {nodes}")
        elif depth:
            self.send(f"go depth {depth}")
        else:
            self.send(f"go movetime {ms}")
        mv, cp = None, None
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine died")
            if line.startswith("info") and " score cp " in line:
                try:
                    cp = int(line.split(" score cp ")[1].split()[0])
                except Exception:
                    pass
            if line.startswith("bestmove"):
                u = line.split()[1]
                if len(u) >= 4 and u[0].isalpha():
                    fx = "abcdefghi".index(u[0]); fy = 9 - int(u[1])
                    tx = "abcdefghi".index(u[2]); ty = 9 - int(u[3])
                    mv = (fy * 9 + fx) * 100 + (ty * 9 + tx)
                return mv, cp

    def close(self):
        try:
            self.send("quit"); self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exes", default="xq16.exe")
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--movetime", type=int, default=0)
    ap.add_argument("--nodes", type=int, default=0, help=">0 时用等节点口径")
    ap.add_argument("--ref", type=int, default=60)
    ap.add_argument("--n", type=int, default=0, help="只跑前 n 个局面")
    ap.add_argument("--lo", type=int, default=-700)
    ap.add_argument("--hi", type=int, default=300)
    ap.add_argument("--cap", type=int, default=600)
    ap.add_argument("--mref", default="data/pos_move_ref.json",
                    help="走子后参考分缓存；换参考时限时应指向新文件，避免新旧口径混用")
    ap.add_argument("--out", default="data/bench_cpp.json")
    args = ap.parse_args()

    poss = json.loads(POS.read_text(encoding="utf-8"))
    if args.n:
        poss = poss[:args.n]
    ref = json.loads(REF.read_text(encoding="utf-8"))
    mref_p = pathlib.Path(args.mref)
    if not mref_p.is_absolute():
        mref_p = HERE / mref_p
    mref = json.loads(mref_p.read_text(encoding="utf-8")) if mref_p.exists() else {}

    pika = Pika("movetime", 10)
    table = []
    try:
        for exe in args.exes.split(","):
            eng = Cpp(exe)
            cpls, top1, n_ok, dwell, bypos = [], 0, 0, [], {}
            try:
                for i, po in enumerate(poss):
                    r0 = ref[str(i)]
                    if r0.get("cp") is None or r0.get("mate") is not None:
                        continue
                    if not (args.lo <= r0["cp"] <= args.hi):
                        continue
                    mv, cp = eng.best(po["b"], po["s"], args.depth, args.movetime, args.nodes)
                    lg = [f * 100 + t for (f, t) in B.gen_legal(po["b"], po["s"])]
                    if not mv or mv not in lg:
                        continue
                    after = list(po["b"])
                    B.apply_move(after, (mv // 100, mv % 100))
                    mkey = f"{i}:{mv_to_uci(mv)}"
                    if mkey in mref:
                        a_cp = mref[mkey]
                    else:
                        _, a_cp, _ = analyse(pika, after, -po["s"], args.ref)
                        mref[mkey] = a_cp
                        if len(mref) % 25 == 0:
                            mref_p.write_text(json.dumps(mref), encoding="utf-8")
                    if a_cp is None:
                        continue
                    if cp is not None:
                        dwell.append(cp + a_cp)
                    cpl = max(-50, min(args.cap, r0["cp"] + a_cp))
                    cpls.append(cpl)
                    bypos[str(i)] = cpl
                    n_ok += 1
                    if r0["uci"] and mv_to_uci(mv) == r0["uci"]:
                        top1 += 1
            finally:
                eng.close()
            cpls.sort()
            row = {"engine": exe, "limit": f"depth{args.depth}" if args.depth else f"ms{args.movetime}",
                   "n": n_ok, "cpl_mean": round(statistics.mean(cpls), 1),
                   "cpl_median": round(statistics.median(cpls), 1),
                   "cpl_p90": round(cpls[int(len(cpls) * 0.9)], 1),
                   "blunder200": round(sum(1 for x in cpls if x > 200) / len(cpls), 3),
                   "top1": round(top1 / max(1, n_ok), 3), "cpl_by_pos": bypos}
            if dwell:
                row["selfcal"] = round(statistics.mean(dwell), 1)
            table.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "cpl_by_pos"},
                             ensure_ascii=False), flush=True)
        (HERE / args.out).write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        mref_p.write_text(json.dumps(mref), encoding="utf-8")
    finally:
        pika.close()


if __name__ == "__main__":
    main()
