/* 象棋规则内核：走法生成 / 将军判定 / 中文记谱
 *
 * 与 xq.cpp 的口径保持一致：
 *   - 棋盘 90 格，index = y*9+x，y=0 是黑方底线，红方在下
 *   - 红为正、黑为负，兵种 1..7 = 将 士 象 马 车 炮 兵
 *   - attacked() 含飞将（同列直面无阻挡）
 * 纯函数、无 DOM 依赖，页面与对拍脚本共用同一份实现。
 */
(function (root) {
  "use strict";

  const KING = 1, ADVISOR = 2, ELEPHANT = 3, HORSE = 4, ROOK = 5, CANNON = 6, PAWN = 7;
  const RED = 1, BLACK = -1;
  const W = 9;
  const START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w";
  const ORTHO = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const HORSE_MV = [
    [1, 2, 0, 1], [-1, 2, 0, 1], [1, -2, 0, -1], [-1, -2, 0, -1],
    [2, 1, 1, 0], [2, -1, 1, 0], [-2, 1, -1, 0], [-2, -1, -1, 0]
  ];
  const NAMES = {
    1: ["帅", "将"], 2: ["仕", "士"], 3: ["相", "象"], 4: ["马", "马"],
    5: ["车", "车"], 6: ["炮", "砲"], 7: ["兵", "卒"]
  };
  const CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];

  const sqOf = (x, y) => y * W + x;
  const inBoard = (x, y) => x >= 0 && x < 9 && y >= 0 && y < 10;
  const fx = (s) => s % W;
  const fy = (s) => (s / W) | 0;

  function parseFen(fen) {
    const b = new Int8Array(90);
    const parts = fen.trim().split(/\s+/);
    const rows = parts[0].split("/");
    for (let y = 0; y < 10 && y < rows.length; y++) {
      let x = 0;
      for (const ch of rows[y]) {
        if (ch >= "1" && ch <= "9") { x += +ch; continue; }
        const t = " KABNRCP".indexOf(ch.toUpperCase());
        if (t > 0 && x < 9) b[sqOf(x, y)] = ch === ch.toUpperCase() ? t : -t;
        x++;
      }
    }
    return { b, side: parts[1] === "b" ? BLACK : RED };
  }

  function toFen(b, side) {
    const out = [];
    for (let y = 0; y < 10; y++) {
      let run = 0, line = "";
      for (let x = 0; x < 9; x++) {
        const p = b[sqOf(x, y)];
        if (!p) { run++; continue; }
        if (run) { line += run; run = 0; }
        const t = Math.abs(p);
        line += p > 0 ? " KABNRCP"[t] : " KABNRCP"[t].toLowerCase();
      }
      if (run) line += run;
      out.push(line);
    }
    return out.join("/") + (side === RED ? " w" : " b");
  }

  function genPseudo(b, side) {
    const out = [];
    const add = (f, t) => {
      const q = b[t];
      if (q && (q > 0 ? RED : BLACK) === side) return;
      out.push(f * 100 + t);
    };
    for (let s = 0; s < 90; s++) {
      const p = b[s];
      if (!p || (p > 0 ? RED : BLACK) !== side) continue;
      const t = Math.abs(p), x = fx(s), y = fy(s);

      if (t === KING) {
        for (const [dx, dy] of ORTHO) {
          const nx = x + dx, ny = y + dy;
          if (nx < 3 || nx > 5) continue;
          if (side === RED ? (ny < 7 || ny > 9) : (ny < 0 || ny > 2)) continue;
          add(s, sqOf(nx, ny));
        }
        const ky0 = side === RED ? 0 : 7, ky1 = side === RED ? 2 : 9;
        for (let ny = ky0; ny <= ky1; ny++) {          // 飞将
          if (ny === y) continue;
          if (b[sqOf(x, ny)] !== -KING * side) continue;
          let clear = true;
          for (let yy = Math.min(y, ny) + 1; yy < Math.max(y, ny); yy++)
            if (b[sqOf(x, yy)]) { clear = false; break; }
          if (clear) add(s, sqOf(x, ny));
        }
      } else if (t === ADVISOR) {
        for (const [dx, dy] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
          const nx = x + dx, ny = y + dy;
          if (nx < 3 || nx > 5) continue;
          if (side === RED ? (ny < 7 || ny > 9) : (ny < 0 || ny > 2)) continue;
          add(s, sqOf(nx, ny));
        }
      } else if (t === ELEPHANT) {
        for (const [dx, dy] of [[2, 2], [2, -2], [-2, 2], [-2, -2]]) {
          const nx = x + dx, ny = y + dy;
          if (!inBoard(nx, ny)) continue;
          if (side === RED ? ny < 5 : ny > 4) continue;   // 象不过河
          if (b[sqOf(x + dx / 2, y + dy / 2)]) continue;  // 塞象眼
          add(s, sqOf(nx, ny));
        }
      } else if (t === HORSE) {
        for (const [dx, dy, lx, ly] of HORSE_MV) {
          const nx = x + dx, ny = y + dy;
          if (!inBoard(nx, ny)) continue;
          if (b[sqOf(x + lx, y + ly)]) continue;          // 蹩马腿
          add(s, sqOf(nx, ny));
        }
      } else if (t === ROOK || t === CANNON) {
        for (const [dx, dy] of ORTHO) {
          let nx = x + dx, ny = y + dy, screen = 0;
          while (inBoard(nx, ny)) {
            const q = b[sqOf(nx, ny)];
            if (t === ROOK) {
              if (!q) out.push(s * 100 + sqOf(nx, ny));
              else {
                if ((q > 0 ? RED : BLACK) !== side) out.push(s * 100 + sqOf(nx, ny));
                break;
              }
            } else {
              if (!screen) {
                if (!q) out.push(s * 100 + sqOf(nx, ny));
                else screen = 1;
              } else if (q) {
                if ((q > 0 ? RED : BLACK) !== side) out.push(s * 100 + sqOf(nx, ny));
                break;
              }
            }
            nx += dx; ny += dy;
          }
        }
      } else if (t === PAWN) {
        const dy = side === RED ? -1 : 1;
        const ny = y + dy;
        if (inBoard(x, ny)) add(s, sqOf(x, ny));
        const crossed = side === RED ? y <= 4 : y >= 5;
        if (crossed) {
          if (x > 0) add(s, sqOf(x - 1, y));
          if (x < 8) add(s, sqOf(x + 1, y));
        }
      }
    }
    return out;
  }

  function kingSq(b, side) {
    for (let s = 0; s < 90; s++) if (b[s] === KING * side) return s;
    return -1;
  }

  /* 目标格是否被 by 方攻击（含飞将） */
  function attacked(b, target, by) {
    if (target < 0) return true;
    const tx = fx(target), ty = fy(target);

    const ylo = by === RED ? 7 : 0, yhi = by === RED ? 9 : 2;
    for (let y = ylo; y <= yhi; y++) {
      for (let x = 3; x <= 5; x++) {
        const p = b[sqOf(x, y)];
        if (!p || (p > 0 ? RED : BLACK) !== by) continue;
        const t = Math.abs(p);
        if (t === KING) {
          if (x === tx && y !== ty) {
            let clear = true;
            for (let yy = Math.min(y, ty) + 1; yy < Math.max(y, ty); yy++)
              if (b[sqOf(x, yy)]) { clear = false; break; }
            if (clear) return true;
          }
          if (Math.abs(x - tx) + Math.abs(y - ty) === 1) return true;
        } else if (t === ADVISOR) {
          if (Math.abs(x - tx) === 1 && Math.abs(y - ty) === 1) return true;
        }
      }
    }

    const ELE = [[2, 0], [6, 0], [0, 2], [4, 2], [8, 2], [2, 4], [6, 4]];
    for (const [ex, eyRaw] of ELE) {
      const ey = by === RED ? 9 - eyRaw : eyRaw;
      if (b[sqOf(ex, ey)] !== ELEPHANT * by) continue;
      if (Math.abs(ex - tx) !== 2 || Math.abs(ey - ty) !== 2) continue;
      if (by === RED ? ty < 5 : ty > 4) continue;
      if (!b[sqOf((ex + tx) / 2, (ey + ty) / 2)]) return true;
    }

    const HDX = [1, 2, 2, 1, -1, -2, -2, -1], HDY = [2, 1, -1, -2, -2, -1, 1, 2];
    for (let d = 0; d < 8; d++) {
      const x = tx + HDX[d], y = ty + HDY[d];
      if (!inBoard(x, y)) continue;
      if (b[sqOf(x, y)] !== HORSE * by) continue;
      const ox = tx - x, oy = ty - y;
      const lx = Math.abs(ox) === 2 ? x + (ox > 0 ? 1 : -1) : x;
      const ly = Math.abs(ox) === 2 ? y : y + (oy > 0 ? 1 : -1);
      if (!b[sqOf(lx, ly)]) return true;
    }

    for (const [dx, dy] of ORTHO) {
      let x = tx + dx, y = ty + dy, step = 1, seen = 0;
      while (inBoard(x, y)) {
        const q = b[sqOf(x, y)];
        if (q) {
          const same = (q > 0 ? RED : BLACK) === by;
          const t = Math.abs(q);
          if (!seen) {
            if (same && (t === ROOK || (t === KING && step === 1))) return true;
            seen = 1;
          } else {
            if (same && t === CANNON) return true;
            break;
          }
        }
        x += dx; y += dy; step++;
      }
    }

    // 兵/卒：正面一格恒可攻，横向仅过河后
    const py = by === RED ? ty + 1 : ty - 1;
    if (inBoard(tx, py) && b[sqOf(tx, py)] === PAWN * by) return true;
    const crossed = by === RED ? ty <= 4 : ty >= 5;
    if (crossed) {
      if (tx > 0 && b[sqOf(tx - 1, ty)] === PAWN * by) return true;
      if (tx < 8 && b[sqOf(tx + 1, ty)] === PAWN * by) return true;
    }
    return false;
  }

  function inCheck(b, side) {
    const k = kingSq(b, side);
    if (k < 0) return true;
    return attacked(b, k, -side);
  }

  function legalMoves(b, side) {
    const out = [];
    for (const mv of genPseudo(b, side)) {
      const f = (mv / 100) | 0, t = mv % 100;
      const cap = b[t];
      b[t] = b[f]; b[f] = 0;
      if (!inCheck(b, side)) out.push(mv);
      b[f] = b[t]; b[t] = cap;
    }
    return out;
  }

  function perft(b, side, d) {
    if (d === 0) return 1;
    const lm = legalMoves(b, side);
    if (d === 1) return lm.length;
    let n = 0;
    for (const mv of lm) {
      const f = (mv / 100) | 0, t = mv % 100;
      const cap = b[t];
      b[t] = b[f]; b[f] = 0;
      n += perft(b, -side, d - 1);
      b[f] = b[t]; b[t] = cap;
    }
    return n;
  }

  /* ------------------------------ 记谱 ------------------------------ */
  function cnName(p) {
    const t = Math.abs(p);
    return NAMES[t][p > 0 ? 0 : 1];
  }
  function fileText(x, side) {
    return side === RED ? CN_NUM[9 - x - 1] : String(x + 1);
  }

  function moveText(b, mv) {
    const f = (mv / 100) | 0, t = mv % 100;
    const p = b[f];
    if (!p) return "?";
    const side = p > 0 ? RED : BLACK;
    const x0 = fx(f), x1 = fx(t), y0 = fy(f), y1 = fy(t);
    const name = cnName(p);
    const t2 = Math.abs(p);

    // 同列同兵种用 前/中/后 取代起始列
    let prefix = "";
    const same = [];
    for (let s = 0; s < 90; s++) if (b[s] === p && fx(s) === x0) same.push(s);
    if (same.length >= 2 && t2 <= 7) {
      same.sort((a, c) => side === RED ? fy(a) - fy(c) : fy(c) - fy(a));
      const idx = same.indexOf(f);
      if (same.length === 2) prefix = idx === 0 ? "前" : "后";
      else if (same.length === 3) prefix = ["前", "中", "后"][idx];
      else prefix = CN_NUM[same.length - idx - 1];
    }

    let act, dst;
    if (y0 === y1) {
      act = "平";
      dst = fileText(x1, side);
    } else {
      const fwd = side === RED ? y1 < y0 : y1 > y0;
      act = fwd ? "进" : "退";
      // 直行子写步数，斜行子写目标列
      if (t2 === ROOK || t2 === CANNON || t2 === PAWN || t2 === KING) {
        const steps = Math.abs(y1 - y0);
        dst = side === RED ? CN_NUM[steps - 1] : String(steps);
      } else {
        dst = fileText(x1, side);
      }
    }
    const head = prefix ? prefix + name : name + fileText(x0, side);
    return head + act + dst;
  }

  function uciOf(mv) {
    const f = (mv / 100) | 0, t = mv % 100;
    return String.fromCharCode(97 + fx(f)) + (9 - fy(f)) +
           String.fromCharCode(97 + fx(t)) + (9 - fy(t));
  }
  function parseUci(u) {
    if (!/^[a-i][0-9][a-i][0-9]$/.test(u)) return 0;
    const f = sqOf(u.charCodeAt(0) - 97, 9 - (u.charCodeAt(1) - 48));
    const t = sqOf(u.charCodeAt(2) - 97, 9 - (u.charCodeAt(3) - 48));
    return f * 100 + t;
  }

  root.XQ = {
    KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN, RED, BLACK, W,
    START_FEN, ORTHO, HORSE_MV, NAMES, CN_NUM,
    sqOf, inBoard, fx, fy,
    parseFen, toFen, genPseudo, kingSq, attacked, inCheck, legalMoves, perft,
    cnName, fileText, moveText, uciOf, parseUci
  };
})(typeof window !== "undefined" ? window : globalThis);
