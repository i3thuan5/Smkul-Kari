"""One-off resweep: make the store's JSON files readable by a person.

The store is the deliverable, and 使用者裁定 2026-09-04 that every file
in it should open and read -- so JSON is indented, keys sorted, Chinese
and Formosan characters left as themselves rather than `\\uXXXX`. What
this sweep must never do is change what a file *says*: the rebuild
verification compares the SRTs it can derive from these inputs, so a
resweep that dropped or reordered a value would show up as a corpus-wide
byte mismatch and nobody could tell whether the data or the formatting
was at fault.

JSONL caches (mt-cache) are the exception the rule names: one record per
line is what makes them appendable, so they get sorted keys and readable
characters but no indent.

冪等是硬需求——掃到一半予人斷去是正常ê，閣走一擺愛照常收煞。
"""
import json
import os
import tempfile
import unittest

from scripts.news import redump_store

MESSY = '{"b": 2, "a": {"\\u65cf\\u8a9e": [1, 2]}}'
MESSY_DOC = {"b": 2, "a": {"族語": [1, 2]}}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def _file(self, name, text):
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()


class TestJsonRedump(Fixture):
    def test_the_content_is_unchanged(self):
        path = self._file("a.json", MESSY)
        redump_store.redump_json(path)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), MESSY_DOC)

    def test_it_becomes_indented_with_sorted_keys(self):
        path = self._file("b.json", MESSY)
        redump_store.redump_json(path)
        text = self._read(path)
        self.assertIn('\n  "a": {\n', text)
        self.assertLess(text.index('"a"'), text.index('"b"'))

    def test_chinese_is_not_escaped(self):
        path = self._file("c.json", MESSY)
        redump_store.redump_json(path)
        text = self._read(path)
        self.assertIn("族語", text)
        self.assertNotIn("\\u", text)

    def test_it_ends_with_one_newline(self):
        path = self._file("d.json", MESSY)
        redump_store.redump_json(path)
        self.assertTrue(self._read(path).endswith("}\n"))

    def test_running_twice_changes_nothing_the_second_time(self):
        path = self._file("e.json", MESSY)
        self.assertTrue(redump_store.redump_json(path))
        self.assertFalse(redump_store.redump_json(path))

    def test_an_already_tidy_file_is_left_alone(self):
        path = self._file("f.json", json.dumps(
            MESSY_DOC, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertFalse(redump_store.redump_json(path))


class TestJsonlRedump(Fixture):
    LINES = ('{"out": "\\u5927\\u5bb6\\u597d", "engine": "ailabs"}\n'
             '{"engine": "ailabs", "out": "\\u8b1d\\u8b1d"}\n')

    def test_each_record_survives(self):
        path = self._file("mt-cache/ailabs.jsonl", self.LINES)
        redump_store.redump_jsonl(path)
        rows = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                rows.append(json.loads(line))
        self.assertEqual(rows, [{"engine": "ailabs", "out": "大家好"},
                                {"engine": "ailabs", "out": "謝謝"}])

    def test_one_record_stays_on_one_line(self):
        path = self._file("mt-cache/a.jsonl", self.LINES)
        redump_store.redump_jsonl(path)
        self.assertEqual(len(self._read(path).splitlines()), 2)

    def test_keys_are_sorted_and_characters_readable(self):
        path = self._file("mt-cache/b.jsonl", self.LINES)
        redump_store.redump_jsonl(path)
        first = self._read(path).splitlines()[0]
        self.assertTrue(first.startswith('{"engine"'))
        self.assertIn("大家好", first)

    def test_running_twice_changes_nothing_the_second_time(self):
        path = self._file("mt-cache/c.jsonl", self.LINES)
        self.assertTrue(redump_store.redump_jsonl(path))
        self.assertFalse(redump_store.redump_jsonl(path))

    def test_record_order_is_preserved(self):
        """快取是內容定址ê，順序無要緊——毋過改順序就變做規檔攏
        佇 diff 內底，看袂出實際加啥物。"""
        path = self._file("mt-cache/d.jsonl",
                          '{"text": "b"}\n{"text": "a"}\n')
        redump_store.redump_jsonl(path)
        self.assertEqual(self._read(path),
                         '{"text": "b"}\n{"text": "a"}\n')


class TestSweep(Fixture):
    def _corpus(self):
        self._file("1-words/2021-01/x.json", MESSY)
        self._file("1-cues/2021-01/x.json", MESSY)
        self._file("mt-cache/ailabs.jsonl", '{"b": 1, "a": 2}\n')
        self._file("notes.txt", "not json")

    def test_a_dry_run_touches_nothing(self):
        self._corpus()
        path = os.path.join(self.root, "1-words", "2021-01", "x.json")
        redump_store.sweep([self.root], write=False)
        self.assertEqual(self._read(path), MESSY)

    def test_it_reports_what_it_would_do(self):
        self._corpus()
        would, tidy = redump_store.sweep([self.root], write=False)
        self.assertEqual(len(would), 3)
        self.assertEqual(tidy, 0)

    def test_writing_rewrites_every_json_and_jsonl(self):
        self._corpus()
        redump_store.sweep([self.root], write=True)
        changed, tidy = redump_store.sweep([self.root], write=False)
        self.assertEqual(changed, [])
        self.assertEqual(tidy, 3)

    def test_non_json_files_are_not_touched(self):
        self._corpus()
        redump_store.sweep([self.root], write=True)
        self.assertEqual(self._read(os.path.join(self.root, "notes.txt")),
                         "not json")


if __name__ == "__main__":
    unittest.main()
