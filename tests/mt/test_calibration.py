"""calibration: each tribe's own dictionary baseline, computed once.

The dictionaries cover the tribes very unevenly: over the anchors'
opening 90 s the median hit rate is 卑南 0.17, 魯凱 0.20 but 卡那卡那富
0.67. One shared threshold keeps 7～17% of four tribes. So each tribe is
measured against its own opening -- and the table is frozen, or every
new month would shift the tiers of every old episode.

Rows are keyed by (族語別, 語言別代號): an ordinary row carries the
family code; a variety with its own supplement (萬山 `dru-x-opnh`, whose
anchor scores 0.048 against the 霧台-only dictionary) gets its own row."""
import os
import shutil
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.mt import calibration


FAMILY = {"卑南": "pyu", "卡那卡那富": "xnb", "邵": "ssf", "鄒": "tsu",
          "阿美": "ami", "魯凱": "dru"}


def group(tribe, start, words, rate, code=None):
    return {"tribe": tribe, "code": code or FAMILY[tribe], "start": start,
            "asr_words": words, "lexicon_rate": rate}


class TestBaseline(unittest.TestCase):
    def test_median_of_opening_groups_per_tribe(self):
        groups = [group("卑南", 10.0, 20, 0.1), group("卑南", 40.0, 20, 0.2),
                  group("卑南", 70.0, 20, 0.3),
                  group("卡那卡那富", 20.0, 20, 0.7)]
        table = calibration.baseline(groups)
        self.assertAlmostEqual(table[("卑南", "pyu")]["rate"], 0.2)
        self.assertEqual(table[("卑南", "pyu")]["groups"], 3)
        self.assertAlmostEqual(table[("卡那卡那富", "xnb")]["rate"], 0.7)

    def test_a_supplemented_variety_is_its_own_row(self):
        # 萬山的開場不可混進魯凱那列（那列凍結），也不可被霧台拉低。
        groups = [group("魯凱", 10.0, 20, 0.27), group("魯凱", 20.0, 20, 0.27),
                  group("魯凱", 10.0, 20, 0.36, code="dru-x-opnh")]
        table = calibration.baseline(groups)
        self.assertAlmostEqual(table[("魯凱", "dru")]["rate"], 0.27)
        self.assertEqual(table[("魯凱", "dru")]["groups"], 2)
        self.assertAlmostEqual(table[("魯凱", "dru-x-opnh")]["rate"], 0.36)

    def test_groups_after_ninety_seconds_do_not_count(self):
        # interviews later in the bulletin are where the ASR fails
        groups = [group("邵", 30.0, 20, 0.5), group("邵", 90.0, 20, 0.0),
                  group("邵", 600.0, 20, 0.0)]
        self.assertAlmostEqual(
            calibration.baseline(groups)[("邵", "ssf")]["rate"], 0.5)

    def test_fragments_do_not_count(self):
        # a two-word fragment scores 0 or 1 and means nothing
        groups = [group("鄒", 10.0, 4, 1.0), group("鄒", 20.0, 5, 0.3)]
        self.assertAlmostEqual(
            calibration.baseline(groups)[("鄒", "tsu")]["rate"], 0.3)


class TestTable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="calibration-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "校正基準.csv")

    def test_round_trip_is_byte_stable(self):
        table = {("卑南", "pyu"): {"rate": 0.171428, "groups": 161},
                 ("魯凱", "dru"): {"rate": 0.2667, "groups": 193},
                 ("魯凱", "dru-x-opnh"): {"rate": 0.357, "groups": 215},
                 ("阿美", "ami"): {"rate": 0.5, "groups": 170}}
        calibration.write(table, self.path)
        first = open(self.path, "rb").read()
        calibration.write(calibration.read(self.path), self.path)
        self.assertEqual(open(self.path, "rb").read(), first)
        self.assertTrue(first.startswith(
            "族語別,語言別代號,開場組數,辭典命中率中位數\n".encode("utf-8")))
        self.assertNotIn(b"\r", first)
        self.assertIn("魯凱,dru,193,0.2667\n魯凱,dru-x-opnh,215,0.3570\n"
                      .encode("utf-8"), first)

    def test_rate_read_back_is_the_stored_rounding(self):
        calibration.write({("卑南", "pyu"): {"rate": 0.171428, "groups": 1}},
                          self.path)
        self.assertEqual(
            calibration.read(self.path)[("卑南", "pyu")]["rate"], 0.1714)

    def test_an_old_table_without_the_code_column_is_refused(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("族語別,開場組數,辭典命中率中位數\n卑南,136,0.1727\n")
        with self.assertRaises(PipelineError) as caught:
            calibration.read(self.path)
        self.assertIn("語言別代號", str(caught.exception))
        self.assertIn(self.path, str(caught.exception))

    def test_missing_table_is_refused(self):
        with self.assertRaises(PipelineError):
            calibration.read(os.path.join(self.tmp, "nope.csv"))


class TestRateOf(unittest.TestCase):
    TABLE = {("魯凱", "dru"): {"rate": 0.2667, "groups": 193},
             ("魯凱", "dru-x-opnh"): {"rate": 0.357, "groups": 215},
             ("阿美", "ami"): {"rate": 0.5018, "groups": 132}}

    def test_a_variety_with_its_own_row_uses_it(self):
        self.assertEqual(calibration.rate_of(
            self.TABLE, "魯凱", "dru-x-opnh", "20210618_169_午間_Rukai_魯凱"),
            0.357)

    def test_a_variety_without_its_own_row_uses_the_family_row(self):
        # 霧台、海岸阿美照舊用族語別那列；查不到語言別不可中止。
        self.assertEqual(calibration.rate_of(
            self.TABLE, "魯凱", "dru-x-ngdr", "x"), 0.2667)
        self.assertEqual(calibration.rate_of(
            self.TABLE, "阿美", "ami-x-pswl", "x"), 0.5018)
        self.assertEqual(calibration.rate_of(self.TABLE, "魯凱", "dru", "x"),
                         0.2667)

    def test_missing_tribe_is_refused_by_name_not_defaulted(self):
        with self.assertRaises(PipelineError) as caught:
            calibration.rate_of(self.TABLE, "邵", "ssf",
                                "20210227_058_晨間_Thau_邵")
        self.assertIn("邵", str(caught.exception))
        self.assertIn("20210227_058", str(caught.exception))


class TestFillMissing(unittest.TestCase):
    def test_existing_rows_are_kept_and_only_gaps_are_added(self):
        # 全量重算魯凱會從 0.2667 變 0.44（2026-11-16 量），已交付 657 集
        # 的分層全變；補算只能加缺的列。
        old = {("魯凱", "dru"): {"rate": 0.2667, "groups": 193}}
        new = {("魯凱", "dru"): {"rate": 0.44, "groups": 900},
               ("魯凱", "dru-x-opnh"): {"rate": 0.357, "groups": 215}}
        merged = calibration.fill_missing(old, new)
        self.assertEqual(merged[("魯凱", "dru")],
                         {"rate": 0.2667, "groups": 193})
        self.assertEqual(merged[("魯凱", "dru-x-opnh")],
                         {"rate": 0.357, "groups": 215})

    def test_no_old_table_takes_everything(self):
        new = {("魯凱", "dru"): {"rate": 0.44, "groups": 900}}
        self.assertEqual(calibration.fill_missing({}, new), new)


if __name__ == "__main__":
    unittest.main()
