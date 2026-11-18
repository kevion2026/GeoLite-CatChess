"""配对比较两份基准结果：同一批局面下的 CPL 差值与 bootstrap 置信区间。

为什么需要它：残局 CPL 的分布极重尾（p90 常到 600），单次 160 局面的均值标准误约 20cp，
直接用均值比大小会被噪声骗。配对差值把「局面难度」这个共同项消掉，方差大幅下降。

用法：
  python cmp_bench.py data/scr_eg_n40k.json
  python cmp_bench.py data/a.json data/b.json --base CatChess-v1.0pro-preview.exe
"""
import argparse
import json
import random
import statistics


def load(paths):
    rows, groups = [], []
    for p in paths:
        rows += json.load(open(p, encoding="utf-8"))
    seen = set()
    for r in rows:
        k = (r["engine"], r.get("nodes", 0), r.get("depth", 0), r.get("ms", 0), r["n"])
        if k in seen:
            continue
        seen.add(k)
        groups.append(r)
    return groups


def paired(a, b, cap=None):
    ka = a.get("cpl_by_pos") or {}
    kb = b.get("cpl_by_pos") or {}
    keys = sorted(set(ka) & set(kb))
    if cap:
        d = [min(ka[k], cap) - min(kb[k], cap) for k in keys]
    else:
        d = [ka[k] - kb[k] for k in keys]
    return keys, d


def paired_rate(a, b, thr=50):
    """好着率之差：CPL<=thr 记为 1。二值量的方差远小于重尾 CPL，判别力更强。"""
    ka = a.get("cpl_by_pos") or {}
    kb = b.get("cpl_by_pos") or {}
    keys = sorted(set(ka) & set(kb))
    d = [(1 if ka[k] <= thr else 0) - (1 if kb[k] <= thr else 0) for k in keys]
    return keys, d


def boot_ci(d, n=4000, seed=7):
    rng = random.Random(seed)
    m = len(d)
    means = []
    for _ in range(n):
        means.append(sum(d[rng.randrange(m)] for _ in range(m)) / m)
    means.sort()
    return means[int(n * 0.025)], means[int(n * 0.975)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--base", default=None, help="对照组引擎名，默认第一行")
    args = ap.parse_args()

    groups = load(args.files)
    if not groups:
        print("无数据")
        return
    base = None
    for g in groups:
        if args.base and g["engine"] == args.base:
            base = g
    if base is None:
        base = groups[0]

    print("口径：nodes=%s depth=%s ms=%s  局面数 %d" %
          (base.get("nodes"), base.get("depth"), base.get("ms"), base["n"]))
    print("%-32s %8s %8s %9s %9s  %s" %
          ("引擎", "CPL均值", "vs基准", "95%CI下", "95%CI上", "结论"))
    for g in groups:
        if g is base:
            print("%-32s %8.1f %8s %9s %9s  基准" % (g["engine"], g["cpl_mean"], "-", "-", "-"))
            continue
        keys, d = paired(g, base)
        if not d:
            print("%-32s %8.1f   无逐局面数据" % (g["engine"], g["cpl_mean"]))
            continue
        mean_d = statistics.mean(d)
        lo, hi = boot_ci(d)
        verdict = "更快" if hi < 0 else ("更慢" if lo > 0 else "持平")
        # 截断均值：>300 的着法一律按 300 计，压掉重尾
        _, dc = paired(g, base, cap=300)
        loc, hic = boot_ci(dc)
        vc = "更快" if hic < 0 else ("更慢" if loc > 0 else "持平")
        # 好着率（CPL<=50）
        _, dr = paired_rate(g, base, 50)
        r = 100 * statistics.mean(dr)
        lor, hir = boot_ci(dr)
        vr = "更高" if lor > 0 else ("更低" if hir < 0 else "持平")
        print("%-30s %7.1f %+7.1f [%+6.1f,%+6.1f] %-4s | 截断 %+6.1f [%+6.1f,%+6.1f] %-4s | 好着率 %+5.1fpp %-4s" %
              (g["engine"], g["cpl_mean"], mean_d, lo, hi, verdict,
               statistics.mean(dc), loc, hic, vc, r, vr))


if __name__ == "__main__":
    main()
