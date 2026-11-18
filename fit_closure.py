"""导出样本 → node 计算几何树分与闭合项 → 纯 python 岭回归标定闭合层权重。

用法：
  python fit_closure.py export      # 写 data/fit_rows.json
  node fit_closure_probe.js         # 写 data/fit_terms.json
  python fit_closure.py fit         # 拟合权重
"""
import json
import pathlib
import pickle
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROWS = HERE / "data" / "fit_rows.json"
TERMS = HERE / "data" / "fit_terms.json"

NAMES = ["mat", "kdanger", "guard", "rook", "horse", "pawn"]


def export():
    d = pickle.load(open(HERE / "data" / "battle_labels_all.pkl", "rb"))
    out = []
    for r in d["rows"]:
        out.append({"b": [int(v) for v in r["board"]], "s": int(r["side"]),
                    "y": float(r["score"]), "g": str(r["game"]), "p": int(r["ply"])})
    ROWS.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("rows", len(out), "games", len({r['g'] for r in out}))


def solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            continue
        M[i], M[p] = M[p], M[i]
        piv = M[i][i]
        for j in range(i, n + 1):
            M[i][j] /= piv
        for r in range(n):
            if r == i:
                continue
            f = M[r][i]
            if f:
                for j in range(i, n + 1):
                    M[r][j] -= f * M[i][j]
    return [M[i][n] for i in range(n)]


def fit():
    data = json.loads(TERMS.read_text(encoding="utf-8"))
    games = sorted({d["g"] for d in data})
    hold = {g for i, g in enumerate(games) if i % 4 == 0}
    tr = [d for d in data if d["g"] not in hold]
    te = [d for d in data if d["g"] in hold]
    print(f"train {len(tr)} / test {len(te)}  (hold-out {len(hold)} games)")

    def design(rows):
        X, y = [], []
        for d in rows:
            f = d["c"]
            X.append([1.0] + list(f) + [d["t"]])
            y.append(d["y"] - d["t"])
        return X, y

    X, y = design(tr)
    n = len(X[0])
    lam = 1e-3
    A = [[0.0] * n for _ in range(n)]
    Bv = [0.0] * n
    for row, t in zip(X, y):
        for i in range(n):
            Bv[i] += row[i] * t
            for j in range(n):
                A[i][j] += row[i] * row[j]
    # 只惩罚闭合项（不含截距与树的交互项）
    for i in range(1, n - 1):
        A[i][i] += lam * len(X)
    w = solve(A, Bv)

    def mae(rows, w):
        s = 0.0
        for d in rows:
            pred = d["t"] + w[0] + sum(w[1 + i] * d["c"][i] for i in range(len(d["c"]))) + w[-1] * d["t"]
            s += abs(pred - d["y"])
        return s / len(rows)

    base_tr = sum(abs(d["t"] - d["y"]) for d in tr) / len(tr)
    base_te = sum(abs(d["t"] - d["y"]) for d in te) / len(te)
    print(f"\n几何树单独       train MAE {base_tr:7.2f}   test MAE {base_te:7.2f}")
    print(f"树 + 闭合校正     train MAE {mae(tr, w):7.2f}   test MAE {mae(te, w):7.2f}")
    print(f"\n截距 {w[0]:+.2f}   树增益 {w[-1]:+.3f}")
    for i, nm in enumerate(NAMES):
        print(f"  w[{nm:8}] = {w[1+i]:+.4f}")
    print("\n建议闭包权重（按项量纲换算，闭合项本身已是 cp）：")
    print("closure = [" + ", ".join(f"{w[1+i]:.4f}" for i in range(len(NAMES))) + "]")
    (HERE / "data" / "closure_w.json").write_text(
        json.dumps({"w": [w[1 + i] for i in range(len(NAMES))], "bias": w[0],
                    "tree_gain": w[-1], "mae_tree": base_te, "mae_fit": mae(te, w)},
                   ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    (export if (len(sys.argv) < 2 or sys.argv[1] == "export") else fit)()
