"""为两个三维空间各训一个胜率模型：局部（邻域）空间与全局（共线）空间。

局部空间附「密集度」特征，全局空间附「延伸」与「主轴斜率」特征；
另训 14 维联合模型作参照。
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

import dual3d
import geo

LAYERS = [0, 3, 6]


def shape_feats(state, pts):
    """state 为 7 维；pts 为 [(w, [x,y,z])]。返回 [密集度, 延伸, 主轴斜率]。"""
    c = state[0:3]
    v = state[3:6]
    sw = sum(w for w, _ in pts) or 1.0
    dens = 0.0
    proj = []
    for w, p in pts:
        d2 = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2
        dens += w * float(np.exp(-d2 / 1.6))
        proj.append((p[0] - c[0]) * v[0] + (p[1] - c[1]) * v[1] + (p[2] - c[2]) * v[2])
    span = float(max(proj) - min(proj)) if proj else 0.0
    slope = min(5.0, float(np.hypot(v[0], v[1])) / max(abs(v[2]), 1e-6))
    return [dens / sw, span, slope]


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
    print(f"{tag:22s} acc {acc*100:5.1f}%  宏F1 {f1*100:5.1f}%  logloss {ll:.3f}  MAE {mae:.3f}  多数类 {maj*100:4.1f}%", flush=True)
    return {"acc": round(float(acc), 4), "f1": round(float(f1), 4), "logloss": round(float(ll), 4),
            "score_mae": round(mae, 4), "majority": round(float(maj), 4)}


def main():
    with open("data/result_positions.pkl", "rb") as f:
        d = pickle.load(f)
    rows = d["rows"]
    print("样本", len(rows), Counter(y for _, _, y in rows), flush=True)

    model = json.load(io.open("model_dual.json", encoding="utf-8"))
    A, Bt = model["coords3a"], model["coords3b"]
    y = np.array([r[2] for r in rows], dtype=int)
    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=0.25, random_state=0, stratify=y)

    Xs = {}
    for layer in LAYERS:
        X, F = [], []
        for b, s, _ in rows:
            v, _ = dual3d.state_dual(b, s, A, Bt, layers=layer)
            toks = geo.position_tokens(b, s)
            pa = [(t[3], A[t[0]]) for t in toks if t[0] in A]
            pb = [(t[3], Bt[t[0]]) for t in toks if t[0] in Bt]
            X.append(v)
            F.append(shape_feats(v[:7], pa) + shape_feats(v[7:], pb))
        Xs[layer] = (np.asarray(X, dtype=np.float64), np.asarray(F, dtype=np.float64))
        print("层", layer, "状态", Xs[layer][0].shape, "形特征", Xs[layer][1].shape, flush=True)

    def fit(X, tag):
        sc = StandardScaler().fit(X[tr])
        clf = LogisticRegression(max_iter=3000, C=1.0)
        clf.fit(sc.transform(X[tr]), y[tr])
        m = report(y[te], clf.predict_proba(sc.transform(X[te])), tag)
        seg = {"classes": [-1, 0, 1], "layer": None, "mean": sc.mean_.tolist(),
               "std": sc.scale_.tolist(), "W": clf.coef_.tolist(), "b": clf.intercept_.tolist(),
               "metrics": m, "dim": int(X.shape[1])}
        return m, seg, float(m["logloss"])

    best_local = best_global = best_all = None
    for layer in LAYERS:
        X14, F = Xs[layer]
        m, seg, ll = fit(np.hstack([X14[:, :7], F[:, 0:3]]), f"局部空间 第{layer}层")
        seg["layer"] = layer; seg["metrics"]["layer"] = layer; seg["feats"] = "7维+密集度带"
        if best_local is None or ll < best_local[0]:
            best_local = (ll, seg, m)

        m2, seg2, ll2 = fit(np.hstack([X14[:, 7:], F[:, 3:6]]), f"全局空间 第{layer}层")
        seg2["layer"] = layer; seg2["metrics"]["layer"] = layer; seg2["feats"] = "7维+延伸带"
        if best_global is None or ll2 < best_global[0]:
            best_global = (ll2, seg2, m2)

        m3, seg3, ll3 = fit(X14, f"联合 14 维 第{layer}层")
        seg3["layer"] = layer; seg3["metrics"]["layer"] = layer; seg3["feats"] = "14维"
        if best_all is None or ll3 < best_all[0]:
            best_all = (ll3, seg3, m3)

    model["winprob_local"] = best_local[1]
    model["winprob_global"] = best_global[1]
    model["winprob_dual"] = best_all[1]
    model["winprob_routes"] = {"local": best_local[2], "global": best_global[2], "dual": best_all[2],
                              "samples": len(rows)}
    json.dump(model, io.open("model_dual.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入 winprob_local / winprob_global / winprob_dual")


if __name__ == "__main__":
    main()
