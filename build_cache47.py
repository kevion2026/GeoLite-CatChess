"""把 20 万标签局面转成 47 维（45 几何 + 张力/空洞）缓存。"""
import io, json, pickle, time
from pathlib import Path

import numpy as np

from feats45 import feats47

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
LABELS = HERE / "data/pika_values_200k.pkl"
OUT = HERE / "data/value47_cache_200k.npz"


def main():
    rows = pickle.load(open(LABELS, "rb"))
    M = json.load(io.open(HERE / "model_value.json", encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])
    X = np.zeros((len(rows), 47), float)
    y = np.zeros(len(rows), float)
    t0 = time.time()
    for i, r in enumerate(rows):
        X[i] = feats47(r["board"], r["side"], *AC)
        y[i] = float(np.clip(r["cp"], -1500, 1500))
        if (i + 1) % 2000 == 0:
            print(f"feat {i+1}/{len(rows)} {time.time()-t0:.0f}s", flush=True)
    np.savez(OUT, X=X, y=y)
    print("saved", OUT, X.shape, "seconds", round(time.time() - t0, 1), flush=True)


if __name__ == "__main__":
    main()
