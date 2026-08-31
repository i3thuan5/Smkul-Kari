"""Cut every episode's flagged cues into segments and lay them out as sheets.

Resumable: an episode whose segments.tsv already exists is skipped, so this
survives an interruption without redoing finished work.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scripts.ocr import cuelib
from scripts.news import blind_cues, reread

OUT = "kithann/out/reread"
FONT = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 20)
GUT, SCALE = 130, 0.62


def one(name):
    dest = os.path.join(OUT, name)
    if os.path.exists(os.path.join(dest, "segments.tsv")):
        print("SKIP\t%s" % name, flush=True)
        return
    vid = os.path.join("kithann/out/mkv", name + ".mkv")
    if not os.path.exists(vid):
        print("NOVID\t%s" % name, flush=True)
        return
    doc = reread._timeline(name)
    spec = cuelib.MaskSpec.from_dict(doc.get("mask", {}))
    region = tuple(doc.get("region", reread.REGION))
    flagged = blind_cues.risky(doc["cues"])
    strips, segs = [], []
    for cue in flagged:
        rgbs, masks = [], []
        for _ts, rgb in cuelib.stream_region(vid, region, fps=reread.FPS,
                                             start=cue["start"],
                                             duration=cue["end"]
                                             - cue["start"]):
            rgbs.append(rgb)
            masks.append(cuelib.text_mask(rgb, spec))
        if not rgbs:
            continue
        for seg in reread.segments(cue, masks, frame_dt=1.0 / reread.FPS):
            i0 = int(round((seg["start"] - cue["start"]) * reread.FPS))
            i1 = max(i0 + 1, int(round(
                (seg["end"] - cue["start"]) * reread.FPS)))
            chunk = rgbs[i0:i1] or rgbs[-1:]
            if not reread.has_text(reread.median(masks[i0:i1] or masks[-1:])):
                continue
            img = (np.median(np.stack(chunk), axis=0).astype(np.uint8)
                   if len(chunk) >= 3 else chunk[0])
            strips.append(img)
            segs.append(seg)
    if not strips:
        print("EMPTY\t%s\t%d" % (name, len(flagged)), flush=True)
        return
    os.makedirs(dest, exist_ok=True)
    h, w = strips[0].shape[0], strips[0].shape[1]
    sw, sh = int(w * SCALE), int(h * SCALE)
    for k in range(0, len(strips), reread.PER_SHEET):
        idxs = range(k, min(k + reread.PER_SHEET, len(strips)))
        sheet = Image.new("RGB", (GUT + sw, len(idxs) * (sh + 3)), "black")
        dr = ImageDraw.Draw(sheet)
        for r, i in enumerate(idxs):
            sheet.paste(Image.fromarray(strips[i]).resize((sw, sh)),
                        (GUT, r * (sh + 3)))
            dr.text((6, r * (sh + 3) + sh // 2 - 12), reread.label(segs[i]),
                    fill="yellow", font=FONT)
        sheet.save(os.path.join(
            dest, "sheet_%03d.png" % (k // reread.PER_SHEET + 1)))
    with open(os.path.join(dest, "segments.tsv"), "w", encoding="utf-8") as h2:
        for seg in segs:
            h2.write("%s\t%d\t%d\t%.2f\t%.2f\n"
                     % (reread.label(seg), seg["cue"], seg["part"],
                        seg["start"], seg["end"]))
    sheets = (len(strips) + reread.PER_SHEET - 1) // reread.PER_SHEET
    print("DONE\t%s\t%d\t%d\t%d" % (name, len(flagged), len(segs), sheets),
          flush=True)


for name in blind_cues.delivered():
    try:
        one(name)
    except Exception as exc:                       # noqa: BLE001
        print("FAIL\t%s\t%r" % (name, exc), flush=True)
