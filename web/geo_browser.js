/* 45 维几何特征的浏览器侧实现
 *
 * 与 geo_eval.h 逐行对应：令牌 → 三空间坐标 → 质心/主轴/残差 + 形特征
 * + 子力 + 威胁，再进 64 专家 RBF 门控。只用于可视化与自检，
 * 引擎决策仍由 C++ 完成（两边在 1cp 内一致，见 tools 对拍脚本）。
 *
 * 依赖：window.XQ（规则内核）、window.GEO_MODEL（geo_model.js 导出的权重）
 */
(function (root) {
  "use strict";
  const X = root.XQ;
  const G = root.GEO_MODEL;
  const { fx, fy, sqOf, kingSq, attacked, RED, BLACK } = X;

  const ROLE_W = [0, 1.40, 0.80, 0.85, 1.00, 1.25, 1.10, 0.95];
  const VALUE = [0, 1000, 300, 300, 550, 1100, 580, 180];
  const MAT_V = [0, 0, 100, 100, 200, 450, 230, 40];
  const PAWN = 7, HORSE = 4, ROOK = 5, CANNON = 6, ADVISOR = 2, ELEPHANT = 3;
  const fr = Math.fround;

  function tokensOf(b, side) {
    const toks = [];
    const flip = side === BLACK;
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (!p) continue;
      const x = s % 9, y = (s / 9) | 0;
      const bx = flip ? 8 - x : x;
      const by = flip ? 9 - y : y;
      const ps = p > 0 ? RED : BLACK;
      const role = (ps === side) ? 0 : 1;
      const t = Math.abs(p);
      let w = ROLE_W[t];
      const crossed = ps === RED ? y <= 4 : y >= 5;
      if (crossed) w *= 1.15;
      const slot = G.slot[(role * 7 + (t - 1)) * 90 + by * 9 + bx];
      if (slot < 0) continue;
      toks.push({ slot, w, t, s, role });
    }
    return toks;
  }

  function xyzOf(space, slot) {
    const o = (space * G.nvec + slot) * 3;
    return [G.xyz[o], G.xyz[o + 1], G.xyz[o + 2]];
  }

  function fitSpace(pts, wts) {
    let sw = 0, sx = 0, sy = 0, sz = 0;
    let sxx = 0, syy = 0, szz = 0, sxy = 0, sxz = 0, syz = 0;
    const n = pts.length;
    for (let i = 0; i < n; i++) {
      const w = wts[i], x = pts[i][0], y = pts[i][1], z = pts[i][2];
      sw += w; sx += w * x; sy += w * y; sz += w * z;
      sxx += w * x * x; syy += w * y * y; szz += w * z * z;
      sxy += w * x * y; sxz += w * x * z; syz += w * y * z;
    }
    if (sw <= 0) return { c: [0, 0, 0], v: [1, 0, 0], rho: 0, lam: 0 };
    const iw = 1 / sw;
    const cx = sx * iw, cy = sy * iw, cz = sz * iw;
    const a11 = sxx * iw - cx * cx, a22 = syy * iw - cy * cy, a33 = szz * iw - cz * cz;
    const a12 = sxy * iw - cx * cy, a13 = sxz * iw - cx * cz, a23 = syz * iw - cy * cz;
    const p1 = a12 * a12 + a13 * a13 + a23 * a23;
    let v, lamMax;
    if (p1 < 1e-18) {
      if (a11 >= a22 && a11 >= a33) { v = [1, 0, 0]; lamMax = a11; }
      else if (a22 >= a33) { v = [0, 1, 0]; lamMax = a22; }
      else { v = [0, 0, 1]; lamMax = a33; }
    } else {
      const q = (a11 + a22 + a33) / 3;
      const p2 = (a11 - q) ** 2 + (a22 - q) ** 2 + (a33 - q) ** 2 + 2 * p1;
      const p = Math.sqrt(p2 / 6);
      const b11 = (a11 - q) / p, b22 = (a22 - q) / p, b33 = (a33 - q) / p;
      const b12 = a12 / p, b13 = a13 / p, b23 = a23 / p;
      const det = b11 * (b22 * b33 - b23 * b23) - b12 * (b12 * b33 - b23 * b13) + b13 * (b12 * b23 - b22 * b13);
      let r = det / 2;
      if (r > 1) r = 1; else if (r < -1) r = -1;
      const phi = Math.acos(r) / 3;
      const e1 = q + 2 * p * Math.cos(phi);
      lamMax = e1;
      const x1 = a11 - e1, x2 = a22 - e1, x3 = a33 - e1;
      const c1 = [a12 * a23 - a13 * x2, a13 * a12 - x1 * a23, x1 * x2 - a12 * a12];
      const c2 = [a12 * x3 - a13 * a23, a13 * a13 - x1 * x3, x1 * a23 - a12 * a13];
      const cb = [x2 * x3 - a23 * a23, a23 * a13 - a12 * x3, a12 * a23 - x2 * a13];
      let best = c1, bn = c1[0] ** 2 + c1[1] ** 2 + c1[2] ** 2;
      const n2 = c2[0] ** 2 + c2[1] ** 2 + c2[2] ** 2;
      if (n2 > bn) { best = c2; bn = n2; }
      const n3 = cb[0] ** 2 + cb[1] ** 2 + cb[2] ** 2;
      if (n3 > bn) { best = cb; bn = n3; }
      if (bn < 1e-20) v = [0.5774, 0.5774, 0.5774];
      else { const nn = Math.sqrt(bn); v = [best[0] / nn, best[1] / nn, best[2] / nn]; }
    }
    let idx = 0, amax = Math.abs(v[0]);
    if (Math.abs(v[1]) >= amax) { amax = Math.abs(v[1]); idx = 1; }
    if (Math.abs(v[2]) >= amax) idx = 2;
    if (v[idx] < 0) v = [-v[0], -v[1], -v[2]];
    let res = a11 + a22 + a33 - lamMax;
    if (res < 0) res = 0;
    return { c: [cx, cy, cz], v, rho: Math.sqrt(res), lam: lamMax };
  }

  function shapeOf(st, pts, wts) {
    const [cx, cy, cz] = st.c, [vx, vy, vz] = st.v;
    let sw = 0, dens = 0, pmax = -1e30, pmin = 1e30;
    for (let i = 0; i < pts.length; i++) {
      const w = wts[i];
      sw += w;
      const dx = pts[i][0] - cx, dy = pts[i][1] - cy, dz = pts[i][2] - cz;
      const d2 = dx * dx + dy * dy + dz * dz;
      dens += w * Math.exp(-d2 / 1.6);
      const pr = dx * vx + dy * vy + dz * vz;
      if (pr > pmax) pmax = pr;
      if (pr < pmin) pmin = pr;
    }
    const span = pts.length ? pmax - pmin : 0;
    const denom = Math.abs(vz) > 1e-6 ? Math.abs(vz) : 1e-6;
    let slope = Math.hypot(vx, vy) / denom;
    if (slope > 5) slope = 5;
    return [dens / (sw > 1e-9 ? sw : 1e-9), span, slope];
  }

  function matFeats(b, side) {
    const own = new Array(8).fill(0), opp = new Array(8).fill(0);
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (!p) continue;
      const t = Math.abs(p);
      const k = t === PAWN ? 7 : t;
      const ps = p > 0 ? RED : BLACK;
      const crossed = ps === RED ? fy(s) <= 4 : fy(s) >= 5;
      if (ps === side) { own[k]++; if (t === PAWN && crossed) own[0]++; }
      else { opp[k]++; if (t === PAWN && crossed) opp[0]++; }
    }
    let mv = 0, mo = 0;
    for (let k = 2; k <= 7; k++) { mv += MAT_V[k] * own[k]; mo += MAT_V[k] * opp[k]; }
    const out = [(mv - mo) / 100];
    for (let k = 1; k <= 7; k++) out.push(own[k] - opp[k]);
    out.push(own[0] - opp[0]);
    return out;
  }

  function threatFeats(b, side) {
    const k = kingSq(b, side);
    if (k < 0) return [0, 0, 0, 0, 0, 0];
    const kx = fx(k), ky = fy(k);
    let heavy = 0, def = 0, edge = 0, pal = 0, mob = 0, mat = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q) continue;
      const x = fx(s), y = fy(s), t = Math.abs(q);
      const own = (q > 0 ? RED : BLACK) === side;
      mat += (own ? 1 : -1) * VALUE[t];
      const mx = Math.max(Math.abs(x - kx), Math.abs(y - ky));
      if (!own && (t === HORSE || t === ROOK || t === CANNON) && mx <= 2) heavy++;
      if (own && (t === ADVISOR || t === ELEPHANT || t === ROOK) && mx <= 2) def++;
      if (!own && (x === 0 || x === 8) && (side === RED ? y >= 7 : y <= 2)) edge++;
    }
    for (let yy = Math.max(ky - 1, 0); yy <= Math.min(ky + 1, 9); yy++)
      for (let xx = Math.max(kx - 1, 0); xx <= Math.min(kx + 1, 8); xx++)
        if (attacked(b, sqOf(xx, yy), -side)) pal++;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = kx + dx, ny = ky + dy;
      const inPal = nx >= 0 && nx < 9 && ny >= 0 && ny < 10 && (side === RED ? ny >= 7 : ny <= 2);
      if (inPal && b[sqOf(nx, ny)] === 0 && !attacked(b, sqOf(nx, ny), -side)) mob++;
    }
    return [heavy, def, edge, pal, mob, mat / 100];
  }

  function feats45(b, side) {
    const toks = tokensOf(b, side);
    const out = new Float64Array(45);
    const spaces = [];
    if (!toks.length) {
      const m = matFeats(b, side), th = threatFeats(b, side);
      for (let i = 0; i < 9; i++) out[30 + i] = m[i];
      for (let i = 0; i < 6; i++) out[39 + i] = th[i];
      return { f: out, spaces, toks: 0 };
    }
    const wts = toks.map((t) => t.w);
    for (let sp = 0; sp < 3; sp++) {
      const pts = toks.map((t) => xyzOf(sp, t.slot));
      const st = fitSpace(pts, wts);
      const sh = shapeOf(st, pts, wts);
      out[sp * 7] = st.c[0]; out[sp * 7 + 1] = st.c[1]; out[sp * 7 + 2] = st.c[2];
      out[sp * 7 + 3] = st.v[0]; out[sp * 7 + 4] = st.v[1]; out[sp * 7 + 5] = st.v[2];
      out[sp * 7 + 6] = st.rho;
      for (let j = 0; j < 3; j++) out[21 + sp * 3 + j] = sh[j];
      spaces.push({ pts, wts, st, sh, toks });
    }
    const m = matFeats(b, side), th = threatFeats(b, side);
    for (let i = 0; i < 9; i++) out[30 + i] = m[i];
    for (let i = 0; i < 6; i++) out[39 + i] = th[i];
    return { f: out, spaces, toks: toks.length };
  }

  const CN2 = (function () {
    const a = new Float32Array(G.k);
    for (let k = 0; k < G.k; k++) {
      let s = 0;
      for (let i = 0; i < G.stride; i++) { const v = G.cn[k * G.stride + i]; s += fr(v * v); }
      a[k] = fr(s);
    }
    return a;
  })();

  function dotAt(a, b, off, len) {
    let s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    for (let i = 0; i < len; i += 4) {
      s0 += a[i] * b[off + i];
      s1 += a[i + 1] * b[off + i + 1];
      s2 += a[i + 2] * b[off + i + 2];
      s3 += a[i + 3] * b[off + i + 3];
    }
    return fr((s0 + s1) + (s2 + s3));
  }

  function treeScore45(f) {
    const z = new Float32Array(G.stride);
    let zn = 0;
    for (let i = 0; i < G.dim; i++) {
      const t = fr((f[i] - G.mean[i]) / G.std[i]);
      z[i] = t;
      zn = fr(zn + t * t);
    }
    const invH2 = 1 / (2 * G.h * G.h * G.hScale * G.hScale);
    const wts = new Float32Array(G.k);
    let sw = 0, wmax = 0;
    for (let k = 0; k < G.k; k++) {
      const o = k * G.stride;
      let d2 = fr(zn - 2 * dotAt(z, G.cn, o, G.stride) + CN2[k]);
      if (d2 < 0) d2 = 0;
      const wk = Math.exp(-d2 * invH2);
      wts[k] = wk;
      sw += wk;
      if (wk > wmax) wmax = wk;
    }
    if (sw <= 0) sw = 1;
    const cutoff = wmax * 1e-4;
    let tree = 0, glob = G.gb;
    const contrib = new Float32Array(G.k);
    for (let i = 0; i < G.stride; i++) glob = fr(glob + G.gw[i] * z[i]);
    for (let k = 0; k < G.k; k++) {
      if (wts[k] < cutoff) continue;
      const o = k * G.stride;
      const local = fr(G.lb[k] + dotAt(z, G.lw, o, G.stride));
      tree += wts[k] * local;
      contrib[k] = (wts[k] * local) / sw;
    }
    tree = fr(tree / sw);
    return { score: G.lam * tree + (1 - G.lam) * glob, tree, glob, wts, contrib, sw };
  }

  root.GEOC = { ROLE_W, VALUE, MAT_V, tokensOf, xyzOf, fitSpace, shapeOf, matFeats, threatFeats, feats45, treeScore45 };
})(typeof window !== "undefined" ? window : globalThis);
