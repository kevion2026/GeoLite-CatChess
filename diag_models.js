/* 诊断：两个学习层是否真的带来"位置相关"的区分力。
 *
 * 三个问题：
 *  1) 知彼 top1=29.6% 是真学到了东西，还是只是"优先选吃子"这种手写规则？
 *     对照：手写基线（吃子价值+叫将+将威胁）在同样候选上的 top1。
 *  2) 知己 AUC=0.866 是不是只学到"手数越大越危险"？
 *     对照：只用 ply 的 AUC、只用子力的 AUC。
 *  3) 知己在**同一个根局面的不同候选之间**有没有区分度？
 *     若候选之间的分数几乎一样，它在根部选着时就等于常数，等于没用。
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

function aucOf(scores) {
  const s = scores.slice().sort((a, b) => a.p - b.p);
  let rank = 0, pos = 0;
  for (let i = 0; i < s.length; i++) if (s[i].y === 1) { rank += i + 1; pos++; }
  const neg = s.length - pos;
  return pos && neg ? (rank - pos * (pos + 1) / 2) / (pos * neg) : 0.5;
}

// ---- 取测试集的"对手该走"局面 ----
const replyRows = [], dangerRows = [];
for (const g of test) {
  const ourSide = g.ours_red ? 1 : -1;
  const rows = g.rows;
  const mats = rows.map((r) => {
    let m = 0;
    for (const q of r[0]) if (q) m += ((q > 0) === (ourSide > 0) ? 1 : -1) * (E.VALUE[Math.abs(q)] || 0);
    return m;
  });
  const lossAt = g.res === "loss" ? rows.length : -1;
  for (let i = 0; i < rows.length; i++) {
    const [board, side, mv, who] = rows[i];
    if (who !== 0 || i < 2) continue;
    const b = board.slice();
    const lg = E.legal(b, side);
    if (lg.length < 3 || lg.indexOf(mv) < 0) continue;
    replyRows.push({ b, side, mv, lg, ply: i });
    let drop = 0;
    for (let j = i; j < Math.min(rows.length, i + 9); j++) drop = Math.max(drop, mats[i] - mats[j]);
    dangerRows.push({ b, ourSide, ply: i, y: (drop >= 250 || (lossAt >= 0 && lossAt - i <= 12)) ? 1 : 0, drop });
  }
}
console.log("测试局面", replyRows.length);

// ---- 1) 知彼：与手写基线对比 ----
function evalRank(rows, rankFn) {
  let t1 = 0, t3 = 0;
  for (const r of rows) {
    const arr = r.lg.map((mv) => ({ mv, s: rankFn(r.b, r.side, mv) }));
    arr.sort((a, c) => c.s - a.s);
    if (arr[0].mv === r.mv) t1++;
    if (arr.slice(0, 3).some((x) => x.mv === r.mv)) t3++;
  }
  return { t1: t1 / rows.length, t3: t3 / rows.length };
}
// 手写基线：吃子（按被吃子价值）+ 叫将 + 落点威胁
function handScore(b, side, mv) {
  const f = mv / 100 | 0, t = mv % 100;
  const victim = b[t], piece = b[f];
  let s = victim ? (E.VALUE[Math.abs(victim)] || 0) / 100 : 0;
  const cap = b[t]; b[t] = b[f]; b[f] = 0;
  if (E.inCheck(b, -side)) s += 2.5;
  b[f] = b[t]; b[t] = cap;
  return s;
}
const learned = evalRank(replyRows, (b, side, mv) => E.replyScore(b, side, mv));
const hand = evalRank(replyRows, handScore);
console.log("知彼 top1/top3  学习 %.3f/%.3f   手写基线 %.3f/%.3f   随机 %.3f/%.3f",
  learned.t1, learned.t3, hand.t1, hand.t3, 1 / 40, 3 / 40);

// ---- 2) 知己：与 ply-only / 子力-only 对比 ----
const withDanger = dangerRows.map((r) => ({ y: r.y, p: E.dangerOf(r.b, r.ourSide, r.ply) }));
const plyOnly = dangerRows.map((r) => ({ y: r.y, p: r.ply }));
const matOnly = dangerRows.map((r) => {
  let m = 0;
  for (const q of r.b) if (q) m += (((q > 0) === (r.ourSide > 0)) ? 1 : -1) * (E.VALUE[Math.abs(q)] || 0);
  return { y: r.y, p: -m };
});
console.log("知己 AUC  完整 %.3f  只用ply %.3f  只用子力 %.3f",
  aucOf(withDanger), aucOf(plyOnly), aucOf(matOnly));

// ---- 3) 同一根局面内，候选之间的分散度 ----
// 取 200 个真实局面，对每个局面的全部合法着算"我走完之后对手该走"的危险度，看组内标准差
let intra = [], inter = [];
const sample = replyRows.filter((_, i) => i % 5 === 0).slice(0, 200);
for (const r of sample) {
  const vals = [];
  for (const mv of r.lg) {
    const f = mv / 100 | 0, t = mv % 100;
    const cap = r.b[t];
    r.b[t] = r.b[f]; r.b[f] = 0;
    vals.push(E.dangerOf(r.b, r.ourSide || -r.side, r.ply + 1));
    r.b[f] = r.b[t]; r.b[t] = cap;
  }
  const mean = vals.reduce((a, v) => a + v, 0) / vals.length;
  const sd = Math.sqrt(vals.reduce((a, v) => a + (v - mean) ** 2, 0) / vals.length);
  intra.push(sd);
  inter.push(mean);
}
intra.sort((a, b) => a - b);
inter.sort((a, b) => a - b);
console.log("组内标准差 中位 %.3f p90 %.3f | 组间均值 中位 %.3f 跨度 %.3f..%.3f",
  intra[intra.length / 2 | 0], intra[Math.floor(intra.length * 0.9)],
  inter[inter.length / 2 | 0], inter[0], inter[inter.length - 1]);
