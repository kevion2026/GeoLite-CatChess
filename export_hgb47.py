"""把 47 维 HGB 导出成 engine3d.js 的扁平数组。"""
import io
import json
import pickle
from pathlib import Path

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
base = json.load(io.open(HERE / "model_value200_k128.json", encoding="utf-8"))
m = pickle.load(open(HERE / "model_value_hgb47.pkl", "rb"))["model"]
f, th, left, right, val, leaf, off = [], [], [], [], [], [], [0]
for stage in m._predictors:
    n = stage[0].nodes
    base_i = len(val)
    for node in n:
        if node["is_leaf"]:
            f.append(-1); th.append(0.0); left.append(0); right.append(0); leaf.append(1)
        else:
            f.append(int(node["feature_idx"])); th.append(float(node["num_threshold"]))
            left.append(base_i + int(node["left"])); right.append(base_i + int(node["right"])); leaf.append(0)
        val.append(round(float(node["value"]), 3))
    off.append(len(val))
hgb = {"base": round(float(m._baseline_prediction.ravel()[0]), 3),
       "n": len(m._predictors), "f": f, "th": th, "left": left, "right": right,
       "val": val, "leaf": leaf, "off": off}
t = base["tree"]
old_mean = list(t["model"]["mean"])
old_std = list(t["model"]["std"])
t["model"] = {"kind": "hgb", "hgb": hgb,
              "mean": old_mean + [0.0, 0.0],
              "std": old_std + [1.0, 1.0],
              "metrics": {"mae_200k": 0.0, "features": 47}}
t["k"] = "hgb47"
t["samples"] = 200000
t["features"] = "47"
t["source"] = "pika-movetime50-200k-hgb47-tension"
# 指标回填
met = json.load(io.open(HERE / "data/hgb47_metrics.json", encoding="utf-8"))
t["model"]["metrics"] = {"mae_200k": met["mae"], "r2": met["r2"], "features": 47}
json.dump(base, io.open(HERE / "model_value_hgb47.json", "w", encoding="utf-8"), ensure_ascii=False)
print("trees", hgb["n"], "nodes", len(val), "json ok", "mae", met["mae"])
