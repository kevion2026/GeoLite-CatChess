"""棋子平面输入（14×10×9）训练神经辅助头，几何树仍主导估值。"""

import argparse
import io
import json
import pickle
import pathlib

import numpy as np
from sklearn.neural_network import MLPClassifier

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def planes(board, side):
    """14 通道：7 类棋子 × 双方；视角统一成“我方在下”（黑方镜像 y）。"""
    out = np.zeros((14, 90), dtype=np.float32)
    flip = side < 0
    for s in range(90):
        q = int(board[s])
        if not q:
            continue
        x, y = s % 9, s // 9
        if flip:
            y = 9 - y
        c = (abs(q) - 1) + (0 if q > 0 else 7)
        out[c, y * 9 + x] = 1.0
    return out.ravel()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=["data/battle_labels.pkl", "data/pika_labels.pkl"])
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--blend", type=float, default=0.3)
    args = ap.parse_args()

    X, y, gid = [], [], []
    for f in args.data:
        d = pickle.load(open(HERE / f, "rb"))
        for i, r in enumerate(d["rows"]):
            X.append(planes(r["board"], r["side"]))
            y.append(float(np.clip(r["score"], -1500, 1500)))
            gid.append(str(r.get("game", i)))
    X = np.asarray(X, np.float32)
    y = np.asarray(y)
    gid = np.asarray(gid)
    print("平面样本", X.shape, flush=True)

    cls = np.where(y > 150, 2, np.where(y < -150, 0, 1))
    games = sorted(set(gid))
    rng = np.random.default_rng(0)
    gtr = set(rng.choice(games, size=int(len(games) * 0.75), replace=False).tolist())
    trn = np.array([i for i, g in enumerate(gid) if g in gtr])
    tst = np.array([i for i, g in enumerate(gid) if g not in gtr])
    print("训练/留出", len(trn), len(tst), flush=True)

    clf = MLPClassifier(hidden_layer_sizes=(args.hidden,), alpha=1e-3, max_iter=1200,
                        learning_rate_init=1e-3, random_state=0)
    clf.fit(X[trn], cls[trn])
    p = clf.predict_proba(X[tst])
    acc = float((p.argmax(1) == cls[tst]).mean())
    base = float(np.bincount(cls[tst]).max() / len(tst))
    print("平面网络三类准确率", round(acc * 100, 1), "% 基线", round(base * 100, 1), "%", flush=True)

    M = json.load(io.open(args.model, encoding="utf-8"))
    M["tree"]["neural2"] = {
        "kind": "plane-clf", "out": 90, "channels": 14, "hidden": args.hidden,
        "W": [w.tolist() for w in clf.coefs_], "b": [b.tolist() for b in clf.intercepts_],
        "blend": args.blend, "metrics": {"acc3": acc, "base": base},
    }
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入 neural2", flush=True)


if __name__ == "__main__":
    main()
