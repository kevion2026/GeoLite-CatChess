/* 三维引擎自测：状态维度、检索、引力选着、自对弈合法性与耗时。 */
const fs = require("fs");
const E = require("./engine3d.js");
const model = JSON.parse(fs.readFileSync(process.argv[2] || "model3d.json", "utf8"));
E.setModel(model);

const b0 = E.initial();
const g0 = E.geometry(b0, E.RED, 10, 10);
console.log("state dims:", g0.state.length, "| state:", g0.state.map(v => v.toFixed(3)).join(" "));
console.log("kept@0:", g0.layers[0].kept, "kept@10:", g0.layers[10].kept,
  "ρ:", (g0.layers[0].rhoA !== undefined ? g0.layers[0].rhoA.toFixed(3) + " / " + g0.layers[0].rhoB.toFixed(3) : g0.layers[0].residual.toFixed(3)));
console.log("labels(L0):", E.situationLabel(b0, E.RED));
const r = E.retrieve(g0.state, 0, 5);
console.log("retrieve:", r.knn.cls, "dist", r.knn.dist.toFixed(3), "prob", r.knn.prob.map(p => (p * 100).toFixed(0) + "%").join(" "));

const t0 = Date.now();
const pick = E.gravityPick(b0, E.RED, { phase: r.knn.cls });
console.log("pick:", pick.mv, "score", pick.score.toFixed(1), "cands", pick.nodes, "ms", Date.now() - t0);
console.log("top5:", pick.top.slice(0, 5).map(c => c.mv + ":" + c.score.toFixed(0)).join(" "));

// 自对弈：合法性、时长、均耗
function game(n, noise) {
  const b = E.initial();
  let side = E.RED, ply = 0, ms = 0, caps = 0;
  const keys = [];
  while (ply < 200) {
    const legal = E.legal(b, side);
    if (!legal.length) break;
    const t = Date.now();
    const res = E.play(b, side, { noise, history: keys });
    ms += Date.now() - t;
    if (!res.mv || !legal.includes(res.mv)) throw new Error("illegal move " + res.mv);
    const cap = b[E.tOf(res.mv)];
    if (cap) caps++;
    const f = E.fOf(res.mv), to = E.tOf(res.mv);
    b[to] = b[f]; b[f] = 0;
    side = -side; keys.push(E.keyOf(b, side)); ply++;
  }
  return { ply, ms, caps, end: side === E.RED ? "轮到红" : "轮到黑" };
}
for (const [i, noise] of [[1, 12], [2, 40]]) {
  const st = Date.now();
  const g = game(i, noise);
  console.log(`局${i} noise=${noise}: ${g.ply} 手, 吃子 ${g.caps}, 均耗 ${(g.ms / Math.max(g.ply, 1)).toFixed(1)}ms, 总 ${Date.now() - st}ms, ${g.end}`);
}
