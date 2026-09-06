#!/usr/bin/env python3
"""Constructed probes: what a judge should get wrong, but must not.

There is nobody available who reads these languages, so there is no
ground truth for 高. There is ground truth for the other direction,
though, and it can be manufactured: take the entries a judge graded 高
and break them on purpose -- put another entry's subtitle on them,
change a number, cut the second half off -- and grade them again. A
probe that comes back 高 says the judge was not reading the subtitle, or
not checking the numbers, or not noticing that half the sentence went
missing. Which of those is a diagnosis, not just a score.

So each probe changes **one** thing, and never the Formosan line or the
translation: if two things moved, a downgrade would not say which one
caused it. The entry number is kept, so a reply traces back to the
sentence it came from.

Not every entry can carry every probe -- a subtitle with no number
cannot be renumbered, a short one cannot be halved without becoming a
different probe -- and those are skipped rather than faked.
"""
import re

# 字幕內底ê數字上要緊：金額、人數、年份對毋著就袂使是高，這是訓練
# 集上驚ê彼款錯。
DIGITS = re.compile(r"[0-9]+")

# 中文數字愛**後壁有單位**才算數量。「一大清早」ê「一」是詞ê一部
# 份，毋是數量；kā伊改做「三大清早」，讀起來干焦是拍毋著字，講ê
# iáu是仝一件代誌——彼種探針測無物件，顛倒是探針家己造毋著。
CHINESE = "一二三四五六七八九十兩"
CHINESE_SWAP = {"一": "三", "二": "五", "三": "七", "四": "九", "五": "二",
                "六": "八", "七": "一", "八": "四", "九": "六", "十": "七",
                "兩": "六"}
UNITS = ("人", "元", "萬", "億", "千", "百", "個", "位", "名", "家",
         "處", "座", "件", "次", "成", "倍", "年", "月", "日", "天",
         "點", "分", "秒", "歲", "屆", "條", "隻", "頭", "棟", "戶",
         "公斤", "公里", "公尺", "公分", "度", "％", "%", "族", "村",
         "鄉", "鎮", "縣", "市", "班", "隊", "組", "場", "波", "輛")
MIN_TRUNCATE = 8


def _copy(item, subtitle):
    out = dict(item)
    out["subtitle"] = subtitle
    return out


def mispair(items):
    """Put a distant entry's subtitle on each one. Should never be 高.

    Distant, not adjacent: neighbouring subtitles in a news bulletin are
    often about the same story, and a probe that is accidentally still a
    fair pair proves nothing.
    """
    if len(items) < 2:
        return []
    out = []
    shift = max(1, len(items) // 2)
    for position, item in enumerate(items):
        other = items[(position + shift) % len(items)]
        if other["subtitle"] == item["subtitle"]:
            continue
        out.append(_copy(item, other["subtitle"]))
    return out


def _renumbered(subtitle):
    """The subtitle with its first number changed, or None."""
    found = DIGITS.search(subtitle)
    if found:
        digits = found.group()
        swapped = str((int(digits[0]) + 3) % 10) + digits[1:]
        if swapped == digits:
            swapped = str((int(digits[0]) + 5) % 10) + digits[1:]
        return subtitle[:found.start()] + swapped + subtitle[found.end():]
    for position, char in enumerate(subtitle):
        if char not in CHINESE:
            continue
        rest = subtitle[position + 1:]
        carries_fact = False
        for unit in UNITS:
            if rest.startswith(unit):
                carries_fact = True
        if not carries_fact:
            continue
        return (subtitle[:position] + CHINESE_SWAP[char] + rest)
    return None


def renumber(items):
    """Change one number in the subtitle. Should not stay 高."""
    out = []
    for item in items:
        changed = _renumbered(item["subtitle"])
        if changed is None or changed == item["subtitle"]:
            continue
        out.append(_copy(item, changed))
    return out


def truncate(items):
    """Keep only the subtitle's first half. Should not stay 高.

    This is the 中 case made unmissable: the subtitle now says less than
    the Formosan line does, which is exactly 「華語行少一個子句」.
    """
    out = []
    for item in items:
        subtitle = item["subtitle"]
        if len(subtitle) < MIN_TRUNCATE:
            continue
        out.append(_copy(item, subtitle[:len(subtitle) // 2]))
    return out


PROBES = {"mispair": mispair, "renumber": renumber, "truncate": truncate}
