"""三维状态的双端一致性：Python 侧生成状态，node 侧复用同一坐标表比对。"""

import json

import board as B
import geo

model = json.load(open("model3d.json", encoding="utf-8"))
coords = model["coords3"]

cases = []
# 初始局面 + 三个阶段的自对弈局面
b = B.initial_board()
cases.append((list(b), B.RED))
for ply in range(1, 40):
    lg = B.gen_legal(b, B.RED if ply % 2 else B.BLACK)
    if not lg:
        break
    B.apply_move(b, lg[ply % len(lg)])
    if ply in (6, 14, 26):
        cases.append((list(b), B.RED if ply % 2 else B.BLACK))
# 再补一个真实棋谱局面
import pickle
d = pickle.load(open("data/pgn_positions.pkl", "rb"))
b2, s2 = d["positions"][1234]
cases.append((list(b2), s2))

out = []
for bd, side in cases:
    rows = []
    for layer in range(0, 4):
        v, _ = geo.state_of(bd, side, coords, layers=layer, dim=3)
        rows.append([round(float(x), 6) for x in v])
    out.append({"board": [int(x) for x in bd], "side": int(side), "layers": rows})

json.dump(out, open("data/parity3d.json", "w", encoding="utf-8"))
print("cases", len(out), "state dim", len(out[0]["layers"][0]))
