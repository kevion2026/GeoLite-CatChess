/* 把 book_build.py 的原始开局库压成引擎键索引的 book.json。 */

const fs = require("fs");
const XQ = require("./engine.js");

const raw = JSON.parse(fs.readFileSync("data/book_raw.json", "utf8"));
const entries = {};
let keptMoves = 0;
const sizeLimit = 1200 * 1024; // 目标体积上限，超出则提高门槛重切

function pack(minGames, maxMoves) {
  const out = {};
  let n = 0;
  for (const e of raw.entries) {
    if (e.n < minGames) continue;
    const rows = e.m.filter((r) => r[1] >= 2).slice(0, maxMoves);
    if (!rows.length) continue;
    out[XQ.keyOf(e.b, e.s)] = rows;
    n += rows.length;
  }
  return { out, n };
}

let plan = { minGames: 3, maxMoves: 4 };
let packed = pack(plan.minGames, plan.maxMoves);
let json = JSON.stringify({ plies: raw.plies, games: raw.games, entries: packed.out });
while (Buffer.byteLength(json) > sizeLimit && plan.minGames < 60) {
  plan.minGames += 5;
  packed = pack(plan.minGames, plan.maxMoves);
  json = JSON.stringify({ plies: raw.plies, games: raw.games, entries: packed.out });
}

fs.writeFileSync("data/book.json", json);
const mb = (Buffer.byteLength(json) / 1024).toFixed(0);
console.log("门槛", plan, "局面", Object.keys(packed.out).length, "着法行", packed.n, mb + " KB");

// 抽样自检：开局局面应命中“炮二平五”一类主流着法
const b = XQ.initial();
const bk = JSON.parse(json);
const key = XQ.keyOf(b, XQ.RED);
const rows = bk.entries[key];
console.log("init 命中", rows ? rows.length : 0, rows ? rows.slice(0, 3) : null);
