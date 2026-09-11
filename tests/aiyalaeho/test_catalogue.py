"""catalogue: the file name is the episode, and what it says about it.

This is the one place in the corpus that can be silently wrong -- a file
named as the wrong language would be delivered under the wrong key and
nothing downstream would notice -- so every rule is exercised on the
actual names the folder holds, and on the ones it refuses.
"""
import os
import tempfile
import unittest

from scripts.aiyalaeho import catalogue
from scripts.aiyalaeho import episodes
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
        self.assertEqual(got["語言別代號"], "ami")
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

    def test_no_pending_flag_is_written(self):
        """「做到佗一步」問階段目錄，毋是問一隻旗標。"""
        self.assertNotIn("pending", parse("082-阿美語-雙語字幕.mp4"))


class TestParseVarieties(unittest.TestCase):
    def test_a_variety_becomes_a_private_tag(self):
        got = parse("068-阿美語-秀姑巒-雙語字幕.mp4")
        self.assertEqual(got["語言別"], "秀姑巒")
        self.assertEqual(got["語言別代號"], "ami-x-skl")
        self.assertEqual(got["srt_name"], "開會了_068_Amis_阿美")

    def test_every_variety_the_folder_names(self):
        want = {
            "112-阿美語-南勢-雙語字幕.mp4": ("南勢", "ami-x-iams"),
            "91-泰雅語-賽考利克-雙語字幕.mp4": ("賽考利克", "tay-x-sql"),
            "95-魯凱語-霧台-雙語字幕.mp4": ("霧台", "dru-x-ngdr"),
        }
        for name in sorted(want):
            got = parse(name)
            self.assertEqual((got["語言別"], got["語言別代號"]), want[name],
                             name)

    def test_deluku_is_a_seediq_variety_not_truku(self):
        # 德路固＝規範ê「德鹿谷賽德克語」；佮太魯閣語（trv-x-truku）
        # 仝一个 ISO 碼，毋過是無仝ê語言別，袂使濫。
        got = parse("102-賽德克語-德路固-雙語字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Seediq")
        self.assertEqual(got["語言別代號"], "trv-x-trk")

    def test_truku_is_its_own_language(self):
        got = parse("123-太魯閣語-雙語字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Truku")
        self.assertEqual(got["語言別代號"], "trv-x-truku")

    def test_a_variety_may_stand_in_for_the_language(self):
        # 98 ê檔名干焦寫「東魯凱」，無寫「魯凱語」。
        got = parse("98-東魯凱-無字幕.mp4")
        self.assertEqual(got["族語別(英)"], "Rukai")
        self.assertEqual(got["族語別(中)"], "魯凱")
        self.assertEqual(got["語言別"], "東魯凱")
        self.assertEqual(got["語言別代號"], "dru-x-trmk")

    def test_a_variety_the_standard_does_not_list_keeps_the_base_code(self):
        # 「非霧台」毋是規範頂懸ê語言別名稱：字樣照錄，代號退族語級。
        got = parse("083-魯凱語-非霧台-僅華語字幕.mp4")
        self.assertEqual(got["語言別"], "非霧台")
        self.assertEqual(got["語言別代號"], "dru")


class TestParseNoise(unittest.TestCase):
    # 解析出來ê欄（集數、族語別、語言別、語言代號、srt_name）愛清氣；
    # `file` 佮 `video` 是檔名本身，原樣記，毋佇這條ê範圍內。
    PARSED = ("集數", "族語別(英)", "族語別(中)", "語言別", "語言別代號",
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
        self.assertEqual(got["語言別代號"], "pwn")
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


class TestUnknownLanguage(unittest.TestCase):
    """116 無語言卡嘛無字幕，族語別記做「（未知）」。使用者裁定 2026-09-08。

    伊佮 088／090／098 仝款是「無字幕」ê異常集，差ê是彼幾支ê檔名有
    族語別、伊無。人聽過才有法度命名，毋過等袂得——所以先用「（未知）」
    登記入去，按呢 44 支影片ê帳才做會平（無登記ê話 inventory 少一筆）。
    """

    def test_the_unknown_language_is_accepted(self):
        got, problem = catalogue.parse("116ALL_無字.mp4", language="（未知）")
        self.assertEqual(problem, "")
        self.assertEqual(got["族語別(中)"], "（未知）")
        self.assertEqual(got["族語別(英)"], "Unknown")
        self.assertEqual(got["集數"], "116")

    def test_its_code_is_the_standard_undetermined_one(self):
        # `und` 是 ISO 639-2／639-3 家己對「未確定」ê答案，毋是咱掰ê。
        got, _ = catalogue.parse("116ALL_無字.mp4", language="（未知）")
        self.assertEqual(got["語言別代號"], "und")

    def test_its_srt_name_is_a_valid_key(self):
        got, _ = catalogue.parse("116ALL_無字.mp4", language="（未知）")
        paths.check_srt_name(got["srt_name"])
        self.assertTrue(got["srt_name"].startswith("開會了_116_"))

    def test_the_file_name_still_supplies_the_reason(self):
        # 檔名ê `無字` token 照常變做理由，佮語言是毋是知影無關係。
        self.assertEqual(catalogue.subtitle_state(["無字"]), "無字幕")


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
        self.assertEqual(entry["語言別代號"], "bnn")

    def test_an_unknown_language_override_is_refused(self):
        self.assertRaises(PipelineError, catalogue.parse,
                          "119-混雜.mp4", language="火星")


class TestRegister(unittest.TestCase):
    """登記這馬就是「照來源資料夾ê影片檔清單重寫兩張節目目錄表」。

    `inventory.json` 提掉矣——彼份檔ê逐一欄對兩張表推導會出來，驗過
    44 筆零處無仝。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-inv-")
        self.table = os.path.join(self.tmp, "smkul.csv")
        self.abnormal = os.path.join(self.tmp, "異常.csv")
        catalogue.write([], self.table, self.abnormal)

    def _load(self):
        return episodes.load(self.table, self.abnormal, srt_dir=set())

    def _raw(self):
        with open(self.table, encoding="utf-8-sig") as handle:
            return handle.read()

    def _register(self, names):
        entries, skipped = catalogue.resolve(names)
        merged, added = catalogue.merge(entries, self._load())
        catalogue.write(merged, self.table, self.abnormal)
        return added, skipped

    def test_registration_writes_the_table(self):
        added, _ = self._register(["082-阿美語-雙語字幕.mp4",
                                   "085-泰雅語-雙語字幕.mp4"])
        self.assertEqual(len(added), 2)
        self.assertEqual(len(self._load()), 2)

    def test_an_abnormal_episode_goes_to_the_second_table(self):
        self._register(["083-魯凱語-非霧台-僅華語字幕.mp4"])
        got = self._load()
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0]["abnormal"])
        self.assertEqual(got[0]["備註"], "僅華語字幕")

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
    """檔名ê字幕狀態字樣 → `備註` 欄。非空就是行袂過雙語流程ê集。"""

    def test_no_subtitles_at_all(self):
        self.assertEqual(parse("88-泰雅語-無字幕.mp4")["備註"], "無字幕")

    def test_chinese_only(self):
        got = parse("083-魯凱語-非霧台-僅華語字幕.mp4")
        self.assertEqual(got["備註"], "僅華語字幕")

    def test_bilingual_carries_an_empty_note(self):
        # 兩張表欄位完全相仝，`備註` 空ê就是正常彼張表ê。
        self.assertEqual(parse("082-阿美語-雙語字幕.mp4")["備註"], "")

    def test_a_parenthetical_note_is_not_a_reason(self):
        # 括號內底講ê是受訪者講啥話，毋是字幕按怎排。這兩集是雙語集。
        for name in ("108-排灣語-雙語字幕（講中文居多）.mp4",
                     "111-阿美語-雙語字幕（很多人講中文）.mp4"):
            self.assertEqual(parse(name)["備註"], "", name)

    def test_the_short_form_on_the_server_counts(self):
        # `116ALL_無字.mp4` 是較早期上傳ê，字樣是「無字」毋是「無字幕」。
        # 伊名內無族語別，愛人指定才登記會起來；伊猶未落載，所以量長度
        # 彼步用假ê。
        got = catalogue.parse("116ALL_無字.mp4", language="布農",
                              probe=lambda _path: 2900.0)[0]
        self.assertEqual(got["備註"], "無字幕")

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
            reasons[entry["集數"]] = entry.get("備註", "")
        abnormal = []
        for episode in sorted(reasons):
            if reasons[episode]:
                abnormal.append(episode)
        self.assertEqual(abnormal, ["83", "88", "90", "98"])


class TestAnnotate(unittest.TestCase):
    """既有條目補 `備註`——`merge()` 袂振動舊條目，所以愛另外一條路。

    本底閣有一欄 `影片長度秒`。長度欄規个提掉矣：伊愛讀過影片抑是
    切完 cue 才算會出來，而節目目錄頭一工就愛涵蓋全部集數。
    """

    def _entry(self, **over):
        entry = {
            "srt_name": "開會了_088_Atayal_泰雅",
            "節目名稱": "開會了",
            "集數": "88",
            "族語別(英)": "Atayal",
            "族語別(中)": "泰雅",
            "語言別": "",
            "語言別代號": "tay",
            "video": "ilrdf-corpus/族語節目/開會了/88-泰雅語-無字幕.mp4",
            "file": "88-泰雅語-無字幕.mp4",
            "備註": "",
        }
        entry.update(over)
        return entry

    def test_a_reason_comes_off_the_file_name(self):
        entries = [self._entry()]
        changed = catalogue.annotate(entries)
        self.assertEqual(changed, [("開會了_088_Atayal_泰雅", "備註",
                                    "無字幕")])
        self.assertEqual(entries[0]["備註"], "無字幕")

    def test_an_existing_reason_is_never_overwritten(self):
        entries = [self._entry(備註="人工判定：字幕印佇帶外")]
        self.assertEqual(catalogue.annotate(entries), [])

    def test_a_named_reason_is_written(self):
        entries = [self._entry()]
        catalogue.annotate(entries, named=("開會了_088_Atayal_泰雅",
                                           "版型不符：字幕逝無佇槽內"))
        self.assertEqual(entries[0]["備註"], "版型不符：字幕逝無佇槽內")

    def test_a_blank_named_reason_is_refused(self):
        with self.assertRaises(PipelineError):
            catalogue.annotate([self._entry()],
                               named=("開會了_088_Atayal_泰雅", "  "))

    def test_an_episode_the_table_does_not_have_is_refused(self):
        with self.assertRaises(PipelineError) as caught:
            catalogue.annotate([self._entry()],
                               named=("開會了_999_Amis_阿美", "無字幕"))
        self.assertIn("開會了_999_Amis_阿美", str(caught.exception))
