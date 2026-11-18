"""GeoLite 几何链路：词坐标（PPMI+SVD）、加权质心、主方向、四维状态、十层级联压缩、状态检索。

与论文的对应关系：
  词       -> 棋子-格位令牌（side, 兵种, 规范化格位）
  词性权重 -> 兵种角色权重 + 过河子力加成
  句子     -> 一步棋之后的整个盘面
  四维状态 -> [c_x, c_y, tanθ, ρ]
"""

import numpy as np

from board import (
    BLACK, CANNON, HORSE, KING, PAWN, RED, ROOK, ROLE_WEIGHT, W,
    ADVISOR, ELEPHANT, crossed_river, side_of,
)

SEP = "|"
ROLE_SELF = "S"
ROLE_OPP = "O"

MAX_LAYERS = 10
STOP_TOKENS = 3
CROSS_BOOST = 1.15


def canon(side):
    """把盘面旋到“走子方在下方”的标准视角。"""
    return side


def token_of(p, s, side):
    """单个棋子的令牌与规范化坐标。"""
    x, y = s % W, s // W
    if side == BLACK:
        cx, cy = (W - 1) - x, 9 - y
    else:
        cx, cy = x, y
    role = ROLE_SELF if side_of(p) == side else ROLE_OPP
    return f"{role}{abs(p)}@{cx}{cy}", cx, cy


def position_tokens(board, side):
    """盘面 -> 令牌列表 [(key, cx, cy, weight, type, square)]。"""
    toks = []
    for s in range(90):
        p = board[s]
        if p == 0:
            continue
        key, cx, cy = token_of(p, s, side)
        t = abs(p)
        w = ROLE_WEIGHT[t]
        if crossed_river(s // W, side_of(p)):
            w *= CROSS_BOOST
        toks.append((key, cx, cy, w, t, s))
    return toks


def token_weight_table():
    """导出各兵种权重，供前端与文档使用。"""
    return dict(ROLE_WEIGHT)


# ---------------------------------------------------------------- 坐标学习
def build_vocab(positions):
    vocab = {}
    for board, side, _ in positions:
        for key, *_ in position_tokens(board, side):
            if key not in vocab:
                vocab[key] = len(vocab)
    return vocab


def pair_window(cx1, cy1, cx2, cy2):
    """空间共现窗口：邻域 3x3 记 1，共线近距记 0.5。"""
    dx, dy = abs(cx1 - cx2), abs(cy1 - cy2)
    if max(dx, dy) <= 2:
        return 1.0
    if (dx == 0 or dy == 0) and (dx + dy) <= 6:
        return 0.5
    return 0.0


def cooccurrence(positions, vocab):
    V = len(vocab)
    C = np.zeros((V, V), dtype=np.float64)
    for board, side, _ in positions:
        toks = [t for t in position_tokens(board, side) if t[0] in vocab]
        n = len(toks)
        for i in range(n):
            ki, cx1, cy1 = toks[i][0], toks[i][1], toks[i][2]
            ii = vocab[ki]
            for j in range(i + 1, n):
                w = pair_window(cx1, cy1, toks[j][1], toks[j][2])
                if w == 0.0:
                    continue
                jj = vocab[toks[j][0]]
                C[ii, jj] += w
                C[jj, ii] += w
    return C


def ppmi(C):
    total = C.sum()
    if total <= 0:
        return C
    rs = C.sum(axis=1, keepdims=True)
    cs = C.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        M = np.log((C * total) / (rs * cs))
    M[~np.isfinite(M)] = 0.0
    return np.maximum(M, 0.0)


def embed(positions, dim=2, min_freq=2, window_name="3x3+共线"):
    """PPMI + 截断 SVD，得到每个令牌的 dim 维坐标。"""
    vocab = build_vocab(positions)
    freq = {}
    for board, side, _ in positions:
        for t in position_tokens(board, side):
            freq[t[0]] = freq.get(t[0], 0) + 1
    keep = {k: i for k, i in vocab.items() if freq[k] >= min_freq}
    filtered = [(b, s, l) for (b, s, l) in positions]
    C = cooccurrence(filtered, keep)
    P = ppmi(C)
    U, S, Vt = np.linalg.svd(P, full_matrices=False)
    d = min(dim, S.shape[0])
    E = U[:, :d] * np.sqrt(S[:d])
    # 每维按标准差归一化
    sd = E.std(axis=0)
    sd[sd < 1e-9] = 1.0
    E = E / sd
    keys = list(keep.keys())
    idx_to_key = sorted(keep, key=lambda k: keep[k])
    table = {k: E[i].tolist() for i, k in enumerate(idx_to_key)}
    return table, {"vocab_size": len(table), "dim": d, "singular": S[:8].tolist()}


# ---------------------------------------------------------------- 四维状态
def weighted_centroid(pts, ws):
    sw = sum(ws)
    if sw <= 0:
        return np.zeros(pts.shape[1])
    return (pts * ws[:, None]).sum(axis=0) / sw


def principal_axis(pts, ws):
    c = weighted_centroid(pts, ws)
    deltas = pts - c
    cov = (ws[:, None] * deltas).T @ deltas / max(sum(ws), 1e-9)
    vals, vecs = np.linalg.eigh(cov)
    v = vecs[:, int(np.argmax(vals))]
    idx = int(np.argmax(np.abs(v)))
    if v[idx] < 0:
        v = -v
    return c, v, vals.max()


def state_from_points(pts, ws):
    c, v, lam = principal_axis(pts, ws)
    deltas = pts - c
    proj = deltas @ v
    perp2 = np.maximum((deltas ** 2).sum(axis=1) - proj ** 2, 0.0)
    rho = float(np.sqrt((ws * perp2).sum() / max(sum(ws), 1e-9)))
    d = pts.shape[1]
    if d == 2:
        if abs(v[0]) < 1e-6:
            slope = 5.0 if v[1] >= 0 else -5.0
        else:
            slope = float(np.clip(v[1] / v[0], -5.0, 5.0))
        vec = np.array([c[0], c[1], slope, rho])
    else:
        vec = np.concatenate([c, v, [rho]])
    return vec, {"centroid": c.tolist(), "axis": v.tolist(), "residual": rho,
                 "perp": perp2.tolist(), "lam": float(lam)}


def state_of(board, side, coords, layers=0, dim=2):
    """返回 (状态向量, 明细)。layers=0 表示不压缩，直接返回第 0 层。"""
    toks = [t for t in position_tokens(board, side) if t[0] in coords]
    if not toks:
        return np.zeros(3 + dim + 1), {"dropped": [], "layers": [], "tokens": []}
    pts = np.array([coords[t[0]] for t in toks], dtype=np.float64)
    ws = np.array([t[3] for t in toks], dtype=np.float64)
    keep = list(range(len(toks)))
    record = []
    dropped = []
    vec, info = state_from_points(pts[keep], ws[keep])
    info["kept"] = [toks[i][0] for i in keep]
    info["tokens"] = toks
    record.append({"layer": 0, "state": vec.tolist(), "kept": len(keep),
                   "residual": info["residual"], "slope": float(vec[2]) if dim == 2 else None})
    for layer in range(1, layers + 1):
        if len(keep) <= STOP_TOKENS:
            record.append({"layer": layer, "state": vec.tolist(), "kept": len(keep),
                           "residual": info["residual"], "slope": float(vec[2]) if dim == 2 else None,
                           "drop": None})
            continue
        pts_k = pts[keep]
        ws_k = ws[keep]
        c, v, _ = principal_axis(pts_k, ws_k)
        deltas = pts_k - c
        proj = deltas @ v
        perp2 = np.maximum((deltas ** 2).sum(axis=1) - proj ** 2, 0.0)
        # 取最大垂直距离；并列时取格位较小者，保证确定性
        k = 0
        for idx in range(1, len(keep)):
            if perp2[idx] > perp2[k] + 1e-9 or (
                abs(perp2[idx] - perp2[k]) <= 1e-9 and toks[keep[idx]][5] < toks[keep[k]][5]
            ):
                k = idx
        drop_tok = toks[keep[k]]
        dropped.append({"layer": layer, "token": drop_tok[0], "type": int(drop_tok[4]),
                        "square": int(drop_tok[5]), "perp": float(np.sqrt(perp2[k]))})
        keep.pop(k)
        vec, info = state_from_points(pts[keep], ws[keep])
        info["kept"] = [toks[i][0] for i in keep]
        record.append({"layer": layer, "state": vec.tolist(), "kept": len(keep),
                       "residual": info["residual"], "slope": float(vec[2]) if dim == 2 else None,
                       "drop": drop_tok[0]})
    info["dropped"] = dropped
    info["layers"] = record
    info["weighted"] = [float(w) for w in ws]
    return vec, info


# ---------------------------------------------------------------- 检索
class Retriever:
    """标准化欧氏距离下的最近原型与 kNN。"""

    def __init__(self, states, labels, classes):
        self.states = np.asarray(states, dtype=np.float64)
        self.labels = np.asarray(labels)
        self.classes = list(classes)
        self.mean = self.states.mean(axis=0)
        sd = self.states.std(axis=0)
        sd[sd < 1e-9] = 1.0
        self.std = sd
        z = (self.states - self.mean) / self.std
        self.z = z
        self.prototypes = np.stack([z[self.labels == c].mean(axis=0) for c in self.classes])
        self.prior = np.array([(self.labels == c).mean() for c in self.classes])

    def normalize(self, s):
        return (np.asarray(s, dtype=np.float64) - self.mean) / self.std

    def prototype_distances(self, s):
        z = self.normalize(s)
        return np.linalg.norm(self.prototypes - z, axis=1)

    def knn(self, s, k=5):
        z = self.normalize(s)
        d = np.linalg.norm(self.z - z, axis=1)
        idx = np.argsort(d)[:k]
        vote = {}
        for i in idx:
            lab = self.labels[i]
            vote[lab] = vote.get(lab, 0.0) + 1.0 / (d[i] + 1e-6)
        total = sum(vote.values())
        prob = {c: vote.get(c, 0.0) / total for c in self.classes}
        best = max(prob, key=prob.get)
        return best, prob, float(d[idx[0]]), [(str(self.labels[i]), float(d[i])) for i in idx]
