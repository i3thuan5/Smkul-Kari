"""gradio.Client: the queue protocol shared by mtclient and sapolita.

Pins what was measured against sapolita's test instance 2026-09-18: the
result never arrives on `queue/join` (only an `event_id` does), the SSE
stream carries `estimation`/`process_starts`/several `heartbeat` events
before `process_completed`, and `success: false` on that event has no
separate message -- the whole event is the diagnostic.
"""
import json
import tempfile
import unittest
import urllib.error

from scripts.asrmt import gradio
from scripts.errors import PipelineError
from tests.asrmt import fixtures


class TestCall(unittest.TestCase):
    def test_reads_past_heartbeats_to_process_completed(self):
        opener = fixtures.FakeOpener(
            join=[fixtures.FakeResponse('{"event_id": "abc"}')],
            data=[fixtures.FakeResponse(fixtures.sse(
                {"msg": "estimation", "rank": 0, "queue_size": 1},
                {"msg": "process_starts"},
                {"msg": "heartbeat"},
                {"msg": "heartbeat"},
                {"msg": "heartbeat"},
                {"msg": "process_completed", "success": True,
                 "output": {"data": ["族語：hello\n華語：你好"]}},
            ))])
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener)
        data = client.call(1, 12, [{"video": "p"}, "ssf"])
        self.assertEqual(data, ["族語：hello\n華語：你好"])

    def test_success_false_raises_with_the_raw_event(self):
        opener = fixtures.FakeOpener(
            join=[fixtures.FakeResponse('{"event_id": "abc"}')],
            data=[fixtures.FakeResponse(fixtures.sse(
                {"msg": "process_completed", "success": False,
                 "output": None}))])
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener)
        with self.assertRaises(PipelineError) as caught:
            client.call(1, 12, [{"video": "p"}, "ssf"])
        message = str(caught.exception)
        self.assertIn("success", message.lower())
        self.assertIn("false", message.lower())

    def test_stream_ending_without_process_completed_is_an_error(self):
        opener = fixtures.FakeOpener(
            join=[fixtures.FakeResponse('{"event_id": "abc"}')],
            data=[fixtures.FakeResponse(fixtures.sse(
                {"msg": "estimation"}, {"msg": "heartbeat"}))])
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener)
        with self.assertRaises(PipelineError):
            client.call(1, 12, [])

    def test_join_without_an_event_id_is_an_error(self):
        opener = fixtures.FakeOpener(
            join=[fixtures.FakeResponse('{"error": "not selected"}')])
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener)
        with self.assertRaises(PipelineError):
            client.call(0, 8, ["邵語 (Thau)"])


class TestRetry(unittest.TestCase):
    def _client(self, join):
        sleeps = []
        opener = fixtures.FakeOpener(
            join=join,
            data=[fixtures.FakeResponse(fixtures.sse(
                {"msg": "process_completed", "success": True,
                 "output": {"data": ["ok"]}}))])
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener,
                               sleep=sleeps.append)
        return client, sleeps

    def test_retryable_gateway_codes_are_retried_then_succeed(self):
        for code in (502, 503, 504, 529):
            with self.subTest(code=code):
                client, sleeps = self._client(join=[
                    urllib.error.HTTPError("u", code, "gw", {}, None),
                    fixtures.FakeResponse('{"event_id": "abc"}')])
                data = client.call(1, 12, [])
                self.assertEqual(data, ["ok"])
                self.assertTrue(sleeps)

    def test_a_non_retryable_status_is_raised_immediately(self):
        client, sleeps = self._client(join=[
            urllib.error.HTTPError("u", 404, "not found", {}, None)])
        with self.assertRaises(urllib.error.HTTPError):
            client.call(1, 12, [])
        self.assertEqual(sleeps, [])

    def test_exhausting_retries_raises_a_pipeline_error(self):
        client, _sleeps = self._client(
            join=[urllib.error.HTTPError("u", 503, "gw", {}, None)] * 6)
        with self.assertRaises(PipelineError):
            client.call(1, 12, [])


class TestUpload(unittest.TestCase):
    def test_uploads_a_chinese_filename_and_returns_the_server_path(self):
        with tempfile.NamedTemporaryFile(
                suffix="_晨間_Thau_邵.mp3", delete=False) as handle:
            handle.write(b"fake-mp3-bytes")
            local = handle.name
        opener = fixtures.FakeOpener(
            upload=[fixtures.FakeResponse(
                json.dumps(["/tmp/gradio/abc123/邵.mp3"]))])
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener)
        got = client.upload(local)
        self.assertEqual(got, "/tmp/gradio/abc123/邵.mp3")

        url, body, headers, _timeout = opener.requests[0]
        self.assertTrue(url.endswith("/upload"))
        self.assertIn(b"fake-mp3-bytes", body)
        self.assertIn("邵.mp3".encode("utf-8"), body)
        content_type = headers.get("Content-type", headers.get(
            "Content-Type", ""))
        self.assertIn("multipart/form-data", content_type)

    def test_an_empty_reply_is_an_error(self):
        opener = fixtures.FakeOpener(
            upload=[fixtures.FakeResponse("[]")])
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"x")
            local = handle.name
        client = gradio.Client("https://x/sapolita", "sess1", opener=opener)
        with self.assertRaises(PipelineError):
            client.upload(local)


if __name__ == "__main__":
    unittest.main()
