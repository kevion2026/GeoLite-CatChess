"""从战报中提取战术样本：死亡陷阱、神仙步、防守步，并转成 39 维特征。"""

import argparse
import glob
import json
import pickle
import pathlib
from collections import Counter

import numpy as np

import board as B
from trap_mine import feats39

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", default=["run3"])
    ap.add_argument("--fast-loss", type=int, default=30, help="手数不超过此值算速败")
    ap.add_argument("--back", type=int, default=3, help="速败前倒推几着")
    ap.add_argument("--jump", type=int, default=150, help="皮卡鱼评分跃升阈值")
    ap.add_argument("--out", default="data/tactical.pkl")
    args = ap.parse_args()

    M = json.load(open("model_triple.json", encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]

    rows, games = [], []
    for tag in args.tags:
      for path in sorted(glob.glob(str(HERE / "data" / "battle_logs" / f"{tag}_g*.json"))):
        g = json.loads(open(path, encoding="utf-8").read())
        g["game"] = f"{tag}_{g['game']}"
        games.append({"file": pathlib.Path(path).name, "res": g["res"], "plies": g["plies"],
                      "ours": g["ours"], "opening": g["opening"]})
        plies = g["moves"]
        # 死亡陷阱：速败局，倒推 back 着的位置
        if g["res"] == "loss" and g["plies"] <= args.fast_loss:
            idx = max(0, len(plies) - args.back)
            for j in range(idx, len(plies)):
                p = plies[j]
                if "board" not in p:
                    continue
                rows.append({"x": [round(float(v), 4) for v in feats39(p["board"], B.RED if p["side"] == "red" else B.BLACK, A, Bt, Ct)],
                             "y": -1500.0, "tag": "死亡陷阱", "game": g["game"], "ply": p["ply"], "w": 10.0})
        # 神仙步：皮卡鱼评分跃升 ≥ 阈值，取该步之前的局面（GeoLite 待走）
        pika_cps = [(i, p["cp"]) for i, p in enumerate(plies) if p["by"] == "pika" and p["cp"] is not None]
        for k in range(1, len(pika_cps)):
            i, cp = pika_cps[k]
            _, prev = pika_cps[k - 1]
            if cp - prev >= args.jump and i > 0:
                p = plies[i - 1]
                if "board" in p:
                    rows.append({"x": [round(float(v), 4) for v in feats39(p["board"], B.RED if p["side"] == "red" else B.BLACK, A, Bt, Ct)],
                                 "y": min(1500.0, float(cp)), "tag": "皮卡鱼神之一手", "game": g["game"], "ply": p["ply"], "w": 1.0})
        # 防守步：和棋局里 GeoLite 的低分差着法
        if g["res"] == "draw":
            for i, p in enumerate(plies):
                if p["by"] == "geo" and i > 0 and plies[i - 1]["cp"] is not None and abs(plies[i - 1]["cp"]) <= 50:
                    if "board" in p:
                        rows.append({"x": [round(float(v), 4) for v in feats39(p["board"], B.RED if p["side"] == "red" else B.BLACK, A, Bt, Ct)],
                                     "y": 0.0, "tag": "安全缓冲", "game": g["game"], "ply": p["ply"], "w": 2.0})
    counts = Counter(r["tag"] for r in rows)
    print("样本", len(rows), dict(counts), "| 局数", len(games), flush=True)
    pathlib.Path(HERE / args.out).write_bytes(pickle.dumps({"rows": rows, "games": games}))
    print("已写入", args.out)


if __name__ == "__main__":
    main()
