// GeoLite C++ 搜索引擎（中国象棋）
// 规则与 GeoLite 一致：KING=1,ADVISOR=2,ELEPHANT=3,HORSE=4,ROOK=5,CANNON=6,PAWN=7；红正黑负。
// 走法编码 mv = from*100 + to，sq = y*9+x，y=0 黑底线，y=9 红底线。
// UCI 子集：uci / isready / position fen ... [moves ...] / go movetime N | go depth N
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#ifdef USE_STATIC
#include "linear_weight_static.h"
#else
#include "linear_weight_aug.h"
#endif
#ifdef USE_GEO
#include "geo_eval.h"
#endif
#if defined(USE_MLP)
#include "mlp_eval.h"
#ifndef MLP_SCALE
#define MLP_SCALE 1.0f
#endif
#endif
#ifndef MIX_W
#define MIX_W 0
#endif
/* 空着裁剪的子力下限（双方非将子力总和）。低于此值视为残局，禁用空着。 */
#ifndef NULL_MIN_MAT
#define NULL_MIN_MAT 1800
#endif
/* qsearch 的最小 ply 是 2（根节点 negamax 的 ply 为 1），阈值写成 1 会让补充
   将军的代码永远不执行（已验证：开与不开结果逐位相同）。 */
#ifndef QS_CHECK_PLY
#define QS_CHECK_PLY 4
#endif

using namespace std;

static const int RED = 1, BLACK = -1;
enum { EMPTY = 0, KING = 1, ADVISOR = 2, ELEPHANT = 3, HORSE = 4, ROOK = 5, CANNON = 6, PAWN = 7 };
static const int PV[8] = {0, 0, 200, 200, 450, 900, 450, 100};
static const int MATE = 30000;
static const int MAXPLY = 96;

static int8_t B[90];
static int us = RED;
static uint64_t KEY = 0;
static uint64_t Z[90][15];
static const uint64_t ZSIDE = 0x9e3779b97f4a7c15ULL;
/* 重复局面历史：环形缓冲。原实现用 2048 定长数组且只写到 2048 就停，
   长对局后 keyHist 全是旧值；索引也偏了一位，实际从未命中过重复局面。 */
static const int HIST_BITS = 12;
static const int HIST_SIZE = 1 << HIST_BITS;
static const int HIST_MASK = HIST_SIZE - 1;
static uint64_t keyHist[HIST_SIZE];
static int histLen = 0;

static inline int fx(int s) { return s % 9; }
static inline int fy(int s) { return s / 9; }
static inline int pidx(int p) { return p > 0 ? p : 7 - p; }
static inline int other(int s) { return -s; }
static inline bool onBoard(int x, int y) { return x >= 0 && x < 9 && y >= 0 && y < 10; }
static inline int sqOf(int x, int y) { return y * 9 + x; }
static inline bool inPalace(int x, int y, int side) {
  return x >= 3 && x <= 5 && (side == RED ? (y >= 7 && y <= 9) : (y >= 0 && y <= 2));
}
static inline bool crossedRiver(int y, int side) { return side == RED ? y <= 4 : y >= 5; }

// ---------------------------------------------------------------- Zobrist
static uint64_t splitmix64(uint64_t &s) {
  uint64_t z = (s += 0x9e3779b97f4a7c15ULL);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}
static void initZobrist() {
  uint64_t s = 20261115ULL;
  for (int i = 0; i < 90; i++)
    for (int p = 0; p < 15; p++) Z[i][p] = 0;
  for (int i = 0; i < 90; i++)
    for (int p = 1; p < 15; p++) Z[i][p] = splitmix64(s);
}

// ---------------------------------------------------------------- 棋盘
static uint64_t computeKey() {
  uint64_t k = 0;
  for (int i = 0; i < 90; i++) if (B[i]) k ^= Z[i][pidx(B[i])];
  if (us == BLACK) k ^= ZSIDE;
  return k;
}


/* FEN 解析：先解到临时盘，全部校验通过才提交。
   原实现边解边写 B[]，遇到 "position fen garbage" 会把棋盘清空却照常搜索，
   看上去不崩，实际是在空盘上乱走；这里要求 10 行、每行 ≤9 列、双方各恰好一将。 */
static bool setFen(const string &fen) {
  int8_t nb[90] = {0};
  int x = 0, y = 0;
  size_t i = 0;
  for (; i < fen.size(); i++) {
    char c = fen[i];
    if (c == ' ' || c == '\t') break;
    if (c == '/') {
      if (x != 9) return false;        // 每行必须恰好 9 格（此前只查 x>9，空行/短行会漏过）
      if (++y > 9) return false;
      x = 0;
      continue;
    }
    if (c >= '1' && c <= '9') {
      x += c - '0';
      if (x > 9) return false;
      continue;
    }
    int p = 0;
    switch (tolower(c)) {
      case 'k': p = KING; break;
      case 'a': p = ADVISOR; break;
      case 'b': p = ELEPHANT; break;
      case 'n': p = HORSE; break;
      case 'r': p = ROOK; break;
      case 'c': p = CANNON; break;
      case 'p': p = PAWN; break;
      default: return false;
    }
    if (c >= 'a' && c <= 'z') p = -p;   // 小写=黑方
    if (x >= 9) return false;
    nb[sqOf(x, y)] = (int8_t)p;
    x++;
  }
  if (x != 9) return false;              // 最后一行必须恰好 9 格（此前只查了 x>9，短行会漏过）
  if (y != 9) return false;             // 必须正好 10 行
  int rk = 0, bk = 0;
  for (int sIdx = 0; sIdx < 90; sIdx++) {
    if (nb[sIdx] == KING) rk++;
    else if (nb[sIdx] == -KING) bk++;
  }
  if (rk != 1 || bk != 1) return false; // 将帅缺失或重复的局面不接受

  memcpy(B, nb, sizeof(B));
  us = RED;
  while (i < fen.size() && (fen[i] == ' ' || fen[i] == '\t')) i++;
  if (i < fen.size() && (fen[i] == 'b' || fen[i] == 'B')) us = BLACK;
  histLen = 0;
  KEY = computeKey();
  keyHist[0] = KEY;      // 根局面入历史，之后每走一步按 histLen 写入环形缓冲
  return true;
}

static string fenOf() {
  string out;
  for (int y = 0; y < 10; y++) {
    int empty = 0;
    for (int x = 0; x < 9; x++) {
      int p = B[sqOf(x, y)];
      if (!p) { empty++; continue; }
      if (empty) { out += char('0' + empty); empty = 0; }
      char c = "?kabnrcp"[abs(p)];
      out += (p > 0) ? (char)toupper(c) : c;
    }
    if (empty) out += char('0' + empty);
    if (y != 9) out += '/';
  }
  out += (us == RED ? " w" : " b");
  return out;
}

// ---------------------------------------------------------------- 走法生成
struct Move { int mv; int score; };
static int genPseudo(int side, int *out) {
  int n = 0;
  for (int s = 0; s < 90; s++) {
    int p = B[s];
    if (!p || (p > 0) != (side > 0)) continue;
    int x = fx(s), y = fy(s), a = abs(p);
    if (a == KING) {
      static const int dx[4] = {0, 0, 1, -1}, dy[4] = {1, -1, 0, 0};
      for (int d = 0; d < 4; d++) {
        int nx = x + dx[d], ny = y + dy[d];
        if (!onBoard(nx, ny) || !inPalace(nx, ny, side)) continue;
        if (B[sqOf(nx, ny)] && (B[sqOf(nx, ny)] > 0) == (side > 0)) continue;
        out[n++] = s * 100 + sqOf(nx, ny);
      }
      continue;
    }
    if (a == ADVISOR) {
      static const int dx[4] = {1, 1, -1, -1}, dy[4] = {1, -1, 1, -1};
      for (int d = 0; d < 4; d++) {
        int nx = x + dx[d], ny = y + dy[d];
        if (!onBoard(nx, ny) || !inPalace(nx, ny, side)) continue;
        if (B[sqOf(nx, ny)] && (B[sqOf(nx, ny)] > 0) == (side > 0)) continue;
        out[n++] = s * 100 + sqOf(nx, ny);
      }
      continue;
    }
    if (a == ELEPHANT) {
      static const int dx[4] = {2, 2, -2, -2}, dy[4] = {2, -2, 2, -2};
      for (int d = 0; d < 4; d++) {
        int nx = x + dx[d], ny = y + dy[d];
        if (!onBoard(nx, ny)) continue;
        if (side == RED ? ny < 5 : ny > 4) continue;  // 象不过河
        int mx = x + dx[d] / 2, my = y + dy[d] / 2;
        if (B[sqOf(mx, my)]) continue;                 // 塞象眼
        if (B[sqOf(nx, ny)] && (B[sqOf(nx, ny)] > 0) == (side > 0)) continue;
        out[n++] = s * 100 + sqOf(nx, ny);
      }
      continue;
    }
    if (a == HORSE) {
      static const int dx[8] = {1, 2, 2, 1, -1, -2, -2, -1};
      static const int dy[8] = {2, 1, -1, -2, -2, -1, 1, 2};
      for (int d = 0; d < 8; d++) {
        int nx = x + dx[d], ny = y + dy[d];
        if (!onBoard(nx, ny)) continue;
        int lx = x + (abs(dx[d]) == 2 ? (dx[d] > 0 ? 1 : -1) : 0);
        int ly = y + (abs(dy[d]) == 2 ? (dy[d] > 0 ? 1 : -1) : 0);
        if (B[sqOf(lx, ly)]) continue;  // 蹩马腿
        if (B[sqOf(nx, ny)] && (B[sqOf(nx, ny)] > 0) == (side > 0)) continue;
        out[n++] = s * 100 + sqOf(nx, ny);
      }
      continue;
    }
    if (a == ROOK || a == CANNON) {
      static const int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
      for (int d = 0; d < 4; d++) {
        int nx = x, ny = y, screen = 0;
        while (true) {
          nx += dx[d]; ny += dy[d];
          if (!onBoard(nx, ny)) break;
          int q = B[sqOf(nx, ny)];
          if (a == ROOK) {
            if (!q) out[n++] = s * 100 + sqOf(nx, ny);
            else {
              if ((q > 0) != (side > 0)) out[n++] = s * 100 + sqOf(nx, ny);
              break;
            }
          } else {
            if (!q) { if (!screen) out[n++] = s * 100 + sqOf(nx, ny); continue; }
            if (!screen) { screen = 1; continue; }
            if ((q > 0) != (side > 0)) out[n++] = s * 100 + sqOf(nx, ny);
            break;
          }
        }
      }
      continue;
    }
    if (a == PAWN) {
      int fyStep = (side == RED ? -1 : 1);
      int nx = x, ny = y + fyStep;
      if (onBoard(nx, ny)) {
        int q = B[sqOf(nx, ny)];
        if (!q || (q > 0) != (side > 0)) out[n++] = s * 100 + sqOf(nx, ny);
      }
      if (crossedRiver(y, side)) {
        for (int d = -1; d <= 1; d += 2) {
          nx = x + d; ny = y;
          if (!onBoard(nx, ny)) continue;
          int q = B[sqOf(nx, ny)];
          if (!q || (q > 0) != (side > 0)) out[n++] = s * 100 + sqOf(nx, ny);
        }
      }
      continue;
    }
  }
  return n;
}

// ---------------------------------------------------------------- 攻击检测
static bool attacked(int target, int by) {
  int tx = fx(target), ty = fy(target);
  /* 王/士只在九宫内，扫 9 格而不是全盘 90 格 */
  int ylo = (by == RED ? 7 : 0), yhi = (by == RED ? 9 : 2);
  for (int y = ylo; y <= yhi; y++) {
    for (int x = 3; x <= 5; x++) {
      int p = B[sqOf(x, y)];
      if (!p) continue;
      if (p == (by > 0 ? KING : -KING)) {
        /* 这里的 attacked 只回答「该格是否被攻击」，与 JS/Python 特征口径一致：
           将帅只在相邻格构成攻击；飞将另由 kingsFacing() 在 inCheck 里处理。
           原实现把「同列无遮挡」也算进来，会让 6 个九宫威胁特征在将帅照面时偏离训练分布。 */
        if (abs(x - tx) + abs(y - ty) == 1) return true;
      } else if (p == (by > 0 ? ADVISOR : -ADVISOR)) {
        if (abs(x - tx) == 1 && abs(y - ty) == 1) return true;
      }
    }
  }
  /* 象只在 7 个固定点位 */
  static const int ex[7] = {2, 6, 0, 4, 8, 2, 6};
  static const int ey[7] = {0, 0, 2, 2, 2, 4, 4};
  for (int i = 0; i < 7; i++) {
    int x = ex[i], y = (by == RED ? 9 - ey[i] : ey[i]);
    int p = B[sqOf(x, y)];
    if (p != (by > 0 ? ELEPHANT : -ELEPHANT)) continue;
    if (abs(x - tx) != 2 || abs(y - ty) != 2) continue;
    if (by == RED ? ty < 5 : ty > 4) continue;  // 象不能过河攻击
    int mx = (x + tx) / 2, my = (y + ty) / 2;
    if (!B[sqOf(mx, my)]) return true;
  }
  // 马
  static const int hdx[8] = {1, 2, 2, 1, -1, -2, -2, -1};
  static const int hdy[8] = {2, 1, -1, -2, -2, -1, 1, 2};
  for (int d = 0; d < 8; d++) {
    int x = tx + hdx[d], y = ty + hdy[d];
    if (!onBoard(x, y)) continue;
    int p = B[sqOf(x, y)];
    if (!p || p != (by > 0 ? HORSE : -HORSE)) continue;
    /* 从马(x,y)看向目标(tx,ty)：马腿在长轴方向紧邻马的那一格 */
    int ox = tx - x, oy = ty - y;
    int lx, ly;
    if (abs(ox) == 2) { lx = x + (ox > 0 ? 1 : -1); ly = y; }
    else { lx = x; ly = y + (oy > 0 ? 1 : -1); }
    if (!B[sqOf(lx, ly)]) return true;
  }
  // 车/炮
  static const int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
  for (int d = 0; d < 4; d++) {
    int x = tx, y = ty, screen = 0;
    while (true) {
      x += dx[d]; y += dy[d];
      if (!onBoard(x, y)) break;
      int p = B[sqOf(x, y)];
      if (!p) continue;
      if (screen == 0) {
        if (p == (by > 0 ? ROOK : -ROOK)) return true;
        screen = 1;
      } else {
        if (p == (by > 0 ? CANNON : -CANNON)) return true;
        break;
      }
    }
  }
  // 兵/卒
  if (by == RED) {
    if (onBoard(tx, ty + 1)) {
      int p = B[sqOf(tx, ty + 1)];
      if (p == PAWN) return true;
    }
    for (int d = -1; d <= 1; d += 2) {
      int x = tx + d, y = ty;
      if (!onBoard(x, y)) continue;
      if (B[sqOf(x, y)] == PAWN && crossedRiver(y, RED)) return true;
    }
  } else {
    if (onBoard(tx, ty - 1)) {
      int p = B[sqOf(tx, ty - 1)];
      if (p == -PAWN) return true;
    }
    for (int d = -1; d <= 1; d += 2) {
      int x = tx + d, y = ty;
      if (!onBoard(x, y)) continue;
      if (B[sqOf(x, y)] == -PAWN && crossedRiver(y, BLACK)) return true;
    }
  }
  return false;
}

static int kingSq(int side) {
  int ylo = (side == RED ? 7 : 0), yhi = (side == RED ? 9 : 2);
  for (int y = ylo; y <= yhi; y++)
    for (int x = 3; x <= 5; x++) {
      int p = B[sqOf(x, y)];
      if (p == (side > 0 ? KING : -KING)) return sqOf(x, y);
    }
  return -1;
}
static bool inCheck(int side) {
  int k = kingSq(side);
  if (k < 0) return true;
  if (attacked(k, other(side))) return true;
  /* 飞将：将帅同列且中间无子，等同被将。attacked() 不再承担这一条，
     因为它同时服务 45 维特征的「九宫被攻击格数」，必须与 JS/Python 口径一致。 */
  int ek = kingSq(other(side));
  if (ek >= 0 && fx(k) == fx(ek)) {
    int lo = min(fy(k), fy(ek)) + 1, hi = max(fy(k), fy(ek));
    bool clear = true;
    for (int y = lo; y < hi; y++) if (B[sqOf(fx(k), y)]) { clear = false; break; }
    if (clear) return true;
  }
  return false;
}

// ---------------------------------------------------------------- make / unmake
struct Undo { int cap; uint64_t key; };
static inline int makeMove(int mv, Undo &u) {
  int f = mv / 100, t = mv % 100;
  int cap = B[t];
  u.cap = cap; u.key = KEY;
  if (cap) KEY ^= Z[t][pidx(cap)];
  int p = B[f];
  KEY ^= Z[f][pidx(p)];
  KEY ^= Z[t][pidx(p)];
  B[t] = (int8_t)p; B[f] = 0;
  KEY ^= ZSIDE;
  us = other(us);
  histLen++;
  keyHist[histLen & HIST_MASK] = KEY;   // 环形写入：长对局不会写穿，也不会停止记录
  return cap;
}
static inline void unmakeMove(int mv, const Undo &u) {
  int f = mv / 100, t = mv % 100;
  B[f] = B[t]; B[t] = (int8_t)u.cap;
  KEY = u.key;
  us = other(us);
  if (histLen > 0) histLen--;
}

static int genLegal(int side, int *out) {
  int tmp[128];
  int n = genPseudo(side, tmp), m = 0;
#ifdef GENLEGAL_FAST
  /* 只有这三类着法才可能把自家将暴露出来，其余直接放行：
       ① 己方正被将（任何着法都要复核）
       ② 走将
       ③ 起点与将「同行/同列」（车、炮、将照面），或距将切比雪夫距离 ≤ 2（马腿）
     象棋没有斜线长兵器，象/士走斜线不构成牵制，所以这是安全上界。 */
  const int k = kingSq(side);
  const bool inChk = inCheck(side);   // 含飞将，不能只调 attacked()
  const int kx = k % 9, ky = k / 9;
  for (int i = 0; i < n; i++) {
    int mv = tmp[i], f = mv / 100, t2 = mv % 100;
    int pt = B[f]; pt = pt > 0 ? pt : -pt;
    /* 起点与终点都要看：落在将的行列上会给炮当炮架，同样能送将。 */
    const int fx = f % 9, fy = f / 9, tx = t2 % 9, ty = t2 / 9;
    const int dxf = fx > kx ? fx - kx : kx - fx, dyf = fy > ky ? fy - ky : ky - fy;
    const int dxt = tx > kx ? tx - kx : kx - tx, dyt = ty > ky ? ty - ky : ky - ty;
    const bool nearF = (dxf <= 2 && dyf <= 2), nearT = (dxt <= 2 && dyt <= 2);
    const bool lineF = (dxf == 0 || dyf == 0), lineT = (dxt == 0 || dyt == 0);
    if (!inChk && pt != KING && !nearF && !nearT && !lineF && !lineT) { out[m++] = mv; continue; }
    Undo u;
    makeMove(mv, u);
    if (!inCheck(other(us))) out[m++] = mv;
    unmakeMove(mv, u);
  }
#else
  for (int i = 0; i < n; i++) {
    Undo u;
    makeMove(tmp[i], u);
    if (!inCheck(other(us))) out[m++] = tmp[i];
    unmakeMove(tmp[i], u);
  }
#endif
  return m;
}

// ---------------------------------------------------------------- 评估
// 200k 皮卡鱼标签训练的线性棋子平面模型：等价于学习到的子力+PST，O(棋子数)。
static int evalPosPlane(int side) {
  float s = LB;
  int pawnR[9] = {0}, pawnB[9] = {0};
  int ownR[10], ownP[10], nR = 0, nP = 0;
  int ksq = -1, ownAdv = 0, ownEle = 0;
  for (int i = 0; i < 90; i++) {
    int p = B[i];
    if (!p) continue;
    int a = abs(p), x = fx(i), y = fy(i);
    int nx = side > 0 ? x : 8 - x;
    int ny = side > 0 ? y : 9 - y;
    bool own = (p > 0) == (side > 0);
    int ch = (a - 1) + (own ? 0 : 7);
    s += LW[ch][ny * 9 + nx];
    if (a == PAWN) { if (p > 0) pawnR[x]++; else pawnB[x]++; }
    if (own && a == ROOK && nR < 10) ownR[nR++] = i;
    if (own && a == PAWN && nP < 10) ownP[nP++] = i;
    if (own && a == KING) ksq = i;
    if (own && a == ADVISOR) ownAdv++;
    if (own && a == ELEPHANT) ownEle++;
  }
  if (ksq < 0) return -MATE / 2;  /* 王被吃：搜索中不应出现，兜底 */
#ifndef USE_STATIC
  /* 8 个几何特征：权重由 20 万皮卡鱼标签回归学习，不再手调 */
  float f[8] = {0};
  {
    int kx = fx(ksq), ky = fy(ksq);
    static const int dx4[4] = {1, -1, 0, 0}, dy4[4] = {0, 0, 1, -1};
    for (int d = 0; d < 4; d++) {
      int cx = kx, cy = ky, seen = 0;
      while (true) {
        cx += dx4[d]; cy += dy4[d];
        if (!onBoard(cx, cy)) break;
        int q = B[sqOf(cx, cy)];
        if (!q) continue;
        bool enemy = (q > 0) != (side > 0);
        int a = abs(q);
        if (seen == 0) {
          if (enemy && a == ROOK) f[0] += 1;
          seen = 1;
        } else {
          if (enemy && a == CANNON) f[1] += 1;
          break;
        }
      }
    }
    static const int hx[8] = {1, 2, 2, 1, -1, -2, -2, -1};
    static const int hy[8] = {2, 1, -1, -2, -2, -1, 1, 2};
    for (int k = 0; k < 8; k++) {
      int cx = kx + hx[k], cy = ky + hy[k];
      if (!onBoard(cx, cy)) continue;
      int q = B[sqOf(cx, cy)];
      if (q && (q > 0) != (side > 0) && abs(q) == HORSE) f[2] += 1;
    }
    for (int d = 0; d < 4; d++) {
      int cx = kx + dx4[d], cy = ky + dy4[d];
      if (!onBoard(cx, cy)) continue;
      int q = B[sqOf(cx, cy)];
      if (q && (q > 0) != (side > 0) && abs(q) == PAWN) f[3] += 1;
    }
    f[4] = (float)ownAdv;
    f[5] = (float)ownEle;
  }
  /* 车的机动性 */
  for (int k = 0; k < nR; k++) {
    int i = ownR[k], x = fx(i), y = fy(i), mob = 0;
    static const int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
    for (int d = 0; d < 4; d++) {
      int cx = x, cy = y;
      while (true) {
        cx += dx[d]; cy += dy[d];
        if (!onBoard(cx, cy)) break;
        int q = B[sqOf(cx, cy)];
        if (q) { if ((q > 0) != (side > 0)) mob++; break; }
        mob++;
      }
    }
    f[6] += (float)min(mob, 14);
  }
  /* 通路兵（同/邻线无对方兵） */
  for (int k = 0; k < nP; k++) {
    int i = ownP[k], x = fx(i);
    int blocked = 0;
    for (int ff = max(0, x - 1); ff <= min(8, x + 1); ff++) {
      if (B[i] > 0) blocked += pawnB[ff]; else blocked += pawnR[ff];
    }
    if (blocked == 0) f[7] += 1;
  }
  for (int k = 0; k < 8; k++) s += WF[k] * f[k];
#endif
  return (int)lroundf(s);
}

// 叶子评估入口：USE_GEO 时走 45 维几何树（与 JS 引擎同一套模型），否则走 1260 平面线性。
// MIX_W > 0 时把平面模型按比例混入——几何树把劣势压缩到 ~0.53 倍（回归 tree≈0.53·plane+96），
// 平面模型补的正是「动态范围」，几何树补的是「结构判断」，两者残差 sd 149cp 说明信息互补。
static int evalPos(int side) {
#if defined(USE_MLP) && defined(USE_MLP_BLEND)
  /* 混合：MLP 价值头负责精度，旧「几何树 + 平面」负责稳定性。
     两者尺度已经对齐（MLP×0.75 ≈ 旧融合），直接按比例平均即可。 */
  const int pf = evalPosPlane(side);
  const int g = geo::evalBoard(B, side);
  const int oldf = (65 * g + 35 * pf) / 100;
  float f[45];
  geo::feats45(B, side, f);
  float in[46];
  for (int i = 0; i < 45; i++) in[i] = f[i];
  in[45] = pf * (1.f / 200.f);
  const float m = mlpval::score(in) * MLP_SCALE;
  return (int)std::lroundf((MLP_W * m + (100 - MLP_W) * oldf) / 100.f);
#elif defined(USE_MLP)
  /* v2 价值头：45 维几何特征 + 平面分/200 → MLP(192,96) → cp。
     融合不再靠手调比例：网络自己在 20 万局面上学出了「几何管结构、平面管尺度」。 */
  const int pf = evalPosPlane(side);
  float f[45];
  geo::feats45(B, side, f);
  float in[46];
  for (int i = 0; i < 45; i++) in[i] = f[i];
  in[45] = pf * (1.f / 200.f);
  return (int)std::lroundf(mlpval::score(in) * MLP_SCALE);
#elif defined(USE_GEO) && (MIX_W > 0)
  const int g = geo::evalBoard(B, side);
  const int p = evalPosPlane(side);
#ifdef GEO_CAL
  /* 先把树校准到平面的尺度与零点：回归得 tree ≈ 0.530·plane + 95.6，
     故 plane ≈ (tree − 95.6)/0.530。不校准的话，树的 +96 偏置会一并混进来，
     对称开局就会被高估 +60cp（实测开局 eval=71）。 */
  const int gc = (int)std::lround((g - 95.6f) * 1.887f);
  return (MIX_W * gc + (100 - MIX_W) * p) / 100;
#else
  return (MIX_W * g + (100 - MIX_W) * p) / 100;
#endif
#elif defined(USE_GEO)
  return geo::evalBoard(B, side);
#else
  return evalPosPlane(side);
#endif
}

#ifdef USE_GEO_ORDER
/* 几何先验（只用于排序，不参与评估）：一步棋把子落到「敌将的 line 空间轴线」上了吗？
   line 空间在 engine3d.js 里的定义是「同行/同列且遮挡 ≤ 6」；排序不需要那么宽，
   只保留遮挡 0（车/兵/将直通）与遮挡 1（炮架）两种真威胁。O(9)，不进 RBF 树。
   返回 0=无，1=隔一子成炮架，2=直通。 */
static inline int geoLinePress(int f, int t, int side, int ek) {
  if (ek < 0) return 0;
  int p = B[f];
  if (!p) return 0;
  int pt = p > 0 ? p : -p;
  if (pt != ROOK && pt != CANNON && pt != PAWN) return 0;
  int tx = t % 9, ty = t / 9, kx = ek % 9, ky = ek / 9;
  if (tx != kx && ty != ky) return 0;
  /* 不试走、不写棋盘：起点格在扫描时跳过即可（子已离开），
     这样既等价又不会破坏编译器对 B 的只读假设——排序是每节点每着法都要调的。 */
  int dx = (kx > tx) - (kx < tx), dy = (ky > ty) - (ky < ty);
  int x = tx + dx, y = ty + dy, blk = 0;
  while ((x != kx || y != ky) && blk <= 1) {
    const int s2 = y * 9 + x;
    if (s2 != f && B[s2]) blk++;
    x += dx; y += dy;
  }
  if (pt == CANNON) return blk == 1 ? 2 : 0;
  return blk == 0 ? 2 : 0;
}
#endif

// ---------------------------------------------------------------- 置换表
struct TTEntry {
  uint64_t key;
  int16_t score;
  uint8_t depth;
  uint8_t flag;  // 0 exact, 1 lower, 2 upper
  uint16_t mv;
};
/* Flash：置换表缩到 2^18 × 16B = 4MB。
   标准版 2^22 是 64MB 静态 BSS，边缘设备（路由器/开发板/手机）吃不下。 */
#if defined(FLASH)
static const int TT_BITS = 18;
#else
static const int TT_BITS = 22;
#endif
static const int TT_SIZE = 1 << TT_BITS;
static TTEntry TT[TT_SIZE];
static inline void ttClear() { memset(TT, 0, sizeof(TT)); }
static inline TTEntry *ttProbe(uint64_t k) { return &TT[(uint32_t)(k * 0x9e3779b97f4a7c15ULL >> (64 - TT_BITS))]; }

// ---------------------------------------------------------------- 搜索
static chrono::steady_clock::time_point DEADLINE;
static bool STOP = false;
static uint64_t NODES = 0;
static long long NODE_LIMIT = 0;   // >0 时按节点数停止，用于等算力基准
static int killers[2][MAXPLY];
static int historyTbl[90][90];
/* 反制着法：记录「对手刚走 mv，我们最佳应手是 X」。比 killer 更具体，
   且不依赖深度——中局转入固定结构的残局时尤其有效。
   索引是着法编码 from*100+to（最大 89*100+89=8989），不能用 90*90=8100。 */
static int counterTbl[9000];
static int plyMove[MAXPLY];   // 本层实际走的着法，供下一层查反制表

/* 双方非将子力总和：空着裁剪在低子力残局里不成立（楚格旺），必须按子力关掉。 */
static inline int matNonKing() {
  int s = 0;
  for (int i = 0; i < 90; i++) {
    int p = B[i];
    if (p) { int a = p > 0 ? p : -p; if (a != KING) s += PV[a]; }
  }
  return s;
}

static inline bool timeUp() {
  if (STOP) return true;
  /* 等节点口径：节点数与评估实现完全确定，做 A/B 时不带时限抖动 */
  if (NODE_LIMIT > 0 && (long long)NODES >= NODE_LIMIT) { STOP = true; return true; }
#ifdef CLOCK_THROTTLE
  /* 每 512 节点才读一次时钟：2.5µs/节点的评估下 20ns 只是零头，
     但在 0.5µs/节点的浅层节点上能占到 4%。
     注意：非 512 倍数的节点必须直接返回，否则会落到下面的每节点读钟路径，
     节流形同虚设。 */
  if ((NODES & 511) == 0) {
    if (chrono::steady_clock::now() > DEADLINE) { STOP = true; return true; }
    return false;
  }
#else
  /* 每节点都读时钟：clock_gettime 约 20ns，相对 2.5µs 的叶子评估只有 ~1% 开销，
     但能保证「期望窗口连续放宽」这类不涨节点数的路径也一定退得出来。 */
  if (chrono::steady_clock::now() > DEADLINE) STOP = true;
#endif
  return STOP;
}

static int qsearch(int alpha, int beta, int ply) {
  NODES++;
  if (timeUp()) return 0;
  if (ply >= MAXPLY) return evalPos(us);

  if (inCheck(us)) {
    int lm[128];
    int n = genLegal(us, lm);
    if (!n) return -MATE + ply;
    int best = -MATE;
    for (int i = 0; i < n; i++) {
      Undo u; makeMove(lm[i], u);
      int v = -qsearch(-beta, -alpha, ply + 1);
      unmakeMove(lm[i], u);
      if (STOP) return 0;
      if (v > best) best = v;
      if (v > alpha) alpha = v;
      if (alpha >= beta) return alpha;
    }
    return best;
  }

  int stand = evalPos(us);
  if (stand >= beta) return stand;
  if (stand > alpha) alpha = stand;

  int caps[128], n = 0;
  int tmp[128];
  int np = genPseudo(us, tmp);
#if defined(FLASH)
  static const int DELTA_MARGIN = 120;   // Flash：余量再收 20cp，多吃掉一批追不上的吃子
#elif defined(QS_DELTA_SMALL)
  static const int DELTA_MARGIN = 140;
#elif defined(SEARCH_CONSERVATIVE)
  static const int DELTA_MARGIN = 200;
#elif defined(USE_MLP)
  static const int DELTA_MARGIN = 300;   // 新评估尺度约 1.5 倍，余量同比放大
#else
  static const int DELTA_MARGIN = 200;
#endif
  for (int i = 0; i < np; i++) {
    int t = tmp[i] % 100;
    if (!B[t]) continue;
    /* delta 裁剪：即使白吃这个子也追不上 alpha，这条线不可能影响结果 */
    if (stand + PV[abs(B[t])] + DELTA_MARGIN <= alpha) continue;
    Undo u;
    makeMove(tmp[i], u);
    bool ok = !inCheck(other(us));
    unmakeMove(tmp[i], u);
    if (ok) caps[n++] = tmp[i];
  }
  // MVV-LVA：先用「被吃子价值」再用「走子价值」比较，两步都必须取自同一着法
  int cs[128];
  for (int i = 0; i < n; i++)
    cs[i] = PV[abs(B[caps[i] % 100])] * 16 - PV[abs(B[caps[i] / 100])];
  std::pair<int, int> cpo[128];
  for (int i = 0; i < n; i++) cpo[i] = {cs[i], caps[i]};
  std::sort(cpo, cpo + n, [](const std::pair<int, int> &a, const std::pair<int, int> &b) {
    return a.first != b.first ? a.first > b.first : a.second < b.second;
  });
  for (int i = 0; i < n; i++) caps[i] = cpo[i].second;
#if defined(FLASH)
  static const int DELTA2 = 90;
#elif defined(QS_DELTA_SMALL)
  static const int DELTA2 = 120;
#else
  static const int DELTA2 = 180;
#endif
  for (int i = 0; i < n; i++) {
    int victim = B[caps[i] % 100];
    if (stand + PV[abs(victim)] + DELTA2 < alpha) continue;
    Undo u; makeMove(caps[i], u);
    int v = -qsearch(-beta, -alpha, ply + 1);
    unmakeMove(caps[i], u);
    if (STOP) return 0;
    if (v >= beta) return v;
    if (v > alpha) alpha = v;
  }
#ifdef QS_CHECK
  /* 象棋的杀法大量由「静着 + 将军」构成，只搜吃子会整条战术线漏掉。
     只在接近 alpha 时补，避免无谓膨胀；限头两层。 */
  if (ply < QS_CHECK_PLY && n < 96 && stand + 220 >= alpha) {
    int nq = genPseudo(us, tmp);
    for (int i = 0; i < nq && n < 110; i++) {
      int mv = tmp[i];
      if (B[mv % 100]) continue;                 // 吃子已经在上面搜过
      Undo u; makeMove(mv, u);
      bool gaveCheck = inCheck(us);              // us 已翻到对方
      bool legal = !inCheck(other(us));
      if (gaveCheck && legal) {
        int v = -qsearch(-beta, -alpha, ply + 1);
        unmakeMove(mv, u);
        if (STOP) return 0;
        if (v >= beta) return v;
        if (v > alpha) alpha = v;
        continue;
      }
      unmakeMove(mv, u);
    }
  }
#endif
  return alpha;
}

static int negamax(int depth, int alpha, int beta, int ply, bool allowNull) {
  NODES++;
  if (timeUp()) return 0;
  if (ply >= MAXPLY) return evalPos(us);
  /* 重复局面判和，避免优势时无意义地来回走。
     keyHist 存的是「走完第 N 步后的局面」，当前节点 histLen=N；
     同走子方的历史局面隔 2 步，取 (N-2)、(N-4)…，环形索引即可。 */
  const int maxBack = histLen < HIST_SIZE - 2 ? histLen : HIST_SIZE - 2;
  for (int back = 2; back <= maxBack; back += 2) {
    if (keyHist[(histLen - back) & HIST_MASK] == KEY) return 0;
  }

  bool chk = inCheck(us);
  if (depth <= 0) return qsearch(alpha, beta, ply);

  /* 置换表可能抬高 alpha / 压低 beta；条目 flag 必须按「进入本节点时的原始窗口」
     判定，否则 fail-low 会被误记成 exact。 */
  const int alphaOrig = alpha, betaOrig = beta;

  uint64_t k = KEY;
  TTEntry *e = ttProbe(k);
  int ttMove = 0;
  if (e->key == k) {
    ttMove = e->mv;
    if (e->depth >= depth && abs(e->score) < MATE - 100) {
      if (e->flag == 0) return e->score;
      if (e->flag == 1 && e->score > alpha) alpha = e->score;
      if (e->flag == 2 && e->score < beta) beta = e->score;
      if (alpha >= beta) return e->score;
    }
  }

  int lm[128];
  int n = genLegal(us, lm);
  if (!n) return -MATE + ply;

  int se = 32000;
  auto staticEval = [&]() {
    if (se == 32000) se = evalPos(us);
    return se;
  };

  // 剪枝阈值必须跟评估尺度走：v2 价值头输出接近真实 cp，约为旧融合分的 1.5 倍，
  // 阈值不放大就会让 razoring/futility 几乎不触发，节点数翻倍。
  /* 阈值档位与评估尺度解耦：SEARCH_CONSERVATIVE 显式指定保守档，
     便于在同一份价值头上做「剪枝强度」的 A/B 实验。 */
#if defined(FLASH)
  /* Flash 档：不求棋艺，只求「看得过去 + 省算力」。阈值放得很松，
     浅层就把明显不成立的线砍掉。 */
  static const int RAZOR_K = 45, FUTIL_K = 50, NULL_CAP = 900;
#elif defined(SEARCH_CONSERVATIVE)
  static const int RAZOR_K = 70, FUTIL_K = 80, NULL_CAP = 1200;
#elif defined(USE_MLP) && !defined(MLP_SMALL_SCALE)
  static const int RAZOR_K = 105, FUTIL_K = 120, NULL_CAP = 1800;
#else
  static const int RAZOR_K = 70, FUTIL_K = 80, NULL_CAP = 1200;
#endif
  // 反向无效着裁剪：静态分已远超 beta，直接返回
  if (!chk && depth <= 3 && ply > 0) {
    int ev = staticEval();
    if (ev - RAZOR_K * depth >= beta) return ev;
  }
  // 无效着裁剪：深度浅且静态分远低于 alpha
  if (!chk && depth <= 2 && ply > 0) {
    int ev = staticEval();
    if (ev + FUTIL_K * depth <= alpha) return ev;
  }

  // 空着裁剪
  /* 子力门控的 O(90) 扫描只在空着裁剪确实会被尝试时才做：
     把 matNonKing() 从条件前挪到条件内，chk/浅层/大静态分节点不再白扫一遍棋盘。 */
#if defined(FLASH)
  /* Flash：空着裁剪提前到 depth 2，缩减量也更大 */
  if (allowNull && !chk && depth >= 2 && ply > 0 && abs(staticEval()) < NULL_CAP) {
    int R = depth >= 5 ? 3 : 2;
#else
  if (allowNull && !chk && depth >= 3 && ply > 0 && abs(staticEval()) < NULL_CAP) {
    int R = depth >= 6 ? 3 : 2;
#endif
#ifdef NULL_MAT_GATE
    /* 残局里「不走棋」往往比走棋更差（楚格旺反例），空着裁剪会给出假上界，
       直接把正确着法剪掉。子力低于阈值时干脆不用。 */
    if (matNonKing() >= NULL_MIN_MAT) {
#endif
      Undo u; u.key = KEY; u.cap = 0;
      KEY ^= ZSIDE; us = other(us); NODES++;
      int v = -negamax(depth - 1 - R, -beta, -beta + 1, ply + 1, false);
      KEY = u.key; us = other(us);
      if (STOP) return 0;
      if (v >= beta) return v;
#ifdef NULL_MAT_GATE
    }
#endif
  }

  // 排序
  int score[128];
#ifdef USE_GEO_ORDER
  const int ek = kingSq(-us);   // 每节点只找一次敌将，排序里复用
#endif
  for (int i = 0; i < n; i++) {
    int mv = lm[i], f = mv / 100, t = mv % 100;
    int sc = 0;
    if (mv == ttMove) sc = 10000000;
    else if (B[t]) sc = 1000000 + PV[abs(B[t])] * 16 - PV[abs(B[f])];
    else if (mv == killers[0][ply]) sc = 50000;
    else if (mv == killers[1][ply]) sc = 30000;
#ifdef CM_ORDER
    else if (ply > 0 && mv == counterTbl[plyMove[ply - 1]]) sc = 24000;
#endif
#ifdef USE_GEO_ORDER
    else {
      /* 几何先验插在 killer 之后、history 之前：
         静着里「几何上直接压到敌将 line 轴」的，通常就是下一步的强制手。 */
      const int gp = geoLinePress(f, t, us, ek);
      sc = historyTbl[f][t] + (gp == 2 ? 24000 : (gp == 1 ? 12000 : 0));
    }
#else
    else sc = historyTbl[f][t];
#endif
    score[i] = sc;
  }
  /* 排序：n≤128 的冒泡换成 std::sort，热节点上省 20–30% 排序时间；等分时按着法编码
     决出唯一顺序，保证同局面、同输入下逐位可复现。 */
  std::pair<int, int> ord[128];
  for (int i = 0; i < n; i++) ord[i] = {score[i], lm[i]};
  std::sort(ord, ord + n, [](const std::pair<int, int> &a, const std::pair<int, int> &b) {
    return a.first != b.first ? a.first > b.first : a.second < b.second;
  });
  for (int i = 0; i < n; i++) lm[i] = ord[i].second;

  int best = -MATE, bestMove = 0, moveCount = 0;
  for (int i = 0; i < n; i++) {
    int mv = lm[i];
    bool isCap = B[mv % 100] != 0;
#if defined(FLASH)
    /* Flash：静着只留前几支，深处也只给 10 支；后续着法几乎不可能成为最佳 */
    if (!isCap && depth <= 3 && moveCount >= (depth <= 1 ? 6 : 10)) { moveCount++; continue; }
#else
    if (!isCap && depth <= 2 && moveCount >= (depth <= 1 ? 8 : 14)) { moveCount++; continue; }
#endif
    plyMove[ply] = mv;
    Undo u; makeMove(mv, u);
    /* makeMove 会把 us 翻到对方，所以「我们是否将军」= inCheck(us)。
       历史实现写成 inCheck(other(us))，对合法着法恒为假——将军延伸从未生效。 */
#ifdef CHKEXT
    bool gives = inCheck(us);
    int ext = gives ? 1 : 0;
    if (ext && (ply > 48 || depth > 14)) ext = 0;   // 限制延伸总量，防止杀棋长链爆树
#else
    bool gives = inCheck(other(us));
    int ext = gives ? 1 : 0;
#endif
    int v;
    if (moveCount == 0) {
      v = -negamax(depth - 1 + ext, -beta, -alpha, ply + 1, true);
    } else {
      int red = 0;
#if defined(FLASH)
      /* Flash：第 2 支着法就开始缩，缩得也更狠 */
      if (depth >= 2 && moveCount >= 2 && !isCap && !gives && !chk) {
        red = 1;
        if (moveCount >= 4) red++;
        if (moveCount >= 9 && depth >= 5) red++;
        if (red > depth - 1) red = depth - 1;
      }
#elif defined(LMR_LOG)
      /* 经典对数缩减：靠后的静着按 log(depth)·log(idx) 缩，比固定台阶更平滑 */
      if (depth >= 3 && moveCount >= 3 && !isCap && !gives && !chk) {
        red = (int)(0.8 + std::log((double)depth) * std::log((double)moveCount) / 2.1);
        if (red > depth - 1) red = depth - 1;
        if (red < 0) red = 0;
      }
#else
      if (depth >= 3 && moveCount >= 3 && !isCap && !gives && !chk) {
        red = 1;
        if (moveCount >= 7) red++;
        if (moveCount >= 14 && depth >= 6) red++;
        if (red > depth - 1) red = depth - 1;
      }
#endif
      v = -negamax(depth - 1 - red + ext, -alpha - 1, -alpha, ply + 1, true);
      if (!STOP && v > alpha && red) v = -negamax(depth - 1 + ext, -beta, -alpha, ply + 1, true);
    }
    unmakeMove(mv, u);
    if (STOP) return 0;
    if (v > best) { best = v; bestMove = mv; }
    if (v > alpha) alpha = v;
    if (alpha >= beta) {
      if (!isCap) {
        killers[1][ply] = killers[0][ply];
        killers[0][ply] = mv;
        /* 历史表无上限会随对局时长单调膨胀（int 溢出 + 排序失真），封顶并仍保留相对大小 */
        int &h = historyTbl[mv / 100][mv % 100];
        h += depth * depth;
        if (h > 16384) h = 16384;
      }
#ifdef CM_ORDER
      if (ply > 0 && plyMove[ply - 1]) counterTbl[plyMove[ply - 1]] = mv;
#endif
      break;
    }
    moveCount++;
  }

  int flag;
  if (best >= betaOrig) flag = 1;
  else if (best <= alphaOrig) flag = 2;
  else flag = 0;
  if (abs(best) < MATE - 100) {
    uint64_t k2 = k;
    TTEntry *ee = ttProbe(k2);
#ifdef TT_DEPTH_PREF
    /* 深度优先：新条目比旧条目浅太多时不覆盖，保住深搜索结果 */
    const bool replace = (ee->key == k2) ? (ee->depth <= depth)
                                         : (ee->key == 0 || ee->depth < (uint8_t)(depth + 3));
    if (replace) {
#else
    if (ee->key != k2 || ee->depth <= depth) {
#endif
      ee->key = k2; ee->score = (int16_t)best; ee->depth = (uint8_t)depth;
      ee->flag = (uint8_t)flag; ee->mv = (uint16_t)bestMove;
    }
  }
  return best;
}

static int rootBest = 0;
static int searchRoot(int maxDepth, int ms) {
  STOP = false;
  NODES = 0;
  for (int i = 0; i < 90; i++)
    for (int j = 0; j < 90; j++) historyTbl[i][j] /= 2;
  DEADLINE = chrono::steady_clock::now() + chrono::milliseconds(ms > 0 ? ms : 86400000);

  int lm[128];
  int n = genLegal(us, lm);
  if (!n) return 0;
  int order[128], rscore[128];
  for (int i = 0; i < n; i++) { order[i] = lm[i]; rscore[i] = 0; }
  rootBest = order[0];
  int bestScore = 0;
  auto t0 = chrono::steady_clock::now();

#if defined(FLASH)
  static const int ASP_DELTA = 25, ASP_MIN_D = 5;   // 窄窗 + 提前开窗，省重搜
#else
  static const int ASP_DELTA = 45, ASP_MIN_D = 6;
#endif
  for (int d = 1; d <= maxDepth; d++) {
    int delta = ASP_DELTA;
    int widen = 0;
    int alpha = (d >= ASP_MIN_D) ? bestScore - delta : -MATE;
    int beta = (d >= ASP_MIN_D) ? bestScore + delta : MATE;
    int best = -MATE, bestMv = 0;
    while (true) {
      best = -MATE; bestMv = 0;
      int a = alpha;
      for (int i = 0; i < n; i++) {
        int mv = order[i];
        Undo u; makeMove(mv, u);
#ifdef CHKEXT
        int ext = inCheck(us) ? 1 : 0;
#else
        int ext = inCheck(other(us)) ? 1 : 0;
#endif
        int v;
        if (i == 0) v = -negamax(d - 1 + ext, -beta, -a, 1, true);
        else {
          v = -negamax(d - 1 + ext, -a - 1, -a, 1, true);
          if (!STOP && v > a) v = -negamax(d - 1 + ext, -beta, -a, 1, true);
        }
        unmakeMove(mv, u);
        if (STOP) break;
        rscore[i] = v;
        if (v > best) { best = v; bestMv = mv; }
        if (v > a) a = v;
        if (STOP) break;
      }
      if (STOP) break;
      /* 期望窗口最多放宽 4 次；仍未收敛就直接开全窗口，避免在极端局面上反复重搜。 */
      if (d >= ASP_MIN_D && ++widen <= 4 && (best <= alpha || best >= beta)) {
        if (best <= alpha) alpha = max(-MATE, alpha - delta);
        if (best >= beta) beta = min(MATE, beta + delta);
        delta *= 2;
        if (widen == 4) { alpha = -MATE; beta = MATE; }
        continue;
      }
      break;
    }
    if (STOP) break;
    // 下一层按本层分数重排
    std::pair<int, int> ro[128];
    for (int i = 0; i < n; i++) ro[i] = {rscore[i], order[i]};
    std::sort(ro, ro + n, [](const std::pair<int, int> &a, const std::pair<int, int> &b) {
      return a.first != b.first ? a.first > b.first : a.second < b.second;
    });
    for (int i = 0; i < n; i++) { rscore[i] = ro[i].first; order[i] = ro[i].second; }
    rootBest = bestMv;
    bestScore = best;
    auto now = chrono::steady_clock::now();
    long long ms = chrono::duration_cast<chrono::milliseconds>(now - t0).count();
    cerr << "info depth " << d << " score " << best << " nodes " << NODES
         << " time " << ms << " nps " << (ms > 0 ? (NODES * 1000 / ms) : 0) << endl;
    if (abs(best) > MATE - 100) break;
  }
  (void)bestScore;
  return rootBest;
}

// ---------------------------------------------------------------- UCI
static int parseMove(const string &u) {
  if (u.size() < 4) return 0;
  int fx0 = u[0] - 'a', fy0 = 9 - (u[1] - '0');
  int fx1 = u[2] - 'a', fy1 = 9 - (u[3] - '0');
  if (!onBoard(fx0, fy0) || !onBoard(fx1, fy1)) return 0;
  const int from = sqOf(fx0, fy0), to = sqOf(fx1, fy1);
  if (from == to) return 0;              // 原地不动会把棋子从棋盘上抹掉
  return from * 100 + to;
}
static string moveStr(int mv) {
  int f = mv / 100, t = mv % 100;
  string s;
  s += char('a' + fx(f)); s += char('0' + (9 - fy(f)));
  s += char('a' + fx(t)); s += char('0' + (9 - fy(t)));
  return s;
}

/* 应用一条 UCI 着法，非法则原样返回 false 且不动棋盘。
   原实现无条件 makeMove：一旦上游送进 "a1a1" 或反色着法，棋子会被抹掉/复制，
   整个局面从此损坏（表现为后续搜索乱走），这里补上四道检查：
   起点必须有自己的子、终点不能是自己的子、着法必须在合法着法集里、落子后己方不能被将。 */
static bool applyUci(const string &u) {
  int m = parseMove(u);
  if (!m) return false;
  const int f = m / 100, t = m % 100;
  const int p = B[f];
  if (!p || (p > 0) != (us > 0)) return false;
  if (B[t] && (B[t] > 0) == (us > 0)) return false;
  /* 前两条只挡住「走别人的子/吃自己的子」，挡不住几何上非法的着法
     （如士斜着出宫、马蹩腿硬跳）：这类着法若恰好不送将，会把棋盘走坏。 */
  int lm[128];
  int n = genLegal(us, lm);
  bool legal = false;
  for (int i = 0; i < n; i++) if (lm[i] == m) { legal = true; break; }
  if (!legal) return false;
  Undo uu; makeMove(m, uu);
  return true;   // genLegal 已保证落子后不被将
}

static long long perft(int depth) {
  if (depth == 0) return 1;
  int lm[128];
  int n = genLegal(us, lm);
  if (depth == 1) return n;
  long long tot = 0;
  for (int i = 0; i < n; i++) {
    Undo u; makeMove(lm[i], u);
    tot += perft(depth - 1);
    unmakeMove(lm[i], u);
  }
  return tot;
}

int main(int argc, char **argv) {
  (void)argc; (void)argv;
  initZobrist();
  setFen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w");
  ttClear();

  string line;
  while (getline(cin, line)) {
    if (line.empty()) continue;
    istringstream is(line);
    string cmd; is >> cmd;
    if (cmd == "uci") {
#if defined(CATCHESS_FLASH) || defined(FLASH)
      /* 边缘计算版：4MB 置换表 + 激进裁剪，棋力换资源 */
      cout << "id name CatChess-V1.0-flash" << endl;
#elif defined(CATCHESS_FORMAL) || defined(CATCHESS_V11)
      /* 1.0 正式版：192/96 价值头 + 残局数据 + 搜索层四项修正 */
      cout << "id name CatChess-V1.0-pro" << endl;
#elif defined(USE_MLP) && defined(MLP_EG)
      /* 1.0 候选版（rc1）：与正式版同一份评估，但无搜索层修正 */
      cout << "id name CatChess-V1.0-pro-rc1" << endl;
#elif defined(USE_MLP)
      cout << "id name CatChess-v2.0" << endl;
#else
      cout << "id name CatChess-v1.0pro-preview" << endl;
#endif
      cout << "id author GeoLite / CatChess" << endl;
      cout << "uciok" << endl;
    } else if (cmd == "isready") {
      cout << "readyok" << endl;
    } else if (cmd == "ucinewgame") {
      ttClear();
      memset(killers, 0, sizeof(killers));
      memset(historyTbl, 0, sizeof(historyTbl));
      memset(counterTbl, 0, sizeof(counterTbl));   // 反制表与走子栈跨局残留会污染下一局排序
      memset(plyMove, 0, sizeof(plyMove));
      histLen = 0;
      keyHist[0] = KEY;
    } else if (cmd == "position") {
      /* 逐 token 解析，不再依赖 " moves " 这个精确子串：
         多空格/Tab、FEN 后直接跟 moves、或只有 startpos 都能正确处理。 */
      vector<string> tok;
      string w;
      while (is >> w) tok.push_back(w);
      if (!tok.empty()) {
        size_t i = 0;
        if (tok[0] == "fen") {
          string fen;
          for (i = 1; i < tok.size() && tok[i] != "moves"; i++) {
            if (!fen.empty()) fen += ' ';
            fen += tok[i];
          }
          if (!setFen(fen)) { cerr << "info string bad fen ignored" << endl; continue; }
        } else {
          setFen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w");
          i = 1;
        }
        if (i < tok.size() && tok[i] == "moves") {
          for (++i; i < tok.size(); i++) {
            if (!applyUci(tok[i])) { cerr << "info string illegal move " << tok[i] << endl; break; }
          }
        }
      }
    } else if (cmd == "go") {
      int ms = 0, depth = 64;
      bool hasMs = false, hasDepth = false, hasClock = false, infinite = false;
      long long wtime = -1, btime = -1, winc = 0, binc = 0;
      long long nlimit = 0;
      string t;
      while (is >> t) {
        /* 参数缺失（"go movetime" 后面没数字）时流会进入失败位，ms 保持 0；
           若直接当成 0 时限会退化成 24 小时。这里给安全默认值。 */
        if (t == "movetime") {
          if (!(is >> ms) || ms <= 0) ms = 30;
          hasMs = true;
        } else if (t == "depth") {
          if (!(is >> depth)) depth = 8;
          hasDepth = true;
        }
        else if (t == "wtime") { is >> wtime; hasClock = true; }
        else if (t == "btime") { is >> btime; hasClock = true; }
        else if (t == "winc") is >> winc;
        else if (t == "binc") is >> binc;
        else if (t == "infinite") infinite = true;
        else if (t == "nodes") { if (!(is >> nlimit) || nlimit <= 0) nlimit = 100000; }
      }
      if (depth < 1) depth = 1;
      if (depth > MAXPLY - 8) depth = MAXPLY - 8;   // 深过 MAXPLY 的迭代没有意义
      if (!hasMs) {
        const long long left = (us == RED ? wtime : btime);
        const long long inc = (us == RED ? winc : binc);
        if (hasClock) {
          /* 剩余时间按 40 步均摊，再加 0.8 倍增量；单步不超过剩余 1/3，下限 30ms。
             没有这一步，GUI 发 go wtime/btime 时引擎会搜到深度上限（几分钟）才动。
             剩余时间已经归零时也只给 30ms，不能退化成默认 1 秒而直接超时判负。 */
          long long alloc = 30;
          if (left > 0) {
            alloc = left / 40 + inc * 4 / 5;
            if (alloc < left / 3) { /* 保留均摊值 */ }
            else alloc = left / 3;
            if (alloc < 30) alloc = 30;
          }
          ms = (int)alloc;
        } else if (infinite) {
          ms = 30000;        // 搜索期间读不到 stdin，stop 无法生效，给硬上限
        } else if (!hasDepth) {
          /* 等节点口径必须只受节点约束：个别局面 4 万节点要跑近 1 秒，
             若再叠一个 1 秒默认时限，机器负载一变结果就变（已踩过）。 */
          ms = (nlimit > 0) ? 86400000 : 1000;
        }
      }
      NODE_LIMIT = nlimit;
      int mv = searchRoot(depth, ms);
      NODE_LIMIT = 0;
      cout << "bestmove " << (mv ? moveStr(mv) : "0000") << endl;
    } else if (cmd == "perft") {
      int d = 1; is >> d;
      auto t0 = chrono::steady_clock::now();
      long long v = perft(d);
      auto t1 = chrono::steady_clock::now();
      cerr << "perft " << d << " = " << v << " in "
           << chrono::duration_cast<chrono::milliseconds>(t1 - t0).count() << "ms" << endl;
      cout << v << endl;
    } else if (cmd == "eval") {
      cout << evalPos(us) << endl;
    } else if (cmd == "evalspeed") {
      /* 调试用：拆分评估开销（特征提取 vs 前向），决定优化方向 */
      int N = 200000;
      float f[45];
      auto t0 = chrono::steady_clock::now();
      for (int i = 0; i < N; i++) { geo::feats45(B, us, f); }
      auto t1 = chrono::steady_clock::now();
      float in[46];
      for (int i = 0; i < 45; i++) in[i] = f[i];
      in[45] = 0.f;
      float acc = 0;
#if defined(USE_MLP)
      for (int i = 0; i < N; i++) { acc += mlpval::score(in); }
#else
      (void)in;
#endif
      auto t2 = chrono::steady_clock::now();
      auto d1 = chrono::duration_cast<chrono::nanoseconds>(t1 - t0).count() / N;
      auto d2 = chrono::duration_cast<chrono::nanoseconds>(t2 - t1).count() / N;
      cout << "feats45 " << d1 << "ns  mlp " << d2 << "ns  plane ";
      auto t3 = chrono::steady_clock::now();
      volatile int s = 0;
      int acc2 = 0;
      for (int i = 0; i < N; i++) { acc2 += evalPosPlane(us); if (i == N - 1) s = acc2; }
      (void)s;
      auto t4 = chrono::steady_clock::now();
      cout << chrono::duration_cast<chrono::nanoseconds>(t4 - t3).count() / N << "ns  (acc " << (int)acc << " " << s << ")";
      /* evalPos 总耗时：每轮换一个着法再撤销，避免编译器把纯函数提出循环 */
      int lmv[128];
      int nl = genLegal(us, lmv);
      long long acc3 = 0;
      auto t5 = chrono::steady_clock::now();
      /* 无合法着法（被将死）时 nl=0，i % nl 是除零；该局面直接跳过计时 */
      if (nl > 0) {
        for (int i = 0; i < N; i++) {
          int mv = lmv[i % nl];
          Undo u; makeMove(mv, u);
          acc3 += evalPos(us);
          unmakeMove(mv, u);
        }
      }
      auto t6 = chrono::steady_clock::now();
      cout << "  evalPos " << chrono::duration_cast<chrono::nanoseconds>(t6 - t5).count() / N
           << "ns (含 make/unmake, acc " << (int)(acc3 & 7) << ")" << endl;
    } else if (cmd == "planeeval") {
      /* 调试用：只输出平面评估（LW+WF），供 Python 侧特征复刻对齐校验 */
      cout << evalPosPlane(us) << endl;
    } else if (cmd == "featdump") {
      /* 调试用：45 维几何特征 + 平面分，一行空格分隔，供 Python 逐维对齐 */
      float f[45];
      geo::feats45(B, us, f);
      for (int i = 0; i < 45; i++) cout << f[i] << (i == 44 ? '\n' : ' ');
      cout << evalPosPlane(us) << endl;
    } else if (cmd == "fen" || cmd == "d") {
      cout << fenOf() << endl;
      for (int y = 0; y < 10; y++) {
        for (int x = 0; x < 9; x++) {
          int p = B[sqOf(x, y)];
          char c = p ? "?KABNRCP"[abs(p)] : '.';   // 大写=红、小写=黑（原来两边都是小写，看不出颜色）
          if (p < 0) c = (char)tolower(c);
          cout << c;
        }
        cout << endl;
      }
    } else if (cmd == "quit") {
      break;
    }
  }
  return 0;
}
