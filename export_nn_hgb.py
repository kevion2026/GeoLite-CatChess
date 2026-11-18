"""导出 NN + HGB 混合评估模型：神经分与几何树分按权重融合。"""
import io, json
from pathlib import Path

HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
nn = json.load(io.open(HERE / "model_value_nn.json", encoding="utf-8"))
hgb = json.load(io.open(HERE / "model_value_hgb.json", encoding="utf-8"))
m = nn["tree"]["model"]
m["kind"] = "blend"
m["hgb"] = hgb["tree"]["model"]["hgb"]
m["mix"] = 0.7
m["metrics"] = {"nn_mae": 160.6, "hgb_mae": 192.3, "mix": 0.7}
nn["tree"]["k"] = "nn_hgb"
nn["tree"]["source"] = "pika-movetime50-200k-nn+hgb"
json.dump(nn, io.open(HERE / "model_value_nn_hgb.json", "w", encoding="utf-8"), ensure_ascii=False)
print("saved trees", m["hgb"]["n"])
