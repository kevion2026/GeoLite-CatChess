// 对每个样本计算「纯几何树分」与「闭合项」，供 fit_closure.py 拟合权重。
const fs = require('fs');
global.MODEL3D = JSON.parse(fs.readFileSync('model_triple.json', 'utf8'));
const E = require('./engine3d.js');
E.setModel(global.MODEL3D);
const seg = global.MODEL3D.tree.model;
const rows = JSON.parse(fs.readFileSync('data/fit_rows.json', 'utf8'));
const out = [];
const t0 = Date.now();
for (const r of rows) {
  const g = E.geometry(r.b, r.s, 0, 0);
  // 关闭闭合层，取纯树分
  const saved = seg.closure;
  seg.closure = null;
  const t = E.treeScore(g, seg, r.b, r.s);
  seg.closure = saved;
  if (t === null) continue;
  out.push({ y: r.y, t: +t.toFixed(2), c: E.closureOf(r.b, r.s).map((v) => +v.toFixed(3)), g: r.g, p: r.p });
}
fs.writeFileSync('data/fit_terms.json', JSON.stringify(out));
console.log('rows', out.length, 'ms', Date.now() - t0);
