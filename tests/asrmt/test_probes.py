"""構造法探針：無真值ê時，按怎知影裁判有咧看物件？

無人讀會曉這幾種族語，所以「高」ê真值提無。毋過**倒爿**ê真值造會
出來：kā裁判講懸ê彼寡條目，故意kā字幕換做別條ê、kā數字改掉、kā後
半句剁掉——按呢做了後伊若閣講懸，就是伊無咧看字幕，抑是無咧比數字。

探針愛干焦改**一項**。改兩項ê話，降級是降佇佗一項頭起先無人知，
彼就無診斷ê價值矣。族語逝佮譯文攏袂使振動——動著就毋知是字幕ê問題
抑是族語ê問題。

編號留原本ê：回覆檔轉來ê時，愛認會出彼條本底是佗一句。
"""
import unittest

from scripts.asrmt import probes


def items(count=6):
    out = []
    for i in range(count):
        out.append({"index": i + 1, "formosan": "f%d" % (i + 1),
                    "subtitle": "第%d條字幕總共花費50萬元來支付" % (i + 1),
                    "translation": "譯%d" % (i + 1),
                    "before": "", "after": ""})
    return out


class TestMispair(unittest.TestCase):
    def test_the_subtitle_becomes_another_entrys(self):
        got = probes.mispair(items())
        subtitles = set()
        for item in items():
            subtitles.add(item["subtitle"])
        for original, probe in zip(items(), got):
            self.assertNotEqual(probe["subtitle"], original["subtitle"])
            self.assertIn(probe["subtitle"], subtitles)

    def test_nothing_else_moves(self):
        for original, probe in zip(items(), probes.mispair(items())):
            self.assertEqual(probe["formosan"], original["formosan"])
            self.assertEqual(probe["translation"], original["translation"])
            self.assertEqual(probe["index"], original["index"])

    def test_one_item_cannot_be_mispaired(self):
        """干焦一條ê時，無別條ê字幕通換——莫造一个假ê探針。"""
        self.assertEqual(probes.mispair(items(1)), [])

    def test_the_original_is_not_touched(self):
        data = items()
        probes.mispair(data)
        self.assertEqual(data[0]["subtitle"], items()[0]["subtitle"])


class TestRenumber(unittest.TestCase):
    def test_the_first_number_changes_and_only_that(self):
        """改頭一个就好，而且干焦改彼一个：探針愛干焦動一項。"""
        data = items(1)
        data[0]["subtitle"] = "每年編列50萬元經費"
        probe = probes.renumber(data)[0]
        self.assertEqual(probe["subtitle"], "每年編列80萬元經費")

    def test_a_subtitle_with_two_numbers_only_loses_the_first(self):
        data = items(1)
        data[0]["subtitle"] = "第1條總共花費50萬元"
        probe = probes.renumber(data)[0]
        self.assertEqual(probe["subtitle"], "第4條總共花費50萬元")

    def test_only_the_subtitle_changes(self):
        original = items()[0]
        probe = probes.renumber(items())[0]
        self.assertEqual(probe["formosan"], original["formosan"])
        self.assertEqual(probe["translation"], original["translation"])

    def test_a_subtitle_with_no_number_is_skipped(self):
        data = items(2)
        data[0]["subtitle"] = "沒有數字的字幕"
        got = probes.renumber(data)
        indexes = []
        for item in got:
            indexes.append(item["index"])
        self.assertEqual(indexes, [2])

    def test_chinese_numerals_count_when_a_unit_follows(self):
        data = items(1)
        data[0]["subtitle"] = "總共有五個部落參加"
        probe = probes.renumber(data)[0]
        self.assertNotEqual(probe["subtitle"], data[0]["subtitle"])
        self.assertIn("個部落參加", probe["subtitle"])

    def test_a_numeral_inside_an_idiom_is_left_alone(self):
        """「一大清早」ê「一」毋是數量，是詞ê一部份。

        改伊做「三大清早」，讀起來干焦是拍毋著字，講ê iáu是仝一件
        代誌——裁判判懸無毋著，是探針家己造毋著。探針愛干焦振動
        **帶事實ê數字**：後壁有單位ê，抑是阿拉伯數字。
        """
        for idiom in ("一大清早陽光普照", "族人一起去採集",
                      "他一直在等待", "看起來一樣好"):
            data = items(1)
            data[0]["subtitle"] = idiom
            self.assertEqual(probes.renumber(data), [], idiom)


class TestTruncate(unittest.TestCase):
    def test_the_subtitle_keeps_only_its_first_half(self):
        original = items()[0]
        probe = probes.truncate(items())[0]
        self.assertTrue(original["subtitle"].startswith(probe["subtitle"]))
        self.assertLess(len(probe["subtitle"]), len(original["subtitle"]))

    def test_a_short_subtitle_is_skipped(self):
        """本底就短ê，剁一半賰無物件，變做另外一款探針矣。"""
        data = items(2)
        data[0]["subtitle"] = "大家好"
        got = probes.truncate(data)
        indexes = []
        for item in got:
            indexes.append(item["index"])
        self.assertEqual(indexes, [2])

    def test_the_formosan_line_is_untouched(self):
        for original, probe in zip(items(), probes.truncate(items())):
            self.assertEqual(probe["formosan"], original["formosan"])


class TestTheSetOfProbes(unittest.TestCase):
    def test_every_probe_is_named_and_callable(self):
        self.assertEqual(sorted(probes.PROBES),
                         ["mispair", "renumber", "truncate"])

    def test_each_one_returns_items_the_batch_writer_accepts(self):
        for name in probes.PROBES:
            for item in probes.PROBES[name](items()):
                for field in ("index", "formosan", "subtitle",
                              "translation", "before", "after"):
                    self.assertIn(field, item, (name, field))


if __name__ == "__main__":
    unittest.main()
