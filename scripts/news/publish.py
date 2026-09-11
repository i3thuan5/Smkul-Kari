#!/usr/bin/env python3
"""Put an episode's timeline into Kari-SRT.

    python3 -m scripts.news.publish            # every cut, refined episode
    python3 -m scripts.news.publish --check    # report, write nothing

三个階段逐个各自入庫。`make_all.py` kā交付ê SRT 直接寫入
news/1-ocr/3-srt/，Claude Vision 彼爿家己kā TSV 寫入 2-vision/——剩ê
就是 `rebuild.py` 欲kā SRT 組轉來所需ê彼份：`1-cues/<成果檔名>.json`。

**視覺辨識讀煞才准入庫彼道門提掉矣。** 時間軸切好、精修好就入庫，
免等彼幾十點鐘ê閱讀。理由：彼幾十點鐘ê成果囥佇工作區——gitignore ê
所在——連一份備份都無。捌有一集ê時間軸干焦賰工作目錄一份，而且伊ê
母帶已經刣掉矣。

猶原擋落來ê干焦兩項：無時間軸、時間軸猶未精修。粗切佮精修精度差
一个數量級（0.2 秒 vs 0.05 秒），兩種濫做伙ê話，`1-cues/` 就無法度
直接宣告「內底逐一份攏是精修過ê」。

這爿無閣寫 `smkul.csv` 矣——彼是節目目錄，人維護ê輸入。嘛無閣清
`pending`：某一集做到佗一步，答案佇階段目錄。
"""
import argparse
import json
import os
import sys

from scripts import datadirs
from scripts.news import episodes
from scripts.news import paths
from scripts.news import redump_store
from scripts.errors import PipelineError

WORK = paths.WORK


def publishable(entry):
    """(source work dir, reason it cannot be published).

    A reason only holds back this one episode. An already-delivered episode
    whose work dir has been cleared away is simply nothing to do: its inputs
    are in the store, which is exactly why the work dir was safe to delete.
    """
    work = paths.work_dir(entry["slug"], WORK)
    # Asked through the helper, so every layout the timeline can arrive in
    # counts. Spelling `<work>/cues.json` out here reads a staged work dir
    # as uncut, and the batch is then held back for the wrong reason.
    if paths.cues_to_read(work) is None:
        return "", "尚未切cue"
    return work, ""


def months_of(entries):
    """Every broadcast month the inventory holds, in order."""
    seen = set()
    for entry in entries:
        seen.add(paths.month_of(entry["srt_name"]))
    return sorted(seen)


def gate(entries, month=None):
    """Pending episodes in `month` that are not finished -- why each waits.

    This is a **query**, not the gate. `main` no longer consults it before
    writing: an unfinished episode holds back only itself (see the module
    docstring). What it is still good for is answering "what is this batch
    waiting on", which is what a person wants when a month is dragging.

    Scope is a **broadcast month**, the same unit `plan_month.py` and
    `fetch_sftp.sh` work in; passing no month walks the whole inventory.
    """
    blocked = []
    for entry in entries:
        if month is not None and paths.month_of(entry["srt_name"]) != month:
            continue
        if not entry["pending"]:
            continue
        _work, reason = publishable(entry)
        if reason:
            blocked.append((entry["srt_name"], reason))
    return blocked


def refined_timeline(entry, work):
    """This episode's timeline, or say which of the two things is wrong.

    The store only takes refined timelines. Every delivered timestamp is
    derived from this one file, and the two grades differ by an order of
    magnitude -- 0.2s against 0.05s -- so once both are in `1-cues/`
    nothing tells them apart. Gating here is what lets that folder state
    outright that everything in it has been refined.

    The two refusals are worded apart because the fixes are: a coarse
    timeline wants `refine_cues`, a missing one wants the episode cut.
    """
    source = paths.cues_to_read(work)
    if source is None:
        raise PipelineError("%s：%s 內底揣無時間軸，袂使定版"
                            % (entry["srt_name"], work))
    if not paths.timeline_is_refined(source):
        raise PipelineError(
            "%s：時間軸猶未精修（%s），袂使入 store——先走 refine_cues"
            % (entry["srt_name"], source))
    return source


def publish_one(entry, work, cues_dir=None):
    """Copy this episode's inputs into the store; return what was written.

    Cues used to share a loop with `from_rtf.json` whose "missing? carry
    on" arm was written for that file, which legitimately is absent for
    most episodes. A timeline is never optional, and sharing that arm is
    what made a missing one silent.

    Read and re-dumped rather than `shutil.copy2`-ed, because the store's
    JSON has to be readable by a person (see CLAUDE.md) and the work dir's
    copy is not: its keys are in insertion order. Copying it verbatim
    overwrote the store's sorted layout, so one publish rewrote 74 already
    delivered files whose content had not changed at all -- and the next
    re-dump of the store would flip them straight back. Same fix the
    aiyalaeho side already carries.
    """
    folder = paths.KARI_CUES if cues_dir is None else cues_dir
    source = refined_timeline(entry, work)
    target = paths.stage_path(folder, entry["srt_name"], ".json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(source, encoding="utf-8") as handle:
        manifest = json.load(handle)
    body = redump_store.dump(datadirs.store_timeline(manifest))
    if os.path.exists(target):
        with open(target, encoding="utf-8") as handle:
            if handle.read() == body:
                return []
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(body)
    return [os.path.basename(folder)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would be published, write nothing")
    args = ap.parse_args(argv)

    entries = episodes.load()

    # Decide everything before writing anything. The unit is one episode:
    # each is judged by `publishable` alone, and an unfinished one holds
    # back only itself. Nothing here vouches for anything else -- see the
    # module docstring for why that keeps the store self-consistent.
    ready = []
    for entry in entries:
        work, reason = publishable(entry)
        if reason:
            print("skip  %-46s %s" % (entry["srt_name"], reason))
            continue
        ready.append((entry, work))
        if args.check:
            print("ready %s" % entry["srt_name"])

    # An empty `ready` is not a failure. It means either that everything
    # is already delivered, or that no episode of this batch has finished
    # yet -- and the `skip` line above already named the step each one is
    # stuck at. Returning non-zero here made batch scripts read "not my
    # turn yet" as "something broke".
    if args.check:
        print("\n%d of %d episode(s) ready to publish (nothing written)"
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
    print("next: python3 -m scripts.news.rebuild --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
