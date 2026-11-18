"""从 XQF 棋谱里抽出“局面 + 走子方胜负”样本，供几何胜率模型训练。

与 pgn_import.py 的差别只有一个：记录对局结果（红胜/和/黑胜），
转成走子方视角的 +1 / 0 / -1。
"""

import argparse
import glob
import io
import pickle
import time

import board as B
from pgn_import import STD_FIELD, iccs_to_move, moves_of
from cchess.read_xqf import read_from_xqf


def result_of(game):
    info = getattr(game, "info", {}) or {}
    r = str(info.get("result", "")).strip()
    if r == "1-0":
        return 1
    if r == "0-1":
        return -1
    if r in ("1/2-1/2", "0.5-0.5", "*"):
        return 0
    return None


def extract(path, start_ply=6, max_per_game=12, min_ply=4):
    try:
        g = read_from_xqf(path, read_annotation=False)
    except Exception:
        return [], {"read_err": 1}
    info = getattr(g, "info", {}) or {}
    if info.get("move_player") != "RED":
        return [], {"black_first": 1}
    if g.init_board.to_fen().split(" ")[0] != STD_FIELD:
        return [], {"custom_start": 1}
    res = result_of(g)
    if res is None:
        return [], {"no_result": 1}
    raw = moves_of(g)
    if not raw:
        return [], {"no_moves": 1}
    bd = B.initial_board()
    side = B.RED
    frames = []
    legal = 0
    for s in raw:
        pair = iccs_to_move(s)
        if pair is None:
            break
        if pair not in B.gen_legal(bd, side):
            break
        frames.append((tuple(bd), side))
        B.apply_move(bd, pair)
        side = -side
        legal += 1
    if legal < start_ply + min_ply:
        return [], {"short": 1}
    span = legal - start_ply
    stride = max(4, span // max(1, max_per_game))
    picks = list(range(start_ply, legal, stride))[:max_per_game]
    out = [(frames[i][0], frames[i][1], res * frames[i][1]) for i in picks]
    return out, {"ok": 1, "plies": legal}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/xqf/*.XQF")
    ap.add_argument("--out", default="data/result_positions.pkl")
    ap.add_argument("--max-per-game", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = sorted(glob.glob(args.glob)) + sorted(glob.glob(args.glob.replace(".XQF", ".xqf")))
    if args.limit:
        files = files[: args.limit]
    print("棋谱文件", len(files), flush=True)

    t0 = time.time()
    rows, agg, games = [], {}, 0
    for i, f in enumerate(files, 1):
        pos, st = extract(f, max_per_game=args.max_per_game)
        for k, v in st.items():
            agg[k] = agg.get(k, 0) + v
        if pos:
            games += 1
            rows.extend(pos)
        if i % 1000 == 0:
            print(i, "样本", len(rows), agg, f"{time.time() - t0:.0f}s", flush=True)

    with open(args.out, "wb") as fh:
        pickle.dump({"rows": rows, "agg": agg, "games": games, "files": len(files)}, fh)
    from collections import Counter

    print("完成：", games, "局，", len(rows), "个样本，", Counter(y for _, _, y in rows), agg, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
