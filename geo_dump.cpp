// 对拍工具：从 stdin 读 FEN（每行一个），输出 45 维特征与树评分。
// 用法：geo_dump.exe < fens.txt
#include <cstdio>
#include <cstring>
#include <string>
#include <iostream>
#include <cstdint>
#include "geo_eval.h"

/* FEN → B[90]。红大写为正，y=0 为黑底线。返回是否成功。 */
static bool parseFen(const std::string& fen, int8_t* B) {
  memset(B, 0, 90);
  int x = 0, y = 0;
  size_t i = 0;
  for (; i < fen.size() && fen[i] != ' '; i++) {
    char c = fen[i];
    if (c == '/') { x = 0; y++; continue; }
    if (c >= '1' && c <= '9') { x += c - '0'; continue; }
    int t;
    switch (c | 32) {
      case 'k': t = 1; break; case 'a': t = 2; break; case 'b': t = 3; break;
      case 'n': t = 4; break; case 'r': t = 5; break; case 'c': t = 6; break;
      case 'p': t = 7; break;
      default: return false;
    }
    bool red = (c >= 'A' && c <= 'Z');
    if (x > 8 || y > 9) return false;
    B[y * 9 + x] = (int8_t)(red ? t : -t);
    x++;
  }
  // 走子方
  while (i < fen.size() && fen[i] == ' ') i++;
  return y <= 9;
}

static int sideOf(const std::string& fen) {
  size_t sp = fen.find(' ');
  if (sp == std::string::npos) return 1;
  while (sp < fen.size() && fen[sp] == ' ') sp++;
  return (sp < fen.size() && (fen[sp] == 'b' || fen[sp] == 'B')) ? -1 : 1;
}

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.size() < 5) continue;
    int8_t B[90];
    if (!parseFen(line, B)) { printf("ERR\n"); continue; }
    int side = sideOf(line);
    float f[GEO_DIM];
    geo::feats45(B, side, f);
    float v = geo::treeScore(f);
    printf("%.4f", v);
    for (int i = 0; i < GEO_DIM; i++) printf(" %.4f", f[i]);
    printf("\n");
  }
  return 0;
}
