"""paths: ROOT derivation, the ILRDF_CORPUS override, the --var CLI."""
import os
import subprocess
import sys
import unittest

from scripts.news import paths


class TestConstants(unittest.TestCase):
    def test_root_is_the_repo_checkout(self):
        # derived from __file__, so it must hold this very package
        self.assertTrue(os.path.isdir(os.path.join(paths.ROOT, "scripts",
                                                   "news")))
        self.assertTrue(os.path.isfile(os.path.join(paths.ROOT, "tox.ini")))

    def test_everything_but_corpus_lives_under_root(self):
        for value in (paths.WORK, paths.LOGS, paths.KARI, paths.SRT_DIR,
                      paths.ENGINE_PRESETS, paths.INVENTORY,
                      paths.CATALOGUE):
            self.assertTrue(value.startswith(paths.ROOT + os.sep), value)

    def test_srt_dir_is_inside_kari(self):
        self.assertTrue(paths.SRT_DIR.startswith(paths.KARI + os.sep))

    def test_store_layout_is_corpus_technique_stage(self):
        # Kari-SRT is layered corpus -> technique -> numbered stage; the
        # numbers are the production order (srt-data-store spec).
        news = os.path.join(paths.KARI, "news")
        ocr = os.path.join(news, "1-ocr")
        self.assertEqual(paths.KARI_CUES, os.path.join(ocr, "1-cues"))
        self.assertEqual(paths.KARI_FROM_RTF,
                         os.path.join(ocr, "2-from_rtf"))
        self.assertEqual(paths.KARI_VISION, os.path.join(ocr, "3-vision"))
        self.assertEqual(paths.KARI_VISION_RTF,
                         os.path.join(ocr, "4-vision-rtf"))
        self.assertEqual(paths.SRT_DIR, os.path.join(ocr, "6-srt"))
        self.assertEqual(paths.INVENTORY,
                         os.path.join(news, "inventory.json"))
        self.assertEqual(paths.TRACKER_STORE,
                         os.path.join(news, "smkul.csv"))
        self.assertEqual(paths.ASR_DIR, os.path.join(news, "2-asr"))


class TestCorpusOverride(unittest.TestCase):
    def _var(self, name, env_extra):
        env = dict(os.environ)
        env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.news.paths", "--var", name],
            capture_output=True, text=True, cwd=paths.ROOT, env=env)
        return proc

    def test_ilrdf_corpus_env_wins(self):
        proc = self._var("CORPUS", {"ILRDF_CORPUS": "/mnt/elsewhere"})
        self.assertEqual(proc.stdout.strip(), "/mnt/elsewhere")

    def test_unknown_var_fails_and_lists_the_known_ones(self):
        proc = self._var("NO_SUCH_PATH", {})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("WORK", proc.stderr)


if __name__ == "__main__":
    unittest.main()
