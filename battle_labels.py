"""把枷锁战报转成胜率训练样本：皮卡鱼每步的评分，翻成 GeoLite 视角的 cp。"""

import argparse
import glob
import json
import pickle
import pathlib

import numpy as np

import board as B
from trap_mine import feats39

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", default=["bulk1"])
    ap.add_argument("--out", default="data/battle_labels.pkl")
    args = ap.parse_args()

    M = json.load(open("model_triple.json", encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]

    rows, games = [], []
    for tag in args.tags:
        for path in sorted(glob.glob(str(HERE / "data" / "battle_logs" / f"{tag}_g*.json"))):
            g = json.loads(open(path, encoding="utf-8").read())
            games.append({"game": f"{tag}_{g['game']}", "res": g["res"], "plies": g["plies"]})
            for i, p in enumerate(g["moves"]):
                if p["cp"] is None or i == 0:
                    continue
                prev = g["moves"][i - 1]
                if "board" not in prev:
                    continue
                side = B.RED if prev["side"] == "red" else B.BLACK
                y = float(np.clip(-p["cp"], -1500, 1500))
                rows.append({"board": prev["board"], "side": side, "score": y,
                             "game": f"{tag}_{g['game']}", "ply": prev["ply"]})
    print("样本", len(rows), "局", len(games))
    pathlib.Path(HERE / args.out).write_bytes(pickle.dumps({"rows": rows, "games": games}))
    print("已写入", args.out)


if __name__ == "__main__":
    main()
