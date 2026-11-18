"""打包 CatChess-V1.0-flash（边缘计算版）到 dist/，并生成 UTF-8 文件名的 zip。

Flash = 正式版同一套评估（45 维几何 + MLP 192/96），但价值头量化成 int8
        （权重 112KB → 34KB，前向快 1.7 倍），
        置换表 2^22 → 2^18（64MB → 4MB），
        搜索裁剪整体收紧一档，-O2 -s 压体积。

历代目录/zip 一律不动。不要用 PowerShell 的 Compress-Archive：
它按 GBK 写中文名，解压乱码。
"""
import hashlib
import pathlib
import shutil
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "dist" / "CatChess-V1.0-flash"
ZIP = HERE / "dist" / "CatChess-V1.0-flash.zip"
EXE = "CatChess-V1.0-flash.exe"
MODEL = "model_eg_M.json"

DEFINES = ("-O2 -march=native -ffast-math -std=c++17 -static -s "
           "-DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=1.0f -DMLP_INT8 "
           "-DSEARCH_CONSERVATIVE -DNULL_MAT_GATE -DCHKEXT -DGENLEGAL_FAST "
           "-DCLOCK_THROTTLE -DFLASH -DCATCHESS_FLASH")

FILES = [
    (EXE, EXE),
    ("CatChess-V1.0-flash-README.md", "README.md"),
    ("CatChess-V1.0-flash-架构.md", "CatChess-V1.0-flash-架构.md"),
    ("xq.cpp", "xq.cpp"),
    ("mlp_eval.h", "mlp_eval.h"),
    ("mlp46.h", "mlp46.h"),
    ("mlp46_i8.h", "mlp46_i8.h"),
    ("geo_eval.h", "geo_eval.h"),
    ("geo45.h", "geo45.h"),
    ("linear_weight_aug.h", "linear_weight_aug.h"),
    ("linear_weight_static.h", "linear_weight_static.h"),
    ("export_mlp.py", "export_mlp.py"),
]

BUILD_SH = r'''#!/bin/sh
# CatChess-V1.0-flash 一键重建（边缘计算版）
#   需要 MinGW-w64 的 g++（GCC 9+）。w64devkit 这类绿色包即可：
#     CXX=/path/to/w64devkit/bin/g++ ./build.sh
#
#   ./build.sh                 → CatChess-V1.0-flash.exe（1.1MB，int8 价值头，4MB 置换表）
#   NO_NATIVE=1 ./build.sh     → 不启用 -march=native（老 CPU / 跨机器分发）
#   ./build.sh full            → CatChess-V1.0-pro.exe（正式版，float32 权重，64MB 置换表）
#   ./build.sh f32             → CatChess-V1.0-flash-f32.exe（同上但 float32 权重，用于对照）
set -e
CXX="${CXX:-g++}"
command -v "$CXX" >/dev/null 2>&1 || CXX="$CXX".exe
command -v "$CXX" >/dev/null 2>&1 || {
  echo "找不到编译器：$CXX"
  echo "请安装 MinGW-w64，或用 CXX=/path/to/g++ ./build.sh 指定"
  exit 1
}

# w64devkit 的 g++ 需要可写的临时目录，否则报 Cannot create temporary file。
TMPDIR="$PWD/.tmpbuild"
export TMPDIR
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
mkdir -p "$TMPDIR"

NATIVE=""
[ "${NO_NATIVE:-0}" = "1" ] || NATIVE="-march=native"
SC="${SCALE:-1.0}"
SPEED="-DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SC}f -DSEARCH_CONSERVATIVE \
       -DNULL_MAT_GATE -DCHKEXT -DGENLEGAL_FAST -DCLOCK_THROTTLE"

case "$1" in
  full)  $CXX -O3 $NATIVE -ffast-math -std=c++17 -static $SPEED \
           -DCATCHESS_FORMAL -o CatChess-V1.0-pro.exe xq.cpp \
         && echo "→ CatChess-V1.0-pro.exe（正式版，float32 权重，64MB 置换表）" ;;
  f32)   $CXX -O2 $NATIVE -ffast-math -std=c++17 -static -s $SPEED \
           -DFLASH -DCATCHESS_FLASH -o CatChess-V1.0-flash-f32.exe xq.cpp \
         && echo "→ CatChess-V1.0-flash-f32.exe（float32 权重对照版）" ;;
  *)     $CXX -O2 $NATIVE -ffast-math -std=c++17 -static -s $SPEED -DMLP_INT8 \
           -DFLASH -DCATCHESS_FLASH -o CatChess-V1.0-flash.exe xq.cpp \
         && echo "→ CatChess-V1.0-flash.exe（int8 价值头 + 4MB 置换表 + 激进裁剪）" ;;
esac
'''

SELFCHECK_SH = r'''#!/bin/sh
# CatChess-V1.0-flash 出厂自检
#   ./selfcheck.sh [exe路径]
EXE="${1:-./CatChess-V1.0-flash.exe}"
[ -f "$EXE" ] || { echo "找不到 $EXE"; exit 1; }

OUT=$(printf 'uci\nisready\nperft 1\nperft 2\nperft 3\nperft 4\neval\nposition startpos\ngo depth 6\nquit\n' | "$EXE" 2>&1)
FAIL=0
chk() {
  if printf '%s\n' "$OUT" | grep -q "$1"; then
    echo "  [OK]   $2"
  else
    echo "  [FAIL] $2"
    FAIL=1
  fi
}

echo "== UCI 握手 =="
chk "uciok"                            "uci → uciok"
chk "readyok"                          "isready → readyok"
chk "id name CatChess-V1.0-flash$"     "id name 正确"

echo "== perft（象棋标准值）=="
chk "perft 1 = 44"         "perft 1 = 44"
chk "perft 2 = 1920"       "perft 2 = 1920"
chk "perft 3 = 79666"      "perft 3 = 79666"
chk "perft 4 = 3290240"    "perft 4 = 3290240"

echo "== 搜索 =="
chk "info depth 6"        "到达 depth 6"
chk "bestmove "           "返回 bestmove"

echo "== 评估 =="
EV=$(printf 'position startpos\neval\nquit\n' | "$EXE" 2>/dev/null | tr -dc '0-9-\n' | head -1)
if [ -n "$EV" ]; then echo "  [OK]   开局评估 = $EV cp"; else echo "  [FAIL] eval 无输出"; FAIL=1; fi

echo "== 等节点确定性（两次必须同着）=="
A=$(printf 'position fen 3k5/9/9/9/9/9/7R1/9/9/3K5 w - - 0 1\ngo nodes 20000\nquit\n' | "$EXE" 2>/dev/null | grep bestmove)
B=$(printf 'position fen 3k5/9/9/9/9/9/7R1/9/9/3K5 w - - 0 1\ngo nodes 20000\nquit\n' | "$EXE" 2>/dev/null | grep bestmove)
if [ "$A" = "$B" ] && [ -n "$A" ]; then echo "  [OK]   $A"; else echo "  [FAIL] $A vs $B"; FAIL=1; fi

echo
if [ "$FAIL" = "0" ]; then
  echo "自检通过。"
else
  echo "自检失败，请检查上面的 FAIL 项。"
fi
exit $FAIL
'''


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    import subprocess
    import sys
    # 打包前强制把权重对齐到指定模型，避免「exe 一个模型、mlp46.h 另一个」的错配
    for extra, out in (([], "mlp46.h"), (["--int8"], "mlp46_i8.h")):
        subprocess.run([sys.executable, str(HERE / "export_mlp.py"),
                        "--model", MODEL, "--out", out] + extra, check=True, cwd=str(HERE))
    print("权重来源：", (HERE / "mlp46.h").read_text(encoding="utf-8").splitlines()[0])

    OUT.mkdir(parents=True, exist_ok=True)
    for src, dst in FILES:
        s = HERE / src
        if not s.exists():
            print("跳过（不存在）", src)
            continue
        shutil.copy2(s, OUT / dst)
        print("  %-34s -> %s" % (src, dst))
    (OUT / "build.sh").write_text(BUILD_SH, encoding="utf-8", newline="\n")
    (OUT / "selfcheck.sh").write_text(SELFCHECK_SH, encoding="utf-8", newline="\n")

    names = sorted(p.name for p in OUT.iterdir() if p.is_file())
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in names:
            p = OUT / n
            zi = zipfile.ZipInfo(n, date_time=(2026, 11, 18, 8, 30, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if n.endswith((".exe", ".sh")) else 0o644) << 16
            zi.flag_bits |= 0x800
            z.writestr(zi, p.read_bytes())
    print("\n包目录 %s（%d 个文件）" % (OUT, len(names)))
    for n in names:
        p = OUT / n
        print("  %-36s %9d B" % (n, p.stat().st_size))
    print("zip %s  %.2f MB  md5 %s" % (ZIP, ZIP.stat().st_size / 1e6, md5(ZIP)))
    print("exe md5 %s" % md5(OUT / EXE))


if __name__ == "__main__":
    main()
