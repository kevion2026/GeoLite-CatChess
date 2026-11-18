import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
tag = sys.argv[1] if len(sys.argv) > 1 else 'scaled10s'
gi = int(sys.argv[2]) if len(sys.argv) > 2 else 1
d = json.load(open(HERE / 'data' / 'battle_logs' / f'{tag}_g{gi:03d}.json', encoding='utf-8'))
hist = [p['uci'] for p in d['moves']]
p = subprocess.Popen([str(HERE / 'xq9.exe')], cwd=str(HERE), stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
p.stdin.write('position startpos moves ' + ' '.join(hist) + '\n')
p.stdin.write('go depth 6\n')
p.stdin.flush()
out = p.stdout.readline().strip()
print('hist', len(hist), '->', out)
p.stdin.write('quit\n')
p.stdin.flush()
