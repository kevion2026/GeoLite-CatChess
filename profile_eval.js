// 估值链路逐段剖面：找出单步 15ms 到底花在哪
global.MODEL3D = JSON.parse(require("fs").readFileSync("model_triple.json", "utf8"));
const E = require("./engine3d.js");
E.setModel(global.MODEL3D);
E.setBook(global.MODEL3D.book);
const seg = global.MODEL3D.tree.model;

// 取一个真实中局局面
const seq = [[7, 7, 4, 7], [7, 0, 4, 0], [8, 9, 7, 7], [1, 9, 2, 7], [8, 7, 6, 6], [8, 9, 7, 9],
             [1, 7, 1, 0], [0, 0, 0, 1], [6, 9, 5, 7], [2, 0, 2, 2], [7, 6, 6, 6], [3, 0, 4, 2]];
let b = E.initial(), side = E.RED;
for (const [fx, fy, tx, ty] of seq) { b[ty * 9 + tx] = b[fy * 9 + fx]; b[fy * 9 + fx] = 0; side = -side; }

const N = 4000;
function bench(name, fn) {
  for (let i = 0; i < 200; i++) fn();          // 预热
  const t = process.hrtime.bigint();
  for (let i = 0; i < N; i++) fn();
  const us = Number(process.hrtime.bigint() - t) / 1000 / N;
  console.log(name.padEnd(18), us.toFixed(2) + " us");
  return us;
}

// geometry 单独
const g = E.geometry(b, side, 0, 0);
let total = 0;
total += bench("geometry(triple)", () => E.geometry(b, side, 0, 0));
total += bench("shapeOf x3", () => {
  E.shapeOf(g.a.state, g.a.tokens); E.shapeOf(g.b.state, g.b.tokens); E.shapeOf(g.c.state, g.c.tokens);
});
total += bench("matFeats", () => E.matFeats(b, side));
total += bench("threatFeats", () => E.threatFeats(b, side));
total += bench("treeScore(full)", () => E.treeScore(E.geometry(b, side, 0, 0), seg, b, side));

// RBF 部分单独：直接手写复现，不含前面
const feats = g.state.concat(E.shapeOf(g.a.state, g.a.tokens))
  .concat(E.shapeOf(g.b.state, g.b.tokens)).concat(E.shapeOf(g.c.state, g.c.tokens));
for (const v of E.matFeats(b, side)) feats.push(v);
for (const v of E.threatFeats(b, side)) feats.push(v);
const z = feats.map((v, i) => (v - seg.mean[i]) / (seg.std[i] || 1));
console.log("dims", z.length, "centers", seg.centers.length, "h", seg.h);
const h2 = 2 * seg.h * seg.h;
bench("rbf 64 centers", () => {
  const w = seg.centers.map((c) => {
    let d2 = 0;
    for (let i = 0; i < z.length; i++) d2 += (z[i] - c[i]) ** 2;
    return Math.exp(-d2 / h2);
  });
  return w;
});
bench("local 64 linear", () => {
  let tree = 0;
  for (let k = 0; k < seg.centers.length; k++) {
    let s = seg.local[k].b;
    for (let i = 0; i < z.length; i++) s += seg.local[k].w[i] * z[i];
    tree += s;
  }
  return tree;
});
console.log("--- 合计 ---", total.toFixed(1), "us");
