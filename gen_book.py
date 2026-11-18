"""生成前 20 手的公共开局库（双方均用皮卡鱼 50ms 选招）。"""
import json
from pathlib import Path
import board as B
from cloud_label import fen_of
from match_pikafish import Pika, mv_to_uci
from battle import OPENINGS

HERE = Path(__file__).parent
book = {}
pika = Pika("movetime", 50)
for name, first in OPENINGS:
    b = B.initial_board()
    side = B.RED
    hist = []
    for (fx, fy, tx, ty) in first:
        key = fen_of(b, side)
        f, t = fy * 9 + fx, ty * 9 + tx
        book.setdefault(key, mv_to_uci(f * 100 + t))
        hist.append((f, t))
        B.apply_move(b, (f, t))
        side = -side
    # 固定开局两着也记入库
    for ply in range(2, 20):
        lg = B.gen_legal(b, side)
        if not lg:
            break
        key = fen_of(b, side)
        u, cp, dep = pika.best(key + " - - 0 1")
        mv = None
        for (f, t) in lg:
            if mv_to_uci(f * 100 + t) == u:
                mv = (f, t); break
        if mv is None:
            break
        if key not in book:
            book[key] = u
        B.apply_move(b, mv)
        side = -side
pika.close()
json.dump(book, open(HERE / "data/book.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("book positions", len(book))
