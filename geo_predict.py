"""GeometricPredictor —— 纯几何「历史节点拼接」多步预测模块（纯 Python，无 numpy）。

设计要点（与原引擎共用同一套几何定义）：

1. 45 维特征 = 21 维三空间点云状态 + 9 维形特征 + 9 维子力 + 6 维威胁量，
   与 `engine3d.js::geometry()/shapeOf()/matFeats()/threatFeats()` 逐位同构，
   可用 `verify_feats.py` 与 node 端对拍。
2. 检索用 KD-Tree（在「姿态 12 维 + 子力 1 维」的低维投影上建树），
   命中后回到 45 维全空间重排。高维精确 KD 在纯 Python 里会退化成暴力扫描，
   两段式是这里唯一能压到毫秒级的做法。
3. 拼接冲突检测用三个几何量：主轴夹角（|cos| 下限）、残差量级比（对数比）、
   质心距离。三者都只依赖已算好的 45 维向量，不额外算算力。
4. 经验库的价值完全取决于「喂什么棋谱」：本模块默认从
   `data/result_positions.pkl`（名局局面 + 胜负）构建，而不是本项目自己的败局，
   否则检索出来的全是「必败走法」。

典型用法见文件末尾 `__main__`。

⚠️ 实测结论（务必先读）
----------------------
在 `data/result_positions.pkl` 的 12000 个名局局面上，本模块与皮卡鱼首选着的
一致率是 **0/25（sigma 取 0.45 和 0.90 都一样）**，而现有几何树在同一批局面上
是 16.2%。也就是说：**它能跑、能给出连续支持度，但支持度与走子质量不相关**。
三个原因，按影响排序：

1. **样本密度不够**。45 维标准化空间里，12000 个节点的最近邻距离约 1.6，
   而随机两点距离约 2.0——最近邻几乎不比随机近，检索退化成「全局平均」。
2. **标签太粗**。经验库的标签是整盘棋的胜负，而同一个局面既可能赢也可能输，
   局面级信噪比极低；用「胜负」当走子质量的监督信号，方差远大于信号。
3. **覆盖偏斜**。`result_import.py` 的采样步长恒为偶数，86% 的局面是红方走子。

要让这条路线真正有用，得先换标签（用引擎逐局面评分而不是棋局胜负）、
把库扩到 10 万级以上、并修掉采样奇偶偏斜。架构骨架已经就位，换数据即可复用。
"""

import argparse
import bisect
import glob
import json
import math
import os
import pickle
import random
import time
from array import array

RED, BLACK = 1, -1
W, H = 9, 10

VALUE = {1: 1000, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180}
ROLE_W = {1: 1.40, 2: 0.80, 3: 0.85, 4: 1.00, 5: 1.25, 6: 1.10, 7: 0.95}
MAT_V = {2: 100, 3: 100, 4: 200, 5: 450, 6: 230, 7: 40}
KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN = 1, 2, 3, 4, 5, 6, 7
ORTHO = ((1, 0), (-1, 0), (0, 1), (0, -1))
HORSE_MV = ((1, 2, 0, 1), (-1, 2, 0, 1), (1, -2, 0, -1), (-1, -2, 0, -1),
            (2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0))

# 索引维度：最初只想用 13 维（三空间质心+残差+子力）做「两段式」检索，
# 实测这条路线是错的——姿态相同但子力差很远的节点会占满候选池，
# 即使池放大到 512，真正的近邻依然 0/8 命中。改为在全部 45 维上、
# 用与排序完全一致的分块权重建树：索引距离即全距离的下界，剪枝成立，
# 预算 2000 时精确命中 8/8（约 5.9ms），预算 600 时 1.98ms 但只命中 1/8。
POSE_DIMS = tuple(range(45))

# 语义块：(起, 止, 权重)。直接算 45 维欧氏距离会被「维度多的块」绑架，
# 所以每块先按自身维度取均值，再加权求和，使各块贡献可比。
BLOCKS = ((0, 21, 1.0), (21, 30, 0.30), (30, 39, 0.80), (39, 45, 0.30))


# 逐维权重：块权重摊到块内每一维。索引与排序共用同一套权重，
# 索引只取部分维时，其距离是全距离的**下界**，KD 剪枝才成立。
DIM_W = tuple(
    next((w / (hi - lo) for lo, hi, w in BLOCKS if lo <= i < hi), 0.0)
    for i in range(45)
)


def block_dist2(a, b):
    """分块加权平方距离（标准化空间）。"""
    t = 0.0
    for lo, hi, w in BLOCKS:
        acc = 0.0
        for i in range(lo, hi):
            d = a[i] - b[i]
            acc += d * d
        t += w * acc / (hi - lo)
    return t


def _inb(x, y):
    return 0 <= x < W and 0 <= y < H


def _sgn(v):
    return 1 if v > 0 else (-1 if v < 0 else 0)


# ---------------------------------------------------------------- 45 维特征
class Featurizer:
    """把 10×9 棋盘映射成 45 维几何向量，并给出可做夹角/残差比较的「姿态」。"""

    def __init__(self, model_path="model_triple.json"):
        with open(model_path, encoding="utf-8") as f:
            m = json.load(f)
        self.tabs = (m["coords3a"], m["coords3b"], m["coords3c"])
        md = m["tree"]["model"]
        self.mean = list(md["mean"])
        self.std = [s if s else 1.0 for s in md["std"]]

    # -- token：阵营-兵种-坐标。黑白视角翻转，使特征与颜色无关
    def _tokens(self, b, side):
        out = []
        for s in range(90):
            p = b[s]
            if p == 0:
                continue
            x, y = s % W, s // W
            bx = (W - 1 - x) if side == BLACK else x
            by = (9 - y) if side == BLACK else y
            role = "S" if _sgn(p) == side else "O"
            t = abs(p)
            w = ROLE_W[t]
            if (y <= 4) if _sgn(p) == RED else (y >= 5):   # 过河兵加权
                w *= 1.15
            out.append((role + str(t) + "@" + str(bx) + str(by), w, t, s))
        return out

    # -- 加权协方差的最大主轴：解析特征分解（Smith 三角解法），与 JS 端同算法
    @staticmethod
    def _fit_line3(pts):
        sw = 0.0
        s0 = s1 = s2 = 0.0
        for w, c in pts:
            sw += w
            s0 += w * c[0]
            s1 += w * c[1]
            s2 += w * c[2]
        if sw <= 0:
            return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 0.0
        c = (s0 / sw, s1 / sw, s2 / sw)
        a11 = a22 = a33 = a12 = a13 = a23 = 0.0
        for w, p in pts:
            d0, d1, d2 = p[0] - c[0], p[1] - c[1], p[2] - c[2]
            a11 += w * d0 * d0; a22 += w * d1 * d1; a33 += w * d2 * d2
            a12 += w * d0 * d1; a13 += w * d0 * d2; a23 += w * d1 * d2
        a11 /= sw; a22 /= sw; a33 /= sw; a12 /= sw; a13 /= sw; a23 /= sw

        p1 = a12 * a12 + a13 * a13 + a23 * a23
        if p1 < 1e-18:
            v = (1.0, 0.0, 0.0) if (a11 >= a22 and a11 >= a33) else ((0.0, 1.0, 0.0) if a22 >= a33 else (0.0, 0.0, 1.0))
        else:
            q = (a11 + a22 + a33) / 3.0
            p2 = (a11 - q) ** 2 + (a22 - q) ** 2 + (a33 - q) ** 2 + 2 * p1
            p = math.sqrt(p2 / 6.0)
            b11, b22, b33 = (a11 - q) / p, (a22 - q) / p, (a33 - q) / p
            b12, b13, b23 = a12 / p, a13 / p, a23 / p
            det = (b11 * (b22 * b33 - b23 * b23) - b12 * (b12 * b33 - b23 * b13)
                   + b13 * (b12 * b23 - b22 * b13))
            r = max(-1.0, min(1.0, det / 2.0))
            e1 = q + 2.0 * p * math.cos(math.acos(r) / 3.0)
            x1, x2, x3 = a11 - e1, a22 - e1, a33 - e1
            cands = (
                (a12 * a23 - a13 * x2, a13 * a12 - x1 * a23, x1 * x2 - a12 * a12),
                (a12 * x3 - a13 * a23, a13 * a13 - x1 * x3, x1 * a23 - a12 * a13),
                (x2 * x3 - a23 * a23, a23 * a13 - a12 * x3, a12 * a23 - x2 * a13),
            )
            best, bn = cands[0], sum(t * t for t in cands[0])
            for cd in cands[1:]:
                n2 = sum(t * t for t in cd)
                if n2 > bn:
                    best, bn = cd, n2
            if bn < 1e-20:
                v = (0.5774, 0.5774, 0.5774)
            else:
                n = math.sqrt(bn)
                v = (best[0] / n, best[1] / n, best[2] / n)
        # 符号规范化：最大分量取正，保证同一局面两端得到同一向量
        idx = max(range(3), key=lambda i: abs(v[i]))
        if v[idx] < 0:
            v = (-v[0], -v[1], -v[2])
        lam = (a11 * v[0] * v[0] + a22 * v[1] * v[1] + a33 * v[2] * v[2]
               + 2 * (a12 * v[0] * v[1] + a13 * v[0] * v[2] + a23 * v[1] * v[2]))
        return c, v, lam

    def _state3(self, pts):
        c, v, _ = self._fit_line3(pts)
        sw = 0.0
        res = 0.0
        for w, p in pts:
            sw += w
            d0, d1, d2 = p[0] - c[0], p[1] - c[1], p[2] - c[2]
            proj = d0 * v[0] + d1 * v[1] + d2 * v[2]
            perp2 = max(d0 * d0 + d1 * d1 + d2 * d2 - proj * proj, 0.0)
            res += w * perp2
        rho = math.sqrt(res / max(sw, 1e-9))
        return (c[0], c[1], c[2], v[0], v[1], v[2], rho)

    @staticmethod
    def _shape(state, pts):
        c0, c1, c2, v0, v1, v2 = state[0], state[1], state[2], state[3], state[4], state[5]
        sw = 0.0
        dens = 0.0
        pmax, pmin = -1e18, 1e18
        for w, p in pts:
            sw += w
            d0, d1, d2 = p[0] - c0, p[1] - c1, p[2] - c2
            d2s = d0 * d0 + d1 * d1 + d2 * d2
            dens += w * math.exp(-d2s / 1.6)
            pr = d0 * v0 + d1 * v1 + d2 * v2
            if pr > pmax:
                pmax = pr
            if pr < pmin:
                pmin = pr
        span = (pmax - pmin) if pts else 0.0
        slope = min(5.0, math.hypot(v0, v1) / max(abs(v2), 1e-6))
        return (dens / max(sw, 1e-9), span, slope)

    @staticmethod
    def _mat_feats(b, side):
        own = [0] * 9
        opp = [0] * 9
        for s in range(90):
            p = b[s]
            if not p:
                continue
            t = abs(p)
            k = 7 if t == PAWN else t
            crossed = (s // W <= 4) if _sgn(p) == RED else (s // W >= 5)
            if _sgn(p) == side:
                own[k] += 1
                if t == PAWN and crossed:
                    own[0] += 1
            else:
                opp[k] += 1
                if t == PAWN and crossed:
                    opp[0] += 1
        mv = sum(MAT_V[k] * own[k] for k in range(2, 8))
        mo = sum(MAT_V[k] * opp[k] for k in range(2, 8))
        out = [(mv - mo) / 100.0]
        out.extend(own[k] - opp[k] for k in range(1, 8))
        out.append(own[0] - opp[0])
        return out

    @staticmethod
    def _attacked(b, s, by):
        """与 engine3d.js::attacked 逐条同构（只含车/将贴脸/炮/马/兵）。"""
        x, y = s % W, s // W
        for dx, dy in ORTHO:
            nx, ny, step = x + dx, y + dy, 1
            while _inb(nx, ny):
                q = b[ny * W + nx]
                if q:
                    if _sgn(q) == by:
                        t = abs(q)
                        if t == ROOK or (t == KING and step == 1):
                            return True
                    break
                nx += dx; ny += dy; step += 1
        for dx, dy in ORTHO:
            nx, ny, screens = x + dx, y + dy, 0
            while _inb(nx, ny):
                q = b[ny * W + nx]
                if q:
                    if screens == 1:
                        if _sgn(q) == by and abs(q) == CANNON:
                            return True
                        break
                    screens += 1
                nx += dx; ny += dy
        for dx, dy, lx, ly in HORSE_MV:
            sx, sy = x - dx, y - dy
            if not _inb(sx, sy):
                continue
            q = b[sy * W + sx]
            if q and _sgn(q) == by and abs(q) == HORSE:
                gx, gy = sx + lx, sy + ly
                if _inb(gx, gy) and b[gy * W + gx] == 0:
                    return True
        cand = ((x, y + 1), (x - 1, y), (x + 1, y)) if by == RED else ((x, y - 1), (x - 1, y), (x + 1, y))
        for cx, cy in cand:
            if not _inb(cx, cy):
                continue
            q = b[cy * W + cx]
            if q and _sgn(q) == by and abs(q) == PAWN:
                return True
        return False

    def _threat_feats(self, b, side):
        k = -1
        for s in range(90):
            if b[s] and abs(b[s]) == KING and _sgn(b[s]) == side:
                k = s
                break
        if k < 0:
            return [0, 0, 0, 0, 0, 0]
        kx, ky = k % W, k // W
        heavy = dfd = edge = mat = pal = mob = 0
        for s in range(90):
            q = b[s]
            if not q:
                continue
            x, y = s % W, s // W
            t = abs(q)
            own = _sgn(q) == side
            mat += (1 if own else -1) * VALUE.get(t, 0)
            dx, dy = abs(x - kx), abs(y - ky)
            if (not own) and t in (HORSE, ROOK, CANNON) and max(dx, dy) <= 2:
                heavy += 1
            if own and t in (ADVISOR, ELEPHANT, ROOK) and max(dx, dy) <= 2:
                dfd += 1
            if (not own) and (x == 0 or x == 8) and ((y >= 7) if side == RED else (y <= 2)):
                edge += 1
        for yy in range(max(0, ky - 1), min(9, ky + 1) + 1):
            for xx in range(max(0, kx - 1), min(8, kx + 1) + 1):
                if self._attacked(b, yy * W + xx, -side):
                    pal += 1
        for dx, dy in ORTHO:
            nx, ny = kx + dx, ky + dy
            in_pal = _inb(nx, ny) and ((ny >= 7) if side == RED else (ny <= 2))
            if in_pal and b[ny * W + nx] == 0 and not self._attacked(b, ny * W + nx, -side):
                mob += 1
        return [heavy, dfd, edge, pal, mob, mat / 100.0]

    # -- 对外：一局局面 → (45 维向量, 姿态)
    # 排列顺序必须与 engine3d.js 一致：21 维三空间状态整体在前，
    # 然后才是三空间各 3 维形特征、9 维子力、6 维威胁量（不是每空间 7+3 交错）。
    def describe(self, b, side):
        toks = self._tokens(b, side)
        states = []
        shape = []
        for tab in self.tabs:
            pts = []
            for key, w, _t, _s in toks:
                c = tab.get(key)
                if c is not None:
                    pts.append((w, c))
            if not pts:
                states.extend((0.0,) * 7)
                shape.extend((0.0, 0.0, 0.0))
                continue
            st = self._state3(pts)
            states.extend(st)
            shape.extend(self._shape(st, pts))
        feats = list(states) + list(shape)
        feats.extend(self._mat_feats(b, side))
        feats.extend(self._threat_feats(b, side))
        poses = []
        for k in (0, 7, 14):
            poses.append(((states[k], states[k + 1], states[k + 2]),
                          (states[k + 3], states[k + 4], states[k + 5]), states[k + 6]))
        return feats, poses

    def feats45(self, b, side):
        return self.describe(b, side)[0]

    def standardize(self, feats):
        return [(v - m) / s for v, m, s in zip(feats, self.mean, self.std)]


# ---------------------------------------------------------------- 局面哈希
def board_hash(board, side):
    """局面指纹（含走子方）。用于「精确局面查表」——同一局面在名局里出现过，
    就直接取那几手的统计，这比在 45 维空间里找近邻精确得多。"""
    h = 1469598103934665603
    # 掩到 63 位：array('q') 是有符号 64 位，超过 2^63-1 会溢出
    for p in board:
        h = ((h ^ (p + 7)) * 1099511628211) & 0x7FFFFFFFFFFFFFFF
    return (h ^ (side + 7)) & 0x7FFFFFFFFFFFFFFF


# ---------------------------------------------------------------- 子力桶
def material_key(board, side, feats):
    """检索前的粗过滤桶：子力差档位 + 总子力档位 + 结构粗坐标。

    直接按「各兵种数量」做键会分出上千个桶、每桶只剩几个点（实测 3046 局面
    分 584 桶），检索等于没有邻居。这里退到三档粗粒度，使每桶落在几百到几千点，
    桶内再做 45 维距离才有意义。
    """
    val = {2: 150, 3: 150, 4: 300, 5: 500, 6: 300, 7: 100}
    bal = tot = 0
    for p in board:
        if not p:
            continue
        v = val.get(abs(p), 0)
        tot += v
        bal += v if (p > 0) == (side > 0) else -v
    return (int(bal // 100), int(tot // 600), int(feats[0] * 2))


def canon_move(mv, side):
    """着法换算到「走子方视角」：红方原样，黑方做上下+左右翻转。

    特征本身是视角无关的，着法也必须同样处理，否则红黑两方的同一结构
    无法互相参考。
    """
    f, t = mv
    if side == RED:
        return int(f) * 100 + int(t)

    def flip(p):
        x, y = p % 9, p // 9
        return (9 - y) * 9 + (8 - x)

    return flip(f) * 100 + flip(t)


# ---------------------------------------------------------------- 空间索引
class KDTree:
    """极简 KD-Tree（纯 Python）。

    维度选在建树时给定的低维投影上（默认 13 维：三空间质心 + 残差 + 子力）。
    45 维直接建树在纯 Python 里几乎不剪枝，等价于暴力扫描；两段式
    「低维出候选池 → 45 维全量重排」才是能用的做法。
    """

    __slots__ = ("idx", "dim", "left", "right", "axis")

    def __init__(self, idx, dim, left, right, axis):
        self.idx, self.dim, self.left, self.right, self.axis = idx, dim, left, right, axis

    @staticmethod
    def build(points, ids, dims, leaf=24, depth=0):
        if not ids:
            return None
        if len(ids) <= leaf or depth > 24:
            return KDTree(ids, dims, None, None, -1)
        # 选跨度最大的维度切分
        best_ax, best_var = dims[0], -1.0
        for d in dims:
            lo = hi = points[ids[0]][d]
            for i in ids:
                v = points[i][d]
                if v < lo:
                    lo = v
                elif v > hi:
                    hi = v
            if hi - lo > best_var:
                best_var, best_ax = hi - lo, d
        ids = sorted(ids, key=lambda i: points[i][best_ax])
        mid = len(ids) // 2
        # 枢轴点必须留在某一侧子树里：早先写成 ids[mid+1:] 会把每个内部节点的
        # 枢轴永久排除，导致近一半的点在树里不可达，检索退回到错误子集。
        return KDTree(ids[mid], dims,
                      KDTree.build(points, ids[:mid], dims, leaf, depth + 1),
                      KDTree.build(points, ids[mid:], dims, leaf, depth + 1),
                      best_ax)

    def query(self, q, points, k=64, budget=600, dim_w=None):
        """返回 (id, 投影距离平方) 候选池，按距离升序。

        纯 Python 在 13 维上做精确 KD 查询会退化（剪枝率低、单次 8ms 不可用），
        所以这里给「叶子距离计算次数」设预算，超出即停——标准的近似最近邻取舍。
        budget 越大越准、越慢；600 次约 1.5ms。
        """
        heap = []
        evals = [0]

        def walk(node):
            if node is None or evals[0] > budget:
                return
            if node.axis < 0:
                for i in node.idx:
                    p = points[i]
                    d2 = 0.0
                    for d in node.dim:
                        t = q[d] - p[d]
                        d2 += t * t * (dim_w[d] if dim_w else 1.0)
                    evals[0] += 1
                    if len(heap) < k:
                        heap.append((d2, i))
                        if len(heap) == k:
                            heap.sort()
                    elif d2 < heap[-1][0]:
                        bisect.insort(heap, (d2, i))
                        heap.pop()
                return
            p = points[node.idx]
            t = q[node.axis] - p[node.axis]
            near, far = (node.left, node.right) if t < 0 else (node.right, node.left)
            walk(near)
            # 剪枝必须用与叶子同口径的加权下界；用未加权的 t² 会与加权堆值不可比
            # （权重只有 1/21 量级），几乎每次都会误判「可剪」，只走近侧一条路。
            if len(heap) < k or t * t * (dim_w[node.axis] if dim_w else 1.0) < heap[-1][0]:
                walk(far)

        walk(self)
        heap.sort()
        return heap


# ---------------------------------------------------------------- 经验库
DEFAULT_EXP = "data/exp_lib.pkl"


class GeometricPredictor:
    """基于历史节点拼接的多步预测器。

    参数
    ----
    model_path : 45 维特征的标准化参数与三套坐标表
    exp_path   : 经验库（pickle），含 feats/result/side 三个数组
    sigma      : RBF 支持度核宽（标准化空间距离），越大越平滑
    cos_min    : 拼接允许的最小主轴夹角余弦（|cos| ≥ cos_min 才认为姿态相容）
    rho_ratio  : 残差量级允许的最大对数比（ln(ρ₁/ρ₂) 的绝对值）
    pool       : KD-Tree 候选池大小
    """

    def __init__(self, model_path="model_triple.json", exp_path=DEFAULT_EXP,
                 sigma=0.90, cos_min=0.9, rho_ratio=0.35, pool=64, centroid_max=1.2, budget=2000, strict=False, pose_dims=POSE_DIMS):
        self.fz = Featurizer(model_path)
        self.sigma = sigma
        self.cos_min = cos_min
        self.rho_ratio = rho_ratio
        self.pool = pool
        self.pose_dims = tuple(pose_dims)
        self.centroid_max = centroid_max
        self.budget = budget
        self.strict = strict
        self.feats = []          # 标准化后的 45 维（list[tuple]）
        self.raw = []            # 原始 45 维（算夹角必须用未标准化的主轴）
        self.res = array("b")    # 走子方视角结果：1 胜 / 0 和 / -1 负
        self.side = array("b")   # 该局面轮到谁走
        self.tree = None
        self.meta = {}
        # 走子先验库（build_exp.py 产出）：局面 → 名手实际着法
        self.mfeats = None
        self.mmoves = None
        self.mres = None
        self.msides = None
        self.mbuckets = None
        self.mmode = "value"
        if exp_path and os.path.exists(exp_path):
            self.load_experience(exp_path)

    # -- 建/存/取 --------------------------------------------------
    def build_experience(self, rows, limit=None, verbose=True):
        """rows: [(board, side, result), ...]，result 为**走子方视角**：1 胜 / 0 和 / -1 负。"""
        t0 = time.time()
        self.feats, self.raw, self.res, self.side = [], [], array("b"), array("b")
        for i, (b, side, r) in enumerate(rows):
            if limit and i >= limit:
                break
            f = self.fz.feats45(list(b), side)
            self.raw.append(f)
            self.feats.append(self.fz.standardize(f))
            self.res.append(int(r))
            self.side.append(int(side))
            if verbose and (i + 1) % 5000 == 0:
                print(f"  特征 {i+1}/{limit or len(rows)}  {time.time()-t0:.0f}s", flush=True)
        self._rebuild_index()
        self.meta = {"n": len(self.feats), "sigma": self.sigma,
                     "cos_min": self.cos_min, "rho_ratio": self.rho_ratio}
        if verbose:
            print(f"经验库建成：{len(self.feats)} 节点，{time.time()-t0:.1f}s", flush=True)
        return self

    def _rebuild_index(self):
        self.tree = KDTree.build(self.feats, list(range(len(self.feats))), self.pose_dims, leaf=16) if self.feats else None

    def save_experience(self, path=DEFAULT_EXP):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"raw": self.raw, "res": self.res, "side": self.side,
                         "meta": self.meta}, f, protocol=4)

    def load_experience(self, path=DEFAULT_EXP):
        with open(path, "rb") as f:
            d = pickle.load(f)
        self.raw = d["raw"]
        self.res, self.side = d["res"], d["side"]
        self.feats = [self.fz.standardize(r) for r in self.raw]
        self.meta = d.get("meta", {})
        self._rebuild_index()
        return self

    # -- 拼接相容性（核心） -----------------------------------------
    def pose_agreement(self, pose_a, pose_b):
        """几何一致度 ∈ [0,1]：三空间主轴夹角余弦的平均值。

        这是「拼接」的连续度量。硬阈值（|cos| ≥ cos_min）在实测里太苛刻：
        12000 个节点的经验库上，最近邻的 |cos| 中位数只有 0.63、p75 才 0.83，
        0.9 会一次性拒掉约 87% 的邻居，使判据退化成常数折扣、失去区分力。
        所以默认用连续值加权，硬阈值保留给 `strict=True` 和统计口径。
        """
        tot = 0.0
        for (ca, va, ra), (cb, vb, rb) in zip(pose_a, pose_b):
            tot += abs(va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2])
        return tot / 3.0

    def pose_compatible(self, pose_a, pose_b, cos_min=None, rho_ratio=None):
        """硬判据：三个几何条件全部满足才允许「强拼接」。

        1. **主轴夹角** |cos| ≥ cos_min：姿态朝向一致（取绝对值，因为主轴正负号
           只是规范化约定，反向不代表结构不同）。
        2. **残差量级** |ln(ρa/ρb)| ≤ rho_ratio：ρ 是点云到主轴的均方垂直距离，
           衡量「松紧程度」；用对数比是因为 ρ 跨数量级。实测邻居 p90 只有 0.30，
           所以 0.35 已足够严格。
        3. **质心距离**：三空间质心必须落在同一片区域，避免把「左翼密集」和
           「右翼密集」当成同一姿态。

        返回 (ok, 原因)。
        """
        cos_min = self.cos_min if cos_min is None else cos_min
        rho_ratio = self.rho_ratio if rho_ratio is None else rho_ratio
        for i, ((ca, va, ra), (cb, vb, rb)) in enumerate(zip(pose_a, pose_b)):
            dot = abs(va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2])
            if dot < cos_min:
                return False, "axis%d" % i
            if ra > 1e-6 and rb > 1e-6 and abs(math.log(ra / rb)) > rho_ratio:
                return False, "rho%d" % i
            if math.dist(ca, cb) > self.centroid_max:
                return False, "centroid%d" % i
        return True, ""

    # -- 检索 ------------------------------------------------------
    def retrieve_similar_nodes(self, feat, top_k=8, raw=None, use_compat=False):
        """45 维特征 → 最相似的 top_k 个历史节点。

        返回 [{'i': 索引, 'd': 标准化距离, 'res': 红方视角结果, 'side': 轮到谁,
                'w': 核权重, 'v': 我方视角价值}]，按距离升序。
        """
        if not self.feats:
            return []
        z = feat if raw is None else self.fz.standardize(feat)
        pool = self.tree.query(z, self.feats, k=max(self.pool, top_k * 4),
                               budget=self.budget, dim_w=DIM_W) if self.tree else []
        if not pool:                      # 索引为空时退回全量
            pool = []
        out = []
        for d2, i in pool:
            # 第二段：45 维分块加权重排（索引只在 13 维投影上剪枝）
            out.append((block_dist2(z, self.feats[i]), i))
        out.sort()
        res = []
        for d2f, i in out[:top_k]:
            d = math.sqrt(d2f)
            w = math.exp(-d2f / (2 * self.sigma * self.sigma))
            # 经验库里存的已经是「走子方视角」（result_import.py 里做过 res*side），
            # 这里不能再乘一次 side，否则会引入系统性正偏。
            z_side = self.res[i]
            res.append({"i": i, "d": d, "w": w, "res": self.res[i],
                        "side": self.side[i], "v": z_side})
        if use_compat and raw is not None:
            kept = []
            for r in res:
                ok, _why = self.pose_compatible(self._pose_of(raw), self._pose_of(self.raw[r["i"]]))
                if ok:
                    kept.append(r)
            if kept:
                res = kept
        return res

    @staticmethod
    def _pose_of(f):
        """从 45 维向量里取三空间 (质心, 主轴, 残差)。"""
        out = []
        for k in (0, 7, 14):
            out.append(((f[k], f[k + 1], f[k + 2]),
                        (f[k + 3], f[k + 4], f[k + 5]), f[k + 6]))
        return out

    # -- 走子先验库 ------------------------------------------------
    def load_move_experience(self, path):
        """载入 build_exp.py 产出的「局面 → 着法 → 胜负」经验库。"""
        with open(path, "rb") as f:
            d = pickle.load(f)
        self.mfeats = d["feats"]
        self.mmoves = d["moves"]
        self.mres = d["res"]
        self.msides = d["sides"]
        self.mbuckets = d["buckets"]
        self.mplies = d.get("plies")
        # 精确局面表：hash → 节点下标列表
        self.mindex = {}
        hs = d.get("hashes")
        if hs is not None:
            for i, h in enumerate(hs):
                self.mindex.setdefault(h, []).append(i)
        self.mmode = "move"
        self.meta = dict(d.get("meta", {}), buckets=len(self.mbuckets))
        return self

    def move_prior(self, board, side, top_k=64, expand=1, max_cand=9000, ply=None,
                   ply_w=0.35, verbose=False):
        """检索一次，聚合邻居局面里名手走过的着法 → 走子先验。

        与「价值检索」的关键区别：**每个局面只查一次**，不是每个候选着法查一次。
        所以即使单次检索十几毫秒，整条推演仍然可跑。

        返回 (hist, info)：hist 是 {canon_move: 权重}，权重已按核函数归一化。
        """
        if self.mfeats is None:
            return {}, {"n": 0}
        raw = self.fz.feats45(board, side)
        z = self.fz.standardize(raw)

        # ① 先查精确局面：库里有同一局面时，几何近邻反而不如直接取统计
        hit = self.mindex.get(board_hash(board, side))
        if hit:
            hist = {}
            for i in hit:
                mv = self.mmoves[i]
                hist[mv] = hist.get(mv, 0.0) + 1.0
            tot = sum(hist.values())
            for k in hist:
                hist[k] /= tot
            return hist, {"n": len(hit), "cand": len(hit), "d0": 0.0, "exact": True}

        key = material_key(board, side, raw)
        cand, seen = [], set()
        for db in range(-expand, expand + 1):
            for dt in range(-expand, expand + 1):
                for dc in range(-expand, expand + 1):
                    lst = self.mbuckets.get((key[0] + db, key[1] + dt, key[2] + dc))
                    if not lst:
                        continue
                    for i in lst:
                        if i not in seen:
                            seen.add(i)
                            cand.append(i)
                    if len(cand) >= max_cand:
                        break
        # 只取同一走子方的邻居：特征本身与颜色无关，但「走法」不无关，
        # 混色会把红黑两侧的着法折叠成一类，先验变得不可解释。
        cand = [i for i in cand if self.msides[i] == side]
        if not cand:
            return {}, {"n": 0}
        if len(cand) > max_cand:
            cand = cand[:max_cand]

        # 桶内 45 维分块加权距离（桶已按子力对齐，所以这里的距离才「有意义」）
        scored = []
        F = self.mfeats
        for i in cand:
            base = i * 45
            t = 0.0
            for lo, hi, w in BLOCKS:
                acc = 0.0
                for k in range(lo, hi):
                    d = z[k] - F[base + k]
                    acc += d * d
                t += w * acc / (hi - lo)
            # 步数感知：同一形状在 ply 4 和 ply 40 的意义完全不同。
            # 不加这一项时，初始局面会被匹配到 ply 4~5 的局面，
            # 于是「第一手」的先验其实来自「第五手」，完全错位。
            if ply is not None and self.mplies is not None:
                dp = (self.mplies[i] - ply) / 10.0
                t += ply_w * dp * dp
            scored.append((t, i))
        scored.sort()
        scored = scored[:top_k]

        hist = {}
        tot = 0.0
        for d2, i in scored:
            w = math.exp(-d2 / (2 * self.sigma * self.sigma))
            mv = self.mmoves[i]
            hist[mv] = hist.get(mv, 0.0) + w
            tot += w
        if tot > 0:
            for k in hist:
                hist[k] /= tot
        if verbose:
            print(f"  桶 {key} 候选 {len(cand)} 近邻 {len(scored)} 着法 {len(hist)}")
        return hist, {"n": len(scored), "cand": len(cand),
                      "d0": scored[0][0] ** 0.5 if scored else None, "exact": False}

    # -- 拼接打分 --------------------------------------------------
    def stitch_and_score(self, board, side, moves, top_k=8, detail=False, mode=None, ply=None):
        """mode='prior'：走子先验（名手在相似局面里怎么走）；
        mode='value'：局面价值（相似局面的历史胜负）。默认按已载入的库自动选。"""
        mode = mode or ("prior" if self.mfeats is not None else "value")
        if mode == "prior":
            hist, info = self.move_prior(board, side, top_k=max(top_k, 64), ply=ply)
            rows = []
            for mv in moves:
                rows.append({"mv": mv, "score": hist.get(mv[0] * 100 + mv[1], 0.0),
                             "n": info.get("n", 0), "compat": 0, "nearest": info.get("d0")})
            rows.sort(key=lambda r: -r["score"])
            return rows if detail else [(r["mv"], r["score"]) for r in rows]
        return self._value_score(board, side, moves, top_k, detail)

    def _value_score(self, board, side, moves, top_k=8, detail=False):
        """对每个候选走法，用「走完之后的局面」去查历史经验，给出支持度。

        支持度定义：相似节点按核权加权、并换算到「我们」视角的结果均值，
        取值 [-1, 1]。正数表示历史上走到类似局面的走子方更容易赢。
        注意走完一步后轮到对手，所以取负号。
        """
        rows = []
        for mv in moves:
            b2 = list(board)
            f0, t0 = mv
            b2[t0] = b2[f0]
            b2[f0] = 0
            feats, pose = self.fz.describe(b2, -side)      # 走完后轮到对手
            sims = self.retrieve_similar_nodes(feats, top_k=top_k)
            if not sims:
                rows.append({"mv": mv, "score": 0.0, "n": 0})
                continue
            sw = 0.0
            acc = 0.0
            keep = 0
            for s in sims:
                q = self._pose_of(self.raw[s["i"]])
                ag = self.pose_agreement(pose, q)               # 连续一致度 0~1
                ok, _why = self.pose_compatible(pose, q)
                if self.strict and not ok:
                    continue
                # 一致度做软加权（平方使差异更明显），硬判据只用于统计
                w = s["w"] * (0.10 + 0.90 * ag * ag)
                sw += w
                acc += w * s["v"]
                keep += 1 if ok else 0
            val = -(acc / sw) if sw > 0 else 0.0            # 对手视角 → 我方视角
            rows.append({"mv": mv, "score": val, "n": len(sims),
                         "compat": keep, "nearest": sims[0]["d"] if sims else None})
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows if detail else [(r["mv"], r["score"]) for r in rows]

    # -- 多步预测（束搜索） -----------------------------------------
    def predict_trajectory(self, board, side, depth=30, beam=3, max_moves=None,
                           top_k=8, verbose=False):
        """沿历史经验向前推演 depth 步（半步），保留得分最高的 beam 条轨迹。

        每推进一步都是一次「检索 + 姿态匹配 + 拼接」，所以一条轨迹天然是
        由多个历史节点缝起来的；束搜索负责在缝合点出现冲突时换一条线。
        返回 dict：best(首步)、traj(着法序列)、value(累计支持度)、frames。
        """
        t0 = time.time()
        # 每条轨迹：(累计支持度, 剩余盘面, 轮到谁, 着法序列, 逐步分数)
        beams = [(0.0, list(board), side, [], [])]
        first_rows = None
        for ply in range(depth):
            nxt = []
            for cum, b, sd, path, scores in beams:
                moves = _legal_moves(b, sd)
                if not moves:            # 终局：该轨迹到此为止，不再往下累加
                    continue
                cand = moves if not max_moves else moves[:max_moves]
                rows = self.stitch_and_score(b, sd, cand, top_k=top_k, detail=True, ply=ply)
                if ply == 0:
                    first_rows = rows
                for r in rows[:beam]:
                    b2 = list(b)
                    f0, t0_ = r["mv"]
                    b2[t0_] = b2[f0]
                    b2[f0] = 0
                    nxt.append((cum + r["score"], b2, -sd, path + [r["mv"]], scores + [r["score"]]))
            if not nxt:
                break
            nxt.sort(key=lambda x: x[0], reverse=True)
            beams = nxt[:beam]
            if verbose and ply % 10 == 0:
                print(f"  ply {ply}: best={beams[0][0]:.3f} {time.time()-t0:.1f}s", flush=True)
            if all(not _legal_moves(b, sd) for _c, b, sd, _p, _s in beams):
                break
        beams.sort(key=lambda x: x[0], reverse=True)
        cum, b, sd, path, scores = beams[0]
        return {"best": path[0] if path else None,
                "traj": path, "value": cum / max(1, len(path)),
                "total": cum, "plies": len(path),
                "final_side": sd, "secs": round(time.time() - t0, 2),
                "first_rows": first_rows or []}


# ---------------------------------------------------------------- 规则小工具
def _legal_moves(b, side):
    import board as B
    return B.gen_legal(b, side)


def _in_check(b, side):
    import board as B
    return B.in_check(b, side)


def main():
    ap = argparse.ArgumentParser(description="GeometricPredictor 命令行")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--exp", default=DEFAULT_EXP)
    ap.add_argument("--build", action="store_true", help="从 result_positions.pkl 重建经验库")
    ap.add_argument("--limit", type=int, default=12000, help="建库最多取多少个局面")
    ap.add_argument("--depth", type=int, default=30)
    ap.add_argument("--beam", type=int, default=3)
    ap.add_argument("--topk", type=int, default=8)
    args = ap.parse_args()

    if args.build:
        with open("data/result_positions.pkl", "rb") as f:
            rows = pickle.load(f)["rows"]
        # result_positions.pkl 的三元组是 (board, 走子方, 走子方视角结果)，
        # 由 result_import.py 的 res*side 生成，直接可用，不要重复换算。
        random.Random(20261115).shuffle(rows)      # 打散，避免只取到同一批棋谱
        p = GeometricPredictor(args.model, exp_path=None)
        p.build_experience(rows, limit=args.limit)
        p.save_experience(args.exp)
        print(f"已写入 {args.exp}")

    p = GeometricPredictor(args.model, exp_path=args.exp)
    print(f"经验库 {len(p.feats)} 节点，索引维度 {len(p.pose_dims)}")
    import board as B
    b = B.initial_board()
    r = p.predict_trajectory(b, RED, depth=args.depth, beam=args.beam, top_k=args.topk, verbose=True)
    print(f"首步 {r['best']}  平均支持度 {r['value']:.3f}  推演 {r['plies']} 步  {r['secs']}s")
    for row in r["first_rows"][:6]:
        print(f"   {row['mv']}  score={row['score']:+.3f}  相容 {row.get('compat',0)}/{row['n']}  "
              f"最近距离 {row['nearest']:.3f}" if row.get('nearest') is not None else f"   {row['mv']} 无邻居")


if __name__ == "__main__":
    main()
