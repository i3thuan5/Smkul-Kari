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
from scripts.news import episodes
from scripts.news import paths
from scripts.news import sources
from scripts.news import rebuild
from scripts.srtlib import assemble
from scripts import lowpri
from scripts.errors import PipelineError

JSON = ".json"
MT_URL = "https://ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil"
MODEL_ID = "ILRDF/kaldi_formosan_250514_%s"

# How many entries one judging batch carries.
#
# 500，本底是 50。改ê因端是固定開銷：逐个 agent 量著 9 萬到 10 萬
# token 是固定ê（系統提示、判定規則、詞表，逐回合重送一擺），逐列
# ê邊際成本才 1300。50 列一批ê時，固定開銷佔欲一半——雅美尾批賰
# 3 列，照常開 5 萬 1。
#
# 使用者裁定 2026-09-08：一批至少 200 列，愈大愈好，用會著 sonnet
# context ê 50%；超過 15 分鐘無要緊，先省 token。第二輪 fable 仝款
# （伊本底就一兩批爾，改了無差）。
#
# 揀 500 無揀「規集一批」：一列量著 204 bytes，500 列約 102KB、4 萬
# 1 token ê材料，加規則佮詞表約佔 20 萬 context ê四分之一。上大彼
# 集 966 列，一批食 45% ê context，賰無偌濟通推理，而且一批去予退
# ê時了ê是規集ê工。省ê差額才一成外，無值得。
#
# 頭起先ê理路留咧做參考：50 是為著「一批 12 分、逾時ê機會細」佮
# 「資料歹ê批次話濟，會撞著 64K 輸出上限」。逾時彼項使用者講會使放
# 予伊久。輸出上限彼項猶原會出現，毋過**毋是綴批次大細直直大**：
# 2026-09-08 量著，500 列ê大批做十外擺攏無代誌，倒是 124 列佮 150
# 列ê細批撞著。彼是 agent 家己ê變異——有ê話濟有ê話少。
# 2026-09-09 閣一擺：仝一輪 13 批內底，兩批 500 列ê攏過，倒是卡那
# 卡那富 045午 408 列彼批爆去。切做 204×2 就過。
#
# 派工講話ê寫法愛**量化**才有效。實測三个層次：「莫逐條寫分析」
# 擋袂牢；「回予我ê可見文字對頭到尾干焦一逝」較好，猶原有ê會過
# 分；「你唯一會使輸出ê可見文字是尾彼逝『高 N 中 N 低 N』，無超過
# 15 字」才穩。卡那卡那富 038午 s02 三擺才過，就是按呢一層一層絚
# 起來ê。
#
# 派工講話會使減少，毋過擋袂全：「回予我ê可見文字對頭到尾干焦一
# 逝」比「莫逐條寫分析」有效，124 列佮 150 列補派了就過。毋過布農
# 035晚 賰ê 418 列，加了嚴ê講法猶原撞著，落尾是切做 200 列一批才
# 過。所以：**撞著ê時莫干焦改講話，共彼集切較細（用 `step_judge`
# ê `size=` 參數）**。切了後愛先kā收過ê回覆檔改名囥起來，若無新舊
# 編號會相撞。
BATCH_SIZE = 500

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


def audio_source(entry):
    """這集ê影片，予抽音軌用ê。

    影片ê正本佇遠端，毋過這條流程本底就會kā伊抓落來切 cue。所以揣ê
    順序是：本機暫存ê原檔 → 本機封存 mkv → 攏無ê時照節目目錄ê
    `原始影片檔案位置` 對遠端提（佮切 cue 仝一條路、仝一組憑證）。

    本底這爿是問目錄ê `音檔位置(mp3)`，直接抓伺服器頂ê mp3。彼一欄
    推導袂出來——量過 983 逝，干焦 835 逝ê音檔佮影片仝資料夾仝主檔名，
    69 逝主檔名無仝（影片帶族語前綴、音檔無），64 逝規氣無仝資料夾，
    15% 無規則通循。影片位置彼欄是規條流程攏咧用ê，音軌對伊抽就免
    閣飼第二份路徑。
    """
    name = entry["srt_name"]
    staged = os.path.join(paths.STAGE, os.path.basename(entry["file"]))
    if os.path.exists(staged):
        return staged, ""
    archived = os.path.join(paths.MKV_ARCHIVE, name + ".mkv")
    if os.path.exists(archived):
        return archived, ""
    chosen, problem = sources.pick(entry)
    if not chosen:
        raise PipelineError("%s：本機無影片，節目目錄嘛揀袂出來源（%s）"
                            % (name, problem))
    return "", REMOTE_ROOT + "/" + chosen


def extract_audio(local_video, out):
    """對影片抽音軌，落做辨識食ê mp3。"""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done = subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", local_video,
                           "-vn", "-ac", "1", "-ar", "16000", out],
                          capture_output=True)
    if done.returncode or not os.path.exists(out):
        raise PipelineError("對 %s 抽音軌失敗" % local_video)
    return out


AMI_CODES = ["ami_Coas", "ami_Heng", "ami_Mala", "ami_Sout", "ami_Xiug"]
DIALECT_SAMPLE = 50

ANCHORS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "anchors_ami.json")


# 伺服器頂ê語料根，佮 transcode 彼爿仝款。
REMOTE_ROOT = "/docker"

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
    for entry in episodes.load():
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

    `.work` is the one that counts: `make_all` assembled the delivered SRT
    from it and `publish` moves that same cues.json into the store, so both
    sides read one timeline and the two SRTs stay line-for-line aligned.
    """
    stored = paths.stage_path(paths.KARI_CUES, srt_name, JSON)
    if os.path.exists(stored):
        return stored
    work = os.path.join(paths.WORK,
                        paths.check_name(slug, "slug") + ".work")
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
    """Drop this judge's batch files for the version being written.

    Only this version's: the file names carry the prompt version, so an
    older version's reply can never be read as this one's -- `ingest`
    simply does not look at it.

    That naming is what makes this safe. Clearing *everything* with the
    prefix, which is what this did at first, also removed the request
    and reply files of agents **still working**, and their finished
    replies with them. Most of the "said it wrote the file, the file is
    not there" cases in the first day's batch were this, not the agents.
    """
    tail = "." + judge.PROMPT_VERSION + ".tsv"
    for entry in sorted(os.listdir(folder)):
        if entry.startswith(prefix) and entry.endswith(tail):
            os.remove(os.path.join(folder, entry))


def _refuse_over_uningested(folder, prefix, cache, name, items):
    """Do not rewrite the batches while a reply is sitting there unread.

    `_clear_batches` removes this version's request files and they are
    written again from whatever the cache still owes. Let a few entries
    land in the cache between the two runs and the remainder splits
    differently -- the fifty rows that were `s03` now straddle `s02` and
    `s03`. An agent still working off the old `s03` answers with ids the
    new `s03` does not hold, and nothing downstream can tell.

    An *ingested* reply is harmless: its rows are in the cache, so they
    leave `pending` and the rewrite is over settled ground. What has to
    stop the rewrite is a reply nobody has read yet.
    """
    by_index = {}
    for item in items:
        by_index[str(item["index"])] = item
    tail = "." + judge.PROMPT_VERSION + ".reply.tsv"
    waiting = []
    for entry in sorted(os.listdir(folder)):
        if not entry.startswith(prefix) or not entry.endswith(tail):
            continue
        with open(os.path.join(folder, entry), encoding="utf-8") as handle:
            for line in handle:
                key = line.split("\t")[0].strip()
                item = by_index.get(key)
                if item is not None and cache.get(name, item) is None:
                    waiting.append(entry)
                    break
    if waiting:
        raise PipelineError(
            "%d 个回覆檔猶未收就欲重寫批次，按呢會kā咧做ê agent 害死"
            "——先走 `--step ingest`：%s"
            % (len(waiting), "、".join(waiting[:5])))


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
    _refuse_over_uningested(folder, judge.PREFIX[name],
                            cache, name, items)
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
    tail = "." + judge.PROMPT_VERSION + ".tsv"
    for entry in sorted(os.listdir(folder)):
        if not entry.startswith(judge.PREFIX[name]):
            continue
        if not entry.endswith(tail):
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
