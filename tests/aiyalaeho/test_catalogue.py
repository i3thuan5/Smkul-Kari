"""catalogue: the file name is the episode, and what it says about it.

This is the one place in the corpus that can be silently wrong -- a file
named as the wrong language would be delivered under the wrong key and
nothing downstream would notice -- so every rule is exercised on the
actual names the folder holds, and on the ones it refuses.
"""
import json
import os
import tempfile
import unittest

from scripts.aiyalaeho import catalogue
from scripts.aiyalaeho import paths
from scripts.errors import PipelineError


def parse(name):
    entry, problem = catalogue.parse(name)
    if problem:
        raise AssertionError("%s: %s" % (name, problem))
    return entry


class TestParseStandardNames(unittest.TestCase):
    def test_a_plain_name(self):
        got = parse("082-阿美語-雙語字幕.mp4")
        self.assertEqual(got["集數"], "82")
        self.assertEqual(got["族語別(英)"], "Amis")
        self.assertEqual(got["族語別(中)"], "阿美")
        self.assertEqual(got["語言別"], "")
        self.assertEqual(got["語言代號"], "ami")
        self.assertEqual(got["srt_name"], "開會了_082_Amis_阿美")

    def test_a_two_digit_episode_is_padded(self):
        # 檔名寫 88，鍵愛零補做 088，SRT 才照集數排。
        got = parse("88-泰雅語-無字幕.mp4")
        self.assertEqual(got["srt_name"], "開會了_088_Atayal_泰雅")

    def test_the_video_path_is_corpus_root_relative(self):
        got = parse("082-阿美語-雙語字幕.mp4")
        self.assertEqual(got["video"],
                         "ilrdf-corpus/族語節目/開會了/082-阿美語-雙語字幕.mp4")
        self.assertEqual(got["file"], "082-阿美語-雙語字幕.mp4")

    def test_the_programme_name_is_recorded(self):
        self.assertEqual(parse("082-阿美語-雙語字幕.mp4")["節目名稱"], "開會了")

    def test_registered_entries_start_pending(self):
        self.assertTrue(parse("082-阿美語-雙語字幕.mp4")["pending"])


class TestParseVarieties(unittest.TestCase):
    def test_a_variety_becomes_a_private_tag(self):
        got = parse("068-阿美語-秀姑巒-雙語字幕.mp4")
        self.assertEqual(got["語言別"], "秀姑巒")
        self.assertEqual(got["語言代號"], "ami-x-skl")
        self.assertEqual(got["srt_name"], "開會了_068_Amis_阿美")

    def test_every_variety_the_folder_names(self):
        want = {
            "112-阿美語-南勢-雙語字幕.mp4": ("南勢", "ami-x-iams"),
            "91-泰雅語-賽考利克-雙語字幕.mp4": ("賽考利克", "tay-x-sql"),
            "95-魯凱語-霧台-雙語字幕.mp4": ("霧台", "dru-x-ngdr"),
        }
        for name in sorted(want):
            got = parse(name)
            self.assertEqual((got["語言別"], got["語言代號"]), want[name],
                             name)

    def test_deluku_is_a_seediq_variety_not_truku(self):
        # 德路固＝規範ê「德鹿谷賽德克語」；佮太魯閣語（trv-x-truku）
        # 仝一个 ISO 碼，毋過是無仝ê語言別，袂使濫。
        got = parse("102-賽德克語-德路固-雙語字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Seediq")
        self.assertEqual(got["語言代號"], "trv-x-trk")

    def test_truku_is_its_own_language(self):
        got = parse("123-太魯閣語-雙語字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Truku")
        self.assertEqual(got["語言代號"], "trv-x-truku")

    def test_a_variety_may_stand_in_for_the_language(self):
        # 98 ê檔名干焦寫「東魯凱」，無寫「魯凱語」。
        got = parse("98-東魯凱-無字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Rukai")
        self.assertEqual(got["族語別(中)"], "魯凱")
        self.assertEqual(got["語言別"], "東魯凱")
        self.assertEqual(got["語言代號"], "dru-x-trmk")

    def test_a_variety_the_standard_does_not_list_keeps_the_base_code(self):
        # 「非霧台」毋是規範頂懸ê語言別名稱：字樣照錄，代號退族語級。
        got = parse("083-魯凱語-非霧台-僅華語字幕.mp4")
        self.assertEqual(got["語言別"], "非霧台")
        self.assertEqual(got["語言代號"], "dru")


class TestParseNoise(unittest.TestCase):
    # 解析出來ê欄（集數、族語別、語言別、語言代號、srt_name）愛清氣；
    # `file` 佮 `video` 是檔名本身，原樣記，毋佇這條ê範圍內。
    PARSED = ("集數", "族語別(英)", "族語別(中)", "語言別", "語言代號",
              "srt_name")

    def _parsed_values(self, entry):
        out = []
        for field in self.PARSED:
            out.append(str(entry[field]))
        return out

    def test_a_parenthetical_note_stays_out_of_every_field(self):
        got = parse("108-排灣語-雙語字幕（講中文居多）.mp4")
        self.assertEqual(got["族語別(英)"], "Paiwan")
        self.assertEqual(got["語言別"], "")
        self.assertEqual(got["語言代號"], "pwn")
        for value in self._parsed_values(got):
            self.assertNotIn("講中文", value)

    def test_a_bracket_inside_the_language_name(self):
        got = parse("100-雅美(達悟)語-雙語字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Yami")
        self.assertEqual(got["族語別(中)"], "雅美")
        self.assertEqual(got["語言別"], "")

    def test_the_subtitle_status_never_enters_a_field(self):
        for name in ("88-泰雅語-無字幕.mp4", "083-魯凱語-非霧台-僅華語字幕.mp4",
                     "082-阿美語-雙語字幕.mp4"):
            got = parse(name)
            for value in self._parsed_values(got):
                self.assertNotIn("字幕", value, name)

    def test_the_whole_folder_parses(self):
        # 本機彼份是伺服器彼夾ê複本，逐支攏愛解析會開。
        if not os.path.isdir(paths.SOURCE):
            self.skipTest("no local copy of the source folder")
        for name in sorted(os.listdir(paths.SOURCE)):
            if not name.lower().endswith(".mp4"):
                continue
            entry, problem = catalogue.parse(name)
            self.assertEqual(problem, "", name)
            paths.check_srt_name(entry["srt_name"])


class TestParseRefusals(unittest.TestCase):
    def test_a_name_with_no_language_is_reported_not_guessed(self):
        # 119-混雜.mp4／122-混雜.mp4：檔名無族語別，人看過才會當命名。
        entry, problem = catalogue.parse("119-混雜.mp4")
        self.assertIsNone(entry)
        self.assertIn("族語別", problem)

    def test_an_old_upload_name_is_reported(self):
        entry, problem = catalogue.parse("116ALL_無字.mp4")
        self.assertIsNone(entry)
        self.assertTrue(problem)

    def test_a_name_with_no_episode_number_is_reported(self):
        entry, problem = catalogue.parse("開會了-阿美語-雙語字幕.mp4")
        self.assertIsNone(entry)
        self.assertIn("集數", problem)

    def test_an_unnameable_file_does_not_stop_the_others(self):
        # 一支歹名袂使kā其他四十外集擋牢；報出來予人判就好。
        names = ["082-阿美語-雙語字幕.mp4", "119-混雜.mp4",
                 "085-泰雅語-雙語字幕.mp4"]
        entries, skipped = catalogue.resolve(names)
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0][0], "119-混雜.mp4")

    def test_a_person_can_name_a_refused_file(self):
        # 人看過影片了後，用 --language 指定族語別補做該集。
        entry, problem = catalogue.parse("119-混雜.mp4", language="布農")
        self.assertEqual(problem, "")
        self.assertEqual(entry["srt_name"], "開會了_119_Bunun_布農")
        self.assertEqual(entry["語言代號"], "bnn")

    def test_an_unknown_language_override_is_refused(self):
        self.assertRaises(PipelineError, catalogue.parse,
                          "119-混雜.mp4", language="火星")


class TestRegister(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-inv-")
        self.inventory = os.path.join(self.tmp, "inventory.json")
        with open(self.inventory, "w", encoding="utf-8") as handle:
            json.dump([], handle)

    def _load(self):
        return paths.load_inventory(self.inventory)

    def _raw(self):
        with open(self.inventory, encoding="utf-8") as handle:
            return json.load(handle)

    def _register(self, names):
        entries, skipped = catalogue.resolve(names)
        merged, added = catalogue.merge(entries, self._load())
        catalogue.write(merged, self.inventory)
        return added, skipped

    def test_registration_writes_pending_entries(self):
        added, _ = self._register(["082-阿美語-雙語字幕.mp4",
                                   "085-泰雅語-雙語字幕.mp4"])
        self.assertEqual(len(added), 2)
        for entry in self._load():
            self.assertTrue(entry["pending"])

    def test_re_running_adds_nothing_and_changes_nothing(self):
        self._register(["082-阿美語-雙語字幕.mp4"])
        before = self._raw()
        added, _ = self._register(["082-阿美語-雙語字幕.mp4",
                                   "085-泰雅語-雙語字幕.mp4"])
        self.assertEqual(len(added), 1)
        after = self._raw()
        self.assertEqual(after[0], before[0])

    def test_registering_one_episode_at_a_time_is_allowed(self):
        # 試做一集ê時就是按呢：干焦登記彼一集。
        added, _ = self._register(["068-阿美語-秀姑巒-雙語字幕.mp4"])
        self.assertEqual(len(self._load()), 1)
        self.assertEqual(added[0]["srt_name"], "開會了_068_Amis_阿美")

    def test_an_episode_the_catalogue_never_listed_registers_anyway(self):
        # `ilrdf-corpus.csv` 無 068 佮 164 這兩列，照常登記。
        added, _ = self._register(["068-阿美語-秀姑巒-雙語字幕.mp4",
                                   "164-布農語-雙語字幕.mp4"])
        self.assertEqual(len(added), 2)

    def test_the_written_entries_load_back(self):
        self._register(["083-魯凱語-非霧台-僅華語字幕.mp4"])
        got = self._load()
        self.assertEqual(got[0]["語言別"], "非霧台")


if __name__ == "__main__":
    unittest.main()
