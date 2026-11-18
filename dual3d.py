"""双三维分解：共现关系拆成「邻域窗口」与「共线窗口」两套矩阵，各自 PPMI-SVD 到 3 轴。

每个令牌因此在两个三维空间里各有一个坐标；局面在各自空间里拟合出一条主轴，
得到 2 × 7 = 14 维状态。压缩时按两空间垂直距离的平方和选弃令牌，线仍然是线。
"""

import argparse
import json
import pickle
import time

import numpy as np

import board as B
import geo
import train

CLASSES = train.CLASSES


def cooc_matrix(positions, vocab, mode):
    V = len(vocab)
    C = np.zeros((V, V), dtype=np.float64)
    for board_, side, _ in positions:
        toks = [t for t in geo.position_tokens(board_, side) if t[0] in vocab]
        n = len(toks)
        for i in range(n):
            cx1, cy1 = toks[i][1], toks[i][2]
            ii = vocab[toks[i][0]]
            for j in range(i + 1, n):
                dx, dy = abs(cx1 - toks[j][1]), abs(cy1 - toks[j][2])
                if mode == 'near':
                    w = 1.0 if max(dx, dy) <= 2 else 0.0
                else:
                    w = 0.5 if ((dx == 0 or dy == 0) and dx + dy <= 6) else 0.0
                if w == 0.0:
                    continue
                jj = vocab[toks[j][0]]
                C[ii, jj] += w
                C[jj, ii] += w
    return C


def embed_from(C, keys, dim=3):
    P = geo.ppmi(C)
    U, S, Vt = np.linalg.svd(P, full_matrices=False)
    d = min(dim, S.shape[0])
    E = U[:, :d] * np.sqrt(S[:d])
    sd = E.std(axis=0)
    sd[sd < 1e-9] = 1.0
    E = E / sd
    return {k: E[i].tolist() for i, k in enumerate(keys)}, S[:8].tolist()


def pair_pts(toks, table):
    pts, ws, keys, ss = [], [], [], []
    for t in toks:
        c = table.get(t[0])
        if c is None:
            continue
        pts.append(c)
        ws.append(t[3])
        keys.append(t)
    return np.asarray(pts, dtype=np.float64), np.asarray(ws, dtype=np.float64), keys


def fit(pts, ws):
    c, v, lam = geo.principal_axis(pts, ws)
    deltas = pts - c
    proj = deltas @ v
    perp2 = np.maximum((deltas ** 2).sum(axis=1) - proj ** 2, 0.0)
    rho = float(np.sqrt((ws * perp2).sum() / max(ws.sum(), 1e-9)))
    return c, v, rho, perp2


def state_dual(board_, side, A, Bt, layers=0):
    toks = geo.position_tokens(board_, side)
    ptsA, wsA, toksA = pair_pts(toks, A)
    ptsB, wsB, toksB = pair_pts(toks, Bt)
    if len(ptsA) == 0 or len(ptsB) == 0 or len(ptsA) != len(ptsB):
        return np.zeros(14), {"kept": [], "layers": []}
    keep = list(range(len(ptsA)))
    recs = []

    def build(keep):
        cA, vA, rA, perpA = fit(ptsA[keep], wsA[keep])
        cB, vB, rB, perpB = fit(ptsB[keep], wsB[keep])
        vec = np.concatenate([cA, vA, [rA], cB, vB, [rB]])
        return vec, (cA, vA, rA, perpA), (cB, vB, rB, perpB)

    vec, ia, ib = build(keep)
    recs.append({"layer": 0, "state": vec.tolist(), "kept": len(keep),
                 "rhoA": ia[2], "rhoB": ib[2]})
    for layer in range(1, layers + 1):
        if len(keep) <= 3:
            recs.append({"layer": layer, "state": vec.tolist(), "kept": len(keep),
                         "rhoA": ia[2], "rhoB": ib[2]})
            continue
        comb = ia[3] + ib[3]          # 两个三维空间的垂直距离平方和
        k = int(np.argmax(comb))
        keep.pop(k)
        vec, ia, ib = build(keep)
        recs.append({"layer": layer, "state": vec.tolist(), "kept": len(keep),
                     "rhoA": ia[2], "rhoB": ib[2]})
    return vec, {"kept": [toksA[i][0] for i in keep], "layers": recs, "tokens": toks}


def states(pos_list, A, Bt, layer):
    out = []
    for b, s, _ in pos_list:
        v, _ = state_dual(b, s, A, Bt, layers=layer)
        out.append(v)
    return np.asarray(out, dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", default="data/pgn_positions.pkl")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--eval-max", type=int, default=19999)
    ap.add_argument("--out", default="model_dual.json")
    args = ap.parse_args()

    t0 = time.time()
    positions = train.build_corpus(args.games)
    with open(args.pgn, "rb") as f:
        d = pickle.load(f)
    real = d["positions"]
    positions.extend((b, s, train.situation(b, s)) for (b, s) in real)
    print(f"语料 {len(positions)} 局面，{time.time()-t0:.1f}s")

    rng0 = np.random.default_rng(7)
    by = {}
    for i, p in enumerate(positions):
        by.setdefault(p[2], []).append(i)
    idx_ev = []
    for c, v in by.items():
        take = max(1, int(round(args.eval_max * len(v) / len(positions))))
        idx_ev.extend(rng0.choice(v, size=min(take, len(v)), replace=False).tolist())
    idx_ev = sorted(set(int(i) for i in idx_ev))
    ev = [positions[i] for i in idx_ev]
    labels = [positions[i][2] for i in idx_ev]
    y = np.array([CLASSES.index(l) for l in labels])
    print("评估集", len(ev), {c: labels.count(c) for c in CLASSES})

    vocab = geo.build_vocab(positions)
    freq = {}
    for b, s, _ in positions:
        for t in geo.position_tokens(b, s):
            freq[t[0]] = freq.get(t[0], 0) + 1
    keep = {k: i for k, i in vocab.items() if freq[k] >= 2}
    keys = sorted(keep, key=lambda k: keep[k])

    t0 = time.time()
    CA = cooc_matrix(positions, keep, 'near')
    CB = cooc_matrix(positions, keep, 'line')
    A, sA = embed_from(CA, keys, 3)
    Bt, sB = embed_from(CB, keys, 3)
    print(f"两个三维空间各 {len(A)} 令牌，{time.time()-t0:.1f}s")
    print("邻域奇异值", [round(x, 2) for x in sA[:5]])
    print("共线奇异值", [round(x, 2) for x in sB[:5]])

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.metrics import f1_score

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    folds = list(skf.split(np.zeros(len(y)), y))

    def eval_knn(X, k=5):
        accs = []
        for tr, te in folds:
            clf = KNeighborsClassifier(n_neighbors=k, weights="distance").fit(X[tr], y[tr])
            accs.append((clf.predict(X[te]) == y[te]).mean())
        return float(np.mean(accs))

    def eval_proto(X):
        accs = []
        for tr, te in folds:
            mu, sd = X[tr].mean(0), X[tr].std(0)
            sd[sd < 1e-9] = 1.0
            ztr = (X[tr] - mu) / sd
            zte = (X[te] - mu) / sd
            pr = np.stack([ztr[y[tr] == c].mean(0) for c in range(len(CLASSES))])
            accs.append(((np.linalg.norm(pr[None] - zte[:, None], axis=2)).argmin(1) == y[te]).mean())
        return float(np.mean(accs))

    table = []
    lib_states, proto_by_layer, norm = {}, {}, {}
    allX = {}
    for layer in range(11):
        X = states(ev, A, Bt, layer)
        allX[layer] = X
        k_acc, p_acc = eval_knn(X), eval_proto(X)
        table.append({"layer": layer, "knn_acc": round(k_acc, 4), "proto_acc": round(p_acc, 4),
                      "kept": round(float(np.mean([len(state_dual(b, s, A, Bt, layers=layer)[1]["kept"]) for b, s, _ in ev[:200]])), 2)})
        mu, sd = X.mean(0), X.std(0)
        sd[sd < 1e-9] = 1.0
        norm[str(layer)] = {"mean": [round(float(v), 3) for v in mu], "std": [round(float(max(v, 1e-6)), 3) for v in sd]}
        z = (X - mu) / sd
        proto_by_layer[str(layer)] = np.stack([z[y == c].mean(0) for c in range(len(CLASSES))]).tolist()
        print(table[-1])

    best = max(table, key=lambda r: r["knn_acc"])
    Xb = allX[best["layer"]]
    # 两个空间各自的贡献：拆开评估
    kA = eval_knn(Xb[:, :7])
    kB = eval_knn(Xb[:, 7:])
    print(f"最佳层 {best['layer']}：联合 {best['knn_acc']*100:.2f}% | 仅邻域 {kA*100:.2f}% | 仅共线 {kB*100:.2f}%")

    rng = np.random.default_rng(42)
    idx = rng.choice(len(ev), size=min(1200, len(ev)), replace=False)
    for layer in range(11):
        lib_states[str(layer)] = [[round(float(v), 3) for v in row] for row in allX[layer][idx]]
    lib_labels = [CLASSES.index(labels[i]) for i in idx]

    model = {
        "meta": {
            "positions": len(positions), "eval_positions": len(ev), "games": args.games,
            "pgn_files": int(d.get("files", 0)), "real_positions": len(real),
            "vocab": len(A), "dim": "dual3", "coverage": 1.0,
            "classes": CLASSES, "class_cn": train.CLASS_CN,
            "class_dist": {c: labels.count(c) for c in CLASSES},
            "majority": round(max(labels.count(c) for c in CLASSES) / len(labels), 4),
            "layers": 10, "stop_tokens": 3, "k": 5,
            "best_layer": best["layer"], "knn_best": best["knn_acc"], "proto_best": max(r["proto_acc"] for r in table),
            "knn_onlyA": round(kA, 4), "knn_onlyB": round(kB, 4),
            "model_kb": round(len(json.dumps({"a": A, "b": Bt})) / 1024, 1),
        },
        "coords3a": {k: [round(x, 3) for x in v] for k, v in A.items()},
        "coords3b": {k: [round(x, 3) for x in v] for k, v in Bt.items()},
        "norm": norm, "prototypes": proto_by_layer,
        "library": {"states": lib_states, "labels": lib_labels},
        "layers": table,
        "baseline": {"bow_lr": [0.9108, 0.0014, 0.8719], "majority": model_meta_majority(labels)},
    }
    json.dump(model, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写出", args.out)


def model_meta_majority(labels):
    return round(max(labels.count(c) for c in CLASSES) / len(labels), 4)


if __name__ == "__main__":
    main()
