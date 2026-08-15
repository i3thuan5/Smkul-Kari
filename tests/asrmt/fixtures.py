"""Synthetic data builders shared by the asrmt test files.

Everything is built in memory: word streams with timestamps, subtitle
entries with true windows, and canned translation tables. No vosk, no
network, no real episode data.
"""


def word(w, start, end, conf=1.0):
    return {"w": w, "start": start, "end": end, "conf": conf}


def words_evenly(text, start, end, conf=1.0):
    """Spread the words of `text` evenly across [start, end]."""
    parts = text.split()
    out = []
    if not parts:
        return out
    step = (end - start) / len(parts)
    for i, w in enumerate(parts):
        out.append(word(w, start + i * step, start + (i + 1) * step, conf))
    return out


def entry(index, true_start, true_end, subtitle="", srt_start=None,
          srt_end=None):
    """One SRT entry: true window plus (padded) display window."""
    if srt_start is None:
        srt_start = true_start
    if srt_end is None:
        srt_end = true_end
    return {
        "index": index,
        "true_start": true_start, "true_end": true_end,
        "srt_start": srt_start, "srt_end": srt_end,
        "subtitle": subtitle,
    }


def entries_grid(count, width=2.0, subtitle_of=None):
    """`count` back-to-back entries of `width` seconds each, from t=0."""
    out = []
    for i in range(count):
        text = ""
        if subtitle_of is not None:
            text = subtitle_of(i)
        out.append(entry(i + 1, i * width, (i + 1) * width, text))
    return out


class FakeMT(object):
    """A translation engine backed by a dict: {(direction, text): out}.

    Counts calls so tests can pin "translate once, slide for free" and
    cache-hit behaviour.
    """

    def __init__(self, table):
        self.table = table
        self.calls = []

    def translate(self, direction, src_lang, text):
        self.calls.append((direction, src_lang, text))
        return self.table.get((direction, text), "")


class FakeTransport(object):
    """Stands in for the gradio HTTP layer inside MTClient tests.

    `script` maps (endpoint, text) -> reply; every hit is recorded so the
    tests can assert call order (lambda handshake before translate) and
    call counts (cache hits make no requests).
    """

    def __init__(self, script):
        self.script = script
        self.requests = []

    def call(self, endpoint, payload_text):
        self.requests.append((endpoint, payload_text))
        key = (endpoint, payload_text)
        if key not in self.script:
            raise AssertionError("unexpected request %r" % (key,))
        return self.script[key]
