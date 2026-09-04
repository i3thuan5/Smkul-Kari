"""Synthetic-video fixture shared by the end-to-end tests.

Burns a known SRT into a generated 1080p clip, runs the real pipeline over
it, and diffs the recovered cues against the ground truth. This is the only
way to check the timing maths against something other than itself.
"""
import argparse
import json
import os
import subprocess

import numpy as np

from scripts import datadirs
from scripts.ocr import cli as subs2srt
from scripts.srtlib import srt

CJK_FONT = "Noto Sans CJK TC"

GROUND_TRUTH = [
    (2.0, 5.0, "Ati han ako ko singsi"),
    (5.0, 8.5, "Hay na ilisin hananay"),          # back-to-back with above
    (10.0, 10.9, "mako"),                          # short cue
    (12.0, 18.0, "kafana'an no mako a demak"),     # long cue
    (19.5, 22.0, "Kinci ko somowalay"),
    (22.5, 25.0, "o kafana'an no niyam"),
    (26.0, 29.0, "sowal no Pangcah"),
]

GROUND_TRUTH_HAN = [
    (2.0, 5.0, "我就請我們的老師"),
    (5.0, 8.5, "關於豐年祭從小到現在"),
    (10.0, 10.9, "是的"),
    (12.0, 18.0, "我所經歷過的事情"),
    (19.5, 22.0, "來說明這部分"),
    (22.5, 25.0, "我們所知道的"),
    (26.0, 29.0, "阿美族的語言"),
]


def write_srt(entries, path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(srt.render_srt(entries))
        handle.write("\n")


def build_fixture(path, entries, band=False, duration=31):
    """Burn `entries` into a synthetic 1080p clip with moving content."""
    srt_path = path + ".srt"
    write_srt(entries, srt_path)

    style = ("FontName=%s,FontSize=40,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,"
             "Alignment=2,MarginV=30" % CJK_FONT)
    chain = []
    if band:
        # Mimic video A: an opaque yellow bar *behind* the text. libass puts
        # a MarginV=30 Alignment=2 line at roughly y=830..945, so the bar has
        # to cover that, not merely sit near the bottom of the frame.
        chain.append("drawbox=x=0:y=815:w=1920:h=150:"
                     "color=yellow@1.0:t=fill")
    escaped = srt_path.replace(":", r"\:")
    chain.append("subtitles=%s:force_style='%s'" % (escaped, style))

    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi",
        "-i", "testsrc2=size=1920x1080:rate=30:duration=%d" % duration,
        "-vf", ",".join(chain),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-pix_fmt", "yuv420p", path,
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
    return srt_path


def match_cues(truth, found, tolerance):
    """Pair ground-truth cues with detected cues by start time."""
    pairs = []
    unmatched = []
    remaining = list(found)
    for start, end, text in truth:
        best = None
        for candidate in remaining:
            delta = abs(candidate["start"] - start)
            if best is None or delta < best[0]:
                best = (delta, candidate)
        if best is not None and best[0] <= tolerance:
            pairs.append(((start, end, text), best[1]))
            remaining.remove(best[1])
        else:
            unmatched.append((start, end, text))
    return pairs, unmatched, remaining


def run_end_to_end(tmpdir, band, entries, lang, label, fps=5.0):
    video = os.path.join(tmpdir, "fixture_%s.mp4" % label)
    build_fixture(video, entries, band=band)

    work = os.path.join(tmpdir, "work_%s" % label)
    os.makedirs(work, exist_ok=True)
    args = argparse.Namespace(
        video=video, out=work, region=None, presets=None, preset=None,
        autodetect=True, fps=fps,
        start=0.0, duration=None, min_ink=120, change=0.35, min_stable=2,
        min_duration=0.30, samples=60, lang=lang, sheets=False,
        sheet_megapixels=1.1, progress=False)
    subs2srt.stage_cues(args)

    with open(datadirs.cues_to_read(work), encoding="utf-8") as handle:
        manifest = json.load(handle)

    tolerance = 1.0 / fps + 0.05
    pairs, missed, extra = match_cues(entries, manifest["cues"], tolerance)

    print("\n--- end-to-end [%s] ---" % label)
    print("region detected : %s" % manifest["region"])
    print("truth cues      : %d" % len(entries))
    print("detected cues   : %d" % len(manifest["cues"]))
    print("matched         : %d" % len(pairs))
    print("missed          : %d" % len(missed))
    print("spurious        : %d" % len(extra))

    start_errs = []
    end_errs = []
    for (t_start, t_end, _), cue in pairs:
        start_errs.append(cue["start"] - t_start)
        end_errs.append(cue["end"] - t_end)
    if start_errs:
        print("start error     : mean %+.3fs  max |%.3f|s"
              % (float(np.mean(start_errs)), float(np.max(np.abs(
                  start_errs)))))
        print("end error       : mean %+.3fs  max |%.3f|s"
              % (float(np.mean(end_errs)), float(np.max(np.abs(end_errs)))))
    for item in missed:
        print("  MISSED  %.2f-%.2f  %s" % item)
    for cue in extra:
        print("  EXTRA   %.2f-%.2f" % (cue["start"], cue["end"]))

    # Build these through the real parser rather than by hand: a
    # hand-rolled Namespace silently rots the moment the CLI grows an
    # option, and the stage then dies on a missing attribute instead of
    # testing anything.
    parser = subs2srt.build_parser()
    ocr_args = parser.parse_args(["ocr", work])
    ocr_args.progress = False
    subs2srt.stage_ocr(ocr_args)

    srt_out = os.path.join(tmpdir, "out_%s.srt" % label)
    srt_args = parser.parse_args(["srt", work, "-o", srt_out])
    subs2srt.stage_srt(srt_args)

    with open(os.path.join(work, "transcripts.json"), encoding="utf-8") as fh:
        texts = json.load(fh)
    line_name = manifest["lines"][0]["name"]

    exact = 0
    print("  text comparison (tesseract):")
    for (t_start, _, truth_text), cue in pairs:
        got = (texts.get(str(cue["index"]), {}).get(line_name) or "").strip()
        want = truth_text.strip()
        if lang.startswith("chi"):
            want = want.replace(" ", "")
        flag = "ok " if got == want else "DIFF"
        if got == want:
            exact += 1
        else:
            print("    %s want=%r got=%r" % (flag, want, got))
    print("  exact text matches: %d/%d" % (exact, len(pairs)))

    with open(srt_out, encoding="utf-8") as handle:
        reparsed = srt.parse_srt(handle.read())
    print("  final SRT parses back to %d entries" % len(reparsed))

    return {
        "label": label,
        "truth": len(entries),
        "detected": len(manifest["cues"]),
        "matched": len(pairs),
        "missed": len(missed),
        "extra": len(extra),
        "exact_text": exact,
        "start_errs": start_errs,
        "end_errs": end_errs,
        "srt_entries": len(reparsed),
    }


def check_odd_region(video, fps=5.0):
    """Pin the vf_crop rounding bug: an all-odd box must not desynchronise.

    vf_crop is zero-copy, so for yuv420p it rounds width/height/x/y down to
    even -- 107 becomes 106 -- and says nothing above -v verbose. A reader
    consuming w*h*3 bytes then slips a row per frame and every frame is a
    torn blend of two, which looks like plausible cue boundaries rather than
    a crash. crop_chain() asks for `exact=1`; if that ever stops being
    applied, stream_region() raises here instead of corrupting quietly.
    """
    region = (101, 845, 1043, 107)
    seen = 0
    from scripts.ocr import cuelib
    for _, frame in cuelib.stream_region(video, region, fps, start=0.0,
                                         duration=6.0):
        if frame.shape != (107, 1043, 3):
            raise AssertionError("frame shape %s, wanted (107, 1043, 3)"
                                 % (frame.shape,))
        seen += 1
    return seen


def require_fixture_tools():
    """Fail loudly on a missing dependency instead of on its symptoms.

    Without a CJK font libass silently renders every Chinese glyph as a tofu
    box. The pipeline then behaves plausibly -- it finds a band, cuts cues,
    runs OCR -- and only the final text comparison looks wrong, which reads
    exactly like a regression in the code under test. Diagnosing that from
    the symptoms costs far more than this check.
    """
    missing = []
    for tool in ("ffmpeg", "tesseract"):
        found = subprocess.run(["which", tool], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if found.returncode != 0:
            missing.append(tool)

    langs = subprocess.run(["tesseract", "--list-langs"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if b"chi_tra" not in langs.stdout:
        missing.append("tesseract-ocr-chi-tra")

    fonts = subprocess.run(["fc-list"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
    if b"CJK" not in fonts.stdout:
        missing.append("fonts-noto-cjk (否則中文會渲染成豆腐塊)")

    if missing:
        raise SystemExit(
            "end-to-end 測試缺少系統相依：\n  - %s\n"
            "安裝：sudo apt-get install ffmpeg tesseract-ocr "
            "tesseract-ocr-chi-tra fonts-noto-cjk\n"
            "（只跑單元測試：tox -e unittest）" % "\n  - ".join(missing))
