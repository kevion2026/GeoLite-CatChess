"""中国象棋规则内核：90 格棋盘、全部走法、将军与将死判定。

坐标约定：x=0..8 自左向右，y=0..9 自上向下；y=0 为黑方底线，y=9 为红方底线。
棋子编码：1=帅/将 2=仕/士 3=相/象 4=马 5=车 6=炮 7=兵/卒；红为正，黑为负。
"""

W, H = 9, 10
RED, BLACK = 1, -1
KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN = 1, 2, 3, 4, 5, 6, 7

PIECE_NAME = {
    KING: "将", ADVISOR: "士", ELEPHANT: "象", HORSE: "马",
    ROOK: "车", CANNON: "炮", PAWN: "卒",
}
PIECE_NAME_RED = {
    KING: "帅", ADVISOR: "仕", ELEPHANT: "相", HORSE: "马",
    ROOK: "车", CANNON: "炮", PAWN: "兵",
}
PIECE_VALUE = {KING: 100, ADVISOR: 30, ELEPHANT: 30, HORSE: 55, ROOK: 110, CANNON: 58, PAWN: 18}

# 角色权重（对应论文“词性加权”：关键术语更高）
ROLE_WEIGHT = {KING: 1.40, ADVISOR: 0.80, ELEPHANT: 0.85, HORSE: 1.00,
               ROOK: 1.25, CANNON: 1.10, PAWN: 0.95}

ORTHO = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAG = ((1, 1), (1, -1), (-1, 1), (-1, -1))

# 马：目标偏移与马腿
HORSE_MOVES = (
    ((1, 2), (0, 1)), ((-1, 2), (0, 1)), ((1, -2), (0, -1)), ((-1, -2), (0, -1)),
    ((2, 1), (1, 0)), ((2, -1), (1, 0)), ((-2, 1), (-1, 0)), ((-2, -1), (-1, 0)),
)


def sq(x, y):
    return y * W + x


def xy(s):
    return s % W, s // W


def in_board(x, y):
    return 0 <= x < W and 0 <= y < H


def in_palace(x, y, side):
    return 3 <= x <= 5 and (7 <= y <= 9 if side == RED else 0 <= y <= 2)


def crossed_river(y, side):
    return y <= 4 if side == RED else y >= 5


def initial_board():
    b = [0] * 90
    back = (ROOK, HORSE, ELEPHANT, ADVISOR, KING, ADVISOR, ELEPHANT, HORSE, ROOK)
    for x, t in enumerate(back):
        b[sq(x, 0)] = -t
        b[sq(x, 9)] = t
    b[sq(1, 2)] = -CANNON
    b[sq(7, 2)] = -CANNON
    for x in (0, 2, 4, 6, 8):
        b[sq(x, 3)] = -PAWN
        b[sq(x, 6)] = PAWN
    b[sq(1, 7)] = CANNON
    b[sq(7, 7)] = CANNON
    return b


def side_of(p):
    return RED if p > 0 else BLACK if p < 0 else 0


def board_copy(b):
    return list(b)


def gen_pseudo(b, side):
    """生成伪合法走法 (from, to)。"""
    moves = []
    for s in range(90):
        p = b[s]
        if p == 0 or side_of(p) != side:
            continue
        t = abs(p)
        x, y = xy(s)
        if t == KING:
            for dx, dy in ORTHO:
                nx, ny = x + dx, y + dy
                if in_palace(nx, ny, side):
                    q = b[sq(nx, ny)]
                    if q == 0 or side_of(q) != side:
                        moves.append((s, sq(nx, ny)))
        elif t == ADVISOR:
            for dx, dy in DIAG:
                nx, ny = x + dx, y + dy
                if in_palace(nx, ny, side):
                    q = b[sq(nx, ny)]
                    if q == 0 or side_of(q) != side:
                        moves.append((s, sq(nx, ny)))
        elif t == ELEPHANT:
            for dx, dy in DIAG:
                nx, ny = x + 2 * dx, y + 2 * dy
                if not in_board(nx, ny):
                    continue
                if side == RED and ny < 5:
                    continue
                if side == BLACK and ny > 4:
                    continue
                if b[sq(x + dx, y + dy)] != 0:
                    continue
                q = b[sq(nx, ny)]
                if q == 0 or side_of(q) != side:
                    moves.append((s, sq(nx, ny)))
        elif t == HORSE:
            for (dx, dy), (lx, ly) in HORSE_MOVES:
                nx, ny = x + dx, y + dy
                if not in_board(nx, ny):
                    continue
                if b[sq(x + lx, y + ly)] != 0:
                    continue
                q = b[sq(nx, ny)]
                if q == 0 or side_of(q) != side:
                    moves.append((s, sq(nx, ny)))
        elif t == ROOK:
            for dx, dy in ORTHO:
                nx, ny = x + dx, y + dy
                while in_board(nx, ny):
                    q = b[sq(nx, ny)]
                    if q == 0:
                        moves.append((s, sq(nx, ny)))
                    else:
                        if side_of(q) != side:
                            moves.append((s, sq(nx, ny)))
                        break
                    nx, ny = nx + dx, ny + dy
        elif t == CANNON:
            for dx, dy in ORTHO:
                nx, ny = x + dx, y + dy
                while in_board(nx, ny) and b[sq(nx, ny)] == 0:
                    moves.append((s, sq(nx, ny)))
                    nx, ny = nx + dx, ny + dy
                # 越过炮架后寻找第一个棋子
                nx, ny = nx + dx, ny + dy
                while in_board(nx, ny):
                    q = b[sq(nx, ny)]
                    if q != 0:
                        if side_of(q) != side:
                            moves.append((s, sq(nx, ny)))
                        break
                    nx, ny = nx + dx, ny + dy
        elif t == PAWN:
            ny = y - side
            if in_board(x, ny):
                q = b[sq(x, ny)]
                if q == 0 or side_of(q) != side:
                    moves.append((s, sq(x, ny)))
            if crossed_river(y, side):
                for dx in (-1, 1):
                    nx = x + dx
                    if in_board(nx, y):
                        q = b[sq(nx, y)]
                        if q == 0 or side_of(q) != side:
                            moves.append((s, sq(nx, y)))
    return moves


def find_king(b, side):
    target = KING * side
    for s in range(90):
        if b[s] == target:
            return s
    return -1


def generals_facing(b):
    kr = find_king(b, RED)
    kb = find_king(b, BLACK)
    if kr < 0 or kb < 0:
        return False
    xr, yr = xy(kr)
    xb, yb = xy(kb)
    if xr != xb:
        return False
    lo, hi = (yr, yb) if yr < yb else (yb, yr)
    for y in range(lo + 1, hi):
        if b[sq(xr, y)] != 0:
            return False
    return True


def attacked(b, s, by):
    """s 是否被 by 方攻击。"""
    x, y = xy(s)
    # 车与将的直线
    for dx, dy in ORTHO:
        nx, ny = x + dx, y + dy
        step = 1
        while in_board(nx, ny):
            q = b[sq(nx, ny)]
            if q != 0:
                if side_of(q) == by:
                    t = abs(q)
                    if t == ROOK:
                        return True
                    if t == KING and step == 1:
                        return True
                break
            nx, ny = nx + dx, ny + dy
            step += 1
    # 炮：隔一子吃
    for dx, dy in ORTHO:
        nx, ny = x + dx, y + dy
        screens = 0
        while in_board(nx, ny):
            q = b[sq(nx, ny)]
            if q != 0:
                if screens == 1:
                    if side_of(q) == by and abs(q) == CANNON:
                        return True
                    break
                screens += 1
            nx, ny = nx + dx, ny + dy
    # 马
    for (dx, dy), (lx, ly) in HORSE_MOVES:
        sx_, sy_ = x - dx, y - dy          # 马的反向落点
        if not in_board(sx_, sy_):
            continue
        q = b[sq(sx_, sy_)]
        if q != 0 and side_of(q) == by and abs(q) == HORSE:
            leg_x, leg_y = sx_ + lx, sy_ + ly
            if in_board(leg_x, leg_y) and b[sq(leg_x, leg_y)] == 0:
                return True
    # 兵
    if by == RED:
        cand = [(x, y + 1)] + ([(x - 1, y), (x + 1, y)] if crossed_river(y, RED) else [])
    else:
        cand = [(x, y - 1)] + ([(x - 1, y), (x + 1, y)] if crossed_river(y, BLACK) else [])
    for cx, cy in cand:
        if in_board(cx, cy):
            q = b[sq(cx, cy)]
            if q != 0 and side_of(q) == by and abs(q) == PAWN:
                return True
    return False


def in_check(b, side):
    k = find_king(b, side)
    if k < 0:
        return True
    return attacked(b, k, -side) or generals_facing(b)


def apply_move(b, mv):
    f, t = mv
    cap = b[t]
    b[t] = b[f]
    b[f] = 0
    return cap


def undo_move(b, mv, cap):
    f, t = mv
    b[f] = b[t]
    b[t] = cap


def gen_legal(b, side):
    out = []
    for mv in gen_pseudo(b, side):
        cap = apply_move(b, mv)
        ok = not in_check(b, side)
        undo_move(b, mv, cap)
        if ok:
            out.append(mv)
    return out


def is_capture(b, mv):
    return b[mv[1]] != 0


def perft(b, side, depth):
    if depth == 0:
        return 1
    if depth == 1:
        return len(gen_legal(b, side))
    n = 0
    for mv in gen_pseudo(b, side):
        cap = apply_move(b, mv)
        if not in_check(b, side):
            n += perft(b, -side, depth - 1)
        undo_move(b, mv, cap)
    return n


def piece_list(b):
    """[(square, code)] 全部棋子。"""
    return [(s, b[s]) for s in range(90) if b[s] != 0]


def fen_like(b):
    rows = []
    for y in range(H):
        row = ""
        for x in range(W):
            p = b[sq(x, y)]
            row += "." if p == 0 else PIECE_NAME[abs(p)].upper() if p > 0 else PIECE_NAME[abs(p)]
        rows.append(row)
    return "/".join(rows)


def parse_fen_like(text):
    b = [0] * 90
    rows = text.strip().split("/")
    for y, row in enumerate(rows):
        x = 0
        for ch in row:
            if ch == ".":
                x += 1
            else:
                t = {v: k for k, v in PIECE_NAME.items()}[ch.lower()]
                b[sq(x, y)] = t if ch.isupper() else -t
                x += 1
    return b


if __name__ == "__main__":
    b = initial_board()
    print(fen_like(b))
    for d in (1, 2, 3):
        print("perft", d, perft(initial_board(), RED, d))
