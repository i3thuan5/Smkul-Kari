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
import urllib.error
import urllib.request
from scripts.errors import PipelineError

ZH = "zho_Hant"

# transient gateway states worth waiting out; anything else is a bug
RETRYABLE = (502, 503, 504, 529)
RETRY_WAITS = (5, 10, 20, 40, 80)

# language-code prefix -> the ethnicity label the service's lambda wants
ETHNICITY = {
    "ami": "阿美", "tay": "泰雅", "bnn": "布農", "xnb": "卡那卡那富",
    "ckv": "噶瑪蘭", "pwn": "排灣", "pyu": "卑南", "dru": "魯凱",
    "sxr": "拉阿魯哇", "xsy": "賽夏", "szy": "撒奇萊雅", "trv": "太魯閣",
    "ssf": "邵", "tsu": "鄒", "tao": "雅美", "sdq": "賽德克",
}


def ethnicity_of(lang_code):
    prefix = lang_code.split("_")[0]
    if prefix not in ETHNICITY:
        raise PipelineError("unknown language code %r (no ethnicity for %r)"
                            % (lang_code, prefix))
    return ETHNICITY[prefix]


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

    def put(self, engine, direction, src_lang, text, out):
        key = (engine, direction, src_lang, text)
        self.entries[key] = out
        path = os.path.join(self.folder, engine + ".jsonl")
        row = {"engine": engine, "direction": direction,
               "src_lang": src_lang, "text": text, "out": out}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class HttpTransport(object):
    """The real gradio queue protocol, single concurrency by construction.

    Kept in one place: `call(endpoint, text)` joins the queue and reads
    the SSE stream until the result arrives. Failures carry the raw
    response so a protocol change is diagnosable.
    """

    FN = {"lambda": 0, "translate": 1, "lambda_1": 2, "translate_1": 3}
    TRIGGER = {"lambda": 7, "translate": 11, "lambda_1": 17,
               "translate_1": 21}

    def __init__(self, base_url, session_hash):
        self.base = base_url.rstrip("/") + "/gradio_api"
        self.session = session_hash

    def _payload(self, endpoint, text, src_lang, tgt_lang):
        if endpoint == "lambda" or endpoint == "lambda_1":
            return [text]
        if endpoint == "translate":
            return [text, src_lang, ZH]
        return [text, ZH, tgt_lang]

    def call_full(self, endpoint, text, src_lang="", tgt_lang=""):
        """Retry transient gateway failures, then give up loudly."""
        last = None
        for wait in (0,) + RETRY_WAITS:
            if wait:
                time.sleep(wait)
            try:
                return self._once(endpoint, text, src_lang, tgt_lang)
            except urllib.error.HTTPError as err:
                if err.code not in RETRYABLE:
                    raise
                last = err
            except urllib.error.URLError as err:
                last = err
        raise PipelineError("service unreachable after retries: %s" % last)

    def _once(self, endpoint, text, src_lang="", tgt_lang=""):
        body = json.dumps({
            "data": self._payload(endpoint, text, src_lang, tgt_lang),
            "fn_index": self.FN[endpoint],
            "trigger_id": self.TRIGGER[endpoint],
            "session_hash": self.session,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base + "/queue/join", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            joined = resp.read().decode("utf-8")
        if "event_id" not in joined:
            raise PipelineError("queue/join failed: %s" % joined[:500])

        stream = urllib.request.Request(
            self.base + "/queue/data?session_hash=" + self.session)
        with urllib.request.urlopen(stream, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[len("data:"):])
                if event.get("msg") == "process_completed":
                    output = event.get("output") or {}
                    if not event.get("success", True):
                        raise PipelineError("service error: %s"
                                            % json.dumps(event)[:500])
                    data = output.get("data") or [""]
                    first = data[0]
                    if isinstance(first, str):
                        return first
                    return json.dumps(first, ensure_ascii=False)
        raise PipelineError("SSE stream ended without process_completed")


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

    def _call(self, endpoint, text, src_lang="", tgt_lang=""):
        if self._called_before:
            self.sleep(self.pause)
        self._called_before = True
        if hasattr(self.transport, "call_full"):
            return self.transport.call_full(endpoint, text,
                                            src_lang, tgt_lang)
        return self.transport.call(endpoint, text)

    def translate(self, direction, lang, text):
        """direction: 'f2z' (formosan->zho_Hant) or 'z2f' (the reverse).

        `lang` is always the formosan language code; the handshake
        switches the session's dropdown to its ethnicity first.
        """
        if not text.strip():
            return ""
        if direction == "f2z":
            handshake, endpoint = "lambda", "translate"
        elif direction == "z2f":
            handshake, endpoint = "lambda_1", "translate_1"
        else:
            raise PipelineError("unknown direction %r" % direction)
        if (direction, lang) not in self._ready:
            self._call(handshake, ethnicity_of(lang))
            self._ready.add((direction, lang))
        if direction == "f2z":
            return self._call(endpoint, text, src_lang=lang)
        return self._call(endpoint, text, tgt_lang=lang)

    def translate_cached(self, cache, engine, direction, lang, text):
        if not text.strip():
            return ""
        hit = cache.get(engine, direction, lang, text)
        if hit is not None:
            return hit
        out = self.translate(direction, lang, text)
        cache.put(engine, direction, lang, text, out)
        return out
