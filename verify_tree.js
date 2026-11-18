// 校验扁平化后的 treeScore 与原始公式逐局面一致（含闭合层/陷阱关闭时）
global.MODEL3D = JSON.parse(require("fs").readFileSync("model_triple.json", "utf8"));
const E = require("./engine3d.js");
E.setModel(global.MODEL3D);
E.setBook(global.MODEL3D.book);
const seg = global.MODEL3D.tree.model;

function oldScore(g, b, side) {
  const feats = g.state.concat(E.shapeOf(g.a.state, g.a.tokens))
    .concat(E.shapeOf(g.b.state, g.b.tokens)).concat(E.shapeOf(g.c.state, g.c.tokens));
  for (const v of E.matFeats(b, side)) feats.push(v);
  for (const v of E.threatFeats(b, side)) feats.push(v);
  const z = feats.map((v, i) => (v - seg.mean[i]) / (seg.std[i] || 1));
  const h2 = 2 * seg.h * seg.h;
  const w = seg.centers.map((c) => {
    let d2 = 0;
    for (let i = 0; i < z.length; i++) d2 += (z[i] - c[i]) ** 2;
    return Math.exp(-d2 / h2);
  });
  const sw = w.reduce((a, v) => a + v, 0) || 1;
  let tree = 0, glob = seg.glob.b;
  for (let k = 0; k < seg.centers.length; k++) {
    let s = seg.local[k].b;
    for (let i = 0; i < z.length; i++) s += seg.local[k].w[i] * z[i];
    tree += (w[k] / sw) * s;
  }
  for (let i = 0; i < z.length; i++) glob += seg.glob.w[i] * z[i];
  return seg.lam * tree + (1 - seg.lam) * glob;
}

// 用真实对局推进，取每个局面红黑双方视角
const fs = require("fs");
const files = fs.readdirSync("data/battle_logs").slice(0, 6);
let maxDiff = 0, n = 0, sumOld = 0, sumNew = 0, worst = null;
for (const f of files) {
  let log;
  try { log = JSON.parse(fs.readFileSync("data/battle_logs/" + f, "utf8")); } catch (e) { continue; }
  const mvs = log.moves || log.mvs || [];
  let b = E.initial(), side = E.RED;
  for (let i = 0; i < mvs.length; i++) {
    const mv = mvs[i];
    if (!mv) break;
    const f0 = (mv >> 8) & 0xff, t0 = mv & 0xff;
    if (!b[f0]) break;
    b[t0] = b[f0]; b[f0] = 0;
    side = -side;
    if (i % 7 === 0) {
      for (const sd of [1, -1]) {
        const g = E.geometry(b, sd, 0, 0);
        if (!g.a) continue;
        const a = oldScore(g, b, sd), c = E.treeScore(g, seg, b, sd);
        const diff = Math.abs(a - c);
        if (diff > maxDiff) { maxDiff = diff; worst = { f, i, a, c }; }
        sumOld += a; sumNew += c; n++;
      }
    }
  }
}
console.log("局面数", n, "最大绝对差", maxDiff.toFixed(6), "均值差", ((sumNew - sumOld) / n).toFixed(8));
if (maxDiff > 1e-3) console.log("最差", JSON.stringify(worst));
