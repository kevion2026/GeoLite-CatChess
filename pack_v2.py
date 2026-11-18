"""打包 CatChess-v2.0 到 dist/，并生成 UTF-8 文件名的 zip。

注意：不要用 PowerShell 的 Compress-Archive —— 它按 GBK 写中文名，解压乱码。
"""
import hashlib
import pathlib
import shutil
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "dist" / "CatChess-v2.0"
ZIP = HERE / "dist" / "CatChess-v2.0.zip"

FILES = [
    ("CatChess-v2.0.exe", "CatChess-v2.0.exe"),
    ("CatChess-v2.0-架构.md", "CatChess-v2.0-架构.md"),
    ("CatChess-v2.0-README.md", "README.md"),
    ("xq.cpp", "xq.cpp"),
    ("mlp_eval.h", "mlp_eval.h"),
    ("mlp46.h", "mlp46.h"),
    ("geo_eval.h", "geo_eval.h"),
    ("geo45.h", "geo45.h"),
    ("linear_weight_aug.h", "linear_weight_aug.h"),
    ("linear_weight_static.h", "linear_weight_static.h"),
    ("train_mlp45.py", "train_mlp45.py"),
    ("export_mlp.py", "export_mlp.py"),
]


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for src, dst in FILES:
        s = HERE / src
        if not s.exists():
            print("跳过（不存在）", src)
            continue
        shutil.copy2(s, OUT / dst)
        print("  %-28s -> %s" % (src, dst))

    names = sorted(p.name for p in OUT.iterdir() if p.is_file())
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in names:
            p = OUT / n
            zi = zipfile.ZipInfo(n, date_time=(2026, 11, 17, 21, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if n.endswith(".exe") else 0o644) << 16
            zi.flag_bits |= 0x800          # UTF-8 文件名标志位
            z.writestr(zi, p.read_bytes())
    print("\n包目录 %s（%d 个文件）" % (OUT, len(names)))
    for n in names:
        p = OUT / n
        print("  %-34s %9d B" % (n, p.stat().st_size))
    print("zip %s  %.2f MB  md5 %s" % (ZIP, ZIP.stat().st_size / 1e6, md5(ZIP)))
    print("exe md5 %s" % md5(OUT / "CatChess-v2.0.exe"))


if __name__ == "__main__":
    main()
