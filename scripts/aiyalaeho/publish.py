#!/usr/bin/env python3
"""Move a finished batch into the store and stand behind it.

    python3 -m scripts.aiyalaeho.publish            # 規批定版
    python3 -m scripts.aiyalaeho.publish --check    # 報告，一字都無寫

`make_all` writes the delivered SRTs straight into 3-srt/, and the vision
TSVs are written into 2-vision/ by the readers themselves. What is left is
the per-episode input the offline rebuild needs to put an SRT back
together without a video -- `1-cues/<srt_name>.json`。無閣寫任何一張
表，嘛無閣清 pending：兩張 smkul 表是節目目錄，人維護ê輸入。

The unit is **one episode**, not the batch. An unread episode holds back
only itself; the finished ones go out. This was all-or-nothing until
2026-09-09, when the news side hit the cost of it: January had 58 episodes
not yet cut, and that kept 006午 -- cut, refined, read and verified -- out
of the store, while the only copy of its timeline sat in a work dir whose
master had already been deleted.

Per-episode stays self-consistent because no episode vouches for another:
`publishable` already demands that this one was cut, refined and fully
read; the delivered table lists only the non-pending ones; and the offline
rebuild walks only the non-pending ones. Publishing one moves that one
from pending to delivered and puts its own inputs in the store.
"""
import argparse
import json
import os
import sys

from scripts import datadirs
from scripts.aiyalaeho import make_all
from scripts.aiyalaeho import episodes
from scripts.aiyalaeho import paths


def publishable(entry):
    """(source work dir, reason it cannot be published).

    A reason only stops the batch when the episode is pending -- an
    already-delivered episode whose work dir has been cleared away is
    nothing to do, which is exactly why the work dir was safe to delete.

    An abnormal episode is publishable with nothing to publish: it has no
    timeline, no transcript and no SRT, and asking `vision_complete` about
    it would hold the whole batch open forever waiting for a reading that
    is never going to happen.
    """
    if entry["abnormal"]:
        return "", ""
    work = paths.work_dir(entry["srt_name"])
    if not datadirs.cues_to_read(work):
        return "", "尚未切cue"
    if not make_all.vision_complete(work):
        return "", "視覺辨識尚未讀完"
    if not os.path.exists(paths.stage_path(paths.SRT_DIR,
                                           entry["srt_name"], ".srt")):
        return "", "猶未組裝（先走 make_all）"
    return work, ""


def gate(entries):
    """Registered episodes that are not finished -- why each one waits.

    A **query**, not the gate: `main` no longer consults it before writing
    (see the module docstring). It answers "what is this batch waiting on",
    which is what a person wants when a batch is dragging.
    """
    blocked = []
    for entry in entries:
        if not entry["pending"]:
            continue
        _work, reason = publishable(entry)
        if reason:
            blocked.append((entry["srt_name"], reason))
    return blocked


def publish_one(entry, work):
    """Put this episode's timeline in the store, laid out for a reader.

    Read and re-dumped rather than copied: the store's formatting is this
    program's to decide, not the work dir's. Copying let the work copy's
    layout through, and with another line of work re-indenting the store
    the two would have taken turns overwriting each other.
    """
    if entry["abnormal"]:
        return ""
    target = paths.stage_path(paths.KARI_CUES, entry["srt_name"], ".json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(datadirs.cues_to_read(work), encoding="utf-8") as handle:
        manifest = json.load(handle)
    body = json.dumps(datadirs.store_timeline(manifest), ensure_ascii=False,
                      indent=2, sort_keys=True)
    # 內容相仝就莫重寫：捌有一擺入庫kā 74 份內容根本無變ê已交付檔
    # 全部重寫過。比ê是**正規化了後**ê字串——工作目錄彼份ê鍵是插入
    # 順序，比原始檔ê話逐擺攏會判做無仝。
    if os.path.exists(target):
        with open(target, encoding="utf-8") as handle:
            if handle.read() == body:
                return ""
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(body)
    return target


def measured_reasons(entries):
    """[srt_name…] whose reason this pipeline decided, not the file name.

    A reason lifted off the file name is the broadcaster's own label. One
    that says 版型不符 or 人工判定, or that says 無字幕 where the name does
    not, came from the band check or from somebody reading a sheet -- and
    that is what a person wants to glance at once the batch is over.
    """
    from scripts.aiyalaeho import catalogue
    named = []
    for entry in entries:
        reason = entry.get("備註")
        if not reason:
            continue
        stem = os.path.splitext(entry.get("file")
                                or os.path.basename(entry["video"]))[0]
        _episode, tokens = catalogue._tokens(stem)
        if reason != catalogue.subtitle_state(tokens):
            named.append(entry["srt_name"])
    return named


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="報告欲定版啥，一字都無寫")
    args = ap.parse_args(argv)

    entries = episodes.load()

    # Decide everything before writing anything. The unit is one episode:
    # each is judged by `publishable` alone, and an unfinished one holds
    # back only itself.
    ready = []
    for entry in entries:
        work, reason = publishable(entry)
        if reason:
            print("skip  %-30s %s" % (entry["srt_name"], reason))
            continue
        ready.append((entry, work))
        if args.check:
            print("ready %s" % entry["srt_name"])

    if args.check:
        print("\n%d／%d 集會使定版（試跑，無寫入）"
              % (len(ready), len(entries)))
        return 0

    written = 0
    for entry, work in ready:
        if publish_one(entry, work):
            written += 1
            print("write %s" % entry["srt_name"])
        else:
            print("same  %s" % entry["srt_name"])

    print("\n%d 集ê時間軸入庫（%d 集內容相仝，無重寫）"
          % (written, len(ready) - written))
    for name in measured_reasons(entries):
        print("  ← %s ê理由是量測抑是人判ê，看一目" % name)
    print("next: python3 -m scripts.aiyalaeho.rebuild --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
