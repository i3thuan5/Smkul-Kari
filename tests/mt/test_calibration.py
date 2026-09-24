"""calibration: each tribe's own dictionary baseline, computed once.

The dictionaries cover the tribes very unevenly: over the anchors'
opening 90 s the median hit rate is 卑南 0.17, 魯凱 0.20 but 卡那卡那富
0.67. One shared threshold keeps 7～17% of four tribes. So each tribe is
measured against its own opening -- and the table is frozen, or every
new month would shift the tiers of every old episode."""
import os
import shutil
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.mt import calibration


def group(tribe, start, words, rate):
    return {"tribe": tribe, "start": start, "asr_words": words,
            "lexicon_rate": rate}


class TestBaseline(unittest.TestCase):
    def test_median_of_opening_groups_per_tribe(self):
        groups = [group("卑南", 10.0, 20, 0.1), group("卑南", 40.0, 20, 0.2),
                  group("卑南", 70.0, 20, 0.3),
                  group("卡那卡那富", 20.0, 20, 0.7)]
        table = calibration.baseline(groups)
        self.assertAlmostEqual(table["卑南"]["rate"], 0.2)
        self.assertEqual(table["卑南"]["groups"], 3)
        self.assertAlmostEqual(table["卡那卡那富"]["rate"], 0.7)

    def test_groups_after_ninety_seconds_do_not_count(self):
        # interviews later in the bulletin are where the ASR fails
        groups = [group("邵", 30.0, 20, 0.5), group("邵", 90.0, 20, 0.0),
                  group("邵", 600.0, 20, 0.0)]
        self.assertAlmostEqual(calibration.baseline(groups)["邵"]["rate"],
                               0.5)

    def test_fragments_do_not_count(self):
        # a two-word fragment scores 0 or 1 and means nothing
        groups = [group("鄒", 10.0, 4, 1.0), group("鄒", 20.0, 5, 0.3)]
        self.assertAlmostEqual(calibration.baseline(groups)["鄒"]["rate"],
                               0.3)


class TestTable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="calibration-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "校正基準.csv")

    def test_round_trip_is_byte_stable(self):
        table = {"卑南": {"rate": 0.171428, "groups": 161},
                 "阿美": {"rate": 0.5, "groups": 170}}
        calibration.write(table, self.path)
        first = open(self.path, "rb").read()
        calibration.write(calibration.read(self.path), self.path)
        self.assertEqual(open(self.path, "rb").read(), first)
        self.assertTrue(first.startswith("族語別,".encode("utf-8")))
        self.assertNotIn(b"\r", first)

    def test_rate_read_back_is_the_stored_rounding(self):
        calibration.write({"卑南": {"rate": 0.171428, "groups": 1}},
                          self.path)
        self.assertEqual(calibration.read(self.path)["卑南"]["rate"],
                         0.1714)

    def test_missing_tribe_is_refused_by_name_not_defaulted(self):
        table = {"阿美": {"rate": 0.5, "groups": 170}}
        with self.assertRaises(PipelineError) as caught:
            calibration.rate_of(table, "邵", "20210227_058_晨間_Thau_邵")
        self.assertIn("邵", str(caught.exception))
        self.assertIn("20210227_058", str(caught.exception))

    def test_missing_table_is_refused(self):
        with self.assertRaises(PipelineError):
            calibration.read(os.path.join(self.tmp, "nope.csv"))


if __name__ == "__main__":
    unittest.main()
