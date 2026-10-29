#!/usr/bin/env python3
"""開會了阿美各集送 sapolita（whisper 族語辨識），回傳 SRT 原樣存。

    python3 -m scripts.modeleval.asr_run [--server URL]

影片是本機 `kithann/mp4/<成果檔名>.preview.mp4`（有音軌），抽成 16 kHz
單聲道 mp3 再送。一次只送一集——伺服器不可平行。做過的（SRT 在）跳過。
"""
import argparse
import os
import sys

from scripts.asrmt import sapolita
from scripts.modeleval import pairs
from scripts.news import audio
from scripts import datadirs

DEFAULT_SERVER = "https://ai-labs.ilrdf.org.tw/sapolita/"
OUT = os.path.join(datadirs.KITHANN, "out", "modeleval-阿美")
VIDEOS = os.path.join(datadirs.KITHANN, "mp4")


def episodes(rows):
    """[(成果檔名, sapolita 語別碼)]，照成果檔名排。"""
    codes = {}
    for item in rows:
        codes[item["srt_name"]] = item["code"]
    out = []
    for name in sorted(codes):
        out.append((name, pairs.sapolita_code(name, codes[name])))
    return out


def srt_path(out_dir, name):
    return os.path.join(out_dir, "asr", name + ".srt")


def run(todo, server, out_dir, recognize=None, extract=None):
    recognize = recognize or sapolita.recognize
    extract = extract or audio.extract_audio
    os.makedirs(os.path.join(out_dir, "asr"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "audio"), exist_ok=True)
    for name, code in todo:
        target = srt_path(out_dir, name)
        if os.path.exists(target):
            continue
        mp3 = os.path.join(out_dir, "audio", name + ".mp3")
        extract(os.path.join(VIDEOS, name + ".preview.mp4"), mp3)
        try:
            text = recognize(server, mp3, code)
        finally:
            os.remove(mp3)
        with open(target + ".part", "wb") as handle:
            handle.write(text.encode("utf-8"))
        os.replace(target + ".part", target)
        print("%s %s done" % (name, code), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    args = parser.parse_args(argv)
    run(episodes(pairs.load()), args.server, OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
