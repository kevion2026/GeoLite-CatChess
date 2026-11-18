"""用几何状态预测胜率：把棋谱局面的四维/十七维状态喂给多项逻辑回归。

输出写回 model.json 的 winprob 段，供前端 XQ.winProb() 直接做前向计算。
"""

import argparse
import io
import json
import pickle
from collections import Counter

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

import board as B
import geo


def build_states(rows, coords, layer, dim):
    X = []
    for b, s, _ in rows:
        v, _ = geo.state_of(b, s, coords, layers=layer, dim=dim)
        X.append(v)
    return np.asarray(X, dtype=np.float64)


def report(y_true, proba, tag):
    pred = proba.argmax(1)
    cls = np.array([-1, 0, 1])
    acc = accuracy_score(y_true, cls[pred])
    f1 = f1_score(y_true, cls[pred], average="macro")
    ll = log_loss(y_true, proba, labels=[-1, 0, 1])
    exp = proba[:, 2] + 0.5 * proba[:, 1]
    real = (y_true + 1) / 2.0        # -1/0/1 -> 0/0.5/1
    mae = float(np.mean(np.abs(exp - real)))
    maj = max(Counter(y_true).values()) / len(y_true)
    print(f"{tag:28s} acc {acc*100:5.1f}%  宏F1 {f1*100:5.1f}%  logloss {ll:.3f}  "
          f"胜率预测MAE {mae:.3f}  多数类 {maj*100:4.1f}%", flush=True)
    return {"acc": round(float(acc), 4), "f1": round(float(f1), 4), "logloss": round(float(ll), 4),
            "score_mae": round(mae, 4), "majority": round(float(maj), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/result_positions.pkl")
    ap.add_argument("--max", type=int, default=60000)
    ap.add_argument("--layers", default="0,3,6,9,10")
    ap.add_argument("--test", type=float, default=0.25)
    args = ap.parse_args()

    with open(args.data, "rb") as f:
        d = pickle.load(f)
    rows = d["rows"]
    print("样本", len(rows), Counter(y for _, _, y in rows), flush=True)
    if len(rows) > args.max:
        rng = np.random.default_rng(0)
        rows = [rows[i] for i in rng.choice(len(rows), args.max, replace=False)]
        print("抽样到", len(rows), flush=True)

    y = np.array([r[2] for r in rows], dtype=int)
    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=args.test, random_state=0, stratify=y)

    coords2 = {k: tuple(v) for k, v in json.load(io.open("coords2.json", encoding="utf-8")).items()}
    coords8 = {k: tuple(v) for k, v in json.load(io.open("coords8.json", encoding="utf-8")).items()}

    best = None
    results = {}
    for layer in [int(x) for x in args.layers.split(",")]:
        X = build_states(rows, coords2, layer, 2)
        sc = StandardScaler().fit(X[tr])
        clf = LogisticRegression(max_iter=3000, C=1.0)
        clf.fit(sc.transform(X[tr]), y[tr])
        proba = clf.predict_proba(sc.transform(X[te])
)
        tag = f"4维 第{layer}层"
        m = report(y[te], proba, tag)
        results[tag] = m
        if best is None or m["logloss"] < results[best]["logloss"]:
            best = tag
            save = {"dim": 2, "layer": layer, "classes": [-1, 0, 1],
                    "mean": sc.mean_.tolist(), "std": sc.scale_.tolist(),
                    "W": clf.coef_.tolist(), "b": clf.intercept_.tolist(), "metrics": m}
        print("")

    # 17 维（八维坐标）第 10 层
    X8 = build_states(rows, coords8, 10, 8)
    sc8 = StandardScaler().fit(X8[tr])
    clf8 = LogisticRegression(max_iter=3000, C=1.0)
    clf8.fit(sc8.transform(X8[tr]), y[tr])
    m8 = report(y[te], clf8.predict_proba(sc8.transform(X8[te])), "17维 第10层")
    results["17维 第10层"] = m8

    with open("model.json", encoding="utf-8") as f:
        model = json.load(f)
    model["winprob"] = save
    model["winprob_17"] = {"dim": 17, "layer": 10, "classes": [-1, 0, 1], "metrics": m8,
                           "mean": sc8.mean_.tolist(), "std": sc8.scale_.tolist(),
                           "W": clf8.coef_.tolist(), "b": clf8.intercept_.tolist()}
    model["winprob_all"] = results
    with io.open("model.json", "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)
    print("最佳", best, "已写入 model.json 的 winprob 段")


if __name__ == "__main__":
    main()
