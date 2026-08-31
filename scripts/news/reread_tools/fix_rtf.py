"""Renumber the 4-vision-rtf overlay to match a resplit episode.

`rebuild` composes each episode's text from 3-vision AND 4-vision-rtf, and
the rtf side wins where both have a cue. That overlay is keyed by cue
number, so a resplit that renumbers the timeline leaves it pointing at the
wrong cues -- and because it wins, its stale text overwrites the correct
reading. `rebuild --verify` is what catches this
nothing else would.

The old numbering is recovered from git (the store is a repo and none of
this session's work is committed), the mapping is recomputed the same way
the resplit computed it, and cues that were split are dropped from the
overlay: the reread supplies per-segment text for those, which is what the
screen actually showed.
"""
import json
import os
import subprocess
import sys

NAME, SLUG = sys.argv[1], sys.argv[2]
WRITE = "--write" in sys.argv
RTF = "Kari-SRT/news/1-ocr/4-vision-rtf/2021-02/%s" % NAME
W = "kithann/out/mxf/%s.B.work" % SLUG

# 無疊層就免做。這步本底是「該集有 4-vision-rtf 才走」ê，毋過鏈是
# 手寫ê，20210217_048晚 就按呢無條件走落去，死佇提舊編號彼步
# （伊ê cues.json 是 staged 猶未 commit，`git show HEAD:` 揣無）。
# 予伊家己判，鏈就免記這條。
if not os.path.isdir(RTF):
    print("%s 無 4-vision-rtf，免重編號" % NAME)
    raise SystemExit(0)

old_cues = json.loads(subprocess.run(
    ["git", "-C", "Kari-SRT", "show",
     "HEAD:news/1-ocr/1-cues/2021-02/%s.json" % NAME],
    capture_output=True, text=True, check=True).stdout)
old_cues = old_cues["cues"] if isinstance(old_cues, dict) else old_cues
new_cues = json.load(open(os.path.join(W, "cues.json"), encoding="utf-8"))
new_cues = new_cues["cues"] if isinstance(new_cues, dict) else new_cues
print("舊 %d cue → 新 %d cue" % (len(old_cues), len(new_cues)))

# 舊 cue ê起點時間是無變ê，用時間鬥出對照表
starts = {}
for c in new_cues:
    starts.setdefault(round(c["start"], 2), c["index"])
mapping, split = {}, set()
for c in old_cues:
    hit = starts.get(round(c["start"], 2))
    if hit is None:
        print("  ！舊 cue %d（%.2f）鬥無新ê" % (c["index"], c["start"]))
        continue
    mapping[c["index"]] = hit
# 一條舊 cue 若切做幾若條，新ê彼幾條ê時間攏佇伊內底
for c in old_cues:
    if c["index"] not in mapping:
        continue
    lo = mapping[c["index"]]
    n = 0
    for d in new_cues:
        if d["index"] >= lo and d["start"] < c["end"] - 1e-6:
            n += 1
        elif d["index"] > lo:
            break
    if n > 1:
        split.add(c["index"])
print("鬥著 %d 條，其中予切開ê %d 條" % (len(mapping), len(split)))

rows = []
for f in sorted(os.listdir(RTF)):
    if not f.endswith(".tsv"):
        continue
    for line in open(os.path.join(RTF, f), encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 3 and p[0].isdigit():
            rows.append((int(p[0]), p[2]))
kept, dropped = [], []
for old, text in rows:
    if old in split:
        dropped.append(old)
    elif old in mapping:
        kept.append((mapping[old], text))
    else:
        dropped.append(old)
print("rtf 疊層：%d 逝 → 留 %d、擲 %d（予切開ê，重讀已經逐段供字）"
      % (len(rows), len(kept), len(dropped)))
if not WRITE:
    print("（dry run）")
    raise SystemExit(0)
for f in sorted(os.listdir(RTF)):
    if f.endswith(".tsv"):
        os.remove(os.path.join(RTF, f))
kept.sort()
for k in range(0, len(kept), 96):
    with open(os.path.join(RTF, "b%02d.tsv" % (k // 96 + 1)), "w",
              encoding="utf-8") as h:
        for i, text in kept[k:k + 96]:
            h.write("%d\than\t%s\n" % (i, text))
idx = sorted(i for i, _ in kept)
for p in (os.path.join(W, "from_rtf.json"),
          "Kari-SRT/news/1-ocr/2-from_rtf/2021-02/%s.json" % NAME):
    if os.path.exists(os.path.dirname(p)):
        json.dump(idx, open(p, "w", encoding="utf-8"), ensure_ascii=False)
print("寫入：rtf %d 逝、from_rtf %d 條" % (len(kept), len(idx)))
