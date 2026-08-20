#!/usr/bin/env python3
"""Speech-subtitle misalignment detection: score, locate, attribute.

Read-only over the entries record and the word stream; its only product
is a diagnostic document (and its human-readable summary). Content is
measured in Chinese with character-bigram F1 -- word-order immune, since
a VSO sentence split over SVO subtitle screens scrambles order inside a
block without being wrong. Time is measured in Formosan with character
LCS after stripping segmentation marks, because the translators and the
recogniser do not yet agree on where words break. Number and loanword
anchors need no translation at all. Every threshold rides along in the
output, flagged uncalibrated until the human sample pass sets it.
"""
import re

from scripts.asrmt.align import dpalign

ENGINES = ("ailabs", "claude")

DEFAULT_THRESHOLDS = {"content": 0.25, "conf": 0.7, "recover": 0.5}

CLASSES = ("ok", "offset", "asr-doubt", "mismatch", "no-speech")


# ----------------------------------------------------------------- scores


def _bigrams(text):
    text = re.sub(r"\s+", "", text)
    if len(text) < 2:
        if text:
            return {text: 1}
        return {}
    counts = {}
    for i in range(len(text) - 1):
        pair = text[i:i + 2]
        counts[pair] = counts.get(pair, 0) + 1
    return counts


def char_bigram_f1(a, b):
    """Order-insensitive content similarity of two Chinese strings."""
    ca = _bigrams(a)
    cb = _bigrams(b)
    if not ca or not cb:
        return 0.0
    overlap = 0
    for key, count in ca.items():
        overlap += min(count, cb.get(key, 0))
    total = sum(ca.values()) + sum(cb.values())
    return 2.0 * overlap / total


_MARKS = re.compile(r"[\s\-'’ʼˈ⌃^:]+")


def strip_marks(text):
    """Drop segmentation marks and fold case before character LCS."""
    return _MARKS.sub("", text).lower()


def lcs_ratio(a, b):
    """Normalised character LCS of the mark-stripped strings."""
    a = strip_marks(a)
    b = strip_marks(b)
    if not a or not b:
        return 0.0
    previous = [0] * (len(b) + 1)
    for ch_a in a:
        current = [0]
        for j, ch_b in enumerate(b):
            if ch_a == ch_b:
                current.append(previous[j] + 1)
            else:
                current.append(max(previous[j + 1], current[j]))
        previous = current
    return 2.0 * previous[len(b)] / (len(a) + len(b))


# ----------------------------------------------------------------- blocks


def build_blocks(sents, entries):
    """One block per Chinese sentence of the subtitle stream.

    The unit is semantic, decided from the subtitle text: each entry
    carries `sent_end` -- would its line end in a full stop (True) or a
    comma (False)? A block is a run of consecutive entries up to and
    including the next full stop, and never crosses one: word order may
    scramble inside a sentence (VSO against SVO), never beyond it. An
    entry without the flag stands alone. Speech sentences overlapping
    the block's span ride along for reference only.
    """
    blocks = []
    current = []
    for j, row in enumerate(entries):
        current.append(j)
        if row.get("sent_end", True):
            blocks.append({"entries": current, "sents": []})
            current = []
    if current:
        blocks.append({"entries": current, "sents": []})

    for block in blocks:
        first = entries[block["entries"][0]]
        last = entries[block["entries"][-1]]
        for i, (start, end, _) in enumerate(sents):
            overlap = (min(end, last["true_end"])
                       - max(start, first["true_start"]))
            if overlap > 0:
                block["sents"].append(i)
    return blocks


def merge_groups(doc, entries, dp_floor=0.2, max_span=20.0):
    """Merge units for the deliverable: sentence blocks, unioned by
    interleaving evidence (使用者裁定：交錯的句子合併，不移時間).

    Evidence unions neighbouring sentence blocks: a DP pairing spanning
    more than one block (score >= dp_floor, strongest first) and an
    `offset` entry whose delta-shifted true window overlaps a
    neighbouring block. A union always covers the full consecutive
    block range (an SRT entry is one unbroken stretch of time) and is
    refused when the merged span would exceed `max_span` seconds --
    the cap that keeps evidence chains from swallowing half a minute.
    Returns {entry index -> group id}.
    """
    block_of = {}
    for record in doc["entries"]:
        block_of[record["index"]] = record["block"]

    span = {}
    for row in entries:
        block = block_of[row["index"]]
        if block not in span:
            span[block] = [row["true_start"], row["true_end"]]
        span[block][0] = min(span[block][0], row["true_start"])
        span[block][1] = max(span[block][1], row["true_end"])

    parent = {}
    for block in span:
        parent[block] = block

    edges = _dp_edges(doc, entries, block_of, dp_floor)
    edges += _offset_edges(doc, entries, block_of, span)
    edges.sort(key=lambda edge: -edge[0])
    for _, lo_block, hi_block in edges:
        _range_union(parent, span, lo_block, hi_block, max_span)

    out = {}
    for row in entries:
        out[row["index"]] = _find(parent, block_of[row["index"]])
    return out


def _find(parent, node):
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _range_members(parent, span, lo_block, hi_block):
    """Every block in [lo..hi], plus whatever their groups already hold
    -- the union may drag in blocks already grouped beyond the range."""
    members = []
    for block in span:
        if lo_block <= block <= hi_block:
            members.append(block)
    for block in list(members):
        root = _find(parent, block)
        for other in span:
            if _find(parent, other) == root and other not in members:
                members.append(other)
    return members


def _range_union(parent, span, lo_block, hi_block, max_span):
    """Union every block in [lo..hi] unless the span would blow the
    cap; covering the whole range keeps entries time-contiguous."""
    members = _range_members(parent, span, lo_block, hi_block)
    lo = span[members[0]][0]
    hi = span[members[0]][1]
    for block in members:
        lo = min(lo, span[block][0])
        hi = max(hi, span[block][1])
    if hi - lo > max_span:
        return
    first = members[0]
    for block in members[1:]:
        parent[_find(parent, block)] = _find(parent, first)


def _dp_edges(doc, entries, block_of, dp_floor):
    """Union evidence: DP pairings that span more than one block."""
    edges = []
    for match in doc.get("matched_entries", []):
        if match["score"] < dp_floor:
            continue
        touched = set()
        for side in ("a", "b"):
            lo, hi = match[side]
            # the record is our own output, but clamp anyway: a stale or
            # hand-edited file must not index outside the entry list
            for position in range(max(0, lo), min(hi, len(entries))):
                touched.add(block_of[entries[position]["index"]])
        if len(touched) > 1:
            edges.append((match["score"], min(touched), max(touched)))
    return edges


def _offset_edges(doc, entries, block_of, span):
    """Union evidence: offset entries whose shifted window lands in a
    neighbouring block."""
    deltas = {}
    classes = {}
    for record in doc["entries"]:
        deltas[record["index"]] = record.get("best_delta", 0.0)
        classes[record["index"]] = record.get("class", "ok")
    edges = []
    for row in entries:
        index = row["index"]
        if classes.get(index) != "offset" or not deltas.get(index):
            continue
        lo = row["true_start"] + deltas[index]
        hi = row["true_end"] + deltas[index]
        home = block_of[index]
        for block, (b_lo, b_hi) in span.items():
            if block == home:
                continue
            if min(hi, b_hi) - max(lo, b_lo) > 0:
                edges.append((0.0, min(home, block), max(home, block)))
    return edges


# ------------------------------------------------------------------ time


def delta_scan(entry, target_text, words, span=3.0, step=0.1):
    """Best time shift of the entry window over the word stream.

    `target_text` is the subtitle's Formosan translation -- computed
    once; sliding only re-reads the word stream, no translation call is
    ever made in here. A word belongs to the shifted window when its
    midpoint falls inside. Ties prefer the smaller |delta|.
    """
    best_delta = 0.0
    best_score = -1.0
    curve = []
    steps = int(round(span / step))
    for k in range(-steps, steps + 1):
        delta = k * step
        lo = entry["true_start"] + delta
        hi = entry["true_end"] + delta
        parts = []
        for item in words:
            mid = (item["start"] + item["end"]) / 2.0
            if lo <= mid < hi:
                parts.append(item["w"])
        score = lcs_ratio(" ".join(parts), target_text)
        curve.append((round(delta, 3), score))
        better = score > best_score + 1e-9
        same = abs(score - best_score) <= 1e-9
        if better or (same and abs(delta) < abs(best_delta)):
            best_score = score
            best_delta = round(delta, 3)
    return best_delta, curve


def rolling_median(values, window=21):
    """Centred rolling median; edges use what is available."""
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        chunk = sorted(values[lo:hi])
        out.append(chunk[len(chunk) // 2])
    return out


# --------------------------------------------------------------- anchors


_ZH_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3,
              "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZH_UNITS = {"十": 10, "百": 100, "千": 1000}


def _zh_number(run):
    total = 0
    digit = 0
    for ch in run:
        if ch in _ZH_DIGITS:
            digit = _ZH_DIGITS[ch]
        else:
            unit = _ZH_UNITS[ch]
            if digit == 0:
                digit = 1
            total += digit * unit
            digit = 0
    return total + digit


def find_numbers(text):
    """Arabic and Chinese numerals in a subtitle line, as ints."""
    values = []
    for run in re.findall(r"\d+", text):
        values.append(int(run))
    zh = "".join(_ZH_DIGITS) + "".join(_ZH_UNITS)
    for run in re.findall("[%s]+" % zh, text):
        values.append(_zh_number(run))
    return values


def _window_words(words, lo, hi):
    """The word stream cut to a time window (就近定位); None = no bound."""
    out = []
    for item in words:
        if lo is not None and item["start"] < lo:
            continue
        if hi is not None and item["start"] >= hi:
            continue
        out.append(item)
    return out


def match_anchors(values, words, numerals, lo=None, hi=None):
    """Numeral anchors located in the word stream, no translation.

    With `lo`/`hi` the search is windowed: a form heard minutes away is
    no evidence for this entry (就近定位).
    """
    hits = []
    for value in values:
        forms = numerals.get(str(value), [])
        for item in _window_words(words, lo, hi):
            if item["w"].lower() in forms:
                hits.append({"value": value, "time": item["start"],
                             "word": item["w"]})
                break
    return hits


def _edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, 1):
        current = [i]
        for j, ch_b in enumerate(b, 1):
            cost = 0 if ch_a == ch_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + cost))
        previous = current
    return previous[len(b)]


def _loanword_matches(forms, item):
    for form in forms:
        if _edit_distance(item["w"].lower(), form) <= 1:
            return True
    return False


def match_loanwords(subtitle, words, table, lo=None, hi=None):
    """Loanword proper-name anchors, matched within one edit."""
    hits = []
    for name, forms in table.items():
        if name not in subtitle:
            continue
        for item in _window_words(words, lo, hi):
            if _loanword_matches(forms, item):
                hits.append({"name": name, "time": item["start"],
                             "word": item["w"]})
                break
    return hits


# ---------------------------------------------------------- attribution


def classify(row, thresholds):
    """The attribution matrix. `row` carries every number it needs."""
    if not row["word_i"]:
        return "no-speech"
    best = 0.0
    for engine in ENGINES:
        best = max(best, row["block_score"].get(engine, 0.0),
                   row["entry_score"].get(engine, 0.0))
    if best >= thresholds["content"]:
        return "ok"
    if row["avg_conf"] < thresholds["conf"]:
        return "asr-doubt"
    if row["recovered"] >= thresholds["recover"]:
        return "offset"
    return "mismatch"


def recover_pairs(entries, band_seconds=10.0):
    """The DP pairing over MT text vs subtitle text (配對恢復)."""
    a_units = []
    b_units = []
    for row in entries:
        zh_best = ""
        for engine in ENGINES:
            candidate = row.get("zh", {}).get(engine, "")
            if len(candidate) > len(zh_best):
                zh_best = candidate
        a_units.append((row["true_start"], row["true_end"], zh_best))
        b_units.append((row["true_start"], row["true_end"],
                        row.get("subtitle", "")))
    return dpalign.align(a_units, b_units, char_bigram_f1,
                         band_seconds=band_seconds)


# ------------------------------------------------------------- document


def _block_texts(blocks, entries):
    """Concatenated subtitle and MT text per block."""
    out = []
    for block in blocks:
        subtitle = []
        zh = {}
        for engine in ENGINES:
            zh[engine] = []
        for j in block["entries"]:
            subtitle.append(entries[j].get("subtitle", ""))
            for engine in ENGINES:
                zh[engine].append(entries[j].get("zh", {}).get(engine, ""))
        joined = {"subtitle": "".join(subtitle)}
        for engine in ENGINES:
            joined[engine] = "".join(zh[engine])
        out.append(joined)
    return out


def _content_scores(row, block):
    """Block-level and entry-level bigram F1 per engine."""
    block_score = {}
    entry_score = {}
    for engine in ENGINES:
        block_score[engine] = char_bigram_f1(block[engine],
                                             block["subtitle"])
        entry_score[engine] = char_bigram_f1(
            row.get("zh", {}).get(engine, ""),
            row.get("subtitle", ""))
    return block_score, entry_score


def _avg_conf(row, words):
    confs = []
    for index in row.get("word_i", []):
        confs.append(words[index].get("conf", 0.0))
    if not confs:
        return 0.0
    return sum(confs) / len(confs)


def _time_recovery(row, words):
    """Best delta and the score it recovers, from the longest back-MT."""
    target = ""
    for engine in ENGINES:
        candidate = row.get("formosan_from_zh", {}).get(engine, "")
        if len(candidate) > len(target):
            target = candidate
    if not target or not row.get("word_i"):
        return 0.0, 0.0
    best_delta, curve = delta_scan(row, target, words)
    recovered = 0.0
    for delta, score in curve:
        if delta == best_delta:
            recovered = score
    return best_delta, recovered


def _recovered_pairs(records, entries):
    """The DP pairing, run only when some entry needs recovering."""
    low = []
    for record in records:
        if record["class"] in ("mismatch", "asr-doubt", "offset"):
            low.append(record["index"])
    if not low:
        return []
    matched = recover_pairs(entries)
    for match in matched:
        match["a"] = list(match["a"])
        match["b"] = list(match["b"])
    return matched


def _entry_anchors(row, index, words, numerals, loanwords,
                   numbers_by_entry, anchor_near):
    subtitle = row.get("subtitle", "")
    lo = row["true_start"] - anchor_near
    hi = row["true_end"] + anchor_near
    if numbers_by_entry is not None:
        values = numbers_by_entry.get(index, [])
    else:
        values = find_numbers(subtitle)
    found = []
    if numerals is not None:
        found.extend(match_anchors(values, words, numerals, lo=lo, hi=hi))
    if loanwords is not None:
        found.extend(match_loanwords(subtitle, words, loanwords,
                                     lo=lo, hi=hi))
    return found


def diagnose(srt_name, entries, words, sents, thresholds=None,
             numerals=None, loanwords=None, numbers_by_entry=None,
             anchor_near=10.0):
    """Score every entry and return the diagnostic document.

    Pure: reads the entries record, the word stream and the sentence
    spans; writes nothing. Anchor tables are optional -- without them
    the anchor section is empty, never wrong.
    """
    if thresholds is None:
        thresholds = dict(DEFAULT_THRESHOLDS)

    blocks = build_blocks(sents, entries)
    block_of = {}
    for pos, block in enumerate(blocks):
        for j in block["entries"]:
            block_of[j] = pos
    block_text = _block_texts(blocks, entries)

    records = []
    deltas = []
    for j, row in enumerate(entries):
        block_score, entry_score = _content_scores(
            row, block_text[block_of[j]])
        agreement = char_bigram_f1(row.get("zh", {}).get("ailabs", ""),
                                   row.get("zh", {}).get("claude", ""))
        best_delta, recovered = _time_recovery(row, words)
        deltas.append(best_delta)
        record = {
            "index": row.get("index", j + 1),
            "block": block_of[j],
            "word_i": row.get("word_i", []),
            "avg_conf": round(_avg_conf(row, words), 3),
            "block_score": block_score,
            "entry_score": entry_score,
            "engine_agreement": round(agreement, 3),
            "best_delta": best_delta,
            "recovered": round(recovered, 3),
        }
        record["class"] = classify(record, thresholds)
        records.append(record)

    anchors = []
    if numerals is not None or loanwords is not None:
        for j, row in enumerate(entries):
            index = row.get("index", j + 1)
            found = _entry_anchors(row, index, words, numerals, loanwords,
                                   numbers_by_entry, anchor_near)
            if found:
                anchors.append({"index": index, "hits": found})

    return {
        "srt_name": srt_name,
        "calibrated": False,
        "thresholds": thresholds,
        "entries": records,
        "offset_curve": rolling_median(deltas),
        "matched_entries": _recovered_pairs(records, entries),
        "anchors": anchors,
    }


def block_view(doc, entries):
    """The per-entry block view: sentence bars, punctuation, verdicts.

    ┌ opens a sentence block, │ continues it; 。/， is the sentence-end
    label the segmentation decided; [class] is the verdict. One glance
    shows what the detector saw.
    """
    classes = {}
    blocks = {}
    for record in doc["entries"]:
        classes[record["index"]] = record["class"]
        blocks[record["index"]] = record["block"]
    lines = []
    previous = None
    for row in entries:
        index = row["index"]
        bar = "│"
        if blocks.get(index) != previous:
            bar = "┌"
        mark = "，"
        if row.get("sent_end", True):
            mark = "。"
        lines.append("%s 塊%-3d %3d %s%s  [%s]"
                     % (bar, blocks.get(index, -1), index,
                        row.get("subtitle", ""), mark,
                        classes.get(index, "?")))
        previous = blocks.get(index)
    return "\n".join(lines)


def summary_md(doc, entries=None):
    """The human-readable side of the diagnosis."""
    counts = {}
    for name in CLASSES:
        counts[name] = 0
    for record in doc["entries"]:
        counts[record["class"]] += 1

    lines = ["# %s 語音-字幕對不齊偵測摘要" % doc["srt_name"], ""]
    state = "門檻尚未校準（calibrated: false）"
    if doc["calibrated"]:
        state = "門檻已經人工校準"
    lines.append("狀態：%s，門檻 %s" % (state, doc["thresholds"]))
    lines.append("")
    lines.append("| 歸類 | 條數 |")
    lines.append("|---|---|")
    for name in CLASSES:
        lines.append("| %s | %d |" % (name, counts[name]))
    lines.append("")

    examples = []
    for record in doc["entries"]:
        if record["class"] in ("mismatch", "asr-doubt") and \
                len(examples) < 10:
            examples.append(record)
    if examples:
        lines.append("## 代表例（被標的條目）")
        lines.append("")
        for record in examples:
            lines.append("- 條目 %d：%s，塊級分數 %s，conf %.2f，"
                         "最佳 δ %+.1fs" % (
                             record["index"], record["class"],
                             record["block_score"], record["avg_conf"],
                             record["best_delta"]))
        lines.append("")
    if entries is not None:
        lines.append("## 塊視圖（┌新句 │同句延續；。句尾 ，未完；[歸類]）")
        lines.append("")
        lines.append("```")
        lines.append(block_view(doc, entries))
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"
