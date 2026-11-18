"""对拍：Python 的 Featurizer 与 engine3d.js 的 45 维特征必须逐位一致。"""

import json
import random
import subprocess
import sys

import board as B
from geo_predict import RED, BLACK, Featurizer


def main():
    rng = random.Random(20261115)
    boards = []

    # 1) 开局 + 随机推进的对局局面
    for g in range(6):
        b = B.initial_board()
        side = RED
        for ply in range(rng.randint(0, 60)):
            lg = B.gen_legal(b, side)
            if not lg:
                break
            B.apply_move(b, rng.choice(lg))
            side = -side
            if ply % 9 == 0:
                boards.append((list(b), side))
    # 2) 真实对局局面（如果存在）
    try:
        rows = json.load(open("data/fit_rows.json", encoding="utf-8"))
        for r in rows[:40]:
            boards.append((list(r["b"]), r["s"]))
    except Exception as e:
        print("跳过 fit_rows:", e)

    fz = Featurizer("model_triple.json")
    p = subprocess.Popen(["node", "dump_feats.js"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", bufsize=1)
    lines = []
    try:
        # 必须一问一答：先把所有请求写完会把 node 的 stdout 管道塞满而死锁
        for b, s in boards:
            p.stdin.write(json.dumps({"b": b, "s": s}) + "\n")
            p.stdin.flush()
            line = p.stdout.readline()
            if not line:
                raise RuntimeError("node 无响应: " + (p.stderr.read() or "")[:300])
            lines.append(line.strip())
        p.stdin.close()
    finally:
        try:
            p.kill()
        except Exception:
            pass

    if len(lines) != len(boards):
        print("node 输出行数不符", len(lines), len(boards), p.stderr.read()[:300])
        return 1

    worst = 0.0
    worst_i = -1
    for k, (b, s) in enumerate(boards):
        js = json.loads(lines[k])
        py = fz.feats45(b, s)
        if len(js) != 45 or len(py) != 45:
            print("维度错误", len(js), len(py))
            return 1
        for j in range(45):
            d = abs(js[j] - py[j])
            if d > worst:
                worst, worst_i = d, (k, j, js[j], py[j])
    print(f"对拍 {len(boards)} 个局面，最大绝对误差 {worst:.3e}")
    if worst > 1e-6:
        print("最差位置", worst_i)
        return 1
    print("45 维特征与 JS 引擎一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
