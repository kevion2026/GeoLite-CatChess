"""统计败局里的子力曲线：判断是被吃子打崩，还是均势被将死。"""
import json, glob
from pathlib import Path

V = {1: 0, 2: 200, 3: 200, 4: 900, 5: 450, 6: 450, 7: 100}
HERE = Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋\data\battle_logs")


def mat(b, side):
    s = 0
    for p in b:
        if not p:
            continue
        s += (1 if p > 0 else -1) * side * V[abs(p)]
    return s


for f in sorted(glob.glob(str(HERE / "*mt50_g*.json")))[-12:]:
    d = json.load(open(f, encoding="utf-8"))
    ours = 1 if d["ours"] == "red" else -1
    track = []
    for p in d["moves"]:
        if (p["ply"] % 10) == 9:
            track.append(mat(p["board"], ours))
    print(Path(f).name, "plies", d["plies"], "mat@10..", track)
