/* GeoLite 走子服务：stdin 一行一个 JSON {mvs:[..]}，stdout 返回一个着法。
   第四个参数为模式：pro（默认，含静态交换估值与战术回应）或 base（旧路径，仅用于对照）。*/
const fs = require("fs");
const path = require("path");
global.MODEL3D = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
global.XQ3 = require(path.resolve(process.argv[3]));
const E = global.XQ3;
E.setModel(global.MODEL3D);
if (process.env.GEO_BOOK) {
  E.setBook(JSON.parse(require("fs").readFileSync(process.env.GEO_BOOK, "utf8")));
} else if (global.MODEL3D.book) {
  E.setBook(global.MODEL3D.book);
}
const MODE = process.argv[4] || process.env.GEO_MODE || "default";
if (process.env.GEO_SEED) {
  let s = (Number(process.env.GEO_SEED) || 1) >>> 0;
  Math.random = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
const MW = [0.69, 0.75, 0.55, 0.32, 0.62, 0, 0, 0, 0];
const MS = [0.69, 0.75, 0.55, 0.32, 0.62, 0.6, 0, 0.5, 0.3];
// 盲区补丁：dev=出子差(+112/子)，cblk=炮被闷(+46.75/遮挡)
const BL05 = MS.concat([56, 23.4]);
const BL10 = MS.concat([112, 46.75]);
const MODES = {
  // 产品默认：与 sym2 完全一致（闭合层结构项 + 宽根 + 对称化估值 + 3 层强制手）
  default: { dangerW: 300 },   // 知己：崩盘预警惩罚（300 局三种子实测速败 13.7%→2.7%）
  nobook: { book: false },
  bk: { book: false, bookCand: true },
  // 实战学习层：rc=知彼（学习回应集），dng=知己（崩盘惩罚）
  rc: { replyModel: true },
  cl: { closure: MS, dangerW: 300 },        // 复检：新树是否丢了闭合层
  mx30: { dangerW: 300, mix: 0.30 },
  mx60: { dangerW: 300, mix: 0.60 },
  h07: { dangerW: 300, hScale: 0.7 },
  h10: { dangerW: 300, hScale: 1.0 },
  h15: { dangerW: 300, hScale: 1.5 },
  h25: { dangerW: 300, hScale: 2.5 },
  h40: { dangerW: 300, hScale: 4.0 },
  h60: { dangerW: 300, hScale: 6.0 },
  bl05: { closure: BL05, dangerW: 300 },
  bl10: { closure: BL10, dangerW: 300 },
  bke2: { bookEval: 0.02 },
  bke5: { bookEval: 0.05 },
  bke10: { bookEval: 0.10 },
  rcev: { replyModel: true, agg: "ev" },
  rcev4: { replyModel: true, agg: "ev", replyK: 4 },
  rc6: { replyModel: true, replyK: 6 },
  rc4: { replyModel: true, replyK: 4 },
  dng: { dangerW: 300 },
  dng150: { dangerW: 150 },
  dng600: { dangerW: 600 },
  hist: { dangerW: 300, historyTrack: true, historyTop: 2 },
  hist4: { dangerW: 300, historyTrack: true, historyTop: 4 },
  hybrid: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 3, verifyTop: 6, verifyCap: 12000, verifyQ: 2, verifyThreat: 4, sym: true },
  hybrid2: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 2, verifyThreat: 2, sym: true },
  h2t1: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 2, verifyThreat: 1, sym: true },
  h2t3: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 2, verifyThreat: 3, sym: true },
  h2d3: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 3, verifyTop: 8, verifyCap: 16000, verifyQ: 2, verifyThreat: 2, sym: true },
  h2q0: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, sym: true },
  h1q0: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 1, sym: true },
  h3q0: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 3, sym: true },
  h2q0d3: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 3, verifyTop: 8, verifyCap: 16000, verifyQ: 0, verifyThreat: 2, sym: true },
  h2q0t12: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 12, verifyCap: 16000, verifyQ: 0, verifyThreat: 2, sym: true },
  h2m25: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, verifyMix: 0.25, sym: true },
  h2m35: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, verifyMix: 0.35, sym: true },
  h2m55: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, verifyMix: 0.55, sym: true },
  h2veto: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, verifyVeto: true, sym: true },
  h2d600: { dangerW: 600, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, sym: true },
  h2d900: { dangerW: 900, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, sym: true },
  h2d1500: { dangerW: 1500, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, sym: true },
  h2d2400: { dangerW: 2400, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, sym: true },
  nnhf: { dangerW: 300, forceHgb: true },
  nnhf600: { dangerW: 600, forceHgb: true },
  nnh2: { dangerW: 300, forceHgb: true, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 0, verifyThreat: 2, historyTrack: true, historyTop: 2, sym: true },
  nnall: { dangerW: 300, rootAll: true, rootKeep: 20, forceHgb: true, sym: true },
  nnall16: { dangerW: 300, rootAll: true, rootKeep: 16, forceHgb: true, sym: true },
  npol: { dangerW: 300, forceHgb: true, policyW: 100, sym: true },
  npol50: { dangerW: 300, forceHgb: true, policyW: 50, sym: true },
  npol200: { dangerW: 300, forceHgb: true, policyW: 200, sym: true },
  npol5: { dangerW: 300, forceHgb: true, policyW: 200, force: 5, forceCap: 1500, forceTop: 8, sym: true },
  deep5: { deepDepth: 5, deepQ: 4, deepCap: 300000, dangerW: 300 },
  deep6: { deepDepth: 6, deepQ: 4, deepCap: 400000, dangerW: 300 },
  deep7: { deepDepth: 7, deepQ: 4, deepCap: 600000, dangerW: 300 },
  deep8: { deepDepth: 8, deepQ: 5, deepCap: 900000, dangerW: 300 },
  dnn4: { deepDepth: 4, deepQ: 3, deepCap: 12000, deepEval: 'nn', deepKeep: 8, sym: true },
  dnn5: { deepDepth: 5, deepQ: 3, deepCap: 20000, deepEval: 'nn', deepKeep: 8, sym: true },
  ps1s: { proMs: 1000, proDepth: 10 },
  ps3s: { proMs: 3000, proDepth: 12 },
  ps3nb: { book: false, proMs: 3000, proDepth: 14 },
  ps10s: { proMs: 10000, proDepth: 14 },
  ps10nb: { book: false, proMs: 10000, proDepth: 18 },
  ps30nb: { book: false, proMs: 30000, proDepth: 24 },
  ps30s: { proMs: 30000, proDepth: 16 },
  h2c: { dangerW: 300, historyTrack: true, historyTop: 2, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 2, verifyThreat: 2, verifyEval: 'classic', sym: true },
  rcd: { replyModel: true, dangerW: 300 },
  // 以下为历史实验档，sym:false 保持各自当时的口径（对称化是后加的统一开关）
  cl0: { closure: null, q: 0, sym: false },
  clm: { closure: MW, q: 0, sym: false },
  clmq: { closure: MW, q: 2, sym: false },
  cls: { closure: MS, q: 0, sym: false },
  cw: { closure: MW, q: 2, width: 5, forceTop: 8, force: 3, forceCap: 400, sym: false },
  sym: { closure: MW, q: 2, width: 5, forceTop: 8, force: 3, forceCap: 400, sym: true },
  sym2: { closure: MS, q: 2, width: 5, forceTop: 8, force: 3, forceCap: 400, sym: true },
  symmean: { closure: MW, q: 2, width: 5, forceTop: 8, force: 3, forceCap: 400, sym: true, agg: "mean" },
  base: { pro: false, width: 3, force: 0, q: 0, sym: false },
  tac6: { pro: true, rootTactics: true, agg: "mix", force: 3, forceTop: 6, width: 4, q: 0, sym: false },
  deep: { dangerW: 0, width: 6, force: 4, forceTop: 10, forceCap: 900, q: 3, rootAll: true, rootKeep: 18, sym: false },
  deep2: { dangerW: 300, width: 6, force: 5, forceTop: 12, forceCap: 1400, q: 3, rootAll: true, rootKeep: 22, sym: true },
  c30: { dangerW: 300, classicW: 0.30, sym: true },
  c40: { dangerW: 300, classicW: 0.40, sym: true },
  c30s: { dangerW: 300, classicW: 0.30, sym: false },
  c40s: { dangerW: 300, classicW: 0.40, sym: false },
  c60: { dangerW: 300, classicW: 0.60, sym: true },
  c100: { dangerW: 0, classicW: 1.0, sym: true },
  f6: { dangerW: 300, width: 8, force: 6, forceTop: 12, forceCap: 2600, q: 3, rootAll: true, rootKeep: 24, sym: true },
  f6b: { book: false, dangerW: 300, width: 8, force: 6, forceTop: 12, forceCap: 2600, q: 3, rootAll: true, rootKeep: 24, sym: true },
  f8: { dangerW: 300, width: 8, force: 8, forceTop: 10, forceCap: 4000, q: 4, rootAll: true, rootKeep: 24, sym: true },
  c100f6: { dangerW: 0, classicW: 1.0, width: 8, force: 6, forceTop: 12, forceCap: 2600, q: 3, rootAll: true, rootKeep: 24, sym: true },
  full: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 3, verifyTop: 6, verifyCap: 12000, rootAll: true, rootKeep: 16, sym: true },
  full4: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 4, verifyTop: 5, verifyCap: 16000, rootAll: true, rootKeep: 16, sym: true },
  veto: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 3, verifyTop: 8, verifyCap: 16000, verifyVeto: true, rootAll: true, rootKeep: 16, sym: true },
  vetoC: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 3, verifyTop: 8, verifyCap: 16000, verifyVeto: true, verifyEval: 'classic', rootAll: true, rootKeep: 16, sym: true },
  fullC: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 3, verifyTop: 6, verifyCap: 12000, verifyEval: 'classic', rootAll: true, rootKeep: 16, sym: true },
  fullQ: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 3, verifyTop: 6, verifyCap: 16000, verifyQ: 3, rootAll: true, rootKeep: 16, sym: true },
  fullQ4: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 4, verifyTop: 5, verifyCap: 20000, verifyQ: 3, rootAll: true, rootKeep: 16, sym: true },
  opp1: { dangerW: 300, width: 5, force: 3, forceTop: 8, forceCap: 400, verifyDepth: 2, verifyTop: 8, verifyCap: 12000, verifyQ: 2, verifyVeto: true, rootAll: true, rootKeep: 16, sym: true }
};

const INIT = E.initial();

const rl = require("readline").createInterface({ input: process.stdin });
rl.on("line", (line) => {
  let req;
  try { req = JSON.parse(line); } catch (e) { return; }
  /* 重复局面必须用引擎自己的 Zobrist 键：Python 的 hash(fen) 带进程随机化，
     和 JS 的 hashBoard 永远不相等，之前的“重复扣分”在评测里其实一直是死代码。 */
  let b = INIT.slice();
  let side = E.RED;
  if (req.board) {                 // 静态局面直供（固定局面基准用），跳过重放
    b = req.board.slice();
    side = req.side || E.RED;
    req.mvs = req.mvs || [];
  }
  const hist = [E.keyOf(b, side)];
  for (const mv of req.mvs) {
    b[E.tOf(mv)] = b[E.fOf(mv)];
    b[E.fOf(mv)] = 0;
    side = -side;
    hist.push(E.keyOf(b, side));
  }
  const cfg = MODES[MODE] || MODES.default;
  if (cfg.closure !== undefined) E.setClosure(cfg.closure);
  if (cfg.hScale) E.setHScale(cfg.hScale);   // 未指定则沿用模型自带权重
  // ply 必须传真实手数：崩盘模型的输入含 ply/50，钉成常数会让它偏离训练分布
  const r = E.routePlay(b, side, Object.assign({ noise: 0, history: hist, ply: hist.length }, cfg));
  process.stdout.write(JSON.stringify({
    mv: r.mv, route: r.route, by: r.by, ms: r.ms,
    cpL: r.localCand ? r.localCand.cp : null,
    cpG: r.globalCand ? r.globalCand.cp : null,
    pW: r.localCand && r.localCand.pWin !== undefined ? r.localCand.pWin : null,
    cands: r.search && r.search.rows ? r.search.rows.slice(0, 14).map((x) => x.mv) : [],
    top: r.search && r.search.rows && r.search.rows.length ? r.search.rows[0].mv : null
  }) + "\n");
});
