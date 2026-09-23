#!/usr/bin/env python3
"""The gradio queue protocol, shared by every gradio app this repo talks to.

Two apps use this today -- the ai-labs translation service (`mtclient.py`)
and sapolita (`sapolita.py`, whisper 族語辨識) -- and both hit the same
quirks, measured against sapolita's test instance 2026-09-18:

- A session's language dropdown is primed by an earlier call in the *same*
  session; asking for a non-default code cold gets back `event: error`
  with no message at all.
- The result does not arrive with `queue/join` -- that call only returns
  an `event_id`. The real answer comes down a second request, a Server-
  Sent-Events stream at `queue/data`, and it is preceded by an
  `estimation`, a `process_starts` and several `heartbeat` events before
  `process_completed` shows up. A caller that stops at the first line
  never sees the result.
- `success: false` on `process_completed` carries no separate error
  message -- the whole event is the diagnostic, so it goes into the
  exception verbatim.

`Client.call` retries the gateway states a public service behind a proxy
actually throws (502/503/504/529); anything else is a bug, not a blip,
and is raised immediately.
"""
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid

from scripts.errors import PipelineError

# transient gateway states worth waiting out; anything else is a bug
RETRYABLE = (502, 503, 504, 529)
RETRY_WAITS = (5, 10, 20, 40, 80)


class Client(object):
    """One gradio session: upload a file, then call an endpoint.

    `opener` stands in for `urllib.request.urlopen` -- injectable so the
    protocol can be exercised against a script instead of a real socket
    (`tests/asrmt/test_gradio.py`). It is called as `opener(request,
    timeout=N)` and must behave like `urlopen`: a context manager whose
    `.read()` gives bytes and whose iteration gives lines.
    """

    def __init__(self, base_url, session_hash, opener=None, sleep=None):
        self.base = base_url.rstrip("/") + "/gradio_api"
        self.session = session_hash
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep or time.sleep

    def upload(self, path):
        """Upload a local file, returning the server-assigned path.

        The server's own path is handed back and used as-is downstream
        (as the `path` field of a gradio FileData) -- it is not rebuilt
        from the local file name, which the server is free to rewrite.
        """
        boundary = uuid.uuid4().hex
        filename = os.path.basename(path)
        content_type = (mimetypes.guess_type(filename)[0]
                        or "application/octet-stream")
        with open(path, "rb") as handle:
            content = handle.read()
        crlf = b"\r\n"
        body = crlf.join([
            b"--" + boundary.encode("ascii"),
            b'Content-Disposition: form-data; name="files"; filename="'
            + filename.encode("utf-8") + b'"',
            b"Content-Type: " + content_type.encode("ascii"),
            b"",
            content,
            b"--" + boundary.encode("ascii") + b"--",
            b"",
        ])
        content_type_header = "multipart/form-data; boundary=" + boundary
        req = urllib.request.Request(
            self.base + "/upload", data=body,
            headers={"Content-Type": content_type_header})
        with self._open(req, timeout=120) as resp:
            uploaded = json.loads(resp.read().decode("utf-8"))
        if not uploaded:
            raise PipelineError("upload 無回傳任何路徑：%s" % path)
        return uploaded[0]

    def call(self, fn_index, trigger_id, data, timeout=180):
        """Join the queue and read the stream, retrying transient failures."""
        last = None
        for wait in (0,) + RETRY_WAITS:
            if wait:
                self._sleep(wait)
            try:
                return self._once(fn_index, trigger_id, data, timeout)
            except urllib.error.HTTPError as err:
                if err.code not in RETRYABLE:
                    raise
                last = err
            except urllib.error.URLError as err:
                last = err
        raise PipelineError("service unreachable after retries: %s" % last)

    def _once(self, fn_index, trigger_id, data, timeout):
        body = json.dumps({
            "data": data,
            "fn_index": fn_index,
            "trigger_id": trigger_id,
            "session_hash": self.session,
            "event_data": None,
        }).encode("utf-8")
        join_req = urllib.request.Request(
            self.base + "/queue/join", data=body,
            headers={"Content-Type": "application/json"})
        with self._open(join_req, timeout=60) as resp:
            joined = resp.read().decode("utf-8")
        if "event_id" not in joined:
            raise PipelineError("queue/join failed: %s" % joined[:500])

        stream_req = urllib.request.Request(
            self.base + "/queue/data?session_hash=" + self.session)
        with self._open(stream_req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[len("data:"):])
                if event.get("msg") == "process_completed":
                    if not event.get("success", True):
                        raise PipelineError("service error: %s"
                                            % json.dumps(event)[:500])
                    output = event.get("output") or {}
                    return output.get("data") or []
        raise PipelineError("SSE stream ended without process_completed")
