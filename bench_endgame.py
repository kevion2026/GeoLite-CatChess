"""残局着法质量基准：每个引擎在残局局面上走一步，用皮卡鱼深搜算着法损失（CPL）。

比对局更灵敏：对局结果被「能不能赢」的二值化吞掉，CPL 直接量化每一步的判断误差。
参考分与走子后评分都缓存到 data/eg_mref.json，多引擎比较时口径完全一致。

用法：
  python bench_endgame.py --exes CatChess-v2.0.exe,xqeg_s100.exe --n 120 --ms 60
"""
import argparse
import json
import pathlib
import pickle
import statistics

import board as B
from bench_cpp import Cpp
from gen_pika_values2 import Engine as Pika, fen_of

HERE = pathlib.Path(__file__).resolve().parent
MREF = HERE / "data" / "eg_mref.json"
MATV = {1: 0, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}


def pick(path, n, lo_cp, hi_cp, lo_mat, hi_mat, seed):
    rows = pickle.load(open(path, "rb"))
    cand = []
    for r in rows:
        if r.get("cp") is None:
            continue
        if not (lo_cp <= abs(r["cp"]) <= hi_cp):
            continue
        m = sum(MATV[abs(p)] for p in r["board"] if p)
        if not (lo_mat <= m <= hi_mat):
            continue
        cand.append(r)
    import random
    random.Random(seed).shuffle(cand)
    # 按子力分 4 档轮取
    bands = {}
    for r in cand:
        m = sum(MATV[abs(p)] for p in r["board"] if p)
        bands.setdefault(0 if m < 900 else 1 if m < 1500 else 2 if m < 2300 else 3, []).append(r)
    out, k = [], 0
    while len(out) < n and any(bands.values()):
        b = k % 4
        k += 1
        if bands.get(b):
            out.append(bands[b].pop())
    return out


def uci_of(mv):
    f, t = mv // 100, mv % 100
    return "abcdefghi"[f % 9] + str(9 - f // 9) + "abcdefghi"[t % 9] + str(9 - t // 9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exes", default="CatChess-v2.0.exe")
    ap.add_argument("--pos", default="data/pika_values_endgame.pkl")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--ms", type=int, default=60)
    ap.add_argument("--depth", type=int, default=0, help=">0 时改用固定深度，消除时限抖动")
    ap.add_argument("--nodes", type=int, default=0, help=">0 时改用等节点口径（确定性，最公平）")
    ap.add_argument("--lo-cp", type=int, default=120)
    ap.add_argument("--hi-cp", type=int, default=900)
    ap.add_argument("--lo-mat", type=int, default=800)
    ap.add_argument("--hi-mat", type=int, default=2800)
    ap.add_argument("--ref-nodes", type=int, default=250000)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default="data/bench_endgame.json")
    args = ap.parse_args()

    rows = pick(HERE / args.pos, args.n, args.lo_cp, args.hi_cp,
                args.lo_mat, args.hi_mat, args.seed)
    print("残局基准局面 %d 个（|cp| %d~%d，子力 %d~%d）"
          % (len(rows), args.lo_cp, args.hi_cp, args.lo_mat, args.hi_mat), flush=True)

    mref = {}
    if MREF.exists():
        try:
            mref = json.loads(MREF.read_text(encoding="utf-8"))
        except Exception:
            mref = {}

    pika = Pika()
    table = []
    try:
        for exe in args.exes.split(","):
            eng = Cpp(exe)
            cpls, top1, n_ok, sign_ok = [], 0, 0, 0
            bypos = {}
            try:
                for i, r in enumerate(rows):
                    b0, s0 = list(r["board"]), r["side"]
                    # 缓存键用 FEN 而不是局面序号：换 --n / --seed 时序号会整体错位，
                    # 旧缓存会被张冠李戴地复用（踩过一次），FEN 键天然免疫。
                    fen0 = fen_of(b0, s0)
                    key0 = fen0
                    if key0 in mref:
                        ref_cp, ref_uci = mref[key0]
                    else:
                        ref_cp, ref_uci = pika.probe(fen0, nodes=args.ref_nodes)
                        mref[key0] = [ref_cp, ref_uci or ""]
                    # 用皮卡鱼自己的最佳着法做 top1 参照
                    mv, _ = eng.best(b0, s0, args.depth, args.ms, args.nodes)
                    lg = B.gen_legal(b0, s0)
                    if not mv or mv not in [f * 100 + t for (f, t) in lg]:
                        continue
                    after = list(b0)
                    B.apply_move(after, (mv // 100, mv % 100))
                    k1 = fen0 + "|" + uci_of(mv)
                    if k1 in mref:
                        a_cp = mref[k1][0]
                    else:
                        a_cp = pika.label(fen_of(after, -s0), 0, 0, args.ref_nodes)
                        mref[k1] = [a_cp, ""]
                    cpl = max(-100, min(900, ref_cp + a_cp))
                    cpls.append(cpl)
                    bypos[fen0] = cpl
                    n_ok += 1
                    if uci_of(mv) == mref[key0][1]:
                        top1 += 1
                    if (ref_cp >= 0) == (ref_cp + a_cp >= 0):
                        sign_ok += 1
            finally:
                eng.close()
            cpls.sort()
            row = {"engine": exe, "ms": args.ms, "depth": args.depth, "nodes": args.nodes, "n": n_ok,
                   "cpl_mean": round(statistics.mean(cpls), 1),
                   "cpl_median": round(statistics.median(cpls), 1),
                   "cpl_p90": round(cpls[int(len(cpls) * 0.9)], 1),
                   "blunder200": round(sum(1 for x in cpls if x > 200) / len(cpls), 3),
                   "top1": round(top1 / max(1, n_ok), 3),
                   "keep_sign": round(sign_ok / max(1, n_ok), 3),
                   "cpl_by_pos": bypos}
            table.append(row)
            brief = {k: v for k, v in row.items() if k != "cpl_by_pos"}
            print(json.dumps(brief, ensure_ascii=False), flush=True)
            MREF.write_text(json.dumps(mref), encoding="utf-8")
    finally:
        pika.close()
        MREF.write_text(json.dumps(mref), encoding="utf-8")
    (HERE / args.out).write_text(json.dumps(table, ensure_ascii=False, indent=1),
                                 encoding="utf-8")


if __name__ == "__main__":
    main()
