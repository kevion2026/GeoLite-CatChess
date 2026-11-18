// 对拍用 JS 侧：读 FEN 行 → 45 维特征 + treeScore，输出格式与 geo_dump.cpp 一致。
// 用法：node dump45.js < fens.txt
const fs = require('fs');
const path = require('path');
const XQ3 = require('./engine3d.js');

const model = JSON.parse(fs.readFileSync(path.join(__dirname, 'model_triple.json'), 'utf8'));
XQ3.setModel(model);
const seg = model.tree.model;

const VAL = { K: 1, A: 2, B: 3, N: 4, R: 5, C: 6, P: 7 };
function parseFen(fen) {
  const b = new Int8Array(90);
  const field = fen.split(/\s+/);
  let x = 0, y = 0;
  for (const c of field[0]) {
    if (c === '/') { x = 0; y++; continue; }
    if (c >= '1' && c <= '9') { x += +c; continue; }
    const t = VAL[c.toUpperCase()];
    b[y * 9 + x] = (c === c.toUpperCase()) ? t : -t;
    x++;
  }
  const side = (field[1] === 'b') ? XQ3.BLACK : XQ3.RED;
  return { b, side };
}

const lines = fs.readFileSync(0, 'utf8').split('\n').filter((s) => s.trim().length > 5);
const out = [];
for (const fen of lines) {
  const { b, side } = parseFen(fen);
  const g = XQ3.geometry(b, side, 0, 0);
  const feats = g.state.slice()
    .concat(XQ3.shapeOf(g.a.state, g.a.tokens))
    .concat(XQ3.shapeOf(g.b.state, g.b.tokens))
    .concat(XQ3.shapeOf(g.c.state, g.c.tokens));
  for (const v of XQ3.matFeats(b, side)) feats.push(v);
  for (const v of XQ3.threatFeats(b, side)) feats.push(v);
  const v = XQ3.treeScore(g, seg, b, side);
  out.push([v.toFixed(4)].concat(feats.map((z) => z.toFixed(4))).join(' '));
}
process.stdout.write(out.join('\n') + '\n');
