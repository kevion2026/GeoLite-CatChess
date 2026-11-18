"""语料生成、局面态势标注、坐标训练、五折评估与 model.json 导出。

论文里的“意图”在这里对应“局面态势”：棋子令牌 → 几何状态 → 检索态势类别 →
类别决定搜索策略权重。语料用随机对局自生成（论文用的是公开指令集）。
"""

import argparse
import json
import os
import random
import time

import numpy as np

import board as B
import geo

CLASSES = ["open", "contact", "attack", "defense", "endgame", "maneuver"]
CLASS_CN = {"open": "开局部署", "contact": "接触对峙", "attack": "攻王压迫",
            "defense": "防守回撤", "endgame": "残局收兵", "maneuver": "中局调动"}

PALACE_CENTER = {B.RED: (4, 1), B.BLACK: (4, 8)}


def situation(bd, side):
    """规则标注：局面态势（作为检索目标）。

    六类阈值经语料分位数校准：多数类约 25%，各类均有可观样本。
    """
    total = 0
    own, opp = [], []
    near2 = opp_near2 = 0
    for s in range(90):
        p = bd[s]
        if p == 0:
            continue
        t = abs(p)
        so = B.side_of(p)
        isown = so == side
        if t != B.KING:
            total += B.PIECE_VALUE[t]
        x, y = s % 9, s // 9
        (own if isown else opp).append((x, y, t))
        if t in (B.HORSE, B.ROOK, B.CANNON, B.PAWN) and B.crossed_river(y, so):
            pc = PALACE_CENTER[so]
            if max(abs(x - pc[0]), abs(y - pc[1])) <= 2:
                if isown:
                    near2 += 1
                else:
                    opp_near2 += 1
    contact = 0
    for x1, y1, _ in own:
        for x2, y2, _ in opp:
            if max(abs(x1 - x2), abs(y1 - y2)) <= 2:
                contact += 1
    if total <= 430:
        return "endgame"
    if near2 >= 1 and near2 >= opp_near2:
        return "attack"
    if opp_near2 >= 1 and opp_near2 > near2:
        return "defense"
    if contact >= 10:
        return "contact"
    if total >= 780 and contact <= 6:
        return "open"
    return "maneuver"


def playout(rng, max_plies=140, sample_from=4, sample_every=3):
    bd = B.initial_board()
    side = B.RED
    out = []
    for ply in range(max_plies):
        legal = B.gen_legal(bd, side)
        if not legal:
            break
        if ply >= sample_from and (ply - sample_from) % sample_every == 0:
            out.append((list(bd), side, situation(bd, side)))
        caps = [m for m in legal if bd[m[1]] != 0]
        if caps and rng.random() < 0.20:
            mv = rng.choice(caps)
        else:
            mv = rng.choice(legal)
        B.apply_move(bd, mv)
        side = -side
    return out


def build_corpus(games, seed=42):
    rng = random.Random(seed)
    positions = []
    for _ in range(games):
        positions.extend(playout(rng))
    return positions


def coverage(positions, coords):
    tot = 0
    hit = 0
    for bd, side, _ in positions:
        for key, *_ in geo.position_tokens(bd, side):
            tot += 1
            if key in coords:
                hit += 1
    return hit / max(tot, 1)


def states_at_layer(positions, coords, layer, dim=2):
    xs = []
    kept = []
    for bd, side, _ in positions:
        v, info = geo.state_of(bd, side, coords, layers=layer, dim=dim)
        xs.append(v)
        kept.append(len(info.get("kept", [])))
    return np.asarray(xs), kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=420)
    ap.add_argument("--pgn", default="", help="pgn_import.py 输出的真实棋谱局面文件")
    ap.add_argument("--eval-max", type=int, default=20000, help="评估用局面抽样上限")
    ap.add_argument("--out", default="model.json")
    ap.add_argument("--dim", type=int, default=2)
    args = ap.parse_args()

    t0 = time.time()
    positions = build_corpus(args.games)
    pgn_games = 0
    real_n = 0
    if args.pgn and os.path.exists(args.pgn):
        import pickle
        with open(args.pgn, "rb") as f:
            d = pickle.load(f)
        real = d["positions"]
        pgn_games = int(d.get("files", 0))
        real_n = len(real)
        positions.extend((b, s, situation(b, s)) for (b, s) in real)
        print(f"合入真实棋谱 {len(real)} 个局面（{pgn_games} 个棋谱文件）")
    print(f"语料 {len(positions)} 个局面，耗时 {time.time()-t0:.1f}s")
    labels = [p[2] for p in positions]

    # 评估集：类别分层抽样，控制 11 层消融的运行时间
    if len(positions) > args.eval_max:
        rng0 = random.Random(7)
        by_cls = {}
        for p in positions:
            by_cls.setdefault(p[2], []).append(p)
        quota = {c: max(1, int(round(args.eval_max * len(v) / len(positions))) ) for c, v in by_cls.items()}
        ev = []
        for c, v in by_cls.items():
            ev.extend(rng0.sample(v, min(quota[c], len(v))))
        positions_eval = ev
    else:
        positions_eval = positions
    print(f"评估集 {len(positions_eval)} 个局面（分层抽样）")
    labels_ev = [p[2] for p in positions_eval]
    dist = {c: labels_ev.count(c) for c in CLASSES}
    print("态势分布:", dist)

    t0 = time.time()
    coords, meta = geo.embed(positions, dim=args.dim, min_freq=2)
    print(f"二维坐标 {meta}，耗时 {time.time()-t0:.1f}s，覆盖率 {coverage(positions, coords):.3f}")

    coords8, meta8 = geo.embed(positions, dim=8, min_freq=2)

    with open("coords2.json", "w", encoding="utf-8") as f:
        json.dump(coords, f)
    with open("coords8.json", "w", encoding="utf-8") as f:
        json.dump(coords8, f)

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.metrics import f1_score

    y = np.array([CLASSES.index(l) for l in labels_ev])
    X2, kept0 = states_at_layer(positions_eval, coords, 0, dim=args.dim)
    X8, _ = states_at_layer(positions_eval, coords8, 0, dim=8)

    # 词袋基线：棋子-格位多热向量
    vocab = {k: i for i, k in enumerate(coords.keys())}
    X_bow = np.zeros((len(positions_eval), len(vocab)), dtype=np.float32)
    for i, (bd, side, _) in enumerate(positions_eval):
        for key, *_ in geo.position_tokens(bd, side):
            if key in vocab:
                X_bow[i, vocab[key]] = 1.0

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    folds = list(skf.split(X2, y))

    def eval_knn(X, k=5):
        accs, f1s = [], []
        for tr, te in folds:
            clf = KNeighborsClassifier(n_neighbors=k, weights="distance")
            clf.fit(X[tr], y[tr])
            pred = clf.predict(X[te])
            accs.append((pred == y[te]).mean())
            f1s.append(f1_score(y[te], pred, average="macro"))
        return float(np.mean(accs)), float(np.std(accs)), float(np.mean(f1s))

    def eval_proto(X):
        accs, f1s = [], []
        for tr, te in folds:
            mu = X[tr].mean(axis=0)
            sd = X[tr].std(axis=0)
            sd[sd < 1e-9] = 1.0
            ztr = (X[tr] - mu) / sd
            protos = np.stack([ztr[y[tr] == c].mean(axis=0) for c in range(len(CLASSES))])
            zte = (X[te] - mu) / sd
            d = np.linalg.norm(protos[None, :, :] - zte[:, None, :], axis=2)
            pred = d.argmin(axis=1)
            accs.append((pred == y[te]).mean())
            f1s.append(f1_score(y[te], pred, average="macro"))
        return float(np.mean(accs)), float(np.std(accs)), float(np.mean(f1s)), protos

    layer_table = []
    proto_by_layer = {}
    for layer in range(11):
        X2l, kept = states_at_layer(positions_eval, coords, layer, dim=args.dim)
        p_acc, p_std, p_f1, protos = eval_proto(X2l)
        k_acc, k_std, k_f1 = eval_knn(X2l)
        layer_table.append({"layer": layer, "proto_acc": round(p_acc, 4), "proto_std": round(p_std, 4),
                            "knn_acc": round(k_acc, 4), "knn_std": round(k_std, 4),
                            "proto_f1": round(p_f1, 4), "knn_f1": round(k_f1, 4),
                            "mean_tokens": round(float(np.mean(kept)), 2)})
        proto_by_layer[layer] = protos.tolist()
        print(layer_table[-1])

    X8l, _ = states_at_layer(positions_eval, coords8, 10, dim=8)
    k8_acc, k8_std, _ = eval_knn(X8l)
    p8_acc, p8_std, _, protos8 = eval_proto(X8l)
    print(f"八维 第10层 kNN {k8_acc:.3f} 原型 {p8_acc:.3f}")

    bow_acc = []
    bow_f1 = []
    for tr, te in folds:
        clf = LogisticRegression(max_iter=2000, C=3.0, class_weight="balanced")
        clf.fit(X_bow[tr], y[tr])
        pred = clf.predict(X_bow[te])
        bow_acc.append((pred == y[te]).mean())
        bow_f1.append(f1_score(y[te], pred, average="macro"))
    bow = (float(np.mean(bow_acc)), float(np.std(bow_acc)), float(np.mean(bow_f1)))

    majority = float(max(dist.values()) / len(labels_ev))

    # 延迟
    sample = positions_eval[:400]
    t0 = time.time()
    for bd, side, _ in sample:
        geo.state_of(bd, side, coords, layers=3, dim=args.dim)
    per_ms = (time.time() - t0) / len(sample) * 1000

    # 导出 4 维状态库（供前端 kNN），每层抽 1200 例
    rng = np.random.default_rng(42)
    idx = rng.choice(len(positions_eval), size=min(1200, len(positions_eval)), replace=False)
    lib = {}
    for layer in range(11):
        X2l, _ = states_at_layer([positions[i] for i in idx], coords, layer, dim=args.dim)
        lib[layer] = [[round(float(v), 2) for v in row] for row in X2l]
    lib_labels = [CLASSES.index(labels_ev[i]) for i in idx]

    norm = {}
    for layer in range(11):
        X2l, _ = states_at_layer(positions_eval, coords, layer, dim=args.dim)
        norm[layer] = {"mean": [round(float(v), 3) for v in X2l.mean(axis=0)],
                       "std": [round(float(max(v, 1e-6)), 3) for v in X2l.std(axis=0)]}

    model = {
        "meta": {
            "positions": len(positions), "eval_positions": len(positions_eval),
            "games": args.games, "pgn_files": pgn_games, "real_positions": real_n,
            "vocab": meta["vocab_size"], "dim": args.dim, "coverage": round(coverage(positions, coords), 4),
            "classes": CLASSES, "class_cn": CLASS_CN,
            "class_dist": dist,
            "majority": round(majority, 4),
            "layers": 10, "stop_tokens": 3, "k": 5,
            "latency_ms": round(per_ms, 3),
            "model_kb": round((len(json.dumps(coords)) + len(json.dumps(lib))) / 1024, 1),
        },
        "coords" + str(args.dim): {k: [round(x, 3) for x in v] for k, v in coords.items()},
        "norm": norm,
        "prototypes": proto_by_layer,
        "library": {"states": lib, "labels": lib_labels},
        "layers": layer_table,
        "baseline": {"bow_lr": [round(bow[0], 4), round(bow[1], 4), round(bow[2], 4)],
                     "majority": round(majority, 4)},
        "dim8": {"knn10": round(k8_acc, 4), "knn10_std": round(k8_std, 4),
                 "proto10": round(p8_acc, 4), "proto10_std": round(p8_std, 4),
                 "vocab": meta8["vocab_size"]},
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)
    print(f"已写出 {args.out}  {len(json.dumps(model))/1024:.0f} KB")


if __name__ == "__main__":
    main()

