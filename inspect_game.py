import json, pathlib, sys

HERE = pathlib.Path(__file__).parent
VAL = {1: 6000, 2: 200, 3: 200, 4: 450, 5: 900, 6: 450, 7: 100}
NAME = {1: 'K', 2: 'A', 3: 'B', 4: 'N', 5: 'R', 6: 'C', 7: 'P'}


def mat(b):
    red = sum(VAL[abs(p)] for p in b if p > 0)
    black = sum(VAL[abs(p)] for p in b if p < 0)
    return red - black


def show(b):
    for y in range(10):
        row = ''
        for x in range(9):
            p = b[y * 9 + x]
            c = NAME.get(abs(p), '.')
            row += c if p > 0 else (c.lower() if p < 0 else '.')
        print(row)


def main(tag, gi=1):
    d = json.load(open(HERE / 'data' / 'battle_logs' / f'{tag}_g{gi:03d}.json', encoding='utf-8'))
    print(d['res'], d['plies'], d['opening'], d['ours'])
    prev = 0
    for p in d['moves']:
        m = mat(p['board'])
        if m != prev or p['ply'] % 10 == 0:
            print(f"ply {p['ply']:3d} {p['by']:5s} {p['uci']} cp={p['cp']} mat={m:+d}")
        prev = m
    print('--- final ---')
    show(d['moves'][-1]['board'])


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'cpptest1', int(sys.argv[2]) if len(sys.argv) > 2 else 1)
