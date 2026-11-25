"""How far a batch has got and how long the rest will take.

Printed to the terminal and written to the run's log, so a run started
in the background can be followed with `tail -f`.

The estimate is the mean of the **last 10** episodes that were really
processed (使用者裁定 2026-11-23), times how many are left to do. A
whole-run mean is dragged by the first few: when the network slows, it
takes hours to catch up, while ten episodes is about an hour. Episodes
skipped because the server already had both outputs take a second or
two and are not work, so they never enter the window -- counting the
1200 of a resumed run would print "under an hour" for 195 hours.
"""
import math
import time

WINDOW = 10
SKIPPED = "已存在"


def hours_minutes(seconds):
    """"H 小時 M 分", rounded to the minute first so 59:36 is 1 h 0 m."""
    minutes = int(math.floor(seconds / 60.0 + 0.5))
    hours, minutes = divmod(minutes, 60)
    return "%d 小時 %d 分" % (hours, minutes)


def minutes_seconds(seconds):
    whole = int(math.floor(seconds + 0.5))
    minutes, rest = divmod(whole, 60)
    return "%d 分 %d 秒" % (minutes, rest)


def eta_seconds(recent, remaining):
    """Mean of `recent` times `remaining`, or None with nothing to go on."""
    if not recent:
        return None
    return sum(recent) / len(recent) * remaining


def done_labels(labels, remotes, existing):
    """Which labels already have both outputs on the server.

    `remotes` maps a label to its (preview, wav) remote paths; `existing`
    is the set of remote paths the server listed. One output alone is
    still work to do.
    """
    out = set()
    for label in labels:
        preview, wav = remotes[label]
        if preview in existing and wav in existing:
            out.add(label)
    return out


class Progress:
    """Counts for one run.

    `labels` is every episode in the run (after --limit), in order;
    `done_before` the ones whose outputs were already all there when it
    started.
    """

    def __init__(self, labels, done_before, clock=time.monotonic,
                 window=WINDOW):
        self.total = len(labels)
        self.done_before = set(done_before)
        self.to_do = self.total - len(self.done_before)
        self.remaining = self.to_do
        self.worked = 0
        self.position = 0
        self.recent = []
        self.window = window
        self.clock = clock
        self.started = None
        self.counts = {"成功": 0, "失敗": 0, SKIPPED: 0}

    def start(self):
        self.started = self.clock()
        return ("全部 %d 支，已完成 %d 支（預覽檔與音檔都在），這次要做 %d 支"
                % (self.total, len(self.done_before), self.to_do))

    def finished(self, label, result, seconds):
        """Record one episode; the line to print for it."""
        self.position += 1
        self.counts[result] = self.counts.get(result, 0) + 1
        if result == SKIPPED:
            if label not in self.done_before:
                # Appeared on the server after the run began: one fewer to
                # do, but it says nothing about how fast we are.
                self.remaining = max(self.remaining - 1, 0)
            head = "[第 %d／%d 支] %s %s" % (self.position, self.total,
                                          label, result)
        else:
            self.worked += 1
            self.remaining = max(self.remaining - 1, 0)
            self.recent.append(seconds)
            if len(self.recent) > self.window:
                self.recent.pop(0)
            head = "[第 %d／%d 支] %s %s 用時 %s" % (
                self.position, self.total, label, result,
                minutes_seconds(seconds))
        eta = eta_seconds(self.recent, self.remaining)
        if self.remaining == 0:
            tail = "這次沒有要做的了"
        elif eta is None:
            tail = "預計時間：第一支做完後估算"
        else:
            tail = "預計還要 %s" % hours_minutes(eta)
        return "%s｜這次已做 %d／%d 支，%s" % (
            head, self.worked, self.to_do, tail)

    def summary(self):
        elapsed = self.clock() - (self.started if self.started is not None
                                  else self.clock())
        return ("總用時 %s；成功 %d 支、失敗 %d 支、已存在 %d 支"
                % (hours_minutes(elapsed), self.counts.get("成功", 0),
                   self.counts.get("失敗", 0), self.counts.get(SKIPPED, 0)))
