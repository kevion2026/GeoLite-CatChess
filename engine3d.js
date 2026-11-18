/* GeoLite-Xiangqi 3D / 引力版引擎 —— 规则、三维几何链路、引力势选着，无搜索树。
   浏览器与 node 共用。 */
(function (global) {
  'use strict';

  const W = 9, H = 10, RED = 1, BLACK = -1;
  const KING = 1, ADVISOR = 2, ELEPHANT = 3, HORSE = 4, ROOK = 5, CANNON = 6, PAWN = 7;
  const VALUE = { 1: 1000, 2: 300, 3: 300, 4: 550, 5: 1100, 6: 580, 7: 180 };
  const ROLE_W = { 1: 1.40, 2: 0.80, 3: 0.85, 4: 1.00, 5: 1.25, 6: 1.10, 7: 0.95 };
  const NAME = {
    [RED]: { 1: '帅', 2: '仕', 3: '相', 4: '马', 5: '车', 6: '炮', 7: '兵' },
    [BLACK]: { 1: '将', 2: '士', 3: '象', 4: '马', 5: '車', 6: '砲', 7: '卒' }
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
  // 引力势的相位权重：类别只改变各项势的系数，不改变势本身
  const PHASE = {
    open: { att: 0.75, def: 0.80, exp: 0.90, mass: 1.15, cen: 1.25 },
    contact: { att: 1.00, def: 1.00, exp: 1.00, mass: 1.00, cen: 1.00 },
    attack: { att: 1.45, def: 0.85, exp: 1.00, mass: 1.00, cen: 1.05 },
    defense: { att: 0.80, def: 1.55, exp: 1.25, mass: 0.95, cen: 0.85 },
    endgame: { att: 1.20, def: 1.10, exp: 0.85, mass: 1.30, cen: 1.10 },
    maneuver: { att: 1.00, def: 1.00, exp: 1.00, mass: 1.00, cen: 1.00 }
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

  // 几何威胁：敌方在边线/底线的密度 + 九宫周边压力（替代纯回防权重）
  function threatScore(b, side) {
    const k = findKing(b, side);
    if (k < 0) return 0;
    const kx = k % W, ky = (k / W) | 0;
    const ownY = side === RED ? 7 : 2;      // 己方底线方向
    let p = 0;
    if (inCheck(b, side)) p += 3;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q || sside(q) !== -side) continue;
      const x = s % W, y = (s / W) | 0;
      const t = Math.abs(q);
      const w = t === ROOK ? 3 : (t === CANNON ? 2 : 1);
      if (Math.abs(x - kx) <= 2 && Math.abs(y - ky) <= 2) p += w * 1.5;   // 九宫贴身
      const edge = (x === 0 || x === 8);
      const deep = (side === RED ? y >= 7 : y <= 2);                      // 压到我方底线
      if (edge && deep) p += w * 1.2;                                     // 边线沉底飞刀
      else if (edge && t === CANNON) p += w * 0.6;                        // 边炮瞄中
    }
    return p;
  }

  // 截击：己方有多少敌方重子正被我们反切线（攻击其根部）
  function interceptCount(b, side) {
    const k = findKing(b, side);
    if (k < 0) return 0;
    const kx = k % W, ky = (k / W) | 0;
    let n = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q || sside(q) !== -side) continue;
      const t = Math.abs(q);
      if (t !== ROOK && t !== CANNON && t !== HORSE) continue;
      const x = s % W, y = (s / W) | 0;
      if (Math.abs(x - kx) <= 3 && Math.abs(y - ky) <= 3 && attacked(b, s, side)) n++;
    }
    return n;
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

  // ---------------------------------------------------------------- 交换估值
  /* 兵种分值（厘兵）只服务于「吃子是否划算」，与几何估值互不干扰：
     几何仍然是唯一的形势判断，这里只回答“这一步会不会白丢子”。 */
  const SEE_V = { 1: 8000, 2: 200, 3: 200, 4: 450, 5: 900, 6: 450, 7: 100 };

  /* 攻击 s 的 by 方棋子格位。车/将走直线、炮隔一子、马走日带马腿、兵按方向，
     与 attacked() 同构，区别是返回全部攻击子而不是布尔值。 */
  function attackersOf(b, s, by) {
    const out = [];
    const x = s % W, y = (s / W) | 0;
    for (let k = 0; k < 4; k++) {
      const dx = ORTHO[k][0], dy = ORTHO[k][1];
      let nx = x + dx, ny = y + dy, step = 1, screen = 0;
      while (nx >= 0 && nx < W && ny >= 0 && ny < H) {
        const q = b[ny * W + nx];
        if (q) {
          if (screen === 0) {
            if (sside(q) === by) {
              const t = Math.abs(q);
              if (t === ROOK || (t === KING && step === 1)) out.push(ny * W + nx);
            }
            screen = 1;
          } else {
            if (sside(q) === by && Math.abs(q) === CANNON) out.push(ny * W + nx);
            break;
          }
        }
        nx += dx; ny += dy; step++;
      }
    }
    for (let i = 0; i < HORSE_MV.length; i++) {
      const dx = HORSE_MV[i][0], dy = HORSE_MV[i][1], lx = HORSE_MV[i][2], ly = HORSE_MV[i][3];
      const sx = x - dx, sy = y - dy;
      if (!inBoard(sx, sy)) continue;
      const q = b[sy * W + sx];
      if (!q || sside(q) !== by || Math.abs(q) !== HORSE) continue;
      const gx = sx + lx, gy = sy + ly;
      if (inBoard(gx, gy) && b[gy * W + gx] === 0) out.push(sy * W + sx);
    }
    const fwd = by === RED ? 1 : -1;                  // 兵从 y+1 走上来（红兵向上）
    const cand = [[x, y + fwd]];
    if (crossed(y, by)) cand.push([x - 1, y], [x + 1, y]);
    for (const [cx, cy] of cand) {
      if (!inBoard(cx, cy)) continue;
      const q = b[cy * W + cx];
      if (q && sside(q) === by && Math.abs(q) === PAWN) out.push(cy * W + cx);
    }
    return out;
  }

  /* 静态交换估值：从 to 开始按「最廉攻击子先上」把交换列完，返回先手方净收益（厘兵）。
     负数表示这一口吃下去是亏的。 */
  function seeCapture(b, from, to) {
    const victim = b[to];
    if (!victim) return 0;
    const first = b[from];
    const gain = [SEE_V[Math.abs(victim)] || 100];
    const stack = [{ sq: from, p: first }];
    b[to] = first; b[from] = 0;
    let side = -sside(first), cur = first;
    for (let d = 0; d < 6; d++) {
      const att = attackersOf(b, to, side).filter((s) => b[s] !== 0);
      if (!att.length) break;
      let best = att[0];
      for (let i = 1; i < att.length; i++) {
        if ((SEE_V[Math.abs(b[att[i]])] || 100) < (SEE_V[Math.abs(b[best])] || 100)) best = att[i];
      }
      gain.push((SEE_V[Math.abs(cur)] || 100) - gain[gain.length - 1]);
      cur = b[best];
      stack.push({ sq: best, p: cur });
      b[to] = cur; b[best] = 0;
      side = -side;
    }
    for (let i = stack.length - 1; i >= 0; i--) b[stack[i].sq] = stack[i].p;
    b[to] = victim;
    for (let d = gain.length - 1; d > 0; d--) gain[d - 1] = Math.min(gain[d - 1], -gain[d]);
    return gain[0];
  }

  /* 该格上的己方子是否「实质危险」：攻方多于守方，且最廉攻子比它便宜（或干脆没人保）。
     返回将要丢掉的厘兵，0 表示安全。 */
  function exposedValue(b, s, side) {
    const piece = b[s];
    if (!piece || sside(piece) !== side) return 0;
    const val = SEE_V[Math.abs(piece)] || 100;
    if (val < 130) return 0;                          // 士象兵不必计较
    const att = attackersOf(b, s, -side);
    if (!att.length) return 0;
    const def = attackersOf(b, s, side).filter((q) => q !== s);
    let minAtt = Infinity;
    for (const a of att) minAtt = Math.min(minAtt, SEE_V[Math.abs(b[a])] || 100);
    if (!def.length) return minAtt < val ? val : 0;
    if (att.length > def.length && minAtt < val) return val * (att.length - def.length) / att.length;
    return 0;
  }

  // ---------------------------------------------------------------- 三维几何
  let MODEL = null, COORDS = null, COORDS_B = null, COORDS_C = null, CLS = 'maneuver';
  function setModel(m) {
    MODEL = m;
    // 核宽缩放随模型走：实测平滑 2.5 倍比原始 h 稳定得多（300 局 +2.7 手、速败 5.7%→2.3%）
    if (m && m.tree && m.tree.hScale) H_SCALE = m.tree.hScale;
    COORDS = {};
    const tab = m.coords3a || m.coords3 || m.coords || m.coords2;
    for (const k in tab) COORDS[k] = tab[k];
    COORDS_B = null;
    if (m.coords3b) {
      COORDS_B = {};
      for (const k in m.coords3b) COORDS_B[k] = m.coords3b[k];
    }
    COORDS_C = null;
    if (m.coords3c) {
      COORDS_C = {};
      for (const k in m.coords3c) COORDS_C[k] = m.coords3c[k];
    }
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

  /* 加权质心 + 协方差主特征向量（幂迭代），与 Python 的 eigh 结果同向。 */
  function fitLine3(pts) {
    let sw = 0;
    const sw3 = [0, 0, 0];
    for (const p of pts) {
      sw += p.w;
      sw3[0] += p.w * p.c[0]; sw3[1] += p.w * p.c[1]; sw3[2] += p.w * p.c[2];
    }
    if (sw <= 0) return { c: [0, 0, 0], v: [1, 0, 0], lam: 0 };
    const c = [sw3[0] / sw, sw3[1] / sw, sw3[2] / sw];
    const cov = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (const p of pts) {
      const d = [p.c[0] - c[0], p.c[1] - c[1], p.c[2] - c[2]];
      for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] += p.w * d[i] * d[j];
    }
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] /= sw;
    /* 对称 3×3 用解析特征分解（Smith 三角解法）替代 160 次幂迭代：
       每空间省掉 160 次矩阵向量乘与 160 次数组分配，且结果确定、无迭代残留。
       剖面实测 fitLine3 原占单次 geometry 的 90% 以上。 */
    const a11 = cov[0][0], a22 = cov[1][1], a33 = cov[2][2];
    const a12 = cov[0][1], a13 = cov[0][2], a23 = cov[1][2];
    const p1 = a12 * a12 + a13 * a13 + a23 * a23;
    let v;
    if (p1 < 1e-18) {
      // 已是对角阵，主轴就是最大对角元所在坐标轴
      v = (a11 >= a22 && a11 >= a33) ? [1, 0, 0] : (a22 >= a33 ? [0, 1, 0] : [0, 0, 1]);
    } else {
      const q = (a11 + a22 + a33) / 3;
      const p2 = (a11 - q) * (a11 - q) + (a22 - q) * (a22 - q) + (a33 - q) * (a33 - q) + 2 * p1;
      const p = Math.sqrt(p2 / 6);
      const b11 = (a11 - q) / p, b22 = (a22 - q) / p, b33 = (a33 - q) / p;
      const b12 = a12 / p, b13 = a13 / p, b23 = a23 / p;
      const det = b11 * (b22 * b33 - b23 * b23) - b12 * (b12 * b33 - b23 * b13) + b13 * (b12 * b23 - b22 * b13);
      let r = det / 2;
      if (r > 1) r = 1; else if (r < -1) r = -1;
      const phi = Math.acos(r) / 3;
      const e1 = q + 2 * p * Math.cos(phi);
      // (A − e1·I) 有两行线性相关，任取两行叉积即落在其零空间，取范数最大者更稳
      const x1 = a11 - e1, x2 = a22 - e1, x3 = a33 - e1;
      const c1 = [a12 * a23 - a13 * x2, a13 * a12 - x1 * a23, x1 * x2 - a12 * a12];
      const c2 = [a12 * x3 - a13 * a23, a13 * a13 - x1 * x3, x1 * a23 - a12 * a13];
      const c3 = [x2 * x3 - a23 * a23, a23 * a13 - a12 * x3, a12 * a23 - x2 * a13];
      let best = c1, bn = c1[0] * c1[0] + c1[1] * c1[1] + c1[2] * c1[2];
      const n2 = c2[0] * c2[0] + c2[1] * c2[1] + c2[2] * c2[2];
      if (n2 > bn) { best = c2; bn = n2; }
      const n3 = c3[0] * c3[0] + c3[1] * c3[1] + c3[2] * c3[2];
      if (n3 > bn) { best = c3; bn = n3; }
      if (bn < 1e-20) {
        v = [0.5774, 0.5774, 0.5774];          // 三重简并（各向同性点云），任取方向
      } else {
        const n = Math.sqrt(bn);
        v = [best[0] / n, best[1] / n, best[2] / n];
      }
    }
    // 符号规范化：最大分量取正，保证同一局面在两端得到同一个向量
    const idx = [Math.abs(v[0]), Math.abs(v[1]), Math.abs(v[2])].reduce((a, b2, i, arr) => (b2 >= arr[a] ? i : a), 0);
    if (v[idx] < 0) v = [-v[0], -v[1], -v[2]];
    const lam = cov[0][0] * v[0] * v[0] + cov[1][1] * v[1] * v[1] + cov[2][2] * v[2] * v[2] +
      2 * (cov[0][1] * v[0] * v[1] + cov[0][2] * v[0] * v[2] + cov[1][2] * v[1] * v[2]);
    return { c, v, lam };
  }

  function stateOf3(pts) {
    const f = fitLine3(pts);
    let sw = 0, res = 0;
    for (const p of pts) {
      sw += p.w;
      const d = [p.c[0] - f.c[0], p.c[1] - f.c[1], p.c[2] - f.c[2]];
      const proj = d[0] * f.v[0] + d[1] * f.v[1] + d[2] * f.v[2];
      const perp2 = Math.max(d[0] * d[0] + d[1] * d[1] + d[2] * d[2] - proj * proj, 0);
      res += p.w * perp2;
    }
    const rho = Math.sqrt(res / Math.max(sw, 1e-9));
    return {
      state: [f.c[0], f.c[1], f.c[2], f.v[0], f.v[1], f.v[2], rho],
      centroid: f.c.slice(), axis: f.v.slice(), rho
    };
  }

  function perp2List(pts) {
    const f = fitLine3(pts);
    return pts.map((p) => {
      const d = [p.c[0] - f.c[0], p.c[1] - f.c[1], p.c[2] - f.c[2]];
      const proj = d[0] * f.v[0] + d[1] * f.v[1] + d[2] * f.v[2];
      return Math.max(d[0] * d[0] + d[1] * d[1] + d[2] * d[2] - proj * proj, 0);
    });
  }

  /* 双三维：同一批令牌在两套坐标里各成一组点，各自拟合主轴；
     压缩按两空间垂直距离平方和选弃，状态拼接为 2×7 维。 */
  function geometryDual(b, side, layers, maxLayers) {
    maxLayers = (maxLayers === undefined || maxLayers === null) ? layers : maxLayers;
    const raw = tokensOf(b, side);
    const ta = [], tb = [];
    for (const t of raw) {
      const ca = COORDS[t.key], cb = COORDS_B[t.key];
      if (!ca || !cb) continue;
      const base = { key: t.key, w: t.w, t: t.t, s: t.s, bx: t.bx, by: t.by };
      ta.push(Object.assign({}, base, { c: [ca[0], ca[1], ca[2]] }));
      tb.push(Object.assign({}, base, { c: [cb[0], cb[1], cb[2]] }));
    }
    if (!ta.length) return { state: new Array(14).fill(0), layers: [], dropped: [], tokens: [], kept: [], a: null, b: null };
    let ka = ta.slice(), kb = tb.slice();
    const recs = [], dropped = [];
    let sa = stateOf3(ka), sb = stateOf3(kb);
    const merge = (sa, sb) => sa.state.concat(sb.state);
    let cur = merge(sa, sb);
    recs.push({ layer: 0, state: cur.slice(), kept: ka.length, rhoA: sa.rho, rhoB: sb.rho, drop: null });
    for (let l = 1; l <= maxLayers; l++) {
      if (ka.length <= 3) {
        recs.push({ layer: l, state: cur.slice(), kept: ka.length, rhoA: sa.rho, rhoB: sb.rho, drop: null });
        continue;
      }
      const pa = perp2List(ka), pb = perp2List(kb);
      let best = 0, bestD = -1;
      for (let i = 0; i < ka.length; i++) {
        const d = pa[i] + pb[i];
        if (d > bestD + 1e-9 || (Math.abs(d - bestD) <= 1e-9 && ka[i].s < ka[best].s)) { bestD = Math.max(bestD, d); best = i; }
      }
      dropped.push({ layer: l, token: ka[best].key, type: ka[best].t, square: ka[best].s, perp: Math.sqrt(bestD) });
      const dropKey = ka[best].key;
      ka = ka.filter((_, i) => i !== best);
      kb = kb.filter((p) => p.key !== dropKey);
      sa = stateOf3(ka); sb = stateOf3(kb);
      cur = merge(sa, sb);
      recs.push({ layer: l, state: cur.slice(), kept: ka.length, rhoA: sa.rho, rhoB: sb.rho, drop: dropKey });
    }
    const L = Math.max(0, Math.min(layers, maxLayers));
    return {
      state: recs[L].state.slice(), at: recs[L], layers: recs, dropped,
      tokens: ta, kept: ka.map((p) => p.key),
      a: { tokens: ta, at: sa, state: sa.state },
      b: { tokens: tb, at: sb, state: sb.state }
    };
  }

  /* 三三维：邻域 / 共线 / 中距-同兵种，三套坐标各成一组点。
     第三空间专职仲裁：给前两个空间的候选着法打分。 */
  function geometryTriple(b, side, layers, maxLayers) {
    maxLayers = (maxLayers === undefined || maxLayers === null) ? layers : maxLayers;
    const raw = tokensOf(b, side);
    const tabs = [COORDS, COORDS_B, COORDS_C];
    const base = [];
    for (const t of raw) {
      const cs = tabs.map((tab) => tab[t.key]);
      if (cs.some((c) => !c)) continue;
      base.push({ key: t.key, w: t.w, t: t.t, s: t.s, bx: t.bx, by: t.by, cs });
    }
    if (!base.length) {
      return { state: new Array(21).fill(0), layers: [], dropped: [], tokens: [], kept: [], a: null, b: null, c: null };
    }
    const mk = (list, i) => list.map((p) => ({ w: p.w, c: p.cs[i], key: p.key, t: p.t, s: p.s }));
    let keep = base.slice();
    const dropped = [], recs = [];
    const fitAll = () => [0, 1, 2].map((i) => stateOf3(mk(keep, i)));
    let st = fitAll();
    const merge = (s) => s[0].state.concat(s[1].state).concat(s[2].state);
    let cur = merge(st);
    recs.push({ layer: 0, state: cur.slice(), kept: keep.length, rhoA: st[0].rho, rhoB: st[1].rho, rhoC: st[2].rho, drop: null });
    for (let l = 1; l <= maxLayers; l++) {
      if (keep.length <= 3) {
        recs.push({ layer: l, state: cur.slice(), kept: keep.length, rhoA: st[0].rho, rhoB: st[1].rho, rhoC: st[2].rho, drop: null });
        continue;
      }
      const perps = [0, 1, 2].map((i) => perp2List(mk(keep, i)));
      let best = 0, bestD = -1;
      for (let i = 0; i < keep.length; i++) {
        const d = perps[0][i] + perps[1][i] + perps[2][i];
        if (d > bestD + 1e-9 || (Math.abs(d - bestD) <= 1e-9 && keep[i].s < keep[best].s)) { bestD = Math.max(bestD, d); best = i; }
      }
      dropped.push({ layer: l, token: keep[best].key, type: keep[best].t, square: keep[best].s, perp: Math.sqrt(bestD) });
      keep = keep.filter((_, i) => i !== best);
      st = fitAll();
      cur = merge(st);
      recs.push({ layer: l, state: cur.slice(), kept: keep.length, rhoA: st[0].rho, rhoB: st[1].rho, rhoC: st[2].rho, drop: keep[best] ? keep[best].key : null });
    }
    const L = Math.max(0, Math.min(layers, maxLayers));
    return {
      state: recs[L].state.slice(), at: recs[L], layers: recs, dropped,
      tokens: mk(base, 0), kept: keep.map((p) => p.key),
      a: { tokens: mk(base, 0), at: st[0], state: st[0].state },
      b: { tokens: mk(base, 1), at: st[1], state: st[1].state },
      c: { tokens: mk(base, 2), at: st[2], state: st[2].state }
    };
  }

  function geometry(b, side, layers, maxLayers) {
    if (COORDS_C) return geometryTriple(b, side, layers, maxLayers);
    if (COORDS_B) return geometryDual(b, side, layers, maxLayers);
    maxLayers = (maxLayers === undefined || maxLayers === null) ? layers : maxLayers;
    const raw = tokensOf(b, side);
    const toks = [];
    for (const t of raw) {
      const c = COORDS[t.key];
      if (!c) continue;
      toks.push({ key: t.key, c: [c[0], c[1], c[2]], w: t.w, t: t.t, s: t.s, bx: t.bx, by: t.by });
    }
    if (!toks.length) return { state: [0, 0, 0, 0, 0, 0, 0], layers: [], dropped: [], tokens: [], kept: [] };
    let keep = toks.slice();
    const recs = [], dropped = [];
    let cur = stateOf3(keep);
    recs.push({ layer: 0, state: cur.state.slice(), kept: keep.length, residual: cur.rho, drop: null,
                axis: cur.axis.slice(), centroid: cur.centroid.slice() });
    for (let l = 1; l <= maxLayers; l++) {
      if (keep.length <= 3) {
        recs.push({ layer: l, state: cur.state.slice(), kept: keep.length, residual: cur.rho, drop: null,
                    axis: cur.axis.slice(), centroid: cur.centroid.slice() });
        continue;
      }
      const f = fitLine3(keep);
      let best = 0, bestD = -1;
      keep.forEach((p, i) => {
        const d = [p.c[0] - f.c[0], p.c[1] - f.c[1], p.c[2] - f.c[2]];
        const proj = d[0] * f.v[0] + d[1] * f.v[1] + d[2] * f.v[2];
        const perp2 = Math.max(d[0] * d[0] + d[1] * d[1] + d[2] * d[2] - proj * proj, 0);
        if (perp2 > bestD + 1e-9 || (Math.abs(perp2 - bestD) <= 1e-9 && p.s < keep[best].s)) {
          bestD = Math.max(bestD, perp2); best = i;
        }
      });
      const dropTok = keep[best];
      dropped.push({ layer: l, token: dropTok.key, type: dropTok.t, square: dropTok.s, perp: Math.sqrt(bestD) });
      keep = keep.filter((_, i) => i !== best);
      cur = stateOf3(keep);
      recs.push({ layer: l, state: cur.state.slice(), kept: keep.length, residual: cur.rho, drop: dropTok.key,
                  axis: cur.axis.slice(), centroid: cur.centroid.slice() });
    }
    const L = Math.max(0, Math.min(layers, maxLayers));
    return { state: recs[L].state.slice(), at: recs[L], layers: recs, dropped, tokens: toks,
             kept: keep.map((p) => p.key) };
  }

  function normOf(layer) {
    const n = (MODEL && (MODEL.norm[String(layer)] || MODEL.norm[layer])) || null;
    return n;
  }

  function retrieve(vec, layer, k) {
    if (!MODEL || !MODEL.library) return null;
    const n = normOf(layer);
    const D = vec.length;
    const z = vec.map((v, i) => (v - n.mean[i]) / n.std[i]);
    const protos = MODEL.prototypes[String(layer)] || MODEL.prototypes[layer];
    const pd = protos.map((p, i) => ({
      cls: CLASSES[i],
      dist: Math.sqrt(p.reduce((s, v, j) => s + (v - z[j]) * (v - z[j]), 0))
    })).sort((a, b2) => a.dist - b2.dist);
    const libRaw = MODEL.library.states[String(layer)] || MODEL.library.states[layer];
    const labels = MODEL.library.labels;
    const cand = [];
    for (let i = 0; i < libRaw.length; i++) {
      const row = libRaw[i];
      let s = 0;
      for (let j = 0; j < D; j++) {
        const dz = (row[j] - n.mean[j]) / n.std[j] - z[j];
        s += dz * dz;
      }
      cand.push([Math.sqrt(s), labels[i], i]);
    }
    cand.sort((a, b2) => a[0] - b2[0]);
    const top = cand.slice(0, k || (MODEL.meta && MODEL.meta.k) || 5);
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
      proto: pd,
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

  // ---------------------------------------------------------------- 引力势
  /* 平方反比势核（离散格点）：phi(d) = 1 / (1 + d^2)，d 为切比雪夫间距。
     局面总势 = 己方质量向敌王的吸引 + 己方质量存量 + 中央占位
                - 敌方质量对本方王的压迫 - 己方棋子被引力锁定的惩罚。 */
  const K = { att: 620, mass: 34, cen: 14, def: 330, exp: 130, rep: 300, mate: 9000 };

  function gravity(b, mover, phase) {
    const ph = PHASE[phase] || PHASE.maneuver;
    const ek = findKing(b, -mover), ok = findKing(b, mover);
    let att = 0, mass = 0, cen = 0, def = 0, exp = 0;
    const ekX = ek >= 0 ? ek % W : 4, ekY = ek >= 0 ? (ek / W) | 0 : (mover === RED ? 0 : 9);
    const okX = ok >= 0 ? ok % W : 4, okY = ok >= 0 ? (ok / W) | 0 : (mover === RED ? 9 : 0);
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0) continue;
      const so = sside(p), t = Math.abs(p), m = ROLE_W[t];
      const x = s % W, y = (s / W) | 0;
      if (so === mover) {
        mass += m;
        cen += m * (1 - Math.abs(x - 4) / 4) * 0.5 + m * (1 - Math.abs(y - (mover === RED ? 4.5 : 4.5)) / 9) * 0.5;
        const d = Math.max(Math.abs(x - ekX), Math.abs(y - ekY));
        att += m / (1 + d * d);
        if (attacked(b, s, -mover)) {
          // 被吃即失去该质量；有己方子护住时只损失一半
          exp += m * (attacked(b, s, mover) ? 0.85 : 2.3);
        }
      } else {
        const d = Math.max(Math.abs(x - okX), Math.abs(y - okY));
        def += m / (1 + d * d);
      }
    }
    const score = ph.att * K.att * att + ph.mass * K.mass * mass + ph.cen * K.cen * cen
      - ph.def * K.def * def - ph.exp * K.exp * exp;
    return { score, att, mass, cen, def: -def, exp: -exp, phase, ph };
  }

  // 单层评估：走完一步后，以走子方视角算引力势，取最大
  function gravityPick(b, side, opts) {
    opts = opts || {};
    const phCls = opts.phase || CLS;
    const noise = opts.noise || 0;
    const repSet = new Set(opts.history || []);
    const mine = legal(b, side);
    if (!mine.length) return null;
    const cand = [];
    for (const mv of mine) {
      const f = fOf(mv), t = tOf(mv), cap = b[t], piece = b[f];
      b[t] = piece; b[f] = 0;
      let score = gravity(b, side, phCls).score;
      // 吃子：被吃子的质量直接离场，另有少量“吞并”奖励（质量守恒的直觉）
      if (cap) score += ROLE_W[Math.abs(cap)] * K.mass * 0.15 * 10;
      // 将死：对手无合法着法且被将军
      if (inCheck(b, -side) && legal(b, -side).length === 0) score += K.mate;
      const key = hashBoard(b) ^ (-side === RED ? 0x5bf03635 : 0);
      if (repSet.has(key)) score -= K.rep;
      b[f] = b[t]; b[t] = cap;
      cand.push({ mv, score });
    }
    cand.sort((a, b2) => b2.score - a.score);
    const pool = cand.filter((c) => c.score >= cand[0].score - Math.max(noise, 0.001));
    const pick = noise > 0 ? pool[Math.floor(Math.random() * pool.length)] : cand[0];
    return { mv: pick.mv, score: pick.score, top: cand.slice(0, 8), nodes: cand.length };
  }

  // ---------------------------------------------------------------- 双路线引力势
  /* 局部路线：邻域点云的密集度（连环马、担子炮、士象联防）。
     全局路线：主轴延伸与明线控制（车占明线、炮镇中路、沉底车）。 */
  const K_LOCAL = { att: 430, cluster: 25, mass: 16, def: 210, exp: 140 };
  const K_GLOBAL = { reach: 27, mass: 16, center: 17, deep: 24, def: 230, exp: 140 };

  function gravityLocal(b, mover, phase) {
    const ph = PHASE[phase] || PHASE.maneuver;
    const ek = findKing(b, -mover), ok = findKing(b, mover);
    const ekX = ek >= 0 ? ek % W : 4, ekY = ek >= 0 ? (ek / W) | 0 : (mover === RED ? 0 : 9);
    const okX = ok >= 0 ? ok % W : 4, okY = ok >= 0 ? (ok / W) | 0 : (mover === RED ? 9 : 0);
    let att = 0, mass = 0, def = 0, exp = 0;
    const own = [];
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0) continue;
      const so = sside(p), t = Math.abs(p), m = ROLE_W[t];
      const x = s % W, y = (s / W) | 0;
      if (so === mover) {
        mass += m;
        const d = Math.max(Math.abs(x - ekX), Math.abs(y - ekY));
        att += m / (1 + d * d);
        if (t === ADVISOR || t === ELEPHANT) {
          const dk = Math.max(Math.abs(x - okX), Math.abs(y - okY));
          if (dk <= 2) att += m * 0.35;          // 士象联防落在九宫附近
        }
        if (attacked(b, s, -mover)) exp += m * (attacked(b, s, mover) ? 0.85 : 2.3);
        own.push({ x, y, m });
      } else {
        const d = Math.max(Math.abs(x - okX), Math.abs(y - okY));
        def += m / (1 + d * d);
      }
    }
    let cluster = 0;
    for (let i = 0; i < own.length; i++) {
      for (let j = i + 1; j < own.length; j++) {
        const d = Math.max(Math.abs(own[i].x - own[j].x), Math.abs(own[i].y - own[j].y));
        if (d <= 2) cluster += own[i].m * own[j].m / (1 + d * d);
      }
    }
    const score = ph.att * (K_LOCAL.att * att * 0.62) + K_LOCAL.cluster * cluster + ph.mass * (K_LOCAL.mass * mass)
      - ph.def * (K_LOCAL.def * def) - ph.exp * (K_LOCAL.exp * exp);
    return { score, att, cluster, mass, def: -def, exp: -exp };
  }

  function gravityGlobal(b, mover, phase) {
    const ph = PHASE[phase] || PHASE.maneuver;
    const ek = findKing(b, -mover), ok = findKing(b, mover);
    const okX = ok >= 0 ? ok % W : 4, okY = ok >= 0 ? (ok / W) | 0 : (mover === RED ? 9 : 0);
    let reach = 0, mass = 0, center = 0, deep = 0, def = 0, exp = 0;
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (p === 0) continue;
      const so = sside(p), t = Math.abs(p), m = ROLE_W[t];
      const x = s % W, y = (s / W) | 0;
      if (so === mover) {
        mass += m;
        if (t === ROOK || t === CANNON) {
          let mob = 0;
          for (let k = 0; k < 4; k++) {
            const dx = k === 0 ? 1 : k === 1 ? -1 : 0, dy = k === 2 ? 1 : k === 3 ? -1 : 0;
            let nx = x + dx, ny = y + dy;
            while (nx >= 0 && nx < 9 && ny >= 0 && ny < 10 && !b[ny * W + nx]) { mob++; nx += dx; ny += dy; }
          }
          reach += m * mob / 8;
          if (x === 4) center += m;
          if (crossed(y, mover)) deep += m * (crossed(y + (mover === RED ? -1 : 1), mover) ? 1.35 : 1.0);
        } else {
          const d = Math.max(Math.abs(x - (ek >= 0 ? ek % W : 4)), Math.abs(y - (ek >= 0 ? (ek / W) | 0 : 0)));
          reach += m / (1 + d * d);
        }
        if (attacked(b, s, -mover)) exp += m * (attacked(b, s, mover) ? 0.85 : 2.3);
      } else {
        const d = Math.max(Math.abs(x - okX), Math.abs(y - okY));
        def += (t === ROOK || t === CANNON ? m * 1.3 : m) / (1 + d * d);
      }
    }
    const score = K_GLOBAL.reach * reach + K_GLOBAL.mass * mass + K_GLOBAL.center * center + K_GLOBAL.deep * deep
      - K_GLOBAL.def * def - K_GLOBAL.exp * exp;
    return { score, reach, mass, center, deep, def: -def, exp: -exp };
  }

  function pickWith(b, side, fn, phase, noise, repSet) {
    const mine = legal(b, side);
    if (!mine.length) return null;
    const cand = [];
    for (const mv of mine) {
      const f = fOf(mv), t = tOf(mv), cap = b[t], piece = b[f];
      b[t] = piece; b[f] = 0;
      let score = fn(b, side, phase).score;
      if (cap) score += ROLE_W[Math.abs(cap)] * 120;
      if (inCheck(b, -side) && legal(b, -side).length === 0) score += K.mate;
      if (repSet && repSet.has(hashBoard(b) ^ (-side === RED ? SIDE_Z : 0))) score -= K.rep;
      b[f] = b[t]; b[t] = cap;
      cand.push({ mv, score });
    }
    cand.sort((a, b2) => b2.score - a.score);
    const pool = cand.filter((c) => c.score >= cand[0].score - Math.max(noise, 1e-3));
    return { mv: (noise > 0 ? pool[Math.floor(Math.random() * pool.length)] : cand[0]).mv, score: cand[0].score, top: cand.slice(0, 6) };
  }

  /* 形特征：密集度（局部）、延伸与主轴斜率（全局）。 */
  function shapeOf(state, pts) {
    const c = [state[0], state[1], state[2]];
    const v = [state[3], state[4], state[5]];
    let sw = 0, dens = 0;
    let pmax = -Infinity, pmin = Infinity;
    for (const p of pts) {
      sw += p.w;
      const d2 = (p.c[0] - c[0]) ** 2 + (p.c[1] - c[1]) ** 2 + (p.c[2] - c[2]) ** 2;
      dens += p.w * Math.exp(-d2 / 1.6);
      const pr = (p.c[0] - c[0]) * v[0] + (p.c[1] - c[1]) * v[1] + (p.c[2] - c[2]) * v[2];
      if (pr > pmax) pmax = pr;
      if (pr < pmin) pmin = pr;
    }
    const span = pts.length ? pmax - pmin : 0;
    const slope = Math.min(5, Math.hypot(v[0], v[1]) / Math.max(Math.abs(v[2]), 1e-6));
    return [dens / Math.max(sw, 1e-9), span, slope];
  }

  /* 云库评分模型：三空间状态 + 形特征 + 子力结构 → 分值（走子方视角，单位 cp）。 */
  const MAT_V = { 2: 100, 3: 100, 4: 200, 5: 450, 6: 230, 7: 40 };
  function matFeats(b, side) {
    const own = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    const opp = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (!p) continue;
      const t = Math.abs(p);
      const k = t === PAWN ? 7 : t;
      if (sside(p) === side) {
        own[k]++;
        if (t === PAWN && crossed((s / W) | 0, side)) own[0]++;
      } else {
        opp[k]++;
        if (t === PAWN && crossed((s / W) | 0, -side)) opp[0]++;
      }
    }
    let mv = 0, mo = 0;
    for (let k = 2; k <= 7; k++) { mv += MAT_V[k] * own[k]; mo += MAT_V[k] * opp[k]; }
    const out = [(mv - mo) / 100];
    for (let k = 1; k <= 7; k++) out.push(own[k] - opp[k]);
    out.push(own[0] - opp[0]);
    return out;
  }

  /* 分支激活树：同一套 39 维特征 → 标准化 → 按距离激活邻近分支（核权重）
     各分支本地线性打分，再与全局线性按 λ 融合。全程离线，无网络请求。 */
  // 45 维里的 6 个九宫/边线威胁量，须与 Python feats45 完全同构
  /* ── 几何闭合层 ────────────────────────────────────────────────
     几何树从样本里“学”出局势，好处是能表达态势，坏处是守恒量也会被学歪：
     实测这棵树对子力的敏感度只有真实值的 ~1/4（拿掉对手六个车马炮只涨 543 cp），
     对车的开放线/底线占位甚至是负贡献（红车压到对方肋道底线 −11.9 cp）。
     所以把“守恒量”从学习里拿出来，用同一批棋子坐标直接算：
       子力 / 将帅受压 / 士象 / 车的通路 / 马腿 / 兵推进
     几何树继续负责姿态与风格，闭合层负责不随样本漂移的硬约束。      */
  const CL_V = { 2: 200, 3: 200, 4: 400, 5: 900, 6: 450, 7: 100 };
  const CLOSURE_W = [0, 0, 0, 0, 0, 0, 0, 0, 0];
  function kingPressure(b, ks, bySide) {
    const kx = ks % W, ky = (ks / W) | 0;
    let p = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q || sside(q) !== bySide) continue;
      const t = Math.abs(q);
      if (t === KING || t === ADVISOR || t === ELEPHANT) continue;
      const dx = Math.abs((s % W) - kx), dy = Math.abs(((s / W) | 0) - ky);
      if (dx > 2 || dy > 2) continue;
      p += t === ROOK ? 15 : t === CANNON ? 10 : t === HORSE ? 8 : t === PAWN ? 5 : 0;
    }
    return p;
  }
  /* 返回 9 项闭合量（已是 cp 量纲）：
     0 车 1 马 2 炮 3 兵 4 士象 5 将帅受压 6 车通路 7 马腿 8 兵推进  */
  function closureOf(b, side) {
    const ownFile = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    const oppFile = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    let matR = 0, matH = 0, matC = 0, matP = 0, guard = 0, pawn = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q) continue;
      const t = Math.abs(q), own = sside(q) === side, sg = own ? 1 : -1;
      const x = s % W, y = (s / W) | 0;
      if (t === PAWN) { if (own) ownFile[x]++; else oppFile[x]++; }
      if (t === KING) continue;
      if (t === ROOK) matR += sg * 900;
      else if (t === HORSE) matH += sg * 400;
      else if (t === CANNON) matC += sg * 450;
      else if (t === PAWN) matP += sg * 100;
      else guard += sg * 200;
      if (t === PAWN) {
        const adv = own ? (side === RED ? 9 - y : y) : (side === RED ? y : 9 - y);
        if (adv >= 4) pawn += sg * ((adv - 3) * 16 + (adv >= 7 ? 60 : 0));
      }
    }
    let rook = 0, horse = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q) continue;
      const t = Math.abs(q);
      if (t !== ROOK && t !== HORSE) continue;
      const own = sside(q) === side, sg = own ? 1 : -1;
      const x = s % W, y = (s / W) | 0;
      if (t === ROOK) {
        const f = own ? ownFile[x] : oppFile[x];
        rook += sg * (f === 0 ? 16 : f === 1 ? 5 : 0);
        // 侵入底线奖励必须按「该子自己的敌方底线」判定。原来无论红黑都查 y===0/1，
        // 结果黑车停在自家底线也被算成"侵入"，开局白送 -24。
        const inv1 = own ? (side === RED ? 0 : 9) : (side === RED ? 9 : 0);
        const inv2 = own ? (side === RED ? 1 : 8) : (side === RED ? 8 : 1);
        if (y === inv1) rook += sg * 12;
        if (y === inv2) rook += sg * 6;
      } else {
        let blk = 0;
        for (let d = 0; d < 4; d++) {
          const nx = x + ORTHO[d][0], ny = y + ORTHO[d][1];
          if (nx < 0 || nx > 8 || ny < 0 || ny > 9 || b[ny * W + nx] !== 0) blk++;
        }
        horse -= sg * blk * 8;
        if (x === 0 || x === 8) horse -= sg * 6;
      }
    }
    let kd = 0;
    const kOwn = findKing(b, side), kOpp = findKing(b, -side);
    if (kOwn >= 0) kd -= kingPressure(b, kOwn, -side);
    if (kOpp >= 0) kd += kingPressure(b, kOpp, side);

    /* 下列两项来自「几何树残差回归」（analyze_blind.js）：用 3802 个实战局面的
       (皮卡鱼评分 − 几何树评分) 去回归 9 个 45 维里没有的描述量，这两项系数最大、
       且校验集 R² 达 0.264。它们是闭合形式的几何量，不含任何学习型模型。 */
    // 出子差：仍停在本方后两排的车马炮（对方未出动 = 对我们有利）
    let dev = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q) continue;
      const t = Math.abs(q);
      if (t !== ROOK && t !== HORSE && t !== CANNON) continue;
      const own = sside(q) === side;
      const y = (s / W) | 0;
      const back = own ? (side === RED ? y >= 8 : y <= 1) : (side === RED ? y <= 1 : y >= 8);
      if (back) dev += own ? -1 : 1;
    }
    // 炮被闷：每个方向上的第一个阻挡子。挡得越多越没用（炮需一"架"两用，
    // 被自家子贴脸堵住的炮，价值远低于材料表上的 450）
    let cblk = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q || Math.abs(q) !== CANNON) continue;
      const own = sside(q) === side, sg = own ? 1 : -1;
      const x = s % W, y = (s / W) | 0;
      let cnt = 0;
      for (let d = 0; d < 4; d++) {
        let nx = x + ORTHO[d][0], ny = y + ORTHO[d][1];
        while (nx >= 0 && nx < 9 && ny >= 0 && ny < 10) {
          if (b[ny * W + nx] !== 0) { cnt++; break; }
          nx += ORTHO[d][0]; ny += ORTHO[d][1];
        }
      }
      cblk -= sg * cnt;
    }
    return [matR, matH, matC, matP, guard, kd, rook, horse, pawn, dev, cblk];
  }

  function threatFeats(b, side) {
    const k = findKing(b, side);
    if (k < 0) return [0, 0, 0, 0, 0, 0];
    const kx = k % W, ky = (k / W) | 0;
    let heavy = 0, def = 0, edge = 0, mat = 0, pal = 0, mob = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q) continue;
      const x = s % W, y = (s / W) | 0, t = Math.abs(q), own = sside(q) === side;
      mat += (own ? 1 : -1) * (VALUE[t] || 0);
      const dx = Math.abs(x - kx), dy = Math.abs(y - ky);
      if (!own && (t === HORSE || t === ROOK || t === CANNON) && Math.max(dx, dy) <= 2) heavy++;
      if (own && (t === ADVISOR || t === ELEPHANT || t === ROOK) && Math.max(dx, dy) <= 2) def++;
      if (!own && (x === 0 || x === 8) && (side === RED ? y >= 7 : y <= 2)) edge++;
    }
    for (let yy = Math.max(0, ky - 1); yy <= Math.min(9, ky + 1); yy++) {
      for (let xx = Math.max(0, kx - 1); xx <= Math.min(8, kx + 1); xx++) {
        if (attacked(b, yy * 9 + xx, -side)) pal++;
      }
    }
    for (const [dx, dy] of ORTHO) {
      const nx = kx + dx, ny = ky + dy;
      const inPal = nx >= 0 && nx < 9 && ny >= 0 && ny < 10 && (side === RED ? ny >= 7 : ny <= 2);
      if (inPal && b[ny * 9 + nx] === 0 && !attacked(b, ny * 9 + nx, -side)) mob++;
    }
    return [heavy, def, edge, pal, mob, mat / 100];
  }

  /* 第 46/47 维：九宫格火力交汇密度、防守空洞体积。
     只数静态几何关系，不依赖历史；Python feats45.tension_feats 为同构实现。 */
  function attackerCount(b, s, by) {
    const x = s % W, y = (s / W) | 0;
    let cnt = 0;
    // 直线：车、炮、将帅飞将
    for (const [dx, dy] of ORTHO) {
      let nx = x + dx, ny = y + dy, screen = 0;
      while (nx >= 0 && nx < W && ny >= 0 && ny < 10) {
        const q = b[ny * W + nx];
        if (q) {
          if (screen === 0) {
            if (sside(q) === by) {
              const t = Math.abs(q);
              if (t === ROOK) cnt++;
              else if (t === KING && dx === 0) cnt++;
            }
            screen = 1;
          } else {
            if (sside(q) === by && Math.abs(q) === CANNON) cnt++;
            break;
          }
        }
        nx += dx; ny += dy;
      }
    }
    // 斜线：士、象
    for (const [dx, dy] of DIAG) {
      const ax = x + dx, ay = y + dy;
      if (ax >= 0 && ax < W && ay >= 0 && ay < 10) {
        const q = b[ay * W + ax];
        if (q && sside(q) === by && Math.abs(q) === ADVISOR) cnt++;
      }
      const ex = x + 2 * dx, ey = y + 2 * dy, mx = x + dx, my = y + dy;
      if (ex >= 0 && ex < W && ey >= 0 && ey < 10 && b[my * W + mx] === 0) {
        const q = b[ey * W + ex];
        if (q && sside(q) === by && Math.abs(q) === ELEPHANT) cnt++;
      }
    }
    // 马：反查八个来源格，马腿为空
    for (const [dx, dy, lx, ly] of HORSE_MV) {
      const ox = x - dx, oy = y - dy;
      if (ox < 0 || ox >= W || oy < 0 || oy >= 10) continue;
      const q = b[oy * W + ox];
      if (!(q && sside(q) === by && Math.abs(q) === HORSE)) continue;
      const gx = ox + lx, gy = oy + ly;
      if (gx >= 0 && gx < W && gy >= 0 && gy < 10 && b[gy * W + gx] === 0) cnt++;
    }
    // 兵/卒：向前与左右
    const py = by === RED ? y + 1 : y - 1;
    if (py >= 0 && py < 10 && b[py * W + x] === PAWN * by) cnt++;
    for (const dx of [-1, 1]) {
      const nx = x + dx;
      if (nx >= 0 && nx < W && b[y * W + nx] === PAWN * by) cnt++;
    }
    return cnt;
  }

  function tensionFeats(b, side) {
    const ek = findKing(b, -side), ok = findKing(b, side);
    if (ek < 0 || ok < 0) return [0, 0];
    const ex = ek % W, ey = (ek / W) | 0;
    let cross = 0;
    for (let yy = Math.max(0, ey - 1); yy <= Math.min(9, ey + 1); yy++) {
      for (let xx = Math.max(0, ex - 1); xx <= Math.min(8, ex + 1); xx++) {
        if (attackerCount(b, yy * 9 + xx, side) >= 2) cross++;
      }
    }
    const ox = ok % W, oy = (ok / W) | 0;
    let voidVol = 0;
    for (let yy = Math.max(0, oy - 1); yy <= Math.min(9, oy + 1); yy++) {
      for (let xx = Math.max(0, ox - 1); xx <= Math.min(8, ox + 1); xx++) {
        const s = yy * 9 + xx;
        if (b[s] !== 0) continue;
        if (attackerCount(b, s, -side) > 0 && attackerCount(b, s, side) === 0) voidVol++;
      }
    }
    return [cross, voidVol];
  }

  /* 分支参数扁平化：把 centers / local.w / glob.w 展成 Float32Array，
     并把 ‖c‖² 预存，使每节点核计算只剩「一次点积 + 一次减法 + 一次 exp」。 */
  const SEG_CACHE = new WeakMap();
  /* 核宽缩放：h 越大，64 个专家的混合越平滑（接近全局线性）；越小则越局部。
     估值噪声大时平滑往往更稳，但会损失分辨力，所以做成可跑参数由实测决定。 */
  let H_SCALE = 1;
  function setHScale(k) {
    H_SCALE = (k > 0.2 && k < 5) ? k : 1;
  }

  function prepSeg(seg) {
    let P = SEG_CACHE.get(seg);
    if (P && P.hs === H_SCALE) return P;   // WeakMap 没有 clear，改核宽时靠版本字段失效
    const d = seg.mean.length, K = seg.centers.length;
    const c = new Float32Array(K * d), cn = new Float32Array(K);
    const lw = new Float32Array(K * d), lb = new Float32Array(K);
    for (let k = 0; k < K; k++) {
      const ck = seg.centers[k], lk = (seg.local && seg.local[k]) || { w: [], b: 0 };
      let s = 0;
      for (let i = 0; i < d; i++) { const x = ck[i]; c[k * d + i] = x; s += x * x; }
      cn[k] = s; lb[k] = lk.b || 0;
      for (let i = 0; i < d; i++) lw[k * d + i] = lk.w[i] || 0;
    }
    const gw = new Float32Array(d), mean = new Float32Array(d), std = new Float32Array(d);
    for (let i = 0; i < d; i++) { gw[i] = seg.glob.w[i]; mean[i] = seg.mean[i]; std[i] = seg.std[i] || 1; }
    P = { d, K, c, cn, lw, lb, gw, mean, std, hs: H_SCALE, invH2: 1 / (2 * seg.h * seg.h * H_SCALE * H_SCALE),
          lam: seg.lam, globB: seg.glob.b };
    SEG_CACHE.set(seg, P);
    return P;
  }

  /* ---------- 实战学习层：知彼（对手回应）/ 知己（崩盘预警） ----------
     两层都是线性打分表，权重由 train_battle.js 从实战轨迹里学出（不是神经网络）。
     它们只改变「考虑哪些对手回应」与「给多大风险加权」，局面估值仍只由几何树给出。 */
  const BF_DIM = 20;

  /* 着法层面的特征。训练与推理共用同一份实现，避免两端漂移。 */
  function battleFeats(b, side, mv) {
    const f = fOf(mv), t = tOf(mv);
    const piece = b[f], victim = b[t];
    const pv = Math.abs(piece), vv = victim ? Math.abs(victim) : 0;
    const x = t % W, y = (t / W) | 0;
    const oppK = findKing(b, -side);
    const okX = oppK >= 0 ? oppK % W : (side === RED ? 4 : 4);
    const okY = oppK >= 0 ? (oppK / W) | 0 : (side === RED ? 0 : 9);
    const dist = Math.max(Math.abs(x - okX), Math.abs(y - okY));
    const seeGain = victim ? seeCapture(b, f, t) : 0;
    let mat = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (q) mat += (sside(q) === side ? 1 : -1) * (VALUE[Math.abs(q)] || 0);
    }
    const cap = victim;
    b[t] = piece; b[f] = 0;
    const isChk = inCheck(b, -side);
    const destAtt = attacked(b, t, -side) ? 1 : 0;
    const destDef = attacked(b, t, side) ? 1 : 0;
    let threat = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (!q || sside(q) === side) continue;
      if (attacked(b, s, side)) threat += VALUE[Math.abs(q)] || 0;
    }
    b[f] = b[t]; b[t] = cap;
    const crossed = pv === PAWN && (side === RED ? y <= 4 : y >= 5);
    const out = new Float64Array(BF_DIM);
    out[0] = 1;
    out[1] = victim ? 1 : 0;
    out[2] = vv / 1000;
    out[3] = Math.max(-1.5, Math.min(1.5, seeGain / 400));
    out[4] = pv / 1000;
    out[5] = isChk ? 1 : 0;
    out[6] = (victim || isChk) ? 0 : 1;
    out[7] = dist / 9;
    out[8] = 1 - Math.abs(x - 4) / 4;
    out[9] = crossed ? 1 : 0;
    out[10] = destAtt;
    out[11] = destDef;
    out[12] = pv === PAWN ? 1 : 0;
    out[13] = pv === HORSE ? 1 : 0;
    out[14] = pv === ROOK ? 1 : 0;
    out[15] = pv === CANNON ? 1 : 0;
    out[16] = (pv === ADVISOR || pv === ELEPHANT) ? 1 : 0;
    out[17] = (mat + (victim ? (VALUE[vv] || 0) : 0)) / 1000;
    out[18] = Math.min(3, threat / 1000);
    out[19] = Math.min(2, (destAtt && !destDef ? (SEE_V[pv] || 0) : 0) / 1000);
    return out;
  }

  /* 局面上层特征：45 维几何（与树模型同一空间）+ 步数 + 子力。 */
  function dangerFeats(b, side, ply) {
    const seg = MODEL && MODEL.tree && MODEL.tree.model;
    const out = new Float64Array(47);
    if (!seg) return out;
    const g = geometry(b, side, 0, 0);
    const raw = g.state.concat(shapeOf(g.a.state, g.a.tokens))
      .concat(shapeOf(g.b.state, g.b.tokens)).concat(shapeOf(g.c.state, g.c.tokens));
    for (const v of matFeats(b, side)) raw.push(v);
    for (const v of threatFeats(b, side)) raw.push(v);
    const mean = seg.mean, std = seg.std;
    for (let i = 0; i < 45; i++) out[i] = (raw[i] - mean[i]) / (std[i] || 1);
    let mat = 0;
    for (let s = 0; s < 90; s++) {
      const q = b[s];
      if (q) mat += (sside(q) === side ? 1 : -1) * (VALUE[Math.abs(q)] || 0);
    }
    out[45] = (ply || 0) / 50;
    out[46] = mat / 1500;
    return out;
  }

  function dotW(w, f) {
    let s = w[w.length - 1] || 0;        // 最后一维是偏置
    const d = f.length;
    for (let i = 0; i < d; i++) s += w[i] * f[i];
    return s;
  }

  /* 知彼：给定局面与对方的一步候选，返回「对方会走这一步」的对数几率。 */
  function replyScore(b, side, mv) {
    const m = MODEL && MODEL.battle && MODEL.battle.reply;
    if (!m) return 0;
    return dotW(m.w, battleFeats(b, side, mv));
  }

  /* 知己：我方局面「即将崩盘」的概率 ∈ [0,1]。 */
  function dangerOf(b, side, ply) {
    const m = MODEL && MODEL.battle && MODEL.battle.danger;
    if (!m) return 0;
    const s = dotW(m.w, dangerFeats(b, side, ply));
    return 1 / (1 + Math.exp(-s));
  }

  /* 神经价值头：1260 个棋子平面（10×9×14）+ 45 维几何特征 → cp。
     平面按 side-to-move 视角翻转，几何特征原样拼接，几何仍是显式输入。 */
  function boardPlanes(b, side) {
    const a = new Float32Array(1260);
    for (let y = 0; y < 10; y++) {
      for (let x = 0; x < 9; x++) {
        let p = b[y * 9 + x];
        if (!p) continue;
        let ny = y, nx = x;
        if (side < 0) { p = -p; ny = 9 - y; nx = 8 - x; }
        const ch = (Math.abs(p) - 1) + (p > 0 ? 0 : 7);
        a[ch * 90 + ny * 9 + nx] = 1;
      }
    }
    return a;
  }

  function mlpScore(b, side, feats, seg) {
    if (!b || !seg || !seg.layers) return null;
    const planes = boardPlanes(b, side);
    const inp = new Float32Array(1260 + feats.length);
    inp.set(planes, 0); inp.set(feats, 1260);
    if (seg.mlpMean && seg.mlpStd) {
      for (let i = 0; i < inp.length; i++) inp[i] = (inp[i] - seg.mlpMean[i]) / (seg.mlpStd[i] || 1);
    }
    let x = inp;
    for (let li = 0; li < seg.layers.length; li++) {
      const L = seg.layers[li], outN = L.b.length, inN = x.length;
      const y = new Float32Array(outN);
      for (let o = 0; o < outN; o++) {
        let s = L.b[o];
        for (let i = 0; i < inN; i++) s += L.w[i * outN + o] * x[i];
        y[o] = li === seg.layers.length - 1 ? s : (s > 0 ? s : 0);
      }
      x = y;
    }
    return Math.max(-2500, Math.min(2500, x[0] * (seg.out_scale || 1000)));
  }

  function hgbEval(H, feats) {
    let s = H.base;
    for (let t = 0; t < H.n; t++) {
      let i = H.off[t];
      while (!H.leaf[i]) i = feats[H.f[i]] <= H.th[i] ? H.left[i] : H.right[i];
      s += H.val[i];
    }
    return Math.max(-2500, Math.min(2500, s));
  }

  function movePlanes(mv) {
    const a = new Float32Array(180);
    const f = fOf(mv), t = tOf(mv);
    a[(f % 9) + Math.floor(f / 9) * 9] = 1;
    a[90 + (t % 9) + Math.floor(t / 9) * 9] = 1;
    return a;
  }

  function geomFeats45(b, side) {
    const g = geometry(b, side, 0, 0);
    const f = g.state.concat(shapeOf(g.a.state, g.a.tokens))
      .concat(shapeOf(g.b.state, g.b.tokens)).concat(shapeOf(g.c.state, g.c.tokens));
    for (const v of matFeats(b, side)) f.push(v);
    for (const v of threatFeats(b, side)) f.push(v);
    return f;
  }

  /* 策略头：局面平面 + 候选着法平面 + 45 维几何 → 该着法是皮卡鱼选择的概率。 */
  function policyScore(b, side, mv, pol) {
    if (!pol || !pol.layers) return 0;
    const base = boardPlanes(b, side);
    const mp = movePlanes(mv);
    const gf = geomFeats45(b, side);
    const inp = new Float32Array(1260 + 180 + gf.length);
    inp.set(base, 0); inp.set(mp, 1260); inp.set(gf, 1440);
    if (pol.mean && pol.std) {
      for (let i = 0; i < inp.length; i++) inp[i] = (inp[i] - pol.mean[i]) / (pol.std[i] || 1);
    }
    let x = inp;
    for (let li = 0; li < pol.layers.length; li++) {
      const L = pol.layers[li], outN = L.b.length, inN = x.length;
      const y = new Float32Array(outN);
      for (let o = 0; o < outN; o++) {
        let s = L.b[o];
        for (let i = 0; i < inN; i++) s += L.w[i * outN + o] * x[i];
        y[o] = li === pol.layers.length - 1 ? 1 / (1 + Math.exp(-s)) : (s > 0 ? s : 0);
      }
      x = y;
    }
    return x[0];
  }

  /* 深搜：用棋理基线做全宽 α-β，叶子和交换序列都走完。
     它不替代几何树，而是补上“两层束搜索看不见的战术纵深”。 */
  const DV = [0, 0, 200, 200, 450, 900, 450, 100];
  function deepQ(b, side, alpha, beta, ctx, ply, qd) {
    ctx.nodes++;
    const stand = ctx.ev(b, side);
    if (qd <= 0 || ctx.nodes >= ctx.cap) return stand;
    if (stand >= beta) return stand;
    if (stand > alpha) alpha = stand;
    const caps = forcingMoves(b, side, true);
    let best = stand;
    for (let i = 0; i < caps.length && i < 10; i++) {
      const mv = caps[i].mv, cap = b[tOf(mv)];
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const v = -deepQ(b, -side, -beta, -alpha, ctx, ply + 1, qd - 1);
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      if (v > best) best = v;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break;
    }
    return best;
  }

  function deepSearch(b, side, depth, alpha, beta, ctx, ply) {
    ctx.nodes++;
    const lm = legal(b, side);
    if (!lm.length) return -MATE + ply;
    if (ctx.nodes >= ctx.cap) return ctx.ev(b, side);
    const key = keyTT(b, side);
    const e = ctx.tt.get(key);
    if (e && e.depth >= depth) {
      if (e.flag === 0) return e.score;
      if (e.flag === 1) { if (e.score > alpha) alpha = e.score; }
      else { if (e.score < beta) beta = e.score; }
      if (alpha >= beta) return e.score;
    }
    if (depth <= 0) return deepQ(b, side, alpha, beta, ctx, ply, ctx.q);
    const ttMove = e && e.move;
    const killer = ctx.killer[ply] || 0;
    const ordered = lm.map((mv) => {
      const f = fOf(mv), t = tOf(mv), victim = b[t], attacker = b[f];
      let s = 0;
      if (mv === ttMove) s += 1e7;
      if (victim) s += 1e5 + DV[Math.abs(victim)] * 10 - DV[Math.abs(attacker)];
      if (mv === killer) s += 1e4;
      s += ctx.hist.get(mv) || 0;
      return { mv, s };
    }).sort((x, y) => y.s - x.s);
    let best = -Infinity, bestMove = 0, flag = 1;
    const oldAlpha = alpha;
    for (const { mv } of ordered) {
      const cap = b[tOf(mv)];
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const v = -deepSearch(b, -side, depth - 1, -beta, -alpha, ctx, ply + 1);
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      if (v > best) { best = v; bestMove = mv; }
      if (best > alpha) alpha = best;
      if (alpha >= beta) {
        if (!cap) {
          ctx.killer[ply] = mv;
          ctx.hist.set(mv, (ctx.hist.get(mv) || 0) + depth * depth);
        }
        flag = 0; break;
      }
    }
    if (best > oldAlpha) flag = 0; else if (best < oldAlpha) flag = 2; else flag = 1;
    ctx.tt.set(key, { depth, score: best, flag, move: bestMove });
    return best;
  }

  function deepRoot(b, side, opts) {
    const depth = opts.deepDepth || 6;
    const seg = MODEL && MODEL.tree && MODEL.tree.model;
    const ev = (opts.deepEval === 'nn' && seg) ? makeEval(seg, true, opts.classicW || 0) : classicScore;
    const ctx = { nodes: 0, cap: opts.deepCap || 300000, q: opts.deepQ === undefined ? 4 : opts.deepQ,
                  tt: new Map(), hist: new Map(), killer: new Array(40).fill(0), ev };
    const t0 = Date.now();
    const ordered = legal(b, side).map((mv) => {
      const victim = b[tOf(mv)], attacker = b[fOf(mv)];
      return { mv, s: victim ? DV[Math.abs(victim)] * 10 - DV[Math.abs(attacker)] : 0 };
    }).sort((x, y) => y.s - x.s);
    let best = -Infinity, bestMv = 0;
    const rows = [];
    let alpha = -Infinity;
    for (const { mv } of ordered) {
      const cap = b[tOf(mv)];
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const v = -deepSearch(b, -side, depth - 1, -Infinity, -alpha, ctx, 1);
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      rows.push({ mv, deep: v });
      if (v > best) { best = v; bestMv = mv; }
      if (v > alpha) alpha = v;
      if (ctx.nodes >= ctx.cap) break;
    }
    rows.sort((x, y) => y.deep - x.deep);
    return { mv: bestMv, score: best, rows, nodes: ctx.nodes, depth, ms: Date.now() - t0 };
  }

  /* ── 正式搜索评估：子力 + 位置 + 王安全 + 兵型。全部是廉价整数运算，
     供迭代加深的 α-β 使用；几何树/神经头仍在根节点候选排序里保留。 ── */
  const PV = { 1: 0, 2: 200, 3: 200, 4: 450, 5: 900, 6: 450, 7: 100 };
  function proEval(b, side) {
    let s = 0;
    let kr = -1, kb = -1;
    const pawnFilesR = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    const pawnFilesB = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    for (let i = 0; i < 90; i++) {
      const p = b[i]; if (!p) continue;
      const a = Math.abs(p), x = i % 9, y = (i / 9) | 0;
      const own = p > 0 ? 1 : -1;
      const sg = own * side;
      const ry = p > 0 ? y : 9 - y;
      const rx = p > 0 ? x : 8 - x;
      let v = PV[a];
      if (a === 7) {
        if (p > 0) pawnFilesR[x]++; else pawnFilesB[x]++;
        if (ry <= 4) v += 120;
        v += (6 - ry) * 8;
        v += (4 - Math.abs(rx - 4)) * 5;
      } else if (a === 5) {
        v += (4 - Math.abs(rx - 4)) * 10 + (4 - Math.abs(ry - 4)) * 6;
        if (rx === 0 || rx === 8) v -= 25;
      } else if (a === 6) {
        v += (4 - Math.abs(rx - 4)) * 9;
        if (ry >= 3 && ry <= 6) v += 12;
      } else if (a === 4) {
        v += (4 - Math.abs(rx - 4)) * 6;
        if (ry === 1 || ry === 8) v += 20;
      } else if (a === 2 || a === 3) {
        if (ry >= 7 && rx >= 2 && rx <= 6) v += 30;
      } else if (a === 1) {
        if (p > 0) kr = i; else kb = i;
        v -= Math.abs(rx - 4) * 12;
      }
      s += sg * v;
    }
    /* 兵型：叠兵/孤兵轻罚 */
    for (let x = 0; x < 9; x++) {
      if (pawnFilesR[x] > 1) s -= (pawnFilesR[x] - 1) * 20;
      if (pawnFilesB[x] > 1) s += (pawnFilesB[x] - 1) * 20;
    }
    /* 王安全：九宫内士象数量、敌重子距离 */
    const k = side > 0 ? kr : kb;
    if (k >= 0) {
      const kx = k % 9, ky = (k / 9) | 0;
      for (let i = 0; i < 90; i++) {
        const p = b[i]; if (!p || (p > 0) === (side > 0)) continue;
        const a = Math.abs(p);
        if (a === 4 || a === 5 || a === 6) {
          const x = i % 9, y = (i / 9) | 0;
          const d = Math.max(Math.abs(x - kx), Math.abs(y - ky));
          if (d <= 2) s -= (a === 4 ? 120 : 70) - d * 20;
        }
      }
    }
    return s;
  }

  function psQ(b, side, alpha, beta, ctx, ply) {
    ctx.nodes++;
    if ((ctx.nodes & 2047) === 0 && Date.now() > ctx.deadline) ctx.stop = true;
    if (ctx.stop) return 0;
    if (ply >= ctx.maxPly) return proEval(b, side);
    /* 被将军时禁止 stand-pat：否则会把「正在被将死」当成平静局面。
       只搜应将着，没有应将着就是被杀。 */
    if (inCheck(b, side)) {
      const lm = legal(b, side);
      if (!lm.length) return -MATE + ply;
      let best = -MATE;
      for (let i = 0; i < lm.length && i < 24; i++) {
        const mv = lm[i], f = fOf(mv), t = tOf(mv), cap = b[t];
        b[t] = b[f]; b[f] = 0;
        const v = -psQ(b, -side, -beta, -alpha, ctx, ply + 1);
        b[f] = b[t]; b[t] = cap;
        if (ctx.stop) return 0;
        if (v > best) best = v;
        if (v > alpha) alpha = v;
        if (alpha >= beta) return alpha;
      }
      return best;
    }
    const stand = proEval(b, side);
    if (stand >= beta) return stand;
    if (stand > alpha) alpha = stand;
    /* 静态搜索不再对每个吃子跑 SEE（那是热点里的热点），
       改用 MVV-LVA 排序 + delta 剪枝；是否亏子交给递归本身判断。 */
    const caps = [];
    for (const mv of legal(b, side)) {
      const f = fOf(mv), t = tOf(mv), victim = b[t];
      if (!victim) continue;
      caps.push({ mv, s: (SEE_V[Math.abs(victim)] || 100) * 16 - (SEE_V[Math.abs(b[f])] || 100) });
    }
    caps.sort((x, y) => y.s - x.s);
    for (let i = 0; i < caps.length && i < 16; i++) {
      const mv = caps[i].mv, f = fOf(mv), t = tOf(mv);
      const victim = b[t];
      if (stand + (SEE_V[Math.abs(victim)] || 0) + 180 < alpha) continue;
      const cap = b[t];
      b[t] = b[f]; b[f] = 0;
      const v = -psQ(b, -side, -beta, -alpha, ctx, ply + 1);
      b[f] = b[t]; b[t] = cap;
      if (ctx.stop) return 0;
      if (v >= beta) return v;
      if (v > alpha) alpha = v;
    }
    return alpha;
  }

  function psSearch(b, side, depth, alpha, beta, ctx, ply) {
    ctx.nodes++;
    if ((ctx.nodes & 1023) === 0 && Date.now() > ctx.deadline) ctx.stop = true;
    if (ctx.stop) return 0;
    if (ply >= ctx.maxPly) return proEval(b, side);
    /* 叶子节点先走静态搜索：它内部只在被将军时才生成合法着，
       避免「先生成全量合法着、再进 psQ 又生成一遍」的双倍开销。 */
    if (depth <= 0) return psQ(b, side, alpha, beta, ctx, ply);
    const lm = legal(b, side);
    if (!lm.length) return -MATE + ply;

    const key = keyTT(b, side);
    const e = ctx.tt.get(key);
    let ttMove = 0;
    if (e) {
      ttMove = e.move || 0;
      /* 将杀分与 ply 相关，跨层复用会被误读成「别的深度上的杀」，
         直接不采信带将杀分的表项。 */
      if (e.depth >= depth && Math.abs(e.score) < MATE - 100) {
        if (e.flag === 0) return e.score;
        if (e.flag === 1 && e.score > alpha) alpha = e.score;
        if (e.flag === 2 && e.score < beta) beta = e.score;
        if (alpha >= beta) return e.score;
      }
    }

    const inChk = inCheck(b, side);
    /* 空着裁剪：非将军、有足够子力时，把对手「不动」交给自己搜一层 */
    if (depth >= 3 && !inChk && Math.abs(proEval(b, side)) < 1200 && ply > 0) {
      const R = depth >= 6 ? 3 : 2;
      const v = -psSearch(b, -side, depth - 1 - R, -beta, -beta + 1, ctx, ply + 1);
      if (ctx.stop) return 0;
      if (v >= beta) return v;
    }

    const killer1 = ctx.killer[ply] || 0, killer2 = ctx.killer2[ply] || 0;
    /* 浅层 futility：静态分已经远低于 alpha，安静着不可能翻盘，直接返回 */
    if (depth <= 2 && !inChk && ply > 0) {
      const se = proEval(b, side);
      if (se + 220 * depth <= alpha) return se;
    }
    const ordered = lm.map((mv) => {
      const f = fOf(mv), t = tOf(mv), victim = b[t], attacker = b[f];
      let sc = 0;
      if (mv === ttMove) sc += 1e9;
      if (victim) sc += 1e6 + (PV[Math.abs(victim)] || 0) * 20 - (PV[Math.abs(attacker)] || 0);
      else if (mv === killer1) sc += 5e4;
      else if (mv === killer2) sc += 3e4;
      sc += ctx.hist.get(mv) || 0;
      return { mv, sc };
    }).sort((x, y) => y.sc - x.sc);

    const oldAlpha = alpha;
    let best = -MATE, bestMove = 0;
    let moveCount = 0;
    for (const { mv } of ordered) {
      const cap = b[tOf(mv)];
      /* 浅层迟到着剪枝：排序已经靠后的安静着，在低深度不再展开 */
      if (!cap && depth <= 3 && moveCount >= (depth <= 2 ? 8 : 14)) { moveCount++; continue; }
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const gives = inCheck(b, -side);
      const ext = gives ? 1 : 0;
      let v;
      if (moveCount === 0) {
        v = -psSearch(b, -side, depth - 1 + ext, -beta, -alpha, ctx, ply + 1);
      } else {
        /* LMR：靠后的安静着先浅搜，不剪就重搜 */
        let red = 0;
        if (depth >= 4 && moveCount >= 4 && !cap && !gives) red = 1 + (moveCount >= 12 ? 1 : 0);
        v = -psSearch(b, -side, depth - 1 - red + ext, -alpha - 1, -alpha, ctx, ply + 1);
        if (!ctx.stop && v > alpha && red) {
          v = -psSearch(b, -side, depth - 1 + ext, -beta, -alpha, ctx, ply + 1);
        }
      }
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      if (ctx.stop) return 0;
      if (v > best) { best = v; bestMove = mv; }
      if (v > alpha) alpha = v;
      if (alpha >= beta) {
        if (!cap) {
          ctx.killer2[ply] = ctx.killer[ply] || 0;
          ctx.killer[ply] = mv;
          ctx.hist.set(mv, (ctx.hist.get(mv) || 0) + depth * depth);
        }
        break;
      }
      moveCount++;
    }
    const flag = best > oldAlpha ? 0 : (best < oldAlpha ? 2 : 1);
    if (Math.abs(best) < MATE - 100) ctx.tt.set(key, { depth, score: best, flag, move: bestMove });
    return best;
  }

  function psRoot(b, side, opts) {
    const maxDepth = opts.deepDepth || 10;
    const deadline = Date.now() + (opts.deepMs || 3000);
    const ctx = { nodes: 0, cap: opts.deepCap || 4e6, maxPly: 64, tt: new Map(),
                  hist: new Map(), killer: [], killer2: [], stop: false, deadline };
    const ordered = legal(b, side).map((mv) => {
      const victim = b[tOf(mv)], attacker = b[fOf(mv)];
      return { mv, s: victim ? (PV[Math.abs(victim)] || 0) * 20 - (PV[Math.abs(attacker)] || 0) : 0 };
    }).sort((x, y) => y.s - x.s);
    if (!ordered.length) return null;
    let rows = ordered.map((o) => ({ mv: o.mv, score: -Infinity }));
    let bestMv = ordered[0].mv, bestScore = 0, doneDepth = 0;
    for (let d = 1; d <= maxDepth; d++) {
      let alpha = -MATE;
      const cur = [];
      let first = true;
      for (const r of rows) {
        const mv = r.mv, cap = b[tOf(mv)];
        b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
        const ext = inCheck(b, -side) ? 1 : 0;
        let v;
        if (first) {
          v = -psSearch(b, -side, d - 1 + ext, -MATE, MATE, ctx, 1);
          first = false;
        } else {
          /* 根节点 PVS：先零窗口试，超过 alpha 必须全窗口重搜，
             否则会把下界当成真实分，选出错误的着法。 */
          v = -psSearch(b, -side, d - 1 + ext, -alpha - 1, -alpha, ctx, 1);
          if (!ctx.stop && v > alpha) {
            v = -psSearch(b, -side, d - 1 + ext, -MATE, -alpha, ctx, 1);
          }
        }
        b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
        if (ctx.stop) break;
        cur.push({ mv, score: v });
        if (v > alpha) alpha = v;
      }
      if (ctx.stop) break;
      cur.sort((x, y) => y.score - x.score);
      rows = cur;
      bestMv = rows[0].mv; bestScore = rows[0].score; doneDepth = d;
      if (Math.abs(bestScore) > MATE - 100) break;
    }
    return { mv: bestMv, score: bestScore, rows, nodes: ctx.nodes, depth: doneDepth, ms: Date.now() - (deadline - (opts.deepMs || 3000)) };
  }

  function treeScore(g, seg, b, side) {
    if (!seg || !g.a || !g.b || !g.c || (!seg.centers && !seg.hgb && !seg.layers)) return null;
    const feats = g.state.concat(shapeOf(g.a.state, g.a.tokens))
      .concat(shapeOf(g.b.state, g.b.tokens)).concat(shapeOf(g.c.state, g.c.tokens));
    if (b !== undefined && side !== undefined) {
      for (const v of matFeats(b, side)) feats.push(v);
      if (seg.mean.length === 45 || seg.mean.length === 47) for (const v of threatFeats(b, side)) feats.push(v);
      if (seg.mean.length === 47) for (const v of tensionFeats(b, side)) feats.push(v);
    }
    if (feats.length !== seg.mean.length) return null;
    if (seg.kind === 'mlp' && seg.layers) return mlpScore(b, side, feats, seg);
    if (seg.kind === 'blend' && seg.layers && seg.hgb) {
      const nn = mlpScore(b, side, feats, seg);
      const hg = hgbEval(seg.hgb, feats);
      if (nn === null) return hg;
      const mix = seg.mix === undefined ? 0.7 : seg.mix;
      return mix * nn + (1 - mix) * hg;
    }
    if (seg.kind === 'hgb' && seg.hgb) {
      return hgbEval(seg.hgb, feats);
    }
    const P = prepSeg(seg);
    const d = P.d, K = P.K;
    const z = new Float32Array(d);
    let zn = 0;
    for (let i = 0; i < d; i++) { const t = (feats[i] - P.mean[i]) / P.std[i]; z[i] = t; zn += t * t; }
    const wts = new Float32Array(K);
    let sw = 0, wmax = 0;
    for (let k = 0; k < K; k++) {
      const off = k * d;
      let dot = 0;
      for (let i = 0; i < d; i++) dot += z[i] * P.c[off + i];
      let d2 = zn - 2 * dot + P.cn[k];
      if (d2 < 0) d2 = 0;                       // 浮点抵消可能产生极小负值
      const wk = Math.exp(-d2 * P.invH2);
      wts[k] = wk; sw += wk; if (wk > wmax) wmax = wk;
    }
    if (sw <= 0) sw = 1;
    let tree = 0, glob = P.globB;
    const cutoff = wmax * 1e-4;                 // 贡献 <1e-4 峰值的分支跳过点积
    for (let k = 0; k < K; k++) {
      const wk = wts[k];
      if (wk < cutoff) continue;
      const off = k * d;
      let s = P.lb[k];
      for (let i = 0; i < d; i++) s += P.lw[off + i] * z[i];
      tree += wk * s;
    }
    tree /= sw;
    for (let i = 0; i < d; i++) glob += P.gw[i] * z[i];
    let val = seg.lam * tree + (1 - seg.lam) * glob;
    // 黑洞：速败局面的点云坐标是强排斥源，特征越接近，扣分越多
    // 神经辅助头：3 类 softmax（负/和/正），与树估值按比例融合
    if (seg.mlp && seg.mlp.kind === 'clf' && (seg.mlp.blend || 0) > 0) {
      let a = z;
      for (let l = 0; l < seg.mlp.W.length; l++) {
        const W = seg.mlp.W[l], b = seg.mlp.b[l], out = new Array(b.length);
        for (let j = 0; j < b.length; j++) {
          let s = b[j];
          const wj = W[j];
          for (let i = 0; i < a.length; i++) s += wj[i] * a[i];
          out[j] = s > 0 ? s : 0;
        }
        a = out;
      }
      const mx = Math.max.apply(null, a);
      const ex = a.map((v) => Math.exp(v - mx));
      const sum = ex.reduce((x, y) => x + y, 0);
      const neural = 600 * (ex[2] / sum - ex[0] / sum);
      const bl = seg.mlp.blend === undefined ? 0.6 : seg.mlp.blend;
      val = bl * neural + (1 - bl) * val;
    }
    // 棋子平面神经头（14×10×9 直接输入），几何树保持主导
    if (seg.neural2 && seg.neural2.kind === 'plane-clf' && (seg.neural2.blend || 0) > 0) {
      const net = seg.neural2;
      const x = new Float32Array(1260);
      const flip = side < 0;
      for (let s = 0; s < 90; s++) {
        const q = b[s];
        if (!q) continue;
        const px = s % 9, py = flip ? 9 - ((s / 9) | 0) : ((s / 9) | 0);
        const c = (Math.abs(q) - 1) + (q > 0 ? 0 : 7);
        x[c * 90 + py * 9 + px] = 1;
      }
      let a = x;
      for (let l = 0; l < net.W.length; l++) {
        const W = net.W[l], b2 = net.b[l], out = new Array(b2.length);
        for (let j = 0; j < b2.length; j++) {
          let acc = b2[j];
          const wj = W[j];
          for (let i = 0; i < wj.length; i++) if (a[i]) acc += wj[i];
          out[j] = l < net.W.length - 1 ? (acc > 0 ? acc : 0) : acc;
        }
        a = out;
      }
      const mx = Math.max.apply(null, a);
      const ex = a.map((v) => Math.exp(v - mx));
      const sum = ex.reduce((x2, y2) => x2 + y2, 0);
      const neural = 600 * (ex[2] / sum - ex[0] / sum);
      const bn = net.blend === undefined ? 0.3 : net.blend;
      val = (1 - bn) * val + bn * neural;
    }
    // 闭合层：不受学习衰减的硬约束（子力/安全/活动性），权重在推理期直接相加
    const cw = seg.closure || CLOSURE_W;
    if (b !== undefined && side !== undefined) {
      let any = false;
      for (let i = 0; i < cw.length; i++) if (cw[i]) { any = true; break; }
      if (any) {
        const cl = closureOf(b, side);
        for (let i = 0; i < cw.length; i++) if (cw[i]) val += cw[i] * cl[i];
      }
    }
    const bl = seg.blacklist || [];
    for (const tr of bl) {
      let d2 = 0;
      for (let i = 0; i < tr.x.length; i++) d2 += (z[i] - tr.x[i]) ** 2;
      const d = Math.sqrt(d2);
      if (d < tr.r) val -= tr.k * (1 - d / tr.r) ** 2;
    }
    if (seg.traps && seg.traps.length) {
      let pen = 0;
      for (const tr of seg.traps) {
        let d2 = 0;
        for (let i = 0; i < tr.x.length; i++) d2 += (z[i] - tr.x[i]) ** 2;
        const d = Math.sqrt(d2);
        if (d < tr.r) {
          const p = tr.k * (1 - d / tr.r) ** 2;
          if (p > pen) pen = p;
        }
      }
      val -= pen;
    }
    return val;
  }

  const MATE = 90000;

  /* 强制手：只挑「交换不亏的吃子」和「叫将」。这两类才可能引出连杀，
     沉底炮、马挂角、双马饮泉都是从连续叫将开始的，静态两层看不出来。 */
  function forcingMoves(b, side, capsOnly) {
    const out = [];
    for (const mv of legal(b, side)) {
      const f = fOf(mv), t = tOf(mv), victim = b[t];
      let r = 0;
      if (victim) {
        const sv = seeCapture(b, f, t);
        if (sv >= 0) r = 300 + (SEE_V[Math.abs(victim)] || 100) + sv * 0.1;
      }
      if (!r && !capsOnly) {
        const cap = b[t];
        b[t] = b[f]; b[f] = 0;
        const chk = inCheck(b, -side);
        b[f] = b[t]; b[t] = cap;
        if (chk) r = 200;
      }
      if (r > 0) out.push({ mv, r });
    }
    out.sort((x, y) => y.r - x.r);
    return out;
  }

  /* 叶子静态搜索：深度耗尽时若还处在交换序列中途，直接估分会把“半个交换”当成终局。
     这里只补吃子（stand-pat + 不亏的吃子），把交换走完再交给几何树。
     估值来源依旧是几何树，没有引入任何外部评分。 */
  function leafScore(b, side, seg, evals, qd, alpha, beta) {
    evals.n++;
    const v = evals.ev ? evals.ev(b, side) : treeScore(geometry(b, side, 0, 0), seg, b, side);
    if (qd <= 0 || evals.n >= evals.cap) return v;
    if (v >= beta) return v;
    const caps = forcingMoves(b, side, true);
    if (!caps.length) return v;
    let best = v, a = v > alpha ? v : alpha;
    const n = caps.length < 6 ? caps.length : 6;
    for (let i = 0; i < n; i++) {
      const mv = caps[i].mv, cap = b[tOf(mv)];
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const w = -leafScore(b, -side, seg, evals, qd - 1, -beta, -a);
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      if (w > best) best = w;
      if (best > a) a = best;
      if (a >= beta) break;
    }
    return best;
  }

  /* 只走强制手的 negamax。叶子仍然交给几何树打分，几何依旧是唯一的估值。
     ply 用来给杀棋分级（越早杀分越高），evals 是节点预算。 */
  /* 单点估值入口。sym=true 时做「对称化」：同一局面分别从双方视角各估一次，
     取半差 (v(我方) − v(对方)) / 2。训练样本只覆盖「我方走子」的视角，
     模型因此带有方向性偏差；两次估计的偏差方向相反，取半差可以把这部分噪声抵消掉。 */
  /* 棋理基线：子力+PST+王前威胁。只作为几何树的低权重修正项（<0.5），
     不改变“几何主导”的架构；用于检验几何估值在安静局面是否漏掉了常识。 */
  function classicScore(b, side) {
    const VAL = [0, 0, 200, 200, 450, 900, 450, 100];
    let s = 0, kingR = -1, kingB = -1;
    for (let i = 0; i < 90; i++) {
      const p = b[i]; if (!p) continue;
      const t = p > 0 ? 1 : -1, a = Math.abs(p), y = Math.floor(i / 9), x = i % 9;
      const own = t === side ? 1 : -1;
      s += own * VAL[a];
      if (a === 1) { if (t > 0) kingR = i; else kingB = i; }
      if (a === 4) s += own * (18 - 2 * Math.abs(x - 4));
      if (a === 6) s += own * (10 - Math.abs(x - 4));
      if (a === 5 && own > 0) {
        let open = true;
        for (let yy = 0; yy < 10; yy++) if (Math.abs(b[yy * 9 + x]) === 7) { open = false; break; }
        if (open) s += 70;
      }
      if (a === 7 && own > 0) s += t > 0 ? Math.max(0, 4 - y) * 18 : Math.max(0, y - 5) * 18;
    }
    // 王前重子威胁：敌车/炮/马距将 2 格内
    const k = side > 0 ? kingR : kingB;
    if (k >= 0) {
      const kx = k % 9, ky = Math.floor(k / 9);
      for (let i = 0; i < 90; i++) {
        const p = b[i]; if (!p || (p > 0) === (side > 0)) continue;
        const a = Math.abs(p), y = Math.floor(i / 9), x = i % 9;
        if (a === 5 || a === 6 || a === 4) {
          const d = Math.max(Math.abs(x - kx), Math.abs(y - ky));
          if (d <= 2) s -= 90 - d * 20;
        }
      }
    }
    return s;
  }

  function makeEval(seg, sym, classicW) {
    return function (b, side) {
      let v1 = treeScore(geometry(b, side, 0, 0), seg, b, side);
      if (classicW) v1 = (1 - classicW) * v1 + classicW * classicScore(b, side);
      if (!sym) return v1;
      let v2 = treeScore(geometry(b, -side, 0, 0), seg, b, -side);
      if (classicW) v2 = (1 - classicW) * v2 + classicW * classicScore(b, -side);
      return 0.5 * (v1 - v2);
    };
  }

  function forceSearch(b, side, seg, depth, ply, alpha, beta, evals) {
    if (!legal(b, side).length) return -MATE + ply;
    if (depth <= 0 || evals.n >= evals.cap) {
      return leafScore(b, side, seg, evals, evals.q || 0, alpha, beta);
    }
    const fm = forcingMoves(b, side);
    if (!fm.length) {
      return leafScore(b, side, seg, evals, evals.q || 0, alpha, beta);
    }
    let best = -Infinity;
    for (const { mv } of fm) {
      const cap = b[tOf(mv)];
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const v = -forceSearch(b, -side, seg, depth - 1, ply + 1, -beta, -alpha, evals);
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      if (v > best) best = v;
      if (v > alpha) alpha = v;
      if (alpha >= beta) break;
    }
    return best;
  }

  /* 全宽浅层校验：对前几名候选，走完后让对手走「全部合法着」，再轮到我方走一层，
     用同一棵几何树结算。它补的是 forceSearch 看不到的 quiet move（不将军、不吃子
     的阵型压缩），而不是再把强制手加深。 */
  function fullSearch(b, side, depth, alpha, beta, evals) {
    const lm = legal(b, side);
    if (!lm.length) return -MATE;
    if (depth <= 0 || evals.n >= evals.cap) {
      return leafScore(b, side, evals.seg, evals, evals.q || 0, alpha, beta);
    }
    evals.n++;
    // 吃子优先，将军次之；顺序只影响剪枝效率，不改变全宽范围
    const ordered = lm.map((mv) => {
      const victim = b[tOf(mv)];
      let r = victim ? (SEE_V[Math.abs(victim)] || 0) : 0;
      const f = fOf(mv), t = tOf(mv), cap = b[t];
      b[t] = b[f]; b[f] = 0;
      if (inCheck(b, -side)) r += 40;
      b[f] = b[t]; b[t] = cap;
      return { mv, r };
    }).sort((x, y) => y.r - x.r);
    let best = -Infinity;
    for (const { mv } of ordered) {
      const cap = b[tOf(mv)];
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      const v = -fullSearch(b, -side, depth - 1, -beta, -alpha, evals);
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
      if (v > best) best = v;
      if (v > alpha) alpha = v;
      if (alpha >= beta) break;
    }
    return best;
  }

  function cloudScore(g, seg, b, side) {
    if (!seg || !g.a || !g.b || !g.c) return null;
    const feats = g.state.concat(shapeOf(g.a.state, g.a.tokens))
      .concat(shapeOf(g.b.state, g.b.tokens)).concat(shapeOf(g.c.state, g.c.tokens));
    if (b !== undefined && side !== undefined) {
      for (const v of matFeats(b, side)) feats.push(v);
    }
    if (feats.length !== seg.mean.length) return null;
    let s = seg.b;
    for (let i = 0; i < feats.length; i++) s += seg.w[i] * (feats[i] - seg.mean[i]) / (seg.std[i] || 1);
    return s;
  }

  function winProbSpace(state, pts, seg) {
    if (!seg) return null;
    const feats = state.concat(shapeOf(state, pts));
    const z = feats.map((v, i) => (v - seg.mean[i]) / (seg.std[i] || 1));
    const lg = seg.W.map((row, k) => {
      let s = seg.b[k];
      for (let i = 0; i < row.length; i++) s += row[i] * z[i];
      return s;
    });
    const mx = Math.max.apply(null, lg);
    const ex = lg.map((v) => Math.exp(v - mx));
    const sum = ex.reduce((a, v) => a + v, 0);
    const p = ex.map((v) => v / sum);           // 顺序 [-1, 0, 1]
    return { pLoss: p[0], pDraw: p[1], pWin: p[2], score: p[2] + 0.5 * p[1] };
  }

  /* 双路线决策：局部最优 vs 全局最优，各用自己的胜率模型，谁高走谁。 */
  /* 动态分支树：静态几何只给方向，这里在方向内展开候选着的分支，
     逐支用激活树打分并以对手最狠回应的最坏值为上界，取“符合度”最高的一步。
     宽束固定、逐层展开，不是 α-β 剪枝。 */
  function branchSearch(b, side, opts) {
    opts = opts || {};
    const seg = MODEL && MODEL.tree && MODEL.tree.model;
    if (!seg) return null;
    const width = opts.width || 5;
    const repWidth = opts.repWidth || 1;
    const pro = opts.pro !== false;
    const phase = situationLabel(b, side);
    const rep = new Set(opts.history || []);
    /* 对称化估值：同一局面从双方视角各估一次再取半差。模型本身带方向性偏差
       （某方视角系统偏高），半差把公共偏置抵消掉，同一着法的比较更稳。
       实测固定局面集上 CPL 93.9→89.9、失着率 14.5%→13.7%、首选命中 13.7%→16.2%。 */
    const ev = makeEval(seg, opts.sym === undefined ? seg.sym !== false : !!opts.sym, opts.classicW || 0);
    let cands = [];
    for (const fn of [gravityLocal, gravityGlobal]) {
      const pick = pickWith(b, side, fn, phase, 0, rep);
      if (!pick) continue;
      for (const c of pick.top.slice(0, width)) {
        if (!cands.includes(c.mv)) cands.push(c.mv);
      }
    }
    /* 历史启发轨道：库内同形局面的高频着法直接进候选池。
       它不参与估值，只负责“别漏掉人类实战验证过的走法”。 */
    if (pro && opts.historyTrack) {
      const legalNow = new Set(legal(b, side));
      for (const mv of bookTopMoves(b, side, opts.historyTop || 2)) {
        if (legalNow.has(mv) && !cands.includes(mv)) cands.push(mv);
      }
    }
    /* 引力势只看“势”，看不见“白吃的子”和“叫将”。把交换不亏的吃子与将军直接塞进候选集，
       否则一步白吃车可能因为势不涨而根本没进过候选。 */
    let rootTac = 0;
    if (pro && opts.rootTactics !== false) {
      const extra = [];
      for (const mv of legal(b, side)) {
        if (cands.includes(mv)) continue;
        const victim = b[tOf(mv)];
        let r = 0;
        if (victim) {
          const sv = seeCapture(b, fOf(mv), tOf(mv));
          if (sv > 0) r = 300 + (SEE_V[Math.abs(victim)] || 100) + sv * 0.1;
        }
        if (!r) {
          const f = fOf(mv), t = tOf(mv), cap = b[t];
          b[t] = b[f]; b[f] = 0;
          const chk = inCheck(b, -side);
          b[f] = b[t]; b[t] = cap;
          if (chk) r = 200;
        }
        if (r > 0) extra.push({ mv, r });
      }
      extra.sort((x, y) => y.r - x.r);
      const cap = opts.rootCap || 4;
      for (const x of extra.slice(0, cap)) { cands.push(x.mv); rootTac++; }
    }
    if (!cands.length) return null;
    /* ── 全宽一层筛选 ──────────────────────────────────────────────
       引力势只覆盖约三分之一的合法着，实测参考引擎的最优着有 53% 根本不在候选集里，
       且被漏掉的几乎全是安静着法（占位/防守/腾挪）——引力先验只会提“让势变大”的着。
       这里换个次序：先用同一棵几何树给「每一个合法着」做一次单层估值，
       取前 N 名才进入两层的对手回应与强制手搜索。
       估值来源没变，变的只是“哪些着法有资格被认真算”。                      */
    const pre = new Map();
    if (opts.rootAll) {
      for (const mv of legal(b, side)) {
        const f = fOf(mv), t = tOf(mv), cap = b[t];
        if (cap && seeCapture(b, f, t) < 0) continue;
        b[t] = b[f]; b[f] = 0;
        if (legal(b, -side).length === 0) {
          b[f] = b[t]; b[t] = cap;
          return { mv, value: 99999, rows: [{ mv, value: 99999, mate: true }],
                   nodes: 1, width, repWidth, depth: 1, forceNodes: 0 };
        }
        const cp = -ev(b, -side);
        b[f] = b[t]; b[t] = cap;
        pre.set(mv, cp);
      }
      const scored = Array.from(pre.entries()).sort((x, y) => y[1] - x[1]);
      const keep = opts.rootKeep || 12;
      const keepSet = new Set();
      for (let i = 0; i < scored.length && i < keep; i++) keepSet.add(scored[i][0]);
      // 战术手（将军/赚子）无论一层分高低都保留，避免安静估值把它们筛掉
      for (const mv of cands) if (!keepSet.has(mv) && pre.has(mv) && keepSet.size < keep + 4) keepSet.add(mv);
      cands = Array.from(keepSet);
    }
    // 战术叶子：吃子先做静态交换估值，亏本的吃子直接剔除
    const checked = inCheck(b, side);
    const threat0 = threatScore(b, side);
    const cut0 = interceptCount(b, side);
    const seeBad = (mv) => {
      const victim = b[tOf(mv)];
      if (!victim) return false;
      return seeCapture(b, fOf(mv), tOf(mv)) < 0;
    };
    // 挂子过滤：落子后若己方大子（>=300）被攻击且无人保护，直接淘汰该候选
    const hangBad = (mv) => { return false;
      const f = fOf(mv), t = tOf(mv), cap = b[t];
      b[t] = b[f]; b[f] = 0;
      let bad = false;
      for (let s = 0; s < 90 && !bad; s++) {
        const q = b[s];
        if (!q || sside(q) !== side) continue;
        const v = Math.abs(q);
        if (v === KING || VALUE[v] < 300) continue;
        if (attacked(b, s, -side) && !attacked(b, s, side)) bad = true;
      }
      b[f] = b[t]; b[t] = cap;
      return bad;
    };
    const cands0 = cands.slice();
    if (opts.tactics !== false) {
      const legalNow = new Set(legal(b, side));
      cands = cands.filter((mv) => legalNow.has(mv) && !seeBad(mv) && !hangBad(mv));
    }
    if (!cands.length) {
      // 全部候选都“挂子”时退回常规过滤，而不是随便挑几步合法着
      const legalNow = new Set(legal(b, side));
      cands = cands0.filter((mv) => legalNow.has(mv) && !seeBad(mv));
      if (!cands.length) cands = cands0.filter((mv) => legalNow.has(mv));
    }
    if (!cands.length) return null;
    const replyCap = opts.replyCap || 5;
    /* 对手的回应不再只用我们的引力势猜：先列全部合法着里的「吃子（交换不亏）」与「将军」，
       再补引力势前二。引力势看不出对方一步杀，tactical 列表看得出来。 */
    function replyList(sd, hist) {
      const g = [];
      for (const fn of [gravityLocal, gravityGlobal]) {
        const pk = pickWith(b, sd, fn, situationLabel(b, sd), 0, hist);
        if (pk) for (const c of pk.top.slice(0, 2)) if (!g.includes(c.mv)) g.push(c.mv);
      }
      if (!pro) return g.slice(0, replyCap);
      const out = [];
      const seen = new Set();
      const rank = [];
      for (const mv of legal(b, sd)) {
        const victim = b[tOf(mv)];
        let r = 0;
        if (victim) {
          const sv = seeCapture(b, fOf(mv), tOf(mv));
          if (sv > 0) r = 400 + (SEE_V[Math.abs(victim)] || 100) + sv * 0.1;
        }
        if (!r) {
          const f = fOf(mv), t = tOf(mv), cap = b[t];
          b[t] = b[f]; b[f] = 0;
          const chk = inCheck(b, -sd);
          b[f] = b[t]; b[t] = cap;
          if (chk) r = 260 + (victim ? 40 : 0);
        }
        if (r > 0 && !seen.has(mv)) { seen.add(mv); rank.push({ mv, r }); }
      }
      rank.sort((x, y) => y.r - x.r);
      for (const x of rank) out.push(x.mv);
      for (const mv of g) if (!seen.has(mv)) { seen.add(mv); out.push(mv); }

      /* 知彼：用实战学出的对手模型重排回应集。
         实测（1072 个真实局面）：同样 5 个候选，启发式只罩住 43.5% 的皮卡鱼真实回应，
         学习模型罩住 62.9%。搜索里 min 是对"假想对手"取的，罩不住就等于估错最坏情形。
         这里仍保留启发式里最靠前的两个强制手（吃子/叫将），避免纯概率排序漏掉战术回应。 */
      if (opts.replyModel && MODEL && MODEL.battle && MODEL.battle.reply) {
        const all = legal(b, sd);
        const sc = [];
        for (const mv of all) sc.push({ mv, s: replyScore(b, sd, mv) });
        sc.sort((x, y) => y.s - x.s);
        const K = opts.replyK || replyCap;
        const out2 = [];
        for (const x of sc.slice(0, K)) out2.push(x.mv);
        for (const x of rank.slice(0, 2)) if (!out2.includes(x.mv)) out2.push(x.mv);
        return out2.slice(0, K + 2);
      }
      return out.slice(0, replyCap);
    }
    let nodes = 0;
    const rows = [];
    for (const mv of cands) {
      const cap = b[tOf(mv)];
      const seeGain = cap ? seeCapture(b, fOf(mv), tOf(mv)) : 0;
      b[tOf(mv)] = b[fOf(mv)]; b[fOf(mv)] = 0;
      // 一步将死直接给满分，避免“看起来赚”的送死棋压过杀棋
      if (opts.tactics !== false && legal(b, -side).length === 0) {
        rows.push({ mv, value: 99999, immediate: 99999, replyFloor: 99999, replies: 0, mate: true });
        b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
        nodes++;
        continue;
      }
      const valImmediate = pre.has(mv) ? pre.get(mv) : -ev(b, -side);
      nodes++;
      // 自身安全：这一子落下去会不会被白吃
      let pen = 0;
      if (pro) {
        pen += exposedValue(b, tOf(mv), side) * 0.7;
        if (seeGain < 0) pen += -seeGain;
      }
      let worst = Infinity, sum = 0, cnt = 0;
      const replies = replyList(-side, rep);
      const rw = checked ? Math.max(2, repWidth) : repWidth;
      const repTrim = pro ? replies : replies.slice(0, rw);
      /* 知彼·期望值：min 假设对手永远走最狠那一步，实际对手有偏好。
         用学习到的回应概率做加权平均，等于「按对手真实倾向估分」。
         权重必须在落子前算（replyScore 依赖当前局面）。 */
      let rwts = null;
      if (opts.agg === 'ev' && MODEL && MODEL.battle && MODEL.battle.reply && repTrim.length) {
        const raw = repTrim.map((rm) => replyScore(b, -side, rm));
        const mx = Math.max(...raw);
        let Z = 0;
        const ex = raw.map((v) => Math.exp(v - mx));
        for (const v of ex) Z += v;
        rwts = ex.map((v) => v / (Z || 1));
      }
      let evv = 0;
      for (let ri = 0; ri < repTrim.length; ri++) {
        const rm = repTrim[ri];
        const rc = b[tOf(rm)];
        b[tOf(rm)] = b[fOf(rm)]; b[fOf(rm)] = 0;
        const cpUs = ev(b, side);
        nodes++;
        if (cpUs < worst) worst = cpUs;
        sum += cpUs; cnt++;
        if (rwts) evv += rwts[ri] * cpUs;
        b[fOf(rm)] = b[tOf(rm)]; b[tOf(rm)] = rc;
      }
      if (!cnt) { worst = valImmediate; sum = valImmediate; cnt = 1; }
      /* 对 K 个回应取 min 等于在噪声上下界里挑最差的那个：估值的 MAE 有 170，
         min 会被系统性拉低，且放大“哪个候选恰好有个难看回应”的随机性。
         与均值混合既保留“按最狠回应”的本意，又不让噪声主导排序。 */
      const mean = sum / cnt;
      const agg = opts.agg || (pro ? 'mix' : 'min');
      const floor = agg === 'mean' ? mean
        : agg === 'min' ? worst
        : agg === 'ev' ? 0.5 * worst + 0.5 * evv
        : 0.6 * worst + 0.4 * mean;
      const mix = opts.mix === undefined ? 0.45 : opts.mix;
      const threat1 = threatScore(b, side);
      const cut1 = interceptCount(b, side);
      const defOn = !(MODEL && MODEL.tree && MODEL.tree.defense === false);
      const defBonus = !defOn ? 0 : (threat0 - threat1) * 70 + (cut1 - cut0) * 110;
      const value = mix * valImmediate + (1 - mix) * floor + defBonus - pen;
      rows.push({ mv, value, immediate: valImmediate, replyFloor: floor, replies: repTrim.length });
      b[fOf(mv)] = b[tOf(mv)]; b[tOf(mv)] = cap;
    }
    /* 策略头只重排候选，不替换估值：皮卡鱼选过的形状加分，没选过的减分。 */
    if (pro && opts.policyW && seg.policy) {
      for (const r of rows) {
        r.policy = policyScore(b, side, r.mv, seg.policy);
        r.value += opts.policyW * (r.policy - 0.5);
      }
    }
    rows.sort((x, y) => y.value - x.value);
    /* 强制手校验：对前几名再往后推 2~3 层「吃子/叫将」，把连杀与交换看清楚。
       估值仍然是同一棵几何树，只是看得更远。 */
    let forceNodes = 0;
    const forceDepth = opts.force === undefined ? 3 : opts.force;
    if (pro && forceDepth > 0) {
      const topN = Math.min(opts.forceTop || 8, rows.length);
      const head = rows.slice(0, topN);
      const forceEv = (opts.forceHgb && seg.hgb)
        ? ((bb, ss) => treeScore(geometry(bb, ss, 0, 0), { kind: 'hgb', hgb: seg.hgb, mean: seg.mean, std: seg.std }, bb, ss))
        : ev;
      const evals = { n: 0, cap: opts.forceCap || 400, q: opts.q === undefined ? 2 : opts.q, ev: forceEv };
      for (const r of head) {
        const cap = b[tOf(r.mv)];
        b[tOf(r.mv)] = b[fOf(r.mv)]; b[fOf(r.mv)] = 0;
        r.force = -forceSearch(b, -side, seg, forceDepth - 1, 1, -Infinity, Infinity, evals);
        b[fOf(r.mv)] = b[tOf(r.mv)]; b[tOf(r.mv)] = cap;
      }
      forceNodes = evals.n;
      nodes += evals.n;
      for (const r of head) {
        const f = r.force === undefined ? r.value : r.force;
        r.value = f >= MATE - 400 || f <= -MATE + 400 ? f : 0.45 * r.value + 0.55 * f;
      }
      rows.sort((x, y) => y.value - x.value);
    }
    /* 全宽浅层校验：只对前 6 个候选展开「对手全部合法着 → 我方再走一层」，
       用同一棵几何树结算。解决的是 forceSearch 看不到的 quiet move。 */
    let verifyNodes = 0;
    const verifyOn = !opts.verifyThreat || threat0 >= opts.verifyThreat;
    if (pro && verifyOn && opts.verifyDepth && opts.verifyDepth > 0) {
      const topN = Math.min(opts.verifyTop || 6, rows.length);
      const head = rows.slice(0, topN);
      const vev = opts.verifyEval === 'classic'
        ? (bb, ss) => classicScore(bb, ss)
        : ev;
      const evals = { n: 0, cap: opts.verifyCap || 12000, ev: vev, seg, q: opts.verifyQ === undefined ? 2 : opts.verifyQ };
      for (const r of head) {
        const cap = b[tOf(r.mv)];
        b[tOf(r.mv)] = b[fOf(r.mv)]; b[fOf(r.mv)] = 0;
        r.verify = -fullSearch(b, -side, opts.verifyDepth - 1, -Infinity, Infinity, evals);
        b[fOf(r.mv)] = b[tOf(r.mv)]; b[tOf(r.mv)] = cap;
      }
      verifyNodes = evals.n;
      nodes += evals.n;
      for (const r of head) {
        const f = r.verify === undefined ? r.value : r.verify;
        if (opts.verifyVeto) {
          // 只否决“必死/大亏”的线路，不覆盖正常几何排序，避免把 CPL 拖坏
          if (f >= MATE - 400 || f <= -MATE + 400 || f <= -700) r.value = f;
        } else if (f >= MATE - 400 || f <= -MATE + 400) r.value = f;
        else {
          const vm = opts.verifyMix === undefined ? 0.45 : opts.verifyMix;
          r.value = (1 - vm) * r.value + vm * f;
        }
      }
      rows.sort((x, y) => y.value - x.value);
    }
    // 送杀过滤：如果某候选走后对手存在一步将死（将军且我方无解），往后退一档
    const allowsMateIn1 = (mv) => {
      const f = fOf(mv), t = tOf(mv), cap = b[t];
      b[t] = b[f]; b[f] = 0;
      let bad = false;
      for (const om of legal(b, -side)) {
        const f2 = fOf(om), t2 = tOf(om), cap2 = b[t2];
        b[t2] = b[f2]; b[f2] = 0;
        if (inCheck(b, side) && legal(b, side).length === 0) bad = true;
        b[f2] = b[t2]; b[t2] = cap2;
        if (bad) break;
      }
      b[f] = b[t]; b[t] = cap;
      return bad;
    };
    // 知己：给"走完之后大概率崩盘"的候选降权。权重刻意压小——诊断显示这个模型
    // 的 AUC 主要来自"手数越大越危险"，组内区分度只有 0.09 左右，只该在同一档
    // 候选之间做微调，不该盖过几何估值。
    if (opts.dangerW && MODEL && MODEL.battle && MODEL.battle.danger) {
      for (const r of rows) {
        const f = fOf(r.mv), t = tOf(r.mv), cap = b[t];
        b[t] = b[f]; b[f] = 0;
        const p = dangerOf(b, side, opts.ply === undefined ? 20 : opts.ply);
        b[f] = b[t]; b[t] = cap;
        r.danger = p;
        r.value -= opts.dangerW * p;
      }
      rows.sort((x, y) => y.value - x.value);
    }
    let pick = rows[0];
    for (let i = 0; i < Math.min(3, rows.length); i++) {
      if (!allowsMateIn1(rows[i].mv)) { pick = rows[i]; break; }
    }
    return { mv: pick.mv, value: pick.value, rows, nodes, width, repWidth,
             depth: 2 + forceDepth, forceNodes };
  }

  function routePlay(b, side, opts) {
    opts = opts || {};
    const t0 = Date.now();
    // 手数从 history 兜底取：崩盘模型的输入含 ply/50，缺省当 0 会把它推出训练分布
    const ply0 = opts.ply === undefined ? ((opts.history && opts.history.length) || 0) : opts.ply;
    const bk = (opts.book === false) ? null : bookPick(b, side, (opts.history || []).length, opts.bookEval || 0);
    if (bk) {
      return { mv: bk.mv, route: 'book', by: 'book', phase: null,
               localCand: null, globalCand: null, search: null,
               cpDelta: null, judgeDelta: null, gate: 0, cpGate: 0,
               book: { n: bk.n, score: bk.score }, ms: Date.now() - t0 };
    }
    if (opts.proMs) {
      const d = psRoot(b, side, { deepDepth: opts.proDepth || 12, deepMs: opts.proMs,
                                  deepCap: opts.proCap || 4e6, deepQ: 4 });
      if (d && d.mv) {
        return { mv: d.mv, route: 'pro', by: 'pro', phase: null,
                 localCand: null, globalCand: null, search: d,
                 cpDelta: null, judgeDelta: null, gate: 0, cpGate: 0, ms: d.ms };
      }
    }
    if (opts.deepDepth) {
      const d = deepRoot(b, side, opts);
      if (d.mv) {
        /* 深搜先按棋理把明显战术亏的着法过滤掉，剩下前 K 名再交给神经价值头做位置判断。
           几何仍在：深搜的 PST/王前威胁是几何，神经输入含 45 维几何。 */
        let rows = (d.rows || []).slice(0, opts.deepKeep || 10).map((r) => ({ mv: r.mv, deep: r.deep }));
        const seg = MODEL && MODEL.tree && MODEL.tree.model;
        if (seg && opts.deepEval !== 'classic') {
          for (const r of rows) {
            const cap = b[tOf(r.mv)];
            b[tOf(r.mv)] = b[fOf(r.mv)]; b[fOf(r.mv)] = 0;
            const cp = -treeScore(geometry(b, -side, 0, 0), seg, b, -side);
            b[fOf(r.mv)] = b[tOf(r.mv)]; b[tOf(r.mv)] = cap;
            r.nn = cp === null ? 0 : cp;
          }
          rows.sort((x, y) => y.nn - x.nn);
        }
        const pick = rows[0] || d;
        return { mv: pick.mv, route: 'deep', by: 'deep', phase: null,
                 localCand: null, globalCand: null, search: { ...d, rows },
                 cpDelta: null, judgeDelta: null, gate: 0, cpGate: 0, ms: Date.now() - t0 };
      }
    }
    const g = geometry(b, side, 0, 0);
    const r = retrieve(g.state, 0, 5);
    const cls = r ? r.knn.cls : situationLabel(b, side);
    const noise = opts.noise || 0;
    const hist = new Set(opts.history || []);
    const pl = pickWith(b, side, gravityLocal, cls, noise, hist);
    const pg = pickWith(b, side, gravityGlobal, cls, noise, hist);
    if (!pl || !pg) return { mv: 0, route: null };

    function evalCand(cand) {
      if (!cand) return null;
      const f = fOf(cand.mv), t = tOf(cand.mv), cap = b[t], piece = b[f];
      b[t] = piece; b[f] = 0;
      const g2 = geometry(b, -side, 0, 0);
      const mk = (sub, seg) => {
        if (!sub || !seg) return null;
        const p = winProbSpace(sub.state, sub.tokens, seg);
        return p ? { score: 1 - p.score, pWin: p.pLoss, pDraw: p.pDraw, pLoss: p.pWin } : null;
      };
      const own = mk(g2.a, MODEL && MODEL.winprob_local);
      const alt = mk(g2.b, MODEL && MODEL.winprob_global);
      const judg = mk(g2.c, MODEL && (MODEL.winprob_judge || MODEL.winprob_dual));
      const tree = MODEL && MODEL.tree ? treeScore(g2, MODEL.tree.model, b, side) : null;
      const cloud = tree === null && MODEL && MODEL.cloud ? cloudScore(g2, MODEL.cloud, b, side) : null;
      b[f] = b[t]; b[t] = cap;
      const pick = judg || own;
      const cpRaw = tree !== null ? tree : cloud;
      const cp = cpRaw === null ? null : -cpRaw;        // 走完轮到对手，取负号回到我方视角
      return { mv: cand.mv, phi: cand.score, score: pick ? pick.score : 0,
               own: own, alt: alt, judge: judg,
               cp: cp, byCp: tree !== null ? 'tree' : (cloud !== null ? 'cloud' : null),
               pWin: cp === null ? null : 1 / (1 + Math.exp(-cp / 400)) };
    }

    const localCand = evalCand(pl);
    const globalCand = evalCand(pg);
    const jl = localCand && localCand.judge ? localCand.judge.score : null;
    const jg = globalCand && globalCand.judge ? globalCand.judge.score : null;
    const gate = (opts.gate === undefined || opts.gate === null) ? 0.003 : opts.gate;
    const cpGate = (opts.cpGate === undefined || opts.cpGate === null) ? 0 : opts.cpGate;
    const cl = localCand && localCand.cp !== undefined ? localCand.cp : null;
    const cg = globalCand && globalCand.cp !== undefined ? globalCand.cp : null;
    let route = null, by = null;
    if (cl !== null && cg !== null && Math.abs(cl - cg) >= cpGate) {
      route = cl >= cg ? 'local' : 'global';
      by = (localCand.byCp === 'tree' || globalCand.byCp === 'tree') ? 'tree' : 'cloud';
    } else if (jl !== null && jg !== null && Math.abs(jl - jg) >= gate) {
      route = jl >= jg ? 'local' : 'global';
      by = 'judge';                                  // 裁判空间的分差够大，听裁判
    } else if (localCand && globalCand && localCand.own && globalCand.own) {
      route = localCand.own.score >= globalCand.own.score ? 'local' : 'global';
      by = 'own';                                    // 裁判分差太小，回到各自空间的胜率
    } else {
      route = localCand ? 'local' : 'global';
      by = 'only';
    }
    const chosen = route === 'local' ? localCand : globalCand;
    const search = (opts.search === false || !(MODEL && MODEL.tree)) ? null
      : branchSearch(b, side, { width: opts.width, repWidth: opts.repWidth || 1,
                                history: opts.history, pro: opts.pro, replyCap: opts.replyCap,
                                rootTactics: opts.rootTactics, rootCap: opts.rootCap,
                                agg: opts.agg, mix: opts.mix,
                                force: opts.force, forceTop: opts.forceTop, forceCap: opts.forceCap,
                                verifyDepth: opts.verifyDepth, verifyTop: opts.verifyTop, verifyCap: opts.verifyCap,
                                verifyVeto: opts.verifyVeto, verifyEval: opts.verifyEval,
                                verifyQ: opts.verifyQ, classicW: opts.classicW,
                                verifyThreat: opts.verifyThreat, verifyMix: opts.verifyMix,
                                forceHgb: opts.forceHgb, policyW: opts.policyW,
                                historyTrack: opts.historyTrack, historyTop: opts.historyTop,
                                rootAll: opts.rootAll, rootKeep: opts.rootKeep,
                                sym: opts.sym, q: opts.q, bookCand: opts.bookCand,
                                replyModel: opts.replyModel, replyK: opts.replyK,
                                dangerW: opts.dangerW, ply: ply0 });
    const shapeA = g.a ? shapeOf(g.a.state, g.a.tokens) : null;
    const shapeB = g.b ? shapeOf(g.b.state, g.b.tokens) : null;
    const shapeC = g.c ? shapeOf(g.c.state, g.c.tokens) : null;
    return {
      mv: (search && search.mv) || (chosen ? chosen.mv : (pl || pg).mv),
      route, by, judgeDelta: (jl !== null && jg !== null) ? (jl - jg) : null,
      cpDelta: (cl !== null && cg !== null) ? (cl - cg) : null, gate, cpGate,
      phase: cls, localCand, globalCand, search,
      shapeA, shapeB, shapeC, state: g.state, retrieve: r,
      nodes: (pl ? pl.top.length : 0) + (search ? search.nodes : 0) + (pg ? pg.top.length : 0),
      ms: Date.now() - t0
    };
  }

  // 兼容旧调用：单路线版本（局部势）
  function play(b, side, opts) {
    const t0 = Date.now();
    const g = geometry(b, side, 0, 0);
    const r = retrieve(g.state, 0, 5);
    const cls = r ? r.knn.cls : situationLabel(b, side);
    const pick = gravityPick(b, side, { phase: cls, noise: (opts && opts.noise) || 0, history: (opts && opts.history) || [] });
    const lg = legal(b, side);
    return { mv: pick ? pick.mv : (lg.length ? lg[0] : 0), score: pick ? pick.score : 0, phase: cls,
             state: g.state, retrieve: r, top: pick ? pick.top : [], nodes: pick ? pick.nodes : 0,
             ms: Date.now() - t0 };
  }

  // ---------------------------------------------------------------- 重复局面
  const ZOB = new Int32Array(90 * 15);
  (function () {
    let s = 20261115;
    for (let i = 0; i < 90 * 15; i++) {
      s = (s * 1103515245 + 12345) & 0x7fffffff;
      ZOB[i] = s;
    }
  })();
  const pidx = (p) => (p > 0 ? p : 7 - p);
  const SIDE_Z = 0x5bf03635;
  function hashBoard(b) {
    let h = 0;
    for (let s = 0; s < 90; s++) { const p = b[s]; if (p) h ^= ZOB[s * 15 + pidx(p)]; }
    return h;
  }
  function keyOf(b, side) { return hashBoard(b) ^ (side === RED ? SIDE_Z : 0); }
  /* 置换表专用 53 位键：32 位 Zobrist 在 30 万节点量级必然碰撞，
     深搜会把别的局面的分数当成本局面，直接走出送子着。
     用第二张独立随机表拼到 53 位（JS Number 安全整数上限内）。
     开局库仍用旧的 keyOf，避免已有库整体失效。 */
  const ZOB2 = new Int32Array(90 * 15);
  (function () {
    let s = 99182631;
    for (let i = 0; i < 90 * 15; i++) {
      s = (s * 1103515245 + 12345) & 0x7fffffff;
      ZOB2[i] = s;
    }
  })();
  function hashBoard2(b) {
    let h = 0;
    for (let s = 0; s < 90; s++) { const p = b[s]; if (p) h ^= ZOB2[s * 15 + pidx(p)]; }
    return h;
  }
  function keyTT(b, side) {
    const h1 = (hashBoard(b) ^ (side === RED ? SIDE_Z : 0)) >>> 0;
    const h2 = (hashBoard2(b) ^ (side === RED ? SIDE_Z : 0)) >>> 0;
    return h1 * 2097152 + (h2 & 0x1fffff);
  }

  // ---------------------------------------------------------------- 开局库（可选）
  let BOOK = null;
  function setBook(bk) { BOOK = bk || null; }
  /* 闭合层权重（推理期可覆盖），null 表示退回模型内自带的 seg.closure */
  function setClosure(w) {
    if (MODEL && MODEL.tree && MODEL.tree.model) MODEL.tree.model.closure = w || null;
  }
  function bookInfo() {
    if (!BOOK) return null;
    return { games: BOOK.games || 0, plies: BOOK.plies || 0, positions: BOOK.size || Object.keys(BOOK.entries || {}).length };
  }
  /* 只取库内统计前 k 的着法，不做随机抽取——用于把历史着法塞进搜索候选集。 */
  function bookTopMoves(b, side, k) {
    if (!BOOK || !BOOK.entries) return [];
    const rows = BOOK.entries[keyOf(b, side)];
    if (!rows || !rows.length) return [];
    const cand = rows.filter((r) => r[1] >= 2).map((r) => ({ mv: r[0], n: r[1], score: (r[2] + 0.5 * r[3]) / r[1] }));
    cand.sort((x, y) => (y.score - x.score) || (y.n - x.n));
    return cand.slice(0, k).map((c) => c.mv);
  }

  function bookPick(b, side, ply, evalW) {
    if (!BOOK || !BOOK.entries) return null;
    if (ply !== undefined && BOOK.plies && ply >= BOOK.plies) return null;
    const rows = BOOK.entries[keyOf(b, side)];
    if (!rows || !rows.length) return null;
    const cand = rows.filter((r) => r[1] >= 2).map((r) => ({ mv: r[0], n: r[1], score: (r[2] + 0.5 * r[3]) / r[1] }));
    if (!cand.length) return null;
    cand.sort((a, b2) => b2.score - a.score);
    const keep = cand.filter((c) => c.score >= cand[0].score - 0.12);
    /* 知己：库里的分数是「人类走这步的胜率」，不是「我们走这步的胜率」。
       我们的引擎未必会下人类那套后续，所以再用几何树给一步后的局面打个分，
       按 evalW 混进排序。evalW 为 0 时完全退回原来的按人类频率抽样。 */
    if (evalW) {
      const seg = MODEL && MODEL.tree && MODEL.tree.model;
      if (seg) {
        for (const c of keep) {
          const f = fOf(c.mv), t = tOf(c.mv), cap = b[t];
          b[t] = b[f]; b[f] = 0;
          const cp = -treeScore(geometry(b, -side, 0, 0), seg, b, -side);
          b[f] = b[t]; b[t] = cap;
          c.cp = cp === null ? 0 : cp;
          c.mix = c.score + evalW * c.cp / 1000;
        }
        keep.sort((a, b2) => b2.mix - a.mix);
        return keep[0];
      }
    }
    const tot = keep.reduce((a, c) => a + Math.pow(c.n, 0.75), 0);
    let x = Math.random() * tot;
    for (const c of keep) { x -= Math.pow(c.n, 0.75); if (x <= 0) return c; }
    return keep[0];
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

  global.XQ3 = {
    W, H, RED, BLACK, KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN,
    NAME, VALUE, ROLE_W, CLASSES, CLASS_CN, PHASE, K,
    sq, initial, genPseudo, legal, inCheck, attacked, facing,
    hashBoard, keyOf, fOf, tOf, mk,
    setModel, setBook, setClosure, setHScale, bookPick, bookInfo, bookTopMoves,
    threatScore,
    tokensOf, geometry, geometryDual, retrieve, situationLabel, stateOf3, fitLine3, cloudScore, treeScore, matFeats, threatFeats, tensionFeats, closureOf, branchSearch, gravity, gravityPick, play, perft, gravityLocal, gravityGlobal, pickWith, shapeOf, winProbSpace, routePlay,
    attackersOf, seeCapture, exposedValue, SEE_V,
    battleFeats, dangerFeats, replyScore, dangerOf, classicScore, proEval
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.XQ3;
})(typeof window !== 'undefined' ? window : globalThis);
