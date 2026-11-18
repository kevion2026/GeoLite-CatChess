"""给残局局面打皮卡鱼标签：先浅搜剔除「绝杀已在眼前」的局面，再深搜定值。

两段式的原因：
  对走采样后仍有约 1/4 局面是 mate-in-N，这类局面静态评估原理上无法拟合，
  留着只会把损失曲线拉成噪声。浅搜（depth 8）识别出来直接丢掉，
  剩下的按 --deep-nodes 深搜给标签，省下大量机时。

分片落盘（data/eg_labels/shard_*.pkl，每 2000 条刷一次），中断可续。
"""
import argparse
import collections
import pathlib
import pickle
import time
from concurrent.futures import ProcessPoolExecutor

from gen_pika_values2 import Engine, fen_of

HERE = pathlib.Path(__file__).resolve().parent
SHARD_DIR = HERE / "data" / "eg_labels"


class SafeEngine:
    def __init__(self):
        self.eng = None
        self.restarts = 0

    def get(self):
        if self.eng is None:
            self.eng = Engine()
        return self.eng

    def drop(self):
        if self.eng is not None:
            try:
                self.eng.close()
            except Exception:
                pass
        self.eng = None
        self.restarts += 1


def worker(args):
    idx, rows, shallow_depth, deep_nodes, tag = args
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SHARD_DIR / ("shard_%02d.pkl" % idx)
    done = []
    if out_path.exists():
        try:
            done = pickle.load(open(out_path, "rb"))
            print("分片 %d 已有 %d 条，续跑" % (idx, len(done)), flush=True)
        except Exception:
            done = []
    start = len(done)
    eng = SafeEngine()
    stats = collections.Counter()
    t0 = time.time()
    buf = list(done)
    try:
        for k in range(start, len(rows)):
            b, s = rows[k]
            rec = {"board": b, "side": s, "cp": None, "drop": ""}
            try:
                cp = eng.get().label(fen_of(b, s), shallow_depth, 0, 0)
                if abs(cp) >= 29000:
                    rec["drop"] = "mate"
                    stats["mate"] += 1
                else:
                    cp = eng.get().label(fen_of(b, s), 0, 0, deep_nodes)
                    rec["cp"] = cp
                    stats["ok"] += 1
            except RuntimeError:
                eng.drop()
                rec["drop"] = "crash"
                stats["crash"] += 1
            buf.append(rec)
            if (k + 1) % 2000 == 0:
                pickle.dump(buf, open(out_path, "wb"))
                el = time.time() - t0
                sp = (k + 1 - start) / max(el, 1e-9)
                print("  片%d %d/%d  %.0fs  %.1f/s  %s"
                      % (idx, k + 1, len(rows), el, sp, dict(stats)), flush=True)
    finally:
        pickle.dump(buf, open(out_path, "wb"))
        try:
            eng.get().close()
        except Exception:
            pass
    print("片%d 完成 %d 条 %s 重启%d次" % (idx, len(buf), dict(stats), eng.restarts),
          flush=True)
    return len(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pos", default="data/endgame_plays.pkl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shallow-depth", type=int, default=8)
    ap.add_argument("--deep-nodes", type=int, default=150000)
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", default="data/pika_values_endgame.pkl")
    args = ap.parse_args()

    rows = pickle.load(open(HERE / args.pos, "rb"))
    if args.limit:
        rows = rows[:args.limit]
    pos = [(r["board"], r["side"]) for r in rows]
    print("待标注 %d 局面  浅深 %d  深节点 %d  进程 %d"
          % (len(pos), args.shallow_depth, args.deep_nodes, args.workers), flush=True)

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    for f in SHARD_DIR.glob("shard_*.pkl"):
        f.unlink()

    n = len(pos)
    per = (n + args.workers - 1) // args.workers
    tasks = []
    for i, lo in enumerate(range(0, n, per)):
        tasks.append((i, pos[lo:lo + per], args.shallow_depth, args.deep_nodes, i))

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(worker, tasks))

    merged = []
    for i in range(len(tasks)):
        p = SHARD_DIR / ("shard_%02d.pkl" % i)
        if p.exists():
            merged.extend(pickle.load(open(p, "rb")))
    # 补上 cfg
    for k, r in enumerate(merged):
        r["cfg"] = rows[k]["cfg"] if k < len(rows) else ""
    ok = [r for r in merged if r["cp"] is not None]
    print("合并 %d 条，可用 %d 条，用时 %.0fs"
          % (len(merged), len(ok), time.time() - t0), flush=True)
    pickle.dump(merged, open(HERE / args.out, "wb"))
    print("写入", args.out, flush=True)


if __name__ == "__main__":
    main()
