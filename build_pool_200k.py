"""汇总去重局面，生成 20 万训练池（不足时用左右镜像补齐）。"""
import json
import pickle
import pathlib
import glob
import random

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
OUT = HERE / "data" / "positions_200k.pkl"


def add(rows, seen, board, side, src):
    k = (tuple(board), int(side))
    if k in seen:
        return 0
    seen.add(k)
    rows.append((list(board), int(side), src))
    return 1


def main():
    rows = []
    seen = set()
    p = pickle.load(open(HERE / "data/pgn_positions.pkl", "rb"))["positions"]
    for b, s in p:
        add(rows, seen, b, s, "pgn")
    print("pgn", len(rows), flush=True)

    r = pickle.load(open(HERE / "data/result_positions.pkl", "rb"))["rows"]
    for b, s, _res in r:
        add(rows, seen, b, s, "result")
    print("+result", len(rows), flush=True)

    ds = json.load(open(HERE / "data/battle_ds.json", encoding="utf-8"))
    for g in ds.get("games", []):
        for x in g.get("rows", []):
            add(rows, seen, x[0], x[1], "battle")
    print("+battle_ds", len(rows), flush=True)

    c = 0
    for f in sorted(glob.glob(str(HERE / "data/battle_logs/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for m in d.get("moves", []):
            if m.get("board") and m.get("side"):
                side = 1 if m["side"] == "red" else -1
                c += add(rows, seen, m["board"], side, "battle_log")
    print("+battle_logs", c, len(rows), flush=True)

    sp = HERE / "data/selfplay_positions.jsonl"
    if sp.exists():
        c = 0
        for line in sp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            c += add(rows, seen, d["b"], d["s"], "selfplay")
        print("+selfplay", c, len(rows), flush=True)

    # 去重后仍不足 20 万，用左右镜像补齐（board 横向翻转，side 取反）
    need = 200000 - len(rows)
    if need > 0:
        mirrors = []
        for b, s, src in rows:
            mb = [0] * 90
            for y in range(10):
                for x in range(9):
                    mb[y * 9 + (8 - x)] = -b[y * 9 + x]
            mirrors.append((mb, -s, src + "_mirror"))
        for b, s, src in mirrors:
            if need <= 0:
                break
            need -= add(rows, seen, b, s, src)
        print("+mirror", 200000 - len(rows) - need, len(rows), flush=True)

    if len(rows) > 200000:
        random.seed(20261116)
        rows = random.sample(rows, 200000)
    print("最终", len(rows), flush=True)
    pickle.dump(rows, open(OUT, "wb"))
    from collections import Counter
    print(Counter(r[2] for r in rows), flush=True)
    print("写入", OUT, flush=True)


if __name__ == "__main__":
    main()
