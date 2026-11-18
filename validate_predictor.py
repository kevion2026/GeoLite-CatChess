"""评测 GeometricPredictor 的走子质量：与固定局面集上的皮卡鱼首选着对比。

指标与 bench_positions.py 完全同口径（top1 命中率），便于横向比较：
  - 几何树（线上默认）在同一 117 个局面上 top1 = 16.2%
  - 本模块只看「历史相似局面的胜负」，不含任何形状/子力估值
"""

import argparse
import json
import statistics
import time

import board as B
from match_pikafish import mv_to_uci
from geo_predict import GeometricPredictor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--exp", default="data/exp_lib.pkl")
    ap.add_argument("--exp-move", default="data/exp_move.pkl", help="走子先验库；存在则优先用")
    ap.add_argument("--pos", default="data/pos_set.json")
    ap.add_argument("--ref", default="data/pos_ref.json")
    ap.add_argument("--lo", type=int, default=-700)
    ap.add_argument("--hi", type=int, default=300)
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    poss = json.load(open(args.pos, encoding="utf-8"))
    ref = json.load(open(args.ref, encoding="utf-8"))
    p = GeometricPredictor(args.model, exp_path=None)
    import os
    if args.exp_move and os.path.exists(args.exp_move):
        p.load_move_experience(args.exp_move)
        print("使用走子先验库", args.exp_move, "节点", len(p.mmoves))
    else:
        p.load_experience(args.exp)

    n = 0
    hit1 = hit3 = 0
    secs = []
    t0 = time.time()
    for i, po in enumerate(poss):
        r0 = ref.get(str(i))
        if not r0 or r0.get("cp") is None or r0.get("mate") is not None:
            continue
        if not (args.lo <= r0["cp"] <= args.hi):
            continue
        if args.limit and n >= args.limit:
            break
        b, s = po["b"], po["s"]
        lg = B.gen_legal(b, s)
        if not lg:
            continue
        t1 = time.time()
        rows = p.stitch_and_score(b, s, lg, top_k=args.topk, ply=po.get("ply"))
        secs.append(time.time() - t1)
        order = [mv for mv, _sc in rows]          # mv 是 (from, to) 元组
        best = r0["uci"]
        if best and mv_to_uci(order[0][0] * 100 + order[0][1]) == best:
            hit1 += 1
        if best and any(mv_to_uci(mv[0] * 100 + mv[1]) == best for mv in order[:3]):
            hit3 += 1
        n += 1
        if n % 25 == 0:
            print(f"  {n} 个局面  {time.time()-t0:.0f}s", flush=True)

    if not n:
        print("没有可用局面")
        return
    print(json.dumps({
        "n": n, "top1": round(hit1 / n, 3), "top3": round(hit3 / n, 3),
        "avg_ms": round(statistics.mean(secs) * 1000, 1),
        "total_s": round(time.time() - t0, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
