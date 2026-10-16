"""開會了字幕清洗的命令列。一步一個子命令，照順序跑：

    python -m scripts.aiyalaeho.cleaning 詞庫        # 1-詞庫
    python -m scripts.aiyalaeho.cleaning 候選        # 2-候選（含語言別推測）
    python -m scripts.aiyalaeho.cleaning 送判 文字   # 3-判定/文字分類/<族語>/待判-bNN.csv
      （Opus subagent 照 brief_text.md 寫 bNN.csv）
    python -m scripts.aiyalaeho.cleaning 匯入 文字
    python -m scripts.aiyalaeho.cleaning 送判 看圖   # 3-判定/看圖/<族語>/待判-bNN.csv
      （Opus subagent 照 brief_image.md 寫 bNN.csv）
    python -m scripts.aiyalaeho.cleaning 匯入 看圖
    python -m scripts.aiyalaeho.cleaning 清洗        # 4-清洗版、5-交付/修改前後對照表.csv
    python -m scripts.aiyalaeho.cleaning 報表        # 5-交付 另外三份

每一步缺上一步的產出就指名中止。Kari-SRT 只讀。
"""
import argparse
import collections
import csv
import os
import sys

from scripts.aiyalaeho import episodes
from scripts.aiyalaeho import paths as store
from scripts.aiyalaeho.cleaning import apply
from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.cleaning import dialect
from scripts.aiyalaeho.cleaning import paths
from scripts.aiyalaeho.cleaning import report
from scripts.aiyalaeho.cleaning import source
from scripts.aiyalaeho.cleaning import verdicts
from scripts import languages
from scripts.errors import PipelineError
from scripts.lexicon import dictionary
from scripts.lexicon import kaldi_words
from scripts.lexicon import klokah
from scripts.lexicon import script
from scripts.news import asrmt_run

CHANGES_CSV = "修改前後對照表.csv"
SPELLING_CSV = "拼寫不一致表.csv"
DICTIONARY_CSV = "辭典比對表.csv"
DIALECT_CSV = "語言別推測表.csv"


def _srt(srt_name):
    return store.stage_path(store.SRT_DIR, srt_name, ".srt")


def _catalogue():
    out = {}
    for entry in episodes.load():
        out[entry["srt_name"]] = entry
    return out


def _language_dirs(base, language):
    return os.path.join(base, language)


# ------------------------------------------------------------------ 詞庫

def step_lexicon(layout):
    vocabs = klokah.vocabularies(paths.KLOKAH_SOURCE, paths.KLOKAH_NAMES)
    written = klokah.write_all(vocabs, layout.klokah)
    print("E樂園 %d 個語別 → %s" % (len(written), layout.klokah))
    for language in sorted(paths.DICTIONARY_VARIETY):
        model = asrmt_run.model_id_of(languages.english_for(language))
        words = kaldi_words.words_of(kaldi_words.find(model))
        path = os.path.join(layout.kaldi, language + ".txt")
        dictionary.write(words, path)
        print("Kaldi %s %d 詞 → %s" % (language, len(words), path))


# ------------------------------------------------------------ 共用的脈絡

class Context(object):
    """候選以後每一步都要的東西：語別推測、各族候選、逐條文字。"""

    def __init__(self, layout):
        self.layout = layout
        catalogue = _catalogue()
        by_language = collections.defaultdict(dict)
        for name, words in klokah.load_all(layout.klokah).items():
            language, variety, _code = klokah.variety_of(name)
            by_language[language][variety] = words
        self.entries = {}
        self.texts = {}
        self.results = []
        targets = collections.defaultdict(list)
        for srt_name in paths.TARGETS:
            row = catalogue[srt_name]
            language = row["族語別(中)"]
            entries = source.read_srt(_srt(srt_name))
            self.entries[srt_name] = entries
            for entry in entries:
                self.texts[(srt_name, entry.number)] = entry
            lines = []
            for entry in entries:
                lines.append(entry.formosan)
            result = dialect.infer(lines, by_language[language], language,
                                   labelled=row["語言別"])
            self.results.append((srt_name, language, row["語言別"], result))
            targets[language].append(
                candidates.EpisodeText(srt_name, language, result.considered,
                                       entries))
        self.language_of = {}
        for srt_name in paths.TARGETS:
            self.language_of[srt_name] = catalogue[srt_name]["族語別(中)"]
        self.builts = {}
        for language in sorted(targets):
            # b、c 只做「多於 1 則影片」的族語（承辦原文）。
            if len(targets[language]) < 2:
                continue
            evidence = candidates.Evidence(
                dictionary.load(store.lexicon_path(language)),
                by_language[language],
                dictionary.load(os.path.join(layout.kaldi,
                                             language + ".txt")),
                _corpus(catalogue, language), _transcripts(language),
                paths.DICTIONARY_VARIETY[language])
            self.builts[language] = candidates.build(targets[language],
                                                     evidence)
        self._maps = {}

    def strips_for(self, srt_name, number):
        if srt_name not in self._maps:
            self._maps[srt_name] = source.checked_cue_map(srt_name,
                                                          _srt(srt_name))
        return source.strips(srt_name, self._maps[srt_name][number])

    def text_verdicts(self, required=True):
        out = {}
        for language in self.builts:
            folder = _language_dirs(self.layout.text_verdicts, language)
            got = verdicts.load_text(folder) if os.path.isdir(folder) else {}
            lacking = []
            for key in self.builts[language].to_send():
                if key not in got:
                    lacking.append(key)
            if lacking and required:
                raise PipelineError("%s 有 %d 個詞還沒送判或沒判：%s"
                                    % (language, len(lacking),
                                       "、".join(lacking[:10])))
            out[language] = got
        return out

    def image_items(self, text):
        by_language = collections.defaultdict(list)
        for language, built in self.builts.items():
            by_language[language].extend(report.typo_items(
                built, text[language], self.texts, self.strips_for))
        for srt_name in paths.TARGETS:
            by_language[self.language_of[srt_name]].extend(report.gap_items(
                srt_name, self.entries[srt_name], self.strips_for))
        return by_language

    def image_verdicts(self, items):
        out = {}
        for language in sorted(items):
            if not items[language]:
                continue
            folder = _language_dirs(self.layout.image_verdicts, language)
            if not os.path.isdir(folder):
                raise PipelineError("看圖還沒送判：%s" % folder)
            out.update(verdicts.load_image(folder))
        return out

    def overrides(self):
        return verdicts.load_overrides(self.layout.overrides)

    def plan(self):
        """(fixes, merges, 已改的 (成果檔名, 字幕編號, 詞) 集合)。"""
        text = self.text_verdicts()
        items = self.image_items(text)
        image = self.image_verdicts(items)
        overrides = self.overrides()
        fixes = []
        for language, built in self.builts.items():
            fixes.extend(report.typo_fixes(built, text[language], image,
                                           self.texts,
                                           overrides.get(language, {})))
        gaps = []
        for srt_name in paths.TARGETS:
            gaps.extend(report.gap_items(srt_name, self.entries[srt_name],
                                         self.strips_for))
        merges = report.gap_merges(gaps, image)
        return text, fixes, merges


def _corpus(catalogue, language):
    """{詞: Counter(集數)}：開會了該族全部已交付集。"""
    out = collections.defaultdict(collections.Counter)
    for srt_name, row in catalogue.items():
        if row["族語別(中)"] != language or row["pending"] or row["abnormal"]:
            continue
        number = candidates.episode_number(srt_name)
        for entry in source.read_srt(_srt(srt_name)):
            for token in candidates.tokens(
                    candidates.tentative(entry.formosan)):
                out[token.lower()][number] += 1
    return out


def _transcripts(language):
    """上字文稿（Kari-SRT/aiyalaeho/text/1-句對.csv）該族族語欄的詞次。"""
    out = collections.Counter()
    with open(store.TEXT_PAIRS, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["族語別(中)"] == language:
                out.update(script.words(row["族語"]))
    return out


# ------------------------------------------------------------- 各個步驟

def step_candidates(layout):
    context = Context(layout)
    for language, built in sorted(context.builts.items()):
        path = os.path.join(layout.candidates, language + ".csv")
        report.write(path, built.rows())
        screens = collections.Counter()
        for word in built.words.values():
            screens[word.screen] += 1
        print("%s %d 個詞形 %s → %s"
              % (language, len(built.words), dict(screens), path))
    for srt_name, _language, _labelled, result in context.results:
        print("%s %s %s %s" % (srt_name, result.verdict, result.variety,
                               result.code))


def step_send_text(layout):
    context = Context(layout)
    for language, built in sorted(context.builts.items()):
        written = verdicts.export_text(
            built, context.texts, built.considered,
            _language_dirs(layout.text_verdicts, language))
        print("%s 新送 %d 批" % (language, len(written)))
        for path in written:
            print("  " + path)


def step_ingest_text(layout):
    context = Context(layout)
    for language, got in sorted(context.text_verdicts().items()):
        kinds = collections.Counter()
        for verdict in got.values():
            kinds[verdict.kind] += 1
        print("%s %d 詞 %s" % (language, len(got), dict(kinds)))


def step_send_image(layout):
    context = Context(layout)
    items = context.image_items(context.text_verdicts())
    for language in sorted(items):
        written = verdicts.export_image(
            items[language], _language_dirs(layout.image_verdicts, language))
        print("%s %d 處，新送 %d 批"
              % (language, len(items[language]), len(written)))
        for path in written:
            print("  " + path)


def step_ingest_image(layout):
    context = Context(layout)
    items = context.image_items(context.text_verdicts())
    image = context.image_verdicts(items)
    kinds = collections.Counter()
    for verdict in image.values():
        kinds[verdict.kind] += 1
    print("看圖 %d 處 %s" % (len(image), dict(kinds)))


def _clean_all(fixes, merges):
    changes = []
    bodies = {}
    for srt_name in paths.TARGETS:
        with open(_srt(srt_name), encoding="utf-8") as handle:
            original = handle.read()
        body, found = apply.clean_episode(original, srt_name, fixes, merges)
        bodies[srt_name] = body
        changes.extend(found)
    return bodies, changes


def step_clean(layout):
    context = Context(layout)
    _text, fixes, merges = context.plan()
    bodies, changes = _clean_all(fixes, merges)
    os.makedirs(paths.guard(layout.cleaned), exist_ok=True)
    for srt_name, body in bodies.items():
        path = paths.guard(os.path.join(layout.cleaned, srt_name + ".srt"))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
    path = os.path.join(layout.deliver, CHANGES_CSV)
    report.write(path, apply.change_rows(changes))
    kinds = collections.Counter()
    for change in changes:
        kinds[change.kind] += 1
    print("清洗版 %d 集 → %s" % (len(bodies), layout.cleaned))
    print("修改 %d 處 %s → %s" % (len(changes), dict(kinds), path))


def step_report(layout):
    context = Context(layout)
    text, fixes, _merges = context.plan()
    # 每個 Fix 都會套上（apply 找不到要改的詞就中止），所以它們就是
    # 「已修改」的那些處。
    changed = set()
    for fix in fixes:
        changed.add((fix.srt_name, fix.number, fix.word))
    overrides = context.overrides()
    merged = {}
    for language in context.builts:
        merged.update(text[language])
    outputs = (
        (SPELLING_CSV, report.spelling_rows(context.builts, merged,
                                            changed, overrides)),
        (DICTIONARY_CSV, report.dictionary_rows(context.builts, merged,
                                                changed, context.texts,
                                                overrides)),
        (DIALECT_CSV, report.dialect_rows(context.results)),
    )
    for name, rows in outputs:
        path = os.path.join(layout.deliver, name)
        report.write(path, rows)
        print("%s %d 列 → %s" % (name, len(rows) - 1, path))


STEPS = {
    "詞庫": step_lexicon,
    "候選": step_candidates,
    "清洗": step_clean,
    "報表": step_report,
}
TWO_PART = {
    ("送判", "文字"): step_send_text,
    ("匯入", "文字"): step_ingest_text,
    ("送判", "看圖"): step_send_image,
    ("匯入", "看圖"): step_ingest_image,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("step", help="詞庫／候選／送判／匯入／清洗／報表")
    ap.add_argument("kind", nargs="?", help="送判、匯入要指定：文字／看圖")
    ap.add_argument("--out", default=paths.OUT, help="輸出根目錄")
    args = ap.parse_args(argv)
    layout = paths.Layout(args.out)
    if args.step in STEPS and not args.kind:
        STEPS[args.step](layout)
        return 0
    if (args.step, args.kind) in TWO_PART:
        TWO_PART[(args.step, args.kind)](layout)
        return 0
    ap.error("不認得的步驟：%s %s" % (args.step, args.kind or ""))
    return 2


if __name__ == "__main__":
    sys.exit(main())
