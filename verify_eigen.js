// 校验解析特征分解：对随机点云，比较解析解与 5000 次幂迭代参考解
function refPower(pts) {
  let sw = 0; const s3 = [0, 0, 0];
  for (const p of pts) { sw += p.w; for (let i = 0; i < 3; i++) s3[i] += p.w * p.c[i]; }
  const c = s3.map((x) => x / sw);
  const cov = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const p of pts) {
    const d = [p.c[0] - c[0], p.c[1] - c[1], p.c[2] - c[2]];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] += p.w * d[i] * d[j];
  }
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] /= sw;
  let v = [0.577, 0.577, 0.577];
  for (let it = 0; it < 5000; it++) {
    const nv = [
      cov[0][0] * v[0] + cov[0][1] * v[1] + cov[0][2] * v[2],
      cov[1][0] * v[0] + cov[1][1] * v[1] + cov[1][2] * v[2],
      cov[2][0] * v[0] + cov[2][1] * v[1] + cov[2][2] * v[2]
    ];
    const n = Math.hypot(nv[0], nv[1], nv[2]);
    if (n < 1e-14) break;
    v = [nv[0] / n, nv[1] / n, nv[2] / n];
  }
  const idx = [Math.abs(v[0]), Math.abs(v[1]), Math.abs(v[2])].reduce((a, b, i, arr) => (b >= arr[a] ? i : a), 0);
  if (v[idx] < 0) v = [-v[0], -v[1], -v[2]];
  const lam = cov[0][0] * v[0] * v[0] + cov[1][1] * v[1] * v[1] + cov[2][2] * v[2] * v[2] +
    2 * (cov[0][1] * v[0] * v[1] + cov[0][2] * v[0] * v[2] + cov[1][2] * v[1] * v[2]);
  return { c, v, lam };
}

global.MODEL3D = JSON.parse(require("fs").readFileSync("model_triple.json", "utf8"));
const E = require("./engine3d.js");
E.setModel(global.MODEL3D);

// 用真实开局/中局局面的 token 点云 + 随机扰动
let worstAng = 0, worstLam = 0, n = 0, worstCase = null;
const rnd = (() => { let s = 12345; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; })();

const starts = [
  [],
  [[7, 7, 4, 7], [7, 0, 4, 0], [8, 9, 7, 7], [1, 9, 2, 7], [8, 7, 6, 6], [8, 9, 7, 9]],
  [[7, 7, 4, 7], [7, 0, 4, 0], [8, 9, 7, 7], [1, 9, 2, 7], [1, 7, 1, 0], [0, 0, 0, 1], [6, 9, 5, 7]]
];
for (const seq of starts) {
  let b = E.initial(), side = E.RED;
  for (const [fx, fy, tx, ty] of seq) { b[ty * 9 + tx] = b[fy * 9 + fx]; b[fy * 9 + fx] = 0; side = -side; }
  for (let trial = 0; trial < 60; trial++) {
    const g = E.geometry(b, side, 0, 0);
    for (const sp of [g.a, g.b, g.c]) {
      // 加噪：模拟不同子集
      const pts = sp.tokens.filter(() => rnd() > 0.15).map((p) => ({ w: p.w * (0.5 + rnd()), c: [p.c[0] + (rnd() - 0.5) * 0.3, p.c[1] + (rnd() - 0.5) * 0.3, p.c[2] + (rnd() - 0.5) * 0.3] }));
      if (pts.length < 2) continue;
      const got = (function () {
        // 复用引擎内部：借 geometry 的 state 无法直接拿 fitLine3，这里通过模块内导出
        return E.fitLine3 ? E.fitLine3(pts) : null;
      })();
      if (!got) { console.log("fitLine3 未导出"); process.exit(1); }
      const ref = refPower(pts);
      const dot = Math.abs(got.v[0] * ref.v[0] + got.v[1] * ref.v[1] + got.v[2] * ref.v[2]);
      const ang = Math.acos(Math.min(1, dot)) * 180 / Math.PI;
      const dlam = Math.abs(got.lam - ref.lam) / Math.max(1e-9, Math.abs(ref.lam));
      const dcen = Math.hypot(got.c[0] - ref.c[0], got.c[1] - ref.c[1], got.c[2] - ref.c[2]);
      n++;
      if (ang > worstAng) { worstAng = ang; worstCase = { ang, lam: [got.lam, ref.lam], dcen }; }
      if (dlam > worstLam) worstLam = dlam;
      if (dcen > 1e-9) console.log("质心不一致!", dcen);
    }
  }
}
console.log("样本", n, "最大主轴夹角(度)", worstAng.toExponential(2), "最大 lam 相对误差", worstLam.toExponential(2));
console.log("最差一例", JSON.stringify(worstCase));
