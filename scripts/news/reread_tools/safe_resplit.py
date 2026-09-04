"""Split only the cues whose split provably loses no text.

The gate is per cue, not per episode. A reread can be right about twenty
cues and wrong about one -- 20210221_052 cue 792 came back with its first
segment blank (two sentences overprinted) and its second holding cue 793's
line, so its own sentence appears in neither. Splitting that one would turn
"crammed together" into "gone", which is the thing this whole exercise
exists to avoid.

So each cue is checked on its own and skipped if it fails. A skipped cue
keeps exactly what it has today.
"""
import glob
import json
import os
import sys
from scripts.news import paths, resplit

NAME = sys.argv[1]
WRITE = "--write" in sys.argv
D = paths.stage_path(paths.KARI_VISION, NAME)
RD = os.path.join("kithann/out/reread", NAME)

# 正本是 transcripts.json，毋是 TSV。
#
# `ingest` 是**合併**：TSV 內底無彼條 cue ê時，transcripts 內底舊ê
# 條目原封不動留咧。有 16 集ê TSV 無涵蓋規模ê cue（缺 74 到 474 逝
# 無等），彼寡是文稿（RTF）供字ê——文字干焦佇 transcripts.json。
# 對 TSV 讀，彼寡字就無去矣；閣較歹ê是編號一改，舊條目會指去**別
# ê cue**，字就走位，而且無一个所在會報錯。
W = None
for d in sorted(glob.glob("kithann/out/mxf/*.B.work")):
    stem = os.path.basename(d)[:-len(".B.work")]
    bits = stem.split("_")
    if bits[1] == NAME.split("_")[1] and bits[3] == NAME.split("_")[2]:
        W = d
        break
if W is None:
    raise SystemExit("揣無 work dir：%s" % NAME)
with open(os.path.join(W, "transcripts.json"), encoding="utf-8") as handle:
    store = json.load(handle)
rows = {}
for key, got in store.items():
    if key.isdigit():
        rows[int(key)] = got.get("han", "") if isinstance(got, dict) else ""

parts, segs = {}, {}
for f in sorted(glob.glob(os.path.join(RD, "read*.tsv"))):
    for line in open(f, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and "." in p[0]:
            c = int(p[1])
            n = int(p[0].split(".")[1])
            parts.setdefault(c, {})[n] = (p[2] if len(p) > 2 else "").strip()
for line in open(os.path.join(RD, "segments.tsv"), encoding="utf-8"):
    p = line.rstrip("\n").split("\t")
    segs.setdefault(int(p[1]), []).append(
        {"cue": int(p[1]), "part": int(p[2]),
         "start": float(p[3]), "end": float(p[4])})


def joined(cue):
    out = []
    for s in segs[cue]:
        t = parts.get(cue, {}).get(s["part"], "")
        if t and (not out or out[-1] != t):
            out.append(t)
    return "".join(out)


# 一集做伙判，毋是一條一條家己判。
#
# 句子跨過 cue 界線ê時，重讀會kā伊判予真正佔多數彼爿——嘛就是**搬去
# 厝邊彼格**。伊無不見，是徙位。一條一條提「新ê這格」佮「**舊ê**厝
# 邊」比ê時，看袂著這件事，煞kā本底teh改毋著ê彼刀擋落來。理路佮
# 20210206_037 cue 498 彼个案例記佇 `resplit.admit`。
after = {}
for cue in sorted(segs):
    if cue in rows and len(segs[cue]) >= 2:
        after[cue] = joined(cue)
keep = resplit.admit(rows, after)
ok, skip = [], []
for cue in sorted(after):
    if cue in keep:
        ok.append(cue)
    else:
        skip.append(cue)

# 切袂開ê 單段 cue，讀者若讀著無仝款——報出來，莫恬恬放捒。理路佮
# 20210219_050 cue 1115／1116 彼个案例記佇 `resplit.unsplit_but_changed`。
lone = {}
for cue in sorted(segs):
    if cue in rows and len(segs[cue]) == 1:
        lone[cue] = parts.get(cue, {}).get(segs[cue][0]["part"], "")
odd = resplit.unsplit_but_changed(rows, lone)

print("%s：切會開 %d 條，其中通過 %d 條、擋落 %d 條"
      % (NAME, len(after), len(ok), len(skip)))
for cue in skip[:12]:
    # 印規句，毋是差異片段——片段看無意思
    print("  擋 cue %-5d 既有：%s" % (cue, rows[cue].strip()[:30]))
if odd:
    print("  ── 切袂開、毋過讀者讀著無仝ê（%d 條，這支無動，家己判）──" % len(odd))
    for cue in odd[:12]:
        print("  cue %-5d 既有：%s" % (cue, rows[cue].strip()[:26]))
        print("  %11s 讀著：%s" % ("", lone[cue].strip()[:26]))
if not WRITE:
    print("（dry run）")
    raise SystemExit(0)

doc = json.load(open(os.path.join(W, "cues.json"), encoding="utf-8"))
cues = doc["cues"] if isinstance(doc, dict) else doc
for at in sorted(ok, reverse=True):
    got = segs[at]
    texts = [parts[at].get(s["part"], "") for s in got]
    cues = resplit.replace(cues, at, got)
    rows = resplit.shift(rows, at, len(got) - 1)
    rows = resplit.place(rows, at, texts)
assert len(cues) == len(rows) and sorted(rows) == list(range(1, len(cues) + 1))
if isinstance(doc, dict):
    doc["cues"] = cues
else:
    doc = cues
json.dump(doc, open(os.path.join(W, "cues.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
other = os.path.join(W.replace(".B.work", ".work"), "cues.json")
if os.path.exists(other):
    json.dump(doc, open(other, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
for f in glob.glob(os.path.join(D, "b*.tsv")):
    os.remove(f)
idx = sorted(rows)
for k in range(0, len(idx), 96):
    with open(os.path.join(D, "b%02d.tsv" % (k // 96 + 1)), "w",
              encoding="utf-8") as h:
        for i in idx[k:k + 96]:
            h.write("%d\than\t%s\n" % (i, rows[i]))
print("寫入：cue %d 條、TSV %d 逝、%d 檔" % (len(cues), len(idx), (len(idx)+95)//96))
