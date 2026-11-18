"""把模型与偏离引擎内联进页面模板，产出单文件网页。

用法：python build3d.py --model model3d.json --out "GeoLite象棋AI_三维引力版.html"
"""

import argparse
import json
import pathlib

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="model3d.json")
ap.add_argument("--out", default="GeoLite象棋AI_三维引力版.html")
args = ap.parse_args()

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / args.out

tpl = (HERE / "web_src3d.html").read_text(encoding="utf-8")
model = json.loads((HERE / args.model).read_text(encoding="utf-8"))
engine = (HERE / "engine3d.js").read_text(encoding="utf-8")

html = tpl.replace("/*__MODEL3D__*/", "window.MODEL3D = " + json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";")
html = html.replace("/*__ENGINE3D__*/", engine.replace("</", "<\\/"))
OUT.write_text(html, encoding="utf-8")
print(OUT, round(OUT.stat().st_size / 1024), "KB")
