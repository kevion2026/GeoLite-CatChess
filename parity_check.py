"""Python 侧与 JS 侧几何状态一致性检查（模型更新后必跑）。"""

import io
import json
import pickle

import board as B
import geo

LAYERS = range(0, 11)


def pick_positions():
    pos = [(B.initial_board(), B.RED)]
    try:
        with open("data/pgn_positions.pkl", "rb") as f:
            real = pickle.load(f)["positions"]
        for i in (500, 20000, 50000):
            if i < len(real):
                pos.append((real[i][0], real[i][1]))
    except FileNotFoundError:
        pass
    return pos


def main():
    with open("model.json", encoding="utf-8") as f:
        m = json.load(f)
    coords = {k: tuple(v) for k, v in m["coords2"].items()}
    out = []
    for bd, side in pick_positions():
        states = {}
        kept = {}
        for L in LAYERS:
            v, info = geo.state_of(bd, side, coords, layers=L)
            states[str(L)] = [round(float(v[0]), 4), round(float(v[1]), 4),
                              round(float(v[2]), 4), round(float(v[3]), 4)]
            kept[str(L)] = len(info.get("kept", []))
        out.append({"board": list(bd), "side": side, "states": states, "kept": kept})
    with io.open("data/parity_py.json", "w", encoding="utf-8") as f:
        json.dump(out, f)
    for rec in out:
        print("side", rec["side"], "L0", rec["states"]["0"], "L7", rec["states"]["7"], "kept7", rec["kept"]["7"])


if __name__ == "__main__":
    main()
