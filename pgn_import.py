"""把 XQF 棋谱（象棋巫师格式）转成局面语料。

只用 cchess 解出着法的起止格，合法性、走子与局面采样全部走本项目自己的
board.py，任何非法着法都视为棋谱损坏并截断该局，统计后写进元信息。
"""

import argparse
import glob
import io
import json
import os
import pickle
import time

import board as B

try:
    from cchess.read_xqf import read_from_xqf
except Exception as e:  # pragma: no cover
    read_from_xqf = None
    print("缺少 cchess：pip install cchess", e)

STD_START = B.initial_board()
STD_FIELD = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"


def iccs_to_move(s):
    """'h2e2' -> (from_sq, to_sq)，列 a-i，行 0-9（红方底线为 0 行）。"""
    f, t = s[:2], s[2:4]
    fx, fy = ord(f[0]) - 97, 9 - int(f[1])
    tx, ty = ord(t[0]) - 97, 9 - int(t[1])
    if not (0 <= fx < 9 and 0 <= fy < 10 and 0 <= tx < 9 and 0 <= ty < 10):
        return None
    return (fy * 9 + fx, ty * 9 + tx)


def moves_of(game):
    """取主线着法（多分支棋谱只取第一条主线）。"""
    for attr in ("dump_iccs_moves", "move_line_to_list"):
        if hasattr(game, attr):
            try:
                data = getattr(game, attr)()
            except Exception:
                continue
            if isinstance(data, list) and data and isinstance(data[0], list):
                return data[0]
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
    return []


def import_game(path, sample_from=6, sample_every=4, max_per_game=12):
    try:
        g = read_from_xqf(path, read_annotation=False)
    except Exception:
        return [], {"err": 1}
    if g.init_board.to_fen().split(" ")[0] != STD_FIELD:
        return [], {"custom_start": 1}
    raw = moves_of(g)
    if not raw:
        return [], {"no_moves": 1}
    bd = B.initial_board()
    side = B.RED
    frames = []                     # 每手之前的（局面, 走子方）
    legal_n = 0
    for s in raw:
        mv = iccs_to_move(s)
        if mv is None or mv not in B.gen_legal(bd, side):
            break
        frames.append((list(bd), side))
        B.apply_move(bd, mv)
        side = -side
        legal_n += 1
    if legal_n <= sample_from:
        return [], {"short": 1, "plies": legal_n}
    # 从第 sample_from 手起，按等间隔覆盖整局（开局、中局、残局都能采到）
    span = legal_n - sample_from
    stride = max(sample_every, span // max(1, max_per_game))
    picks = list(range(sample_from, legal_n, stride))[:max_per_game]
    out = [frames[i] for i in picks]
    stats = {"ok": 1, "plies": legal_n, "cut": 1 if legal_n < len(raw) else 0}
    return out, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/xqf/*.XQF")
    ap.add_argument("--out", default="data/pgn_positions.pkl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample-every", type=int, default=4)
    ap.add_argument("--max-per-game", type=int, default=12)
    args = ap.parse_args()

    files = sorted(glob.glob(args.glob)) + sorted(glob.glob(args.glob.replace(".XQF", ".xqf")))
    if args.limit:
        files = files[: args.limit]
    print("棋谱文件", len(files))

    t0 = time.time()
    positions, agg, games_ok = [], {}, 0
    for i, f in enumerate(files, 1):
        pos, st = import_game(f, sample_every=args.sample_every, max_per_game=args.max_per_game)
        for k, v in st.items():
            agg[k] = agg.get(k, 0) + v
        if pos:
            games_ok += 1
            positions.extend(pos)
        if i % 500 == 0:
            print(i, "局面", len(positions), agg, f"{time.time() - t0:.0f}s", flush=True)

    with open(args.out, "wb") as fh:
        pickle.dump({"positions": positions, "agg": agg, "files": len(files)}, fh)
    print(f"完成：{games_ok} 局可解析，{len(positions)} 个局面，统计 {agg}，{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
