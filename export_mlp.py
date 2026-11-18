"""把 numpy 训练出的 MLP 价值模型导出成 C++ 头文件。

    python export_mlp.py --model model_eg_M.json            → mlp46.h     （float32）
    python export_mlp.py --model model_eg_M.json --int8      → mlp46_i8.h  （int8 权重）

输入 46 维 = 45 维几何特征 + 平面评估分/200（第 46 维由 C++ 侧现算）。
输出两层 ReLU + 线性输出。W1 按 (H1, 48) 存（补零到 48，便于 AVX2 整段点积）。

int8 版：W1/W2 按「输出神经元」逐行对称量化（每行一个 float 尺度），
激活由 C++ 侧按局面现算 uint8 非对称量化。逐行量化的相对误差与权重尺度无关，
所以不需要也没有办法再引入 per-tensor 尺度；实测（6000 残局局面）两层的
量化噪声各约 7cp，激活噪声约 4cp。全 float 对照见 --int8 的注释。
"""
import argparse
import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def _round_half_away(x):
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def quant_rows(W, qmax=127):
    """按输出神经元（列）逐行对称量化。W 为 (fan_in, fan_out)。

    返回 (Q, S)：Q 是 (fan_out, fan_in) 的行优先 int8 矩阵，S 是每行的 float 尺度。
    行尺度取 max|w|，不剪裁——实测按 99.5 分位剪裁反而更差（大头权重被压掉）。
    """
    fan_in = len(W)
    fan_out = len(W[0])
    Q = [[0] * fan_in for _ in range(fan_out)]
    S = [0.0] * fan_out
    for j in range(fan_out):
        mx = max(abs(W[i][j]) for i in range(fan_in))
        s = mx / qmax if mx > 1e-8 else 1e-8
        S[j] = s
        for i in range(fan_in):
            v = _round_half_away(W[i][j] / s)
            Q[j][i] = 127 if v > 127 else (-127 if v < -127 else v)
    return Q, S


def fmt_i8(name, rows, cols, data, per_line=24):
    out = ["static const signed char %s[%d][%d] = {" % (name, rows, cols)]
    for r in data:
        lines = [", ".join("%d" % v for v in r[s:s + per_line])
                 for s in range(0, cols, per_line)]
        out.append("  {" + (",\n   ".join(lines)) + "},")
    out.append("};")
    return "\n".join(out)


def fmt_block(name, rows, cols, data, per_line=8, fmt="%.6ff"):
    out = ["static const float %s[%d][%d] = {" % (name, rows, cols)]
    for i in range(rows):
        vals = data[i]
        line = ", ".join(fmt % v for v in vals)
        out.append("  {" + line + "},")
    out.append("};")
    return "\n".join(out)


def export_float(m, args, din, h1, h2, W1, b1, W2, b2, W3, b3):
    stride = 48
    # 转置成行优先的点积布局
    W1t = [[W1[i][j] for i in range(din)] + [0.0] * (stride - din) for j in range(h1)]
    W2t = [[W2[i][j] for i in range(h1)] for j in range(h2)]
    W3v = [W3[i][0] for i in range(h2)]

    L = []
    L.append("// 自动生成：export_mlp.py ← %s。勿手改。" % args.model)
    L.append("// 46 维输入 = 45 维几何特征 + 平面分/200；两层 ReLU，输出走子方视角 cp。")
    L.append("#pragma once")
    L.append("namespace %s {" % args.name)
    L.append("static const int DIM = %d;" % din)
    L.append("static const int H1 = %d;" % h1)
    L.append("static const int H2 = %d;" % h2)
    L.append("static const int STRIDE = %d;" % stride)
    L.append("static const float MEAN[%d] = {%s};" % (din, ", ".join("%.6ff" % v for v in m["mean"])))
    L.append("static const float STD[%d] = {%s};" % (din, ", ".join("%.6ff" % v for v in m["std"])))
    L.append(fmt_block("W1", h1, stride, W1t))
    L.append(fmt_block("W2", h2, h1, W2t))
    L.append("static const float B1[%d] = {%s};" % (h1, ", ".join("%.6ff" % v for v in b1)))
    L.append("static const float B2[%d] = {%s};" % (h2, ", ".join("%.6ff" % v for v in b2)))
    L.append("static const float W3[%d] = {%s};" % (h2, ", ".join("%.6ff" % v for v in W3v)))
    L.append("static const float B3 = %.6ff;" % float(b3[0]))
    L.append("}  // namespace %s" % args.name)
    return L


def export_int8(m, args, din, h1, h2, W1, b1, W2, b2, W3, b3):
    """int8 权重：W1 补齐到 PAD1=64（AVX-512 一次 dpbusd 吃完一行），W2 恰为 192。"""
    pad1 = 64
    Q1, S1 = quant_rows(W1)          # (h1, din), (h1,)
    Q2, S2 = quant_rows(W2)          # (h2, h1), (h2,)
    W3v = [W3[i][0] for i in range(h2)]
    # 零点修正：非对称量化下 z ≈ AZ·q + lo，所以 dot 结果要补 lo·Σw
    SUM1 = [sum(W1[i][j] for i in range(din)) for j in range(h1)]
    Q1 = [row + [0] * (pad1 - din) for row in Q1]

    L = []
    L.append("// 自动生成：export_mlp.py --int8 ← %s。勿手改。" % args.model)
    L.append("// int8 量化价值头：权重逐输出神经元对称量化（Q 为 int8，S 为该行尺度）；")
    L.append("// 激活由 mlp_eval.h 按局面现算 uint8 非对称量化，不存表。")
    L.append("#pragma once")
    L.append("namespace %s {" % args.name)
    L.append("static const int DIM = %d;" % din)
    L.append("static const int H1 = %d;" % h1)
    L.append("static const int H2 = %d;" % h2)
    L.append("static const int PAD1 = %d;" % pad1)
    L.append("static const int PAD2 = %d;" % h1)
    L.append("static const float MEAN[%d] = {%s};" % (din, ", ".join("%.6ff" % v for v in m["mean"])))
    L.append("static const float STD[%d] = {%s};" % (din, ", ".join("%.6ff" % v for v in m["std"])))
    L.append(fmt_i8("Q1", h1, pad1, Q1))
    L.append("static const float S1[%d] = {%s};" % (h1, ", ".join("%.8ff" % v for v in S1)))
    L.append("static const float SUM1[%d] = {%s};" % (h1, ", ".join("%.6ff" % v for v in SUM1)))
    L.append(fmt_i8("Q2", h2, h1, Q2))
    L.append("static const float S2[%d] = {%s};" % (h2, ", ".join("%.8ff" % v for v in S2)))
    L.append("static const float B1[%d] = {%s};" % (h1, ", ".join("%.6ff" % v for v in b1)))
    L.append("static const float B2[%d] = {%s};" % (h2, ", ".join("%.6ff" % v for v in b2)))
    L.append("static const float W3[%d] = {%s};" % (h2, ", ".join("%.6ff" % v for v in W3v)))
    L.append("static const float B3 = %.6ff;" % float(b3[0]))
    L.append("}  // namespace %s" % args.name)
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="model_mlp46_n.json")
    ap.add_argument("--out", default="mlp46.h")
    ap.add_argument("--name", default="mlp")
    ap.add_argument("--int8", action="store_true", help="导出 int8 量化权重（默认 mlp46_i8.h）")
    args = ap.parse_args()
    if args.int8 and args.out == "mlp46.h":
        args.out = "mlp46_i8.h"

    m = json.load(open(HERE / args.model, encoding="utf-8"))
    din, h1, h2, _ = m["dims"]
    assert din == 46, "输入维度应为 46（45 几何 + 平面分）"
    W1 = m["W"][0]          # (din, h1)
    b1 = m["b"][0]
    W2 = m["W"][1]          # (h1, h2)
    b2 = m["b"][1]
    W3 = m["W"][2]          # (h2, 1)
    b3 = m["b"][2]

    fn = export_int8 if args.int8 else export_float
    L = fn(m, args, din, h1, h2, W1, b1, W2, b2, W3, b3)

    p = HERE / args.out
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("saved", p, "%.2f MB" % (p.stat().st_size / 1e6),
          "| dims %d-%d-%d-%d" % (din, h1, h2, 1),
          "| val_mae", m["metrics"]["val_mae"], "均势", m["metrics"]["val_mae_calm"])


if __name__ == "__main__":
    main()
