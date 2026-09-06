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

    # 三支較早期ê上傳，檔名內底無族語別。`parse` 拒絕臆測是著ê行為，
    # 所以規夾解析ê時 in 會回報問題，毋是解析會開。2026-09-06 三支
    # 落地了後，原本彼句「逐支攏愛解析會開」就予現實反證去矣。
    NAMELESS = ("116ALL_無字.mp4", "119-混雜.mp4", "122-混雜.mp4")

    def test_the_whole_folder_parses(self):
        # 本機彼份是伺服器彼夾ê複本。除了頂懸彼三支以外，逐支攏愛
        # 解析會開——新出現ê歹名猶原愛予這條紅。
        if not os.path.isdir(paths.SOURCE):
            self.skipTest("no local copy of the source folder")
        refused = []
        for name in sorted(os.listdir(paths.SOURCE)):
            if not name.lower().endswith(".mp4"):
                continue
            entry, problem = catalogue.parse(name)
            if problem:
                refused.append(name)
                continue
            paths.check_srt_name(entry["srt_name"])
        self.assertEqual(sorted(refused), sorted(
            name for name in self.NAMELESS
            if os.path.isfile(os.path.join(paths.SOURCE, name))))

    def test_the_nameless_three_parse_once_a_language_is_given(self):
        # 有人講出族語別了後，仝彼三个名就愛解析會開。
        for name in self.NAMELESS:
            entry, problem = catalogue.parse(name, language="布農")
            self.assertEqual(problem, "", name)
            self.assertEqual(entry["族語別(英)"], "Bunun", name)
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


class TestParseReason(unittest.TestCase):
    """檔名ê字幕狀態字樣 → `理由` 欄。非空就是行袂過雙語流程ê集。"""

    def test_no_subtitles_at_all(self):
        self.assertEqual(parse("88-泰雅語-無字幕.mp4")["理由"], "無字幕")

    def test_chinese_only(self):
        got = parse("083-魯凱語-非霧台-僅華語字幕.mp4")
        self.assertEqual(got["理由"], "僅華語字幕")

    def test_bilingual_carries_no_reason_field_at_all(self):
        # 「無資料ê欄莫養」：雙語集是 38 集，逐集园一个空欄無意思，
        # 嘛會予人看做「理由袂記得填」。無彼隻鍵就是正常。
        self.assertNotIn("理由", parse("082-阿美語-雙語字幕.mp4"))

    def test_a_parenthetical_note_is_not_a_reason(self):
        # 括號內底講ê是受訪者講啥話，毋是字幕按怎排。這兩集是雙語集。
        for name in ("108-排灣語-雙語字幕（講中文居多）.mp4",
                     "111-阿美語-雙語字幕（很多人講中文）.mp4"):
            self.assertNotIn("理由", parse(name), name)

    def test_the_short_form_on_the_server_counts(self):
        # `116ALL_無字.mp4` 是較早期上傳ê，字樣是「無字」毋是「無字幕」。
        # 伊名內無族語別，愛人指定才登記會起來；伊猶未落載，所以量長度
        # 彼步用假ê。
        got = catalogue.parse("116ALL_無字.mp4", language="布農",
                              probe=lambda _path: 2900.0)[0]
        self.assertEqual(got["理由"], "無字幕")

    def test_a_reason_never_lands_in_another_field(self):
        got = parse("88-泰雅語-無字幕.mp4")
        self.assertEqual(got["語言別"], "")
        self.assertEqual(got["族語別(中)"], "泰雅")

    def test_every_local_file_gets_a_verdict(self):
        # 規夾ê檔逐支攏愛判會出來——理由空ê是雙語集，非空ê是異常集。
        if not os.path.isdir(paths.SOURCE):
            self.skipTest("no local copy of the source folder")
        reasons = {}
        for name in sorted(os.listdir(paths.SOURCE)):
            if not name.lower().endswith(".mp4"):
                continue
            entry, problem = catalogue.parse(
                name, probe=lambda _path: 2900.0)
            if problem:
                continue
            reasons[entry["集數"]] = entry.get("理由", "")
        abnormal = []
        for episode in sorted(reasons):
            if reasons[episode]:
                abnormal.append(episode)
        self.assertEqual(abnormal, ["83", "88", "90", "98"])


class TestParseDuration(unittest.TestCase):
    """異常集登記ê時就量長度——in 佇 `1-cues/` 無時間軸通推。"""

    def test_an_abnormal_episode_is_probed(self):
        seen = []

        def probe(path):
            seen.append(path)
            return 2969.967

        got = catalogue.parse("88-泰雅語-無字幕.mp4", probe=probe)[0]
        self.assertEqual(got["影片長度秒"], 2969.967)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].endswith("88-泰雅語-無字幕.mp4"))

    def test_a_bilingual_episode_is_not_probed(self):
        # 雙語集ê長度是對 `1-cues/` 時間軸推ê，這位莫開影片。
        def probe(path):
            raise AssertionError("袂使量雙語集：%s" % path)

        got = catalogue.parse("082-阿美語-雙語字幕.mp4", probe=probe)[0]
        self.assertNotIn("影片長度秒", got)


class TestAnnotate(unittest.TestCase):
    """既有條目補這兩欄——`merge()` 袂振動舊條目，所以愛另外一條路。"""

    def _entry(self, **over):
        entry = {
            "file": "88-泰雅語-無字幕.mp4",
            "video": "ilrdf-corpus/族語節目/開會了/88-泰雅語-無字幕.mp4",
            "srt_name": "開會了_088_Atayal_泰雅",
            "節目名稱": "開會了",
            "集數": "88",
            "族語別(英)": "Atayal",
            "族語別(中)": "泰雅",
            "語言別": "",
            "語言代號": "tay",
            "pending": True,
        }
        entry.update(over)
        return entry

    def _probe(self, seconds=2969.967):
        def probe(_path):
            return seconds
        return probe

    def test_it_fills_the_reason_from_the_file_name(self):
        entries = [self._entry()]
        changed = catalogue.annotate(entries, probe=self._probe())
        self.assertEqual(entries[0]["理由"], "無字幕")
        self.assertTrue(changed)

    def test_it_fills_the_duration_for_abnormal_entries(self):
        entries = [self._entry()]
        catalogue.annotate(entries, probe=self._probe())
        self.assertEqual(entries[0]["影片長度秒"], 2969.967)

    def test_a_bilingual_entry_keeps_no_reason_field(self):
        entries = [self._entry(file="082-阿美語-雙語字幕.mp4",
                               srt_name="開會了_082_Amis_阿美")]
        catalogue.annotate(entries, probe=self._probe())
        self.assertNotIn("理由", entries[0])
        self.assertNotIn("影片長度秒", entries[0])

    def test_it_leaves_a_bilingual_entry_alone(self):
        entries = [self._entry(file="082-阿美語-雙語字幕.mp4",
                               srt_name="開會了_082_Amis_阿美")]
        before = dict(entries[0])
        changed = catalogue.annotate(entries, probe=self._probe())
        self.assertEqual(entries[0], before)
        self.assertEqual(changed, [])

    def test_it_touches_no_other_field(self):
        entries = [self._entry()]
        before = dict(entries[0])
        catalogue.annotate(entries, probe=self._probe())
        for field in before:
            self.assertEqual(entries[0][field], before[field], field)

    def test_nothing_to_do_reports_nothing(self):
        entries = [self._entry(理由="無字幕", 影片長度秒=2969.967)]
        self.assertEqual(catalogue.annotate(entries, probe=self._probe()), [])

    def test_a_named_reason_is_written(self):
        entries = [self._entry(file="106-排灣語-雙語字幕.mp4",
                               srt_name="開會了_106_Paiwan_排灣")]
        reason = "版型不符：字幕逝 y=1005..1014 無囥佇任何一个宣告ê槽內"
        catalogue.annotate(entries, named=("開會了_106_Paiwan_排灣", reason),
                           probe=self._probe())
        self.assertEqual(entries[0]["理由"], reason)
        self.assertEqual(entries[0]["影片長度秒"], 2969.967)

    def test_a_named_reason_may_not_be_empty(self):
        entries = [self._entry()]
        self.assertRaises(PipelineError, catalogue.annotate, entries,
                          named=("開會了_088_Atayal_泰雅", ""))

    def test_a_named_reason_does_not_overwrite_one_that_is_there(self):
        entries = [self._entry(理由="無字幕")]
        catalogue.annotate(entries, named=("開會了_088_Atayal_泰雅",
                                           "人工判定：帶色無對"),
                           probe=self._probe())
        self.assertEqual(entries[0]["理由"], "無字幕")

    def test_a_named_episode_that_is_not_registered_is_refused(self):
        entries = [self._entry()]
        self.assertRaises(PipelineError, catalogue.annotate, entries,
                          named=("開會了_999_Amis_阿美", "無字幕"))

    def test_it_says_what_it_changed(self):
        entries = [self._entry()]
        changed = catalogue.annotate(entries, probe=self._probe())
        names = []
        for name, _field, _value in changed:
            names.append(name)
        self.assertEqual(names.count("開會了_088_Atayal_泰雅"), 2)


class TestAnnotateCli(unittest.TestCase):
    """`--annotate` ê兩款用法，佮伊拒收啥。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-ann-")
        self.inventory = os.path.join(self.tmp, "inventory.json")
        entry = {
            "file": "88-泰雅語-無字幕.mp4",
            "video": "ilrdf-corpus/族語節目/開會了/88-泰雅語-無字幕.mp4",
            "srt_name": "開會了_088_Atayal_泰雅",
            "節目名稱": "開會了",
            "集數": "88",
            "族語別(英)": "Atayal",
            "族語別(中)": "泰雅",
            "語言別": "",
            "語言代號": "tay",
            "pending": True,
        }
        with open(self.inventory, "w", encoding="utf-8") as handle:
            json.dump([entry], handle, ensure_ascii=False)
        self._patch(paths, "INVENTORY", self.inventory)
        self._patch(catalogue, "_probe_duration", lambda _p: 2969.967)

    def _patch(self, module, name, value):
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)

    def _load(self):
        return paths.load_inventory(self.inventory)

    def test_no_argument_fills_from_the_file_names(self):
        self.assertEqual(catalogue.main(["--annotate"]), 0)
        got = self._load()[0]
        self.assertEqual(got["理由"], "無字幕")
        self.assertEqual(got["影片長度秒"], 2969.967)

    def test_a_named_reason_is_written(self):
        catalogue.main(["--annotate",
                        "開會了_088_Atayal_泰雅=人工判定：帶色無對"])
        self.assertEqual(self._load()[0]["理由"], "人工判定：帶色無對")

    def test_a_dry_run_writes_nothing(self):
        catalogue.main(["--annotate", "-n"])
        self.assertNotIn("理由", self._load()[0])

    def test_a_named_argument_without_an_equals_sign_is_refused(self):
        self.assertRaises(PipelineError, catalogue.main,
                          ["--annotate", "開會了_088_Atayal_泰雅"])

    def test_a_bad_name_is_refused(self):
        self.assertRaises(PipelineError, catalogue.main,
                          ["--annotate", "../x=無字幕"])

    def test_running_it_twice_changes_nothing_the_second_time(self):
        catalogue.main(["--annotate"])
        with open(self.inventory, "rb") as handle:
            first = handle.read()
        catalogue.main(["--annotate"])
        with open(self.inventory, "rb") as handle:
            self.assertEqual(handle.read(), first)


if __name__ == "__main__":
    unittest.main()
