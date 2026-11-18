"""把 127 叶 HGB 导出成 engine3d.js 可推理模型。"""
import io, json, pickle
from pathlib import Path

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
base = json.load(io.open(HERE / "model_value200_k128.json", encoding="utf-8"))
m = pickle.load(open(HERE / "model_value_hgb127.pkl", "rb"))["model"]
met = pickle.load(open(HERE / "model_value_hgb127.pkl", "rb"))["metrics"]
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
mean = t["model"]["mean"]; std = t["model"]["std"]
t["model"] = {"kind": "hgb", "hgb": hgb, "mean": mean, "std": std,
              "metrics": {"mae_200k": met["mae"], "r2": met["r2"]}}
t["k"] = "hgb127"
t["samples"] = 200000
t["source"] = "pika-movetime50-200k-hgb127"
json.dump(base, io.open(HERE / "model_value_hgb127.json", "w", encoding="utf-8"), ensure_ascii=False)
print("trees", hgb["n"], "nodes", len(val), "mae", met["mae"], "json ok")
