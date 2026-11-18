"""挖「案发现场」：跑 GeoLite 对 Pikafish，把速败局的致命前几着转成 39 维特征存盘。"""

import argparse
import json
import pickle
import pathlib

import numpy as np

import board as B
import geo
import triple3d
from cloud_label import fen_of
from dual_winprob import shape_feats
from matfeat import mat_feats
from match_pikafish import Pika, Ours, mv_to_uci

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def feats39(board_, side, A, Bt, Ct):
    v, _ = triple3d.state_triple(board_, side, A, Bt, Ct, layers=0)
    toks = geo.position_tokens(board_, side)
    pa = [(t[3], A[t[0]]) for t in toks if t[0] in A]
    pb = [(t[3], Bt[t[0]]) for t in toks if t[0] in Bt]
    pc = [(t[3], Ct[t[0]]) for t in toks if t[0] in Ct]
    sh = (shape_feats(v[:7], pa) + shape_feats(v[7:14], pb) + shape_feats(v[14:21], pc))
    return np.asarray(list(v) + list(sh) + mat_feats(board_, side), dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--nodes", type=int, default=200)
    ap.add_argument("--max-ply", type=int, default=70)
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--out", default="data/traps.pkl")
    args = ap.parse_args()

    M = json.load(open(args.model, encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]
    pika = Pika("nodes", args.nodes)
    ours = Ours(args.model)
    traps, logs = [], []
    try:
        for gi in range(args.games):
            b = B.initial_board()
            side = B.RED
            ours_side = B.RED if gi % 2 == 0 else B.BLACK
            mvs, keys, uci_hist, snaps = [], [], [], []
            init_fen = fen_of(b, B.RED)
            plies = 0
            for ply in range(args.max_ply):
                lg = B.gen_legal(b, side)
                if not lg:
                    break
                codes = [f * 100 + t for (f, t) in lg]
                if ply < 4:
                    mv = codes[ply % len(codes)]
                elif side == ours_side:
                    r = ours.best(mvs, keys)
                    mv = r["mv"] if r["mv"] in codes else codes[0]
                else:
                    u, cp, _ = pika.best(fen_of(b, side) + " - - 0 1", hist=uci_hist, init_fen=init_fen)
                    mv = next((c for c in codes if mv_to_uci(c) == u), codes[0])
                snaps.append((b.copy(), side))
                B.apply_move(b, (mv // 100, mv % 100))
                mvs.append(mv)
                keys.append(hash(fen_of(b, -side)))
                uci_hist.append(mv_to_uci(mv))
                side = -side
                plies = ply + 1
            # 判定：无合法着法者负
            loser = side if not B.gen_legal(b, side) else None
            res = "unfinished"
            if loser == ours_side:
                res = "loss"
            elif loser is not None:
                res = "win"
            logs.append({"game": gi + 1, "plies": plies, "res": res, "ours": "red" if ours_side == B.RED else "black"})
            print(json.dumps(logs[-1], ensure_ascii=False), flush=True)
            if res == "loss" and plies <= 64:
                # 死局前 2~8 着，每隔 2 着取一个「看起来还不错」的局面
                for back in range(2, min(9, plies), 2):
                    idx = plies - back
                    bb, ss = snaps[idx]
                    traps.append({
                        "x": [round(float(v), 4) for v in feats39(bb, ss, A, Bt, Ct)],
                        "our_side": int(ours_side), "side": int(ss),
                        "back": back, "game": gi + 1,
                        "loss_ply": plies,
                    })
    finally:
        ours.close()
        pika.close()

    pathlib.Path(HERE / args.out).write_bytes(pickle.dumps({"traps": traps, "games": logs}))
    print(json.dumps({"traps": len(traps), "losses": sum(1 for g in logs if g["res"] == "loss"),
                      "games": len(logs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
