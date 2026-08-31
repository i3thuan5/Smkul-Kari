#!/usr/bin/env python3
"""Write `reread`'s segments into the timeline: one cue becomes several.

`reread` finds how many sentences a mis-cut cue actually holds and when each
one is on screen. Appending them into that cue's cell recovers the words but
leaves the timing wrong -- 20210220_051 cue 735 ends up as a single 27.58s
subtitle carrying sixteen sentences. Read as text that is an improvement;
used as training data for speech recognition it is worse than the gap it
replaced, because the audio no longer lines up with anything and nothing
about the file says so.

This module makes the split real. The cue is replaced by one cue per
segment, and everything after it moves up.

RENUMBERING IS THE DANGEROUS PART
---------------------------------
The vision TSVs are keyed by cue number. Split cue 735 into sixteen and
every later cue gains fifteen; if the timeline moves and the TSVs do not,
every subsequent line lands on the wrong subtitle. `ingest` does catch it --
it refuses a TSV naming cues it was not given -- but only after the fact, so
the two are changed together here rather than in separate passes.

The functions are deliberately small and pure: `replace` moves the timeline,
`shift` moves the TSV rows to match, `place` fills the new rows in. Nothing
here reads or writes a file; the caller supplies the data and decides when
to commit it.
"""
from scripts.errors import PipelineError

# Recognitions the existing data got wrong, normalised before comparing so
# the gate does not read a deliberate correction as a loss.
#
# 牝 -> 牠: three readers of 20210215_046 confirmed it independently, one
# comparing the glyph at 5x against Noto Serif CJK -- the right half is 也
# (closed horizontal, long hook), not 匕. The stronger evidence is that the
# existing data contradicts itself: cue 290 has 牠 while 136/139/146/100
# have 牝, over the same glyph on screen. Twenty lines across four files in
# the whole corpus.
# 會使加入這張表ê門檻：既有資料**家己相矛盾**——仝一个字形佇仝一集
# 寫做兩種。無這个證據就莫加。
#
# 反面例：`者老`／`耆老` 兩種寫法佇全語料庫**攏真實存在**（耆老 145
# 擺、者老 18 擺），20210213_044 段 619.05／622.04 放大 4 倍確認畫面
# 就是「者老」（耂+日，無「耆」彼撇匕）。彼是播出端家己ê寫法，毋是
# 辨識掠毋著；若kā伊正規化做「耆老」，就是kā著ê改做毋著ê。
#
# 判準：**播出端本底就有ê錯字照抄；既有辨識掠毋著ê才更正。**
# Normalised **for comparison only** -- what gets written is what the
# reader saw. These are pairs where the two spellings mean the same cue,
# so a difference between them is a correction, not a lost word, and the
# gate must not read it as one.
#
# `者老`/`耆老` was deliberately left out for a while: both spellings are
# genuinely in the corpus, so which one is "right" was a human call. 使用者
# 裁定 2026-08-31 -- typos get corrected to Taiwanese traditional forms --
# settles it. Leaving it out cost 20210208_039晚 cue 298 and the two new
# sentences behind it (`啊呀漢人今天都休息`, `準備吃團圓飯了`).
FIXES = {"牝": "牠", "者老": "耆老",
         # 簡體：畫面頂懸真正有，讀者這馬會訂正，既有ê無。
         "统": "統", "带": "帶", "经": "經",
         # 日式異體
         "経": "經"}


def normalise(text):
    """Text with known bad recognitions corrected, for comparison only."""
    for bad, good in FIXES.items():
        text = text.replace(bad, good)
    return text


def survives(old, new, neighbours):
    """Would splitting this cue keep every word it already carries?

    `old` is the cell being replaced, `new` the segments joined back up,
    `neighbours` the text the cues around it hold. True means the split is
    safe to make.

    The direction of the neighbour test is the whole game. Asking it both
    ways -- "the lost piece contains a neighbour, or a neighbour contains
    it" -- lets a neighbour holding a mere FRAGMENT vouch for the whole
    sentence, which is how 20210221_052 cue 60 lost 搶搶搶: the reread kept
    only the head and tail, and cue 61's 下手(預定)手刀要快 is a fragment of
    what went missing. The lost piece has to be findable IN a neighbour.
    """
    old, new = normalise(old.strip()), normalise(new.strip())
    if not old or old in new:
        return True
    near = set()
    for text in neighbours:
        near.add(normalise(text.strip()))
    for piece in old.replace(new, "\x00").split("\x00"):
        if piece and not any(piece in t for t in near):
            return False
    return True


# 厝邊看外遠。句子跨界頂多跨一格，兩格是留ê寬。
REACH = 2


def admit(old, new, reach=REACH):
    """Which of the split cues are safe to write, judged as one batch.

    `old` maps cue number to the text it holds now; `new` maps cue number
    to the segments joined back up, for the cues that split. The result is
    the set of cue numbers to write.

    ONE CUE AT A TIME IS NOT ENOUGH
    -------------------------------
    A sentence that straddles a cue boundary gets given to whichever cue
    holds most of it, which often means it moves INTO THE NEIGHBOUR. It is
    not lost; it is somewhere else in the same write. Judging each cue
    against its neighbours' OLD text cannot see that, and blocks the split
    that was fixing the error.

    20210206_037 cue 498 is the case that found this:

        existing  497 古琉璃珠的圖騰   498 樣式來製作
        on screen 2.00s of cue 498's 2.38s is 很像古琉璃珠;
                  樣式來製作 is cue 497's tail crossing the line by 0.34s
        reread    497 -> 古琉璃珠的圖騰 + 樣式來製作
                  498 -> 很像古琉璃珠

    Blocking 498 "because 樣式來製作 would be lost" leaves that sentence in
    two places and keeps 很像古琉璃珠 out of the corpus for good -- the gate
    doing damage in the name of safety.

    So a neighbour vouches with its NEW text once it is itself admitted,
    and with its old text while it is not. A cue that is blocked never gets
    written, so it must not vouch for anything with text it will not hold.
    The admitted set only grows, so repeating until it stops settles.
    """
    admitted = set()
    while True:
        grew = False
        for cue in sorted(new):
            if cue in admitted:
                continue
            near = set()
            for k in range(cue - reach, cue + reach + 1):
                if k == cue:
                    continue
                if k in admitted:
                    text = new[k]
                else:
                    text = old.get(k, "")
                if text.strip():
                    near.add(text.strip())
            if survives(old.get(cue, ""), new[cue], near):
                admitted.add(cue)
                grew = True
        if not grew:
            return admitted


def unsplit_but_changed(old, single):
    """Cues the reread left whole but read differently from what is stored.

    `single` maps cue number to the text a reader wrote for a cue that came
    back as ONE segment. A cue like that is skipped by the splitter -- there
    is nothing to split -- so whatever the reader saw is thrown away without
    a word. Sometimes that is right (the reader misread a character) and
    sometimes it is the segmenter failing on a bright, still background and
    the reader running two sentences together to fit them in one cell.

    The two look identical in the data, so this only reports.
    """
    out = []
    for cue in sorted(single):
        got = normalise(single[cue].strip())
        if not got:
            continue
        if got not in normalise(old.get(cue, "").strip()):
            out.append(cue)
    return out


def replace(cues, at, parts):
    """The timeline with cue `at` replaced by one cue per part.

    Indices are rebuilt from one across the whole list, so the result is
    always a clean 1..N with no holes and no duplicates.
    """
    found = None
    for cue in cues:
        if cue["index"] == at:
            found = cue
            break
    if found is None:
        raise PipelineError("時間軸內底揣無 cue %s" % at)
    out = []
    for cue in cues:
        if cue["index"] != at:
            out.append(dict(cue))
            continue
        for part in parts:
            fresh = dict(cue)
            fresh["start"] = part["start"]
            fresh["end"] = part["end"]
            out.append(fresh)
    for n, cue in enumerate(out, 1):
        cue["index"] = n
    return out


def shift(rows, at, extra):
    """The TSV rows renumbered for a cue that became `extra` more cues.

    The split cue's own row is dropped: its text was the whole stretch run
    together, and each new cue gets its own line from `place`.
    """
    out = {}
    for index, text in rows.items():
        if index == at:
            continue
        if index < at:
            out[index] = text
        else:
            out[index + extra] = text
    return out


def place(rows, at, texts):
    """`rows` with one row per new cue, starting at `at`."""
    out = dict(rows)
    for n, text in enumerate(texts):
        out[at + n] = text
    return out
