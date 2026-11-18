"""构建 10×9×14 棋子平面缓存（side-to-move 视角，红方在下）。
通道 0..6 = 己方 帅仕相马车炮兵，7..13 = 敌方同序。
"""
import pickle, time
from pathlib import Path
import numpy as np

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
LABELS = HERE / "data/pika_values_200k.pkl"
OUT = HERE / "data/planes_200k.npy"


def planes(board, side):
    a = np.zeros((14, 10, 9), np.uint8)
    for y in range(10):
        for x in range(9):
            p = int(board[y * 9 + x])
            if not p:
                continue
            if side < 0:
                p = -p
                ny, nx = 9 - y, 8 - x
            else:
                ny, nx = y, x
            ch = (abs(p) - 1) + (0 if p > 0 else 7)
            a[ch, ny, nx] = 1
    return a


def main():
    rows = pickle.load(open(LABELS, "rb"))
    out = np.zeros((len(rows), 14 * 10 * 9), np.uint8)
    t0 = time.time()
    for i, r in enumerate(rows):
        out[i] = planes(r["board"], r["side"]).reshape(-1)
        if (i + 1) % 5000 == 0:
            print(f"planes {i+1}/{len(rows)} {time.time()-t0:.0f}s", flush=True)
    np.save(OUT, out)
    print("saved", OUT, out.shape, out.dtype, round(time.time() - t0, 1), flush=True)


if __name__ == "__main__":
    main()
