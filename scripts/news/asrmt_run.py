#!/usr/bin/env python3
"""One episode through the speech side: audio -> bilingual SRT + QC.

    python3 -m scripts.news.asrmt_run <srt_name> [--step NAME]

Steps, each skipped when its output already exists (a rerun continues,
never redoes paid work):

    words           whole-episode vosk decode -> 2-asr/1-words/
    entries         chain rows + word projection -> 2-asr/2-entries/
    dialect         pick the MT language code on a 50-entry sample
    mt              ai-labs both directions, cached -> entries updated
    claude-batches  write numbered TSVs for the Claude pass
    claude-ingest   validate replies, fill cache + entries
    raw             ASR x subtitle two-line render -> 2-asr/3-srt-raw/
                    (預設流程到此為止)
  align 延伸（指名 --step 才跑）：
    seg-ingest      sentence-boundary labels -> entries (sent_end)
    detect          misalignment QC -> 2-asr/5-align/
    srt             review render + verdict line -> 2-asr/4-srt-ai/
    complete        merged two-line render -> 2-asr/6-srt-complete/

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
from scripts.asrmt.align import claude_mt
from scripts.asrmt.align import detect
from scripts.asrmt.align import mtclient
from scripts.asrmt.align import render
from scripts.news import make_srt
from scripts.news import paths
from scripts.news import rebuild
from scripts.srtlib import assemble
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


def step_needed(path):
    return not os.path.exists(path)


def verify_audio(srt_name, actual, expected, tolerance=1.0):
    """Same timeline or nothing (spec: 音檔時長不符 -> fail loud)."""
    if abs(actual - expected) > tolerance:
        raise PipelineError(
            "%s: 音檔時長 %.3fs 與 cue 軸 %.3fs 差超過 %.1fs——"
            "音檔與時間軸不同源，中止；改抓 mxf 抽音再來"
            % (srt_name, actual, expected, tolerance))


def _stage(name):
    folder = os.path.join(paths.ASR_DIR, name)
    os.makedirs(folder, exist_ok=True)
    return folder


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


def _cues_duration(srt_name):
    with open(os.path.join(paths.KARI_CUES, srt_name + JSON),
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
    out = os.path.join(_stage("1-words"), srt_name + JSON)
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
        shutil.copy2(os.path.join(paths.KARI_CUES, srt_name + JSON),
                     os.path.join(work, "cues.json"))
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
    out = os.path.join(_stage("2-entries"), srt_name + JSON)
    if not step_needed(out):
        print("2-entries 已存在，跳過")
        return
    words_doc = _load(os.path.join(_stage("1-words"), srt_name + JSON))
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
    return os.path.join(_stage("2-entries"), srt_name + JSON)


def _client_cache():
    cache = mtclient.MTCache(os.path.join(paths.ASR_DIR, "mt-cache"))
    client = mtclient.MTClient(base_url=MT_URL)
    return client, cache


def _codes_for(client, ethnicity_zh):
    """The MT service's own dialect codes for one ethnicity, live.

    The lambda reply is the dropdown update: its choices are the
    (label, code) pairs this ethnicity offers -- the single source the
    service itself uses, so new tribes need no hardcoded list.
    """
    reply = client._call("lambda", ethnicity_zh)
    try:
        data = json.loads(reply)
        codes = []
        for pair in data.get("choices", []):
            codes.append(pair[1])
        if codes:
            return codes
    except (ValueError, TypeError, IndexError):
        pass
    raise PipelineError("無法從服務取得 %s 的語別碼（回應：%.120s）"
                        % (ethnicity_zh, reply))


def step_dialect(srt_name):
    doc = _load(_entries_path(srt_name))
    if doc.get("src_lang"):
        print("語別碼已定：", doc["src_lang"], "跳過")
        return
    entry = _entry_of(srt_name)
    client, cache = _client_cache()
    codes = _codes_for(client, entry["族語別(中)"])
    if len(codes) == 1:
        doc["src_lang"] = codes[0]
        doc["dialect_scores"] = {codes[0]: None}
        doc["dialect_tie"] = False
        _save(doc, _entries_path(srt_name))
        print("該族只有一個語別碼，直接定案：", codes[0])
        return
    sample = []
    for row in doc["entries"]:
        if row["formosan"] and row["subtitle"]:
            sample.append(row)
        if len(sample) == DIALECT_SAMPLE:
            break
    scores = {}
    for code in codes:
        per = []
        for row in sample:
            zh = client.translate_cached(cache, "ailabs", "f2z", code,
                                         row["formosan"])
            per.append(detect.char_bigram_f1(zh, row["subtitle"]))
        # mean, not median: subtitle lines are condensed rewrites, so
        # most per-entry scores are legitimately zero and a median
        # degenerates -- the mean still ranks codes by how often their
        # wording lands on the subtitle's
        scores[code] = sum(per) / len(per)
        print("  %s 平均 %.4f" % (code, scores[code]))
    ranked = sorted(scores, key=lambda code: scores[code], reverse=True)
    tie = scores[ranked[0]] - scores[ranked[-1]] < 0.01
    if tie:
        # near-identical translations on this sample: for Amis take the
        # news anchors' usual dialect rather than an alphabetical
        # accident; other tribes take the service's first listing
        best = "ami_Xiug" if "ami_Xiug" in codes else codes[0]
        print("五碼無可辨差異（<0.01），平手指定：", best)
    else:
        best = ranked[0]
        print("語別碼定案：", best)
    doc["src_lang"] = best
    doc["dialect_scores"] = scores
    doc["dialect_tie"] = tie
    _save(doc, _entries_path(srt_name))


def step_mt(srt_name):
    doc = _load(_entries_path(srt_name))
    lang = doc["src_lang"]
    if not lang:
        raise PipelineError("run --step dialect first")
    client, cache = _client_cache()
    done = 0
    for row in doc["entries"]:
        row["zh"]["ailabs"] = client.translate_cached(
            cache, "ailabs", "f2z", lang, row["formosan"])
        row["formosan_from_zh"]["ailabs"] = client.translate_cached(
            cache, "ailabs", "z2f", lang, row["subtitle"])
        done += 1
        if done % 25 == 0:
            _save(doc, _entries_path(srt_name))
            print("  ai-labs %d/%d" % (done, len(doc["entries"])))
    _save(doc, _entries_path(srt_name))
    print("ai-labs 兩方向完成：", done, "條目")


def step_claude_batches(srt_name):
    doc = _load(_entries_path(srt_name))
    folder = os.path.join(_workdir(srt_name), "claude")
    f2z = []
    z2f = []
    for row in doc["entries"]:
        f2z.append((row["index"], row["formosan"]))
        z2f.append((row["index"], row["subtitle"]))
    wrote = claude_mt.write_batches(f2z, "f2z", folder)
    wrote += claude_mt.write_batches(z2f, "z2f", folder)
    print("批次檔：", len(wrote), "個，在", folder)
    print("回覆檔名：bNN.<dir>.reply.tsv，一檔一次寫成")


def step_claude_ingest(srt_name):
    doc = _load(_entries_path(srt_name))
    folder = os.path.join(_workdir(srt_name), "claude")
    _, cache = _client_cache()
    total = 0
    for name in sorted(os.listdir(folder)):
        if ".reply." in name or not name.endswith(".tsv"):
            continue
        reply = os.path.join(folder, name.replace(".tsv", ".reply.tsv"))
        if not os.path.exists(reply):
            print("  缺回覆：", name)
            continue
        direction = name.split(".")[1]
        total += claude_mt.ingest_reply(os.path.join(folder, name), reply,
                                        cache, direction, doc["src_lang"])
    for row in doc["entries"]:
        got = cache.get("claude", "f2z", doc["src_lang"], row["formosan"])
        if got is not None:
            row["zh"]["claude"] = got
        got = cache.get("claude", "z2f", doc["src_lang"], row["subtitle"])
        if got is not None:
            row["formosan_from_zh"]["claude"] = got
    _save(doc, _entries_path(srt_name))
    print("claude ingest：", total, "句入快取")


def step_raw(srt_name):
    doc = _load(_entries_path(srt_name))
    out = os.path.join(_stage("3-srt-raw"), srt_name + ".srt")
    bisrt.write(out, bisrt.raw_body(doc["entries"]))
    print("3-srt-raw 寫出", out)


def step_seg_ingest(srt_name):
    """Sentence-boundary labels (E/C per entry) -> sent_end flags."""
    doc = _load(_entries_path(srt_name))
    folder = os.path.join(_workdir(srt_name), "seg-iso")
    labels = {}
    for name in sorted(os.listdir(folder)):
        reply = os.path.join(folder, name, "reply.tsv")
        if not os.path.exists(reply):
            raise PipelineError("缺分句回覆：%s" % name)
        with open(reply, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                key, _, mark = line.partition("\t")
                labels[int(key)] = mark.strip().upper()
    missing = []
    for row in doc["entries"]:
        mark = labels.get(row["index"])
        if mark not in ("E", "C"):
            missing.append(row["index"])
            continue
        row["sent_end"] = (mark == "E")
    if missing:
        raise PipelineError("分句標記缺漏或非 E/C：%s" % missing[:20])
    doc["entries"][-1]["sent_end"] = True
    _save(doc, _entries_path(srt_name))
    ends = 0
    for row in doc["entries"]:
        if row["sent_end"]:
            ends += 1
    print("分句標記入檔：%d 條，%d 個句尾" % (len(doc["entries"]), ends))


def step_srt(srt_name):
    doc = _load(_entries_path(srt_name))
    classes = {}
    align_path = os.path.join(_stage("5-align"), srt_name + JSON)
    if os.path.exists(align_path):
        for record in _load(align_path)["entries"]:
            classes[record["index"]] = record["class"]
    out = os.path.join(_stage("4-srt-ai"), srt_name + ".srt")
    bisrt.write(out, render.review_body(doc["entries"], classes))
    print("4-srt-ai 寫出", out)


def step_detect(srt_name):
    doc = _load(_entries_path(srt_name))
    words_doc = _load(os.path.join(_stage("1-words"), srt_name + JSON))
    sents = []
    for sent in words_doc["sents"]:
        text = []
        for item in words_doc["words"][sent["i0"]:sent["i1"]]:
            text.append(item["w"])
        sents.append((sent["start"], sent["end"], " ".join(text)))
    entry = _entry_of(srt_name)
    if entry["族語別(英)"] == "Amis":
        anchors = _load(ANCHORS)
    else:
        # 錨點表目前只有阿美；其他族依 spec 降級（摘要照 anchors
        # 空集呈現，不影響歸類）
        anchors = {"numerals": None, "loanwords": None}
    numbers, source = _ckip_numbers(srt_name, doc["entries"])
    report = detect.diagnose(srt_name, doc["entries"], words_doc["words"],
                             sents, numerals=anchors["numerals"],
                             loanwords=anchors["loanwords"],
                             numbers_by_entry=numbers)
    report["anchor_numbers"] = source
    folder = _stage("5-align")
    _save(report, os.path.join(folder, srt_name + JSON))
    with open(os.path.join(folder, srt_name + ".md"), "w",
              encoding="utf-8") as handle:
        handle.write(detect.summary_md(report, doc["entries"]))
    print("5-align 寫出；摘要同名 .md")


def step_complete(srt_name):
    doc = _load(_entries_path(srt_name))
    align_path = os.path.join(_stage("5-align"), srt_name + JSON)
    if not os.path.exists(align_path):
        raise PipelineError("run --step detect first -- the complete render "
                            "merges by its verdicts and blocks")
    align = _load(align_path)
    verdicts = {}
    for record in align["entries"]:
        verdicts[record["index"]] = record["class"]
    groups = detect.merge_groups(align, doc["entries"])
    out = os.path.join(_stage("6-srt-complete"), srt_name + ".srt")
    bisrt.write(out, render.complete_body(doc["entries"], verdicts,
                                          groups))
    print("6-srt-complete 寫出", out)


def _ckip_numbers(srt_name, entries):
    """Word-segmented numeral candidates per entry, cached per episode.

    CKIP (中研院) segments the subtitle lines; only tokens that are a
    number on their own count -- 「新聞一開始」 segments to 新聞/一開始
    and yields nothing. Falls back to the regex extractor with a loud
    note when the segmenter or its data is unavailable.
    """
    cache_path = os.path.join(_workdir(srt_name), "ckip-numbers.json")
    if os.path.exists(cache_path):
        return _load(cache_path), "ckip"
    data_dir = os.path.expanduser("~/.cache/ckiptagger/data")
    try:
        from ckiptagger import WS
        if not os.path.isdir(data_dir):
            raise RuntimeError("no ckip data at %s" % data_dir)
        ws = WS(data_dir)
    except Exception as error:
        print("CKIP 不可用（%s）——退回 regex 抽取並記錄" % error)
        return None, "regex-fallback"
    texts = []
    for row in entries:
        texts.append(row["subtitle"])
    import re
    zh_digits = set("零〇一二兩三四五六七八九十百千")
    out = {}
    for row, tokens in zip(entries, ws(texts)):
        values = []
        for token in tokens:
            arabic = re.match(r"^(\d[\d,]*)", token)
            if arabic:
                values.append(int(arabic.group(1).replace(",", "")))
                continue
            # 單字的中文數詞太歧義，不作錨點：斷詞從新聞一開始這種
            # 句子切出來的孤字一，多半不是數量。兩字以上才收，
            # 像是一百二十
            if len(token) >= 2 and all(ch in zh_digits for ch in token):
                values.append(detect._zh_number(token))
        out[row["index"]] = values
    _save(out, cache_path)
    return out, "ckip"


# The default pipeline ends at the raw SRT (使用者裁定)。 Everything
# after -- translation, segmentation, detection, review, complete --
# is the align extension, run only when named via --step.
STEPS = [("words", None), ("entries", None), ("raw", None)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt_name")
    ap.add_argument("--step", default="all",
                    help="words|entries|raw|dialect|mt|claude-batches|"
                         "claude-ingest|seg-ingest|detect|srt|complete|"
                         "all")
    args = ap.parse_args(argv)
    paths.check_srt_name(args.srt_name)

    entry = _entry_of(args.srt_name)
    runners = {
        "words": lambda: step_words(args.srt_name, entry["族語別(英)"]),
        "entries": lambda: step_entries(args.srt_name),
        "dialect": lambda: step_dialect(args.srt_name),
        "mt": lambda: step_mt(args.srt_name),
        "claude-batches": lambda: step_claude_batches(args.srt_name),
        "claude-ingest": lambda: step_claude_ingest(args.srt_name),
        "raw": lambda: step_raw(args.srt_name),
        "seg-ingest": lambda: step_seg_ingest(args.srt_name),
        "srt": lambda: step_srt(args.srt_name),
        "detect": lambda: step_detect(args.srt_name),
        "complete": lambda: step_complete(args.srt_name),
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
