#!/usr/bin/env python3
"""一擺性：2024-08-01 起ê新聞，節目名稱換做《看見族語（時段）》。

    python3 openspec/changes/rename-news-programme-2024-08/migrations/\
rename_programme.py                       # 看伊beh改啥，毋寫
    python3 …/rename_programme.py --write --expect-changed 337   # 真正寫

吃：`Kari-SRT/news/smkul.csv`（或 `--catalogue` 指定ê表）。
出：仝一張表，干焦 2024-08-01 起、猶是舊名稱ê逐逝改 `節目名稱`。
成果檔名、列序、BOM 佮 CRLF 攏無動。重跑無代誌：改過ê逐逝已經是新名稱。

`--expect-changed N` 是保險：實際欲改ê逐數若毋是 N，就停落來、毋寫。
改了後逐逝ê節目名稱佮播出日期愛對會著，成果檔名愛佮改進前一模一樣，
無就嘛毋寫。

跑一擺就無路用矣，留佇 change 目錄做紀錄，無入 `scripts/`。
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, ROOT)

from scripts import catalogue_checks as checks      # noqa: E402
from scripts.errors import PipelineError           # noqa: E402
from scripts.news import name_catalogue            # noqa: E402


def migrate(rows):
    """(新ê逐逝, 改著ê逐數 {時段: 幾逝})；入來ê逐逝無動。"""
    out = []
    changed = collections.Counter()
    for row in rows:
        new = dict(row)
        programme = row["節目名稱"]
        date = row["播出日期"]
        if programme in checks.SLOTS and date >= checks.RENAMED_ON:
            slot = checks.SLOTS[programme]
            want = checks.programme_for(slot, date)
            if programme != want:
                new["節目名稱"] = want
                changed[slot] += 1
        out.append(new)
    return out, changed


def verify(before, after):
    """改了ê表愛過關，無就講是佗一逝。"""
    if len(before) != len(after):
        raise PipelineError("逝數變矣：%d → %d" % (len(before), len(after)))
    for old, new in zip(before, after):
        if old["成果檔名"] != new["成果檔名"]:
            raise PipelineError("成果檔名無愛動：%s" % old["成果檔名"])
        if checks.srt_name_of(new) != new["成果檔名"]:
            raise PipelineError("改了後成果檔名推袂對：%s" % old["成果檔名"])
    problems = checks.row_problems(after)
    if problems:
        raise PipelineError("改了猶有問題：%s" % problems[0])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalogue", help="欲改ê目錄表；無指定就用 smkul.csv")
    ap.add_argument("--write", action="store_true", help="真正寫入")
    ap.add_argument("--expect-changed", type=int,
                    help="預期欲改幾逝，對袂著就停")
    args = ap.parse_args(argv)

    path = args.catalogue or name_catalogue.paths.TRACKER_STORE
    rows, head = name_catalogue.read(path)
    after, changed = migrate(rows)
    total = sum(changed.values())
    print("目錄 %d 逝：要改 %d 逝（%s），不動 %d 逝"
          % (len(rows), total,
             "、".join("%s %d" % (slot, changed[slot])
                      for slot in ("午間", "晚間", "晨間")),
             len(rows) - total))
    if args.expect_changed is not None and total != args.expect_changed:
        print("預期改 %d 逝，實際 %d 逝，停。" % (args.expect_changed, total))
        return 1
    verify(rows, after)
    if not args.write:
        print("（dry-run，無寫。加 --write 才寫）")
        return 0
    if total == 0:
        print("無愛改ê，無重寫。")
        return 0
    name_catalogue.write(path, after, head)
    print("寫好矣：%s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
