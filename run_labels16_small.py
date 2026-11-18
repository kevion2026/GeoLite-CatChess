"""并行生成前 50k 局面的 depth=16 标签（4 分片，避免 CPU 过载）。"""
import subprocess
import sys
import pathlib
import time

HERE = pathlib.Path(__file__).parent
N = 50000
SHARDS = 4
procs = []
t0 = time.time()
for k in range(SHARDS):
    a = N * k // SHARDS
    b = N * (k + 1) // SHARDS
    log = open(HERE / "data" / f"d16s_shard{k}.log", "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "gen_pika_shard.py", "--positions", "data/positions_200k.pkl",
                          "--start", str(a), "--end", str(b), "--depth", "16", "--movetime", "0",
                          "--out", f"data/pika_d16s_shard{k}.pkl", "--checkpoint", "1000"],
                         cwd=str(HERE), stdout=log, stderr=subprocess.STDOUT)
    procs.append((p, log))
print("started", SHARDS, flush=True)
alive = [True] * SHARDS
while any(alive):
    time.sleep(30)
    for i, (p, _) in enumerate(procs):
        if alive[i] and p.poll() is not None:
            alive[i] = False
            print(f"shard {i} exit {p.returncode} at {time.time()-t0:.0f}s", flush=True)
print("all done", f"{time.time()-t0:.0f}s", flush=True)
