"""从全部 XQF 棋谱建「局面 → 着法统计」表，用于引擎运行期的历史检索。

与 `build_exp.py` 的区别：这里不需要 45 维特征，只要「这个局面名手走过哪些着法、
各多少次」。所以可以吃下全部 5000+ 份棋谱、几万局对局，而不用付特征计算的开销。

产出 `data/prior_book.json`，格式：
    {"meta": {...}, "entries": {"<32位哈希>": [[move, n, win, draw, loss], ...]}}

键用 32 位 FNV-1a（Python 与 JS 用同一套位运算），引擎端可直接查表。
"""

import argparse
import glob
import json
import time

import board as B
from result_import import result_of


# 与 engine3d.js 完全一致的 Zobrist：固定种子 LCG 生成 90×15 表，
# 局面哈希 = 逐格 XOR。两端必须逐位相同，否则引擎查不到表。
_ZOB = []
_s = 20261115
for _i in range(90 * 15):
    # 必须按 IEEE754 双精度 + ToInt32 复刻：JS 里 s*1103515245 超过 2^53，
    # 乘法已经丢低位，用精确整数算出来的表与引擎不一致（实测键完全不同）。
    _x = float(_s) * 1103515245.0 + 12345.0
    _i32 = int(_x) % (2 ** 32)
    if _i32 >= 2 ** 31:
        _i32 -= 2 ** 32
    _s = _i32 & 0x7FFFFFFF
    _ZOB.append(_s)
SIDE_Z = 0x5BF03635


def _pidx(p):
    return p if p > 0 else 7 - p


def hash32(board, side):
    """引擎同款局面键（含走子方），非负 32 位。"""
    h = 0
    for sq in range(90):
        p = board[sq]
        if p:
            h ^= _ZOB[sq * 15 + _pidx(p)]
    return (h ^ (SIDE_Z if side == B.RED else 0)) & 0x7FFFFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/xqf/*")
    ap.add_argument("--max-ply", type=int, default=30, help="只收前 N 手，控制表体积")
    ap.add_argument("--min-n", type=int, default=2, help="某着法至少出现几次才收录")
    ap.add_argument("--out", default="data/prior_book.json")
    ap.add_argument("--file-start", type=int, default=0)
    ap.add_argument("--file-end", type=int, default=0, help="0 表示到结尾")
    args = ap.parse_args()

    from cchess.read_xqf import read_from_xqf
    from pgn_import import moves_of, iccs_to_move, STD_FIELD

    files = sorted(glob.glob(args.glob))
    lo = args.file_start
    hi = args.file_end if args.file_end else len(files)
    files = files[lo:hi]
    print(f"棋谱 {len(files)} 份（第 {lo}~{hi} 份），收录前 {args.max_ply} 手", flush=True)

    # key -> {move: [n, win, draw, loss]}
    book = {}
    t0 = time.time()
    games = 0
    for gi, path in enumerate(files):
        try:
            g = read_from_xqf(path, read_annotation=False)
        except Exception:
            continue
        info = getattr(g, "info", {}) or {}
        if info.get("move_player") != "RED":
            continue
        try:
            if g.init_board.to_fen().split(" ")[0] != STD_FIELD:
                continue
        except Exception:
            continue
        res = result_of(g)
        if res is None:
            continue
        raw = moves_of(g)
        if not raw:
            continue
        bd = B.initial_board()
        side = B.RED
        ok = True
        n_ply = 0
        for s_iccs in raw:
            pair = iccs_to_move(s_iccs)
            if pair is None:
                ok = False
                break
            f, t = pair
            pc = bd[f]
            # 轻校验：起点必须是我方棋子、终点不能是己方棋子。
            # 不为建库跑 gen_legal（每手 ~2ms，会拖到十几分钟且没有必要）。
            if not pc or (pc > 0) != (side > 0) or (bd[t] and (bd[t] > 0) == (side > 0)):
                ok = False
                break
            if n_ply >= args.max_ply:
                break
            key = hash32(bd, side)
            mv = pair[0] * 100 + pair[1]
            slot = book.setdefault(key, {})
            row = slot.get(mv)
            if row is None:
                row = [0, 0, 0, 0]
                slot[mv] = row
            row[0] += 1
            own = res * side                       # 走子方视角
            row[1 if own > 0 else (2 if own == 0 else 3)] += 1
            B.apply_move(bd, pair)
            side = -side
            n_ply += 1
        if ok and n_ply >= 8:
            games += 1
        if (gi + 1) % 500 == 0:
            print(f"  {gi+1} 份 / 局面 {len(book)}  {time.time()-t0:.0f}s", flush=True)

    entries = {}
    for key, slot in book.items():
        rows = [[mv, r[0], r[1], r[2], r[3]] for mv, r in slot.items() if r[0] >= args.min_n]
        if rows:
            rows.sort(key=lambda r: -r[1])
            entries[str(key)] = rows[:6]           # 每局面最多留 6 个候选着法
    payload = {"meta": {"games": games, "files": len(files), "max_ply": args.max_ply,
                        "min_n": args.min_n, "positions": len(entries),
                        "built": time.strftime("%Y-%m-%d %H:%M")},
               "entries": entries}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    import os
    print(f"对局 {games}，局面 {len(entries)}，文件 {os.path.getsize(args.out)/1048576:.1f}MB，"
          f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
