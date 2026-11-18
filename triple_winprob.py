"""三空间各训一个胜率模型；第三个空间（中距）专职当「裁判」。

每个空间用 7 维状态 + 3 个形特征（密集度 / 延伸 / 主轴斜率）。
"""

import io
import json
import pickle
from collections import Counter

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

import geo
import triple3d
from dual_winprob import shape_feats

LAYERS = [0, 3]


def report(y_true, proba, tag):
    cls = np.array([-1, 0, 1])
    pred = cls[proba.argmax(1)]
    acc = accuracy_score(y_true, pred)
    f1 = f1_score(y_true, pred, average="macro")
    ll = log_loss(y_true, proba, labels=[-1, 0, 1])
    exp = proba[:, 2] + 0.5 * proba[:, 1]
    real = (y_true + 1) / 2.0
    mae = float(np.mean(np.abs(exp - real)))
    maj = max(Counter(y_true).values()) / len(y_true)
    print(f"{tag:20s} acc {acc*100:5.1f}%  宏F1 {f1*100:5.1f}%  logloss {ll:.3f}  MAE {mae:.3f}  多数类 {maj*100:4.1f}%", flush=True)
    return {"acc": round(float(acc), 4), "f1": round(float(f1), 4), "logloss": round(float(ll), 4),
            "score_mae": round(mae, 4), "majority": round(float(maj), 4)}


def main():
    with open("data/result_positions.pkl", "rb") as f:
        d = pickle.load(f)
    rows = d["rows"]
    print("样本", len(rows), Counter(y for _, _, y in rows), flush=True)

    M = json.load(io.open("model_triple.json", encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]
    y = np.array([r[2] for r in rows], dtype=int)
    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=0.25, random_state=0, stratify=y)

    Xs = {}
    for layer in LAYERS:
        X, F = [], []
        for b, s, _ in rows:
            v, _ = triple3d.state_triple(b, s, A, Bt, Ct, layers=layer)
            toks = geo.position_tokens(b, s)
            pa = [(t[3], A[t[0]]) for t in toks if t[0] in A]
            pb = [(t[3], Bt[t[0]]) for t in toks if t[0] in Bt]
            pc = [(t[3], Ct[t[0]]) for t in toks if t[0] in Ct]
            X.append(v)
            F.append(shape_feats(v[:7], pa) + shape_feats(v[7:14], pb) + shape_feats(v[14:21], pc))
        Xs[layer] = (np.asarray(X, dtype=np.float64), np.asarray(F, dtype=np.float64))
        print("层", layer, Xs[layer][0].shape, Xs[layer][1].shape, flush=True)

    def fit(X, tag):
        sc = StandardScaler().fit(X[tr])
        clf = LogisticRegression(max_iter=3000, C=1.0)
        clf.fit(sc.transform(X[tr]), y[tr])
        m = report(y[te], clf.predict_proba(sc.transform(X[te])), tag)
        seg = {"classes": [-1, 0, 1], "dim": int(X.shape[1]), "mean": sc.mean_.tolist(),
               "std": sc.scale_.tolist(), "W": clf.coef_.tolist(), "b": clf.intercept_.tolist(),
               "metrics": m}
        return seg, float(m["logloss"])

    best = {}
    for layer in LAYERS:
        X21, F = Xs[layer]
        parts = {"local": (np.hstack([X21[:, :7], F[:, 0:3]]), 0),
                 "global": (np.hstack([X21[:, 7:14], F[:, 3:6]]), 1),
                 "judge": (np.hstack([X21[:, 14:21], F[:, 6:9]]), 2),
                 "joint": (X21, 3)}
        for name, (X, _) in parts.items():
            seg, ll = fit(X, f"{name} 第{layer}层")
            seg["layer"] = layer
            seg["metrics"]["layer"] = layer
            if name not in best or ll < best[name][0]:
                best[name] = (ll, seg)

    M["winprob_local"] = best["local"][1]
    M["winprob_global"] = best["global"][1]
    M["winprob_judge"] = best["judge"][1]
    M["winprob_joint"] = best["joint"][1]
    M["winprob_routes"] = {k: v[1]["metrics"] for k, v in best.items()}
    json.dump(M, io.open("model_triple.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入 winprob_local / winprob_global / winprob_judge / winprob_joint")


if __name__ == "__main__":
    main()
