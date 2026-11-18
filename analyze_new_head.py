"""新价值头的落地检查：尺度标定、分档 MAE、子力单调性。

三件事：
  1) 尺度：新模型输出幅度和旧融合分（65% 几何树 + 35% 平面）的比值，
     决定 C++ 里 MLP_SCALE 取多少，才能让剪枝阈值仍然成立；
  2) 分档：中局 + 残局验证集的 MAE，逐 |y| 桶、逐子力档；
  3) 单调性：按「行棋方净子力优势」分档，预测均值应随优势单调上升。
"""
import argparse
import io
import json

import numpy as np

import diag_heads as D
from eval_endgame_head import MATV, mlp_forward, report


def load_pair(path):
    z = np.load(path)
    return z["X"].astype(np.float32), z["y"].astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--mid", default="data/value45_cache_200k.npz")
    ap.add_argument("--mid-plane", default="data/heads_200k.npz")
    ap.add_argument("--eg", default="data/eg_cache.npz")
    ap.add_argument("--val", type=float, default=0.12)
    args = ap.parse_args()

    m = json.load(io.open(args.model, encoding="utf-8"))
    Xm, ym = load_pair(args.mid)
    plm = np.load(args.mid_plane)["plane"].astype(np.float32)
    ze = np.load(args.eg)
    Xe, ye, ple, adv = (ze["X"].astype(np.float32), ze["y"].astype(np.float32),
                        ze["plane"].astype(np.float32), ze["adv"].astype(np.float32))

    # 只取验证切分（与训练脚本同一切法）
    rng = np.random.default_rng(1234)
    perm = rng.permutation(len(ym))
    nval = int(len(ym) * args.val)
    vm = perm[:nval]
    rng2 = np.random.default_rng(99)
    perm2 = rng2.permutation(len(ye))
    nval2 = int(len(ye) * args.val)
    ve = perm2[:nval2]

    def pred(X, pl):
        return mlp_forward(m, np.hstack([X, (pl / 200.0)[:, None]]).astype(np.float32))

    pm, pe = pred(Xm[vm], plm[vm]), pred(Xe[ve], ple[ve])
    yvm, yve = ym[vm], ye[ve]

    g = D.load_geo()
    old = (65 * D.geo_scores(Xm[vm], g) + 35 * plm[vm]) / 100.0
    print("\n=== 尺度标定 ===")
    print("旧融合分 sd %.1f   新模型 sd %.1f   比值 %.3f"
          % (np.std(old), np.std(pm), np.std(pm) / np.std(old)))
    c = np.polyfit(pm, old, 1)
    print("old ≈ %.3f·pred %+.1f  → 对齐旧尺度需 MLP_SCALE ≈ %.3f"
          % (c[0], c[1], 1.0 / c[0] if abs(c[0]) > 1e-6 else float("nan")))
    for s in (0.6, 0.7, 0.75, 0.85, 1.0):
        print("  scale %.2f  中局 MAE %6.1f  残局 MAE %6.1f"
              % (s, np.abs(pm * s - yvm).mean(), np.abs(pe * s - yve).mean()))

    print("\n=== 中局验证集 ===")
    print("n=%d MAE %.1f  corr %.4f  同号 %.1f%%"
          % (len(yvm), np.abs(pm - yvm).mean(), np.corrcoef(pm, yvm)[0, 1],
             100 * np.mean(np.sign(pm) == np.sign(yvm))))
    for lo, hi in [(0, 150), (150, 400), (400, 800), (800, 1e9)]:
        k = (np.abs(yvm) >= lo) & (np.abs(yvm) < hi)
        if k.sum():
            print("  |y| %4d-%4d n=%6d MAE %6.1f 偏差 %+6.1f"
                  % (lo, hi, k.sum(), np.abs(pm[k] - yvm[k]).mean(),
                     (pm[k] - yvm[k]).mean()))

    report("残局验证集", pe, yve, adv[ve])

    print("\n=== 子力单调性（残局验证集）===")
    a = adv[ve]
    for lo, hi in [(-9000, -1500), (-1500, -600), (-600, -200), (-200, 200),
                   (200, 600), (600, 1500), (1500, 9000)]:
        k = (a >= lo) & (a < hi)
        if k.sum():
            print("  净子力 %+5d~%+5d  n=%5d  预测均值 %+7.1f  标签均值 %+7.1f"
                  % (lo, hi, k.sum(), pe[k].mean(), yve[k].mean()))


if __name__ == "__main__":
    main()
