"""皮卡鱼自对弈采样：把顶级引擎的评分当成新的监督信号（离线数据集）。

每局随机开局 4 着，之后双方均由 Pikafish 以固定节点数出着；
每隔若干着记录一次局面与当前根的 cp 评分，落盘 data/pika_labels.pkl。
"""

import argparse
import json
import pickle
import pathlib
import random

import board as B
from cloud_label import fen_of
from match_pikafish import Pika, mv_to_uci

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--nodes", type=int, default=200)
    ap.add_argument("--max-ply", type=int, default=140)
    ap.add_argument("--every", type=int, default=4)
    ap.add_argument("--out", default="data/pika_labels.pkl")
    args = ap.parse_args()

    pika = Pika("nodes", args.nodes)
    rows, games, seen = [], [], set()
    try:
        for gi in range(args.games):
            rng = random.Random(gi * 104729 + 7)
            b = B.initial_board()
            side = B.RED
            hist, uci_hist = [], []
            init_fen = fen_of(b, B.RED)
            for ply in range(args.max_ply):
                lg = B.gen_legal(b, side)
                if not lg:
                    break
                codes = [f * 100 + t for (f, t) in lg]
                if ply < 4:
                    mv = rng.choice(codes)
                else:
                    u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
                    mv = None
                    for c in codes:
                        if mv_to_uci(c) == u:
                            mv = c
                            break
                    if mv is None:
                        mv = codes[0]
                    if cp is not None and ply % args.every == 0:
                        key = (fen_of(b, side), side)
                        if key not in seen and len(rows) < args.games * 40:
                            seen.add(key)
                            rows.append({"fen": key[0], "board": list(b), "side": side,
                                         "score": max(-1500, min(1500, cp)), "ply": ply, "game": gi})
                B.apply_move(b, (mv // 100, mv % 100))
                uci_hist.append(mv_to_uci(mv))
                hist.append(mv)
                side = -side
            games.append({"game": gi, "plies": ply + 1, "moves": uci_hist})
            print(f"第 {gi + 1}/{args.games} 局：{ply + 1} 着，累计样本 {len(rows)}", flush=True)
    finally:
        pika.close()

    d = {"rows": rows, "games": games, "ok": len(rows), "miss": 0, "nodes": args.nodes}
    pathlib.Path(HERE / args.out).write_bytes(pickle.dumps(d))
    print(json.dumps({"samples": len(rows), "games": len(games)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
