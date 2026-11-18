/* 生成自对弈局面，用于扩充价值标签池。输出 JSONL：{"b":[...],"s":1} */
const fs = require('fs');
const X = require('./engine3d.js');
X.setModel(require('./model_triple.json'));

const N = +process.argv[2] || 1200;
const OUT = process.argv[3] || 'data/selfplay_positions.jsonl';
const fd = fs.openSync(OUT, 'w');

function randLegal(b, side) {
  const L = X.legal(b, side);
  return L.length ? L[Math.floor(Math.random() * L.length)] : 0;
}

let total = 0, games = 0;
for (let g = 0; g < N; g++) {
  let b = X.initial(), side = 1, plies = 0;
  const keys = [X.keyOf(b, side)];
  for (; plies < 110; plies++) {
    const legal = X.legal(b, side);
    if (!legal.length) break;
    let mv = 0;
    if (plies < 6 || Math.random() < 0.28) {
      mv = legal[Math.floor(Math.random() * legal.length)];
    } else {
      try {
        const r = X.branchSearch(b, side, {
          width: 3, repWidth: 1, rootAll: true, rootKeep: 8,
          pro: true, history: keys, rootTactics: true,
        });
        if (r && r.mv && legal.includes(r.mv)) mv = r.mv;
      } catch (e) { mv = 0; }
      if (!mv) mv = randLegal(b, side);
    }
    if (!mv) break;
    if (plies % 2 === 0) {
      fs.writeSync(fd, JSON.stringify({ b: Array.from(b), s: side }) + '\n');
      total++;
    }
    const f = X.fOf(mv), t = X.tOf(mv);
    b[t] = b[f]; b[f] = 0;
    side = -side;
    keys.push(X.keyOf(b, side));
    if (keys.length > 24) keys.shift();
  }
  games++;
  if ((g + 1) % 100 === 0) console.log('games', g + 1, 'positions', total, 'lastPlies', plies);
}
fs.closeSync(fd);
console.log('DONE', games, total, OUT);
