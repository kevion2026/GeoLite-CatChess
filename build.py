"""把引擎与模型内联进单文件网页，产出可直接双击打开的 HTML。"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
OUT = "GeoLite象棋AI.html"


def main():
    tpl = (HERE / "web_src.html").read_text(encoding="utf-8")
    engine = (HERE / "engine.js").read_text(encoding="utf-8")
    model = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
    model_js = "window.GEOLITE_MODEL = " + json.dumps(model, ensure_ascii=False, separators=(",", ":")) + ";"
    out = tpl.replace("/*__MODEL__*/", model_js).replace("/*__ENGINE__*/", engine)
    book_path = HERE / "data" / "book.json"
    if book_path.exists():
        book = json.loads(book_path.read_text(encoding="utf-8"))
        book_js = "window.GEOLITE_BOOK = " + json.dumps(book, ensure_ascii=False, separators=(",", ":")) + ";"
    else:
        book_js = "window.GEOLITE_BOOK = null;"
    out = out.replace("/*__BOOK__*/", book_js)
    target = HERE / OUT
    target.write_text(out, encoding="utf-8")
    print(f"{target}  {target.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
