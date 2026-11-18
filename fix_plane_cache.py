"""重算 20 万中局局面的平面分（修正「通路兵」红黑查反的 bug），写回 heads_200k.npz。

第 46 维输入直接取自平面分，训练侧必须与 C++ 的 evalPosPlane 逐位一致。
"""
import pickle
import time

import numpy as np

from diag_plane import plane_score

rows = pickle.load(open("data/pika_values_200k.pkl", "rb"))
z = np.load("data/heads_200k.npz")
old = z["plane"]
y = z["y"]
geo = z["geo"]
n = len(rows)
pl = np.zeros(n, np.float32)
t0 = time.time()
for i, r in enumerate(rows):
    pl[i] = plane_score(r["board"], r["side"])
    if (i + 1) % 50000 == 0:
        print("  %d/%d %.0fs" % (i + 1, n, time.time() - t0), flush=True)

d = np.abs(pl - old)
print("与旧值差异：均值 %.2f  最大 %.2f  不同的样本 %.1f%%"
      % (d.mean(), d.max(), 100 * np.mean(d > 0.5)))
np.savez("data/heads_200k.npz", plane=pl, y=y, geo=geo)
print("已写回 data/heads_200k.npz")
