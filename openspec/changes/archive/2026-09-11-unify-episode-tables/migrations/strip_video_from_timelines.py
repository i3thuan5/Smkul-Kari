#!/usr/bin/env python3
"""一擺性：kā Kari-SRT 已經入庫ê時間軸內底ê `video` 欄提掉。

    python3 openspec/changes/unify-episode-tables/migrations/\
strip_video_from_timelines.py          # 看伊beh改佗幾份
    python3 …/strip_video_from_timelines.py --write     # 真正改

彼欄記ê是當初彼台機器ê暫存位置，換機器就無意義。`publish` 這爿已經
用 `datadirs.store_timeline()` 擋起來矣，這支是掃既有ê。跑一擺就無路
用矣，留佇 change 目錄做紀錄，無入 `scripts/`。
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

sys.path.insert(0, ROOT)

from scripts import datadirs                       # noqa: E402
from scripts.news import redump_store              # noqa: E402


def timelines():
    found = []
    for pattern in ("Kari-SRT/news/1-ocr/1-cues/*/*.json",
                    "Kari-SRT/aiyalaeho/1-ocr/1-cues/*.json"):
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            found.append(path)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    changed = 0
    for path in timelines():
        with open(path, encoding="utf-8") as handle:
            before = handle.read()
        after = redump_store.dump(datadirs.store_timeline(json.loads(before)))
        if after == before:
            continue
        changed += 1
        if args.write:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(after)
    verb = "改矣" if args.write else "會改"
    print("%d／%d 份時間軸%s" % (changed, len(timelines()), verb))
    return 0


if __name__ == "__main__":
    sys.exit(main())
