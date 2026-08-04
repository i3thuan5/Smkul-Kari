"""Decoding the corpus 文稿: RTF 1.0, \\'xx escapes, Big5 despite the header.

The fixtures are synthesised the same way the real files are built: Big5
bytes written as \\'xx escapes inside an \\ansicpg1252 header. Decoding via
cp1252 is exactly the mojibake trap the module exists to avoid.
"""
import os
import tempfile
import unittest

from scripts.news import rtf


def big5_escapes(text):
    """The \\'xx escape sequence for `text`, as the real files encode it."""
    out = []
    for byte in text.encode("big5"):
        out.append("\\'%02x" % byte)
    return "".join(out)


def write_rtf(folder, name, body):
    path = os.path.join(folder, name)
    with open(path, "wb") as handle:
        handle.write(body.encode("latin-1"))
    return path


class TestRtfText(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _decode(self, body):
        path = write_rtf(self.tmp.name, "one.rtf", body)
        return rtf.rtf_text(path)

    def test_big5_escapes_decode_as_big5_not_cp1252(self):
        body = "{\\rtf1\\ansi\\ansicpg1252 %s}" % big5_escapes("主播")
        self.assertIn("主播", self._decode(body))

    def test_par_and_line_become_newlines(self):
        body = ("{\\rtf1 %s\\par %s}"
                % (big5_escapes("第一句"), big5_escapes("第二句")))
        lines = self._decode(body).splitlines()
        self.assertIn("第一句", lines[0])
        self.assertIn("第二句", lines[1])

    def test_font_table_group_is_stripped(self):
        body = ("{\\rtf1{\\fonttbl{\\f0\\fcharset136 PMingLiU;}}%s}"
                % big5_escapes("內文"))
        got = self._decode(body)
        self.assertIn("內文", got)
        self.assertNotIn("PMingLiU", got)

    def test_control_words_are_dropped(self):
        body = "{\\rtf1\\fs28\\b %s\\b0}" % big5_escapes("標題")
        got = self._decode(body)
        self.assertIn("標題", got)
        self.assertNotIn("fs28", got)

    def test_mixed_latin_survives(self):
        body = "{\\rtf1 Alang %s}" % big5_escapes("部落")
        got = self._decode(body)
        self.assertIn("Alang", got)
        self.assertIn("部落", got)


class TestEpisodeText(unittest.TestCase):
    def test_missing_folder_yields_nothing(self):
        self.assertEqual(rtf.episode_text(""), [])
        self.assertEqual(rtf.episode_text("/no/such/folder"), [])

    def test_reads_rtf_files_in_name_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_rtf(tmp, "b.rtf",
                      "{\\rtf1 %s}" % big5_escapes("第二篇稿"))
            write_rtf(tmp, "a.rtf",
                      "{\\rtf1 %s}" % big5_escapes("第一篇稿"))
            write_rtf(tmp, "notes.txt", "ignored")
            items = rtf.episode_text(tmp)
        names = []
        for item in items:
            names.append(item["file"])
        self.assertEqual(names, ["a.rtf", "b.rtf"])
        self.assertEqual(items[0]["lines"], ["第一篇稿"])


if __name__ == "__main__":
    unittest.main()
