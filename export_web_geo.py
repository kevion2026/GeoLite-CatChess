# 从 geo45.h 导出前端可视化用的紧凑 JSON。
# 只在浏览器侧做特征复算与专家门控展示，不参与引擎决策，所以浮点保留 4 位即可。
import json
import re
import sys

SRC = "geo45.h"
OUT = "web/geo_model.js"


def grab(name):
    txt = open(SRC, "r", encoding="utf-8").read()
    m = re.search(r"static const \w+ " + name + r"\[[^\]]*\]\s*=\s*\{(.*?)\};", txt, re.S)
    if not m:
        raise SystemExit("找不到数组 " + name)
    return [float(x) for x in re.findall(r"-?\d+\.?\d*", m.group(1))]


def grab_scalar(name):
    txt = open(SRC, "r", encoding="utf-8").read()
    m = re.search(r"static const \w+ " + name + r"\s*=\s*(-?\d+\.?\d*)", txt)
    if not m:
        raise SystemExit("找不到常量 " + name)
    return float(m.group(1))


def main():
    txt = open(SRC, "r", encoding="utf-8").read()
    ints = {}
    for name in ("GEO_DIM", "GEO_STRIDE", "GEO_K", "GEO_NVEC"):
        m = re.search(r"static const int " + name + r"\s*=\s*(\d+)", txt)
        ints[name] = int(m.group(1))

    slot = [int(x) for x in re.findall(r"-?\d+", re.search(
        r"GEO_SLOT\[1260\]\s*=\s*\{(.*?)\};", txt, re.S).group(1))]
    xyz = grab("GEO_XYZ")
    mean = grab("GEO_MEAN")
    std = grab("GEO_STD")
    cn = grab("GEO_CN")
    lw = grab("GEO_LW")
    lb = grab("GEO_LB")
    gw = grab("GEO_GW")
    gb = grab_scalar("GEO_GB")
    h = grab_scalar("GEO_H")
    hs = grab_scalar("GEO_HSCALE")
    lam = grab_scalar("GEO_LAM")

    dim, stride, k, nvec = (ints["GEO_DIM"], ints["GEO_STRIDE"],
                            ints["GEO_K"], ints["GEO_NVEC"])
    assert len(slot) == 1260, len(slot)
    assert len(xyz) == nvec * 9, (len(xyz), nvec * 9)
    # MEAN/STD 导出时按补齐后的 STRIDE 长度写（后 3 位是占位），只用前 dim 维
    assert len(mean) == stride and len(std) == stride, (len(mean), len(std))
    assert len(cn) == k * stride and len(lw) == k * stride
    assert len(lb) == k and len(gw) == stride

    r = lambda a, n=4: [round(v, n) for v in a]
    out = {
        "dim": dim, "stride": stride, "k": k, "nvec": nvec,
        "h": h, "hScale": hs, "lam": lam, "gb": gb,
        "slot": slot,
        "xyz": r(xyz),
        "mean": r(mean, 5), "std": r(std, 5),
        "cn": r(cn), "lw": r(lw), "lb": r(lb), "gw": r(gw),
    }
    import os
    os.makedirs("web", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        # 输出成 JS 而不是纯 JSON：<script src> 在 file:// 下也能加载，双击页面即可看几何视图
        f.write("/* 自动生成：export_web_geo.py ← geo45.h。仅供前端复算与可视化，勿手改。 */\n")
        f.write("window.GEO_MODEL=")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print("写出 %s，%.1f KB" % (OUT, os.path.getsize(OUT) / 1024.0))
    print("dim=%d stride=%d K=%d nvec=%d h=%.2f hScale=%.2f lam=%.2f" %
          (dim, stride, k, nvec, h, hs, lam))


if __name__ == "__main__":
    sys.exit(main())
