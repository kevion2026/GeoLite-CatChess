"""在同一验证集上比较旧树（geo45.h）与新树（model_geo_v2*.json）。"""
import json, sys, pathlib
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diag_heads as D

def load_new(path):
    m = json.load(open(path, encoding="utf-8"))
    K = m["k"]; S = 48
    C = np.array(m["centers"])
    Wm = np.array([l["w"] for l in m["local"]])
    B = np.array([l["b"] for l in m["local"]])
    gw = np.array(m["glob"]["w"]); gb = float(m["glob"]["b"])
    mu = np.array(m["mean"]); sd = np.array(m["std"])
    return dict(C=C, Wm=Wm, B=B, gw=gw, gb=gb, mu=mu, sd=sd,
                h=m["h"], hscale=m.get("hScale", 2.5), lam=m["lam"])

def score_new(X, m):
    Z = np.zeros((len(X), 48))
    Z[:, :45] = (X - m["mu"]) / m["sd"]
    inv = 1.0 / (2 * m["h"] ** 2 * m["hscale"] ** 2)
    zn = (Z ** 2).sum(1); cn = (m["C"] ** 2).sum(1)
    d2 = np.maximum(zn[:, None] - 2 * Z @ m["C"].T + cn[None, :], 0)
    W = np.exp(-d2 * inv)
    sw = np.maximum(W.sum(1), 1e-9)
    tree = (W * (m["B"][None, :] + Z @ m["Wm"].T)).sum(1) / sw
    glob = m["gb"] + Z @ m["gw"]
    return m["lam"] * tree + (1 - m["lam"]) * glob

z = np.load(HERE / "data/value45_cache_200k.npz")
X, y = z["X"], z["y"]
n = len(y); nval = int(n * 0.12)
rng = np.random.default_rng(1234); perm = rng.permutation(n)
vi, ti = perm[:nval], perm[nval:]

g = D.load_geo()
old = D.geo_scores(X, g)
new = score_new(X, load_new(HERE / "model_geo_v2_k128.json"))

def rep(name, p, idx):
    yy = y[idx]; pp = p[idx]
    for tag, m in (("all", np.ones(len(yy), bool)), ("|y|<150", np.abs(yy) < 150), ("|y|>600", np.abs(yy) > 600)):
        e = np.abs(pp[m] - yy[m])
        print("  %-10s %-8s n=%6d MAE %6.1f" % (name, tag, m.sum(), e.mean()))

print("验证集（24k）：")
rep("旧树 geo45", old, vi)
rep("新树 k128", new, vi)
print("训练集（176k）：")
rep("旧树 geo45", old, ti)
rep("新树 k128", new, ti)
