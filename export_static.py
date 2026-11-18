"""导出静态评估线性模型（平面权重 ×2.0，几何特征权重置零）。"""
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent
d = np.load(HERE / "data/linear_static.npz")
SCALE = 2.0
w = d["w"].astype(np.float32).reshape(14, 90) * SCALE
b = float(d["b"]) * SCALE
lines = ["// 由 train_static.py 自动生成：Pikafish NNUE 静态评估的线性平面模型（×2.0）",
         "static const float LB = %.6ff;" % b,
         "static const float LW[14][90] = {"]
for ch in range(14):
    vals = ", ".join("%.6ff" % v for v in w[ch])
    lines.append("  {%s}%s" % (vals, "," if ch < 13 else ""))
lines.append("};")
lines.append("static const float WF[8] = {0, 0, 0, 0, 0, 0, 0, 0};")
out = HERE / "linear_weight_static.h"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", out.name, "bias", b)
