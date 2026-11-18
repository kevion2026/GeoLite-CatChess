"""并行启动 7 个标注分片，合并为最终价值标签。"""
import pathlib
import pickle
import subprocess
import sys
import time

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
POS = "data/positions_200k.pkl"
SDIR = HERE / "data" / "pika200k_shards"
OUT = HERE / "data" / "pika_values_200k.pkl"
N = 200000
W = 7
MOVETIME = 50

SDIR.mkdir(parents=True, exist_ok=True)
chunks = []
per = (N + W - 1) // W
for i in range(0, N, per):
    chunks.append((i, min(N, i + per), SDIR / f"shard_{i:06d}.pkl"))

procs = []
for start, end, out in chunks:
    done = 0
    if out.exists():
        try:
            done = len(pickle.load(open(out, "rb")))
        except Exception:
            done = 0
    if done >= end - start:
        print("shard", start, end, "already done", done, flush=True)
        continue
    cmd = [sys.executable, str(HERE / "gen_pika_shard.py"),
           "--positions", POS, "--start", str(start), "--end", str(end),
           "--movetime", str(MOVETIME), "--out", str(out)]
    procs.append((start, end, out, subprocess.Popen(cmd, cwd=str(HERE))))

for start, end, out, p in procs:
    code = p.wait()
    print("shard", start, end, "exit", code, flush=True)

rows = pickle.load(open(HERE / POS, "rb"))
got = {}
for start, end, out in chunks:
    if not out.exists():
        print("MISSING", out, flush=True)
        continue
    for idx, cp in pickle.load(open(out, "rb")):
        got[idx] = cp
print("合并", len(got), "/", N, flush=True)
if len(got) < N:
    # 缺失的用 0 填充并报告，不静默
    for i in range(N):
        got.setdefault(i, 0)
rows2 = [{"board": rows[i][0], "side": rows[i][1], "cp": got[i], "src": rows[i][2]}
         for i in range(N)]
pickle.dump(rows2, open(OUT, "wb"))
print("写入", OUT, len(rows2), flush=True)
