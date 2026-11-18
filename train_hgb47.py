"""训练 47 维（45 几何 + 张力/空洞）加权 HGB，并输出同口径指标。"""
import io, json, pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")


def main():
    z = np.load(HERE / "data/value47_cache_200k.npz", allow_pickle=True)
    X, y = z["X"], z["y"]
    rows = pickle.load(open(HERE / "data/pika_values_200k.pkl", "rb"))
    w = np.array([4.0 if r["src"] in {"pgn", "pgn_mirror", "result"} else
                  (0.5 if r["src"] == "selfplay" else
                   (0.25 if r["src"] == "battle_log" else 1.0)) for r in rows])
    n = len(y)
    idx = np.random.default_rng(20261116).permutation(n)
    tr, te = idx[:int(n * .9)], idx[int(n * .9):]
    m = HistGradientBoostingRegressor(max_iter=600, learning_rate=.12, max_leaf_nodes=63,
                                      l2_regularization=1.0, random_state=0).fit(
        X[tr], y[tr], sample_weight=w[tr])
    p = m.predict(X[te])
    met = dict(mae=round(float(np.mean(np.abs(y[te] - p))), 1),
               r2=round(float(1 - ((y[te] - p) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum()), 3),
               n=int(n), test=int(len(te)))
    print("HGB47", met, flush=True)
    pickle.dump({"model": m, "metrics": met}, open(HERE / "model_value_hgb47.pkl", "wb"))
    (HERE / "data/hgb47_metrics.json").write_text(json.dumps(met, ensure_ascii=False), encoding="utf-8")
    print("saved model_value_hgb47.pkl", flush=True)


if __name__ == "__main__":
    main()
