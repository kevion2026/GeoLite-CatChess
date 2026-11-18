"""把未完成分片逐个补齐（每个分片用全新进程，避免句柄泄漏），最后合并。"""
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
per = (N + W - 1) // W
chunks = [(i, min(N, i + per), SDIR / f"shard_{i:06d}.pkl") for i in range(0, N, per)]

for start, end, out in chunks:
    size = end - start
    attempts = 0
    while attempts < 12:
        done = 0
        if out.exists():
            try:
                done = len(pickle.load(open(out, "rb")))
            except Exception:
                done = 0
        if done >= size:
            break
        print(f"shard {start}: {done}/{size} attempt {attempts+1}", flush=True)
        cmd = [sys.executable, str(HERE / "gen_pika_shard.py"),
               "--positions", POS, "--start", str(start), "--end", str(end),
               "--movetime", str(MOVETIME), "--out", str(out)]
        p = subprocess.Popen(cmd, cwd=str(HERE))
        code = p.wait()
        print(f"shard {start}: exit {code}", flush=True)
        attempts += 1
        time.sleep(1)

rows = pickle.load(open(HERE / POS, "rb"))
got = {}
missing = 0
for start, end, out in chunks:
    size = end - start
    if not out.exists():
        missing += size
        continue
    data = pickle.load(open(out, "rb"))
    for idx, cp in data:
        got[idx] = cp
    missing += max(0, size - len(data))
print("合并", len(got), "/", N, "missing", missing, flush=True)
if missing:
    print("仍有缺失，停止（不写零标签）", flush=True)
    sys.exit(1)
rows2 = [{"board": rows[i][0], "side": rows[i][1], "cp": got[i], "src": rows[i][2]}
         for i in range(N)]
pickle.dump(rows2, open(OUT, "wb"))
print("写入", OUT, len(rows2), flush=True)
