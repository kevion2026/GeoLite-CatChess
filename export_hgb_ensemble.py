"""把 HGB45(600×63) 与 HGB127(800×127) 平均成一个集成 HGB，供 engine3d 推理。"""
import io, json, pickle
from pathlib import Path

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
base = json.load(io.open(HERE / "model_value200_k128.json", encoding="utf-8"))


def flatten(path, weight):
    m = pickle.load(open(path, "rb"))["model"]
    f, th, left, right, val, leaf, off = [], [], [], [], [], [], [0]
    for stage in m._predictors:
        nodes = stage[0].nodes
        base_i = len(val)
        for node in nodes:
            if node["is_leaf"]:
                f.append(-1); th.append(0.0); left.append(0); right.append(0); leaf.append(1)
            else:
                f.append(int(node["feature_idx"])); th.append(float(node["num_threshold"]))
                left.append(base_i + int(node["left"])); right.append(base_i + int(node["right"])); leaf.append(0)
            val.append(round(float(node["value"]) * weight, 3))
        off.append(len(val))
    return {"base": float(m._baseline_prediction.ravel()[0]) * weight, "n": len(m._predictors),
            "f": f, "th": th, "left": left, "right": right, "val": val, "leaf": leaf, "off": off}


a = flatten(HERE / "model_value_hgb_w.pkl", 0.5)
b = flatten(HERE / "model_value_hgb127.pkl", 0.5)
# 合并两套树：偏移量整体后移
off = a["off"] + [x + a["off"][-1] for x in b["off"][1:]]
hgb = {"base": a["base"] + b["base"], "n": a["n"] + b["n"],
       "f": a["f"] + b["f"], "th": a["th"] + b["th"],
       "left": a["left"] + ([x + a["off"][-1] if x else 0 for x in b["left"]]),
       "right": a["right"] + ([x + a["off"][-1] if x else 0 for x in b["right"]]),
       "val": a["val"] + b["val"], "leaf": a["leaf"] + b["leaf"], "off": off}
t = base["tree"]
t["model"] = {"kind": "hgb", "hgb": hgb, "mean": t["model"]["mean"], "std": t["model"]["std"],
              "metrics": {"ensemble": "hgb45+hgb127"}}
t["k"] = "hgb_ens"
t["samples"] = 200000
t["source"] = "pika-movetime50-200k-hgb-ensemble"
json.dump(base, io.open(HERE / "model_value_hgb_ens.json", "w", encoding="utf-8"), ensure_ascii=False)
print("trees", hgb["n"], "nodes", len(hgb["val"]), "json ok")
