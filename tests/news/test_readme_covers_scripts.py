"""README ài綴著程式走——袂記得更新ê時，遮會當場破。

問題毋是「文件寫了好穤」，是**文件佮程式走精去矣家己無聲無說**。
新開一支模組，`scripts/README.md` 彼張表若無補一逝，過三個月無人
知影彼支是創啥ê，嘛無人知影伊佮別支ê關係。

靠記無效——已經有三支（`blind_cues.py`、`evidence.py`、
`name_catalogue.py`）就是按呢漏去ê。所以改做予伊**機械性掠著**：
這條測試綴 `tox -e unittest` 走，驗收清單本底就有彼條，免加新習慣。

規則真簡單：`scripts/<pkg>/` 內底逐支 `.py`（`__init__.py` 除外），
`scripts/README.md` 內底ài有伊ê檔名。寫佇佗一節、寫偌詳細，這條無
管——彼是人ê判斷；伊干焦保證「有講著」。
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
README = os.path.join(ROOT, "scripts", "README.md")

# 這幾支毋是模組，是 package ê空殼，免寫入文件。
SKIP = {"__init__.py"}


def modules():
    """scripts/ 底下逐支愛有文件ê .py，回 (相對路徑, 檔名)。"""
    out = []
    top = os.path.join(ROOT, "scripts")
    for base, _dirs, files in os.walk(top):
        if "__pycache__" in base:
            continue
        for name in sorted(files):
            if not name.endswith(".py") or name in SKIP:
                continue
            out.append((os.path.relpath(os.path.join(base, name), ROOT),
                        name))
    return out


class TestReadmeCoversScripts(unittest.TestCase):
    def setUp(self):
        with open(README, encoding="utf-8") as handle:
            self.text = handle.read()

    def test_every_module_is_named_in_the_readme(self):
        missing = []
        for path, name in modules():
            if not re.search(re.escape(name), self.text):
                missing.append(path)
        self.assertEqual(
            missing, [],
            "這幾支程式 scripts/README.md 無講著，補一逝才過：\n  "
            + "\n  ".join(missing))

    def test_the_readme_does_not_name_modules_that_are_gone(self):
        """反爿嘛愛顧：檔hìnn-sak矣，文件彼逝愛做伙提掉。"""
        alive = set()
        for _path, name in modules():
            alive.add(name)
        stale = []
        for name in re.findall(r"`([A-Za-z0-9_]+\.py)`", self.text):
            if name not in alive and name not in SKIP:
                stale.append(name)
        self.assertEqual(
            sorted(set(stale)), [],
            "scripts/README.md 講著ê程式已經無佇咧矣：%s" % sorted(set(stale)))


if __name__ == "__main__":
    unittest.main()
