"""在皮卡鱼 depth8 价值标签上重训 45 维激活树（几何输入不变）。"""
import io, json, pickle, pathlib, time
import numpy as np
from feats45 import feats45
from tree_winprob import TreeExpert, metrics

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/pika_values.pkl")
    ap.add_argument("--cache", default="data/value45_cache.npz")
    ap.add_argument("--model", default="model_triple.json")
    ap.add_argument("--out", default="model_value.json")
    ap.add_argument("--k", type=int, default=64)
    ap.add_argument("--h", type=float, default=3.5)
    ap.add_argument("--alpha", type=float, default=3.0)
    ap.add_argument("--lam", type=float, default=-1.0)
    ap.add_argument("--src", default="")
    args = ap.parse_args()

    rows = pickle.load(open(HERE / args.data, "rb"))
    print("标签样本", len(rows), flush=True)
    M = json.load(io.open(HERE / args.model, encoding="utf-8"))
    AC = (M["coords3a"], M["coords3b"], M["coords3c"])
    cache = HERE / args.cache
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        X, y = z["X"], z["y"]
        print("缓存", X.shape, flush=True)
    else:
        X = np.zeros((len(rows), 45), float); y = np.zeros(len(rows), float)
        t0 = time.time()
        for i, r in enumerate(rows):
            X[i] = feats45(r["board"], r["side"], *AC)
            y[i] = float(np.clip(r["cp"], -1500, 1500))
            if (i + 1) % 2000 == 0:
                print(f"  feat {i+1}/{len(rows)} {time.time()-t0:.0f}s", flush=True)
        np.savez(cache, X=X, y=y)
    if args.src:
        srcs = set(s.strip() for s in args.src.split(",") if s.strip())
        mask = np.array([r["src"] in srcs for r in rows])
        print("筛选来源", srcs, "样本", int(mask.sum()), flush=True)
        X, y = X[mask], y[mask]
    y = np.clip(y, -1500, 1500)
    n = len(y); rng = np.random.default_rng(20261116)
    idx = rng.permutation(n); ntr = int(n * 0.9)
    trn, tst = idx[:ntr], idx[ntr:]
    et = TreeExpert(k=args.k, h=args.h, alpha=args.alpha).fit(X[trn], y[trn])
    p = et.predict(et.sc.transform(X[tst]))
    m = metrics(y[tst], p, 150)
    print("留出", m, flush=True)
    final = TreeExpert(k=args.k, h=args.h, alpha=args.alpha).fit(X, y)
    M["tree"]["model"] = final.export()
    M["tree"]["features"] = "45"
    M["tree"]["k"] = args.k
    M["tree"]["metrics"] = m
    M["tree"]["samples"] = int(n)
    M["tree"]["source"] = "pika-depth8-45"
    json.dump(M, io.open(HERE / args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("写入", args.out, flush=True)


if __name__ == "__main__":
    main()
