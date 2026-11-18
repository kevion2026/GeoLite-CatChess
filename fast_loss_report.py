"""打印速败局棋谱，并统计死法：谁将的死、死在哪个区域。"""

import argparse
import glob
import json
import pathlib
from collections import Counter

import board as B

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
NAMES = {1: "帅/将", 2: "仕/士", 3: "相/象", 4: "车", 5: "马", 6: "炮", 7: "兵/卒"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="verify100b")
    ap.add_argument("--fast-loss", type=int, default=30)
    ap.add_argument("--out", default="data/fast_losses.md")
    args = ap.parse_args()

    games = []
    for path in sorted(glob.glob(str(HERE / "data" / "battle_logs" / f"{args.tag}_g*.json"))):
        g = json.loads(open(path, encoding="utf-8").read())
        if g["res"] == "loss" and g["plies"] <= args.fast_loss:
            games.append(g)

    killer, zone = Counter(), Counter()
    lines = [f"# {args.tag} 速败局清单（≤{args.fast_loss} 着）", "", f"共 {len(games)} 局。", ""]
    for g in games:
        last = g["moves"][-1]
        b = last.get("board")
        mv = int(last["uci"][0:2]) if False else None
        # 末着皮卡鱼的着法：从最后局面的镜像推回上一手
        prev = g["moves"][-2] if len(g["moves"]) > 1 else None
        if prev and prev.get("board"):
            bb = prev["board"]
            # 找到 uci 对应的起点与终点
            f = "abcdefghi".index(last["uci"][0]) + (9 - int(last["uci"][1])) * 9
            t = "abcdefghi".index(last["uci"][2]) + (9 - int(last["uci"][3])) * 9
            pc = bb[f]
            killer[NAMES.get(abs(pc), "?")] += 1
            x, y = t % 9, t // 9
            zone["九宫" if 3 <= x <= 5 and (y <= 2 or y >= 7) else ("肋道" if x in (3, 5) else "边线")] += 1
        moves = " ".join(p["uci"] for p in g["moves"])
        lines.append(f"## 第 {g['game']} 局 · {g['opening']} · {g['plies']} 着 · 我执{'红' if g['ours'] == 'red' else '黑'}")
        lines.append("")
        lines.append(f"`{moves}`")
        lines.append("")
        if g["moves"][-1].get("cp") is not None:
            lines.append(f"末着皮卡鱼评分 {g['moves'][-1]['cp']} cp")
            lines.append("")

    lines += ["## 死法统计", "",
              "- 绝杀子力：" + "、".join(f"{k} {v} 局" for k, v in killer.most_common()) if killer else "- 无",
              "- 绝杀落点：" + "、".join(f"{k} {v} 局" for k, v in zone.most_common()) if zone else "- 无",
              ""]
    pathlib.Path(HERE / args.out).write_text("\n".join(lines), encoding="utf-8")
    print("速败局", len(games), "绝杀子", dict(killer), "落点", dict(zone))
    print("已写入", args.out)


if __name__ == "__main__":
    main()
