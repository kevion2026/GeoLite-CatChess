"""45 维几何特征：39 维 + 6 个九宫/边线威胁量，几何仍为唯一输入。"""

import numpy as np

from trap_mine import feats39

VAL = {1: 1000, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}
HEAVY = (4, 5, 6)
HORSE_MV = [(1, 2, 0, 1), (-1, 2, 0, 1), (1, -2, 0, -1), (-1, -2, 0, -1),
            (2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0)]


def _inb(x, y):
    return 0 <= x < 9 and 0 <= y < 10


def _attacked(board, s, by):
    """与 engine3d.js attacked 逐条同构，避免 z 标准化被 1 格差异放大。"""
    x, y = s % 9, s // 9
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny, step = x + dx, y + dy, 1
        while _inb(nx, ny):
            q = int(board[ny * 9 + nx])
            if q:
                if (q > 0) == (by > 0):
                    t = abs(q)
                    if t == 5 or (t == 1 and step == 1):
                        return True
                break
            nx += dx; ny += dy; step += 1
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny, screens = x + dx, y + dy, 0
        while _inb(nx, ny):
            q = int(board[ny * 9 + nx])
            if q:
                if screens == 1:
                    if (q > 0) == (by > 0) and abs(q) == 6:
                        return True
                    break
                screens += 1
            nx += dx; ny += dy
    for dx, dy, lx, ly in HORSE_MV:
        sx, sy = x - dx, y - dy
        if not _inb(sx, sy):
            continue
        q = int(board[sy * 9 + sx])
        if q and (q > 0) == (by > 0) and abs(q) == 4:
            gx, gy = sx + lx, sy + ly
            if _inb(gx, gy) and int(board[gy * 9 + gx]) == 0:
                return True
    cand = [(x, y + 1), (x - 1, y), (x + 1, y)] if by > 0 else [(x, y - 1), (x - 1, y), (x + 1, y)]
    for cx, cy in cand:
        if not _inb(cx, cy):
            continue
        q = int(board[cy * 9 + cx])
        if q and (q > 0) == (by > 0) and abs(q) == 7:
            return True
    return False


def _king_of(board, side):
    t = 1 * side
    for s in range(90):
        if int(board[s]) == t:
            return s
    return -1


def feats45(board, side, A, B, C):
    f = feats39(board, side, A, B, C)
    k = _king_of(board, side)
    if k < 0:
        return np.concatenate([f, np.zeros(6)])
    kx, ky = k % 9, k // 9
    heavy_near = defenders_near = edge_deep = 0
    mat = 0
    for s in range(90):
        q = int(board[s])
        if not q:
            continue
        x, y = s % 9, s // 9
        own = (q > 0) == (side > 0)
        mat += VAL[abs(q)] * (1 if own else -1)
        if not own and abs(q) in HEAVY and max(abs(x - kx), abs(y - ky)) <= 2:
            heavy_near += 1
        if own and abs(q) in (2, 3, 5) and max(abs(x - kx), abs(y - ky)) <= 2:
            defenders_near += 1
        if not own and x in (0, 8) and (y >= 7 if side > 0 else y <= 2):
            edge_deep += 1
    palace_att = 0
    for yy in range(max(0, ky - 1), min(9, ky + 1) + 1):
        for xx in range(max(0, kx - 1), min(8, kx + 1) + 1):
            if _attacked(board, yy * 9 + xx, -side):
                palace_att += 1
    mob = 0
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = kx + dx, ky + dy
        inPal = 0 <= nx < 9 and 0 <= ny < 10 and (ny >= 7 if side > 0 else ny <= 2)
        if inPal and int(board[ny * 9 + nx]) == 0 and not _attacked(board, ny * 9 + nx, -side):
            mob += 1
    extra = np.array([heavy_near, defenders_near, edge_deep, palace_att, mob, mat / 100.0], float)
    return np.concatenate([f, extra])


# ---------------------------------------------------------------- 空间张力
# 第 46/47 维：火力交汇密度、防守空洞体积。两者都是静态几何量，
# 不依赖历史序列；训练与线上推理必须用同一套实现。

def _attacker_count(board, s, by):
    """攻击 s 格的 by 方棋子数量（只数不重复的棋子，含飞将）。"""
    x, y = s % 9, s // 9
    cnt = 0
    # 直线：车、炮、将帅（飞将）
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny, screen = x + dx, y + dy, 0
        while _inb(nx, ny):
            q = int(board[ny * 9 + nx])
            if q:
                if screen == 0:
                    if (q > 0) == (by > 0):
                        t = abs(q)
                        if t == 5:
                            cnt += 1
                        elif t == 1 and dx == 0:
                            cnt += 1
                    screen = 1
                else:
                    if (q > 0) == (by > 0) and abs(q) == 6:
                        cnt += 1
                    break
            nx += dx; ny += dy
    # 斜线：士、象
    for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        ax, ay = x + dx, y + dy
        if _inb(ax, ay):
            q = int(board[ay * 9 + ax])
            if q and (q > 0) == (by > 0) and abs(q) == 2:
                cnt += 1
        ex, ey = x + 2 * dx, y + 2 * dy
        mx, my = x + dx, y + dy
        if _inb(ex, ey) and _inb(mx, my) and int(board[my * 9 + mx]) == 0:
            q = int(board[ey * 9 + ex])
            if q and (q > 0) == (by > 0) and abs(q) == 3:
                cnt += 1
    # 马：从八个来源格反查，马腿必须为空
    for dx, dy, lx, ly in HORSE_MV:
        ox, oy = x - dx, y - dy
        if not _inb(ox, oy):
            continue
        q = int(board[oy * 9 + ox])
        if not (q and (q > 0) == (by > 0) and abs(q) == 4):
            continue
        gx, gy = ox + lx, oy + ly
        if _inb(gx, gy) and int(board[gy * 9 + gx]) == 0:
            cnt += 1
    # 兵/卒
    if by > 0:
        origins = [(x, y + 1), (x - 1, y), (x + 1, y)]
        want = 7
    else:
        origins = [(x, y - 1), (x - 1, y), (x + 1, y)]
        want = -7
    for ox, oy in origins:
        if _inb(ox, oy) and int(board[oy * 9 + ox]) == want:
            cnt += 1
    return cnt


def tension_feats(board, side):
    """返回 [火力交汇密度, 防守空洞体积]，均为九宫格内的整数计数。"""
    ek = _king_of(board, -side)
    ok = _king_of(board, side)
    if ek < 0 or ok < 0:
        return np.zeros(2)
    ex, ey = ek % 9, ek // 9
    cross = 0
    for yy in range(max(0, ey - 1), min(9, ey + 1) + 1):
        for xx in range(max(0, ex - 1), min(8, ex + 1) + 1):
            if _attacker_count(board, yy * 9 + xx, side) >= 2:
                cross += 1
    ox, oy = ok % 9, ok // 9
    void = 0
    for yy in range(max(0, oy - 1), min(9, oy + 1) + 1):
        for xx in range(max(0, ox - 1), min(8, ox + 1) + 1):
            s = yy * 9 + xx
            if int(board[s]) != 0:
                continue
            if _attacker_count(board, s, -side) > 0 and _attacker_count(board, s, side) == 0:
                void += 1
    return np.array([cross, void], float)


def feats47(board, side, A, B, C):
    return np.concatenate([feats45(board, side, A, B, C), tension_feats(board, side)])
