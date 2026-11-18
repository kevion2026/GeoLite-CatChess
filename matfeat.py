"""子力九维特征：与 engine3d.js matFeats 同序。"""

MAT_V = {2: 100, 3: 100, 4: 200, 5: 450, 6: 230, 7: 40}


def mat_feats(board_, side):
    own, opp = [0] * 8, [0] * 8
    for s in range(90):
        p = int(board_[s])
        if not p:
            continue
        t = abs(p)
        k = 7 if t == 7 else t
        if (p > 0) == (side > 0):
            own[k] += 1
            if t == 7 and (s // 9 <= 4 if side > 0 else s // 9 >= 5):
                own[0] += 1
        else:
            opp[k] += 1
            if t == 7 and (s // 9 <= 4 if side < 0 else s // 9 >= 5):
                opp[0] += 1
    mv = sum(MAT_V[k] * own[k] for k in range(2, 8))
    mo = sum(MAT_V[k] * opp[k] for k in range(2, 8))
    return [(mv - mo) / 100.0] + [own[k] - opp[k] for k in range(1, 8)] + [own[0] - opp[0]]
