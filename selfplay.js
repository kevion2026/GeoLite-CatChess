/* 自对弈：用 engine3d 的 pro 搜索，双方同强度，检查是否会出现战术崩盘。 */
const E = require("./engine3d.js");
const V = { 1: 0, 2: 200, 3: 200, 4: 450, 5: 900, 6: 450, 7: 100 };
function mat(b) {
  let s = 0;
  for (const p of b) if (p) s += (p > 0 ? 1 : -1) * V[Math.abs(p)];
  return s;
}
const ms = parseInt(process.argv[2] || "1000", 10);
const b = E.initial();
let side = 1;
for (let ply = 0; ply < 150; ply++) {
  const r = E.routePlay(b, side, { book: false, proMs: ms, proDepth: 20 });
  if (!r || !r.mv) { console.log("no move at", ply); break; }
  const f = Math.floor(r.mv / 100), t = r.mv % 100;
  b[t] = b[f]; b[f] = 0;
  side = -side;
  if (ply % 2 === 1) {
    console.log(ply + 1, "mat", mat(b), "mv", r.mv, "d", r.search.depth, "cp", r.search.score);
  }
}
