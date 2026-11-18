// 摄动探针：不依赖标签，直接测「模型对棋盘事实的响应是否合棋理」。
// 对每个样本局面做若干次受控扰动，报告平均分差。理想值按真实子力/棋理给出。
const fs = require('fs');
global.MODEL3D = JSON.parse(fs.readFileSync('model_triple.json', 'utf8'));
const E = require('./engine3d.js');
E.setModel(global.MODEL3D);
const seg = global.MODEL3D.tree.model;
const rows = JSON.parse(fs.readFileSync('data/fit_rows.json', 'utf8'));

const W = 9;
function score(b, side) {
  return E.treeScore(E.geometry(b, side, 0, 0), seg, b, side);
}
function withBoard(b, f) {
  const c = b.slice();
  const r = f(c);
  return r;
}

// 从己方（红）视角：扰动后分差为正 = 对我们更有利
const probes = [
  { name: '拿掉对方1车', ideal: 900, fn: (b, s) => killOne(b, -s, 5) },
  { name: '拿掉对方1马', ideal: 400, fn: (b, s) => killOne(b, -s, 4) },
  { name: '拿掉对方1炮', ideal: 450, fn: (b, s) => killOne(b, -s, 6) },
  { name: '拿掉对方1兵', ideal: 100, fn: (b, s) => killOne(b, -s, 7) },
  { name: '拿掉对方双士', ideal: 400, fn: (b, s) => killN(b, -s, 2, 2) },
  { name: '拿掉对方双象', ideal: 400, fn: (b, s) => killN(b, -s, 3, 2) },
  { name: '自己的车被吃', ideal: -900, fn: (b, s) => killOne(b, s, 5) },
];

function killOne(b, owner, type) {
  for (let i = 0; i < 90; i++) {
    const q = b[i];
    if (q && Math.sign(q) === owner && Math.abs(q) === type) { b[i] = 0; return 1; }
  }
  return 0;
}
function killN(b, owner, type, n) {
  let c = 0;
  for (let i = 0; i < 90; i++) {
    const q = b[i];
    if (q && Math.sign(q) === owner && Math.abs(q) === type && c < n) { b[i] = 0; c++; }
  }
  return c;
}

function run(label, weights) {
  seg.closure = weights;
  const res = {};
  for (const p of probes) res[p.name] = [];
  let n = 0;
  for (const r of rows) {
    if (r.p > 24) continue;          // 只看布局到中前段，避免残局子力天然稀缺
    if (n++ > 400) break;
    const s = r.s;
    const b0 = r.b;
    const base = score(b0, s);
    for (const p of probes) {
      const c = b0.slice();
      const k = p.fn(c, s);
      if (!k) continue;
      res[p.name].push(score(c, s) - base);
    }
  }
  console.log('\n=== ' + label + ' ===');
  for (const p of probes) {
    const v = res[p.name];
    if (!v.length) continue;
    const m = v.reduce((a, x) => a + x, 0) / v.length;
    const ratio = p.ideal === 0 ? 0 : m / p.ideal;
    console.log(`${p.name.padEnd(12)} 实测 ${m.toFixed(1).padStart(8)}  棋理 ${String(p.ideal).padStart(5)}  灵敏度 ${ratio.toFixed(2)}`);
  }
}

// 车活跃度：把己方最靠角的车搬到对方底线的空位，测分差
function rookActivity(weights) {
  seg.closure = weights;
  let sum = 0, n = 0;
  for (const r of rows) {
    if (r.p > 30) continue;
    if (n > 300) break;
    const s = r.s;
    let best = -1;
    for (let i = 0; i < 90; i++) {
      const q = r.b[i];
      if (q && Math.sign(q) === s && Math.abs(q) === 5) { best = i; break; }
    }
    if (best < 0) continue;
    // 目标：对方底线的一个空位（尽量靠中路）
    const ty = s > 0 ? 0 : 9;
    let tgt = -1;
    for (const tx of [4, 3, 5, 2, 6, 1, 7, 0, 8]) {
      if (r.b[ty * 9 + tx] === 0) { tgt = ty * 9 + tx; break; }
    }
    if (tgt < 0) continue;
    const b2 = r.b.slice();
    b2[tgt] = b2[best];
    b2[best] = 0;
    sum += score(b2, s) - score(r.b, s);
    n++;
  }
  console.log(`红车占位→对方底线空位  实测 ${(sum / n).toFixed(1).padStart(8)}  棋理   +60 左右`);
  seg.closure = null;
}

run('闭合层关闭（原状）', null);
run('按类标定（1-α）', [0.69, 0.75, 0.55, 0.32, 0.62, 0, 0, 0, 0]);
run('按类 + 结构项', [0.69, 0.75, 0.55, 0.32, 0.62, 0.6, 0.6, 0.5, 0.3]);
rookActivity(null);
rookActivity([0.69, 0.75, 0.55, 0.32, 0.62, 0.6, 0.6, 0.5, 0.3]);
