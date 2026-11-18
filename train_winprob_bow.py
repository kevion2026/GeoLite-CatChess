"""用令牌词袋（链路第一段）预测胜负，作为几何状态胜率模型的对照与实用版。"""

import io
import json
import pickle
from collections import Counter

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.model_selection import train_test_split

import geo


def main():
    with open("data/result_positions.pkl", "rb") as f:
        rows = pickle.load(f)["rows"]
    print("样本", len(rows), Counter(y for _, _, y in rows))

    keys = set()
    docs = []
    for b, s, _ in rows:
        ks = [t[0] for t in geo.position_tokens(b, s)]
        keys.update(ks)
        docs.append(ks)
    vocab = sorted(keys)
    vindex = {k: i for i, k in enumerate(vocab)}
    print("词表", len(vocab))

    X = np.zeros((len(docs), len(vocab)), dtype=np.float32)
    for i, ks in enumerate(docs):
        for k in ks:
            X[i, vindex[k]] = 1.0
    y = np.array([r[2] for r in rows], dtype=int)

    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=0.25, random_state=0, stratify=y)
    clf = LogisticRegression(max_iter=3000, C=3.0)
    clf.fit(X[tr], y[tr])
    proba = clf.predict_proba(X[te])
    pred = proba.argmax(1)
    cls = np.array([-1, 0, 1])
    acc = accuracy_score(y[te], cls[pred])
    f1 = f1_score(y[te], cls[pred], average="macro")
    ll = log_loss(y[te], proba, labels=[-1, 0, 1])
    exp = proba[:, 2] + 0.5 * proba[:, 1]
    mae = float(np.mean(np.abs(exp - (y[te] + 1) / 2.0)))
    maj = max(Counter(y[te]).values()) / len(y[te])
    print(f"词袋胜率模型  acc {acc*100:.1f}%  宏F1 {f1*100:.1f}%  logloss {ll:.3f}  MAE {mae:.3f}  多数类 {maj*100:.1f}%")

    metrics = {"acc": round(float(acc), 4), "f1": round(float(f1), 4), "logloss": round(float(ll), 4),
               "score_mae": round(mae, 4), "majority": round(float(maj), 4), "samples": int(len(rows))}

    # 导出给前端：token -> [3 个权重]，顺序 classes [-1,0,1]
    W = clf.coef_          # (3, V)
    b = clf.intercept_
    table = {}
    for k, i in vindex.items():
        w = [round(float(W[c][i]), 4) for c in range(3)]
        if any(abs(x) > 1e-4 for x in w):
            table[k] = w
    payload = {"classes": [-1, 0, 1], "b": [round(float(x), 4) for x in b], "w": table,
               "vocab": len(vocab), "metrics": metrics}
    with open("model.json", encoding="utf-8") as f:
        model = json.load(f)
    model["winprob_bow"] = payload
    model["winprob_bow_kb"] = round(len(json.dumps(payload)) / 1024, 1)
    with io.open("model.json", "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)
    print("已写入 winprob_bow，", payload["metrics"], f"{model['winprob_bow_kb']} KB")


if __name__ == "__main__":
    main()
