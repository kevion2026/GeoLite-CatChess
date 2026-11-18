"""把神经价值头权重封装成 engine3d.js 可加载的完整模型。"""
import io, json, pickle
from pathlib import Path

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
base = json.load(io.open(HERE / "model_value200_k128.json", encoding="utf-8"))
nn = json.load(io.open(HERE / "model_value_nn.json", encoding="utf-8"))
ck = pickle.load(open(HERE / "model_value_nn.pkl", "rb"))
sc = ck["scaler"]
t = base["tree"]
t["model"] = {
    "kind": "mlp",
    "layers": nn["layers"],
    "mlpMean": [round(float(x), 6) for x in sc.mean_],
    "mlpStd": [round(float(x), 6) for x in sc.scale_],
    "out_scale": nn["out_scale"],
    "mean": [0.0] * 45,
    "std": [1.0] * 45,
    "metrics": nn["metrics"],
}
t["k"] = "nn"
t["samples"] = 200000
t["source"] = "pika-movetime50-200k-nn-planes45"
json.dump(base, io.open(HERE / "model_value_nn.json", "w", encoding="utf-8"), ensure_ascii=False)
print("layers", [len(x["b"]) for x in nn["layers"]], "in", nn["in"], "mae", nn["metrics"]["mae"])
