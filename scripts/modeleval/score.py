#!/usr/bin/env python3
"""開會了阿美：ASR／MT 結果對 OCR 字幕算分，寫報表。

    python3 -m scripts.modeleval.score

OCR 字幕當標準答案（使用者 2026-10-28 的前提）。報表寫到
`kithann/out/modeleval-阿美/report/`：

    摘要.csv          每個 (項目, 範圍, 正規化, 指標) 一列：數值、95% 信賴區間
    ASR逐集.csv       每集 WER／CER 與替換／刪除／插入
    CER逐集.csv       每集 CER，考慮與不考慮 ^ : 兩欄並排，各範圍附合計
    MT逐集.csv        每集、每個語別碼、每方向的 BLEU／chrF++／chrF
    MT逐句.csv        每條字幕的原文、兩個方向的翻譯、單句 chrF++，給人翻看

ASR 有兩種範圍（切塊見 `asr_chunks`）：
    全集          整集的族語字幕 vs 整集的 sapolita 族語列
    族語字幕時段  拿掉族語字幕不到一半的 sapolita 段（受訪者講華語時
                  sapolita 照樣硬聽成阿美語），參考答案只取純族語／族語
                  夾雜華語的字幕

信賴區間是 bootstrap 重抽樣（ASR 以塊、MT 以句為單位）。MT 只替每個
方向的主要正規化、「純族語」與「全部」兩個範圍算信賴區間——五千句重抽
一千遍，一個指標就要半分鐘。
"""
import csv
import os
import random
import sys

from scripts.modeleval import metrics
from scripts.modeleval import mt_run
from scripts.modeleval import pairs
from scripts.modeleval.asr_run import OUT, srt_path
from scripts.asrmt import mtclient
from scripts.modeleval import mtboth
from scripts.srtlib import srt as srtlib

FORMOSAN_LABELS = ("純族語", "族語夾雜華語")
MT_SUBSETS = (
    ("純族語", ("純族語",)),
    ("族語夾雜華語", ("族語夾雜華語",)),
    ("全部", ("純族語", "族語夾雜華語", "華語", "無法確定")),
)
CI_SUBSETS = ("純族語", "全部")
# 過半落在族語字幕底下才算族語段
OVERLAP_SHARE = 0.5
# ASR 切塊：一塊至少 30 秒、最長 120 秒，切點離字幕邊界 0.5 秒內算乾淨
MIN_BLOCK = 30.0
MAX_BLOCK = 120.0
CUT_TOLERANCE = 0.5
BOOTSTRAP_ROUNDS = 1000
SEED = 20261028


def fold_ou(text):
    """o／u 合併成 o：阿美語 o、u 不分音位，南勢寫 u、其他語言別寫 o。"""
    return text.replace("u", "o")


def _formosan(mode):
    def norm(text):
        return metrics.normalize_formosan(text, mode)
    return norm


def _marks_folded(text):
    return fold_ou(metrics.normalize_formosan(text, "marks"))


def _identity(text):
    return text


MAIN = "（主要數字）"
FOLDED = "去 ^ :＋o/u 合併（敏感度分析）"
FORMOSAN_NORMS = (
    ("保留撇號與 ^ :", _formosan("strict")),
    ("去 ^ :" + MAIN, _formosan("marks")),
    ("只留字母", _formosan("letters")),
    (FOLDED, _marks_folded),
)
# 翻譯結果（目標語）的正規化；每個方向第二個是主要數字
MT_NORMS = {
    "f2z": (("原樣", _identity),
            ("華語去標點空白" + MAIN, metrics.normalize_zh)),
    "z2f": (("原樣", _identity),
            FORMOSAN_NORMS[1],
            FORMOSAN_NORMS[3]),
}
TOKENIZE = {"f2z": "zh", "z2f": "13a"}
DIRECTION_NAME = {"f2z": "MT 族→華", "z2f": "MT 華→族"}


# ---------------------------------------------------------------- ASR


def parse_sapolita(text):
    """[(start, end, 族語列, 華語列)]"""
    out = []
    for start, end, body in srtlib.parse_srt(text):
        formosan = ""
        han = ""
        for line in body.split("\n"):
            if line.startswith("族語："):
                formosan = line[len("族語："):].strip()
            elif line.startswith("華語："):
                han = line[len("華語："):].strip()
        out.append((start, end, formosan, han))
    return out


def _union(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def segments_under_formosan(segments, cues):
    spans = []
    for item in cues:
        if item["formosan"] and item["label"] in FORMOSAN_LABELS:
            spans.append((item["start"], item["end"]))
    union = _union(spans)
    kept = []
    for segment in segments:
        start, end = segment[0], segment[1]
        if end <= start:
            continue
        covered = 0.0
        for a, b in union:
            covered += max(0.0, min(end, b) - max(start, a))
        if covered / (end - start) > OVERLAP_SHARE:
            kept.append(segment)
    return kept


def _clean_cut(t, rows, tolerance):
    """t 這個時間點有沒有字幕跨過去（容許 tolerance 秒）。"""
    for item in rows:
        if item["start"] + tolerance < t < item["end"] - tolerance:
            return False
    return True


def _block_of(t, cuts):
    block = 0
    for cut in cuts:
        if t >= cut:
            block += 1
    return block


def _blocks(rows, segments, scope, min_block, max_block, tolerance):
    """(切點, 拿掉的段)。見 `asr_chunks`。"""
    dropped = set()
    if scope == "族語字幕時段":
        kept = set(segments_under_formosan(segments, rows))
        for segment in segments:
            if segment not in kept:
                dropped.add(segment)
    cuts = []
    if segments:
        block_start = segments[0][0]
        for i in range(len(segments) - 1):
            t = (segments[i][1] + segments[i + 1][0]) / 2.0
            length = t - block_start
            if length < min_block:
                continue
            if length >= max_block or _clean_cut(t, rows, tolerance):
                cuts.append(t)
                block_start = t
    return cuts, dropped


def _cue_block(item, cuts, dropped):
    """字幕歸哪一塊；中點落在拿掉的段裡就是 None。"""
    middle = (item["start"] + item["end"]) / 2.0
    for segment in dropped:
        if segment[0] <= middle < segment[1]:
            return None
    return _block_of(middle, cuts)


def asr_chunks(rows, segments, scope, min_block=MIN_BLOCK,
               max_block=MAX_BLOCK, tolerance=CUT_TOLERANCE):
    """[(參考答案, 辨識結果)]，一塊至少 min_block 秒。

    sapolita 的段在開會了很碎（中位數 1.5–11 秒），照段歸字幕的話跨段
    字幕會整條歸到一邊。所以把連續的段併成塊，只在沒有字幕跨過的段界
    切；到 max_block 秒還找不到乾淨的切點就硬切。字幕與段都照中點歸塊；
    落在 sapolita 段與段之間（它判成沒講話）的字幕一樣歸塊，沒有對應的
    辨識結果，算刪除。「族語字幕時段」範圍拿掉族語字幕不到一半的段，
    中點落在那些段裡的字幕一起拿掉；留下的段裡，有族語字的字幕不論
    語言標記都進參考答案（「無法確定」的列拿掉的話，它底下的辨識結果
    全變假的插入）。
    """
    segments = sorted(segments)
    cuts, dropped = _blocks(rows, segments, scope, min_block, max_block,
                            tolerance)
    refs = {}
    hyps = {}
    for segment in segments:
        if segment in dropped or not segment[2]:
            continue
        block = _block_of((segment[0] + segment[1]) / 2.0, cuts)
        hyps.setdefault(block, []).append(segment[2])
    for item in rows:
        if not item["formosan"]:
            continue
        block = _cue_block(item, cuts, dropped)
        if block is not None:
            refs.setdefault(block, []).append(item["formosan"])
    out = []
    for block in range(len(cuts) + 1):
        ref = " ".join(refs.get(block, []))
        hyp = " ".join(hyps.get(block, []))
        if ref or hyp:
            out.append((ref, hyp))
    return out


def cascade_blocks(rows, segments, translations, min_block=MIN_BLOCK,
                   max_block=MAX_BLOCK, tolerance=CUT_TOLERANCE):
    """[(OCR 華語, sapolita 華語列, MT 族→華)]，跟 ASR 同樣的塊。

    範圍是「族語字幕時段」；答案只取族語列華語列都有字的字幕，MT 那邊
    是同一批字幕族語列的譯文（`translations`：族語列 → 譯文），塊裡有
    一句還沒翻就給 None。整集一篇算 n-gram 不看順序，拿下一集的辨識
    結果去比都有 BLEU 12，所以兩邊要在同一個塊上比。
    """
    segments = sorted(segments)
    cuts, dropped = _blocks(rows, segments, "族語字幕時段", min_block,
                            max_block, tolerance)
    refs = {}
    cascades = {}
    mts = {}
    missing = set()
    for segment in segments:
        if segment in dropped or not segment[3]:
            continue
        block = _block_of((segment[0] + segment[1]) / 2.0, cuts)
        cascades.setdefault(block, []).append(segment[3])
    for item in rows:
        if not item["formosan"] or not item["han"]:
            continue
        block = _cue_block(item, cuts, dropped)
        if block is None:
            continue
        refs.setdefault(block, []).append(item["han"])
        if item["formosan"] in translations:
            mts.setdefault(block, []).append(translations[item["formosan"]])
        else:
            missing.add(block)
    out = []
    for block in range(len(cuts) + 1):
        ref = " ".join(refs.get(block, []))
        cascade = " ".join(cascades.get(block, []))
        if not ref and not cascade:
            continue
        mt = None
        if block not in missing:
            mt = " ".join(mts.get(block, []))
        out.append((ref, cascade, mt))
    return out


# ----------------------------------------------------------------- MT


def mt_pairs(rows, cache, direction):
    """([{row, src, hyp, ref}], {語言標記: 缺翻譯的句數})"""
    got = []
    missing = {}
    for item in rows:
        if not item["formosan"] or not item["han"]:
            continue
        if direction == "f2z":
            src, ref = item["formosan"], item["han"]
        else:
            src, ref = item["han"], item["formosan"]
        hyp = cache.get((mtboth.ENGINE, direction, item["mt_code"], src))
        if hyp is None:
            missing[item["label"]] = missing.get(item["label"], 0) + 1
            continue
        got.append({"row": item, "src": src, "hyp": hyp, "ref": ref})
    return got, missing


def missing_in(missing, labels):
    total = 0
    for label in labels:
        total += missing.get(label, 0)
    return total


def bootstrap(stats, total, rounds=BOOTSTRAP_ROUNDS, seed=SEED):
    """(下界, 上界)：逐句（逐塊）重抽樣，2.5／97.5 百分位。"""
    rng = random.Random(seed)
    values = []
    count = len(stats)
    for _ in range(rounds):
        sample = []
        for _ in range(count):
            sample.append(stats[rng.randrange(count)])
        values.append(total(sample))
    values.sort()
    low = values[int(0.025 * (rounds - 1))]
    high = values[int(round(0.975 * (rounds - 1)))]
    return low, high


def _sum(stats):
    if not stats:
        return []
    out = [0] * len(stats[0])
    for one in stats:
        for i, value in enumerate(one):
            out[i] += value
    return out


def _bleu_total(sample):
    return metrics.bleu_from_stats(_sum(sample))["score"]


def _chrfpp_total(sample):
    return metrics.chrf_from_stats(_sum(sample))["score"]


def _chrf_total(sample):
    return metrics.chrf_from_stats(_sum(sample), word_order=0)["score"]


MT_METRICS = (("BLEU", _bleu_total), ("chrF++", _chrfpp_total),
              ("chrF", _chrf_total))


def mt_scores(pairs_, direction, norm, with_ci=True):
    """{句數, BLEU, chrF++, chrF, <指標>_ci}；正規化後參考答案空白的句不算。"""
    stats = {"BLEU": [], "chrF++": [], "chrF": []}
    for one in pairs_:
        hyp = norm(one["hyp"])
        ref = norm(one["ref"])
        if not ref:
            continue
        stats["BLEU"].append(
            metrics.bleu_stats(hyp, ref, TOKENIZE[direction]))
        stats["chrF++"].append(metrics.chrf_stats(hyp, ref))
        stats["chrF"].append(metrics.chrf_stats(hyp, ref, word_order=0))
    out = {"句數": len(stats["BLEU"])}
    if not stats["BLEU"]:
        return out
    for name, total in MT_METRICS:
        out[name] = total(stats[name])
        if with_ci:
            out[name + "_ci"] = bootstrap(stats[name], total)
    return out


# -------------------------------------------------------------- 報表


def _write(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        for item in rows:
            writer.writerow(item)


def _fmt(value):
    return "%.2f" % value


def _ci(pair):
    return "%.2f–%.2f" % pair


SUMMARY_FIELDS = ["項目", "範圍", "正規化", "指標", "數值", "95%信賴區間",
                  "句數或集數", "備註"]


def _edit_stats(result):
    """[錯誤數, 參考長度, 替換, 刪除, 插入]，可以逐項相加。"""
    return [result["errors"], result["ref_len"], result["sub"],
            result["dele"], result["ins"]]


def _rate(stats):
    if not stats or not stats[1]:
        return 0.0
    return 100.0 * stats[0] / stats[1]


def _total_rate(sample):
    return _rate(_sum(sample))


def _segments(name):
    with open(srt_path(OUT, name), encoding="utf-8") as handle:
        return parse_sapolita(handle.read())


def _zh_scores(hyps, refs):
    """華語一批（一塊一句）：{BLEU, chrF++, chrF, <指標>_ci}。"""
    pairs_ = []
    for hyp, ref in zip(hyps, refs):
        pairs_.append({"hyp": hyp, "ref": ref})
    return mt_scores(pairs_, "f2z", metrics.normalize_zh)


def _code_source(row_code):
    """smkul 只寫族語別（`ami`）的是保底，寫到語言別的是目錄。"""
    if "-x-" in row_code:
        return "目錄"
    return "保底"


CASCADE_NOTE = ("跟 ASR 同樣的塊，塊內 OCR 華語列當答案；"
                "串接與 MT 只在「MT 已翻完的塊」兩列之間比")
ASR_NOTE = ("替換 %d、刪除 %d、插入 %d／參考 %d 詞；"
            "各集 WER %.1f–%.1f（信賴區間不含集與集的差異）")


def _cascade(by_episode, names, cache):
    """sapolita 自己接的華語列 vs MT 族→華，同樣的塊、同樣的答案。"""
    refs = []
    cascades = []
    complete = []
    for name in names:
        translations = {}
        for item in by_episode[name]:
            key = (mtboth.ENGINE, "f2z", item["mt_code"], item["formosan"])
            if key in cache:
                translations[item["formosan"]] = cache[key]
        for ref, cascade, mt in cascade_blocks(
                by_episode[name], _segments(name), translations):
            refs.append(ref)
            cascades.append(cascade)
            if mt is not None:
                complete.append((ref, cascade, mt))
    out = []
    runs = [("sapolita 華語列（辨識＋翻譯串接）", "族語字幕時段，全部塊",
             cascades, refs)]
    if complete:
        done_refs = []
        done_cascades = []
        done_mts = []
        for ref, cascade, mt in complete:
            done_refs.append(ref)
            done_cascades.append(cascade)
            done_mts.append(mt)
        runs.append(("sapolita 華語列（辨識＋翻譯串接）",
                     "族語字幕時段，MT 已翻完的塊", done_cascades, done_refs))
        runs.append(("MT 族→華（同一批塊，OCR 族語列當輸入）",
                     "族語字幕時段，MT 已翻完的塊", done_mts, done_refs))
    for item_name, scope, hyps, answers in runs:
        result = _zh_scores(hyps, answers)
        for metric, _total in MT_METRICS:
            out.append({
                "項目": item_name, "範圍": scope,
                "正規化": "華語去標點空白", "指標": metric,
                "數值": _fmt(result[metric]),
                "95%信賴區間": _ci(result[metric + "_ci"]),
                "句數或集數": "%d 塊" % result["句數"],
                "備註": CASCADE_NOTE})
    return out


CER_FIELDS = ["範圍", "成果檔名", "語別碼", "語別碼來源", "CER（考慮 ^ :）",
              "CER（不考慮 ^ :）", "參考字元數（考慮 ^ :）",
              "參考字元數（不考慮 ^ :）"]


def cer_table(episode_rows):
    """逐集 CER，考慮（保留）與不考慮（拿掉）^ : 兩欄並排；每個範圍
    最後一列是合計，用錯誤數與參考字元數加總再除。"""
    columns = {FORMOSAN_NORMS[0][0]: "考慮 ^ :",
               FORMOSAN_NORMS[1][0]: "不考慮 ^ :"}
    table = {}
    order = []
    for item in episode_rows:
        if item["正規化"] not in columns:
            continue
        key = (item["範圍"], item["成果檔名"])
        if key not in table:
            order.append(key)
            table[key] = {"範圍": item["範圍"], "成果檔名": item["成果檔名"],
                          "語別碼": item["語別碼"],
                          "語別碼來源": item["語別碼來源"]}
        table[key][columns[item["正規化"]]] = (
            item["字元錯誤數"], item["參考字元數"])
    out = []
    totals = {}
    for key in order:
        line = table[key]
        scope_total = totals.setdefault(key[0], {})
        row = {}
        for field in ("範圍", "成果檔名", "語別碼", "語別碼來源"):
            row[field] = line[field]
        for column in ("考慮 ^ :", "不考慮 ^ :"):
            errors, ref_len = line[column]
            row["CER（%s）" % column] = _fmt(_rate([errors, ref_len]))
            row["參考字元數（%s）" % column] = ref_len
            done = scope_total.setdefault(column, [0, 0])
            done[0] += errors
            done[1] += ref_len
        out.append(row)
        last = key == order[-1] or order[order.index(key) + 1][0] != key[0]
        if last:
            total = {"範圍": key[0], "成果檔名": "合計", "語別碼": "",
                     "語別碼來源": ""}
            for column in ("考慮 ^ :", "不考慮 ^ :"):
                errors, ref_len = scope_total[column]
                total["CER（%s）" % column] = _fmt(_rate([errors, ref_len]))
                total["參考字元數（%s）" % column] = ref_len
            out.append(total)
    return out


def asr_report(rows, cache, report_dir):
    by_episode = {}
    for item in rows:
        by_episode.setdefault(item["srt_name"], []).append(item)
    names = []
    for name in sorted(by_episode):
        if os.path.exists(srt_path(OUT, name)):
            names.append(name)
    if not names:
        return []
    episode_rows = []
    summary = []
    for scope in ("全集", "族語字幕時段"):
        chunks = {}
        for name in names:
            chunks[name] = asr_chunks(by_episode[name], _segments(name),
                                      scope)
        for norm_name, norm in FORMOSAN_NORMS:
            word_stats = []
            char_stats = []
            episode_wer = []
            for name in names:
                words = []
                chars = []
                hyp_words = 0
                for ref, hyp in chunks[name]:
                    ref = norm(ref)
                    hyp = norm(hyp)
                    hyp_words += len(hyp.split())
                    words.append(_edit_stats(metrics.wer([ref], [hyp])))
                    chars.append(_edit_stats(metrics.cer([ref], [hyp])))
                word_stats.extend(words)
                char_stats.extend(chars)
                w = _sum(words)
                c = _sum(chars)
                episode_wer.append(_rate(w))
                episode_rows.append({
                    "成果檔名": name, "範圍": scope, "正規化": norm_name,
                    "語別碼": pairs.sapolita_code(
                        name, by_episode[name][0]["code"]),
                    "語別碼來源": _code_source(by_episode[name][0]["code"]),
                    "WER": _fmt(_rate(w)), "CER": _fmt(_rate(c)),
                    "參考詞數": w[1], "辨識詞數": hyp_words,
                    "詞替換": w[2], "詞刪除": w[3], "詞插入": w[4],
                    "參考字元數": c[1], "字元錯誤數": c[0]})
            w = _sum(word_stats)
            c = _sum(char_stats)
            count = "%d 集、%d 塊" % (len(names), len(word_stats))
            summary.append({
                "項目": "ASR sapolita", "範圍": scope, "正規化": norm_name,
                "指標": "WER", "數值": _fmt(_rate(w)),
                "95%信賴區間": _ci(bootstrap(word_stats, _total_rate)),
                "句數或集數": count,
                "備註": ASR_NOTE % (
                    w[2], w[3], w[4], w[1], min(episode_wer),
                    max(episode_wer))})
            summary.append({
                "項目": "ASR sapolita", "範圍": scope, "正規化": norm_name,
                "指標": "CER", "數值": _fmt(_rate(c)),
                "95%信賴區間": _ci(bootstrap(char_stats, _total_rate)),
                "句數或集數": count,
                "備註": "參考 %d 字元（含詞間空白）" % c[1]})
    summary.extend(_cascade(by_episode, names, cache))
    _write(os.path.join(report_dir, "ASR逐集.csv"),
           ["成果檔名", "範圍", "正規化", "語別碼", "語別碼來源", "WER", "CER",
            "參考詞數", "辨識詞數", "詞替換", "詞刪除", "詞插入",
            "參考字元數", "字元錯誤數"], episode_rows)
    _write(os.path.join(report_dir, "CER逐集.csv"), CER_FIELDS,
           cer_table(episode_rows))
    return summary


def mt_report(rows, cache, report_dir):
    summary = []
    episode_rows = []
    per_line = {}
    sources = {}
    for item in rows:
        sources[item["srt_name"]] = _code_source(item["code"])
    for direction in ("f2z", "z2f"):
        got, missing = mt_pairs(rows, cache, direction)
        main_name, main_norm = MT_NORMS[direction][1]
        for subset, labels in MT_SUBSETS:
            note = ""
            if missing_in(missing, labels):
                note = "另有 %d 句猶未翻譯，無算入" % missing_in(
                    missing, labels)
            chosen = []
            for one in got:
                if one["row"]["label"] in labels:
                    chosen.append(one)
            for norm_name, norm in MT_NORMS[direction]:
                with_ci = norm_name == main_name and subset in CI_SUBSETS
                result = mt_scores(chosen, direction, norm, with_ci)
                if "BLEU" not in result:
                    continue
                for metric, _total in MT_METRICS:
                    interval = ""
                    if with_ci:
                        interval = _ci(result[metric + "_ci"])
                    summary.append({
                        "項目": DIRECTION_NAME[direction], "範圍": subset,
                        "正規化": norm_name, "指標": metric,
                        "數值": _fmt(result[metric]),
                        "95%信賴區間": interval,
                        "句數或集數": "%d 句" % result["句數"],
                        "備註": note})
        groups = {}
        for one in got:
            if one["row"]["label"] != "純族語":
                continue
            groups.setdefault(("集", one["row"]["srt_name"]), []).append(one)
            groups.setdefault(("語別碼", one["row"]["mt_code"]),
                              []).append(one)
        for key in sorted(groups):
            result = mt_scores(groups[key], direction, main_norm,
                               with_ci=False)
            episode_rows.append({
                "方向": DIRECTION_NAME[direction], "分組": key[0],
                "名稱": key[1], "語別碼來源": sources.get(key[1], ""),
                "範圍": "純族語", "正規化": main_name,
                "句數": result["句數"], "BLEU": _fmt(result["BLEU"]),
                "chrF++": _fmt(result["chrF++"]),
                "chrF": _fmt(result["chrF"])})
        for one in got:
            item = one["row"]
            key = (item["srt_name"], item["index"])
            line = per_line.setdefault(key, {
                "成果檔名": item["srt_name"], "字幕編號": item["index"],
                "這列的語言": item["label"], "語別碼": item["mt_code"],
                "族語列": item["formosan"], "華語列": item["han"]})
            single = metrics.chrf_from_stats(metrics.chrf_stats(
                main_norm(one["hyp"]), main_norm(one["ref"])))
            if direction == "f2z":
                line["族→華翻譯"] = one["hyp"]
                line["族→華單句chrF++"] = _fmt(single["score"])
            else:
                line["華→族翻譯"] = one["hyp"]
                line["華→族單句chrF++"] = _fmt(single["score"])
    _write(os.path.join(report_dir, "MT逐集.csv"),
           ["方向", "分組", "名稱", "語別碼來源", "範圍", "正規化", "句數",
            "BLEU",
            "chrF++", "chrF"], episode_rows)
    lines = []
    for key in sorted(per_line):
        lines.append(per_line[key])
    _write(os.path.join(report_dir, "MT逐句.csv"),
           ["成果檔名", "字幕編號", "這列的語言", "語別碼", "族語列",
            "華語列", "族→華翻譯", "族→華單句chrF++", "華→族翻譯",
            "華→族單句chrF++"], lines)
    return summary


def main(argv=None):
    rows = mt_run.with_codes(pairs.load())
    cache = mtclient.MTCache(os.path.join(OUT, "mt-cache")).entries
    report_dir = os.path.join(OUT, "report")
    summary = asr_report(rows, cache, report_dir) + mt_report(
        rows, cache, report_dir)
    _write(os.path.join(report_dir, "摘要.csv"), SUMMARY_FIELDS, summary)
    for item in summary:
        cells = []
        for field in SUMMARY_FIELDS:
            cells.append(str(item.get(field, "")))
        print("\t".join(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
