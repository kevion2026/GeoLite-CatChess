/* 对拍：浏览器侧几何复算 vs 引擎纯几何版（xq17.exe）
 *
 * 浏览器里画出来的专家激活、树分，必须和 C++ 算的是同一件事，
 * 否则右侧面板就是装饰而不是仪表。这里用同一批局面直接比对数值。
 *
 *   node web/_check_geo.js ../xq17.exe
 */
"use strict";
const { spawn } = require("child_process");
const path = require("path");

// geo_model.js 是给浏览器写的（window.GEO_MODEL），在 node 里给它一个 window
globalThis.window = globalThis;

require(path.join(__dirname, "xq_rules.js"));
require(path.join(__dirname, "geo_model.js"));
require(path.join(__dirname, "geo_browser.js"));
const X = globalThis.XQ;
const GEOC = globalThis.GEOC;
const G = globalThis.GEO_MODEL;

const EXE = process.argv[2] || path.join(__dirname, "..", "xq17.exe");
const N = Number(process.argv[3] || 40);

/* ---------- 造局面：固定种子的随机对局 ---------- */
let seed = 20261117 >>> 0;
function rnd() {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296;
}

const cases = [];
{
  const b = X.parseFen(X.START_FEN).b;
  let side = X.RED;
  const moves = [];
  for (let ply = 0; ply < 34; ply++) {
    const legal = X.legalMoves(b, side);
    if (!legal.length) break;
    const mv = legal[(rnd() * legal.length) | 0];
    if (ply >= 2 && (ply % 3 === 0 || ply > 26)) {
      cases.push({ moves: moves.slice(), fenBefore: X.toFen(b, side), side });
      if (cases.length >= N) break;
    }
    const f = (mv / 100) | 0, t = mv % 100;
    b[t] = b[f]; b[f] = 0;
    side = -side;
    moves.push(mv);
  }
}

/* ---------- 问引擎 ---------- */
function askEngine(cases) {
  return new Promise((resolve, reject) => {
    const p = spawn(EXE, [], { windowsHide: true });
    let buf = "", err = "";
    const out = [];
    const need = cases.length;
    p.stdout.setEncoding("utf8");
    p.stderr.setEncoding("utf8");
    p.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (/^-?\d+$/.test(line)) {
          out.push(Number(line));
          if (out.length === need) {
            p.stdin.write("quit\n");
            resolve(out);
          }
        }
      }
    });
    p.stderr.on("data", (d) => { err += d; });
    p.on("exit", () => { if (out.length < need) reject(new Error("引擎只回了 " + out.length + "/" + need + " " + err)); });
    p.on("error", reject);

    let cmd = "uci\n";
    for (const c of cases) {
      cmd += "position startpos" + (c.moves.length ? " moves " + c.moves.map(X.uciOf).join(" ") : "") + "\n";
      cmd += "eval\n";
    }
    p.stdin.write(cmd);
  });
}

/* ---------- 复算 ---------- */
function jsScore(c) {
  const { b, side } = X.parseFen(X.START_FEN);
  let sd = side;
  for (const mv of c.moves) {
    const f = (mv / 100) | 0, t = mv % 100;
    b[t] = b[f]; b[f] = 0;
    sd = -sd;
  }
  const r = GEOC.feats45(b, sd);
  const tr = GEOC.treeScore45(r.f);
  return { score: tr.score, tree: tr.tree, glob: tr.glob, toks: r.toks };
}

(async function () {
  console.log("引擎:", EXE);
  console.log("局面数:", cases.length, "| 模型: dim=" + G.dim, "K=" + G.k);
  const eng = await askEngine(cases);
  let maxAbs = 0, sum = 0, worst = null;
  const rows = [];
  for (let i = 0; i < cases.length; i++) {
    const js = jsScore(cases[i]);
    const d = js.score - eng[i];
    maxAbs = Math.max(maxAbs, Math.abs(d));
    sum += Math.abs(d);
    rows.push({ i, eng: eng[i], js: js.score.toFixed(2), d: d.toFixed(3), toks: js.toks });
    if (!worst || Math.abs(d) > Math.abs(worst.d)) worst = { i, d, fen: cases[i].fenBefore };
  }
  const show = rows.slice(0, 12);
  for (const r of show) console.log(`  #${String(r.i).padStart(2)} 引擎 ${String(r.eng).padStart(6)}  JS ${r.js.padStart(8)}  差 ${r.d.padStart(8)}  令牌 ${r.toks}`);
  console.log("---");
  console.log("平均绝对差:", (sum / cases.length).toFixed(4), "cp");
  console.log("最大绝对差:", maxAbs.toFixed(4), "cp");
  if (worst) console.log("最差局面 #" + worst.i + " 差 " + worst.d.toFixed(3) + "\n  " + worst.fen);
  console.log(maxAbs < 0.6 ? "✓ 两边一致" : "✗ 差异过大，需检查");
  process.exit(maxAbs < 0.6 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
