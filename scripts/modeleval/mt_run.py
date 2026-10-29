#!/usr/bin/env python3
"""開會了阿美的字幕句對，族→華、華→族兩個方向送翻譯服務。

    python3 -m scripts.modeleval.mt_run [--server URL]

逐集輪流：一集的族→華做完接華→族，中途停去的時候兩個方向都有一部份
做好可以先算分。結果全進 `kithann/out/modeleval-阿美/mt-cache/`（JSONL，
重跑只問快取無的句）。
"""
import argparse
import os
import sys

from scripts.asrmt import mtclient
from scripts.modeleval import mtboth
from scripts.modeleval import pairs
from scripts.modeleval.asr_run import OUT


def with_codes(rows):
    for item in rows:
        item["mt_code"] = pairs.mt_code(
            pairs.sapolita_code(item["srt_name"], item["code"]))
    return rows


def ordered_items(rows):
    """逐集：族→華全部，接華→族全部。"""
    by_episode = {}
    for item in rows:
        by_episode.setdefault(item["srt_name"], []).append(item)
    out = []
    for name in sorted(by_episode):
        items = pairs.mt_items(by_episode[name])
        for direction in ("f2z", "z2f"):
            for item in items:
                if item[0] == direction:
                    out.append(item)
    return out


def run(items, cache, client):
    done = 0
    for direction, lang, text in items:
        client.translate_cached(cache, direction, lang, text)
        done += 1
        if done % 100 == 0:
            print("%d/%d" % (done, len(items)), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=mtboth.DEFAULT_SERVER)
    args = parser.parse_args(argv)
    cache = mtclient.MTCache(os.path.join(OUT, "mt-cache"))
    items = ordered_items(with_codes(pairs.load()))
    run(items, cache, mtboth.Client(args.server))
    print("all %d done" % len(items), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
