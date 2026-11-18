"""三空间分解：邻域（纠缠）、共线（远程）、中距+同兵种（结构）。

第三个三维空间专职做「裁判」：给前两个空间产出的候选着法打分。
"""

import argparse
import json
import pickle
import time

import numpy as np

import board as B
import geo
import train
import dual3d as D

CLASSES = train.CLASSES


def cooc_matrix3(positions, vocab, mode):
    """mode: near / line / mid。mid 覆盖 3~5 格的中距接触与同兵种配合。"""
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
                d = max(dx, dy)
                if mode == 'near':
                    w = 1.0 if d <= 2 else 0.0
                elif mode == 'line':
                    w = 0.5 if ((dx == 0 or dy == 0) and dx + dy <= 6) else 0.0
                else:
                    w = 1.0 if 3 <= d <= 5 else 0.0
                    if w == 0.0 and toks[i][0].split('@')[0][1:] == toks[j][0].split('@')[0][1:]:
                        w = 0.6          # 同兵种，跨区呼应
                if w == 0.0:
                    continue
                jj = vocab[toks[j][0]]
                C[ii, jj] += w
                C[jj, ii] += w
    return C


def state_triple(board_, side, A, Bt, Ct, layers=0):
    toks = geo.position_tokens(board_, side)
    ptsA, wsA, tA = D.pair_pts(toks, A)
    ptsB, wsB, tB = D.pair_pts(toks, Bt)
    ptsC, wsC, tC = D.pair_pts(toks, Ct)
    if len(ptsA) == 0 or len(ptsB) != len(ptsA) or len(ptsC) != len(ptsA):
        return np.zeros(21), {"layers": [], "kept": []}
    keep = list(range(len(ptsA)))
    recs = []

    def build(keep):
        cA, vA, rA, pA = D.fit(ptsA[keep], wsA[keep])
        cB, vB, rB, pB = D.fit(ptsB[keep], wsB[keep])
        cC, vC, rC, pC = D.fit(ptsC[keep], wsC[keep])
        vec = np.concatenate([cA, vA, [rA], cB, vB, [rB], cC, vC, [rC]])
        return vec, (cA, vA, rA, pA), (cB, vB, rB, pB), (cC, vC, rC, pC)

    vec, ia, ib, ic = build(keep)
    recs.append({"layer": 0, "state": vec.tolist(), "kept": len(keep),
                 "rhoA": ia[2], "rhoB": ib[2], "rhoC": ic[2]})
    for layer in range(1, layers + 1):
        if len(keep) <= 3:
            recs.append({"layer": layer, "state": vec.tolist(), "kept": len(keep),
                         "rhoA": ia[2], "rhoB": ib[2], "rhoC": ic[2]})
            continue
        comb = ia[3] + ib[3] + ic[3]
        keep.pop(int(np.argmax(comb)))
        vec, ia, ib, ic = build(keep)
        recs.append({"layer": layer, "state": vec.tolist(), "kept": len(keep),
                     "rhoA": ia[2], "rhoB": ib[2], "rhoC": ic[2]})
    return vec, {"kept": [tA[i][0] for i in keep], "layers": recs, "tokens": toks}


def states(pos_list, A, Bt, Ct, layer):
    out = []
    for b, s, _ in pos_list:
        v, _ = state_triple(b, s, A, Bt, Ct, layers=layer)
        out.append(v)
    return np.asarray(out, dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", default="data/pgn_positions.pkl")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--eval-max", type=int, default=19999)
    ap.add_argument("--out", default="model_triple.json")
    args = ap.parse_args()

    t0 = time.time()
    positions = train.build_corpus(args.games)
    with open(args.pgn, "rb") as f:
        d = pickle.load(f)
    real = d["positions"]
    positions.extend((b, s, train.situation(b, s)) for (b, s) in real)
    print(f"语料 {len(positions)} 局面，{time.time()-t0:.1f}s", flush=True)

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
    print("评估集", len(ev), {c: labels.count(c) for c in CLASSES}, flush=True)

    vocab = geo.build_vocab(positions)
    freq = {}
    for b, s, _ in positions:
        for t in geo.position_tokens(b, s):
            freq[t[0]] = freq.get(t[0], 0) + 1
    keep = {k: i for k, i in vocab.items() if freq[k] >= 2}
    keys = sorted(keep, key=lambda k: keep[k])

    t0 = time.time()
    CA = cooc_matrix3(positions, keep, 'near')
    CB = cooc_matrix3(positions, keep, 'line')
    CC = cooc_matrix3(positions, keep, 'mid')
    A, sA = D.embed_from(CA, keys, 3)
    Bt, sB = D.embed_from(CB, keys, 3)
    Ct, sC = D.embed_from(CC, keys, 3)
    print(f"三个空间各 {len(A)} 令牌，{time.time()-t0:.1f}s", flush=True)
    print("奇异值 邻域", [round(x, 2) for x in sA[:5]])
    print("奇异值 共线", [round(x, 2) for x in sB[:5]])
    print("奇异值 中距", [round(x, 2) for x in sC[:5]])

    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.neighbors import KNeighborsClassifier

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
            ztr, zte = (X[tr] - mu) / sd, (X[te] - mu) / sd
            pr = np.stack([ztr[y[tr] == c].mean(0) for c in range(len(CLASSES))])
            accs.append((np.linalg.norm(pr[None] - zte[:, None], axis=2).argmin(1) == y[te]).mean())
        return float(np.mean(accs))

    table, allX, lib_states, proto_by_layer, norm = [], {}, {}, {}, {}
    for layer in range(11):
        X = states(ev, A, Bt, Ct, layer)
        allX[layer] = X
        k_acc, p_acc = eval_knn(X), eval_proto(X)
        table.append({"layer": layer, "knn_acc": round(k_acc, 4), "proto_acc": round(p_acc, 4)})
        mu, sd = X.mean(0), X.std(0)
        sd[sd < 1e-9] = 1.0
        norm[str(layer)] = {"mean": [round(float(v), 3) for v in mu],
                            "std": [round(float(max(v, 1e-6)), 3) for v in sd]}
        z = (X - mu) / sd
        proto_by_layer[str(layer)] = np.stack([z[y == c].mean(0) for c in range(len(CLASSES))]).tolist()
        print(table[-1], flush=True)

    best = max(table, key=lambda r: r["knn_acc"])
    Xb = allX[best["layer"]]
    kA, kB, kC = eval_knn(Xb[:, :7]), eval_knn(Xb[:, 7:14]), eval_knn(Xb[:, 14:21])
    print(f"最佳层 {best['layer']}：三空间 {best['knn_acc']*100:.2f}% | 邻域 {kA*100:.2f}% | 共线 {kB*100:.2f}% | 中距 {kC*100:.2f}%")

    rng = np.random.default_rng(42)
    idx = rng.choice(len(ev), size=min(1200, len(ev)), replace=False)
    for layer in range(11):
        lib_states[str(layer)] = [[round(float(v), 3) for v in row] for row in allX[layer][idx]]
    lib_labels = [CLASSES.index(labels[i]) for i in idx]

    model = {
        "meta": {"positions": len(positions), "eval_positions": len(ev), "games": args.games,
                 "pgn_files": int(d.get("files", 0)), "real_positions": len(real),
                 "vocab": len(A), "dim": "triple3", "coverage": 1.0,
                 "classes": CLASSES, "class_cn": train.CLASS_CN,
                 "class_dist": {c: labels.count(c) for c in CLASSES},
                 "majority": round(max(labels.count(c) for c in CLASSES) / len(labels), 4),
                 "layers": 10, "stop_tokens": 3, "k": 5,
                 "best_layer": best["layer"], "knn_best": best["knn_acc"],
                 "proto_best": max(r["proto_acc"] for r in table),
                 "knn_onlyA": round(kA, 4), "knn_onlyB": round(kB, 4), "knn_onlyC": round(kC, 4),
                 "model_kb": round(len(json.dumps({"a": A, "b": Bt, "c": Ct})) / 1024, 1)},
        "coords3a": {k: [round(x, 3) for x in v] for k, v in A.items()},
        "coords3b": {k: [round(x, 3) for x in v] for k, v in Bt.items()},
        "coords3c": {k: [round(x, 3) for x in v] for k, v in Ct.items()},
        "norm": norm, "prototypes": proto_by_layer,
        "library": {"states": lib_states, "labels": lib_labels},
        "layers": table,
    }
    json.dump(model, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写出", args.out)


if __name__ == "__main__":
    main()
