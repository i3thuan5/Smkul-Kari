"""news/lexicon_fetch: the 16 official dictionaries, kept in kithann/.

The SFTP is guaranteed to hold them (使用者裁定 2026-09-24), so a missing
local copy is fetched rather than treated as an error. What must not
happen is a silent partial set: 別族判定 compares all 16 tribes, and a
missing one makes every speaker of it look like 命中率不足 without any
error. The SFTP is faked; the xlsx files are synthesised.
"""
import os
import shutil
import tempfile
import time
import unittest

from scripts.errors import PipelineError
from scripts.news import lexicon_fetch
from tests.lexicon import fixtures

TRIBES = ["阿美", "泰雅", "排灣", "布農", "卑南", "魯凱", "鄒", "賽夏",
          "雅美", "邵", "噶瑪蘭", "太魯閣", "撒奇萊雅", "賽德克", "拉阿魯哇",
          "卡那卡那富"]


def word_of(number):
    """A letters-only word unique to one tribe (digits split words)."""
    return "kako" + "abcdefghijklmnopq"[number]


def remote_name(number, tribe, date="20260702"):
    return "%s_16族前台上線單字_%02d%s語1234筆(fin)(哈瑪星).xlsx" % (
        date, number, tribe)


def sftp_escape(name):
    """How sftp's `ls -l` prints a non-ASCII name: octal byte escapes."""
    out = []
    for byte in name.encode("utf-8"):
        if byte < 128:
            out.append(chr(byte))
        else:
            out.append("\\%03o" % byte)
    return "".join(out)


class FakeSftp(object):
    """Holds remote files as {name: bytes}; answers `ls` and `get`."""

    def __init__(self, files, short=()):
        self.files = files
        self.short = set(short)
        self.gets = []

    def __call__(self, verb, *args):
        if verb == "ls":
            lines = ['sftp> ls -l "%s"' % args[0]]
            for name, data in sorted(self.files.items()):
                lines.append("-rwxr-xr-x    1 ciciw    users %11d Jul  2 "
                             "00:37 %s" % (len(data), sftp_escape(name)))
            return 0, "\n".join(lines) + "\n"
        if verb == "get":
            remote, local = args
            name = os.path.basename(remote)
            self.gets.append(name)
            data = self.files[name]
            if name in self.short:
                data = data[:len(data) // 2]
            with open(local, "wb") as handle:
                handle.write(data)
            return 0, ""
        raise AssertionError(verb)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lexicon-fetch-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.folder = os.path.join(self.tmp, "族語辭典")
        self.build = os.path.join(self.tmp, "build")
        os.makedirs(self.build)

    def xlsx_bytes(self, words):
        path = os.path.join(self.build, "x.xlsx")
        rows = [fixtures.DICT_HEADER]
        for word in words:
            rows.append(fixtures.dict_row(word=word))
        fixtures.write_xlsx(path, rows)
        with open(path, "rb") as handle:
            return handle.read()

    def remote(self, tribes=TRIBES, date="20260702"):
        files = {}
        for number, tribe in enumerate(tribes, 1):
            files[remote_name(number, tribe, date)] = self.xlsx_bytes(
                [word_of(number), "salikaka"])
        return files


class TestParse(Base):
    def test_tribe_read_from_the_name_not_the_date(self):
        self.assertEqual(lexicon_fetch.tribe_of(remote_name(10, "邵")), "邵")
        self.assertEqual(
            lexicon_fetch.tribe_of(remote_name(10, "邵", date="20271231")),
            "邵")
        self.assertEqual(
            lexicon_fetch.tribe_of(remote_name(16, "卡那卡那富")), "卡那卡那富")

    def test_unknown_tribe_name_is_none(self):
        self.assertIsNone(lexicon_fetch.tribe_of("readme.txt"))

    def test_listing_decodes_sftp_octal_escapes(self):
        files = self.remote()
        listing = FakeSftp(files)("ls", "/remote")[1]
        found = lexicon_fetch.parse_listing(listing)
        self.assertEqual(sorted(found), sorted(files))
        name = remote_name(10, "邵")
        self.assertEqual(found[name], len(files[name]))


class TestEnsure(Base):
    def test_missing_folder_fetches_all_sixteen(self):
        sftp = FakeSftp(self.remote())
        paths = lexicon_fetch.ensure(self.folder, runner=sftp)
        self.assertEqual(sorted(paths), sorted(TRIBES))
        self.assertEqual(len(sftp.gets), 16)
        for path in paths.values():
            self.assertTrue(os.path.exists(path))

    def test_complete_local_copy_needs_no_sftp(self):
        lexicon_fetch.ensure(self.folder, runner=FakeSftp(self.remote()))

        def offline(*_args):
            raise AssertionError("SFTP must not be asked")
        paths = lexicon_fetch.ensure(self.folder, runner=offline)
        self.assertEqual(len(paths), 16)

    def test_only_the_missing_tribe_is_fetched(self):
        files = self.remote()
        lexicon_fetch.ensure(self.folder, runner=FakeSftp(files))
        gone = os.path.join(self.folder, remote_name(10, "邵"))
        os.remove(gone)
        sftp = FakeSftp(files)
        lexicon_fetch.ensure(self.folder, runner=sftp)
        self.assertEqual(sftp.gets, [remote_name(10, "邵")])

    def test_short_download_is_deleted_and_named(self):
        name = remote_name(10, "邵")
        sftp = FakeSftp(self.remote(), short=[name])
        with self.assertRaises(PipelineError) as caught:
            lexicon_fetch.ensure(self.folder, runner=sftp)
        self.assertIn("邵", str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(self.folder, name)))

    def test_fifteen_tribes_on_the_server_is_refused_by_name(self):
        tribes = [t for t in TRIBES if t != "鄒"]
        with self.assertRaises(PipelineError) as caught:
            lexicon_fetch.ensure(self.folder, runner=FakeSftp(
                self.remote(tribes)))
        self.assertIn("鄒", str(caught.exception))

    def test_two_local_versions_of_one_tribe_is_refused(self):
        lexicon_fetch.ensure(self.folder, runner=FakeSftp(self.remote()))
        old = os.path.join(self.folder, remote_name(10, "邵", "20250101"))
        shutil.copy(os.path.join(self.folder, remote_name(10, "邵")), old)
        with self.assertRaises(PipelineError) as caught:
            lexicon_fetch.ensure(self.folder, runner=FakeSftp(self.remote()))
        self.assertIn("邵", str(caught.exception))


class TestLexicons(Base):
    def test_distilled_word_sets_per_tribe(self):
        found = lexicon_fetch.lexicons(self.folder,
                                       runner=FakeSftp(self.remote()))
        self.assertEqual(sorted(found), sorted(TRIBES))
        self.assertIn(word_of(10), found["邵"])
        self.assertTrue(os.path.exists(
            os.path.join(self.folder, "詞庫", "邵.txt")))

    def test_newer_xlsx_is_distilled_again(self):
        files = self.remote()
        lexicon_fetch.lexicons(self.folder, runner=FakeSftp(files))
        cache = os.path.join(self.folder, "詞庫", "邵.txt")
        with open(cache, "w", encoding="utf-8") as handle:
            handle.write("stale\n")
        old = time.time() - 100
        os.utime(cache, (old, old))
        found = lexicon_fetch.lexicons(self.folder, runner=FakeSftp(files))
        self.assertNotIn("stale", found["邵"])
        self.assertIn(word_of(10), found["邵"])

    def test_fresh_cache_is_used_as_is(self):
        files = self.remote()
        lexicon_fetch.lexicons(self.folder, runner=FakeSftp(files))
        cache = os.path.join(self.folder, "詞庫", "邵.txt")
        with open(cache, "a", encoding="utf-8") as handle:
            handle.write("extra\n")
        future = time.time() + 100
        os.utime(cache, (future, future))
        found = lexicon_fetch.lexicons(self.folder, runner=FakeSftp(files))
        self.assertIn("extra", found["邵"])


if __name__ == "__main__":
    unittest.main()
