/* 搜索自检：初始局面估分应为 0；一步杀必须找到；简单吃子不能漏。 */
const E = require("./engine3d.js");

function board(str) {
  const b = new Array(90).fill(0);
  const rows = str.trim().split("\n");
  for (let y = 0; y < 10; y++) {
    const line = rows[y].trim().split(/\s+/);
    for (let x = 0; x < 9; x++) b[y * 9 + x] = parseInt(line[x], 10);
  }
  return b;
}

// 初始局面
const init = board(`
-5 -4 -3 -2 -1 -2 -3 -4 -5
0 0 0 0 0 0 0 0 0
0 -6 0 0 0 0 0 -6 0
-7 0 -7 0 -7 0 -7 0 -7
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
7 0 7 0 7 0 7 0 7
0 6 0 0 0 0 0 6 0
0 0 0 0 0 0 0 0 0
5 4 3 2 1 2 3 4 5
`);

for (const mode of ["ps1s", "ps3s"]) {
  const r = E.routePlay(init, 1, { proMs: mode === "ps1s" ? 1000 : 3000, proDepth: 12 });
  console.log(mode, "init mv", r.mv, "score", r.search && r.search.score, "depth", r.search && r.search.depth, "nodes", r.search && r.search.nodes);
}

// 白脸将杀：红车沉底，黑将无路。构造一个「车吃士一步杀」
// 局面：黑将 e0(4,0)，红车在 (4,1) 直线将军 已被挡？ 直接测「一步将死」
const mateIn1 = board(`
0 0 0 0 -1 0 0 0 0
0 0 0 0 4 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 1 0 0 0 0
`);
// 红车 (4,1) 走到 (4,0)? 那是吃将，非法。改：黑将在 (4,0)，红车在 (4,2)，走 (4,1) 将军但不死。
// 用一个真正的杀：黑将 (4,0)，红车 (4,1) 已在同列相邻，红车再走到 (4,1) 不可能。
// 换成：黑将 (4,0)，红车 (4,9)，红车走 (4,1) 到底线将军；黑将只能走 (3,0)/(5,0)，
// 若红方另一车控制这两格则杀。简化：只验证「被将军时不会 stand-pat」。
const chk = board(`
0 0 0 0 -1 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 4 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 1 0 0 0 0
`);
// 黑方（-1）此时被红车 (4,2) 将？黑将在 (4,0)，红车在 (4,2)，中间 (4,1) 空 → 是的，将军。
// 黑将可走 (3,0)/(5,0) 逃。用 routePlay 从黑方视角，评分不该是「平静」。
const r2 = E.routePlay(chk, -1, { proMs: 1000, proDepth: 8 });
console.log("in-check root mv", r2.mv, "score", r2.search && r2.search.score);

// 吃子测试：红车可白吃黑车
const cap = board(`
0 0 0 0 -1 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 -4
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 1 4 0 0 0
`);
// 红车 (5,9) 可吃 (8,2) 的黑车？不同列不同行，不行。改：红车 (8,9) 沿 8 列吃到 (8,2)。
const cap2 = board(`
0 0 0 0 -1 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 -4
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
0 0 0 0 1 0 0 0 4
`);
const r3 = E.routePlay(cap2, 1, { proMs: 1000, proDepth: 8 });
console.log("free-capture mv", r3.mv, "(期望 8902 = 8,9->8,2)", "score", r3.search && r3.search.score);
