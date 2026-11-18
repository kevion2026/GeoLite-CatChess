#!/bin/sh
# 重新编译 C++ 引擎（w64devkit / GCC 16.2）
#   ./build_xq.sh            → CatChess-V1.0-pro.exe  正式版（192/96 + 残局数据 + 搜索层修正）
#   ./build_xq.sh rc1        → CatChess-V1.0-pro-rc1.exe  候选版（无搜索层修正）
#   ./build_xq.sh v21        → CatChess-v2.1.exe  内部编号，与 rc1 同配置
#   ./build_xq.sh v2         → CatChess-v2.0.exe  历史：MLP 64/32，尺度 0.75
#   ./build_xq.sh v1         → CatChess-v1.0pro-preview.exe  历史：几何树 + 平面融合
#   ./build_xq.sh geo        → xq17.exe  纯 45 维几何树
#   ./build_xq.sh geoorder   → xq18.exe  几何树 + line 空间排序先验
#   ./build_xq.sh aug        → xq16.exe  1260 平面 + 8 个手写几何项
#   ./build_xq.sh static     → xq_static.exe 纯平面（无几何）
#   MIX_W=50 ./build_xq.sh v1 → 自定义融合比例
export PATH="$PWD/tools/w64devkit/w64devkit/bin:$PATH"
# w64devkit 的 g++ 需要可写的临时目录，否则报 Permission denied
export TMPDIR="$PWD/.tmpbuild"; export TMP="$TMPDIR"; export TEMP="$TMPDIR"
mkdir -p "$TMPDIR"
FLAGS="-O3 -march=native -ffast-math -std=c++17 -static"
MW="${MIX_W:-65}"
case "$1" in
  geo)      g++ $FLAGS -DUSE_GEO -o xq17.exe xq.cpp && echo "→ xq17.exe（纯 45 维几何树）" ;;
  geoorder) g++ $FLAGS -DUSE_GEO -DUSE_GEO_ORDER -o xq18.exe xq.cpp && echo "→ xq18.exe（几何树 + 排序先验）" ;;
  aug)      g++ $FLAGS -o xq16.exe xq.cpp && echo "→ xq16.exe（平面 + 8 几何）" ;;
  static)   g++ $FLAGS -DUSE_STATIC -o xq_static.exe xq.cpp && echo "→ xq_static.exe（纯平面）" ;;
  v21)      g++ $FLAGS -DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SCALE:-1.0}f -o CatChess-v2.1.exe xq.cpp && echo "→ CatChess-v2.1.exe（内部编号，192/96，尺度 ${SCALE:-1.0}）" ;;
  v2)       g++ $FLAGS -DUSE_GEO -DUSE_MLP -DMLP_SMALL_SCALE -DMLP_SCALE=${SCALE:-0.75}f -o CatChess-v2.0.exe xq.cpp && echo "→ CatChess-v2.0.exe（几何特征 + MLP 价值头，尺度 ${SCALE:-0.75}）" ;;
  v1)       g++ $FLAGS -DUSE_GEO -DMIX_W=$MW -o CatChess-v1.0pro-preview.exe xq.cpp && echo "→ CatChess-v1.0pro-preview.exe（几何树 + 平面融合 MIX_W=$MW）" ;;
  flash)    g++ -O2 -march=native -ffast-math -std=c++17 -static -s -DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SCALE:-1.0}f -DMLP_INT8 -DSEARCH_CONSERVATIVE -DNULL_MAT_GATE -DCHKEXT -DGENLEGAL_FAST -DCLOCK_THROTTLE -DFLASH -DCATCHESS_FLASH -o CatChess-V1.0-flash.exe xq.cpp && echo "→ CatChess-V1.0-flash.exe（边缘计算版，int8 价值头 + 4MB 置换表 + 激进裁剪）" ;;
  flashf32) g++ -O2 -march=native -ffast-math -std=c++17 -static -s -DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SCALE:-1.0}f -DSEARCH_CONSERVATIVE -DNULL_MAT_GATE -DCHKEXT -DGENLEGAL_FAST -DCLOCK_THROTTLE -DFLASH -DCATCHESS_FLASH -o CatChess-V1.0-flash-f32.exe xq.cpp && echo "→ CatChess-V1.0-flash-f32.exe（同上但 float32 权重，A/B 对照用）" ;;
  v10pro|rc1) g++ $FLAGS -DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SCALE:-1.0}f -o CatChess-V1.0-pro-rc1.exe xq.cpp && echo "→ CatChess-V1.0-pro-rc1.exe（候选版，192/96，无搜索层修正）" ;;
  *)        g++ $FLAGS -DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SCALE:-1.0}f -DSEARCH_CONSERVATIVE -DNULL_MAT_GATE -DCHKEXT -DGENLEGAL_FAST -DCLOCK_THROTTLE -DCATCHESS_FORMAL -o CatChess-V1.0-pro.exe xq.cpp && echo "→ CatChess-V1.0-pro.exe（正式版，192/96 + 搜索层修正）" ;;
esac
