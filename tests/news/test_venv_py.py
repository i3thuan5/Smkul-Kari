"""paths.venv_py()：揣一支**實在佇咧**ê python，莫寫死一條路。

`fetch_sftp.sh` 是用 `paths --var VENV_PY` 提 interpreter ê。彼本底是
一條寫死ê `~/.venvs/subs2srt/bin/python`，佇別台機器無彼跡，
shell 就講「沒有此一檔案或目錄」，規个抓檔停佇遮。

揀ê時毋是干焦看有佇咧無：`numpy` 佮 `PIL` 無ê彼支 python 走袂動
`ocr-cli cues`，錯會佇半路才出來，彼時影片已經落好矣。
"""
import os
import unittest
from unittest import mock

from scripts.news import paths


class TestCandidates(unittest.TestCase):
    def test_the_env_override_comes_first(self):
        with mock.patch.dict(os.environ, {"SUBS2SRT_PY": "/opt/mine/python"}):
            self.assertEqual(paths.venv_candidates()[0], "/opt/mine/python")

    def test_the_documented_venv_is_offered(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            got = paths.venv_candidates()
        self.assertIn(os.path.expanduser("~/.venvs/subs2srt/bin/python"), got)

    def test_the_repo_tox_venv_is_offered(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            got = paths.venv_candidates()
        wanted = os.path.join(paths.ROOT, ".tox", "rebuild", "bin", "python")
        self.assertIn(wanted, got)

    def test_the_running_interpreter_is_the_last_resort(self):
        import sys
        with mock.patch.dict(os.environ, {}, clear=True):
            got = paths.venv_candidates()
        self.assertEqual(got[-1], sys.executable)

    def test_no_candidate_appears_twice(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            got = paths.venv_candidates()
        self.assertEqual(len(got), len(set(got)))


class TestPick(unittest.TestCase):
    def test_the_first_usable_one_wins(self):
        got = paths.venv_py(candidates=["/no/such/a", "/no/such/b"],
                            usable=lambda p: p == "/no/such/b")
        self.assertEqual(got, "/no/such/b")

    def test_order_is_respected(self):
        got = paths.venv_py(candidates=["/a", "/b"], usable=lambda p: True)
        self.assertEqual(got, "/a")

    def test_none_usable_falls_back_to_the_running_one(self):
        """一支都用袂得ê時，猶原愛還一條路轉去——予後壁ê步報
        伊家己ê錯，較好過 shell 講『無此一檔案』。"""
        import sys
        got = paths.venv_py(candidates=["/a", "/b"], usable=lambda p: False)
        self.assertEqual(got, sys.executable)

    def test_it_never_returns_empty(self):
        got = paths.venv_py(candidates=[], usable=lambda p: False)
        self.assertTrue(got)


class TestUsable(unittest.TestCase):
    def test_a_path_that_is_not_there_is_not_usable(self):
        self.assertFalse(paths.python_usable("/no/such/python"))

    def test_the_running_interpreter_is_usable(self):
        """這支 python 走會動這个測試，所以伊有齊ê物件。"""
        import sys
        self.assertTrue(paths.python_usable(sys.executable))


class TestVarCli(unittest.TestCase):
    """`paths --var VENV_PY` 是 shell 唯一ê入口，愛照常會通。"""

    def test_venv_py_is_still_a_var_name(self):
        import subprocess
        import sys
        done = subprocess.run(
            [sys.executable, "-m", "scripts.news.paths", "--var", "VENV_PY"],
            capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=paths.ROOT), cwd=paths.ROOT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.strip())

    def test_what_it_prints_actually_exists(self):
        """本底彼條寫死ê路徑印出來嘛「成功」，soah無彼支檔案。"""
        import subprocess
        import sys
        done = subprocess.run(
            [sys.executable, "-m", "scripts.news.paths", "--var", "VENV_PY"],
            capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=paths.ROOT), cwd=paths.ROOT)
        self.assertTrue(os.path.exists(done.stdout.strip()),
                        done.stdout.strip())


if __name__ == "__main__":
    unittest.main()
