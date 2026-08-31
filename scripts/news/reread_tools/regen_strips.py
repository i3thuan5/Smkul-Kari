"""Regenerate strips + sheets + sheets.json from an already-updated cues.json.

Data only: it never touches cues.json or the TSVs. `strips` is a symlink
into the sibling .work dir, so the real directory is resolved first --
rmtree on the link leaves it in place and makedirs then fails, which is how
the first attempt stopped half way.
"""
import glob
import json
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scripts.ocr import cuelib

NAME, SLUG = sys.argv[1], sys.argv[2]
W = os.path.join("kithann/out/mxf", SLUG + ".B.work")
doc = json.load(open(os.path.join(W, "cues.json"), encoding="utf-8"))
cues = doc["cues"] if isinstance(doc, dict) else doc
spec = cuelib.MaskSpec.from_dict(
    (doc if isinstance(doc, dict) else {}).get("mask", {}))
_meta = doc if isinstance(doc, dict) else {}
region = tuple(_meta.get("region", [0, 722, 1920, 122]))
vid = os.path.join("kithann/out/mkv", NAME + ".mkv")

sdir = os.path.realpath(os.path.join(W, "strips"))
for f in glob.glob(os.path.join(sdir, "*.png")):
    os.remove(f)
os.makedirs(sdir, exist_ok=True)
print("%s：%d cue → %s" % (NAME, len(cues), sdir), flush=True)

for c in cues:
    frames = []
    for _ts, rgb in cuelib.stream_region(
            vid, region, fps=5.0, start=c["start"],
            duration=max(0.2, c["end"] - c["start"])):
        frames.append(rgb)
        if len(frames) >= 24:
            break
    if not frames:
        frames = [np.zeros((region[3], region[2], 3), np.uint8)]
    img = (np.median(np.stack(frames), axis=0).astype(np.uint8)
           if len(frames) >= 3 else frames[0])
    Image.fromarray(img).save(os.path.join(sdir, "%05d_han.png" % c["index"]))
    if c["index"] % 100 == 0:
        print("  %d/%d" % (c["index"], len(cues)), flush=True)

font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 20)
GUT, SCALE = 130, 0.62
sw, sh = int(region[2] * SCALE), int(region[3] * SCALE)
idx = [c["index"] for c in cues]
manifest = {}
for base in (os.path.join(W, "sheets"),
             os.path.join(W.replace(".B.work", ".work"), "sheets")):
    if not os.path.isdir(base):
        continue
    for f in glob.glob(os.path.join(base, "*.png")):
        os.remove(f)
shdir = os.path.realpath(os.path.join(W, "sheets"))
os.makedirs(shdir, exist_ok=True)
for k in range(0, len(idx), 4):
    group = idx[k:k + 4]
    sheet = Image.new("RGB", (GUT + sw, len(group) * (sh + 3)), "black")
    dr = ImageDraw.Draw(sheet)
    for r, i in enumerate(group):
        im = Image.open(
            os.path.join(sdir, "%05d_han.png" % i)).resize((sw, sh))
        sheet.paste(im, (GUT, r * (sh + 3)))
        dr.text((6, r * (sh + 3) + sh // 2 - 12), str(i),
                fill="yellow", font=font)
    fn = "sheet_%03d.png" % (k // 4 + 1)
    sheet.save(os.path.join(shdir, fn))
    manifest[fn] = group
json.dump(manifest,
          open(os.path.join(W, "sheets.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("  strips %d、sheets %d、sheets.json 好矣"
      % (len(idx), len(manifest)), flush=True)
