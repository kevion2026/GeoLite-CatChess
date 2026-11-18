"""诊断：评估函数在「吃子后的叶子局面」上的精度。

动机：qsearch 的 stand-pat 几乎全部发生在「刚吃完子、子力失衡」的局面上。
训练集的局面都是平静局面（12 步对走采样 / 中局池），如果价值头在这类
失衡局面上失准，搜索就会在战术分叉处判错——而这类错误恰好表现为 CPL
的大失误，却完全不会体现在平静局面的 MAE 上。

做法：取平静残局局面，枚举所有合法吃子，落子后让引擎给出 eval 与 planeeval，
再用皮卡鱼深搜当标签，分「平静」与「吃子后」两组比 MAE。

用法：
  python diag_leaf_eval.py --exe t_cons.exe --n 80 --pika-nodes 60000
"""
import argparse
import json
import pickle
import random
import statistics
import subprocess
import sys

sys.path.insert(0, ".")
import board as B
from gen_pika_values2 import Engine as Pika, fen_of

MATV = {1: 0, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}


def pick_positions(n, seed):
    rows = pickle.load(open("data/pika_values_endgame.pkl", "rb"))
    cand = [r for r in rows if r.get("cp") is not None
            and 800 <= sum(MATV[abs(p)] for p in r["board"] if p) <= 2800
            and abs(r["cp"]) <= 900]
    random.Random(seed).shuffle(cand)
    return cand[:n]


def engine_vals(exe, fens):
    """一次进程内批量取 (eval, planeeval)。"""
    cmds = []
    for f in fens:
        cmds += ["position fen " + f, "eval", "planeeval"]
    p = subprocess.run([exe], input="\n".join(cmds + ["quit"]) + "\n",
                       capture_output=True, text=True, timeout=1800)
    out = [x.strip() for x in p.stdout.splitlines() if x.strip()]
    ev, pl = [], []
    i = 0
    while i + 1 < len(out) + 1 and i < len(out):
        try:
            a = int(out[i]); b = int(out[i + 1])
        except (ValueError, IndexError):
            break
        ev.append(a); pl.append(b)
        i += 2
    return ev, pl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="t_cons.exe")
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--pika-nodes", type=int, default=60000)
    ap.add_argument("--max-cap-per-pos", type=int, default=6)
    ap.add_argument("--out", default="data/diag_leaf.json")
    args = ap.parse_args()

    rows = pick_positions(args.n, args.seed)
    print("平静局面 %d 个" % len(rows), flush=True)

    quiet_fens, quiet_y = [], []
    leaf_fens, leaf_y = [], []
    leaf_tag = []

    pika = Pika()
    try:
        for r in rows:
            b, s = r["board"], r["side"]
            f = fen_of(b, s)
            cp = pika.label(f, 0, 0, args.pika_nodes)
            quiet_fens.append(f)
            quiet_y.append(cp)
            caps = [(mv // 100, mv % 100) for (mv, _) in B.gen_legal(b, s)]
            caps = [(fr, to) for (fr, to) in caps if b[to] != 0]
            random.Random(hash(f) & 0xFFFF).shuffle(caps)
            for (fr, to) in caps[:args.max_cap_per_pos]:
                nb = list(b)
                B.apply_move(nb, (fr, to))
                # 吃子后必须仍是合法局面：将帅照面 / 己方被将 / 对方无着 都跳过，
                # 否则皮卡鱼会直接退出进程（踩过一次，整个进程静默死掉）
                if B.generals_facing(nb) or B.in_check(nb, s):
                    continue
                if not B.gen_legal(nb, -s):
                    continue
                # 落子后轮到对方；引擎 eval 是「行棋方视角」，取负换回原来的红方视角
                leaf_fens.append(fen_of(nb, -s))
                try:
                    leaf_cp = pika.label(fen_of(nb, -s), 0, 0, args.pika_nodes)
                except RuntimeError:
                    pika = Pika()          # 进程死了就重开，别丢掉整轮
                    leaf_cp = pika.label(fen_of(nb, -s), 0, 0, args.pika_nodes)
                leaf_y.append(-leaf_cp)
                leaf_tag.append((f, fr, to))
    finally:
        pika.close()

    print("吃子后局面 %d 个" % len(leaf_fens), flush=True)

    qev, qpl = engine_vals(args.exe, quiet_fens)
    lev, lpl = engine_vals(args.exe, leaf_fens)
    print("解析：平静 %d/%d，叶子 %d/%d" % (len(qev), len(quiet_fens), len(lev), len(leaf_fens)),
          flush=True)

    def report(tag, y, ev, pl):
        if not ev:
            print("%s 无数据" % tag)
            return
        d_mlp = [abs(a - b) for a, b in zip(ev, y)]
        d_pl = [abs(a - b) for a, b in zip(pl, y)]
        # 只统计子力仍接近平衡的样本，避免「白吃一车」这种显然项拉偏均值
        print("%-10s n=%4d  价值头 MAE %7.1f | 平面 MAE %7.1f | 价值头更好 %.0f%%"
              % (tag, len(y), statistics.mean(d_mlp), statistics.mean(d_pl),
                 100 * sum(1 for a, b in zip(d_mlp, d_pl) if a < b) / len(y)))

    report("平静", quiet_y, qev, qpl)
    report("吃子后", leaf_y, lev, lpl)

    json.dump({"quiet": {"y": quiet_y, "ev": qev, "pl": qpl},
               "leaf": {"y": leaf_y, "ev": lev, "pl": lpl, "tag": leaf_tag}},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("已存", args.out)


if __name__ == "__main__":
    main()
