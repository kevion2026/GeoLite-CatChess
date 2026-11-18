"""重建反飞刀黑名单：速败局前段 + 致命末段，写入激活树的报警源。"""

import argparse
import glob
import json
import pathlib

import numpy as np

import board as B
from trap_mine import feats39

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", default=["verify100", "verify100b"])
    ap.add_argument("--fast-loss", type=int, default=30)
    ap.add_argument("--head", type=int, default=20)
    ap.add_argument("--tail", type=int, default=6)
    ap.add_argument("--model", default="model_triple.json")
    args = ap.parse_args()

    M = json.load(open(HERE / args.model, encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])
    tm = M["tree"]["model"]
    means = np.asarray(tm["mean"], float)
    stds = np.asarray(tm["std"], float)

    vecs = []   # (x39, 半径, 强度)
    games = 0
    for tag in args.tags:
        for path in sorted(glob.glob(str(HERE / "data" / "battle_logs" / f"{tag}_g*.json"))):
            g = json.loads(open(path, encoding="utf-8").read())
            if g["res"] != "loss" or g["plies"] > args.fast_loss:
                continue
            games += 1
            ms = g["moves"]
            picked = ms[:args.head] + (ms[-args.tail:] if args.tail > 0 else [])
            for p in picked:
                if "board" not in p:
                    continue
                side = B.RED if p["side"] == "red" else B.BLACK
                vecs.append((feats39(p["board"], side, *AC), 0.40 if p["ply"] < args.head else 0.45,
                             3000.0 if p["ply"] < args.head else 5000.0))
    X = np.asarray([v[0] for v in vecs], float)
    Z = (X - means) / np.where(stds == 0, 1, stds)
    M["tree"]["blacklist"] = [{"x": [round(float(v), 4) for v in z], "r": vecs[i][1], "k": vecs[i][2]}
                              for i, z in enumerate(Z)]
    M["tree"]["blacklist_meta"] = {"count": len(Z), "games": games, "tags": args.tags}
    json.dump(M, open(HERE / args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("速败局", games, "黑名单", len(Z))


if __name__ == "__main__":
    main()
