"""双三维状态双端一致性：Python 侧状态 vs node 侧状态。"""

import json

import board as B
import dual3d

D = json.load(open("model_dual.json", encoding="utf-8"))
A, Bt = D["coords3a"], D["coords3b"]

b = B.initial_board()
cases = [(list(b), B.RED)]
for ply in range(1, 40):
    lg = B.gen_legal(b, B.RED if ply % 2 else B.BLACK)
    if not lg:
        break
    B.apply_move(b, lg[ply % len(lg)])
    if ply in (6, 14, 26):
        cases.append((list(b), B.RED if ply % 2 else B.BLACK))

out = []
for bd, side in cases:
    rows = []
    for layer in range(4):
        v, _ = dual3d.state_dual(bd, side, A, Bt, layers=layer)
        rows.append([round(float(x), 6) for x in v])
    out.append({"board": [int(x) for x in bd], "side": int(side), "layers": rows})
json.dump(out, open("data/parity_dual.json", "w", encoding="utf-8"))
print("cases", len(out), "dim", len(out[0]["layers"][0]))
