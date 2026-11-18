"""用留出名局谱评测「走子先验」：库内没见过这些对局，看它能否预测人类着法。

为什么不用「与皮卡鱼首选一致率」当指标：先验的职责是回答「人类在这种局面
通常怎么走」，而皮卡鱼的首选常常是深搜才能算出的战术手，人类不会那么下。
用皮卡鱼衡量先验，等于用错误的尺子量东西。

留出方式：库由 `data/xqf` 前 1600 份棋谱建成，这里只读排序在 4000 之后的棋谱。
"""

import argparse
import glob
import json
import random
import statistics
import time

import board as B
from geo_predict import GeometricPredictor, RED


def held_out_games(glob_pat, skip_files, max_games, min_ply=6, max_ply=40):
    from cchess.read_xqf import read_from_xqf
    from pgn_import import moves_of, iccs_to_move, STD_FIELD

    files = sorted(glob.glob(glob_pat))[skip_files:]
    out = []
    for path in files:
        if len(out) >= max_games:
            break
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
        raw = moves_of(g)
        if not raw:
            continue
        bd = B.initial_board()
        side = B.RED
        seq = []
        ok = True
        for s_iccs in raw:
            pair = iccs_to_move(s_iccs)
            if pair is None or pair not in B.gen_legal(bd, side):
                ok = False
                break
            seq.append((list(bd), side, pair))
            B.apply_move(bd, pair)
            side = -side
        if ok and len(seq) >= min_ply + 6:
            out.append(seq)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="data/exp_move.pkl")
    ap.add_argument("--glob", default="data/xqf/*")
    ap.add_argument("--skip-files", type=int, default=4000)
    ap.add_argument("--games", type=int, default=120)
    ap.add_argument("--samples", type=int, default=400)
    ap.add_argument("--min-ply", type=int, default=6)
    ap.add_argument("--max-ply", type=int, default=40)
    args = ap.parse_args()

    p = GeometricPredictor("model_triple.json", exp_path=None).load_move_experience(args.exp)
    print("库节点", len(p.mmoves), "桶", len(p.mbuckets), flush=True)
    games = held_out_games(args.glob, args.skip_files, args.games)
    print("留出对局", len(games), flush=True)
    if not games:
        return

    pool = []
    for seq in games:
        for b, side, mv in seq:
            pool.append((b, side, mv))
    rng = random.Random(20261115)
    if len(pool) > args.samples:
        pool = rng.sample(pool, args.samples)

    t0 = time.time()
    hit1 = hit3 = hit10 = legal_n = 0
    masses = []
    for b, side, mv in pool:
        lg = B.gen_legal(b, side)
        if mv not in lg:
            continue
        # 用着法序号近似 ply：先验里的步数惩罚只需要同一个量纲
        ply = None
        rows = p.stitch_and_score(b, side, lg, top_k=64, ply=ply)
        order = [x[0] for x in rows]
        target = (mv[0] * 100 + mv[1])
        cand = [(m[0] * 100 + m[1]) for m in order]
        if target in cand:
            r = cand.index(target)
            hit1 += r == 0
            hit3 += r < 3
            hit10 += r < 10
            masses.append(rows[r][1])
            legal_n += 1
    n = len(pool)
    print(json.dumps({
        "n": n, "with_prior": legal_n,
        "human_top1": round(hit1 / n, 3), "human_top3": round(hit3 / n, 3),
        "human_top10": round(hit10 / n, 3),
        "secs": round(time.time() - t0, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
