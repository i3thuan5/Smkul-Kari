#!/usr/bin/env python3
"""Recognisers: turning a cue strip into text.

Two backends, neither of them the one that produced the delivered corpus --
that text was read off contact sheets by a human. Tesseract is kept because
it needs no key and no network, which is what the self-test can exercise;
the API backend is kept because it is what a large unattended pass would
use. Both are proposals until somebody checks them.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

from scripts.subs2srt import cuelib


TESS_COMMON = [
    "-c", "load_system_dawg=0",
    "-c", "load_freq_dawg=0",
    "-c", "load_punc_dawg=0",
    "-c", "load_number_dawg=0",
    "-c", "load_unambig_dawg=0",
    "-c", "load_bigram_dawg=0",
]


def prep_for_tesseract(path, spec, scale=2):
    """Binarise a strip to dark glyphs on white, which tesseract prefers.

    Do not upscale much. These subtitles are already rendered large in a
    1080p frame, and enlarging a *binarised* image only interpolates new grey
    between strokes. Measured on 12 Amis and 17 Chinese hand-read lines,
    whole-line accuracy by scale factor:

        scale   1x     2x     3x     5x
        Amis    13.3%  20.0%   6.7%   6.7%
        Chinese 52.9%  47.1%  41.2%  29.4%

    so 2x suits the Latin rows and 1x the Chinese ones; 3x (the original
    guess, never measured) was the worst of both.
    """
    rgb = np.asarray(Image.open(path).convert("RGB"))
    mask = cuelib.text_mask(rgb, spec)
    page = np.full(mask.shape, 255, dtype=np.uint8)
    page[mask] = 0
    img = Image.fromarray(page, mode="L")
    if scale == 1:
        return img
    return img.resize((int(img.width * scale), int(img.height * scale)),
                      Image.LANCZOS)


def run_tesseract(img, lang, whitelist=None, tmp=None):
    img.save(tmp)
    cmd = ["tesseract", tmp, "stdout", "-l", lang, "--psm", "7"]
    cmd += TESS_COMMON
    if whitelist:
        cmd += ["-c", "tessedit_char_whitelist=%s" % whitelist]
    out = subprocess.run(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    return out.decode("utf-8", "replace").strip()


def ocr_tesseract(workdir, manifest, args):
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    tmp = os.path.join(workdir, "_tess_tmp.png")
    results = {}
    total = len(manifest["cues"])
    for position, cue in enumerate(manifest["cues"]):
        got = {}
        for line in manifest["lines"]:
            rel = cue["images"].get(line["name"])
            if not rel:
                continue
            scale = line.get("ocr_scale", args.ocr_scale)
            img = prep_for_tesseract(os.path.join(workdir, rel), spec,
                                     scale=scale)
            text = run_tesseract(img, line.get("lang", "eng"),
                                 line.get("whitelist"), tmp)
            got[line["name"]] = clean_text(text, line)
        results[str(cue["index"])] = got
        if args.progress and position % 25 == 0:
            sys.stderr.write("\r  ocr %d/%d" % (position, total))
            sys.stderr.flush()
    if args.progress:
        sys.stderr.write("\r%-32s\r" % "")
    if os.path.exists(tmp):
        os.remove(tmp)
    return results


def clean_text(text, line):
    out = text.replace("\n", " ").strip()
    if line.get("lang", "").startswith("chi"):
        out = out.replace(" ", "")
    while "  " in out:
        out = out.replace("  ", " ")
    return out


def ocr_claude_api(workdir, manifest, args):
    """Recognise strips with Claude vision through the Anthropic API.

    Kept separate from the offline path because it needs a key and costs
    money; the offline path is what the self-test exercises.
    """
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "claude-api engine needs the `anthropic` package: "
            "pip install anthropic")
    import base64

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("set ANTHROPIC_API_KEY to use --engine claude-api")

    client = anthropic.Anthropic()
    results = {}
    total = len(manifest["cues"])
    for position, cue in enumerate(manifest["cues"]):
        got = {}
        for line in manifest["lines"]:
            rel = cue["images"].get(line["name"])
            if not rel:
                continue
            with open(os.path.join(workdir, rel), "rb") as handle:
                blob = base64.standard_b64encode(handle.read()).decode()
            prompt = line.get("prompt") or default_prompt(line)
            message = client.messages.create(
                model=args.model,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": blob}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            parts = []
            for block in message.content:
                if block.type == "text":
                    parts.append(block.text)
            got[line["name"]] = clean_text("".join(parts).strip(), line)
        results[str(cue["index"])] = got
        if args.progress and position % 10 == 0:
            sys.stderr.write("\r  ocr %d/%d" % (position, total))
            sys.stderr.flush()
    if args.progress:
        sys.stderr.write("\r%-32s\r" % "")
    return results


def default_prompt(line):
    lang = line.get("lang", "")
    if lang.startswith("chi"):
        what = "one line of Traditional Chinese subtitle text"
    else:
        what = ("one line of Amis (Latin-script Formosan language) "
                "subtitle text; keep apostrophes and ^ exactly as shown")
    return ("This image is %s. Reply with the transcription only -- no "
            "quotes, no commentary, no translation. If the strip is blank, "
            "reply with an empty response." % what)
