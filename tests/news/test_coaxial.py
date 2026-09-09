"""語音側交付愛干焦靠 store 就重建會出來，而且逐 byte 仝款。

本底這爿干焦比時間戳：兩爿ê (index, start, end) 相仝就準過。彼掠會著
「時間軸換版、語音側無綴leh重投影」彼種漂移——47 集就是按呢走精兩個月
無人知——毋過掠袂著別兩種：有人用手改交付檔、抑是程式改矣交付檔無重產。

這馬改做**重建比對**：交付檔家己毋看，倒轉去用 store 內底ê輸入（1-words
＋影像側時間軸；譯文快取；判定快取）閣行一擺仝一條程式，佇記持內底
產出正文，才佮硬碟頂彼份一 byte 一 byte 比。影像側 `rebuild --verify`
本底就是按呢做ê，這是kā仝一條規矩𤆬到語音側。

三種歹法攏掠會著：手改、程式佮產物無同步、輸入換版下游無綴。時間戳
比對干焦掠會著上尾彼種。同軸嘛順紲成立矣——重建過ê族語逝就是對影像
側彼條時間軸投影出來ê。

無做ê階段毋是錯，嘛袂報警告（使用者裁定 2026-09-03）：語音側是家己ê
一條線，做到佗位由 `smkul.csv` 照實反映。毋過**有交付檔而頂手ê輸入
無夠**就是錯——彼表示彼份檔毋是對 store 產出來ê。
"""
import os
import tempfile
import unittest

from scripts.news import coaxial
from scripts.errors import PipelineError

RAW = ("1\n00:00:01,000 --> 00:00:02,000\n族語：a\n華語：甲\n\n"
       "2\n00:00:03,000 --> 00:00:04,000\n族語：b\n華語：乙\n")
SHIFTED = RAW.replace("00:00:03,000", "00:00:03,500")
RETEXTED = RAW.replace("族語：b", "族語：zzz")
SHORTER = "1\n00:00:01,000 --> 00:00:02,000\n族語：a\n華語：甲\n"


class Fixture(unittest.TestCase):
    NAME = "20210101_001_午間_Rukai_魯凱"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def _stage(self, label, text=None, name=None):
        """A stage folder, optionally holding this episode's file."""
        base = os.path.join(self.root, label)
        if text is not None:
            path = os.path.join(base, "2021-01", (name or self.NAME) + ".srt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        return base

    def _stages(self, *specs):
        """[(label, stored, rebuilt)] -> the stage list `problems` takes."""
        out = []
        for label, stored, rebuilt in specs:
            base = self._stage(label, stored)

            def build(name, text=rebuilt):
                if isinstance(text, Exception):
                    raise text
                return text
            out.append((label, base, ".srt", build))
        return out


class TestOneFile(Fixture):
    def test_an_exact_rebuild_is_no_complaint(self):
        stages = self._stages(("2-srt-raw", RAW, RAW))
        self.assertEqual(coaxial.problems([self.NAME], stages), [])

    def test_a_shifted_timestamp_names_the_entry(self):
        stages = self._stages(("2-srt-raw", SHIFTED, RAW))
        got = coaxial.problems([self.NAME], stages)
        self.assertEqual(len(got), 1)
        self.assertIn("條目 2", got[0])
        self.assertIn("2-srt-raw", got[0])
        self.assertIn(self.NAME, got[0])

    def test_changed_text_is_caught_too(self):
        """時間戳比對掠袂著這種：有人kā族語逝改過，抑是程式改矣
        交付檔無重產。逐 byte 比就掠會著。"""
        stages = self._stages(("2-srt-raw", RETEXTED, RAW))
        got = coaxial.problems([self.NAME], stages)
        self.assertEqual(len(got), 1)
        self.assertIn("條目 2", got[0])

    def test_a_different_entry_count_is_reported(self):
        stages = self._stages(("2-srt-raw", SHORTER, RAW))
        got = coaxial.problems([self.NAME], stages)
        self.assertEqual(len(got), 1)
        self.assertIn("條目數", got[0])


class TestStagesNotMadeYet(Fixture):
    def test_a_stage_with_no_file_is_skipped(self):
        stages = self._stages(("2-srt-raw", None, RAW))
        self.assertEqual(coaxial.problems([self.NAME], stages), [])

    def test_half_way_through_is_fine(self):
        """做到 3-srt-ai、猶未做 4-srt-quality——彼是進度，毋是錯。"""
        stages = self._stages(("2-srt-raw", RAW, RAW),
                              ("3-srt-ai", RAW, RAW),
                              ("4-srt-quality", None, RAW))
        self.assertEqual(coaxial.problems([self.NAME], stages), [])

    def test_another_episodes_file_does_not_count(self):
        base = self._stage("2-srt-raw", RAW, name="20210102_002_午間_Amis_阿美")

        def build(name):
            raise AssertionError("this episode has no file to check")
        self.assertEqual(
            coaxial.problems([self.NAME], [("2-srt-raw", base, ".srt",
                                            build)]), [])


class TestUpstreamMissing(Fixture):
    def test_a_file_the_store_cannot_rebuild_is_an_error(self):
        """有交付檔，毋過快取內底無彼條ê譯文／判定——彼份檔毋是對
        store 產出來ê，抑是快取予人剾掉。兩款攏愛講出來。"""
        stages = self._stages(
            ("3-srt-ai", RAW, PipelineError("條目 7：快取內底揣無譯文")))
        got = coaxial.problems([self.NAME], stages)
        self.assertEqual(len(got), 1)
        self.assertIn("條目 7", got[0])
        self.assertIn("3-srt-ai", got[0])


class TestSweep(Fixture):
    def test_it_collects_every_episode_and_stage_that_differs(self):
        good = "20210102_002_午間_Amis_阿美"
        base = self._stage("2-srt-raw", SHIFTED)
        path = os.path.join(base, "2021-01", good + ".srt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(RAW)

        def build(name):
            return RAW
        got = coaxial.problems([self.NAME, good],
                               [("2-srt-raw", base, ".srt", build)])
        self.assertEqual(len(got), 1)
        self.assertIn(self.NAME, got[0])


if __name__ == "__main__":
    unittest.main()


class TestSpeechStagesAreAllListed(unittest.TestCase):
    """語音側三个交付階段攏愛入去逐 byte 重建ê名單。

    本底名單干焦有 2-srt-raw 佮 3-srt-ai，4-srt-quality 無列。
    `rebuild --verify` 就一直講「攏仝款」，其實伊連看都無看彼一
    層——阿美 032晚 彼份判定是舊版 prompt 判ê，材料換過了後根本
    重建袂出來，猶原過關。**無列入名單ê階段毋是「猶未做」，是
    「無人咧顧」。**
    """

    def test_every_speech_stage_has_a_rebuilder(self):
        from scripts.news import rebuild
        listed = []
        for name, _base, _suffix, _build in rebuild.speech_stages():
            listed.append(name)
        self.assertEqual(listed,
                         ["2-srt-raw", "3-srt-ai", "4-srt-quality"])
