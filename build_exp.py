"""从 XQF 名局谱重建「局面 → 着法 → 胜负」经验库（替代 result_positions.pkl）。

旧库有三个致命问题，这里逐条修掉：

1. **标签是整盘胜负**。一盘棋里每个局面都贴同一个标签，局面级信噪比极低。
   这里同时存「该局面下名手实际走的着法」——走子先验（policy prior）比
   「局面价值」稳得多：它问的是「类似局面里人类怎么下」，不是「谁会赢」。
2. **采样步长恒为偶数**，导致 86% 的局面是红方走子。这里逐子（stride=1）采样，
   天然红黑各半。
3. **库太小**（12000）。这里从 5000+ 份棋谱抽 12 万级局面。

存储用 array('f') 平铺（45 维/局面，4 字节），12 万局面约 22MB；
检索时先用「子力签名」分桶（同兵种同数量的局面才可能相似），桶内再算
分块加权距离，把候选集从 12 万压到千级，纯 Python 也能跑到毫秒级。
"""

import argparse
import glob
import pickle
import sys
import time
from array import array

import board as B
from geo_predict import Featurizer, RED, material_key, board_hash


# ---------------------------------------------------------------- 子力签名
def build(games_glob="data/xqf/*", limit=120000, min_ply=4, model="model_triple.json", verbose=True):
    try:
        from cchess.read_xqf import read_from_xqf
    except Exception as e:                                   # pragma: no cover
        raise SystemExit("缺少 cchess：pip install cchess（%s）" % e)
    from pgn_import import moves_of, iccs_to_move, STD_FIELD
    from result_import import result_of

    fz = Featurizer(model)
    feats = array("f")
    hashes = array("q")
    moves = array("i")
    res = array("b")
    plies = array("h")
    sides = array("b")
    buckets = {}

    files = sorted(glob.glob(games_glob))
    if verbose:
        print(f"棋谱 {len(files)} 份，目标 {limit} 个局面", flush=True)
    t0 = time.time()
    stat = {"ok": 0, "short": 0, "err": 0, "skip": 0, "pos": 0}

    for gi, path in enumerate(files):
        if len(moves) >= limit:
            break
        try:
            g = read_from_xqf(path, read_annotation=False)
        except Exception:
            stat["err"] += 1
            continue
        info = getattr(g, "info", {}) or {}
        if info.get("move_player") != "RED":
            stat["skip"] += 1
            continue
        try:
            if g.init_board.to_fen().split(" ")[0] != STD_FIELD:
                stat["skip"] += 1
                continue
        except Exception:
            stat["skip"] += 1
            continue
        r = result_of(g)
        if r is None:
            stat["skip"] += 1
            continue
        raw = moves_of(g)
        if not raw:
            stat["skip"] += 1
            continue

        bd = B.initial_board()
        side = B.RED
        legal_n = 0
        for s_iccs in raw:
            pair = iccs_to_move(s_iccs)
            if pair is None:
                break
            if pair not in B.gen_legal(bd, side):
                break
            if legal_n >= min_ply:
                f45 = fz.feats45(bd, side)
                if len(f45) == 45:
                    # 存标准化后的向量：检索时直接用，避免每次查询重复标准化
                    feats.extend(fz.standardize(f45))
                    hashes.append(board_hash(bd, side))
                    # 存原始着法（不做镜像）：检索时只取同走子方的邻居，
                    # 镜像会把「红马二进三」和「黑马8进7」混成一类，先验反而变糊。
                    moves.append(int(pair[0]) * 100 + int(pair[1]))
                    res.append(r * side)                 # 走子方视角
                    plies.append(min(32767, legal_n))
                    sides.append(side)
                    buckets.setdefault(material_key(bd, side, f45), []).append(len(moves) - 1)
                    stat["pos"] += 1
            B.apply_move(bd, pair)
            side = -side
            legal_n += 1
        if legal_n < min_ply + 4:
            stat["short"] += 1
        else:
            stat["ok"] += 1
        if verbose and (gi + 1) % 400 == 0:
            print(f"  {gi+1} 份 / 局面 {len(moves)}  {time.time()-t0:.0f}s", flush=True)

    if verbose:
        print(f"完成：{len(moves)} 局面，{len(buckets)} 个子力桶，{time.time()-t0:.0f}s", flush=True)
        print("统计", stat, flush=True)
    return {"feats": feats, "hashes": hashes, "moves": moves, "res": res, "plies": plies,
            "sides": sides, "buckets": buckets, "stat": stat,
            "meta": {"n": len(moves), "source": "xqf", "limit": limit, "min_ply": min_ply}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120000)
    ap.add_argument("--min-ply", type=int, default=4)
    ap.add_argument("--glob", default="data/xqf/*")
    ap.add_argument("--out", default="data/exp_move.pkl")
    ap.add_argument("--model", default="model_triple.json")
    args = ap.parse_args()
    lib = build(args.glob, args.limit, args.min_ply, args.model)
    with open(args.out, "wb") as f:
        pickle.dump(lib, f, protocol=4)
    print(f"已写入 {args.out}")


if __name__ == "__main__":
    main()
