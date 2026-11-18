"""复刻 C++ 的平面评估（LW + 8 几何特征），在 20 万局面上求 MAE，并与几何树比较。"""
import io, json, pickle, re, pathlib, sys, time
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diag_heads as D

LW, WF, LB = D.load_plane()
KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN = 1, 2, 3, 4, 5, 6, 7
HX = (1, 2, 2, 1, -1, -2, -2, -1)
HY = (2, 1, -1, -2, -2, -1, 1, 2)


def plane_score(B, side):
    s = LB
    pawn = [0] * 18          # 0-8 红兵列, 9-17 黑兵列
    ownR, ownP = [], []
    ksq = -1; adv = ele = 0
    for i in range(90):
        p = int(B[i])
        if not p:
            continue
        a = abs(p); x = i % 9; y = i // 9
        nx = x if side > 0 else 8 - x
        ny = y if side > 0 else 9 - y
        own = (p > 0) == (side > 0)
        s += LW[(a - 1) + (0 if own else 7)][ny * 9 + nx]
        if a == PAWN:
            pawn[x if p > 0 else 9 + x] += 1
        if own:
            if a == ROOK: ownR.append(i)
            elif a == PAWN: ownP.append(i)
            elif a == KING: ksq = i
            elif a == ADVISOR: adv += 1
            elif a == ELEPHANT: ele += 1
    if ksq < 0:
        return -15000.0
    kx, ky = ksq % 9, ksq // 9
    f = [0.0] * 8
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cx, cy, seen = kx, ky, 0
        while True:
            cx += dx; cy += dy
            if not (0 <= cx < 9 and 0 <= cy < 10):
                break
            q = int(B[cy * 9 + cx])
            if not q:
                continue
            enemy = (q > 0) != (side > 0)
            a = abs(q)
            if seen == 0:
                if enemy and a == ROOK: f[0] += 1
                seen = 1
            else:
                if enemy and a == CANNON: f[1] += 1
                break
    for k in range(8):
        cx, cy = kx + HX[k], ky + HY[k]
        if not (0 <= cx < 9 and 0 <= cy < 10):
            continue
        q = int(B[cy * 9 + cx])
        if q and (q > 0) != (side > 0) and abs(q) == HORSE:
            f[2] += 1
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cx, cy = kx + dx, ky + dy
        if not (0 <= cx < 9 and 0 <= cy < 10):
            continue
        q = int(B[cy * 9 + cx])
        if q and (q > 0) != (side > 0) and abs(q) == PAWN:
            f[3] += 1
    f[4] = float(adv); f[5] = float(ele)
    for i in ownR:
        x, y, mob = i % 9, i // 9, 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cx, cy = x, y
            while True:
                cx += dx; cy += dy
                if not (0 <= cx < 9 and 0 <= cy < 10):
                    break
                q = int(B[cy * 9 + cx])
                if q:
                    if (q > 0) != (side > 0): mob += 1
                    break
                mob += 1
        f[6] += min(mob, 14)
    for i in ownP:
        x = i % 9; blocked = 0
        for ff in range(max(0, x - 1), min(9, x + 2)):
            # 与 C++ 一致：数的是「对方兵」是否卡在同/邻线（原先红黑查反了）
            blocked += pawn[9 + ff] if B[i] > 0 else pawn[ff]
        if blocked == 0: f[7] += 1
    for k in range(8):
        s += WF[k] * f[k]
    return s


def main():
    rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
    z = np.load(HERE / "data/value45_cache_200k.npz")
    X, y = z["X"], z["y"]
    n = len(y)
    ps = np.zeros(n)
    t0 = time.time()
    for i, r in enumerate(rows):
        ps[i] = plane_score(r["board"], r["side"])
        if (i + 1) % 50000 == 0:
            print("plane %d/%d %.0fs" % (i + 1, n, time.time() - t0), flush=True)
    np.savez(HERE / "data/heads_200k.npz", plane=ps, y=y, geo=D.geo_scores(X, D.load_geo()))
    mae = float(np.mean(np.abs(ps - y)))
    r2 = float(1 - np.sum((ps - y) ** 2) / np.sum((y - y.mean()) ** 2))
    print("plane MAE %.1f R2 %.3f corr %.3f sd %.1f mean %.1f"
          % (mae, r2, np.corrcoef(ps, y)[0, 1], ps.std(), ps.mean()), flush=True)
    A = np.vstack([ps, np.ones_like(ps)]).T
    c = np.linalg.lstsq(A, y, rcond=None)[0]
    print("回归 y ≈ %.3f·plane + %.1f  -> MAE %.1f"
          % (c[0], c[1], np.mean(np.abs(A @ c - y))), flush=True)


if __name__ == "__main__":
    main()
