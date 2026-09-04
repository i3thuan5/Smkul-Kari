#!/usr/bin/env python3
"""One episode through the speech side: audio -> the two-line SRT.

    python3 -m scripts.news.asrmt_run <srt_name> [--step NAME]

Steps, each skipped when its output already exists (a rerun continues,
never redoes paid work):

    words           whole-episode vosk decode -> 2-asr/1-words/
    entries         chain rows + word projection -> 2-asr/2-entries/
    raw             ASR x subtitle two-line render -> 2-asr/3-srt-raw/

`3-srt-raw` is the deliverable and the end of the line. An align
extension -- machine translation, sentence segmentation, misalignment
detection, a six-line review render and a semantically merged one -- once
sat above it; the semantic merge was piloted on one episode, did not work
out, and the whole extension has been removed.

The audio file is expected at kithann/out/asrmt/<srt_name>/audio.mp3
(fetched via sftp.sh); its duration must match the cue timeline within
one second or nothing runs at all.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from scripts.asrmt import bisrt
from scripts.asrmt import project
from scripts.news import make_srt
from scripts.news import paths
from scripts.news import rebuild
from scripts.srtlib import assemble
from scripts import lowpri
from scripts.errors import PipelineError

JSON = ".json"
MT_URL = "https://ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil"
MODEL_ID = "ILRDF/kaldi_formosan_250514_%s"

# inventory 的族語別(英) 與 HF 模型 repo 的拼法有五處不同
MODEL_NAME_FIX = {"SaySiyat": "Saisiyat", "Pinuyumayan": "Puyuma",
                  "Hla'alua": "Saaroa", "Cou": "Tsou", "Thau": "Thao"}
MODEL_ETHNICITIES = {"Amis", "Atayal", "Bunun", "Kanakanavu", "Kavalan",
                     "Paiwan", "Puyuma", "Rukai", "Saaroa", "Saisiyat",
                     "Sakizaya", "Seediq", "Thao", "Truku", "Tsou",
                     "Yami"}


def model_id_of(ethnicity):
    fixed = MODEL_NAME_FIX.get(ethnicity, ethnicity)
    if fixed not in MODEL_ETHNICITIES:
        raise PipelineError("no ASR model known for ethnicity %r" % ethnicity)
    return MODEL_ID % fixed


def _mp3_cell_path(cell, slot):
    """One catalogue cell -> the path naming this slot, or None.

    The catalogue sometimes packs several paths into one cell separated
    by ";" -- pick the one naming this slot.
    """
    candidates = []
    for part in cell.split(";"):
        if part.strip():
            candidates.append(part.strip())
    if not candidates:
        return None
    for part in candidates:
        if slot in part:
            return part
    return candidates[0]


def mp3_remote(srt_name, rows):
    """The episode's mp3 path on the SFTP host, from the catalogue."""
    date = "%s-%s-%s" % (srt_name[0:4], srt_name[4:6], srt_name[6:8])
    slot = srt_name.split("_")[2]
    for row in rows:
        if row["播出日期"] != date or row["播出時段"] != slot:
            continue
        chosen = _mp3_cell_path(row["音檔位置(mp3)"].strip(), slot)
        if chosen is not None:
            return "/docker/" + chosen
    raise PipelineError("no mp3 in the catalogue for %s" % srt_name)


AMI_CODES = ["ami_Coas", "ami_Heng", "ami_Mala", "ami_Sout", "ami_Xiug"]
DIALECT_SAMPLE = 50

ANCHORS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "anchors_ami.json")


_REDO = False


def set_redo(on):
    """Make steps run again even when their output is already there.

    Steps skip finished work so an interrupted batch resumes instead of
    paying for the vosk decode twice. The one operation that must not
    skip is the one the spec names: when the picture side's timeline
    changes, the speech side is projected onto it again, and the old
    entries are precisely what has to go. Without a switch the only way
    to do that is deleting files by hand next to `1-words`, which costs
    hours to regenerate if the hand slips.
    """
    global _REDO
    _REDO = bool(on)


def step_needed(path):
    return _REDO or not os.path.exists(path)


def verify_audio(srt_name, actual, expected, tolerance=1.0):
    """Same timeline or nothing (spec: 音檔時長不符 -> fail loud)."""
    if abs(actual - expected) > tolerance:
        raise PipelineError(
            "%s: 音檔時長 %.3fs 與 cue 軸 %.3fs 差超過 %.1fs——"
            "音檔與時間軸不同源，中止；改抓 mxf 抽音再來"
            % (srt_name, actual, expected, tolerance))


def _stage(name, srt_name, suffix=""):
    """This episode's file in a speech-side stage folder, folder created.

    The month layer comes from `paths.stage_path`, the same way the picture
    side gets it -- both technique directories are laid out alike, so one
    episode is one name in both.
    """
    path = paths.stage_path(os.path.join(paths.ASR_DIR, name),
                            srt_name, suffix)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _workdir(srt_name):
    folder = os.path.join(paths.ROOT, "kithann", "out", "asrmt", srt_name)
    os.makedirs(folder, exist_ok=True)
    return folder


def _entry_of(srt_name):
    for entry in paths.load_inventory():
        if entry["srt_name"] == srt_name:
            return entry
    raise PipelineError("%s is not in the inventory" % srt_name)


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip())


def _cues_path(srt_name, slug):
    """This episode's cue timeline, wherever it is right now.

    The store holds it once `publish` has moved it in; before that it is
    still in the work dir. Doing an episode end to end runs the speech side
    first -- OCR, then 3-srt-raw, then publish -- so looking only in the
    store would mean waiting for a step that is itself waiting for this one.

    `.B.work` is the one that counts: `make_all` assembled the delivered SRT
    from it and `publish` moves that same cues.json into the store, so both
    sides read one timeline and the two SRTs stay line-for-line aligned.
    """
    stored = paths.stage_path(paths.KARI_CUES, srt_name, JSON)
    if os.path.exists(stored):
        return stored
    work = os.path.join(paths.WORK,
                        paths.check_name(slug, "slug") + ".B.work")
    pending = paths.cues_to_read(work)
    if pending:
        return pending
    raise PipelineError(
        "%s 揣無時間軸：store 佮 work dir 攏無（%s、%s）"
        % (srt_name, stored, work))


def _cues_duration(srt_name):
    with open(_cues_path(srt_name, _entry_of(srt_name)["slug"]),
              encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("duration"):
        return float(manifest["duration"])
    last = 0.0
    for cue in manifest["cues"]:
        last = max(last, cue["end"])
    return last


def _audio(srt_name):
    path = os.path.join(_workdir(srt_name), "audio.mp3")
    if not os.path.exists(path):
        raise PipelineError("no audio at %s -- fetch it with sftp.sh first"
                            % path)
    verify_audio(srt_name, _probe_duration(path), _cues_duration(srt_name))
    return path


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _save(doc, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False)


# ------------------------------------------------------------------ steps


def step_words(srt_name, ethnicity_en):
    out = _stage("1-words", srt_name, JSON)
    if not step_needed(out):
        print("1-words 已存在，跳過")
        return
    from huggingface_hub import snapshot_download
    from scripts.asrmt import asr
    model_id = model_id_of(ethnicity_en)
    audio = _audio(srt_name)
    print("解碼", audio)
    record = asr.decode(audio, snapshot_download(model_id), srt_name,
                        model_label=model_id)
    asr.write_record(record, out)
    print("1-words:", len(record["words"]), "詞,",
          len(record["sents"]), "語音句")


def _chain_rows(srt_name):
    """The delivered SRT's chain rows, synthesised rebuild-style."""
    work = tempfile.mkdtemp(prefix="asrmt-entries-")
    try:
        timeline = paths.coarse_cues(work)
        os.makedirs(os.path.dirname(timeline), exist_ok=True)
        shutil.copy2(_cues_path(srt_name, _entry_of(srt_name)["slug"]),
                     timeline)
        _save(rebuild.episode_transcripts(srt_name),
              os.path.join(work, "transcripts.json"))
        manifest, records = make_srt.build(work)
        records = make_srt.drop_leader(records)
        entries = make_srt.entries_from(records)
        return assemble.chain_with_spans(
            entries, duration=manifest.get("duration"))
    finally:
        shutil.rmtree(work)


def step_entries(srt_name):
    out = _stage("2-entries", srt_name, JSON)
    if not step_needed(out):
        print("2-entries 已存在，跳過")
        return
    words_doc = _load(_stage("1-words", srt_name, JSON))
    rows = _chain_rows(srt_name)
    for row in rows:
        row["subtitle"] = row.pop("text")
    projected, unassigned = project.project(words_doc["words"], rows)
    for row in projected:
        row["zh"] = {}
        row["formosan_from_zh"] = {}
    doc = {"srt_name": srt_name, "src_lang": None, "primary": "ailabs",
           "entries": projected, "unassigned_words": unassigned}
    _save(doc, out)
    print("2-entries:", len(projected), "條目,",
          len(unassigned), "詞未落窗")


def _entries_path(srt_name):
    return _stage("2-entries", srt_name, JSON)


def step_raw(srt_name):
    doc = _load(_entries_path(srt_name))
    out = _stage("3-srt-raw", srt_name, ".srt")
    bisrt.write(out, bisrt.raw_body(doc["entries"]))
    print("3-srt-raw 寫出", out)


# The default pipeline ends at the raw SRT (使用者裁定)。 Everything
# after -- translation, segmentation, detection, review, complete --
# is the align extension, run only when named via --step.
STEPS = [("words", None), ("entries", None), ("raw", None)]


def main(argv=None):
    lowpri.be_nice()   # 長時間ê重工，莫kā機器食牢去
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt_name")
    ap.add_argument("--step", default="all",
                    help="words|entries|raw|all")
    ap.add_argument("--redo", action="store_true",
                    help="產出已經有嘛閣做一擺（時間軸換版了後重投影）")
    args = ap.parse_args(argv)
    paths.check_srt_name(args.srt_name)

    set_redo(args.redo)
    entry = _entry_of(args.srt_name)
    runners = {
        "words": lambda: step_words(args.srt_name, entry["族語別(英)"]),
        "entries": lambda: step_entries(args.srt_name),
        "raw": lambda: step_raw(args.srt_name),
    }
    if args.step == "all":
        for name, _ in STEPS:
            runners[name]()
        return
    if args.step not in runners:
        raise PipelineError("unknown step %r" % args.step)
    runners[args.step]()


if __name__ == "__main__":
    sys.exit(main())
