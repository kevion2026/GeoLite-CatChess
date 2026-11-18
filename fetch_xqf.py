"""按清单从 GitHub 拉取象棋棋谱（XQF），走公开代理，支持断点续传。"""
import io, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://gh-proxy.com/https://raw.githubusercontent.com/weiyinfu/xqp/main/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "xqf")
CLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "xq_paths.txt")
PREFIXES = ("比赛对局/", "大师专集/", "全局/", "布局/")


def target(path):
    flat = path.replace("/", "~")
    return os.path.join(OUT, flat)


def fetch(path):
    dst = target(path)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return "skip"
    url = BASE + urllib.parse.quote(path, safe="/")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read()
            if not body:
                return "empty"
            os.makedirs(OUT, exist_ok=True)
            with open(dst, "wb") as f:
                f.write(body)
            return "ok"
        except Exception as e:
            if attempt == 2:
                return "fail:" + type(e).__name__
            time.sleep(1 + attempt)
    return "fail"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 9
    paths = [p.strip() for p in io.open(CLIST, encoding="utf-8") if p.strip()]
    paths = [p for p in paths if p.startswith(PREFIXES)][:limit]
    print("待抓取", len(paths))
    stat = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i, res in enumerate(ex.map(fetch, paths), 1):
            key = res.split(":")[0]
            stat[key] = stat.get(key, 0) + 1
            if i % 500 == 0:
                print(i, stat, f"{time.time() - t0:.0f}s", flush=True)
    print("完成", stat, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
