"""交付報表，以及「判定 → 要套用的修改」。

建議寫法依據順序（使用者確認 2026-10-15）：

  1. 該集語別的權威收錄（辭典語別與該集相同用辭典，不同用 E樂園 該語別）
  2. 開會了全語料（Kari-SRT 該族全部已交付集）出現次數
  3. 上字文稿出現次數

Claude 給的建議寫法如果不在權威裡，而錯字的相近寫法（或最接近的辭典
詞條）裡有權威收錄、又和 Claude 的建議差不到兩個字母的，改用那個，
Claude 的建議記在依據欄。判語言別差異的不給建議。

處理方式只有四個值：已修改、建議統一、待討論、不改。
"""
import collections
import os

from scripts.aiyalaeho.cleaning import apply
from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.cleaning import paths
from scripts.aiyalaeho.cleaning import rules
from scripts.aiyalaeho.cleaning import verdicts
from scripts.aiyalaeho.langcheck.report import write_table
from scripts.errors import PipelineError

CHANGED = "已修改"
UNIFY = "建議統一"
DISCUSS = "待討論"
KEEP = "不改"
HANDLING = (CHANGED, UNIFY, DISCUSS, KEEP)

SUGGEST_DISTANCE = 2

SPELLING_HEADER = ["族語別", "組別", "寫法", "各集次數", "辭典",
                   "E樂園見過的語別", "文字分類", "建議寫法", "處理方式", "依據"]
DICTIONARY_HEADER = ["族語別", "詞形", "辭典狀態", "最接近的辭典詞條",
                     "E樂園見過的語別", "Kaldi詞表", "出現次數", "第一次出現",
                     "族語列", "華語列", "處理方式", "依據"]
DIALECT_HEADER = ["成果檔名", "族語別(中)", "smkul標記語別", "推測語別",
                  "語言別代號", "把握", "各語別覆蓋率", "分段第一名", "依據"]


def write(path, rows):
    """rows[0] 是表頭。UTF-8 無 BOM、LF；不寫進 Kari-SRT。"""
    return write_table(paths.guard(path), rows[0], rows[1:])


# ------------------------------------------------------------- 建議寫法

def _rank(built, word):
    counts = built.evidence.corpus.get(word)
    corpus = sum(counts.values()) if counts else 0
    return (-corpus, -built.evidence.transcripts.get(word, 0), word)


def _display(built, word):
    if word in built.words:
        return built.words[word].display
    return word


def suggestion_for(key, built, verdict):
    """(建議寫法, 依據補註)。補註空字串表示照 Claude 的建議。"""
    claude = verdict.suggestion
    wanted = candidates.tokens(claude)
    target = " ".join(wanted).lower() if wanted else claude.lower()
    if built.authorised(target, key):
        return claude, ""
    word = built.words[key]
    options = []
    for other in list(word.neighbours) + list(word.nearest):
        if other in options or not built.authorised(other, key):
            continue
        if candidates.distance(other, target) <= SUGGEST_DISTANCE:
            options.append(other)
    if not options:
        return claude, ""
    chosen = sorted(options, key=lambda w: _rank(built, w))[0]
    shown = _display(built, chosen)
    return shown, "依該集語別權威改用 %s（Claude 建議 %s）" % (shown, claude)


# --------------------------------------------------------- 判定 → 修改

def _occurrences(word):
    out = []
    for place in word.occurrences:
        if place not in out:
            out.append(place)
    return out


def _form_in(entry, key):
    for token in candidates.tokens(candidates.tentative(entry.formosan)):
        if token.lower() == key:
            return token
    return None


def _typos(built, text):
    out = []
    for key in sorted(built.words):
        verdict = text.get(key)
        if verdict is not None and verdict.kind == verdicts.TYPO:
            out.append((key, verdict))
    return out


def typo_items(built, text, texts, strips_for):
    """判錯字的詞，逐處做成看圖項目。strips_for(成果檔名, 字幕編號)→[路徑]。"""
    items = []
    for key, verdict in _typos(built, text):
        target, _note = suggestion_for(key, built, verdict)
        for srt_name, number in _occurrences(built.words[key]):
            entry = texts[(srt_name, number)]
            form = _form_in(entry, key)
            if form is None:
                continue
            items.append(verdicts.ImageItem(
                srt_name, number, form, target, entry.formosan, entry.han,
                strips_for(srt_name, number)))
    return items


def typo_fixes(built, text, image, texts, overrides=None):
    """看圖確認為 OCR 讀錯或播出端錯字的，做成 Fix；看不出來的不改。

    overrides（{詞形小寫: 理由}）裡的詞是使用者改判待討論的，不改。
    """
    fixes = []
    for key, verdict in _typos(built, text):
        if key in (overrides or {}):
            continue
        target, note = suggestion_for(key, built, verdict)
        for srt_name, number in _occurrences(built.words[key]):
            form = _form_in(texts[(srt_name, number)], key)
            if form is None:
                continue
            seen = image.get((srt_name, number, form))
            if seen is None:
                raise PipelineError("%s 第 %d 條的「%s」還沒看圖"
                                    % (srt_name, number, form))
            if seen.kind == verdicts.UNREADABLE:
                continue
            replacement = target
            if seen.kind == verdicts.OCR_MISREAD and seen.screen:
                replacement = seen.screen
            basis = "文字分類：%s；看圖：%s" % (verdict.reason, seen.reason)
            if note:
                basis += "；" + note
            fixes.append(apply.Fix(srt_name, number, key, replacement,
                                   seen.kind, basis))
    return fixes


def gap_items(srt_name, entries, strips_for):
    """「’ 夾空白」逐處做成看圖項目（10 集都做，不限 b、c 的 9 集）。"""
    items = []
    for entry in entries:
        for gap in rules.apostrophe_gaps(entry.formosan):
            items.append(verdicts.ImageItem(
                srt_name, entry.number, gap.raw, gap.joined, entry.formosan,
                entry.han, strips_for(srt_name, entry.number)))
    return items


def gap_merges(items, image):
    """看圖判定後的撇號寫法；看不出來的維持規則清洗的結果。"""
    merges = []
    for item in items:
        seen = image.get((item.srt_name, item.number, item.word))
        if seen is None:
            raise PipelineError("%s 第 %d 條的「%s」還沒看圖"
                                % (item.srt_name, item.number, item.word))
        if seen.kind == verdicts.UNREADABLE:
            continue
        cleaned = rules.clean(item.word)[0]
        replacement = rules.clean(seen.screen or item.suggestion)[0]
        merges.append(apply.Merge(item.srt_name, item.number, cleaned,
                                  replacement,
                                  "彎撇換直撇；看圖：%s" % seen.reason))
    return merges


# ------------------------------------------------------------------ 表格

def _per_episode(counter):
    parts = []
    for number in sorted(counter):
        parts.append("%s:%d" % (number, counter[number]))
    return ";".join(parts)


def _fixed_share(word, changed):
    places = _occurrences(word)
    done = 0
    for srt_name, number in places:
        if (srt_name, number, word.key) in changed:
            done += 1
    return done, len(places)


def _typo_handling(word, changed, overrides=None):
    if word.key in (overrides or {}):
        return DISCUSS, "人工改判：" + overrides[word.key]
    done, total = _fixed_share(word, changed)
    if done == total:
        return CHANGED, ""
    if done:
        return CHANGED, "%d 處中 %d 處已修改，其餘看圖看不出來" % (total, done)
    return DISCUSS, "看圖看不出來，未修改"


def _authority_name(built, word):
    names = set()
    for srt_name, _number in word.occurrences:
        names.update(built.considered.get(srt_name, ()))
    return names


def _dictionary_verdict(built, word, text, changed, overrides=None):
    """(處理方式, 依據) for 辭典比對表。"""
    evidence = built.evidence
    if word.screen == candidates.SEEN_HERE:
        varieties = _authority_name(built, word)
        if evidence.dict_variety in varieties:
            return KEEP, "E樂園 同語別收錄"
        return DISCUSS, "辭典只收%s；該集推測 %s，E樂園 收錄，屬語言別差異" % (
            evidence.dict_variety or "單一語別", "、".join(sorted(varieties)))
    if word.screen == candidates.SEEN_ELSEWHERE:
        return DISCUSS, "E樂園 %s 收錄，不是該集語別" % "、".join(word.varieties)
    if word.screen == candidates.KALDI_ONLY:
        return KEEP, "ILRDF 語音模型詞表見過，辭典與 E樂園 未收"
    verdict = text.get(word.key)
    if verdict is None:
        raise PipelineError("「%s」送了文字分類卻沒有判定" % word.display)
    if verdict.kind == verdicts.TYPO:
        handling, extra = _typo_handling(word, changed, overrides)
        basis = "錯字：" + verdict.reason
        if extra:
            basis += "；" + extra
        return handling, basis
    if verdict.kind == "不同詞":
        return KEEP, "不同詞：%s" % verdict.reason
    return DISCUSS, "%s：%s" % (verdict.kind, verdict.reason)


def dictionary_rows(builts, text, changed, texts, overrides=None):
    """辭典比對表：與辭典不同（近似）或查無的詞。"""
    out = [list(DICTIONARY_HEADER)]
    for language in sorted(builts):
        built = builts[language]
        for key in sorted(built.words):
            word = built.words[key]
            if word.in_dict:
                continue
            handling, basis = _dictionary_verdict(
                built, word, text, changed,
                (overrides or {}).get(language, {}))
            first = _occurrences(word)[0]
            entry = texts[first]
            out.append([
                language, word.display, "近似" if word.nearest else "查無",
                ";".join(word.nearest[:3]), ";".join(word.varieties),
                "有" if word.in_kaldi else "無", _per_episode(word.episodes),
                "%s#%d" % first, entry.formosan, entry.han, handling, basis,
            ])
    return out


def _spelling_row(language, group, built, key, kind, suggestion, handling,
                  basis):
    if key in built.words:
        word = built.words[key]
        per = _per_episode(word.episodes)
        in_dict = word.in_dict
        varieties = word.varieties
    else:
        per = _per_episode(built.evidence.corpus.get(key) or {})
        in_dict = key in built.evidence.dictionary
        found = []
        for variety in sorted(built.evidence.klokah):
            if key in built.evidence.klokah[variety]:
                found.append(variety)
        varieties = tuple(found)
    return [language, group, _display(built, key), per,
            "有" if in_dict else "無", ";".join(varieties), kind, suggestion,
            handling, basis]


def _spelling_groups(built, text, changed, overrides=None):
    """[(組成員排序鍵, [(詞, 文字分類, 建議, 處理方式, 依據)…])…]"""
    groups = []
    targets = collections.OrderedDict()
    for key, verdict in _typos(built, text):
        target, note = suggestion_for(key, built, verdict)
        handling, extra = _typo_handling(built.words[key], changed,
                                         overrides)
        basis = verdict.reason
        for more in (note, extra):
            if more:
                basis += "；" + more
        targets.setdefault(target.lower(), (target, []))[1].append(
            (key, "錯字", target, handling, basis))
    for target_key, (target, members) in targets.items():
        rows = [(target_key, "", target, UNIFY, "該組統一寫法")]
        rows.extend(members)
        groups.append(rows)
    for key in sorted(text):
        verdict = text[key]
        if verdict.kind not in ("語言別差異", "斷詞不同", "不確定"):
            continue
        if key not in built.words or not built.words[key].neighbours:
            continue
        rows = [(key, verdict.kind, "", DISCUSS, verdict.reason)]
        for other in built.words[key].neighbours:
            rows.append((other, "", "", KEEP, "相近寫法"))
        groups.append(rows)
    members = collections.defaultdict(list)
    for key in sorted(built.words):
        if built.words[key].group:
            members[built.words[key].group].append(key)
    for name in sorted(members):
        rows = []
        for key in members[name]:
            found = "、".join(built.words[key].varieties) or "辭典"
            rows.append((key, "語言別差異", "", DISCUSS,
                         "兩種寫法分見於不同語別（本詞：%s）" % found))
        groups.append(rows)
    return groups


def spelling_rows(builts, text, changed, overrides=None):
    """拼寫不一致表：一組相近寫法佔好幾列，一種寫法一列。"""
    out = [list(SPELLING_HEADER)]
    for language in sorted(builts):
        built = builts[language]
        groups = _spelling_groups(built, text, changed,
                                  (overrides or {}).get(language, {}))
        groups.sort(key=lambda rows: rows[0][0])
        for number, rows in enumerate(groups, start=1):
            group = "%s-%03d" % (language, number)
            for key, kind, suggestion, handling, basis in rows:
                out.append(_spelling_row(language, group, built, key, kind,
                                         suggestion, handling, basis))
    return out


def _percent(rate):
    return "%d%%" % round(rate * 100)


def dialect_rows(results):
    """results：[(成果檔名, 族語別, smkul 標記語別, dialect.Result)…]。"""
    out = [list(DIALECT_HEADER)]
    for srt_name, language, labelled, result in sorted(results):
        order = sorted(result.rates, key=lambda n: (-result.rates[n], n))
        rates = []
        for name in order:
            rates.append("%s %s" % (name or language, _percent(
                result.rates[name])))
        total = sum(result.windows.values())
        windows = []
        for name in sorted(result.windows,
                           key=lambda n: (-result.windows[n], n)):
            windows.append("%s %d/%d 段" % (name or language,
                                           result.windows[name], total))
        margin = 0
        if len(order) > 1:
            margin = round((result.rates[order[0]]
                            - result.rates[order[1]]) * 100)
        basis = {
            "高": "第一名領先 %d 點" % margin,
            "中": "第一名只領先 %d 點" % margin,
            "混合": "分段第一名在不同語別之間交錯",
            "已標記": "smkul.csv 已標語別，照標記",
            "單一語別": "該族只有一個語別",
        }[result.verdict]
        out.append([srt_name, language, labelled, result.variety,
                    result.code, result.verdict, ";".join(rates),
                    ";".join(windows), basis])
    return out


def ensure(folder):
    os.makedirs(paths.guard(folder), exist_ok=True)
    return folder
