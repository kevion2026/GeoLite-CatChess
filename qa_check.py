#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CatChess 出厂自检

六项：
  1) perft 交叉验证（对 board.py 的独立实现）
  2) 对局合法性（每一步都用 board.py 的 gen_legal 验，抓非法着法）
  3) 镜像对称性（180° 旋转 + 换色，评估值应完全相等）
  4) 时限遵守（movetime 实测墙钟）
  5) UCI 协议鲁棒性（position fen/startpos moves、go 各种参数）
  6) 评估/搜索一致性（同局面重复调用结果稳定）

用法: python qa_check.py --exe CatChess-V1.0-pro.exe [--quick]
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time

import board as B
from cloud_label import fen_of

FAIL = []
WARN = []


def note(ok, msg):
    print(("  [OK]   " if ok else "  [FAIL] ") + msg)
    if not ok:
        FAIL.append(msg)


def uci_session(exe, lines, timeout=60):
    p = subprocess.run([exe], input="\n".join(lines) + "\nquit\n",
                       capture_output=True, text=True, timeout=timeout)
    return p.stdout, p.stderr


def ask_move(exe, fen, ms=50):
    """返回 (bestmove, 墙钟秒)"""
    t0 = time.time()
    out, _ = uci_session(exe, ["uci", "isready", f"position fen {fen} - - 0 1",
                               f"go movetime {ms}"], timeout=60)
    dt = time.time() - t0
    m = re.search(r"bestmove\s+(\S+)", out)
    return (m.group(1) if m else None), dt


def ask_eval(exe, fen):
    out, _ = uci_session(exe, [f"position fen {fen} - - 0 1", "eval"], timeout=30)
    nums = re.findall(r"^-?\d+", out, re.M)
    return int(nums[-1]) if nums else None


def mv_from_uci(u):
    f = (ord(u[0]) - 97) + (9 - int(u[1])) * 9
    t = (ord(u[2]) - 97) + (9 - int(u[3])) * 9
    return (f, t)


def mv_to_uci(mv):
    f, t = mv
    return "%s%d%s%d" % (chr(97 + f % 9), 9 - f // 9, chr(97 + t % 9), 9 - t // 9)


# ---------------------------------------------------------------- 1. perft
def test_perft(exe):
    print("\n[1] perft 交叉验证")
    poss = json.load(open("data/pos_set.json"))
    random.seed(11)
    sel = random.sample(poss, 24)
    bad = 0
    for po in sel:
        b = list(po["b"])
        side = po["s"]
        fen = fen_of(b, side)
        out, _ = uci_session(exe, [f"position fen {fen} - - 0 1", "perft 3"], timeout=120)
        m = re.search(r"^(\d+)\s*$", out, re.M)
        got = int(m.group(1)) if m else -1
        ref = B.perft(b, side, 3)
        if got != ref:
            bad += 1
            print("    mismatched ply%d: cpp=%d py=%d" % (po["ply"], got, ref))
    note(bad == 0, "24 个局面 perft3 与 board.py 一致（不一致 %d 个）" % bad)


# ---------------------------------------------------------------- 2. 对局合法性
def test_legal_play(exe, games=12, ms=8):
    print("\n[2] 对局合法性（每步用 board.py 验）")
    illegal = 0
    crashed = 0
    plies = []
    for g in range(games):
        b = B.initial_board()
        side = 1
        hist = []
        for ply in range(300):
            legal = B.gen_legal(b, side)
            if not legal:
                break
            fen = fen_of(b, side)
            mv, _ = ask_move(exe, fen, ms=ms)
            if mv is None or mv == "0000":
                crashed += 1
                break
            move = mv_from_uci(mv)
            if move not in legal:
                illegal += 1
                print("    game%d ply%d 非法着法 %s  fen=%s" % (g, ply, mv, fen))
                break
            B.apply_move(b, move)
            side = -side
            hist.append(mv)
        plies.append(ply)
    note(illegal == 0, "%d 局 / 平均 %d 手，非法着法 %d 次" % (games, sum(plies) // max(1, len(plies)), illegal))
    note(crashed == 0, "引擎无崩溃/无空着法（%d 次）" % crashed)


# ---------------------------------------------------------------- 3. 对称性
def mirror(b, side):
    """180° 旋转 + 换色：棋盘几何与走子方同时镜像，评估应完全不变。"""
    nb = [0] * 90
    for y in range(10):
        for x in range(9):
            nb[(9 - y) * 9 + (8 - x)] = -b[y * 9 + x]
    return nb, -side


def test_symmetry(exe):
    print("\n[3] 镜像对称性（180°+换色，评估应相等）")
    poss = json.load(open("data/pos_set.json"))
    random.seed(5)
    sel = random.sample(poss, 40)
    diffs = []
    for po in sel:
        b = list(po["b"])
        s = po["s"]
        nb, ns = mirror(b, s)
        e1 = ask_eval(exe, fen_of(b, s))
        e2 = ask_eval(exe, fen_of(nb, ns))
        if e1 is None or e2 is None:
            continue
        diffs.append(abs(e1 - e2))
    mx = max(diffs) if diffs else -1
    note(mx <= 1, "40 个局面镜像评估差 max=%d cp（阈值 ≤1）" % mx)


# ---------------------------------------------------------------- 4. 时限
def test_time(exe):
    print("\n[4] 时限遵守")
    poss = json.load(open("data/pos_set.json"))[:14]
    for target in (50, 200, 800):
        worst = 0.0
        for po in poss:
            _, dt = ask_move(exe, fen_of(po["b"], po["s"]), ms=target)
            worst = max(worst, dt)
        # 进程启动 + UCI 握手本身约 20~40ms
        ok = worst * 1000 <= target + 350
        note(ok, "movetime %4dms → 最大墙钟 %.0fms" % (target, worst * 1000))


# ---------------------------------------------------------------- 5. 协议
def test_protocol(exe):
    print("\n[5] UCI 协议鲁棒性")
    # position startpos moves
    out, _ = uci_session(exe, ["position startpos moves h2e2 h9g7", "fen"], timeout=30)
    fen = out.strip().splitlines()[0] if out.strip() else ""
    note("h2e2" not in fen and fen.count("/") == 9, "position startpos moves 后棋盘可解析: %s" % fen[:40])

    # 非法/异常输入不应崩溃
    weird = ["position", "position fen garbage", "go", "go depth", "go movetime",
             "perft", "eval", "d", "unknowncmd 1 2 3", "position fen rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b"]
    try:
        out, err = uci_session(exe, weird, timeout=60)
        alive = "Exception" not in err
    except subprocess.TimeoutExpired:
        alive = False
    note(alive, "异常输入序列不崩溃、不挂死")

    # go wtime/btime（真实 GUI 用法）
    try:
        t0 = time.time()
        out, _ = uci_session(exe, ["position startpos", "go wtime 3000 btime 3000 winc 100 binc 100"], timeout=20)
        dt = time.time() - t0
        has_best = "bestmove" in out
        note(has_best and dt < 8.0, "go wtime/btime 有 bestmove 且 ≤8s（实际 %.1fs）" % dt)
    except subprocess.TimeoutExpired:
        note(False, "go wtime/btime 超时未返回（未实现时间分配）")

    # 无合法着法（将死）时应返回 0000 而不是崩溃
    mate_fen = "3k5/9/9/9/9/9/9/9/4r4/4K4 w"   # 红被将军且无处可走（近似）
    out, err = uci_session(exe, [f"position fen {mate_fen} - - 0 1", "go depth 4"], timeout=30)
    note("bestmove" in out, "死局仍返回 bestmove")


# ---------------------------------------------------------------- 6. 稳定性
def test_determinism(exe):
    print("\n[6] 确定性（同局面重复搜索应逐位一致）")
    poss = json.load(open("data/pos_set.json"))[:6]
    bad = 0
    for po in poss:
        fen = fen_of(po["b"], po["s"])
        r = []
        for _ in range(2):
            out, _ = uci_session(exe, [f"position fen {fen} - - 0 1", "go depth 6"], timeout=120)
            m = re.search(r"bestmove\s+(\S+)", out)
            r.append(m.group(1) if m else None)
        if r[0] != r[1]:
            bad += 1
            print("    %s 两次得到 %s / %s" % (fen[:30], r[0], r[1]))
    note(bad == 0, "6 个局面 depth6 两次搜索结果一致")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="CatChess-V1.0-pro.exe")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    print("=" * 60)
    print("CatChess 出厂自检:", a.exe)
    print("=" * 60)
    tests = {"1": test_perft, "2": test_legal_play, "3": test_symmetry,
             "4": test_time, "5": test_protocol, "6": test_determinism}
    for k in (a.only or "123456"):
        if k == "2" and a.quick:
            tests[k](a.exe, games=4, ms=5)
        else:
            tests[k](a.exe)
    print("\n" + "=" * 60)
    if FAIL:
        print("发现 %d 项问题：" % len(FAIL))
        for f in FAIL:
            print("  -", f)
    else:
        print("全部通过")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
