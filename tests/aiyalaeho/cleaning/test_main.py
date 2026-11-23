"""命令列的 Context：範圍跟著節目目錄、b、c 與推測只吃本族語列。

用 fixture 組一個小目錄：阿美兩集（其中一集夾別族來賓的「無法確定」
列）、太魯閣一集、阿美一集 pending。不讀 Kari-SRT、不連網路。

量到的坑（2026-11-23）：布農 119 有 223 條別族來賓（疑似賽夏、排灣、
雅美、噶瑪蘭），整集拿去比，布農查無詞形暴增，郡群覆蓋率掉到 24%
還被判「高」；單集族語（太魯閣 123）不可以因為不做 b、c 就連 a 項
都跳過。
"""
import csv
import os
import tempfile
import unittest
from unittest import mock

from scripts.aiyalaeho import paths as store
from scripts.aiyalaeho.cleaning import __main__ as cli
from scripts.aiyalaeho.cleaning import paths
from tests.aiyalaeho.cleaning import fixtures

A1 = "開會了_001_Amis_阿美"
A3 = "開會了_005_Amis_阿美"     # 多族來賓集：無法確定佔一成以上
A2 = "開會了_002_Amis_阿美"
T1 = "開會了_003_Truku_太魯閣"
PENDING = "開會了_004_Amis_阿美"

FOREIGN = "kayzaeh"          # 別族來賓的詞（賽夏），兩邊詞表都沒有
DICT_ONLY = "romadiw"        # 只有辭典（秀姑巒）有
HOST_ONLY = "pakimadaw"      # 只在多族來賓集的「純族語」列出現


def _row(name, tribe, variety="", pending=False):
    return {"srt_name": name, "成果檔名": name, "族語別(中)": tribe,
            "語言別": variety, "pending": pending, "abnormal": False}


def _pure(name, numbers):
    rows = []
    for number in numbers:
        rows.append((name, number, "純族語"))
    return rows


def _write_words(path, words):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for word in sorted(words):
            handle.write(word + "\n")


class ContextCase(unittest.TestCase):
    def setUp(self):
        self.store = fixtures.Store()
        self.store.episode(A1, [
            (10.0, 12.0, "nga'ay ho kako", "你好"),
            (12.0, 14.0, "romadiw kako", "我唱歌"),
        ])
        # A2：11 條裡 1 條別族來賓（9%，不到一成），本族語列照常比對。
        a2 = [(10.0, 12.0, "nga'ay ho kako", "你好"),
              (12.0, 14.0, "%s  saboeh" % FOREIGN, "大家好")]
        for index in range(9):
            start = 14.0 + index * 2
            a2.append((start, start + 2.0, "kako %d" % index, "我 %d" % index))
        self.store.episode(A2, a2)
        # A3：多族來賓集，3 條裡 1 條無法確定。主持人的「純族語」列也
        # 不比（布農 111 這種集，標純族語的列還混著卑南語）。
        self.store.episode(A3, [
            (10.0, 12.0, "%s  kako" % HOST_ONLY, "主持人"),
            (12.0, 14.0, "%s saboeh" % FOREIGN, "來賓"),
            (14.0, 16.0, "nga'ay ho", "你好"),
        ])
        self.store.episode(T1, [
            (10.0, 12.0, "embiyax  su hug", "你好嗎"),
        ])
        marks = os.path.join(self.store.root, "逐條語言標記.csv")
        fixtures.write_marks(marks, [
            (A1, 1, "純族語"), (A1, 2, "純族語"),
            (A2, 1, "純族語"), (A2, 2, "無法確定"),
            (T1, 1, "純族語"),
            (A3, 1, "純族語"), (A3, 2, "無法確定"), (A3, 3, "純族語"),
        ] + _pure(A2, range(3, 12)))
        self.layout = paths.Layout(tempfile.mkdtemp(prefix="aiya-out-"))
        _write_words(os.path.join(self.layout.klokah, "秀姑巒阿美語.txt"),
                     ["nga'ay", "ho", "kako"])
        _write_words(os.path.join(self.layout.klokah, "海岸阿美語.txt"),
                     ["nga'ay", "saboeh"])
        _write_words(os.path.join(self.layout.klokah, "太魯閣語.txt"),
                     ["embiyax", "su", "hug"])
        _write_words(os.path.join(self.layout.kaldi, "阿美.txt"), ["kako"])
        lexicon = os.path.join(self.store.root, "詞庫")
        _write_words(os.path.join(lexicon, "阿美.txt"),
                     ["nga'ay", "kako", DICT_ONLY])
        _write_words(os.path.join(lexicon, "太魯閣.txt"), ["embiyax"])
        pairs = os.path.join(self.store.root, "1-句對.csv")
        with open(pairs, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["族語別(中)", "族語"])
            writer.writerow(["阿美", "nga'ay kako"])
        catalogue = {
            A1: _row(A1, "阿美", "秀姑巒"),
            A2: _row(A2, "阿美"),
            A3: _row(A3, "阿美"),
            T1: _row(T1, "太魯閣"),
            PENDING: _row(PENDING, "阿美", pending=True),
        }
        patches = (
            mock.patch.object(cli, "_catalogue", lambda: catalogue),
            mock.patch.object(cli, "_srt", self.store.srt_path),
            mock.patch.object(store, "LANGCHECK_MARKS", marks),
            mock.patch.object(store, "TEXT_PAIRS", pairs),
            mock.patch.object(store, "lexicon_path",
                              lambda tribe: os.path.join(lexicon,
                                                         tribe + ".txt")),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.context = cli.Context(self.layout)

    def result_of(self, srt_name):
        for name, _language, _labelled, result in self.context.results:
            if name == srt_name:
                return result
        raise AssertionError(srt_name)


class TestScope(ContextCase):
    def test_targets_follow_the_catalogue(self):
        self.assertEqual(self.context.targets, [A1, A2, T1, A3])

    def test_only_languages_with_two_episodes_get_candidates(self):
        # 太魯閣只有 1 集、pending 那集不算，所以只有阿美。
        self.assertEqual(sorted(self.context.builts), ["阿美"])


class TestOwnLanguageOnly(ContextCase):
    def test_guest_words_stay_out_of_candidates_and_corpus(self):
        built = self.context.builts["阿美"]
        self.assertNotIn(FOREIGN, built.words)
        self.assertNotIn(FOREIGN, built.evidence.corpus)

    def test_multi_guest_episode_stays_out_of_candidates_and_corpus(self):
        # 多族來賓集整集不做 b、c：主持人「純族語」列的詞也不進。
        built = self.context.builts["阿美"]
        self.assertNotIn(HOST_ONLY, built.words)
        self.assertNotIn(HOST_ONLY, built.evidence.corpus)
        self.assertEqual(self.context.multi_guest, [A3])

    def test_under_one_in_ten_keeps_own_lines(self):
        # A2 只有 9% 無法確定，本族語列照常進候選（kako 在 A2 出現）。
        built = self.context.builts["阿美"]
        self.assertIn("002", built.evidence.corpus["kako"])

    def test_dialect_inference_ignores_guest_lines(self):
        # 本族語列只有 nga'ay ho kako，全在秀姑巒詞表；別族列算進來的
        # 話覆蓋率會掉到 1 以下。
        self.assertEqual(self.result_of(A2).rates["秀姑巒"], 1.0)

    def test_single_variety_language_is_not_compared(self):
        self.assertEqual(self.result_of(T1).verdict, "單一語別")

    def test_guest_lines_and_single_episode_language_still_get_rule_a(self):
        bodies, changes = cli._clean_all(self.context.targets, [], [])
        self.assertEqual(sorted(bodies), [A1, A2, T1, A3])
        found = set()
        for change in changes:
            found.add((change.srt_name, change.number))
        self.assertIn((A2, 2), found)
        self.assertIn((T1, 1), found)
        self.assertIn((A3, 1), found)


class TestAuthority(ContextCase):
    def test_dictionary_counts_when_its_variety_is_the_episode_variety(self):
        # A1 標秀姑巒＝阿美辭典的語別，權威要含辭典才有的詞。
        built = self.context.builts["阿美"]
        self.assertIn(DICT_ONLY, built.authorities[A1])


if __name__ == "__main__":
    unittest.main()
