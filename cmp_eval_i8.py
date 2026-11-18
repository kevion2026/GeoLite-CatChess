"""对比 float32 与 int8 价值头的评估差：同一局面喂 `eval`，统计偏差分布。

用法：python cmp_eval_i8.py --a t_flash32.exe --b CatChess-V1.0-flash.exe --n 1500
"""
import argparse, json, pickle, pathlib, random, statistics, subprocess, sys
from cloud_label import fen_of

HERE = pathlib.Path(__file__).resolve().parent


class E:
    def __init__(self, exe):
        self.p = subprocess.Popen([str(HERE / exe)], cwd=str(HERE),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.p.stdin.write("uci\n"); self.p.stdin.flush()
        while "uciok" not in self.p.stdout.readline():
            pass

    def ev(self, board, side):
        self.p.stdin.write("position fen %s - - 0 1\neval\n" % fen_of(board, side))
        self.p.stdin.flush()
        return int(self.p.stdout.readline().strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="t_flash32.exe")
    ap.add_argument("--b", default="CatChess-V1.0-flash.exe")
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    rows = json.loads((HERE / "data" / "pos_set.json").read_text(encoding="utf-8"))
    mid = [(r["b"], r["s"]) for r in rows]
    eg = pickle.load(open(HERE / "data" / "pika_values_endgame.pkl", "rb"))
    eg = [(r["board"], r["side"]) for r in eg if r.get("cp") is not None]
    random.seed(args.seed)
    random.shuffle(eg)
    eg = eg[:args.n]
    mid = mid[:400]

    A, B = E(args.a), E(args.b)
    for tag, pool in (("中局", mid), ("残局", eg)):
        d, same = [], 0
        for b, s in pool:
            x = A.ev(b, s); y = B.ev(b, s)
            d.append(y - x)
            same += (x == y)
        ad = [abs(v) for v in d]
        print("%s n=%d  |Δ| 均值 %.2f cp  中位 %.1f  p95 %.1f  最大 %d  完全相同 %.1f%%"
              % (tag, len(d), statistics.mean(ad), statistics.median(ad),
                 sorted(ad)[int(0.95 * len(ad))], max(ad), 100.0 * same / len(d)))
        print("        系统偏差 %+.2f cp   Δ 标准差 %.2f" % (statistics.mean(d), statistics.pstdev(d)))
    A.p.stdin.write("quit\n"); B.p.stdin.write("quit\n")


if __name__ == "__main__":
    main()
