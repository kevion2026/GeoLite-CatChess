/* 盲区诊断：几何树看不见什么？
 *
 * 做法：对实战里"对手该走"的每个局面，算
 *     残差 = 皮卡鱼评分(换到我方视角) − 几何树评分(我方视角)
 * 再把残差回归到一组**当前 45 维里没有的**几何描述量上。
 * 系数大且稳定的那一项，就是几何树的结构性盲区。
 *
 * 注意：这里只做诊断，不改模型。
 */
const fs = require("fs");
const E = require("./engine3d.js");

global.MODEL3D = JSON.parse(fs.readFileSync("model_triple.json", "utf8"));
E.setModel(global.MODEL3D);
E.setBook(global.MODEL3D.book);
const SEG = global.MODEL3D.tree.model;
const VAL = E.VALUE;

const ds = JSON.parse(fs.readFileSync("data/battle_ds.json", "utf8"));

/* ---------- 候选描述量 ---------- */
function pawnInfo(b, side) {
  const file = new Array(9).fill(0);
  for (const q of b) if (q && Math.abs(q) === E.PAWN && (q > 0) === (side > 0)) file[Math.abs(q) ? q % 9 : 0]++;
  return null;
}

function desc(b, side) {
  const d = [];
  const own = (q) => (q > 0) === (side > 0);

  // 1. 机动性差（合法着数量之差）
  const mo = E.legal(b, side).length, mt = E.legal(b, -side).length;
  d.push((mo - mt) / 10);

  // 2. 炮的"架子"与"靶子"：无架之炮近乎废子
  let screen = 0, target = 0, dead = 0;
  for (let s = 0; s < 90; s++) {
    const q = b[s];
    if (!q || Math.abs(q) !== E.CANNON || !own(q)) continue;
    const x = s % 9, y = (s / 9) | 0;
    let t = 0, sc = 0;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      let nx = x + dx, ny = y + dy, seen = 0;
      while (nx >= 0 && nx < 9 && ny >= 0 && ny < 10) {
        const p = b[ny * 9 + nx];
        if (p) {
          if (seen === 0) { seen = 1; sc++; }
          else { if (!own(p)) t++; break; }
        }
        nx += dx; ny += dy;
      }
    }
    screen += sc; target += t;
    if (!t && !sc) dead++;
  }
  d.push(screen / 4, target / 3, dead);

  // 3. 车在开放/半开放线上的数量（与闭合层口径不同：这里数"两条线都没有己兵"）
  let openR = 0;
  for (let s = 0; s < 90; s++) {
    const q = b[s];
    if (!q || Math.abs(q) !== E.ROOK || !own(q)) continue;
    const x = s % 9;
    let ownPawn = 0, anyPawn = 0;
    for (let y = 0; y < 10; y++) {
      const p = b[y * 9 + x];
      if (p && Math.abs(p) === E.PAWN) { anyPawn++; if (own(p)) ownPawn++; }
    }
    if (!ownPawn) openR += anyPawn ? 0.5 : 1;
  }
  d.push(openR / 2);

  // 4. 对敌方九宫的控制（被攻击的宫格数之差）
  const palace = (sd) => {
    const ys = sd === E.RED ? [0, 1, 2] : [7, 8, 9];
    const out = [];
    for (const y of ys) for (let x = 3; x <= 5; x++) out.push(y * 9 + x);
    return out;
  };
  let pAtk = 0, pDef = 0;
  for (const s of palace(-side)) if (E.attacked(b, s, side)) pAtk++;
  for (const s of palace(side)) if (E.attacked(b, s, -side)) pDef++;
  d.push((pAtk - pDef) / 4);

  // 5. 出子：仍留在本方底线两排的大子数（车马炮）
  let undeveloped = 0, oppUndeveloped = 0;
  for (let s = 0; s < 90; s++) {
    const q = b[s];
    if (!q) continue;
    const ty = Math.abs(q);
    if (ty !== E.ROOK && ty !== E.HORSE && ty !== E.CANNON) continue;
    const y = (s / 9) | 0;
    const back = own(q) ? (side === E.RED ? y >= 8 : y <= 1) : (side === E.RED ? y <= 1 : y >= 8);
    if (back) { if (own(q)) undeveloped++; else oppUndeveloped++; }
  }
  d.push((oppUndeveloped - undeveloped) / 3);

  // 6. 兵的结构：叠兵 / 过河兵差
  let dbl = 0, crossed = 0, oppCrossed = 0;
  const fileOwn = new Array(9).fill(0);
  for (let s = 0; s < 90; s++) {
    const q = b[s];
    if (!q || Math.abs(q) !== E.PAWN) continue;
    const x = s % 9, y = (s / 9) | 0;
    if (own(q)) {
      fileOwn[x]++;
      if (side === E.RED ? y <= 4 : y >= 5) crossed++;
    } else if (side === E.RED ? y >= 5 : y <= 4) oppCrossed++;
  }
  for (const c of fileOwn) if (c > 1) dbl += c - 1;
  d.push((crossed - oppCrossed) / 3, -dbl / 2);

  return d;
}

const NAMES = ["机动性差", "炮有架", "炮有靶", "死炮", "车活线", "攻宫差", "出子差", "过河兵差", "叠兵"];

/* ---------- 收集 ---------- */
const X = [], Y = [];
for (const g of ds.games) {
  const ourSide = g.ours_red ? 1 : -1;
  for (let i = 2; i < g.rows.length; i++) {
    const [board, side, mv, who, cp] = g.rows[i];
    if (who !== 0 || cp === null || cp === undefined) continue;
    const b = board.slice();
    const ts = E.treeScore(E.geometry(b, ourSide, 0, 0), SEG, b, ourSide);
    if (ts === null || !isFinite(ts)) continue;
    X.push(desc(b, ourSide));
    Y.push(-cp - ts);          // 我方视角：皮卡鱼说 -cp，减掉我们自己的评分
  }
}
console.log("样本", X.length, "维度", X[0].length);
console.log("残差 均值 %.1f 标准差 %.1f", Y.reduce((a, v) => a + v, 0) / Y.length,
  Math.sqrt(Y.reduce((a, v, i) => a + (v - Y.reduce((s, w) => s + w, 0) / Y.length) ** 2, 0) / Y.length));

/* ---------- 标准化 + 岭回归 ---------- */
const n = X.length, d = X[0].length;
const mean = new Array(d).fill(0), sd = new Array(d).fill(0);
for (let j = 0; j < d; j++) {
  let s = 0;
  for (let i = 0; i < n; i++) s += X[i][j];
  mean[j] = s / n;
  let v = 0;
  for (let i = 0; i < n; i++) v += (X[i][j] - mean[j]) ** 2;
  sd[j] = Math.sqrt(v / n) || 1;
}
const split = Math.floor(n * 0.75);
function fit(lam, lo, hi) {
  // (X'X + lam I) w = X'y
  const A = Array.from({ length: d }, () => new Array(d).fill(0));
  const b = new Array(d).fill(0);
  for (let i = lo; i < hi; i++) {
    const x = X[i].map((v, j) => (v - mean[j]) / sd[j]);
    const y = Y[i];
    for (let p = 0; p < d; p++) {
      b[p] += x[p] * y;
      for (let q = 0; q < d; q++) A[p][q] += x[p] * x[q];
    }
  }
  for (let p = 0; p < d; p++) A[p][p] += lam;
  // 高斯消元
  for (let c = 0; c < d; c++) {
    let piv = c;
    for (let r = c + 1; r < d; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
    if (Math.abs(A[piv][c]) < 1e-12) continue;
    [A[c], A[piv]] = [A[piv], A[c]];
    [b[c], b[piv]] = [b[piv], b[c]];
    const dd = A[c][c];
    for (let q = c; q < d; q++) A[c][q] /= dd;
    b[c] /= dd;
    for (let r = 0; r < d; r++) {
      if (r === c) continue;
      const f = A[r][c];
      if (!f) continue;
      for (let q = c; q < d; q++) A[r][q] -= f * A[c][q];
      b[r] -= f * b[c];
    }
  }
  return b;
}
function r2(w, lo, hi) {
  let ss = 0, tot = 0;
  const ym = Y.slice(lo, hi).reduce((a, v) => a + v, 0) / (hi - lo);
  for (let i = lo; i < hi; i++) {
    let p = 0;
    for (let j = 0; j < d; j++) p += w[j] * ((X[i][j] - mean[j]) / sd[j]);
    ss += (Y[i] - p) ** 2;
    tot += (Y[i] - ym) ** 2;
  }
  return 1 - ss / tot;
}

let best = null;
for (const lam of [1, 10, 100, 1000]) {
  const w = fit(lam, 0, split);
  const tr = r2(w, 0, split), te = r2(w, split, n);
  console.log("lam %5d  训练 R² %.3f  校验 R² %.3f", lam, tr, te);
  if (!best || te > best.te) best = { lam, w, tr, te };
}
console.log("\n最优 lam", best.lam, " 校验 R²", best.te.toFixed(3));
console.log("标准化系数（cp / 一个标准差）：");
const idx = [...Array(d).keys()].sort((a, b) => Math.abs(best.w[b]) - Math.abs(best.w[a]));
for (const j of idx) console.log("  %s %s  (mean %.3f sd %.3f → 原始尺度 %s cp/单位)",
  (NAMES[j] + "          ").slice(0, 8), (best.w[j] >= 0 ? "+" : "") + best.w[j].toFixed(1),
  mean[j], sd[j], (best.w[j] / sd[j]).toFixed(1));
