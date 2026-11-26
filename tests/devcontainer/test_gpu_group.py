"""gpu-group.sh：把 vscode 加進擁有 GPU 裝置的那個群組，不管它叫什麼名字。

2026-11-26 第一次重建成 Ubuntu 26.04：主機上 /dev/dri/renderD128 的群組
是 GID 992，26.04 image 裡 992 已經是 systemd-resolve。舊寫法
`groupadd -f -g 992 render` 因為 992 被佔，-f 默默改用 1001 建 render，
vscode 在 render 裡卻打不開裝置，vainfo 退去找圖形顯示環境而看似卡住。

離線測試：PATH 最前面放假的 stat（印 FAKE_GID）、getent（讀假的群組
表 FAKE_GROUP）、sudo（只把參數記到 SUDO_LOG），斷言腳本送出的指令。
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".devcontainer", "gpu-group.sh")

FAKE_STAT = """#!/usr/bin/env bash
echo "$FAKE_GID"
"""

FAKE_GETENT = """#!/usr/bin/env bash
# getent group KEY：KEY 是名字或 GID
[ "$1" = group ] || exit 2
while IFS=: read -r name pass gid members; do
    if [ "$name" = "$2" ] || [ "$gid" = "$2" ]; then
        echo "$name:$pass:$gid:$members"
        exit 0
    fi
done < "$FAKE_GROUP"
exit 2
"""

FAKE_SUDO = """#!/usr/bin/env bash
echo "$*" >> "$SUDO_LOG"
"""


class GpuGroupCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gpu-group-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        bin_dir = os.path.join(self.tmp, "bin")
        os.mkdir(bin_dir)
        for name, body in (("stat", FAKE_STAT), ("getent", FAKE_GETENT),
                           ("sudo", FAKE_SUDO)):
            path = os.path.join(bin_dir, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.chmod(path, 0o755)
        self.bin_dir = bin_dir
        self.device = os.path.join(self.tmp, "renderD128")
        self.groups = os.path.join(self.tmp, "group")
        self.log = os.path.join(self.tmp, "sudo.log")

    def run_script(self, groups, gid="992", device_exists=True):
        with open(self.groups, "w", encoding="utf-8") as handle:
            for line in groups:
                handle.write(line + "\n")
        if device_exists:
            open(self.device, "w").close()
        env = dict(os.environ)
        env["PATH"] = self.bin_dir + os.pathsep + env["PATH"]
        env["FAKE_GID"] = gid
        env["FAKE_GROUP"] = self.groups
        env["SUDO_LOG"] = self.log
        proc = subprocess.run(["bash", SCRIPT, self.device, "vscode"],
                              capture_output=True, text=True, env=env)
        calls = []
        if os.path.exists(self.log):
            with open(self.log, encoding="utf-8") as handle:
                for line in handle:
                    calls.append(line.rstrip("\n"))
        return proc, calls


class TestGidTakenBySystemGroup(GpuGroupCase):
    def test_joins_systemd_resolve_without_creating_a_group(self):
        """26.04 實測：992 已是 systemd-resolve，不可以另建 render。"""
        proc, calls = self.run_script(
            ["video:x:44:", "systemd-resolve:x:992:", "nvm:x:999:vscode"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, ["usermod -aG video,systemd-resolve vscode"])


class TestGidFree(GpuGroupCase):
    def test_creates_render_with_the_device_gid(self):
        """24.04 的情形：992 沒有群組，用 992 建 render，而且不帶 -f。"""
        proc, calls = self.run_script(["video:x:44:", "nvm:x:999:vscode"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, ["groupadd -g 992 render",
                                 "usermod -aG video,render vscode"])


class TestRenderNameTaken(GpuGroupCase):
    def test_leftover_render_1001_is_left_alone(self):
        """第一次失敗的重建留下 GID 1001 的 render：再建 render 會撞名。"""
        proc, calls = self.run_script(["video:x:44:", "render:x:1001:vscode"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, ["groupadd -g 992 render-992",
                                 "usermod -aG video,render-992 vscode"])


class TestNoGpu(GpuGroupCase):
    def test_no_device_changes_nothing_and_succeeds(self):
        """沒有 GPU 的機器：post-create 是 set -e，這裡失敗會讓容器建不起來。"""
        proc, calls = self.run_script(["video:x:44:"], device_exists=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, [])
        self.assertIn("renderD128", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
