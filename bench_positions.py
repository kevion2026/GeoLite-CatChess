"""固定局面基准：所有配置在**完全相同的局面集**上比拼走子质量（CPL）。

相比对局式评测，方差小一个量级：同一配置重复测波动约 ±6 cp，而不是 ±20。
局面取自真实对局（battle_labels），覆盖布局到中局。

用法：
  python bench_positions.py --modes cl0,cls,ra8,ra12 --n 160 --ref 60
"""

import argparse
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

import board as B
from match_pikafish import Pika, mv_to_uci
from move_quality import analyse

HERE = pathlib.Path(__file__).resolve().parent
POS = HERE / "data" / "pos_set.json"
REF = HERE / "data" / "pos_ref.json"
MREF = HERE / "data" / "pos_move_ref.json"


class Srv:
    def __init__(self, mode, model=None):
        model = model or os.environ.get("GEO_MODEL", "model_triple.json")
        self.p = subprocess.Popen(
            ["node", str(HERE / "_our_server.js"), str(HERE / model),
             str(HERE / "engine3d.js"), mode],
            cwd=str(HERE), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
            env={**os.environ, "GEO_SEED": "20261115"})
        self.mode = mode

    def best(self, board, side):
        self.p.stdin.write(json.dumps({"board": list(board), "side": side}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError((self.p.stderr.read() or "")[:400])
        return json.loads(line)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def build_positions(n):
    rows = json.loads((HERE / "data" / "fit_rows.json").read_text(encoding="utf-8"))
    cand = []
    for r in rows:
        if not (8 <= r["p"] <= 55):
            continue
        b = r["b"]
        lg = B.gen_legal(b, r["s"])
        if len(lg) < 3:
            continue
        cand.append({"b": b, "s": r["s"], "ply": r["p"], "g": r["g"]})
    if not cand:
        raise SystemExit("没有可用局面")
    stride = max(1, len(cand) // n)
    out = cand[::stride][:n]
    POS.write_text(json.dumps(out), encoding="utf-8")
    print(f"局面集 {len(out)} 个（候选 {len(cand)}，步长 {stride}）", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="cl0,cls,ra8,ra12")
    ap.add_argument("--n", type=int, default=160)
    ap.add_argument("--ref", type=int, default=60)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--out", default="data/pos_bench.json")
    ap.add_argument("--lo", type=int, default=-700, help="参考分下限：低于此视为已败，不计")
    ap.add_argument("--hi", type=int, default=300, help="参考分上限")
    ap.add_argument("--cap", type=int, default=600, help="单步损失上限，避免饱和")
    args = ap.parse_args()

    poss = build_positions(args.n) if (args.rebuild or not POS.exists()) else \
        json.loads(POS.read_text(encoding="utf-8"))
    ref = json.loads(REF.read_text(encoding="utf-8")) if REF.exists() else {}
    mref = json.loads(MREF.read_text(encoding="utf-8")) if MREF.exists() else {}

    pika = Pika("movetime", 10)
    try:
        # 参考分析只需算一次，缓存复用
        for i, po in enumerate(poss):
            key = str(i)
            if key in ref:
                continue
            b_uci, cp, mate = analyse(pika, po["b"], po["s"], args.ref)
            ref[key] = {"uci": b_uci, "cp": cp, "mate": mate}
            if (i + 1) % 40 == 0:
                print(f"  参考分析 {i+1}/{len(poss)}", flush=True)
                REF.write_text(json.dumps(ref), encoding="utf-8")
        REF.write_text(json.dumps(ref), encoding="utf-8")
        print(f"参考分析完成 {len(ref)} 个", flush=True)

        table = []
        for mode in args.modes.split(","):
            srv = Srv(mode)
            cpls, top1, n_ok = [], 0, 0
            try:
                for i, po in enumerate(poss):
                    r0 = ref[str(i)]
                    if r0.get("cp") is None or r0.get("mate") is not None:
                        continue
                    if not (args.lo <= r0["cp"] <= args.hi):
                        continue
                    r = srv.best(po["b"], po["s"])
                    mv = r.get("mv")
                    lg = [f * 100 + t for (f, t) in B.gen_legal(po["b"], po["s"])]
                    if not mv or mv not in lg:
                        continue
                    after = list(po["b"])
                    B.apply_move(after, (mv // 100, mv % 100))
                    # 走子后的参考分必须落盘缓存：皮卡鱼的搜索带置换表残留，
                    # 同一局面在不同时刻重算会差几十 cp，不缓存则配置间差异被噪声吞掉
                    mkey = f"{i}:{mv_to_uci(mv)}"
                    if mkey in mref:
                        a_cp = mref[mkey]
                    else:
                        _, a_cp, _ = analyse(pika, after, -po["s"], args.ref)
                        mref[mkey] = a_cp
                        if len(mref) % 25 == 0:
                            MREF.write_text(json.dumps(mref), encoding="utf-8")
                    if a_cp is None:
                        continue
                    cpls.append(max(-50, min(args.cap, r0["cp"] + a_cp)))
                    n_ok += 1
                    if r0["uci"] and mv_to_uci(mv) == r0["uci"]:
                        top1 += 1
            finally:
                srv.close()
            cpls.sort()
            row = {"mode": mode, "n": n_ok,
                   "cpl_mean": round(statistics.mean(cpls), 1),
                   "cpl_median": round(statistics.median(cpls), 1),
                   "cpl_p90": round(cpls[int(len(cpls) * 0.9)], 1),
                   "blunder200": round(sum(1 for x in cpls if x > 200) / len(cpls), 3),
                   "top1": round(top1 / max(1, n_ok), 3)}
            table.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        (HERE / args.out).write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        MREF.write_text(json.dumps(mref), encoding="utf-8")
    finally:
        pika.close()


if __name__ == "__main__":
    main()
