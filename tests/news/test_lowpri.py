"""Niceness is a target to reach, not an amount to keep adding.

`os.nice` is cumulative, and this pipeline nices in two places: the shell
wrappers run their heavy steps under `nice -n 15`, and the Python entry
points call `be_nice()`. Adding 15 to an already-niced 15 lands on 30,
which the kernel clamps to 19 -- the job ends up at the very bottom
instead of the level that was chosen.

The old guard was a module flag, and it could not see this: a flag is
per-process, and the shell's nice happened before the process existed.
Topping up to a target handles both -- and it is idempotent by nature,
so the flag goes.
"""
import unittest
from unittest import mock

from scripts import lowpri


class TestTopUpToTheTarget(unittest.TestCase):
    def _run(self, current, target=lowpri.NICE):
        """Call be_nice with a fake os.nice that starts at `current`."""
        state = {"value": current}

        def fake_nice(step):
            state["value"] += step
            return state["value"]

        with mock.patch.object(lowpri.os, "nice", fake_nice):
            lowpri.be_nice(target)
        return state["value"]

    def test_a_fresh_process_reaches_the_target(self):
        self.assertEqual(self._run(0), lowpri.NICE)

    def test_a_shell_niced_process_stays_at_the_target(self):
        """`nice -n 15 python …`：本底就佇 15 矣，袂使閣加 15 變 30。"""
        self.assertEqual(self._run(lowpri.NICE), lowpri.NICE)

    def test_a_partly_niced_process_is_topped_up(self):
        self.assertEqual(self._run(5), lowpri.NICE)

    def test_an_already_lower_process_is_left_alone(self):
        """已經比目標閣較低ê，莫kā伊搝懸——彼是別人刻意設ê。"""
        self.assertEqual(self._run(19), 19)

    def test_calling_twice_does_not_add_twice(self):
        state = {"value": 0}

        def fake_nice(step):
            state["value"] += step
            return state["value"]

        with mock.patch.object(lowpri.os, "nice", fake_nice):
            lowpri.be_nice()
            lowpri.be_nice()
        self.assertEqual(state["value"], lowpri.NICE)

    def test_a_platform_that_refuses_still_lets_the_job_run(self):
        def refuse(step):
            raise OSError("not permitted")

        with mock.patch.object(lowpri.os, "nice", refuse):
            self.assertIsNone(lowpri.be_nice())


if __name__ == "__main__":
    unittest.main()
