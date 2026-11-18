"""打包 CatChess-v2.1 到 dist/，并生成 UTF-8 文件名的 zip。

注意：不要用 PowerShell 的 Compress-Archive —— 它按 GBK 写中文名，解压乱码。
"""
import hashlib
import pathlib
import shutil
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "dist" / "CatChess-v2.1"
ZIP = HERE / "dist" / "CatChess-v2.1.zip"
MODEL = "model_eg_M.json"

FILES = [
    ("CatChess-v2.1.exe", "CatChess-v2.1.exe"),
    ("CatChess-v2.1-架构.md", "CatChess-v2.1-架构.md"),
    ("CatChess-v2.1-README.md", "README.md"),
    ("xq.cpp", "xq.cpp"),
    ("mlp_eval.h", "mlp_eval.h"),
    ("mlp46.h", "mlp46.h"),
    ("geo_eval.h", "geo_eval.h"),
    ("geo45.h", "geo45.h"),
    ("linear_weight_aug.h", "linear_weight_aug.h"),
    ("linear_weight_static.h", "linear_weight_static.h"),
    ("export_mlp.py", "export_mlp.py"),
    ("gen_endgames.py", "gen_endgames.py"),
    ("gen_endgame_playout.py", "gen_endgame_playout.py"),
    ("label_endgames.py", "label_endgames.py"),
    ("train_mlp_mix.py", "train_mlp_mix.py"),
]

BUILD_SH = r'''#!/bin/sh
# CatChess-v2.1 一键重建
#   需要 MinGW-w64 的 g++（GCC 9+，AVX2 更好）。w64devkit 这类绿色包即可：
#     CXX=/path/to/w64devkit/bin/g++ ./build.sh
#
#   ./build.sh                 → CatChess-v2.1.exe（残局补数据版，默认）
#   SCALE=0.9 ./build.sh       → 改评估缩放（越小剪枝越狠、搜索越深）
#   ./build.sh v2              → CatChess-v2.0.exe（上一代）
#   ./build.sh v1              → CatChess-v1.0pro-preview.exe（上上代）
#   ./build.sh geo             → xq17.exe   纯 45 维几何树
#   NO_NATIVE=1 ./build.sh     → 不启用 -march=native（跨机器分发时用）
set -e
CXX="${CXX:-g++}"
command -v "$CXX" >/dev/null 2>&1 || CXX="$CXX".exe
command -v "$CXX" >/dev/null 2>&1 || {
  echo "找不到编译器：$CXX"
  echo "请安装 MinGW-w64，或用 CXX=/path/to/g++ ./build.sh 指定"
  exit 1
}

# w64devkit 的 g++ 需要可写的临时目录，否则报 Cannot create temporary file。
# 不能沿用宿主的 TMPDIR/TEMP（Windows 上常指向 AppData\Local\Temp，可能不可写），
# 这里一律指到包内的 .tmpbuild/。
TMPDIR="$PWD/.tmpbuild"
export TMPDIR
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
mkdir -p "$TMPDIR"

NATIVE=""
[ "${NO_NATIVE:-0}" = "1" ] || NATIVE="-march=native"
FLAGS="-O3 $NATIVE -ffast-math -std=c++17 -static"
SC="${SCALE:-1.0}"
MW="${MIX_W:-65}"

case "$1" in
  v2)       $CXX $FLAGS -DUSE_GEO -DUSE_MLP -DMLP_SMALL_SCALE -DMLP_SCALE=0.75f \
              -o CatChess-v2.0.exe xq.cpp \
            && echo "→ CatChess-v2.0.exe（上一代：MLP 64/32，尺度 0.75）" ;;
  v1)       $CXX $FLAGS -DUSE_GEO -DMIX_W=$MW -o CatChess-v1.0pro-preview.exe xq.cpp \
            && echo "→ CatChess-v1.0pro-preview.exe（几何树 + 平面融合 MIX_W=$MW）" ;;
  geo)      $CXX $FLAGS -DUSE_GEO -o xq17.exe xq.cpp && echo "→ xq17.exe（纯 45 维几何树）" ;;
  *)        $CXX $FLAGS -DUSE_GEO -DUSE_MLP -DMLP_EG -DMLP_SCALE=${SC}f \
              -o CatChess-v2.1.exe xq.cpp \
            && echo "→ CatChess-v2.1.exe（残局补数据版，192/96，尺度 $SC）" ;;
esac
'''

SELFCHECK_SH = r'''#!/bin/sh
# CatChess-v2.1 出厂自检
#   ./selfcheck.sh [exe路径]
# 校验 perft、UCI 握手、评估与搜索是否都能给出结果。
EXE="${1:-./CatChess-v2.1.exe}"
[ -f "$EXE" ] || { echo "找不到 $EXE"; exit 1; }

OUT=$(printf 'uci\nisready\nperft 1\nperft 2\nperft 3\neval\nposition startpos\ngo depth 6\nquit\n' | "$EXE" 2>&1)
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
chk "uciok"                     "uci → uciok"
chk "readyok"                   "isready → readyok"
chk "id name CatChess-v2.1"     "id name 正确"

echo "== perft（象棋标准值）=="
chk "perft 1 = 44"     "perft 1 = 44"
chk "perft 2 = 1920"   "perft 2 = 1920"
chk "perft 3 = 79666"  "perft 3 = 79666"

echo "== 搜索 =="
chk "info depth 6"      "到达 depth 6"
chk "bestmove "         "返回 bestmove"

echo "== 评估 =="
EV=$(printf 'position startpos\neval\nquit\n' | "$EXE" 2>/dev/null | tr -dc '0-9-\n' | head -1)
if [ -n "$EV" ]; then echo "  [OK]   开局评估 = $EV cp"; else echo "  [FAIL] eval 无输出"; FAIL=1; fi

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
    # 打包前强制把权重文件对齐到指定的模型，避免「exe 是 M、mlp46.h 是 P」这种错配
    import subprocess, sys
    subprocess.run([sys.executable, str(HERE / "export_mlp.py"),
                    "--model", MODEL, "--out", "mlp46.h"], check=True, cwd=str(HERE))
    head = (HERE / "mlp46.h").read_text(encoding="utf-8").splitlines()[0]
    print("权重来源：", head)

    OUT.mkdir(parents=True, exist_ok=True)
    for src, dst in FILES:
        s = HERE / src
        if not s.exists():
            print("跳过（不存在）", src)
            continue
        shutil.copy2(s, OUT / dst)
        print("  %-30s -> %s" % (src, dst))
    (OUT / "build.sh").write_text(BUILD_SH, encoding="utf-8", newline="\n")
    (OUT / "selfcheck.sh").write_text(SELFCHECK_SH, encoding="utf-8", newline="\n")

    names = sorted(p.name for p in OUT.iterdir() if p.is_file())
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in names:
            p = OUT / n
            zi = zipfile.ZipInfo(n, date_time=(2026, 11, 18, 0, 30, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if n.endswith((".exe", ".sh")) else 0o644) << 16
            zi.flag_bits |= 0x800          # UTF-8 文件名标志位
            z.writestr(zi, p.read_bytes())
    print("\n包目录 %s（%d 个文件）" % (OUT, len(names)))
    for n in names:
        p = OUT / n
        print("  %-34s %9d B" % (n, p.stat().st_size))
    print("zip %s  %.2f MB  md5 %s" % (ZIP, ZIP.stat().st_size / 1e6, md5(ZIP)))
    print("exe md5 %s" % md5(OUT / "CatChess-v2.1.exe"))


if __name__ == "__main__":
    main()
