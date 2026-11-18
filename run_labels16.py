"""并行生成 depth=16 标签（200k 局面，7 分片）。"""
import subprocess
import sys
import pathlib
import time

HERE = pathlib.Path(__file__).parent
N = 200000
SHARDS = 7
procs = []
t0 = time.time()
for k in range(SHARDS):
    a = N * k // SHARDS
    b = N * (k + 1) // SHARDS
    out = f"data/pika_d16_shard{k}.pkl"
    log = open(HERE / f"data" / f"d16_shard{k}.log", "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "gen_pika_shard.py", "--positions", "data/positions_200k.pkl",
                          "--start", str(a), "--end", str(b), "--depth", "16", "--movetime", "0",
                          "--out", out, "--checkpoint", "1000"],
                         cwd=str(HERE), stdout=log, stderr=subprocess.STDOUT)
    procs.append((p, log))
print("started", SHARDS, flush=True)
alive = [True] * SHARDS
while any(alive):
    time.sleep(60)
    for i, (p, _) in enumerate(procs):
        if alive[i] and p.poll() is not None:
            alive[i] = False
            print(f"shard {i} exit {p.returncode} at {time.time()-t0:.0f}s", flush=True)
print("all done", f"{time.time()-t0:.0f}s", flush=True)
