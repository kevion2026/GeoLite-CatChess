"""构建反飞刀黑名单：速败局前段局面全部入册，并整理开局库为可加载 JSON。"""

import argparse
import glob
import json
import pickle
import pathlib

import numpy as np

import board as B
from trap_mine import feats39
from tree_winprob import TreeExpert

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", default=["verify100"])
    ap.add_argument("--fast-loss", type=int, default=30)
    ap.add_argument("--head", type=int, default=20)
    ap.add_argument("--out", default="data/blacklist.pkl")
    ap.add_argument("--model", default="model_triple.json")
    args = ap.parse_args()

    M = json.load(open(HERE / args.model, encoding="utf-8"))
    A = (M["coords3a"], M["coords3b"], M["coords3c"])

    rows, games = [], []
    for tag in args.tags:
        for path in sorted(glob.glob(str(HERE / "data" / "battle_logs" / f"{tag}_g*.json"))):
            g = json.loads(open(path, encoding="utf-8").read())
            if g["res"] != "loss" or g["plies"] > args.fast_loss:
                continue
            games.append(g["game"])
            for p in g["moves"][:args.head]:
                if "board" not in p:
                    continue
                rows.append({"x": [round(float(v), 4) for v in feats39(p["board"], B.RED if p["side"] == "red" else B.BLACK, *A)],
                             "y": -9999.0, "game": g["game"], "ply": p["ply"]})
    print("速败局", len(games), "黑名单局面", len(rows), flush=True)
    pathlib.Path(HERE / args.out).write_bytes(pickle.dumps({"rows": rows, "games": games}))
    print("已写入", args.out)


if __name__ == "__main__":
    main()
