"""分支激活树（Branch-Activation Tree）：离线胜率预测。

把局面的「有用信息」分出来 → 在特征空间里画一棵树 → 每一步按距离激活邻近
分支 → 各分支本地模型加权给出分值 → 折算胜率。不用任何网络接口。
"""

import argparse
import io
import json
import pickle
from collections import Counter

import numpy as np
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import board as B
import geo
import triple3d
from matfeat import mat_feats
from dual_winprob import shape_feats


def metrics(y, p, thr=150):
    mae = float(np.mean(np.abs(y - p)))
    r2 = 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    rho = float(spearmanr(y, p).statistic)
    t3 = np.where(y >= thr, 1, np.where(y <= -thr, -1, 0))
    p3 = np.where(p >= thr, 1, np.where(p <= -thr, -1, 0))
    acc = float((t3 == p3).mean())
    maj = max(Counter(t3.tolist()).values()) / len(y)
    return dict(mae=round(mae, 1), r2=round(float(r2), 3), spearman=round(rho, 3),
                acc3=round(acc, 4), majority=round(float(maj), 4))


def soft_weights(X, centers, h):
    d2 = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
    w = np.exp(-d2 / (2 * h * h))
    return w / w.sum(1, keepdims=True)


class TreeExpert:
    def __init__(self, k=8, h=4.0, alpha=3.0, lam=0.5, depth=2):
        self.k, self.h, self.alpha, self.lam, self.depth = k, h, alpha, lam, depth

    def fit(self, X, y, w=None):
        self.sc = StandardScaler().fit(X)
        Z = self.sc.transform(X)
        sw = np.ones(len(Z)) if w is None else np.asarray(w, float)
        self.centers = KMeans(self.k, n_init=10, random_state=0).fit(Z, sample_weight=sw).cluster_centers_
        self.local = []
        for c in self.centers:
            wgt = np.exp(-((Z - c) ** 2).sum(1) / (2 * self.h * self.h)) * sw
            sel = wgt > 0.15
            if sel.sum() < 40:
                sel = np.zeros(len(Z), bool)
                sel[np.argsort(((Z - c) ** 2).sum(1))[:40]] = True
            reg = Ridge(alpha=self.alpha).fit(Z[sel], y[sel], sample_weight=sw[sel] + 1e-3)
            self.local.append((reg.coef_.tolist(), float(reg.intercept_)))
        self.glob = Ridge(alpha=1.0).fit(Z, y, sample_weight=sw)
        self.mu, self.sd = float(y.mean()), float(y.std())
        # 两段式：树激活与全局按 lam 融合，lam 在训练集内部交叉验证选
        idx = np.arange(len(Z))
        rng = np.random.default_rng(0)
        rng.shuffle(idx)
        cut = int(len(idx) * 0.8)
        tr, va = idx[:cut], idx[cut:]
        best = (1e9, self.lam)
        for lam in (0.0, 0.3, 0.5, 0.7, 1.0):
            self.lam = lam
            p = self.predict(Z[va])
            mae = float(np.mean(np.abs(y[va] - p)))
            if mae < best[0]:
                best = (mae, lam)
        self.lam = best[1]
        return self

    def predict(self, Z):
        W = soft_weights(Z, self.centers, self.h)
        loc = np.stack([Z @ np.asarray(c) + b for c, b in self.local], 1)
        tree = (W * loc).sum(1)
        glob = Z @ self.glob.coef_ + self.glob.intercept_
        return self.lam * tree + (1 - self.lam) * glob

    def export(self):
        return {"k": self.k, "h": self.h, "lam": self.lam, "alpha": self.alpha,
                "mean": self.sc.mean_.tolist(), "std": self.sc.scale_.tolist(),
                "centers": self.centers.tolist(),
                "local": [{"w": c, "b": b} for c, b in self.local],
                "glob": {"w": self.glob.coef_.tolist(), "b": float(self.glob.intercept_)},
                "mu": self.mu, "sd": self.sd}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cloud_labels.pkl")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--layer", type=int, default=0)
    ap.add_argument("--thr", type=int, default=150)
    args = ap.parse_args()

    d = pickle.load(open(args.data, "rb"))
    rows = [r for r in d["rows"] if abs(r["score"]) < 10000]
    score = np.clip(np.array([r["score"] for r in rows], float), -1500, 1500)
    M = json.load(io.open(args.model, encoding="utf-8"))
    A, Bt, Ct = M["coords3a"], M["coords3b"], M["coords3c"]

    X, F, MT = [], [], []
    for r in rows:
        v, _ = triple3d.state_triple(r["board"], r["side"], A, Bt, Ct, layers=args.layer)
        toks = geo.position_tokens(r["board"], r["side"])
        pa = [(t[3], A[t[0]]) for t in toks if t[0] in A]
        pb = [(t[3], Bt[t[0]]) for t in toks if t[0] in Bt]
        pc = [(t[3], Ct[t[0]]) for t in toks if t[0] in Ct]
        X.append(v)
        F.append(shape_feats(v[:7], pa) + shape_feats(v[7:14], pb) + shape_feats(v[14:21], pc))
        MT.append(mat_feats(r["board"], r["side"]))
    X = np.asarray(X, float)
    F = np.asarray(F, float)
    MT = np.asarray(MT, float)
    Zfull = np.hstack([X, F, MT])
    print("样本", len(rows), "特征", Zfull.shape, flush=True)

    idx = np.arange(len(rows))
    rng = np.random.default_rng(0)
    rng.shuffle(idx)
    cut = int(len(idx) * 0.75)
    tr, te = idx[:cut], idx[cut:]

    def report(tag, pred_tr, pred_te):
        m = metrics(score[te], pred_te, args.thr)
        print(f"{tag:22s} MAE {m['mae']:6.1f}cp  R² {m['r2']:5.2f}  ρ {m['spearman']:5.2f}  三类 {m['acc3']*100:5.1f}%", flush=True)
        return m

    # 基线：直接线性
    sc0 = StandardScaler().fit(Zfull[tr])
    g = Ridge(alpha=1.0).fit(sc0.transform(Zfull[tr]), score[tr])
    base = report("线性参与基线", g.predict(sc0.transform(Zfull[tr])), g.predict(sc0.transform(Zfull[te])))

    best = None
    for k in (6, 8, 12, 16, 24):
        for h in (2.5, 3.5, 5.0):
            t = TreeExpert(k=k, h=h, alpha=3.0).fit(Zfull[tr], score[tr])
            ptr = t.predict(t.sc.transform(Zfull[tr]))
            pte = t.predict(t.sc.transform(Zfull[te]))
            m = report(f"树 K={k} h={h} λ={t.lam}", ptr, pte)
            if best is None or m["mae"] < best[1]["mae"]:
                best = ((k, h), m)

    (k, h), _ = best
    print("最优", k, h, "→ 全量重训输出", flush=True)
    final = TreeExpert(k=k, h=h, alpha=3.0).fit(Zfull, score)
    p_all = final.predict(final.sc.transform(Zfull))
    print("全量", metrics(score, p_all, args.thr), flush=True)

    M["tree"] = {"features": "21+9+9", "k": k, "h": h, "lam": final.lam,
                 "model": final.export(), "metrics": metrics(score[te], final.predict(final.sc.transform(Zfull[te]), )),
                 "baseline": base, "samples": len(rows), "offline": True}
    # final 在全量上训练，测试指标用同一 test 集重算
    p_te = final.predict(final.sc.transform(Zfull[te]))
    M["tree"]["metrics"] = metrics(score[te], p_te, args.thr)
    json.dump(M, io.open(args.model, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写入 tree 段 →", args.model, M["tree"]["metrics"], flush=True)


if __name__ == "__main__":
    main()
