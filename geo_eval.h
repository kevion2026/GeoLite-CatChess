// 45 维几何树的 C++ 落地（与 engine3d.js 的 geometry/treeScore 严格同构）
//
// 层次：
//   B[90]（有符号子力，红正黑负，sq=y*9+x，y=0 黑底线）
//     → tokensOf：每个子一枚令牌，按走子方镜像归一化坐标 + 兵种权重
//     → 三空间坐标（coords3a/3b/3c：邻域 / 共线 / 中距同兵种）
//     → 每空间加权质心 + 协方差主轴（解析特征分解）+ 残差 rho   ⇒ 21 维
//     → 每空间形特征（密度/延伸/斜率）                            ⇒ +9
//     → matFeats（子力结构）                                      ⇒ +9
//     → threatFeats（九宫威胁/护子/边线/可走格）                    ⇒ +6
//     = 45 维 → 标准化 → 64 专家 RBF 门控 → 局部线性回归 → cp
//
// 所有数值口径对齐 JS：特征用 double，z 与核权重用 float（JS 里是 Float32Array），
// 累加用 double。这样两端在同一局面上差异 < 1cp。
#pragma once
#include <cmath>
#include <cstring>
#include <cstdint>
#if defined(__AVX2__)
#include <immintrin.h>
#endif

#include "geo45.h"

namespace geo {

static const int W = 9;
static const int RED = 1, BLACK = -1;
enum { EMPTY = 0, KING = 1, ADVISOR = 2, ELEPHANT = 3, HORSE = 4, ROOK = 5, CANNON = 6, PAWN = 7 };

// 令牌权重与价值表：必须与 JS 的 ROLE_W / VALUE / MAT_V 完全一致
static const float ROLE_W[8] = {0.f, 1.40f, 0.80f, 0.85f, 1.00f, 1.25f, 1.10f, 0.95f};
static const float VALUE[8] = {0.f, 1000.f, 300.f, 300.f, 550.f, 1100.f, 580.f, 180.f};
static const int MAT_V[8] = {0, 0, 100, 100, 200, 450, 230, 40};

static const int ORTHO[4][2] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
static const int HORSE_MV[8][4] = {
  {1, 2, 0, 1}, {-1, 2, 0, 1}, {1, -2, 0, -1}, {-1, -2, 0, -1},
  {2, 1, 1, 0}, {2, -1, 1, 0}, {-2, 1, -1, 0}, {-2, -1, -1, 0}
};

static inline bool inBoard(int x, int y) { return x >= 0 && x < W && y >= 0 && y < 10; }
static inline int sqOf(int x, int y) { return y * W + x; }

static inline int findKing(const int8_t* B, int side) {
  for (int s = 0; s < 90; s++) if (B[s] == KING * side) return s;
  return -1;
}

/* 该格是否被 by 方攻击——与 JS attacked() 逐行同构 */
static bool attacked(const int8_t* B, int s, int by) {
  const int x = s % W, y = s / W;
  /* 四个方向各扫一遍就够：第一个子判车/将，第二个子判炮（炮恰好隔一子）。
     原实现分两轮扫同一方向（先车后将、再炮），合并后省掉一半射线读取。 */
  for (int d = 0; d < 4; d++) {
    int nx = x + ORTHO[d][0], ny = y + ORTHO[d][1], step = 1, seen = 0;
    while (inBoard(nx, ny)) {
      int q = B[sqOf(nx, ny)];
      if (q) {
        const bool isBy = ((q > 0 ? RED : BLACK) == by);
        const int t = q > 0 ? q : -q;
        if (seen == 0) {
          if (isBy && (t == ROOK || (t == KING && step == 1))) return true;
          seen = 1;                       // 这枚子充当炮架
        } else {
          if (isBy && t == CANNON) return true;
          break;
        }
      }
      nx += ORTHO[d][0]; ny += ORTHO[d][1]; step++;
    }
  }
  for (int k = 0; k < 8; k++) {
    int sx = x - HORSE_MV[k][0], sy = y - HORSE_MV[k][1];
    if (!inBoard(sx, sy)) continue;
    int q = B[sqOf(sx, sy)];
    if (q && (q > 0 ? RED : BLACK) == by && (q > 0 ? q : -q) == HORSE) {
      int gx = sx + HORSE_MV[k][2], gy = sy + HORSE_MV[k][3];
      if (inBoard(gx, gy) && B[sqOf(gx, gy)] == 0) return true;
    }
  }
  int cx[3], cy[3];
  if (by == RED) { cx[0] = x; cy[0] = y + 1; }
  else { cx[0] = x; cy[0] = y - 1; }
  cx[1] = x - 1; cy[1] = y; cx[2] = x + 1; cy[2] = y;
  for (int i = 0; i < 3; i++) {
    if (!inBoard(cx[i], cy[i])) continue;
    int q = B[sqOf(cx[i], cy[i])];
    if (q && (q > 0 ? RED : BLACK) == by && (q > 0 ? q : -q) == PAWN) return true;
  }
  return false;
}

// 快速指数：range reduction（x = n·ln2 + r）+ 5 阶多项式 + 指数位拼接。
// 相对误差 ~1e-6，与 libm expf 在同一次评估里的差异 < 0.01cp，但快 3~4 倍；
// 96 次形特征核 + 64 次门控核是评估里最大的单项开销。
static inline float fastExp(float x) {
  if (x < -20.f) return 0.f;
  const float t = x * 1.44269504f;
  const float n = std::floor(t + 0.5f);
  const float r = x - n * 0.69314718f;
  float p = 1.f + r * (1.f + r * (0.5f + r * (0.16666667f + r * (0.04166667f + r * 0.00833333f))));
  union { float f; int i; } u;
  u.i = ((int)n + 127) << 23;
  return p * u.f;
}

// ---------------------------------------------------------------- 令牌
struct Tok {
  float w;
  float c[3];   // 当前空间的坐标
  int t;        // 兵种
  int s;        // 棋盘格
};

// 三空间坐标按 [空间][槽位][3] 存放
static inline const float* xyzOf(int space, int slot) { return &GEO_XYZ[(space * GEO_NVEC + slot) * 3]; }

/* 令牌生成：与 JS tokensOf 同构。返回令牌数，输出每个令牌的 (role,type,bx,by) 槽位。 */
static int tokensOf(const int8_t* B, int side, int* slotOut, float* wOut, int* tOut, int* sOut) {
  int n = 0;
  const int flip = (side == BLACK);
  for (int s = 0; s < 90; s++) {
    int p = B[s];
    if (!p) continue;
    int x = s % W, y = s / W;
    int bx = flip ? (W - 1 - x) : x;
    int by = flip ? (9 - y) : y;
    int role = ((p > 0 ? RED : BLACK) == side) ? 0 : 1;   // 0=己方 S, 1=对方 O
    int t = p > 0 ? p : -p;
    float w = ROLE_W[t];
    // 过河兵加权：crossed(y, sside(p)) —— 按该子自己的阵营判断
    int ps = (p > 0 ? RED : BLACK);
    bool crossed = (ps == RED) ? (y <= 4) : (y >= 5);
    if (crossed) w *= 1.15f;
    int slot = GEO_SLOT[(role * 7 + (t - 1)) * 90 + by * 9 + bx];
    if (slot < 0) continue;      // 没有坐标的令牌直接丢弃（与 JS 的过滤一致）
    slotOut[n] = slot; wOut[n] = w; tOut[n] = t; sOut[n] = s;
    n++;
  }
  return n;
}

// ---------------------------------------------------------------- 三空间拟合
/* 加权质心 + 协方差主轴（Smith 解析解法），返回 rho。
   单遍扫描同时累加 0/1/2 阶加权矩；残差不再逐点算——
   点云垂直于主轴的总方差 = tr(Σ) − λmax（另两个特征值之和），与「逐点 perp² 求和」数学等价，
   但省掉一整遍 32 点遍历，这是 45 维特征里最贵的单项。 */
static double fitSpace(const float (*c3)[3], const float* wt, int n, float* st7) {
  double sw = 0, sx = 0, sy = 0, sz = 0;
  double sxx = 0, syy = 0, szz = 0, sxy = 0, sxz = 0, syz = 0;
  for (int i = 0; i < n; i++) {
    const double w = wt[i];
    const double x = c3[i][0], y = c3[i][1], z = c3[i][2];
    sw += w;
    sx += w * x; sy += w * y; sz += w * z;
    sxx += w * x * x; syy += w * y * y; szz += w * z * z;
    sxy += w * x * y; sxz += w * x * z; syz += w * y * z;
  }
  if (sw <= 0) {
    st7[0] = st7[1] = st7[2] = 0.f; st7[3] = 1.f; st7[4] = st7[5] = 0.f; st7[6] = 0.f;
    return 0;
  }
  const double iw = 1.0 / sw;
  const double cx = sx * iw, cy = sy * iw, cz = sz * iw;
  double a11 = sxx * iw - cx * cx;
  double a22 = syy * iw - cy * cy;
  double a33 = szz * iw - cz * cz;
  double a12 = sxy * iw - cx * cy;
  double a13 = sxz * iw - cx * cz;
  double a23 = syz * iw - cy * cz;

  double v[3];
  double lamMax;
  const double p1 = a12 * a12 + a13 * a13 + a23 * a23;
  if (p1 < 1e-18) {
    if (a11 >= a22 && a11 >= a33) { v[0] = 1; v[1] = 0; v[2] = 0; lamMax = a11; }
    else if (a22 >= a33) { v[0] = 0; v[1] = 1; v[2] = 0; lamMax = a22; }
    else { v[0] = 0; v[1] = 0; v[2] = 1; lamMax = a33; }
  } else {
    const double q = (a11 + a22 + a33) / 3;
    const double p2 = (a11 - q) * (a11 - q) + (a22 - q) * (a22 - q) + (a33 - q) * (a33 - q) + 2 * p1;
    const double p = std::sqrt(p2 / 6);
    const double b11 = (a11 - q) / p, b22 = (a22 - q) / p, b33 = (a33 - q) / p;
    const double b12 = a12 / p, b13 = a13 / p, b23 = a23 / p;
    const double det = b11 * (b22 * b33 - b23 * b23) - b12 * (b12 * b33 - b23 * b13) + b13 * (b12 * b23 - b22 * b13);
    double r = det / 2;
    if (r > 1) r = 1; else if (r < -1) r = -1;
    const double phi = std::acos(r) / 3;
    const double e1 = q + 2 * p * std::cos(phi);
    lamMax = e1;
    const double x1 = a11 - e1, x2 = a22 - e1, x3 = a33 - e1;
    const double c1[3] = {a12 * a23 - a13 * x2, a13 * a12 - x1 * a23, x1 * x2 - a12 * a12};
    const double c2[3] = {a12 * x3 - a13 * a23, a13 * a13 - x1 * x3, x1 * a23 - a12 * a13};
    const double cb[3] = {x2 * x3 - a23 * a23, a23 * a13 - a12 * x3, a12 * a23 - x2 * a13};
    const double* best = c1;
    double bn = c1[0] * c1[0] + c1[1] * c1[1] + c1[2] * c1[2];
    double n2 = c2[0] * c2[0] + c2[1] * c2[1] + c2[2] * c2[2];
    if (n2 > bn) { best = c2; bn = n2; }
    double n3 = cb[0] * cb[0] + cb[1] * cb[1] + cb[2] * cb[2];
    if (n3 > bn) { best = cb; bn = n3; }
    if (bn < 1e-20) { v[0] = v[1] = v[2] = 0.5774; }
    else { double nn = std::sqrt(bn); v[0] = best[0] / nn; v[1] = best[1] / nn; v[2] = best[2] / nn; }
  }
  // 符号规范化：绝对值最大的分量取正
  int idx = 0;
  double amax = std::fabs(v[0]);
  if (std::fabs(v[1]) >= amax) { amax = std::fabs(v[1]); idx = 1; }
  if (std::fabs(v[2]) >= amax) { idx = 2; }
  if (v[idx] < 0) { v[0] = -v[0]; v[1] = -v[1]; v[2] = -v[2]; }

  double tr = a11 + a22 + a33;
  double res = tr - lamMax;
  if (res < 0) res = 0;
  const double rho = std::sqrt(res);
  st7[0] = (float)cx; st7[1] = (float)cy; st7[2] = (float)cz;
  st7[3] = (float)v[0]; st7[4] = (float)v[1]; st7[5] = (float)v[2];
  st7[6] = (float)rho;
  return rho;
}

/* 形特征：密度（高斯核局部聚集）、主轴延伸、主轴斜率。
   注意 state 用的是 double 累加前的 float 值，与 JS 传 state 数组一致。 */
static void shapeOf(const float* st7, const float (*c3)[3], const float* wt, int n, float* out3) {
  const double cx = st7[0], cy = st7[1], cz = st7[2];
  const double vx = st7[3], vy = st7[4], vz = st7[5];
  double sw = 0, dens = 0;
  double pmax = -1e30, pmin = 1e30;
  for (int i = 0; i < n; i++) {
    double w = wt[i];
    sw += w;
    double dx = c3[i][0] - cx, dy = c3[i][1] - cy, dz = c3[i][2] - cz;
    double d2 = dx * dx + dy * dy + dz * dz;
    dens += w * fastExp((float)(-d2 / 1.6));
    double pr = dx * vx + dy * vy + dz * vz;
    if (pr > pmax) pmax = pr;
    if (pr < pmin) pmin = pr;
  }
  const double span = n ? (pmax - pmin) : 0;
  const double denom = std::fabs(vz) > 1e-6 ? std::fabs(vz) : 1e-6;
  double slope = std::hypot(vx, vy) / denom;
  if (slope > 5) slope = 5;
  out3[0] = (float)(dens / (sw > 1e-9 ? sw : 1e-9));
  out3[1] = (float)span;
  out3[2] = (float)slope;
}

// ---------------------------------------------------------------- 子力 / 威胁
static void matFeats(const int8_t* B, int side, float* out9) {
  int own[9] = {0}, opp[9] = {0};
  for (int s = 0; s < 90; s++) {
    int p = B[s];
    if (!p) continue;
    int t = p > 0 ? p : -p;
    int k = (t == PAWN) ? 7 : t;
    int ps = (p > 0 ? RED : BLACK);
    bool crossed = (ps == RED) ? (s / W <= 4) : (s / W >= 5);
    if (ps == side) { own[k]++; if (t == PAWN && crossed) own[0]++; }
    else { opp[k]++; if (t == PAWN && crossed) opp[0]++; }
  }
  int mv = 0, mo = 0;
  for (int k = 2; k <= 7; k++) { mv += MAT_V[k] * own[k]; mo += MAT_V[k] * opp[k]; }
  out9[0] = (float)((mv - mo) / 100.0);
  for (int k = 1; k <= 7; k++) out9[k] = (float)(own[k] - opp[k]);
  out9[8] = (float)(own[0] - opp[0]);
}

static void threatFeats(const int8_t* B, int side, float* out6) {
  const int k = findKing(B, side);
  if (k < 0) { for (int i = 0; i < 6; i++) out6[i] = 0.f; return; }
  const int kx = k % W, ky = k / W;
  int heavy = 0, def = 0, edge = 0, pal = 0, mob = 0;
  double mat = 0;
  for (int s = 0; s < 90; s++) {
    int q = B[s];
    if (!q) continue;
    int x = s % W, y = s / W, t = q > 0 ? q : -q;
    bool own = ((q > 0 ? RED : BLACK) == side);
    mat += (own ? 1 : -1) * (double)VALUE[t];
    int dx = std::abs(x - kx), dy = std::abs(y - ky);
    int mx = dx > dy ? dx : dy;
    if (!own && (t == HORSE || t == ROOK || t == CANNON) && mx <= 2) heavy++;
    if (own && (t == ADVISOR || t == ELEPHANT || t == ROOK) && mx <= 2) def++;
    if (!own && (x == 0 || x == 8) && (side == RED ? y >= 7 : y <= 2)) edge++;
  }
  for (int yy = (ky - 1 > 0 ? ky - 1 : 0); yy <= (ky + 1 < 9 ? ky + 1 : 9); yy++) {
    for (int xx = (kx - 1 > 0 ? kx - 1 : 0); xx <= (kx + 1 < 8 ? kx + 1 : 8); xx++) {
      if (attacked(B, yy * 9 + xx, -side)) pal++;
    }
  }
  for (int d = 0; d < 4; d++) {
    int nx = kx + ORTHO[d][0], ny = ky + ORTHO[d][1];
    bool inPal = inBoard(nx, ny) && (side == RED ? ny >= 7 : ny <= 2);
    if (inPal && B[ny * 9 + nx] == 0 && !attacked(B, ny * 9 + nx, -side)) mob++;
  }
  out6[0] = (float)heavy; out6[1] = (float)def; out6[2] = (float)edge;
  out6[3] = (float)pal;   out6[4] = (float)mob; out6[5] = (float)(mat / 100.0);
}

// ---------------------------------------------------------------- 45 维特征
/* 输出 45 维特征。layers 固定为 0（产品模型的调用口径），只算层 0 状态。 */
static void feats45(const int8_t* B, int side, float* out) {
  int slot[90], tt[90], ss[90];
  float ww[90];
  int n = tokensOf(B, side, slot, ww, tt, ss);
  if (n == 0) {
    /* 退化情形：没有任何令牌带坐标。仍要给出子力/威胁两项，
       与 JS 侧一致（treeScore 对空点云照样拼 matFeats/threatFeats）。 */
    for (int i = 0; i < 30; i++) out[i] = 0.f;
    matFeats(B, side, out + 30);
    threatFeats(B, side, out + 39);
    return;
  }
  /* 三空间坐标一次性取齐：每个空间一份连续数组，后续拟合/形特征都读这块内存，
     避免每空间再重复做槽位查表（GEO_SLOT → GEO_XYZ 是跨 12KB 的随机访问）。 */
  float c3[3][90][3];   // 3.2KB 栈上临时：thread_local 的 TLS 查表比拷贝本身还贵
  for (int i = 0; i < n; i++) {
    const int base = slot[i] * 3;
    for (int sp = 0; sp < 3; sp++) {
      const float* c = &GEO_XYZ[sp * GEO_NVEC * 3 + base];
      c3[sp][i][0] = c[0]; c3[sp][i][1] = c[1]; c3[sp][i][2] = c[2];
    }
  }
  float st7[3][7];
  for (int sp = 0; sp < 3; sp++) {
    fitSpace(c3[sp], ww, n, st7[sp]);         // 层 0 状态：3 空间 × 7 维 = 21
    for (int j = 0; j < 7; j++) out[sp * 7 + j] = st7[sp][j];
  }
  for (int sp = 0; sp < 3; sp++) {            // 形特征 3 空间 × 3 维 = 9
    shapeOf(st7[sp], c3[sp], ww, n, out + 21 + sp * 3);
  }
  matFeats(B, side, out + 30);
  threatFeats(B, side, out + 39);
}

// ---------------------------------------------------------------- RBF 树
/* ‖c_k‖² 只需算一次；JS 侧也是在 prepSeg 里预存的。 */
static inline const float* geoCn2() {
  static float tab[GEO_K];
  static bool init = false;
  if (!init) {
    for (int k = 0; k < GEO_K; k++) {
      const float* ck = &GEO_CN[k * GEO_STRIDE];
      float s = 0;
      for (int i = 0; i < GEO_STRIDE; i++) s += ck[i] * ck[i];
      tab[k] = s;
    }
    init = true;
  }
  return tab;
}
/* 48 维点积：AVX2 八路并行；无 AVX2 时退回标量四累加器。
   48 = 6×8，正好是 AVX2 的整数倍，无需处理尾部。 */
static inline float dot48(const float* a, const float* b) {
#if defined(__AVX2__)
  __m256 s0 = _mm256_mul_ps(_mm256_loadu_ps(a), _mm256_loadu_ps(b));
  __m256 s1 = _mm256_mul_ps(_mm256_loadu_ps(a + 8), _mm256_loadu_ps(b + 8));
  __m256 s2 = _mm256_mul_ps(_mm256_loadu_ps(a + 16), _mm256_loadu_ps(b + 16));
  __m256 s3 = _mm256_mul_ps(_mm256_loadu_ps(a + 24), _mm256_loadu_ps(b + 24));
  __m256 s4 = _mm256_mul_ps(_mm256_loadu_ps(a + 32), _mm256_loadu_ps(b + 32));
  __m256 s5 = _mm256_mul_ps(_mm256_loadu_ps(a + 40), _mm256_loadu_ps(b + 40));
  __m256 t0 = _mm256_add_ps(s0, s1);
  __m256 t1 = _mm256_add_ps(s2, s3);
  __m256 t2 = _mm256_add_ps(s4, s5);
  __m256 u = _mm256_add_ps(_mm256_add_ps(t0, t1), t2);
  __m128 lo = _mm256_castps256_ps128(u);
  __m128 hi = _mm256_extractf128_ps(u, 1);
  __m128 v = _mm_add_ps(lo, hi);
  v = _mm_hadd_ps(v, v);
  v = _mm_hadd_ps(v, v);
  return _mm_cvtss_f32(v);
#else
  float a0 = 0, a1 = 0, a2 = 0, a3 = 0;
  for (int i = 0; i < GEO_STRIDE; i += 4) {
    a0 += a[i] * b[i];
    a1 += a[i + 1] * b[i + 1];
    a2 += a[i + 2] * b[i + 2];
    a3 += a[i + 3] * b[i + 3];
  }
  return (a0 + a1) + (a2 + a3);
#endif
}

/* 标准化 → 64 专家核门控 → 局部线性 → 与全局线性按 lam 融合。单位 cp。 */
static float treeScore(const float* f) {
  float z[GEO_STRIDE];
  float zn = 0;
  for (int i = 0; i < GEO_DIM; i++) {
    float t = (f[i] - GEO_MEAN[i]) / GEO_STD[i];
    z[i] = t;
    zn += t * t;
  }
  for (int i = GEO_DIM; i < GEO_STRIDE; i++) z[i] = 0.f;   // 补齐位保持零

  const float invH2 = 1.f / (2.f * GEO_H * GEO_H * GEO_HSCALE * GEO_HSCALE);
  const float* cn2 = geoCn2();
  float wts[GEO_K];
  float sw = 0, wmax = 0;

  for (int k = 0; k < GEO_K; k++) {
    const float* ck = &GEO_CN[k * GEO_STRIDE];
    float dot = dot48(z, ck);
    float d2 = zn - 2.f * dot + cn2[k];
    if (d2 < 0) d2 = 0;
    float wk = fastExp(-d2 * invH2);
    wts[k] = wk;
    sw += wk;
    if (wk > wmax) wmax = wk;
  }
  if (sw <= 0) sw = 1;
  const float cutoff = wmax * 1e-4f;
  float tree = 0;
  for (int k = 0; k < GEO_K; k++) {
    if (wts[k] < cutoff) continue;
    const float* lw = &GEO_LW[k * GEO_STRIDE];
    tree += wts[k] * (GEO_LB[k] + dot48(lw, z));
  }
  tree /= sw;
  float glob = GEO_GB;
  for (int i = 0; i < GEO_STRIDE; i++) glob += GEO_GW[i] * z[i];
  return GEO_LAM * tree + (1.f - GEO_LAM) * glob;
}

/* 一步到位：棋盘 + 走子方 → cp（走子方视角） */
static inline int evalBoard(const int8_t* B, int side) {
  float f[GEO_DIM];
  feats45(B, side, f);
  float v = treeScore(f);
  return (int)std::lround(v);
}

}  // namespace geo
