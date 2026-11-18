/* 从实战轨迹训练两个线性层（不是神经网络，只是查表打分）：
 *
 *   知彼 reply  ：给定局面，在全部合法着上做条件 logit（softmax），
 *                 预测「皮卡鱼实际会走哪一步」。用途：把搜索里"猜对手回应"
 *                 从"用我们自己的引力去猜"换成"用实战学到的对手偏好去猜"。
 *   知己 danger ：给定"我刚走完、对手该走"的局面，预测我方是否即将崩盘
 *                 （8 手内掉子 ≥250 或 12 手内被将死）。用途：给根部候选加风险惩罚。
 *
 * 特征与推理共用 engine3d.js 里的 battleFeats / dangerFeats，避免两端漂移。
 *
 * 用法：node train_battle.js --ds data/battle_ds.json --model model_triple.json --save
 */

const fs = require("fs");

const args = {};
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (a.startsWith("--")) {
    const k = a.slice(2);
    const v = process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[++i] : true;
    args[k] = v;
  }
}
const DS = args.ds || "data/battle_ds.json";
const MODEL_PATH = args.model || "model_triple.json";
const SAVE = !!args.save;
const SEED = Number(args.seed || 20261115);

global.MODEL3D = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
const E = require("./engine3d.js");
E.setModel(global.MODEL3D);
E.setBook(global.MODEL3D.book);

/* ---------- 工具 ---------- */
let _s = SEED >>> 0;
function rnd() { _s = (_s * 1664525 + 1013904223) >>> 0; return _s / 4294967296; }
function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    const t = a[i]; a[i] = a[j]; a[j] = t;
  }
  return a;
}

function matBalance(b, side) {
  let m = 0;
  for (let s = 0; s < 90; s++) {
    const q = b[s];
    if (q) m += ((q > 0) === (side > 0) ? 1 : -1) * (E.VALUE[Math.abs(q)] || 0);
  }
  return m;
}

function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }

/* ---------- 读数据 ---------- */
const ds = JSON.parse(fs.readFileSync(DS, "utf8"));
const games = ds.games;
console.log("对局", games.length, "总局面", games.reduce((a, g) => a + g.rows.length, 0));

const cut = Math.floor(games.length * 0.75);
const train = games.slice(0, cut);
const test = games.slice(cut);

/* ---------- 构造样本 ---------- */
function buildSamples(list) {
  const reply = [];   // {X: Float32Array[](n×20), y: int, ply}
  const danger = [];  // {x: Float32Array(47), y: 0/1}
  let posCount = 0, negDanger = 0, posDanger = 0;
  for (const g of list) {
    const rows = g.rows;
    const ourSide = g.ours_red ? 1 : -1;
    const mats = rows.map((r) => matBalance(r[0], ourSide));
    const lossAt = g.res === "loss" ? rows.length : -1;
    for (let i = 0; i < rows.length; i++) {
      const [board, side, mv, who] = rows[i];
      if (who !== 0) continue;            // 只看"对手该走"的局面
      if (i < 2) continue;                // 跳过固定开局两着
      const b = board.slice();
      const legal = E.legal(b, side);
      if (legal.length < 3) continue;
      const y = legal.indexOf(mv);
      if (y < 0) continue;

      // 知彼样本：全部合法着各算一次特征
      const X = new Array(legal.length);
      for (let k = 0; k < legal.length; k++) {
        const f = E.battleFeats(b, side, legal[k]);
        X[k] = Float32Array.from(f);
      }
      reply.push({ X, y, ply: i });
      posCount++;

      // 知己样本：这个局面（视角=我方）危险吗
      let drop = 0;
      const m0 = mats[i];
      for (let j = i; j < Math.min(rows.length, i + 9); j++) drop = Math.max(drop, m0 - mats[j]);
      const mateSoon = lossAt >= 0 && (lossAt - i) <= 12;
      const lab = (drop >= 250 || mateSoon) ? 1 : 0;
      if (lab) posDanger++; else negDanger++;
      danger.push({ x: E.dangerFeats(b, ourSide, i), y: lab });
    }
  }
  return { reply, danger, posCount, negDanger, posDanger };
}

const TR = buildSamples(train);
const TE = buildSamples(test);
console.log("训练局面", TR.posCount, " 校验局面", TE.posCount,
  "| 危险正例", TR.posDanger, "/", TR.posCount, "(" + (100 * TR.posDanger / TR.posCount).toFixed(1) + "%)");

/* ---------- 知彼：条件 logit ---------- */
function trainReply(samples, dim, epochs, lr, l2) {
  const w = new Float64Array(dim + 1);
  let order = samples.slice();
  for (let ep = 0; ep < epochs; ep++) {
    shuffle(order);
    let loss = 0, correct = 0;
    for (const s of order) {
      const X = s.X, n = X.length;
      const sc = new Float64Array(n);
      let mx = -Infinity;
      for (let i = 0; i < n; i++) {
        let t = 0;
        const x = X[i];
        for (let k = 0; k < dim; k++) t += w[k] * x[k];
        sc[i] = t; if (t > mx) mx = t;
      }
      let Z = 0;
      const p = new Float64Array(n);
      for (let i = 0; i < n; i++) { p[i] = Math.exp(sc[i] - mx); Z += p[i]; }
      let best = 0;
      for (let i = 1; i < n; i++) if (sc[i] > sc[best]) best = i;
      if (best === s.y) correct++;
      loss += Math.log(Z) + mx - sc[s.y];
      // 梯度（按候选数归一，否则候选多的局面主导更新）
      const grad = new Float64Array(dim + 1);
      for (let i = 0; i < n; i++) {
        const gI = p[i] / Z - (i === s.y ? 1 : 0);
        if (gI === 0) continue;
        const x = X[i];
        for (let k = 0; k < dim; k++) grad[k] += gI * x[k];
      }
      for (let k = 0; k < dim; k++) w[k] -= lr * (grad[k] / n + l2 * w[k]);
      w[dim] -= lr * grad[dim] / n;
    }
    if (ep === epochs - 1 || ep % 4 === 0) {
      console.log("  reply ep%2d  loss %.4f  top1 %.3f", ep, loss / order.length, correct / order.length);
    }
  }
  return w;
}

function evalReply(w, samples, dim) {
  let t1 = 0, t3 = 0, n = samples.length;
  for (const s of samples) {
    const sc = new Float64Array(s.X.length);
    for (let i = 0; i < s.X.length; i++) {
      let t = 0; const x = s.X[i];
      for (let k = 0; k < dim; k++) t += w[k] * x[k];
      sc[i] = t;
    }
    const idx = Array.from(sc.keys()).sort((a, b) => sc[b] - sc[a]);
    if (idx[0] === s.y) t1++;
    if (idx.slice(0, 3).includes(s.y)) t3++;
  }
  return { top1: t1 / n, top3: t3 / n };
}

/* 基线：现在引擎实际看到的那套回应集（吃子 SEE>0 / 叫将 / 引力前二，上限 5） */
function baselineCoverage(samples) {
  let hit = 0, tot = 0;
  for (const s of samples) {
    // 训练样本里没有保存局面，这里用"候选特征本身"无法还原，
    // 所以基线覆盖率在 buildSamples 时可另行统计（见 coverage 字段）。
    tot++;
  }
  return hit / Math.max(1, tot);
}

console.log("\n训练知彼模型...");
const wReply = trainReply(TR.reply, 20, 12, 0.35, 1e-5);
const rTrain = evalReply(wReply, TR.reply, 20);
const rTest = evalReply(wReply, TE.reply, 20);
console.log("知彼：训练 top1 %.3f top3 %.3f | 校验 top1 %.3f top3 %.3f",
  rTrain.top1, rTrain.top3, rTest.top1, rTest.top3);
console.log("知彼权重", Array.from(wReply).map((x) => +x.toFixed(3)).join(","));

/* ---------- 知己：logistic ---------- */
function trainLogit(samples, dim, epochs, lr, l2) {
  const w = new Float64Array(dim + 1);
  const pos = samples.filter((s) => s.y === 1).length;
  const neg = samples.length - pos;
  const wPos = samples.length / (2 * Math.max(1, pos));
  const wNeg = samples.length / (2 * Math.max(1, neg));
  let order = samples.slice();
  for (let ep = 0; ep < epochs; ep++) {
    shuffle(order);
    let loss = 0;
    const grad = new Float64Array(dim + 1);
    for (const s of order) {
      let t = w[dim];
      for (let k = 0; k < dim; k++) t += w[k] * s.x[k];
      const p = sigmoid(t);
      const sw = s.y === 1 ? wPos : wNeg;       // 类别不平衡加权
      const g = (p - s.y) * sw;
      loss += -sw * (s.y * Math.log(p + 1e-9) + (1 - s.y) * Math.log(1 - p + 1e-9));
      for (let k = 0; k < dim; k++) grad[k] += g * s.x[k];
      grad[dim] += g;
    }
    for (let k = 0; k < dim; k++) w[k] -= lr * (grad[k] / order.length + l2 * w[k]);
    w[dim] -= lr * grad[dim] / order.length;
    if (ep === epochs - 1 || ep % 100 === 0) console.log("  danger ep%3d  loss %.4f", ep, loss / order.length);
  }
  return w;
}

function auc(w, samples, dim) {
  const sc = samples.map((s) => {
    let t = w[dim];
    for (let k = 0; k < dim; k++) t += w[k] * s.x[k];
    return { p: sigmoid(t), y: s.y };
  });
  sc.sort((a, b) => a.p - b.p);
  let rankSum = 0, pos = 0;
  for (let i = 0; i < sc.length; i++) if (sc[i].y === 1) { rankSum += i + 1; pos++; }
  const neg = sc.length - pos;
  if (!pos || !neg) return 0.5;
  return (rankSum - pos * (pos + 1) / 2) / (pos * neg);
}

console.log("\n训练知己模型...");
const wDanger = trainLogit(TR.danger, 47, 400, 0.5, 2e-4);
console.log("知己：校验 AUC %.3f（训练 %.3f）", auc(wDanger, TE.danger, 47), auc(wDanger, TR.danger, 47));

// 阈值化后的判别率
function cls(w, samples, dim, th) {
  let tp = 0, fp = 0, fn = 0, tn = 0;
  for (const s of samples) {
    let t = w[dim];
    for (let k = 0; k < dim; k++) t += w[k] * s.x[k];
    const p = sigmoid(t) >= th ? 1 : 0;
    if (p === 1 && s.y === 1) tp++;
    else if (p === 1 && s.y === 0) fp++;
    else if (p === 0 && s.y === 1) fn++;
    else tn++;
  }
  return { tp, fp, fn, tn, prec: tp / Math.max(1, tp + fp), rec: tp / Math.max(1, tp + fn) };
}
const c = cls(wDanger, TE.danger, 47, 0.5);
console.log("知己：阈值0.5 精确率 %.3f 召回 %.3f (tp%d fp%d fn%d tn%d)", c.prec, c.rec, c.tp, c.fp, c.fn, c.tn);

/* ---------- 落盘 ---------- */
if (SAVE) {
  const m = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
  m.battle = {
    reply: { w: Array.from(wReply).map((x) => +x.toFixed(5)), dim: 20 },
    danger: { w: Array.from(wDanger).map((x) => +x.toFixed(5)), dim: 47 },
    meta: {
      ds: DS, games: games.length,
      reply_top1: +rTest.top1.toFixed(4), reply_top3: +rTest.top3.toFixed(4),
      danger_auc: +auc(wDanger, TE.danger, 47).toFixed(4),
      danger_prec: +c.prec.toFixed(4), danger_rec: +c.rec.toFixed(4),
      trained: new Date().toISOString().slice(0, 10),
    },
  };
  fs.writeFileSync(MODEL_PATH, JSON.stringify(m));
  console.log("\n已写入", MODEL_PATH, "battle 段");
}
