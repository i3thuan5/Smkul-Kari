#!/usr/bin/env python3
"""One episode through the speech side: audio -> the graded SRTs.

    python3 -m scripts.news.asrmt_run <srt_name> [--step NAME]

Steps, each skipped when its output already exists (a rerun continues,
never redoes paid work):

    words           whole-episode vosk decode -> 2-asr/1-words/
    raw             ASR x subtitle two-line render -> 2-asr/2-srt-raw/

`words` is the only step that costs machine time; everything after it is
a projection plus a render, measured in milliseconds.

**The projection is not stored.** Entries are a pure function of
1-words and the picture side's timeline, so every step that needs them
recomputes them (`rows_of`). It used to be written out as a stage of its
own, which read like provenance but was a view: a re-projection rebuilt
the file and silently dropped everything that had been filled in on top
of it. What is worth keeping is kept content-addressed instead, in the
caches beside the stages.

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
from scripts.asrmt import dialects
from scripts.asrmt import glossary
from scripts.asrmt import judge
from scripts.asrmt import mtclient
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

# How many entries one judging batch carries. A hundred is what the
# vision pass and the translation batches settled on: big enough that the
# per-request overhead is noise, small enough that a rejected batch is
# cheap to redo.
# 50，毋是 100。量著兩項限制：一批 100 條ê agent 逐擺 12 分，逾時ê
# 機會大，而且逾時ê代價是規批重來；koh有，資料歹ê批次 agent 話特別
# 濟，撞著 64K 輸出上限——彼比逾時較歹揀，因為伊看起來像成功。50
# 條兩項攏閃會開，固定開銷（逐个 agent 約 9 萬 token）加五成，毋過
# token 毋是瓶頸，牆鐘才是。
BATCH_SIZE = 50

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


def _stage(base, srt_name, suffix=""):
    """This episode's file in a speech-side stage folder, folder created.

    `base` is one of the stage constants in `paths`, so a layout change is
    made in one place. The month layer comes from `paths.stage_path`, the
    same way the picture side gets it -- both technique directories are
    laid out alike, so one episode is one name in both.
    """
    path = paths.stage_path(base, srt_name, suffix)
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
    first -- OCR, then 2-srt-raw, then publish -- so looking only in the
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
        json.dump(doc, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)


# ------------------------------------------------------------------ steps


def step_words(srt_name, ethnicity_en):
    out = _stage(paths.ASR_WORDS, srt_name, JSON)
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


def rows_of(srt_name):
    """(entries, unassigned word indexes) for this episode, recomputed.

    A pure function of two stored things: the whole-episode word stream
    in `1-words`, and the picture side's cue timeline (through the same
    assembly chain that produced the delivered subtitle SRT). Same
    inputs, same rows, every time -- which is what lets every render
    above be rebuilt from the store alone and byte-compared.

    Cheap enough to do on every call: it is a max-overlap pass over a
    few thousand words. The expensive thing is the decode, and that is
    what `1-words` is for.
    """
    words_doc = _load(_stage(paths.ASR_WORDS, srt_name, JSON))
    rows = _chain_rows(srt_name)
    for row in rows:
        row["subtitle"] = row.pop("text")
    return project.project(words_doc["words"], rows)


def raw_body_of(srt_name):
    """The two-line SRT text for this episode, off the store alone.

    Shared by the write side (`step_raw`) and the verification side
    (`scripts.news.coaxial`), on purpose: a rebuild check that rendered
    through a second code path would pass while the two paths disagreed.
    """
    rows, _unassigned = rows_of(srt_name)
    return bisrt.raw_body(rows)


def step_raw(srt_name):
    out = _stage(paths.ASR_RAW, srt_name, ".srt")
    bisrt.write(out, raw_body_of(srt_name))
    print("2-srt-raw 寫出", out)


# ------------------------------------------------------ translation (mt)


def _lang_of(srt_name):
    """This episode's service language code, from the static table."""
    return dialects.lang_of(_entry_of(srt_name)["族語別(英)"])


def _fetching_translator(srt_name, client=None):
    """A lookup that asks the service when the cache misses.

    One request at a time with a pause, because the service is a public
    one for speakers rather than an API farm; the cache is what keeps a
    rerun -- or a re-projection after the timeline changes -- from
    paying for the same line twice.
    """
    lang = _lang_of(srt_name)
    cache = mtclient.MTCache(paths.MT_CACHE)
    if client is None:
        client = mtclient.MTClient(MT_URL)

    def translate(text):
        return client.translate_cached(cache, "ailabs", "f2z", lang, text)
    return translate


def _cached_translator(srt_name):
    """A lookup that only reads the cache -- for offline rebuilding.

    A miss here is not something to go and fetch: it means the delivered
    file was not produced from the store, so the honest thing is to say
    so and stop.
    """
    lang = _lang_of(srt_name)
    cache = mtclient.MTCache(paths.MT_CACHE)

    def translate(text):
        hit = cache.get("ailabs", "f2z", lang, text)
        if hit is None:
            raise PipelineError("mt-cache 內底揣無這逝ê譯文（%s）" % lang)
        return hit
    return translate


def ai_body_of(srt_name):
    """3-srt-ai's text, off the store alone -- no service, no model."""
    rows, _unassigned = rows_of(srt_name)
    return bisrt.ai_body(rows, _cached_translator(srt_name))


def step_mt(srt_name, client=None):
    rows, _unassigned = rows_of(srt_name)
    out = _stage(paths.ASR_AI, srt_name, ".srt")
    bisrt.write(out, bisrt.ai_body(rows, _fetching_translator(
        srt_name, client=client)))
    print("3-srt-ai 寫出", out)


# --------------------------------------------------- grading (judge)


def judge_folder(srt_name):
    """Where this episode's batch and reply files live.

    In the work dir, not the store: they are scratch. What is worth
    keeping -- the grade and the material it was given for -- goes into
    `quality-cache/`, content-addressed, so a re-projection finds it
    again and a re-run does not pay for the same question twice.
    """
    folder = os.path.join(_workdir(srt_name), "quality")
    os.makedirs(folder, exist_ok=True)
    return folder


def _judge_items(srt_name):
    """(entries, the ones worth asking a judge about).

    The canned-translation detector is built here rather than inside
    `judge`, because what makes a translation canned is a property of
    the whole shared cache, not of one episode: the same sentence coming
    back for unrelated inputs is only visible across everything the
    service has ever been asked.
    """
    rows, _unassigned = rows_of(srt_name)
    repeated = mtclient.MTCache(paths.MT_CACHE).repeated_outputs()

    def suspect(text):
        return text in repeated
    return rows, judge.materials(rows, _cached_translator(srt_name),
                                 suspect=suspect)


def write_glossary(srt_name, rows):
    """The episode's anchor list, for every batch agent to read.

    Written next to the batches rather than into them: it is the same
    for all of them, and a file they all open is one place to look when
    a grade turns on a word.
    """
    path = os.path.join(judge_folder(srt_name), "glossary.tsv")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(glossary.render(glossary.anchors(rows)))
    return path


def _clear_batches(folder, prefix):
    """Drop this judge's old batch and reply files.

    A new batch is a new question -- the definition changed, or the
    material did -- and the file names repeat, so an old reply left
    lying there would be ingested against the new request. The entry
    numbers would still line up, so nothing would fail; yesterday's
    answers would just quietly become today's. Rejecting a whole batch
    on a bad id is the loud failure; this is the quiet one.
    """
    for entry in sorted(os.listdir(folder)):
        if entry == "glossary.tsv":
            continue
        if entry.startswith(prefix) and entry.endswith(".tsv"):
            os.remove(os.path.join(folder, entry))


def step_judge(srt_name, second=False, size=BATCH_SIZE):
    """Write the batch files this judge still owes an answer on."""
    name = judge.SECOND if second else judge.FIRST
    rows, items = _judge_items(srt_name)
    write_glossary(srt_name, rows)
    cache = judge.QualityCache(paths.QUALITY_CACHE)
    if second:
        # The second round is drawn from what the first graded 高, so an
        # unfinished first round produces a short second round -- and
        # nothing says so. The entries in the missing batches would just
        # never reach the second judge, and the only symptom is a
        # complaint from `quality` much later, or none at all.
        owing = judge.pending(items, cache, judge.FIRST)
        if owing:
            raise PipelineError(
                "頭一輪猶閣欠 %d 條無判定，第二輪袂使先寫——"
                "先kā `--step judge` 佮 `--step ingest` 走予齊"
                % len(owing))
    left = judge.pending(items, cache, name)
    folder = judge_folder(srt_name)
    _clear_batches(folder, judge.PREFIX[name])
    written = judge.write_batches(left, folder,
                                  judge.PREFIX[name], size=size)
    if not written:
        print("%s 無賰啥物通問矣（%d 條攏有判定）" % (name, len(items)))
        return written
    print("%s：%d 條、%d 批寫佇 %s"
          % (name, len(left), len(written), folder))
    for path in written:
        print("   ", os.path.basename(path))
    return written


def step_ingest(srt_name, second=False):
    """Take in every reply that has arrived; say what is still out."""
    name = judge.SECOND if second else judge.FIRST
    _rows, items = _judge_items(srt_name)
    cache = judge.QualityCache(paths.QUALITY_CACHE)
    folder = judge_folder(srt_name)
    taken = 0
    waiting = []
    for entry in sorted(os.listdir(folder)):
        if not entry.startswith(judge.PREFIX[name]):
            continue
        if not entry.endswith(".tsv") or entry.endswith(".reply.tsv"):
            continue
        request = os.path.join(folder, entry)
        reply = request[:-len(".tsv")] + ".reply.tsv"
        if not os.path.exists(reply):
            waiting.append(entry)
            continue
        taken += judge.ingest_reply(request, reply, cache, name, items)
    print("%s：收 %d 條" % (name, taken))
    for entry in waiting:
        print("    猶未回覆：", entry)
    return taken


def quality_body_of(srt_name):
    """4-srt-quality's text, off the store alone -- no model, no service."""
    rows, items = _judge_items(srt_name)
    cache = judge.QualityCache(paths.QUALITY_CACHE)
    grades = judge.verdicts(rows, cache, items)

    def grade(row):
        return grades[row["index"]]
    return bisrt.quality_body(rows, grade)


def step_quality(srt_name):
    out = _stage(paths.ASR_QUALITY, srt_name, ".srt")
    bisrt.write(out, quality_body_of(srt_name))
    print("4-srt-quality 寫出", out)


# words is the machine-time step; raw is the projection and render; mt
# adds the translation the judge is shown; judge/ingest/quality are the
# grading round trip. Only words and raw run by default -- everything
# after talks to a public service or costs model tokens, which is a
# decision to make per batch, not a thing to start by accident.
STEPS = [("words", None), ("raw", None)]


def main(argv=None):
    lowpri.be_nice()   # 長時間ê重工，莫kā機器食牢去
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt_name")
    ap.add_argument("--step", default="all",
                    help="words|raw|mt|judge|ingest|quality|all")
    ap.add_argument("--second", action="store_true",
                    help="judge／ingest 換第二个裁判（干焦看頭一个講懸ê）")
    ap.add_argument("--redo", action="store_true",
                    help="產出已經有嘛閣做一擺（時間軸換版了後重投影）")
    args = ap.parse_args(argv)
    paths.check_srt_name(args.srt_name)

    set_redo(args.redo)
    entry = _entry_of(args.srt_name)
    runners = {
        "words": lambda: step_words(args.srt_name, entry["族語別(英)"]),
        "raw": lambda: step_raw(args.srt_name),
        "mt": lambda: step_mt(args.srt_name),
        "judge": lambda: step_judge(args.srt_name, second=args.second),
        "ingest": lambda: step_ingest(args.srt_name, second=args.second),
        "quality": lambda: step_quality(args.srt_name),
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
