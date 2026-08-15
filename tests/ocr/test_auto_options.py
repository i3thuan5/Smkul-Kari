"""`auto` must hand the cue stage everything the caller gave it.

`auto` is `cues` + `ocr` + `srt` in one run, and it passes each stage its
arguments by building a Namespace by hand. Anything left off that list is
accepted on the command line and then silently dropped -- `stage_cues` reads
its optional arguments through getattr(..., None), so a missing one reads as
"not given" rather than raising.

That is how `--preset` came to be ignored by `auto`. It matters more than a
dropped flag usually would: without a preset the band is auto-detected, and
on this material detection ranks the weather graphic and the station's
lower-third above the dialogue line. The run then segments confidently on the
wrong strip of pixels and reports nothing wrong at all.

So the check here is structural rather than a list of flags to remember:
whatever `cues` accepts, `auto` must accept and must pass on.
"""
import argparse
import os
import tempfile
import unittest
from unittest import mock

from scripts.ocr import cli


# Named by their own subcommand, so they are not "missing" from the other.
OWN = {"command", "func", "video", "out", "work"}


def options_of(*argv):
    parsed = vars(cli.build_parser().parse_args(argv))
    names = set()
    for name in parsed:
        if name not in OWN:
            names.add(name)
    return names


class TestAutoAcceptsWhatCuesAccepts(unittest.TestCase):
    def test_auto_accepts_every_cue_option(self):
        cues = options_of("cues", "v.mp4", "-o", "work")
        auto = options_of("auto", "v.mp4", "-o", "out.srt")
        self.assertEqual(cues - auto, set())


class TestAutoPassesThemOn(unittest.TestCase):
    def _run(self, *extra):
        """Run stage_auto with the stages stubbed; return what cues got."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        argv = ["auto", "v.mp4", "-o", os.path.join(tmp.name, "out.srt")]
        args = cli.build_parser().parse_args(list(argv) + list(extra))
        seen = {}

        def record(cue_args):
            seen.update(vars(cue_args))
            return 0

        with mock.patch.object(cli, "stage_cues", record), \
             mock.patch.object(cli, "stage_ocr", lambda a: 0), \
             mock.patch.object(cli, "stage_srt", lambda a: 0):
            cli.stage_auto(args)
        return seen

    def test_preset_reaches_the_cue_stage(self):
        seen = self._run("--presets", "p.json", "--preset", "titv-news")
        self.assertEqual(seen.get("presets"), "p.json")
        self.assertEqual(seen.get("preset"), "titv-news")

    def test_every_cue_option_reaches_the_cue_stage(self):
        # Not just the two that were missing: the point is that nothing can
        # go missing again when a new option is added to `cues`.
        seen = self._run()
        missing = options_of("cues", "v.mp4", "-o", "work") - set(seen)
        self.assertEqual(missing, set())

    def test_the_cue_stage_is_told_where_to_work(self):
        seen = self._run()
        self.assertTrue(seen.get("out"))


class TestStageCuesReadsThemPlainly(unittest.TestCase):
    def test_preset_is_not_read_through_a_default(self):
        # getattr(args, "preset", None) is what turned a dropped argument
        # into a silent fallback. Reading it plainly makes the same mistake
        # an AttributeError instead.
        args = argparse.Namespace(video="v.mp4", out="w")
        with self.assertRaises(AttributeError):
            cli.stage_cues(args)


if __name__ == "__main__":
    unittest.main()
