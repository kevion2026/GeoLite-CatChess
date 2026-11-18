"""从真实棋谱里挖开局库：局面 -> 着法 -> 胜负统计。

只取标准开局、红先的棋谱；每一手都用本项目 board.py 校验合法，
非法即截断该局。输出 data/book_raw.json（坐标与着法都用引擎的整数编码），
再由 book_pack.js 用引擎自己的 Zobrist 键压缩成 data/book.json。
"""

import argparse
import glob
import io
import json
import time

import board as B

try:
    from cchess.read_xqf import read_from_xqf
except Exception as e:  # pragma: no cover
    read_from_xqf = None
    print("缺少 cchess：pip install cchess", e)

STD_FIELD = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"
BOOK_PLIES = 16


def iccs_to_move(s):
    f, t = s[:2], s[2:4]
    fx, fy = ord(f[0]) - 97, 9 - int(f[1])
    tx, ty = ord(t[0]) - 97, 9 - int(t[1])
    if not (0 <= fx < 9 and 0 <= fy < 10 and 0 <= tx < 9 and 0 <= ty < 10):
        return None
    return (fy * 9 + fx) * 100 + (ty * 9 + tx)


def moves_of(game):
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


def result_of(game):
    """返回 1（红胜）/ 0（和）/ -1（黑胜）/ None（未知）。"""
    info = getattr(game, "info", {}) or {}
    r = str(info.get("result", "")).strip()
    if r == "1-0":
        return 1
    if r == "0-1":
        return -1
    if r in ("1/2-1/2", "0.5-0.5", "*"):
        return 0
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/xqf/*.XQF")
    ap.add_argument("--plies", type=int, default=BOOK_PLIES)
    ap.add_argument("--out", default="data/book_raw.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-total", type=int, default=2)
    args = ap.parse_args()

    files = sorted(glob.glob(args.glob)) + sorted(glob.glob(args.glob.replace(".XQF", ".xqf")))
    if args.limit:
        files = files[: args.limit]
    print("棋谱文件", len(files))

    book = {}          # (board_tuple, side) -> {mv: [w, d, l, unk]}
    agg = {}
    t0 = time.time()
    games_used = 0
    for i, f in enumerate(files, 1):
        try:
            g = read_from_xqf(f, read_annotation=False)
        except Exception:
            agg["read_err"] = agg.get("read_err", 0) + 1
            continue
        info = getattr(g, "info", {}) or {}
        if info.get("move_player") != "RED":
            agg["black_first"] = agg.get("black_first", 0) + 1
            continue
        if g.init_board.to_fen().split(" ")[0] != STD_FIELD:
            agg["custom_start"] = agg.get("custom_start", 0) + 1
            continue
        res = result_of(g)
        raw = moves_of(g)
        if not raw:
            agg["no_moves"] = agg.get("no_moves", 0) + 1
            continue
        bd = B.initial_board()
        side = B.RED
        used = 0
        for ply, s in enumerate(raw[: args.plies]):
            mv = iccs_to_move(s)
            if mv is None:
                break
            pair = (mv // 100, mv % 100)
            if pair not in B.gen_legal(bd, side):
                agg["cut"] = agg.get("cut", 0) + 1
                break
            key = (tuple(bd), side)
            slot = book.setdefault(key, {}).setdefault(mv, [0, 0, 0, 0])
            if res is None:
                slot[3] += 1
            elif res * side > 0:
                slot[0] += 1          # 走子方赢
            elif res * side < 0:
                slot[2] += 1          # 走子方输
            else:
                slot[1] += 1          # 和
            B.apply_move(bd, pair)
            side = -side
            used += 1
        if used:
            games_used += 1
        if i % 1000 == 0:
            print(i, "局面", len(book), agg, f"{time.time() - t0:.0f}s", flush=True)

    out = []
    for (b, s), mvmap in book.items():
        total = sum(sum(v) for v in mvmap.values())
        if total < args.min_total:
            continue
        rows = [[mv, sum(v), v[0], v[1], v[2], v[3]] for mv, v in mvmap.items() if sum(v) >= 2]
        if not rows:
            continue
        rows.sort(key=lambda r: -r[1])
        out.append({"b": list(b), "s": s, "m": rows[:5], "n": total})
    with io.open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"plies": args.plies, "games": games_used, "entries": out}, fh)
    print(f"完成：{games_used} 局入书，{len(out)} 个局面，统计 {agg}，{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
