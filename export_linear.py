"""把线性平面价值模型导出为 C++ 头文件（14×90 权重 + 偏置）。"""
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent
d = np.load(HERE / "data/linear_planes.npz")
w = d["w"].astype(np.float32).reshape(14, 90) * 2.3
b = float(d["b"]) * 2.3

out = ["// 由 train_linear_planes.py 自动生成：200k 皮卡鱼标签的线性棋子平面模型",
       "static const float LW[14][90] = {"]
for ch in range(14):
    vals = ", ".join(f"{v:.3f}" for v in w[ch])
    out.append(f"  {{{vals}}},")
out.append("};")
out.append(f"static const float LB = {b:.3f};")
(HERE / "linear_weight.h").write_text("\n".join(out) + "\n", encoding="utf-8")
print("wrote linear_weight.h", (HERE / "linear_weight.h").stat().st_size)
