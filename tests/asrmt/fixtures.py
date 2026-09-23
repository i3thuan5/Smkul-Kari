"""Synthetic data builders shared by the asrmt test files.

Everything is built in memory: word streams with timestamps, subtitle
entries with true windows, and canned translation tables. No vosk, no
network, no real episode data.
"""
import json


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


class FakeResponse(object):
    """Stands in for the object `urllib.request.urlopen` returns.

    `.read()` gives the whole body; iterating gives it back line by line
    (SSE streams are read that way) -- both taken from the same bytes,
    the way a real `HTTPResponse` would behave.
    """

    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self.body

    def __iter__(self):
        for line in self.body.split(b"\n"):
            if line:
                yield line + b"\n"


class FakeOpener(object):
    """Stands in for `urllib.request.urlopen` inside `gradio.Client`.

    One queue per gradio endpoint (`join`, `data`, `upload`); each queue
    holds what to do on the *next* call to that endpoint -- a
    `FakeResponse`, or an exception instance to raise. Every request is
    recorded (url, body bytes, headers, timeout) so a test can check what
    was actually sent, not just what came back.
    """

    def __init__(self, join=None, data=None, upload=None):
        self.join = list(join or [])
        self.data = list(data or [])
        self.upload = list(upload or [])
        self.requests = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requests.append(
            (url, req.data, dict(req.header_items()), timeout))
        if url.endswith("/upload"):
            queue = self.upload
        elif url.endswith("/queue/join"):
            queue = self.join
        elif "/queue/data" in url:
            queue = self.data
        else:
            raise AssertionError("unscripted URL: %s" % url)
        if not queue:
            raise AssertionError("no scripted response left for %s" % url)
        next_item = queue.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def sse(*events):
    """A fake SSE body out of gradio event dicts, `data:` lines only.

    Real streams also carry blank lines and, on some replies, an
    `event: complete` line ahead of the matching `data:` -- the parser
    only ever reads lines starting with `data:`, so those are omitted
    here rather than reproduced.
    """
    lines = []
    for event in events:
        lines.append("data: " + json.dumps(event))
        lines.append("")
    return "\n".join(lines) + "\n"


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
