#!/usr/bin/env python3
"""兩張 CSV：逐條語言標記、逐集語言分布。

    python3 -m scripts.aiyalaeho.langcheck.report

食ê是 store：`1-ocr/3-srt/`、`1-ocr/4-語言檢查/詞庫/`、`smkul.csv`。
無網路、無模型、無讀影片，所以 `rebuild --verify` 涵蓋會著。

逐條表**逐條攏收**，一條都無漏（使用者裁定 2026-09-10）。逐集表
四个計數欄相加等於字幕條數，表家己才講會通。
"""
import argparse
import collections
import csv
import os
import sys

from scripts import catalogue_checks as checks
from scripts.aiyalaeho import paths
from scripts.aiyalaeho.langcheck import dictionary
from scripts.aiyalaeho.langcheck import mark
from scripts.errors import PipelineError

# 前七欄佮其他五張表同名同序（見 `scripts/catalogue_checks.py`）。
# 本底這爿ê `本集族語` 就是 `族語別(中)`——仝一件代誌兩个名，開兩張表
# 對照ê時愛佇心內先翻一擺。
HEAD = list(checks.head(checks.EPISODE_KEYS))

MARK_HEADER = HEAD + ["字幕編號", "開始時間", "結束時間",
                      "這列的語言", "疑似語言", "疑似語言詞庫比對命中率",
                      "族語列", "華語列"]

DIST_HEADER = HEAD + ["字幕條數", "純族語",
                      "族語夾雜華語", "華語", "無法確定"]

Episode = collections.namedtuple(
    "Episode", "srt_name number tribe english variety code text")


def _head_cells(episode):
    """共同ê頭七欄，照 `HEAD` ê順序。"""
    return [episode.srt_name, checks.AIYALAEHO, episode.number,
            episode.english, episode.tribe, episode.variety, episode.code]


def percent(rate):
    return "%d%%" % round(rate * 100)


def write_table(path, header, rows):
    """CSV 一律 \\n 結尾。Excel 讀有，diff 才袂規份反白。"""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def _sorted(episodes):
    return sorted(episodes, key=lambda one: one.srt_name)


def mark_rows(episodes, lexicons):
    out = []
    for episode in _sorted(episodes):
        marked = mark.marks(episode.text, episode.tribe, lexicons,
                            language_code=episode.code)
        for one in sorted(marked, key=lambda m: m.number):
            rate = percent(one.rate) if one.label == mark.UNSURE else ""
            out.append(_head_cells(episode)
                       + [one.number, one.start, one.end, one.label,
                          one.suspect, rate, one.formosan, one.han])
    return out


def dist_rows(episodes, lexicons):
    out = []
    for episode in _sorted(episodes):
        marked = mark.marks(episode.text, episode.tribe, lexicons,
                            language_code=episode.code)
        tally = collections.Counter()
        for one in marked:
            tally[one.label] += 1
        out.append(_head_cells(episode)
                   + [len(marked), tally[mark.PURE], tally[mark.MIXED],
                      tally[mark.CHINESE], tally[mark.UNSURE]])
    return out


def write_marks(path, episodes, lexicons):
    return write_table(path, MARK_HEADER, mark_rows(episodes, lexicons))


def write_distribution(path, episodes, lexicons):
    return write_table(path, DIST_HEADER, dist_rows(episodes, lexicons))


def load_lexicons(tribes, folder=None):
    """指名ê幾族ê詞庫。欠件指名喝停，莫恬恬跳過——彼一族ê集會規份
    判做「純族語」，看起來若無代誌。"""
    out = {}
    for tribe in sorted(tribes):
        if folder is None:
            path = paths.lexicon_path(tribe)
        else:
            path = os.path.join(folder, tribe + ".txt")
        out[tribe] = dictionary.load(path)
    return out


def load_all_lexicons(folder=None):
    """store 內底**逐份**詞庫，毋是干焦有集數彼幾族ê。

    干焦載有集數ê彼幾族（開會了 11 族）ê話，賰彼五族（鄒、邵、
    噶瑪蘭、撒奇萊雅、卡那卡那富）ê話永遠標袂出來——來賓講彼幾族
    ê語言ê時，比對揣無較倚ê，就恬恬歸做「純族語」。
    """
    where = folder or paths.LEXICON_DIR
    if not os.path.isdir(where):
        raise PipelineError("揣無詞庫資料夾：%s" % where)
    tribes = set()
    for name in os.listdir(where):
        if name.endswith(".txt"):
            tribes.add(name[:-4])
    if not tribes:
        raise PipelineError("詞庫資料夾內底一份都無：%s" % where)
    return load_lexicons(tribes, folder)


def lexicons_for(episodes, folder=None):
    """比對愛用ê詞庫：store 內底逐份，閣加一擺「逐集ê族語別攏有」ê
    把關。

    資料夾內底有幾份就載幾份——別族來賓ê話才標會出來。毋過「這集
    ê族語別家己有詞庫」是硬ê：無彼份ê話，彼集逐條攏會判做別族抑
    是規份判做純族語，兩款攏是恬恬歹去。
    """
    lexicons = load_all_lexicons(folder)
    missing = set()
    for episode in episodes:
        if episode.tribe not in lexicons:
            missing.add(episode.tribe)
    if missing:
        raise PipelineError("詞庫欠這幾族：%s" % "、".join(sorted(missing)))
    return lexicons


def load_episodes(tracker_path=None, srt_dir=None):
    """對 smkul.csv 佮 3-srt/ 讀出逐集ê材料。

    smkul.csv 頭前有 BOM（Excel 寫ê），所以 utf-8-sig；用 utf-8 讀
    ê話頭一欄ê名會帶一个看袂著ê字元，`成果檔名` 查有、`節目名稱`
    查無，症頭是 KeyError 佇無關ê所在。
    """
    out = []
    path = tracker_path or paths.TRACKER_STORE
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        name = row["成果檔名"]
        srt_path = paths.stage_path(srt_dir or paths.SRT_DIR, name, ".srt")
        if not os.path.exists(srt_path):
            raise PipelineError("欠交付 SRT：%s" % srt_path)
        with open(srt_path, encoding="utf-8") as srt_handle:
            out.append(Episode(name, row["集數"], row["族語別(中)"],
                               row["族語別(英)"], row["語言別"],
                               row["語言別代號"], srt_handle.read()))
    return out


def run(marks_path=None, dist_path=None):
    episodes = load_episodes()
    lexicons = lexicons_for(episodes)
    one = write_marks(marks_path or paths.LANGCHECK_MARKS, episodes,
                      lexicons)
    two = write_distribution(dist_path or paths.LANGCHECK_DIST, episodes,
                             lexicons)
    print("逐條語言標記 寫出", one)
    print("逐集語言分布 寫出", two)
    return one, two


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    run()


if __name__ == "__main__":
    sys.exit(main())
