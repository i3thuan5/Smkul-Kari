"""rebuild --verify covers 2-csv-analysis and 3-srt-paragraph.

Both layers come from one pairing, a pure function of the store plus
the dictionaries (and the audio length in 辨識紀錄.csv), so they are
produced again and compared byte for byte. The dictionaries are the
one outside input: missing ones are fetched from the SFTP, and when
even that fails the check stops -- it must never pass by skipping.
"""
import os
import unittest

from scripts.errors import PipelineError
from scripts.news import pairs_run
from scripts.news import paths
from scripts.news import rebuild
from tests.mt.test_run import LEXICONS, Store

AMIS_NAME = "20210201_032_晚間_Amis_阿美"


class TestPairsRebuild(Store):
    def produce(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)

    def load(self):
        return LEXICONS

    def test_untouched_layer_rebuilds_byte_identical(self):
        self.produce()
        self.assertEqual(rebuild.pairs_problems(
            load_lexicons=self.load), [])

    def test_hand_edited_cell_is_named(self):
        self.produce()
        path = self.out(AMIS_NAME)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(",ami,", text)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(",ami,", ",amx,", 1))
        found = rebuild.pairs_problems(load_lexicons=self.load)
        self.assertEqual(len(found), 1)
        self.assertIn(AMIS_NAME, found[0])

    def test_no_layer_yet_needs_no_dictionary(self):
        self.standard()

        def unreachable():
            raise AssertionError("dictionary must not be fetched")
        self.assertEqual(rebuild.pairs_problems(load_lexicons=unreachable),
                         [])

    def test_dictionary_unobtainable_stops_rather_than_passes(self):
        self.produce()

        def sftp_down():
            raise PipelineError("列不出 SFTP 的辭典目錄")
        with self.assertRaises(PipelineError) as caught:
            rebuild.pairs_problems(load_lexicons=sftp_down)
        self.assertIn("辭典", str(caught.exception))

    def edit_srt(self, old, new):
        path = self.srt_out(AMIS_NAME)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(old, text)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new, 1))

    def test_hand_edited_paragraph_srt_is_named_with_its_layer(self):
        self.produce()
        self.edit_srt("族語：o tanosok", "族語：o tanosak")
        found = rebuild.pairs_problems(load_lexicons=self.load)
        self.assertEqual(len(found), 1)
        self.assertIn(AMIS_NAME, found[0])
        self.assertIn("3-srt-paragraph", found[0])

    def test_a_csv_without_its_paragraph_srt_is_named(self):
        # both come from one run; a CSV alone was made by older code
        self.produce()
        os.remove(self.srt_out(AMIS_NAME))
        found = rebuild.pairs_problems(load_lexicons=self.load)
        self.assertEqual(len(found), 1)
        self.assertIn("3-srt-paragraph", found[0])

    def test_no_audio_length_is_named_not_passed(self):
        self.produce()
        del self.lengths[AMIS_NAME]
        self.write_log()
        found = rebuild.pairs_problems(load_lexicons=self.load)
        self.assertEqual(len(found), 1)
        self.assertIn(AMIS_NAME, found[0])
        self.assertIn("音長", found[0])


class TestPairsContainment(Store):
    def test_pairs_without_sapolita_is_named(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        os.remove(paths.stage_path(paths.SAPOLITA_SRT, AMIS_NAME, ".srt"))
        found = rebuild.pairs_containment()
        self.assertEqual(len(found), 1)
        self.assertIn(AMIS_NAME, found[0])
        self.assertIn("1-srt-sapolita", found[0])

    def test_pairs_without_delivered_srt_is_named(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        os.remove(paths.stage_path(paths.SRT_DIR, AMIS_NAME, ".srt"))
        found = rebuild.pairs_containment()
        self.assertEqual(len(found), 1)
        self.assertIn("3-srt", found[0])

    def test_not_yet_produced_is_fine(self):
        self.standard()
        self.assertEqual(rebuild.pairs_containment(), [])

    def test_paragraph_srt_without_its_csv_is_named(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        os.remove(self.out(AMIS_NAME))
        found = rebuild.pairs_containment()
        self.assertEqual(len(found), 1)
        self.assertIn(AMIS_NAME, found[0])
        self.assertIn("2-csv-analysis", found[0])

    def test_the_old_directory_beside_the_new_one_fails(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        os.makedirs(paths.LEGACY_PAIRS_DIR)
        found = rebuild.pairs_containment()
        self.assertEqual(len(found), 1)
        self.assertIn("2-平行語料", found[0])


if __name__ == "__main__":
    unittest.main()
