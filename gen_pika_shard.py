"""单个标注分片：断点续跑、引擎崩溃自动重启。"""
import argparse
import pickle
import pathlib
import sys
import time

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
sys.path.insert(0, str(HERE))
from gen_pika_values2 import Engine, fen_of, load_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--movetime", type=int, default=50)
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--checkpoint", type=int, default=500)
    args = ap.parse_args()

    rows = load_rows(HERE / args.positions)
    rows = rows[args.start:args.end]
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = []
    if out.exists():
        try:
            done = pickle.load(open(out, "rb"))
        except Exception:
            done = []
    try:
        eng = Engine()
    except Exception as e:
        print(f"  shard {args.start}: init failed, checkpoint and exit: {e}", flush=True)
        tmp = str(out) + ".tmp"
        pickle.dump(done, open(tmp, "wb"))
        pathlib.Path(tmp).replace(out)
        sys.exit(3)
    t0 = time.time()
    k = len(done)
    while k < len(rows):
        b, s, _src = rows[k]
        cp = None
        for attempt in range(2):
            try:
                cp = eng.label(fen_of(b, s), args.depth, args.movetime)
                break
            except Exception as e:
                print(f"  shard {args.start}: engine restart at {k}: {e}", flush=True)
                try:
                    eng.close()
                except Exception:
                    pass
                time.sleep(0.3)
                try:
                    eng = Engine()
                except Exception as e2:
                    print(f"  shard {args.start}: engine init failed, checkpoint and exit: {e2}", flush=True)
                    tmp = str(out) + ".tmp"
                    pickle.dump(done, open(tmp, "wb"))
                    pathlib.Path(tmp).replace(out)
                    sys.exit(3)
        if cp is None:
            print(f"  shard {args.start}: skip poison position {args.start + k}", flush=True)
            cp = 0
        done.append((args.start + k, int(max(-30000, min(30000, cp)))))
        k += 1
        if k % args.checkpoint == 0 or k == len(rows):
            tmp = str(out) + ".tmp"
            pickle.dump(done, open(tmp, "wb"))
            pathlib.Path(tmp).replace(out)
            print(f"  shard {args.start}: {k}/{len(rows)} {time.time()-t0:.0f}s", flush=True)
    try:
        eng.close()
    except Exception:
        pass
    print(f"DONE shard {args.start}-{args.end} {len(done)}", flush=True)


if __name__ == "__main__":
    main()
