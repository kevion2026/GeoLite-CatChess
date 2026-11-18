"""测量皮卡鱼 50ms 与长时限的判断差：同一局面两次搜索的 bestmove 与 cp 差异。
差得大说明 50ms 会漏着，存在可利用的战术陷阱；差得小说明这条路不存在。
"""
import pickle, random, statistics, sys
import board as B
from cloud_label import fen_of
from match_pikafish import Pika

rows = pickle.load(open(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋\data\positions_200k.pkl", "rb"))
random.Random(7).shuffle(rows)
sample = rows[:40]
fast = Pika("movetime", 50)
slow = Pika("movetime", 2000)
same = 0
diffs = []
for i, (b, side, src) in enumerate(sample):
    if len(B.gen_legal(b, side)) < 2:
        continue
    fen = fen_of(b, side)
    f_best, f_cp, f_dep = fast.best(fen)
    s_best, s_cp, s_dep = slow.best(fen)
    if f_best == s_best:
        same += 1
    # cp 是走子方视角；比较同一局面下两个时限给出的分值差
    if f_cp is not None and s_cp is not None:
        diffs.append(abs(f_cp - s_cp))
    print(f"{i:2d} fast {f_best} d{f_dep} cp{f_cp} | slow {s_best} d{s_dep} cp{s_cp}", flush=True)
fast.close(); slow.close()
print("same bestmove", same, "/", len(sample))
if diffs:
    diffs.sort()
    print("cp diff median", statistics.median(diffs), "mean", round(statistics.mean(diffs), 1),
          "p90", diffs[int(len(diffs) * .9)], "max", diffs[-1])
