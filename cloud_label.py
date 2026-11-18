"""从象棋云库抓「局面评分」，作为判断胜率的专用训练数据。

云库 chessdb.php?action=queryscore 返回 eval:<分值>，走子方视角。
"""

import argparse
import io
import json
import pickle
import time
import urllib.parse
import urllib.request

import board as B

LETTER = {B.KING: 'k', B.ADVISOR: 'a', B.ELEPHANT: 'b', B.HORSE: 'n',
          B.ROOK: 'r', B.CANNON: 'c', B.PAWN: 'p'}


def fen_of(board_, side):
    """标准中国象棋 FEN：第一行是黑方底线（本工程 y=0），最后一行红方底线（y=9）。"""
    rows = []
    for y in range(0, 10):
        row, empty = "", 0
        for x in range(9):
            p = board_[y * 9 + x]
            if p == 0:
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            ch = LETTER[abs(p)]
            row += ch.upper() if p > 0 else ch
        if empty:
            row += str(empty)
        rows.append(row)
    return '/'.join(rows) + (' w' if side == B.RED else ' b')


def query(fen, timeout=10):
    url = ('https://www.chessdb.cn/chessdb.php?action=queryscore&board='
           + urllib.parse.quote(fen, safe='/'))
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'GeoLite/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode('utf-8', 'replace').replace('\x00', '').strip()
    except Exception as e:                     # 网络抖动就跳过，不算失败样本
        return None, 'err:' + type(e).__name__
    if txt.startswith('eval:'):
        return int(txt.split(':')[1]), txt
    return None, txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=4000)
    ap.add_argument("--out", default="data/cloud_labels.pkl")
    ap.add_argument("--sleep", type=float, default=0.05)
    args = ap.parse_args()

    d = pickle.load(open("data/pgn_positions.pkl", "rb"))
    pos = d["positions"]
    import numpy as np
    rng = np.random.default_rng(11)
    idx = rng.choice(len(pos), size=min(args.max, len(pos)), replace=False)

    rows, ok, miss = [], 0, 0
    t0 = time.time()
    for n, i in enumerate(idx):
        b, s = pos[int(i)]
        fen = fen_of(b, s)
        score, raw = query(fen)
        if score is None:
            miss += 1
        else:
            ok += 1
            rows.append({"fen": fen, "board": tuple(int(x) for x in b), "side": int(s),
                         "score": score})
        if n % 200 == 0:
            print(f"{n}/{len(idx)} 命中 {ok} 缺失 {miss} {time.time()-t0:.0f}s", flush=True)
        time.sleep(args.sleep)
    pickle.dump({"rows": rows, "ok": ok, "miss": miss, "asked": len(idx)},
                open(args.out, "wb"))
    print("完成 命中", ok, "缺失", miss, "→", args.out, f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
