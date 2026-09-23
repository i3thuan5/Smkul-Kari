#!/usr/bin/env python3
"""The ai-labs translation service client, and the shared MT cache.

The service is a gradio app whose language dropdown is session-scoped:
a session must call the ethnicity `lambda` before `translate` will accept
a non-default language code (measured, not documented). One request at a
time with a fixed pause -- it is a public service for speakers, not an
API farm.

The cache is content-addressed JSONL, one file per engine under the
store's mt-cache/: the same (engine, direction, src_lang, text) never
hits a service twice, and a rerun -- or a re-projection after the cue
timeline changes -- picks up every already-translated line for free.
"""
import json
import os
import time
from scripts.asrmt import dialects
from scripts.asrmt import gradio
from scripts.errors import PipelineError

ZH = "zho_Hant"

# Which 族別 the handshake selects comes from `scripts.asrmt.dialects`,
# a table read off the service's own dropdowns. It used to be read off
# the code's prefix, which is wrong for Seediq: its codes are trv_Delu /
# trv_Duda / trv_Tegu, the same prefix as Truku, so the prefix rule
# handed the session the Truku dropdown -- which does not contain them.


class MTCache(object):
    """Append-only JSONL cache, one file per engine, loaded whole."""

    def __init__(self, folder):
        self.folder = folder
        self.entries = {}
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    key = (row["engine"], row["direction"],
                           row["src_lang"], row["text"])
                    self.entries[key] = row["out"]

    def get(self, engine, direction, src_lang, text):
        return self.entries.get((engine, direction, src_lang, text))

    def repeated_outputs(self):
        """Translations this service gave for more than one input.

        The service has no way of saying "I don't know": out of its
        depth it emits a canned sentence instead, and the giveaway is
        that the same sentence comes back word for word for unrelated
        source lines. Recognisable ones in this corpus include a couple
        of origin stories and, more tellingly, bare dictionary glosses
        (「屬格標記」,「女子名」) -- the training data evidently held a
        linguistic wordlist.

        Counting is the whole detector: no model, no threshold to
        calibrate, and it gets better as the cache grows.
        """
        sources = {}
        for engine, direction, src_lang, text in self.entries:
            out = self.entries[(engine, direction, src_lang, text)]
            sources.setdefault(out, set()).add(text)
        repeated = set()
        for out in sources:
            if len(sources[out]) > 1:
                repeated.add(out)
        return repeated

    def put(self, engine, direction, src_lang, text, out):
        key = (engine, direction, src_lang, text)
        self.entries[key] = out
        path = os.path.join(self.folder, engine + ".jsonl")
        row = {"engine": engine, "direction": direction,
               "src_lang": src_lang, "text": text, "out": out}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False,
                                    sort_keys=True) + "\n")


class HttpTransport(object):
    """The ai-labs app's two endpoints, over the shared gradio protocol.

    The queue-join-then-read-SSE mechanics (retries included) live in
    `scripts.asrmt.gradio`, shared with sapolita; this class only knows
    the app's own shape: which `fn_index`/`trigger_id` each endpoint is,
    and how to build its payload.
    """

    # The app has four endpoints -- two per direction. Only the
    # Formosan->Chinese pair is used; the reverse was dropped with the
    # review render that was its only reader.
    FN = {"lambda": 0, "translate": 1}
    TRIGGER = {"lambda": 7, "translate": 11}

    def __init__(self, base_url, session_hash):
        self.client = gradio.Client(base_url, session_hash)

    def _payload(self, endpoint, text, src_lang):
        if endpoint == "lambda":
            return [text]
        return [text, src_lang, ZH]

    def call_full(self, endpoint, text, src_lang=""):
        data = self.client.call(self.FN[endpoint], self.TRIGGER[endpoint],
                                self._payload(endpoint, text, src_lang),
                                timeout=180)
        first = data[0] if data else ""
        if isinstance(first, str):
            return first
        return json.dumps(first, ensure_ascii=False)


class MTClient(object):
    """Session bookkeeping over a transport; injectable for tests."""

    def __init__(self, base_url="", transport=None, pause=1.0,
                 sleep=time.sleep, session_hash=None):
        if transport is None:
            if session_hash is None:
                session_hash = "asrmt%d" % os.getpid()
            transport = HttpTransport(base_url, session_hash)
        self.transport = transport
        self.pause = pause
        self.sleep = sleep
        self._ready = set()
        self._called_before = False

    def _call(self, endpoint, text, src_lang=""):
        if self._called_before:
            self.sleep(self.pause)
        self._called_before = True
        if hasattr(self.transport, "call_full"):
            return self.transport.call_full(endpoint, text, src_lang)
        return self.transport.call(endpoint, text)

    def translate(self, direction, lang, text):
        """direction: 'f2z' -- formosan -> zho_Hant. There is no other.

        The reverse direction was dropped with the review render that
        was its only reader (使用者裁定 2026-09-04): the judgment is made
        on the Chinese side, where the subtitle is the reference answer
        and both the judge and anyone calibrating it are strongest.

        `lang` is the formosan language code; the handshake switches the
        session's dropdown to its ethnicity first.
        """
        if not text.strip():
            return ""
        if direction != "f2z":
            raise PipelineError(
                "direction %r 無提供矣——干焦族語→華語（'f2z'）"
                % direction)
        if (direction, lang) not in self._ready:
            self._call("lambda", dialects.ethnicity_of(lang))
            self._ready.add((direction, lang))
        return self._call("translate", text, src_lang=lang)

    def translate_cached(self, cache, engine, direction, lang, text):
        if not text.strip():
            return ""
        hit = cache.get(engine, direction, lang, text)
        if hit is not None:
            return hit
        out = self.translate(direction, lang, text)
        cache.put(engine, direction, lang, text, out)
        return out
