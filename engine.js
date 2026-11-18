/* GeoLite-Xiangqi engine —— 规则、几何链路、检索与搜索，浏览器与 node 共用。 */
(function (global) {
  'use strict';

  const W = 9, H = 10, RED = 1, BLACK = -1;
  const KING = 1, ADVISOR = 2, ELEPHANT = 3, HORSE = 4, ROOK = 5, CANNON = 6, PAWN = 7;
  const VALUE = { 1: 1000, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180 };
  const ROLE_W = { 1: 1.40, 2: 0.80, 3: 0.85, 4: 1.00, 5: 1.25, 6: 1.10, 7: 0.95 };
  const NAME = {
    [RED]: { 1: '帅', 2: '仕', 3: '相', 4: '马', 5: '车', 6: '炮', 7: '兵' },
    [BLACK]: { 1: '将', 2: '士', 3: '象', 4: '马', 5: '车', 6: '砲', 7: '卒' }
  };
  const ORTHO = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const DIAG = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
  const HORSE_MV = [
    [1, 2, 0, 1], [-1, 2, 0, 1], [1, -2, 0, -1], [-1, -2, 0, -1],
    [2, 1, 1, 0], [2, -1, 1, 0], [-2, 1, -1, 0], [-2, -1, -1, 0]
  ];
  const CLASSES = ['open', 'contact', 'attack', 'defense', 'endgame', 'maneuver'];
  const CLASS_CN = {
    open: '开局部署', contact: '接触对峙', attack: '攻王压迫',
    defense: '防守回撤', endgame: '残局收兵', maneuver: '中局调动'
  };
  const PHASE = {
    open: { pawn: 0.8, horse: 1.15, cannon: 1.15, rook: 0.9, king: 0.6, check: 0.6, cap: 1.0, adv: 1.2 },
    contact: { pawn: 1.0, horse: 1.0, cannon: 1.0, rook: 1.1, king: 1.0, check: 1.0, cap: 1.25, adv: 1.0 },
    attack: { pawn: 1.2, horse: 1.2, cannon: 1.35, rook: 1.3, king: 1.25, check: 1.7, cap: 1.1, adv: 1.4 },
    defense: { pawn: 0.8, horse: 0.9, cannon: 0.9, rook: 1.0, king: 1.9, check: 0.8, cap: 1.15, adv: 0.7 },
    endgame: { pawn: 1.6, horse: 1.2, cannon: 1.0, rook: 1.1, king: 0.9, check: 1.1, cap: 1.0, adv: 1.5 },
    maneuver: { pawn: 1.0, horse: 1.0, cannon: 1.0, rook: 1.0, king: 1.0, check: 1.0, cap: 1.0, adv: 1.0 }
  };

  const sq = (x, y) => y * W + x;
  const fOf = (mv) => (mv / 100) | 0;
  const tOf = (mv) => mv % 100;
  const mk = (f, t) => f * 100 + t;
  const sside = (p) => (p > 0 ? RED : p < 0 ? BLACK : 0);
  const inBoard = (x, y) => x >= 0 && x < W && y >= 0 && y < H;
  const inPalace = (x, y, side) => x >= 3 && x <= 5 && (side === RED ? y >= 7 && y <= 9 : y >= 0 && y <= 2);
  const crossed = (y, side) => (side === RED ? y <= 4 : y >= 5);

  function initial() {
    const b = new Int8Array(90);
    const back = [ROOK, HORSE, ELEPHANT, ADVISOR, KING, ADVISOR, ELEPHANT, HORSE, ROOK];
    for (let x = 0; x < 9; x++) { b[sq(x, 0)] = -back[x]; b[sq(x, 9)] = back[x]; }
    b[sq(1, 2)] = -CANNON; b[sq(7, 2)] = -CANNON;
    for (const x of [0, 2, 4, 6, 8]) { b[sq(x, 3)] = -PAWN; b[sq(x, 6)] = PAWN; }
    b[sq(1, 7)] = CANNON; b[sq(7, 7)] = CANNON;
    return b;
  }

  function genPseudo(b, side) {
    const out = [];
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0 || sside(p) !== side) continue;
      const t = Math.abs(p), x = s % W, y = (s / W) | 0;
      if (t === KING) {
        for (const [dx, dy] of ORTHO) {
          const nx = x + dx, ny = y + dy;
          if (!inPalace(nx, ny, side)) continue;
          const q = b[sq(nx, ny)];
          if (q === 0 || sside(q) !== side) out.push(mk(s, sq(nx, ny)));
        }
      } else if (t === ADVISOR) {
        for (const [dx, dy] of DIAG) {
          const nx = x + dx, ny = y + dy;
          if (!inPalace(nx, ny, side)) continue;
          const q = b[sq(nx, ny)];
          if (q === 0 || sside(q) !== side) out.push(mk(s, sq(nx, ny)));
        }
      } else if (t === ELEPHANT) {
        for (const [dx, dy] of DIAG) {
          const nx = x + 2 * dx, ny = y + 2 * dy;
          if (!inBoard(nx, ny)) continue;
          if (side === RED ? ny < 5 : ny > 4) continue;
          if (b[sq(x + dx, y + dy)] !== 0) continue;
          const q = b[sq(nx, ny)];
          if (q === 0 || sside(q) !== side) out.push(mk(s, sq(nx, ny)));
        }
      } else if (t === HORSE) {
        for (const [dx, dy, lx, ly] of HORSE_MV) {
          const nx = x + dx, ny = y + dy;
          if (!inBoard(nx, ny)) continue;
          if (b[sq(x + lx, y + ly)] !== 0) continue;
          const q = b[sq(nx, ny)];
          if (q === 0 || sside(q) !== side) out.push(mk(s, sq(nx, ny)));
        }
      } else if (t === ROOK) {
        for (const [dx, dy] of ORTHO) {
          let nx = x + dx, ny = y + dy;
          while (inBoard(nx, ny)) {
            const q = b[sq(nx, ny)];
            if (q === 0) out.push(mk(s, sq(nx, ny)));
            else { if (sside(q) !== side) out.push(mk(s, sq(nx, ny))); break; }
            nx += dx; ny += dy;
          }
        }
      } else if (t === CANNON) {
        for (const [dx, dy] of ORTHO) {
          let nx = x + dx, ny = y + dy;
          while (inBoard(nx, ny) && b[sq(nx, ny)] === 0) {
            out.push(mk(s, sq(nx, ny))); nx += dx; ny += dy;
          }
          nx += dx; ny += dy;
          while (inBoard(nx, ny)) {
            const q = b[sq(nx, ny)];
            if (q !== 0) { if (sside(q) !== side) out.push(mk(s, sq(nx, ny))); break; }
            nx += dx; ny += dy;
          }
        }
      } else if (t === PAWN) {
        const ny = y - side;
        if (inBoard(x, ny)) {
          const q = b[sq(x, ny)];
          if (q === 0 || sside(q) !== side) out.push(mk(s, sq(x, ny)));
        }
        if (crossed(y, side)) {
          for (const dx of [-1, 1]) {
            const nx = x + dx;
            if (!inBoard(nx, y)) continue;
            const q = b[sq(nx, y)];
            if (q === 0 || sside(q) !== side) out.push(mk(s, sq(nx, y)));
          }
        }
      }
    }
    return out;
  }

  function findKing(b, side) {
    const t = KING * side;
    for (let s = 0; s < 90; s++) if (b[s] === t) return s;
    return -1;
  }

  function facing(b) {
    const kr = findKing(b, RED), kb = findKing(b, BLACK);
    if (kr < 0 || kb < 0) return false;
    const xr = kr % W, yr = (kr / W) | 0, xb = kb % W, yb = (kb / W) | 0;
    if (xr !== xb) return false;
    const lo = Math.min(yr, yb), hi = Math.max(yr, yb);
    for (let y = lo + 1; y < hi; y++) if (b[sq(xr, y)] !== 0) return false;
    return true;
  }

  function attacked(b, s, by) {
    const x = s % W, y = (s / W) | 0;
    for (const [dx, dy] of ORTHO) {
      let nx = x + dx, ny = y + dy, step = 1;
      while (inBoard(nx, ny)) {
        const q = b[sq(nx, ny)];
        if (q !== 0) {
          if (sside(q) === by) {
            const t = Math.abs(q);
            if (t === ROOK || (t === KING && step === 1)) return true;
          }
          break;
        }
        nx += dx; ny += dy; step++;
      }
    }
    for (const [dx, dy] of ORTHO) {
      let nx = x + dx, ny = y + dy, screens = 0;
      while (inBoard(nx, ny)) {
        const q = b[sq(nx, ny)];
        if (q !== 0) {
          if (screens === 1) { if (sside(q) === by && Math.abs(q) === CANNON) return true; break; }
          screens++;
        }
        nx += dx; ny += dy;
      }
    }
    for (const [dx, dy, lx, ly] of HORSE_MV) {
      const sx = x - dx, sy = y - dy;
      if (!inBoard(sx, sy)) continue;
      const q = b[sq(sx, sy)];
      if (q !== 0 && sside(q) === by && Math.abs(q) === HORSE) {
        const gx = sx + lx, gy = sy + ly;
        if (inBoard(gx, gy) && b[sq(gx, gy)] === 0) return true;
      }
    }
    let cand;
    if (by === RED) cand = [[x, y + 1], [x - 1, y], [x + 1, y]];
    else cand = [[x, y - 1], [x - 1, y], [x + 1, y]];
    for (const [cx, cy] of cand) {
      if (!inBoard(cx, cy)) continue;
      const q = b[sq(cx, cy)];
      if (q !== 0 && sside(q) === by && Math.abs(q) === PAWN) return true;
    }
    return false;
  }

  function inCheck(b, side) {
    const k = findKing(b, side);
    if (k < 0) return true;
    return attacked(b, k, -side) || facing(b);
  }

  function legal(b, side) {
    const out = [];
    for (const mv of genPseudo(b, side)) {
      const f = fOf(mv), t = tOf(mv), cap = b[t];
      b[t] = b[f]; b[f] = 0;
      if (!inCheck(b, side)) out.push(mv);
      b[f] = b[t]; b[t] = cap;
    }
    return out;
  }

  // ---------------------------------------------------------------- 评估
  const PST = {};
  (function buildPst() {
    const mkTable = (fn) => {
      const a = new Float32Array(90);
      for (let y = 0; y < 10; y++) for (let x = 0; x < 9; x++) a[sq(x, y)] = fn(x, y);
      return a;
    };
    PST[PAWN] = mkTable((x, y) => Math.max(0, 7 - y) * 6 + (y <= 4 ? 20 : 0) - Math.abs(x - 4) * 2);
    PST[HORSE] = mkTable((x, y) => 14 - 2 * Math.abs(x - 4) - 1.5 * Math.abs(y - 5));
    PST[CANNON] = mkTable((x, y) => 8 - 1.4 * Math.abs(x - 4) - 0.9 * Math.abs(y - 4));
    PST[ROOK] = mkTable((x, y) => 4 + (y <= 6 ? 8 : 0) + (x === 0 || x === 8 ? -2 : 2));
    PST[ADVISOR] = mkTable((x, y) => (y >= 8 && Math.abs(x - 4) === 1 ? 6 : 0));
    PST[ELEPHANT] = mkTable((x, y) => (y >= 8 && (x === 2 || x === 6) ? 6 : 0));
    PST[KING] = mkTable((x, y) => (y >= 8 ? 0 : -10));
  })();

  function mirrorIdx(s) { const x = s % W, y = (s / W) | 0; return sq(W - 1 - x, 9 - y); }

  function evaluate(b, phase) {
    const ph = PHASE[phase] || PHASE.maneuver;
    let score = 0, advR = 0, advB = 0, defR = 0, defB = 0;
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0) continue;
      const side = sside(p), t = Math.abs(p);
      const x = s % W, y = (s / W) | 0;
      const idx = side === RED ? s : mirrorIdx(s);
      let w = 1;
      if (t === PAWN) w = ph.pawn;
      else if (t === HORSE) w = ph.horse;
      else if (t === CANNON) w = ph.cannon;
      else if (t === ROOK) w = ph.rook;
      else if (t === KING || t === ADVISOR || t === ELEPHANT) w = ph.king;
      const v = (VALUE[t] + PST[t][idx] * w) * side;
      score += v;
      if (t === ADVISOR || t === ELEPHANT) { if (side === RED) defR++; else defB++; }
      if (t === HORSE || t === CANNON || t === ROOK) { if (side === RED) advR++; else advB++; }
      // 攻王压力：重子与兵越靠近敌宫，加分越多（阶段 adv 权重调节）
      if (t === ROOK || t === CANNON || t === HORSE || t === PAWN) {
        const d = Math.max(Math.abs(x - 4), Math.abs(y - (side === RED ? 1 : 8)));
        score += side * Math.max(0, 4 - d) * (t === PAWN ? 2.4 : 3.2) * ph.adv;
      }
      // 子力未出动：重子停在自己底线时轻微扣分，避免开局原地蹭炮
      if ((t === ROOK || t === CANNON || t === HORSE) && y === (side === RED ? 9 : 0)) score -= side * 14;
      // 活动空间：车/炮的四向空格数，抑制无意义原地挪动
      if (t === ROOK || t === CANNON) {
        let mob = 0;
        for (let k = 0; k < 4; k++) {
          const dx = k === 0 ? 1 : k === 1 ? -1 : 0, dy = k === 2 ? 1 : k === 3 ? -1 : 0;
          let nx = x + dx, ny = y + dy;
          while (nx >= 0 && nx < 9 && ny >= 0 && ny < 10 && !b[ny * W + nx]) { mob++; nx += dx; ny += dy; }
        }
        score += side * mob * 2;
      }
    }
    // 缺士象在对手重子在场时扣分
    const guardR = Math.min(4, defR), guardB = Math.min(4, defB);
    score -= (4 - guardR) * 14 * ph.king * Math.min(1.5, 0.5 + advB * 0.25);
    score += (4 - guardB) * 14 * ph.king * Math.min(1.5, 0.5 + advR * 0.25);
    return score;
  }

  // ---------------------------------------------------------------- 几何链路
  let MODEL = null;
  let COORDS = null;
  function setModel(m) {
    MODEL = m;
    COORDS = {};
    for (const k in m.coords2) COORDS[k] = m.coords2[k];
  }

  function tokensOf(b, side) {
    const out = [];
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0) continue;
      const x = s % W, y = (s / W) | 0;
      const bx = side === BLACK ? (W - 1 - x) : x;
      const by = side === BLACK ? (9 - y) : y;
      const role = sside(p) === side ? 'S' : 'O';
      const t = Math.abs(p);
      let w = ROLE_W[t];
      if (crossed(y, sside(p))) w *= 1.15;
      out.push({ key: role + t + '@' + bx + by, bx, by, w, t, s });
    }
    return out;
  }

  function fitLine(pts) {
    // pts: [{cx, cy, w}]
    let sw = 0, mx = 0, my = 0;
    for (const p of pts) { sw += p.w; mx += p.w * p.cx; my += p.w * p.cy; }
    if (sw <= 0) return { cx: 0, cy: 0, vx: 1, vy: 0 };
    const cx = mx / sw, cy = my / sw;
    let a = 0, bb = 0, c = 0;
    for (const p of pts) {
      const dx = p.cx - cx, dy = p.cy - cy;
      a += p.w * dx * dx; bb += p.w * dx * dy; c += p.w * dy * dy;
    }
    a /= sw; bb /= sw; c /= sw;
    const tr = a + c, det = a * c - bb * bb;
    const disc = Math.max(tr * tr / 4 - det, 0);
    const lam = tr / 2 + Math.sqrt(disc);
    let vx, vy;
    if (Math.abs(bb) > 1e-12) { vx = lam - c; vy = bb; }
    else { vx = a >= c ? 1 : 0; vy = a >= c ? 0 : 1; }
    const n = Math.hypot(vx, vy) || 1;
    vx /= n; vy /= n;
    if (Math.abs(vx) >= Math.abs(vy)) { if (vx < 0) { vx = -vx; vy = -vy; } }
    else if (vy < 0) { vx = -vx; vy = -vy; }
    return { cx, cy, vx, vy };
  }

  function stateOf(pts) {
    const f = fitLine(pts);
    let sw = 0, res = 0;
    for (const p of pts) {
      sw += p.w;
      const dx = p.cx - f.cx, dy = p.cy - f.cy;
      const proj = dx * f.vx + dy * f.vy;
      const perp2 = Math.max(dx * dx + dy * dy - proj * proj, 0);
      res += p.w * perp2;
    }
    const rho = Math.sqrt(res / Math.max(sw, 1e-9));
    const slopeRaw = Math.abs(f.vx) < 1e-6 ? (f.vy >= 0 ? 5 : -5) : f.vy / f.vx;
    const slope = Math.max(-5, Math.min(5, slopeRaw));
    return { state: [f.cx, f.cy, slope, rho], centroid: [f.cx, f.cy], axis: [f.vx, f.vy], rho };
  }

  function geometry(b, side, layers, maxLayers) {
    maxLayers = (maxLayers === undefined || maxLayers === null) ? layers : maxLayers;
    const raw = tokensOf(b, side);
    const toks = [];
    for (const t of raw) {
      const c = COORDS[t.key];
      if (!c) continue;
      toks.push({ key: t.key, cx: c[0], cy: c[1], w: t.w, t: t.t, s: t.s, bx: t.bx, by: t.by });
    }
    if (!toks.length) return { state: [0, 0, 0, 0], layers: [], dropped: [], tokens: [], kept: [] };
    let keep = toks.slice();
    const recs = [];
    const dropped = [];
    let cur = stateOf(keep);
    recs.push({ layer: 0, state: cur.state.slice(), kept: keep.length, residual: cur.rho,
                slope: cur.state[2], drop: null, axis: cur.axis.slice(), centroid: cur.centroid.slice() });
    for (let l = 1; l <= maxLayers; l++) {
      if (keep.length <= 3) {
        recs.push({ layer: l, state: cur.state.slice(), kept: keep.length, residual: cur.rho,
                    slope: cur.state[2], drop: null, axis: cur.axis.slice(), centroid: cur.centroid.slice() });
        continue;
      }
      const f = fitLine(keep);
      let best = 0, bestD = -1;
      keep.forEach((p, i) => {
        const dx = p.cx - f.cx, dy = p.cy - f.cy;
        const proj = dx * f.vx + dy * f.vy;
        const perp2 = Math.max(dx * dx + dy * dy - proj * proj, 0);
        if (perp2 > bestD + 1e-9 || (Math.abs(perp2 - bestD) <= 1e-9 && p.s < keep[best].s)) {
          bestD = Math.max(bestD, perp2); best = i;
        }
      });
      const dropTok = keep[best];
      dropped.push({ layer: l, token: dropTok.key, type: dropTok.t, square: dropTok.s, perp: Math.sqrt(bestD) });
      keep = keep.filter((_, i) => i !== best);
      cur = stateOf(keep);
      recs.push({ layer: l, state: cur.state.slice(), kept: keep.length, residual: cur.rho,
                  slope: cur.state[2], drop: dropTok.key, axis: cur.axis.slice(), centroid: cur.centroid.slice() });
    }
    const L = Math.max(0, Math.min(layers, maxLayers));
    return {
      state: recs[L].state.slice(), at: recs[L], layers: recs, dropped, tokens: toks,
      kept: keep.map((p) => p.key)
    };
  }

  function normalize(vec, layer) {
    const n = MODEL.norm[String(layer)] || MODEL.norm[layer];
    return vec.map((v, i) => (v - n.mean[i]) / n.std[i]);
  }

  function retrieve(vec, layer, k) {
    if (!MODEL) return null;
    const n = MODEL.norm[String(layer)] || MODEL.norm[layer];
    const z = normalize(vec, layer);
    const protos = (MODEL.prototypes[String(layer)] || MODEL.prototypes[layer]);
    const pd = protos.map((p, i) => ({
      cls: CLASSES[i],
      dist: Math.sqrt(p.reduce((s, v, j) => s + (v - z[j]) * (v - z[j]), 0))
    }));
    const libRaw = (MODEL.library.states[String(layer)] || MODEL.library.states[layer]);
    const labels = MODEL.library.labels;
    const cand = [];
    for (let i = 0; i < libRaw.length; i++) {
      const row = libRaw[i];
      let s = 0;
      for (let j = 0; j < 4; j++) {
        const dz = (row[j] - n.mean[j]) / n.std[j] - z[j];
        s += dz * dz;
      }
      cand.push([Math.sqrt(s), labels[i], i]);
    }
    cand.sort((a, b) => a[0] - b[0]);
    const top = cand.slice(0, k || MODEL.meta.k || 5);
    const votes = {};
    let tot = 0;
    for (const [d, lab] of top) {
      const wgt = 1 / (d + 1e-6);
      votes[lab] = (votes[lab] || 0) + wgt;
      tot += wgt;
    }
    const prob = CLASSES.map((c, i) => (votes[i] || 0) / tot);
    const best = prob.indexOf(Math.max(...prob));
    return {
      proto: pd.sort((a, b) => a.dist - b.dist),
      knn: { cls: CLASSES[best], prob, dist: top[0][0], top: top.map(([d, lab]) => [CLASSES[lab], d]) },
      z
    };
  }

  function situationLabel(b, side) {
    const pc = { [RED]: [4, 1], [BLACK]: [4, 8] };
    let total = 0, near2 = 0, oppNear2 = 0;
    const own = [], opp = [];
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0) continue;
      const t = Math.abs(p), so = sside(p), isOwn = so === side;
      if (t !== KING) total += VALUE[t];
      const x = s % W, y = (s / W) | 0;
      (isOwn ? own : opp).push([x, y]);
      if ((t === HORSE || t === ROOK || t === CANNON || t === PAWN) && crossed(y, so)) {
        const c = pc[so];
        if (Math.max(Math.abs(x - c[0]), Math.abs(y - c[1])) <= 2) { if (isOwn) near2++; else oppNear2++; }
      }
    }
    let contact = 0;
    for (const [x1, y1] of own) for (const [x2, y2] of opp)
      if (Math.max(Math.abs(x1 - x2), Math.abs(y1 - y2)) <= 2) contact++;
    if (total <= 430) return 'endgame';
    if (near2 >= 1 && near2 >= oppNear2) return 'attack';
    if (oppNear2 >= 1 && oppNear2 > near2) return 'defense';
    if (contact >= 10) return 'contact';
    if (total >= 780 && contact <= 6) return 'open';
    return 'maneuver';
  }

  // ---------------------------------------------------------------- 搜索
  let nodes = 0, deadline = 0, aborted = false;
  const history = new Int32Array(90 * 90);
  const killers = [];

  // Zobrist 表：棋子-格位随机键，用于重复局面检测
  const ZOB = new Int32Array(90 * 15);
  (function () {
    let s = 20261115;
    for (let i = 0; i < 90 * 15; i++) {
      s = (s * 1103515245 + 12345) & 0x7fffffff;
      ZOB[i] = s;
    }
  })();
  const pidx = (p) => (p > 0 ? p : 7 - p);      // 红 1..7，黑 8..14
  const SIDE_Z = 0x5bf03635;
  function hashBoard(b) {
    let h = 0;
    for (let s = 0; s < 90; s++) { const p = b[s]; if (p) h ^= ZOB[s * 15 + pidx(p)]; }
    return h;
  }
  function keyOf(b, side) { return hashBoard(b) ^ (side === RED ? SIDE_Z : 0); }

  // ---------------------------------------------------------------- 开局库
  // 由真实棋谱挖出的“局面 -> 着法 -> 胜和负”表；行格式 [mv, 胜, 和, 负, 未知]
  let BOOK = null;
  function setBook(bk) { BOOK = bk || null; }
  function bookInfo() {
    if (!BOOK) return null;
    return { games: BOOK.games || 0, plies: BOOK.plies || 0, positions: BOOK.size || Object.keys(BOOK.entries || {}).length };
  }
  function bookPick(b, side, ply) {
    if (!BOOK || !BOOK.entries) return null;
    if (ply !== undefined && BOOK.plies && ply >= BOOK.plies) return null;
    const rows = BOOK.entries[keyOf(b, side)];
    if (!rows || !rows.length) return null;
    const cand = [];
    let totalN = 0;
    for (const r of rows) totalN += r[1];
    const floorN = Math.max(2, Math.round(totalN * 0.04));
    for (const r of rows) {
      // 行格式 [mv, 总局数, 胜, 和, 负, 无结果]
      const n = r[1];
      if (n < floorN) continue;          // 只走主流着法，避免被一两局的冷门带跑
      cand.push({ mv: r[0], n, score: (r[2] + 0.5 * r[3]) / n, w: r[2], d: r[3], l: r[4] });
    }
    if (!cand.length) {
      for (const r of rows) {
        const n = r[1];
        if (n < 2) continue;
        cand.push({ mv: r[0], n, score: (r[2] + 0.5 * r[3]) / n, w: r[2], d: r[3], l: r[4] });
      }
    }
    if (!cand.length) return null;
    cand.sort((a, b2) => b2.score - a.score);
    // 只在“接近最佳胜率”的候选里抽样，避免整盘只走一条谱
    const best = cand[0].score;
    const keep = cand.filter((c) => c.score >= best - 0.12);
    const tot = keep.reduce((a, c) => a + Math.pow(c.n, 0.75), 0);
    let x = Math.random() * tot;
    for (const c of keep) {
      x -= Math.pow(c.n, 0.75);
      if (x <= 0) return c;
    }
    return keep[0];
  }

  // ---------------------------------------------------------------- 胜率预测
  // 直接用四维状态做多项逻辑回归：任何局面都能算，不依赖棋谱库是否命中
  function winProb(b, side, layerOverride) {
    const wp = MODEL && MODEL.winprob;
    if (!wp) return null;
    const L = layerOverride === undefined ? wp.layer : layerOverride;
    const g = geometry(b, side, L, L);
    const st = g.state;
    const z = [];
    for (let i = 0; i < wp.mean.length; i++) z.push((st[i] - wp.mean[i]) / (wp.std[i] || 1));
    const logits = wp.W.map((row, k) => {
      let s = wp.b[k];
      for (let i = 0; i < row.length; i++) s += row[i] * z[i];
      return s;
    });
    const mx = Math.max(...logits);
    const ex = logits.map((v) => Math.exp(v - mx));
    const sum = ex.reduce((a, v) => a + v, 0);
    const p = ex.map((v) => v / sum);            // 顺序对应 classes [-1, 0, 1]
    return {
      pLoss: p[0], pDraw: p[1], pWin: p[2],
      score: p[2] + 0.5 * p[1],
      layer: L, have: true
    };
  }

  // 链路第一段的令牌词袋模型：任何局面都能算胜率，不依赖库命中
  function winProbBow(b, side) {
    const wp = MODEL && MODEL.winprob_bow;
    if (!wp) return null;
    const toks = tokensOf(b, side);
    const lg = [wp.b[0], wp.b[1], wp.b[2]];
    let hit = 0;
    for (const t of toks) {
      const w = wp.w[t.key];
      if (!w) continue;
      hit++;
      lg[0] += w[0]; lg[1] += w[1]; lg[2] += w[2];
    }
    const mx = Math.max(...lg);
    const ex = lg.map((v) => Math.exp(v - mx));
    const sum = ex.reduce((a, v) => a + v, 0);
    const p = ex.map((v) => v / sum);
    return { pLoss: p[0], pDraw: p[1], pWin: p[2], score: p[2] + 0.5 * p[1], hit, tokens: toks.length };
  }

  // 只读查询（不抽样），给界面展示用
  function bookLookup(b, side, ply) {
    if (!BOOK || !BOOK.entries) return null;
    if (ply !== undefined && BOOK.plies && ply >= BOOK.plies) return null;
    const rows = BOOK.entries[keyOf(b, side)];
    if (!rows || !rows.length) return null;
    let total = 0;
    for (const r of rows) total += r[1];
    const moves = rows.map((r) => ({
      mv: r[0], n: r[1], score: (r[2] + 0.5 * r[3]) / r[1], w: r[2], d: r[3], l: r[4]
    })).sort((a, b2) => b2.score - a.score);
    return { total, moves, main: moves[0] };
  }

  function mvvLva(b, mv) {
    const f = fOf(mv), t = tOf(mv), cap = Math.abs(b[t]), att = Math.abs(b[f]);
    return cap ? 100000 + VALUE[cap] * 12 - VALUE[att] : 0;
  }

  function orderMoves(b, moves, side, depth, ph) {
    const kk = killers[depth] || [];
    return moves.map((mv) => {
      const f = fOf(mv), t = tOf(mv), typ = Math.abs(b[f]);
      let sc = mvvLva(b, mv);
      sc += history[f * 90 + t];
      if (kk[0] === mv) sc += 30000; else if (kk[1] === mv) sc += 15000;
      if (!b[t]) {
        // 非吃子：按阶段偏好给出前推/出动倾向
        const ty = (t / W) | 0, fy = (f / W) | 0;
        const adv = side === RED ? fy - ty : ty - fy;
        const w = typ === PAWN ? ph.pawn : typ === ROOK ? ph.rook : typ === CANNON ? ph.cannon : ph.horse;
        sc += adv * 30 * ph.adv * w;
      }
      return [sc, mv];
    }).sort((a, b2) => b2[0] - a[0]).map((p) => p[1]);
  }

  function quiesce(b, side, alpha, beta, qd, ph) {
    let stand = evaluate(b, ph) * side;
    if (qd <= 0) return stand;
    if (stand >= beta) return stand;
    if (stand > alpha) alpha = stand;
    const caps = genPseudo(b, side).filter((mv) => b[tOf(mv)] !== 0);
    const ordered = orderMoves(b, caps, side, 0, ph);
    for (const mv of ordered) {
      const f = fOf(mv), t = tOf(mv), cap = b[t];
      b[t] = b[f]; b[f] = 0;
      if (inCheck(b, side)) { b[f] = b[t]; b[t] = cap; continue; }
      nodes++;
      const sc = -quiesce(b, -side, -beta, -alpha, qd - 1, ph);
      b[f] = b[t]; b[t] = cap;
      if (sc >= beta) return sc;
      if (sc > alpha) alpha = sc;
    }
    return alpha;
  }

  let curKey = 0, repSet = null, pathKeys = [];

    function negamax(b, side, depth, alpha, beta, ph, root) {
    if ((nodes & 1023) === 0 && Date.now() > deadline) { aborted = true; return 0; }
    if (depth <= 0) return quiesce(b, side, alpha, beta, 3, ph);
    const moves = orderMoves(b, genPseudo(b, side), side, depth, ph);
    let best = -Infinity, any = false;
    for (const mv of moves) {
      const f = fOf(mv), t = tOf(mv), cap = b[t], piece = b[f];
      b[t] = piece; b[f] = 0;
      if (inCheck(b, side)) { b[f] = b[t]; b[t] = cap; continue; }
      const saved = curKey;
      curKey ^= ZOB[f * 15 + pidx(piece)] ^ ZOB[t * 15 + pidx(piece)]
              ^ (cap ? ZOB[t * 15 + pidx(cap)] : 0) ^ SIDE_Z;
      nodes++;
      any = true;
      let sc;
      if (repSet.has(curKey) || pathKeys.indexOf(curKey) >= 0) {
        sc = 0;                                  // 重复局面按和棋计
      } else {
        pathKeys.push(curKey);
        sc = -negamax(b, -side, depth - 1, -beta, -alpha, ph, false);
        pathKeys.pop();
      }
      curKey = saved;
      b[f] = b[t]; b[t] = cap;
      if (aborted) return best === -Infinity ? 0 : best;
      if (sc > best) best = sc;
      if (sc > alpha) {
        alpha = sc;
        if (!root) history[f * 90 + t] += depth * depth;
        if (alpha >= beta) {
          if (!killers[depth]) killers[depth] = [];
          if (killers[depth][0] !== mv) { killers[depth][1] = killers[depth][0]; killers[depth][0] = mv; }
          break;
        }
      }
    }
    if (!any) return -90000 + (10 - depth) * 100;  // 被将死或无路可走
    return best;
  }

  function search(b, side, opts) {
    opts = opts || {};
    const maxDepth = opts.depth || 4;
    const budget = opts.budget || 800;
    const ph = PHASE[opts.phase] || PHASE.maneuver;
    nodes = 0; aborted = false;
    deadline = Date.now() + budget;
    history.fill(0);
    curKey = hashBoard(b) ^ (side === RED ? SIDE_Z : 0);
    repSet = new Set(opts.history || []);
    pathKeys = [curKey];
    let bestMv = 0, bestScore = 0, doneDepth = 0;
    const t0 = Date.now();
    for (let d = 1; d <= maxDepth; d++) {
      let alpha = -Infinity, beta = Infinity;
      let localBest = 0, localScore = -Infinity;
      const moves = orderMoves(b, genPseudo(b, side), side, d, ph);
      for (const mv of moves) {
        const f = fOf(mv), t = tOf(mv), cap = b[t], piece = b[f];
        b[t] = piece; b[f] = 0;
        if (inCheck(b, side)) { b[f] = b[t]; b[t] = cap; continue; }
        const saved = curKey;
        curKey ^= ZOB[f * 15 + pidx(piece)] ^ ZOB[t * 15 + pidx(piece)]
                ^ (cap ? ZOB[t * 15 + pidx(cap)] : 0) ^ SIDE_Z;
        nodes++;
        let sc;
        if (repSet.has(curKey) || pathKeys.indexOf(curKey) >= 0) {
          sc = 0;
        } else {
          pathKeys.push(curKey);
          sc = -negamax(b, -side, d - 1, -beta, -alpha, ph, false);
          pathKeys.pop();
        }
        curKey = saved;
        b[f] = b[t]; b[t] = cap;
        if (aborted) break;
        if (opts.noise) sc += (Math.random() - 0.5) * opts.noise;   // 仅根节点抖动，避免每局同一条线
        if (sc > localScore) { localScore = sc; localBest = mv; }
        if (sc > alpha) alpha = sc;
      }
      if (aborted && doneDepth > 0) break;
      if (localBest) { bestMv = localBest; bestScore = localScore; doneDepth = d; }
      if (Math.abs(bestScore) > 80000) break;   // 已见杀
      if (Date.now() - t0 > budget * 0.4) break;
    }
    if (!bestMv) {
      const lg = legal(b, side);
      bestMv = lg.length ? lg[0] : 0;
    }
    return { mv: bestMv, score: bestScore, depth: doneDepth, nodes, ms: Date.now() - t0 };
  }

  function perft(b, side, depth) {
    if (depth === 0) return 1;
    if (depth === 1) return legal(b, side).length;
    let n = 0;
    for (const mv of genPseudo(b, side)) {
      const f = fOf(mv), t = tOf(mv), cap = b[t];
      b[t] = b[f]; b[f] = 0;
      if (!inCheck(b, side)) n += perft(b, -side, depth - 1);
      b[f] = b[t]; b[t] = cap;
    }
    return n;
  }

  global.XQ = {
    W, H, RED, BLACK, KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN,
    NAME, VALUE, ROLE_W, CLASSES, CLASS_CN, PHASE,
    sq, initial, genPseudo, legal, inCheck, attacked, facing, evaluate, search, perft,
    hashBoard, keyOf, fOf, tOf, mk,
    setBook, bookPick, bookInfo, bookLookup, winProb, winProbBow,
    setModel, tokensOf, geometry, retrieve, normalize, situationLabel, stateOf
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.XQ;
})(typeof window !== 'undefined' ? window : globalThis);
