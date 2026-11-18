"""生成残局局面池：按实用残局子力配置随机合法摆子。

为什么需要这一步：
  现有 20 万局面池里，双方总子力 <1600（约等于「残局」）的样本只有 56 个，
  PGN 池 8.9 万局面里 <1600 只有 34 个。价值头在残局上是纯外推，MAE 无法测量。
  所以只能按残局子力表主动合成，再用皮卡鱼打标签。

子力配置写成 (车,炮,马,象,士,兵)，红黑各一份，weight 控制采样比例。
摆子规则：将士象只能落在各自合法点，兵只能落在合法 rank，其余子任意空点；
过滤将帅照面、非行棋方被将、行棋方无着三种非法局面。

输出 data/endgame_raw.pkl：[{"board": [...], "side": 1/-1, "cfg": "..."}]
"""
import argparse
import collections
import pathlib
import pickle
import random

import board as B

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "data" / "endgame_raw.pkl"

# ---------------------------------------------------------------- 摆子点表
def _tables():
    pal, adv, ele = {}, {}, {}
    RED_ELE = [(2, 9), (6, 9), (0, 7), (4, 7), (8, 7), (2, 5), (6, 5)]
    BLK_ELE = [(2, 0), (6, 0), (0, 2), (4, 2), (8, 2), (2, 4), (6, 4)]
    for side in (1, -1):
        y0, y1, y2 = (7, 8, 9) if side > 0 else (0, 1, 2)
        pal[side] = sorted({B.sq(x, y) for y in (y0, y1, y2) for x in (3, 4, 5)})
        adv[side] = sorted({B.sq(3, y0), B.sq(5, y0), B.sq(4, y1), B.sq(3, y2), B.sq(5, y2)})
        ele[side] = sorted({B.sq(x, y) for x, y in (RED_ELE if side > 0 else BLK_ELE)})
    return pal, adv, ele


PAL, ADV, ELE = _tables()
assert len(PAL[1]) == 9 and len(ADV[1]) == 5 and len(ELE[1]) == 7
assert len(PAL[-1]) == 9 and len(ADV[-1]) == 5 and len(ELE[-1]) == 7

PAWN_SQ = {
    # 未过河的兵只能在原列（x 为偶数）；过河后才可以横走，任意列
    1: [B.sq(x, y) for y in range(0, 7) for x in range(9)
        if y <= 4 or x % 2 == 0],
    -1: [B.sq(x, y) for y in range(3, 10) for x in range(9)
         if y >= 5 or x % 2 == 0],
}
ANY_SQ = list(range(90))

# ---------------------------------------------------------------- 实用残局子力表
# (车,炮,马,象,士,兵)
R = (1, 0, 0, 0, 0, 0)
RR = (2, 0, 0, 0, 0, 0)
C = (0, 1, 0, 0, 0, 0)
CC = (0, 2, 0, 0, 0, 0)
N = (0, 0, 1, 0, 0, 0)
NN = (0, 0, 2, 0, 0, 0)
P = (0, 0, 0, 0, 0, 1)
PP = (0, 0, 0, 0, 0, 2)
PPP = (0, 0, 0, 0, 0, 3)
RP = (1, 0, 0, 0, 0, 1)
RPP = (1, 0, 0, 0, 0, 2)
CP = (0, 1, 0, 0, 0, 1)
CPP = (0, 1, 0, 0, 0, 2)
NP = (0, 0, 1, 0, 0, 1)
NPP = (0, 0, 1, 0, 0, 2)
RC = (1, 1, 0, 0, 0, 0)
RN = (1, 0, 1, 0, 0, 0)
CN = (0, 1, 1, 0, 0, 0)
RCP = (1, 1, 0, 0, 0, 1)
RNP = (1, 0, 1, 0, 0, 1)
BARE = (0, 0, 0, 0, 0, 0)
A1 = (0, 0, 0, 0, 1, 0)
A2 = (0, 0, 0, 0, 2, 0)
B1 = (0, 0, 0, 1, 0, 0)
B2 = (0, 0, 0, 2, 0, 0)
A1B1 = (0, 0, 0, 1, 1, 0)
A1B2 = (0, 0, 0, 2, 1, 0)
A2B1 = (0, 0, 0, 1, 2, 0)
A2B2 = (0, 0, 0, 2, 2, 0)
RA2B2 = (1, 0, 0, 2, 2, 0)
RA1B2 = (1, 0, 0, 2, 1, 0)
CA2B2 = (0, 1, 0, 2, 2, 0)
NA2B2 = (0, 0, 1, 2, 2, 0)

# (红方子力, 黑方子力, 权重)
CONFIGS = [
    # —— 单车/双车 攻 各类防守 ——
    (R, BARE, 8), (R, B1, 8), (R, A1, 7), (R, A2, 7), (R, B2, 7),
    (R, A1B1, 8), (R, A1B2, 8), (R, A2B1, 8), (R, A2B2, 10),
    (RR, A2B2, 6), (RR, A2B1, 4),
    # —— 车兵 / 车马 / 车炮 攻 ——
    (RP, A2B2, 9), (RP, A2B1, 6), (RP, A1B1, 5), (RPP, A2B2, 4),
    (RN, A2B2, 6), (RN, A2B1, 4), (RC, A2B2, 6), (RC, A2B1, 4),
    (RCP, A2B2, 4), (RNP, A2B2, 4),
    # —— 马 / 炮 攻 ——
    (N, BARE, 5), (N, B1, 5), (N, A1, 5), (N, A2B2, 7),
    (NN, A2B2, 5), (NP, A2B2, 8), (NPP, A2B2, 4),
    (C, BARE, 5), (C, B1, 5), (C, A2, 6), (C, A2B2, 8),
    (CC, A2B2, 5), (CP, A2B2, 8), (CPP, A2B2, 4), (CN, A2B2, 4),
    # —— 兵卒残局 ——
    (P, BARE, 5), (P, A1, 5), (PP, A2, 5), (PP, B2, 4), (PPP, A2B2, 4),
    (P, P, 5), (PP, P, 4), (PP, PP, 3), (PPP, PP, 3), (P, A1B1, 3),
    (P, B1, 4), (PP, A1, 4),
    # —— 双方都有攻子（实战最常见） ——
    (R, R, 12), (R, C, 8), (R, N, 8), (R, CA2B2, 6), (R, NA2B2, 6),
    (R, RA2B2, 8), (RP, R, 8), (RP, RA2B2, 6), (RN, R, 6), (RC, R, 6),
    (RC, C, 4), (RN, C, 4), (C, C, 6), (C, N, 5), (N, N, 5),
    (CN, C, 3), (CP, C, 4), (RA2B2, RA2B2, 8), (RA1B2, RA2B2, 5),
    (RCP, RA2B2, 3),
    # —— 略偏中局的全子力残局（少士象/少一兵） ——
    ((2, 2, 2, 2, 2, 4), (2, 2, 2, 2, 2, 5), 4),
    ((2, 2, 2, 2, 1, 5), (2, 2, 2, 2, 2, 5), 4),
    ((2, 2, 2, 1, 2, 3), (2, 2, 2, 2, 2, 5), 4),
    ((2, 2, 2, 2, 2, 3), (2, 2, 2, 2, 2, 5), 4),
    ((2, 1, 2, 2, 2, 5), (2, 2, 2, 2, 2, 5), 3),
    ((1, 2, 2, 2, 2, 4), (2, 2, 2, 2, 2, 5), 3),
]


def place(b, side, mat, rng):
    """把 side 方子力 mat 摆到 b 的空点上，失败返回 False。"""
    nR, nC, nN, nB, nA, nP = mat
    pal = [s for s in PAL[side] if b[s] == 0]
    if not pal:
        return False
    b[rng.choice(pal)] = B.KING * side
    for n, pool, t in ((nA, ADV[side], B.ADVISOR), (nB, ELE[side], B.ELEPHANT)):
        avail = [s for s in pool if b[s] == 0]
        if n > len(avail):
            return False
        for s in rng.sample(avail, n):
            b[s] = t * side
    free = [s for s in ANY_SQ if b[s] == 0]
    rng.shuffle(free)
    i = 0
    for n, t in ((nR, B.ROOK), (nC, B.CANNON), (nN, B.HORSE)):
        for _ in range(n):
            b[free[i]] = t * side
            i += 1
    freeP = [s for s in PAWN_SQ[side] if b[s] == 0]
    rng.shuffle(freeP)
    if nP > len(freeP):
        return False
    for s in freeP[:nP]:
        b[s] = B.PAWN * side
    return True


LEGAL_SET = {
    B.ADVISOR: {1: set(ADV[1]), -1: set(ADV[-1])},
    B.ELEPHANT: {1: set(ELE[1]), -1: set(ELE[-1])},
    B.PAWN: {1: set(PAWN_SQ[1]), -1: set(PAWN_SQ[-1])},
}
MAXCNT = {B.KING: 1, B.ADVISOR: 2, B.ELEPHANT: 2, B.HORSE: 2, B.ROOK: 2,
          B.CANNON: 2, B.PAWN: 5}


def legal_ok(b):
    """按皮卡鱼 position 校验的规则自查：子数上限 + 将士象兵的合法落点。"""
    cnt = {1: collections.Counter(), -1: collections.Counter()}
    for s, p in enumerate(b):
        if not p:
            continue
        side = 1 if p > 0 else -1
        t = abs(p)
        cnt[side][t] += 1
        if t in LEGAL_SET and s not in LEGAL_SET[t][side]:
            return False
    for side in (1, -1):
        for t, cap in MAXCNT.items():
            if cnt[side][t] > cap:
                return False
        if cnt[side][B.KING] != 1:
            return False
    return True


def make(rng, mr, mb):
    b = [0] * 90
    if not place(b, 1, mr, rng):
        return None
    if not place(b, -1, mb, rng):
        return None
    if not legal_ok(b):
        return None
    if B.generals_facing(b):
        return None
    side = 1 if rng.random() < 0.5 else -1
    if B.in_check(b, -side):          # 非行棋方被将：非法局面
        return None
    if not B.gen_legal(b, side):      # 行棋方无着：已终局
        return None
    return b, side


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=160000)
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    cum, acc = [], 0
    for c in CONFIGS:
        acc += c[2]
        cum.append(acc)

    rows, seen = [], set()
    tries = 0
    tgt = args.n
    while len(rows) < tgt and tries < tgt * 80:
        tries += 1
        r = rng.random() * acc
        i = 0
        while cum[i] < r:
            i += 1
        mr, mb = CONFIGS[i][0], CONFIGS[i][1]
        if rng.random() < 0.5:        # 红黑互换，保证优势方向均衡
            mr, mb = mb, mr
        got = make(rng, mr, mb)
        if not got:
            continue
        b, side = got
        key = (tuple(b), side)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"board": b, "side": side,
                     "cfg": "%s|%s" % ("".join(map(str, mr)), "".join(map(str, mb)))})
        if len(rows) % 20000 == 0:
            print("  %d/%d  tries %d" % (len(rows), tgt, tries), flush=True)

    print("生成", len(rows), "局面，尝试", tries, flush=True)
    pickle.dump(rows, open(args.out, "wb"))

    V = {1: 0, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}
    bands = collections.Counter()
    for r in rows:
        m = sum(V[abs(p)] for p in r["board"] if p)
        if m < 400:
            bands["<400"] += 1
        elif m < 800:
            bands["400-800"] += 1
        elif m < 1400:
            bands["800-1400"] += 1
        elif m < 2200:
            bands["1400-2200"] += 1
        elif m < 3200:
            bands["2200-3200"] += 1
        else:
            bands["3200+"] += 1
    print("子力分布", dict(bands), flush=True)
    print("配置数", len(set(r["cfg"] for r in rows)), flush=True)
    print("写入", args.out, flush=True)


if __name__ == "__main__":
    main()
