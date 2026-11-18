// MLP 价值头的前向：46 维输入（45 几何 + 平面分/200）→ 192 → 96 → 1。
//
// 两条实现，编译期由 -DMLP_INT8 选择：
//   float：权重 mlp46.h（float32），AVX2 整段点积。
//   int8 ：权重 mlp46_i8.h（逐行对称量化），激活按局面现算 uint8 非对称量化，
//          整数点积走 AVX-512 VNNI / AVX2 maddubs / 标量三条路径。
//
// int8 的零点处理：z 的量化是 z ≈ AZ·q + lo（非对称，lo 为逐局面最小值），
// 所以 dot(z, w) ≈ AZ·dot(q, w) + lo·Σw；第二项用预先算好的 SUM1 行和补回来，
// 不需要额外的点积。
#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>
#if defined(__AVX2__)
#include <immintrin.h>
#endif

#if defined(MLP_INT8)
#include "mlp46_i8.h"
#else
#include "mlp46.h"
#endif

namespace mlpval {

#if !defined(MLP_INT8)

static inline float dotN(const float* a, const float* b, int n) {
#if defined(__AVX2__)
  __m256 s0 = _mm256_setzero_ps(), s1 = _mm256_setzero_ps();
  for (int i = 0; i < n; i += 16) {
    s0 = _mm256_add_ps(s0, _mm256_mul_ps(_mm256_loadu_ps(a + i), _mm256_loadu_ps(b + i)));
    s1 = _mm256_add_ps(s1, _mm256_mul_ps(_mm256_loadu_ps(a + i + 8), _mm256_loadu_ps(b + i + 8)));
  }
  __m256 u = _mm256_add_ps(s0, s1);
  __m128 lo = _mm256_castps256_ps128(u);
  __m128 hi = _mm256_extractf128_ps(u, 1);
  __m128 v = _mm_add_ps(lo, hi);
  v = _mm_hadd_ps(v, v);
  v = _mm_hadd_ps(v, v);
  return _mm_cvtss_f32(v);
#else
  float s = 0;
  for (int i = 0; i < n; i++) s += a[i] * b[i];
  return s;
#endif
}

/* 输入：46 维原始特征（未标准化）。输出：走子方视角 cp。 */
static inline float score(const float* in) {
  float z[mlp::STRIDE];
  for (int i = 0; i < mlp::DIM; i++) {
    float t = (in[i] - mlp::MEAN[i]) / mlp::STD[i];
    if (t > 8.f) t = 8.f; else if (t < -8.f) t = -8.f;
    z[i] = t;
  }
  for (int i = mlp::DIM; i < mlp::STRIDE; i++) z[i] = 0.f;

  float h1[mlp::H1];
  for (int j = 0; j < mlp::H1; j++) {
    float s = mlp::B1[j] + dotN(z, mlp::W1[j], mlp::STRIDE);
    h1[j] = s > 0.f ? s : 0.f;
  }
  float acc = mlp::B3;
  for (int j = 0; j < mlp::H2; j++) {
    float s = mlp::B2[j] + dotN(h1, mlp::W2[j], mlp::H1);
    if (s > 0.f) acc += s * mlp::W3[j];
  }
  return acc;
}

#else  // ===================== int8 量化路径 =====================

/* 激活量化上限：VNNI 的 dpbusd 直接累加到 int32，可以用满 0..255；
   AVX2 的 maddubs 把相邻两个乘积加进 int16，255×127×2 = 64770 会溢出饱和，
   所以只能到 127。两条路径共用同一份权重表，只有激活尺度不同。 */
#if defined(__AVX512VNNI__) && defined(__AVX512BW__)
static const int AMAX = 255;
#else
static const int AMAX = 127;
#endif

/* 整数点积，int32 精确累加。乘积累加不溢出（最大 192×255×127 ≈ 6.2e6），
   也没有饱和指令参与，所以 AVX2 与标量路径逐位一致（900 局面实测差 0）。
   VNNI 路径的激活上限放到 255，精度略高于这两条，实测平均差 10cp。 */
static inline int32_t dotI8(const signed char* a, const signed char* b, int n) {
#if defined(__AVX512VNNI__) && defined(__AVX512BW__)
  __m512i acc = _mm512_setzero_si512();
  for (int i = 0; i < n; i += 64) {
    __m512i va = _mm512_loadu_si512((const void*)(a + i));
    __m512i vb = _mm512_loadu_si512((const void*)(b + i));
    acc = _mm512_dpbusd_epi32(acc, va, vb);   // a 按无符号字节，b 按有符号字节
  }
  return _mm512_reduce_add_epi32(acc);
#elif defined(__AVX2__)
  __m256i acc = _mm256_setzero_si256();
  const __m256i ones = _mm256_set1_epi16(1);
  for (int i = 0; i < n; i += 32) {
    __m256i va = _mm256_loadu_si256((const __m256i*)(a + i));
    __m256i vb = _mm256_loadu_si256((const __m256i*)(b + i));
    __m256i p = _mm256_maddubs_epi16(va, vb);                  // 两两相加 → 16 个 int16
    acc = _mm256_add_epi32(acc, _mm256_madd_epi16(p, ones));    // 再两两相加 → 8 个 int32
  }
  __m128i s = _mm_add_epi32(_mm256_castsi256_si128(acc),
                            _mm256_extracti128_si256(acc, 1));
  s = _mm_hadd_epi32(s, s);
  s = _mm_hadd_epi32(s, s);
  return _mm_cvtsi128_si32(s);
#else
  int32_t s = 0;
  for (int i = 0; i < n; i++) s += (int32_t)(unsigned char)a[i] * (int32_t)b[i];
  return s;
#endif
}

/* 输入：46 维原始特征（未标准化）。输出：走子方视角 cp。
   与 float 版的结构一一对应，只是每层的点积换成 int8、激活换成 uint8。 */
static inline float score(const float* in) {
  /* 1) 标准化 + 截断到 ±8，顺带求逐局面的取值范围 */
  float z[mlp::DIM];
  float lo = 1e30f, hi = -1e30f;
  for (int i = 0; i < mlp::DIM; i++) {
    float t = (in[i] - mlp::MEAN[i]) / mlp::STD[i];
    if (t > 8.f) t = 8.f; else if (t < -8.f) t = -8.f;
    z[i] = t;
    if (t < lo) lo = t;
    if (t > hi) hi = t;
  }
  /* 2) 非对称量化到 [0, AMAX]。逐局面取范围比固定 ±8 细 3 倍（实测噪声 14.5→4.6cp） */
  float AZ = (hi - lo) * (1.f / (float)AMAX);
  if (!(AZ > 1e-6f)) AZ = 1e-6f;
  const float invAZ = 1.f / AZ;
  signed char qz[mlp::PAD1];
  for (int i = 0; i < mlp::DIM; i++) {
    int v = (int)std::lrintf((z[i] - lo) * invAZ);
    if (v < 0) v = 0; else if (v > AMAX) v = AMAX;
    qz[i] = (signed char)v;
  }
  for (int i = mlp::DIM; i < mlp::PAD1; i++) qz[i] = 0;

  /* 3) 第一层：pre = dot·(AZ·S1) + B1 + lo·SUM1，然后 ReLU */
  float h1[mlp::H1];
  float hmax = 0.f;
  for (int j = 0; j < mlp::H1; j++) {
    int32_t d = dotI8(qz, mlp::Q1[j], mlp::PAD1);
    float s = (float)d * (AZ * mlp::S1[j]) + mlp::B1[j] + lo * mlp::SUM1[j];
    if (!(s > 0.f)) s = 0.f;          // ReLU
    h1[j] = s;
    if (s > hmax) hmax = s;
  }
  /* 4) h1 量化到 [0, AMAX]，尺度取本行最大值 */
  float AH = hmax * (1.f / (float)AMAX);
  if (!(AH > 1e-6f)) AH = 1e-6f;
  const float invAH = 1.f / AH;
  signed char qh[mlp::PAD2];
  for (int j = 0; j < mlp::H1; j++) {
    int v = (int)std::lrintf(h1[j] * invAH);
    if (v < 0) v = 0; else if (v > AMAX) v = AMAX;
    qh[j] = (signed char)v;
  }
  /* 5) 第二层 + 输出层（W3 保持 float，只有 96 个系数） */
  float acc = mlp::B3;
  for (int j = 0; j < mlp::H2; j++) {
    int32_t d = dotI8(qh, mlp::Q2[j], mlp::PAD2);
    float s = (float)d * (AH * mlp::S2[j]) + mlp::B2[j];
    if (s > 0.f) acc += s * mlp::W3[j];
  }
  return acc;
}

#endif

}  // namespace mlpval
