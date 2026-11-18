/* 回应集覆盖率：现有启发式 vs 学习模型，谁把"皮卡鱼真实那一手"罩住得更多。
 * 覆盖率是搜索里最要紧的数：罩不住就等于用错误的对手模型做 min，估值再准也没用。
 */
const fs = require("fs");
const E = require("./engine3d.js");

const ds = JSON.parse(fs.readFileSync("data/battle_ds.json", "utf8"));
global.MODEL3D = JSON.parse(fs.readFileSync("model_triple.json", "utf8"));
E.setModel(global.MODEL3D);
E.setBook(global.MODEL3D.book);

const games = ds.games;
const cut = Math.floor(games.length * 0.75);
const test = games.slice(cut);

function heuristicSet(b, side, cap, rep) {
  const out = [], seen = new Set();
  const rank = [];
  for (const mv of E.legal(b, side)) {
    const f = mv / 100 | 0, t = mv % 100;
    const victim = b[t];
    let r = 0;
    if (victim) {
      const sv = E.seeCapture(b, f, t);
      if (sv > 0) r = 400 + (E.SEE_V[Math.abs(victim)] || 100) + sv * 0.1;
    }
    if (!r) {
      const c = b[t]; b[t] = b[f]; b[f] = 0;
      const chk = E.inCheck(b, -side);
      b[f] = b[t]; b[t] = c;
      if (chk && !victim) r = 260;
    }
    if (r > 0 && !seen.has(mv)) { seen.add(mv); rank.push({ mv, r }); }
  }
  rank.sort((x, y) => y.r - x.r);
  for (const x of rank) out.push(x.mv);
  const ph = E.situationLabel(b, side);
  for (const fn of [E.gravityLocal, E.gravityGlobal]) {
    const pk = E.pickWith(b, side, fn, ph, 0, rep);
    if (pk) for (const c of pk.top.slice(0, 2)) if (!out.includes(c.mv)) out.push(c.mv);
  }
  return out.slice(0, cap);
}

const rows = [];
for (const g of test) {
  for (let i = 0; i < g.rows.length; i++) {
    const [board, side, mv, who] = g.rows[i];
    if (who !== 0 || i < 2) continue;
    const b = board.slice();
    const lg = E.legal(b, side);
    if (lg.length < 3 || lg.indexOf(mv) < 0) continue;
    rows.push({ b, side, mv, lg, ply: i });
  }
}

function cover(fn) {
  let hit = 0, size = 0;
  for (const r of rows) {
    const s = fn(r);
    size += s.length;
    if (s.includes(r.mv)) hit++;
  }
  return { cov: hit / rows.length, size: size / rows.length };
}

const base5 = cover((r) => heuristicSet(r.b, r.side, 5, null));
const base8 = cover((r) => heuristicSet(r.b, r.side, 8, null));
const learnedK = (k) => cover((r) => {
  const sc = r.lg.map((mv) => ({ mv, s: E.replyScore(r.b, r.side, mv) }));
  sc.sort((a, b) => b.s - a.s);
  return sc.slice(0, k).map((x) => x.mv);
});
const l3 = learnedK(3), l5 = learnedK(5), l8 = learnedK(8);
const union = cover((r) => {
  const base = heuristicSet(r.b, r.side, 5, null);
  const sc = r.lg.map((mv) => ({ mv, s: E.replyScore(r.b, r.side, mv) }));
  sc.sort((a, b) => b.s - a.s);
  const out = base.slice();
  for (const x of sc.slice(0, 5)) if (!out.includes(x.mv)) out.push(x.mv);
  return out.slice(0, 7);
});

console.log("局面", rows.length);
console.log("现有启发式 cap5   覆盖率 %.3f  平均集合 %.1f", base5.cov, base5.size);
console.log("现有启发式 cap8   覆盖率 %.3f  平均集合 %.1f", base8.cov, base8.size);
console.log("学习 top3         覆盖率 %.3f  平均集合 3", l3.cov);
console.log("学习 top5         覆盖率 %.3f  平均集合 5", l5.cov);
console.log("学习 top8         覆盖率 %.3f  平均集合 8", l8.cov);
console.log("并集(启发5 ∪ 学习5, cap7) 覆盖率 %.3f  平均集合 %.1f", union.cov, union.size);
