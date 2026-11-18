/* 深搜服务：全宽迭代加深 α-β，估值仍然只用几何激活树（不含任何外部引擎）。
   stdin 一行一个 JSON {mvs:[...]}，stdout 返回着法与统计。
   参数：GEO_DEPTH（最大深度，默认 3）、GEO_MS（每步预算毫秒，默认 300）、GEO_SYM（1/0）。 */
const fs = require("fs");
const path = require("path");
global.MODEL3D = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
global.XQ3 = require(path.resolve(process.argv[3]));
const E = global.XQ3;
E.setModel(global.MODEL3D);
if (process.env.GEO_BOOK) E.setBook(JSON.parse(fs.readFileSync(process.env.GEO_BOOK, "utf8")));
else if (global.MODEL3D.book) E.setBook(global.MODEL3D.book);

const SEG = global.MODEL3D.tree && global.MODEL3D.tree.model;
const SYM = process.env.GEO_SYM !== "0";
const MAXD = Number(process.env.GEO_DEPTH || 3);
const BUDGET = Number(process.env.GEO_MS || 300);
const QDEPTH = Number(process.env.GEO_Q === undefined ? 2 : process.env.GEO_Q);
const DANGER = Number(process.env.GEO_DANGER === undefined ? 300 : process.env.GEO_DANGER);
const CW = Number(process.env.GEO_CLASSIC === undefined ? 0 : process.env.GEO_CLASSIC);
function danger(b, side, ply) {
  if (!DANGER || !E.dangerOf || !global.MODEL3D.battle || !global.MODEL3D.battle.danger) return 0;
  return DANGER * E.dangerOf(b, side, ply);
}
const MATE = 100000;

function ev(b, side) {
  let v1 = E.treeScore(E.geometry(b, side, 0, 0), SEG, b, side);
  if (CW) v1 = (1 - CW) * v1 + CW * E.classicScore(b, side);
  if (!SYM) return v1;
  let v2 = E.treeScore(E.geometry(b, -side, 0, 0), SEG, b, -side);
  if (CW) v2 = (1 - CW) * v2 + CW * E.classicScore(b, -side);
  return 0.5 * (v1 - v2);
}
function mvv(b, mv) {
  const v = b[E.tOf(mv)], a = b[E.fOf(mv)];
  return (v ? 100 + v * 10 : 0) - a;
}
function order(b, side, mvs) {
  const out = mvs.map((mv) => {
    const cap = b[E.tOf(mv)], from = E.fOf(mv);
    const gain = cap ? 1000 + cap * 10 - b[from] : 0;
    return { mv, s: gain };
  });
  out.sort((x, y) => y.s - x.s);
  return out.map((x) => x.mv);
}
let deadline = 0, aborted = false, nodes = 0;

function qsearch(b, side, alpha, beta, ply, q) {
  nodes++;
  if ((nodes & 255) === 0 && Date.now() > deadline) { aborted = true; return ev(b, side); }
  let stand = ev(b, side);
  if (q <= 0 || stand >= beta) return stand;
  if (stand > alpha) alpha = stand;
  const caps = E.legal(b, side).filter((mv) => b[E.tOf(mv)] !== 0);
  for (const mv of order(b, side, caps)) {
    const cap = b[E.tOf(mv)];
    b[E.tOf(mv)] = b[E.fOf(mv)]; b[E.fOf(mv)] = 0;
    const v = -qsearch(b, -side, -beta, -alpha, ply + 1, q - 1);
    b[E.fOf(mv)] = b[E.tOf(mv)]; b[E.tOf(mv)] = cap;
    if (aborted) return stand;
    if (v >= beta) return v;
    if (v > alpha) alpha = v;
  }
  return alpha;
}

function ab(b, side, depth, alpha, beta, ply) {
  nodes++;
  if ((nodes & 255) === 0 && Date.now() > deadline) { aborted = true; return ev(b, side); }
  const mvs = E.legal(b, side);
  if (!mvs.length) return -MATE + ply;
  if (depth <= 0) return qsearch(b, side, alpha, beta, ply, QDEPTH);
  let best = -Infinity;
  for (const mv of order(b, side, mvs)) {
    const cap = b[E.tOf(mv)];
    b[E.tOf(mv)] = b[E.fOf(mv)]; b[E.fOf(mv)] = 0;
    const v = -ab(b, -side, depth - 1, -beta, -alpha, ply + 1);
    b[E.fOf(mv)] = b[E.tOf(mv)]; b[E.tOf(mv)] = cap;
    if (aborted) return best > -Infinity ? best : ev(b, side);
    if (v > best) best = v;
    if (v > alpha) alpha = v;
    if (alpha >= beta) break;
  }
  return best;
}

const INIT = E.initial();
const rl = require("readline").createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const t0 = Date.now();
  let req; try { req = JSON.parse(line); } catch (e) { return; }
  let b = INIT.slice(), side = E.RED;
  if (req.board) { b = req.board.slice(); side = req.side || E.RED; req.mvs = req.mvs || []; }
  const hist = [E.keyOf(b, side)];
  for (const mv of req.mvs) {
    b[E.tOf(mv)] = b[E.fOf(mv)]; b[E.fOf(mv)] = 0; side = -side;
    hist.push(E.keyOf(b, side));
  }
  // 开局库仅在库内命中时使用，不改变“库外全部由几何树决定”
  if (req.book !== false && E.bookPick) {
    const bk = E.bookPick(b, side, req.mvs ? req.mvs.length : 0, 0);
    if (bk) {
      process.stdout.write(JSON.stringify({ mv: bk.mv, route: "book", ms: Date.now() - t0, depth: 0, nodes: 0 }) + "\n");
      return;
    }
  }
  const mvs = E.legal(b, side);
  if (!mvs.length) { process.stdout.write(JSON.stringify({ mv: 0 }) + "\n"); return; }
  deadline = t0 + BUDGET;
  nodes = 0;
  const rep = new Set(req.history || hist);
  let best = mvs[0], bestVal = -Infinity, doneDepth = 0;
  const rootOrder = order(b, side, mvs);
  // 先用一步估值排出根候选，随后迭代加深
  const first = [];
  for (const mv of rootOrder) {
    const cap = b[E.tOf(mv)];
    b[E.tOf(mv)] = b[E.fOf(mv)]; b[E.fOf(mv)] = 0;
    first.push({ mv, v: -ev(b, -side) - danger(b, side, req.mvs ? req.mvs.length : 0) });
    b[E.fOf(mv)] = b[E.tOf(mv)]; b[E.tOf(mv)] = cap;
  }
  first.sort((x, y) => y.v - x.v);
  const roots = first.map((x) => x.mv);
  best = roots[0];
  for (let d = 1; d <= MAXD; d++) {
    let alpha = -Infinity, localBest = null, localVal = -Infinity;
    for (const mv of roots) {
      const cap = b[E.tOf(mv)];
      b[E.tOf(mv)] = b[E.fOf(mv)]; b[E.fOf(mv)] = 0;
      const v = -ab(b, -side, d - 1, -Infinity, -alpha, 1) - danger(b, side, req.mvs ? req.mvs.length : 0);
      b[E.fOf(mv)] = b[E.tOf(mv)]; b[E.tOf(mv)] = cap;
      if (aborted) break;
      if (v > localVal) { localVal = v; localBest = mv; }
      if (v > alpha) alpha = v;
    }
    if (localBest && !aborted) { best = localBest; bestVal = localVal; doneDepth = d; }
    if (aborted || Math.abs(bestVal) > MATE - 100) break;
  }
  process.stdout.write(JSON.stringify({ mv: best, value: bestVal, depth: doneDepth,
    nodes, ms: Date.now() - t0, aborted }) + "\n");
});
