"""导出增强线性模型（平面 + 8 个几何特征）为 C++ 头文件。"""
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent
d = np.load(HERE / "data/linear_aug.npz")
SCALE = 2.3
w = d["w"].astype(np.float32).reshape(14, 90) * SCALE
wf = d["wf"].astype(np.float32) * SCALE
b = float(d["b"]) * SCALE

lines = ["// 由 train_linear_aug.py 自动生成：线性棋子平面 + 8 个几何特征（×2.3）",
         "static const float LB = %.6ff;" % b,
         "static const float LW[14][90] = {"]
for ch in range(14):
    vals = ", ".join("%.6ff" % v for v in w[ch])
    lines.append("  {%s}%s" % (vals, "," if ch < 13 else ""))
lines.append("};")
lines.append("static const float WF[8] = {%s};" % ", ".join("%.6ff" % v for v in wf))
out = HERE / "linear_weight_aug.h"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", out.name, len(lines), "bias", b, "wf", wf.round(3).tolist())
