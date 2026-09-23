"""sapolita: language-code table, session priming, and error surfacing.

A fake gradio client stands in for the real one (the queue/SSE mechanics
are pinned in `test_gradio.py`); what this file pins is sapolita's own
logic -- which group a code selects, that the group is primed before
`generate_srt` in the same session, and what happens when the service
gives back nothing.
"""
import unittest

from scripts.asrmt import sapolita
from scripts.errors import PipelineError


class FakeGradioClient(object):
    """Enforces sapolita's own session rule: `generate_srt` for a code
    whose group was not the last one selected in *this* client fails the
    way the real service does -- no message, the stream just never
    reaches `process_completed` (`gradio.Client` turns that into a
    PipelineError on its own; the fake raises the same class directly).
    """

    def __init__(
            self,
            reply="1\n00:00:00,000 --> 00:00:01,000\n族語：a\n華語：b"):
        self.reply = reply
        self.calls = []
        self.uploaded = []
        self.selected_group = None

    def upload(self, path):
        self.uploaded.append(path)
        return "/tmp/gradio/fake/" + path.rsplit("/", 1)[-1]

    def call(self, fn_index, trigger_id, data, timeout=180):
        self.calls.append((fn_index, trigger_id, data, timeout))
        if fn_index == sapolita.FN["update_languages"]:
            self.selected_group = data[0]
            return [["ok", data[0]]]
        code = data[1]
        if self.selected_group != sapolita.GROUP_OF_CODE.get(code):
            raise PipelineError("event: error / data: null（族別未選）")
        return [self.reply]


class TestGroupOf(unittest.TestCase):
    def test_apostrophes_are_the_curly_kind_the_service_uses(self):
        # U+2019, not the ASCII "'" -- the service rejects the ASCII one.
        self.assertEqual(sapolita.GROUP_OF_CODE["ami-x-pswl"],
                         "阿美語 (’Amis)")
        self.assertEqual(sapolita.GROUP_OF_CODE["sxr"],
                         "拉阿魯哇語 (Hla’alua)")
        self.assertNotIn("阿美語 ('Amis)", sapolita.GROUP_OF_CODE.values())

    def test_seediq_and_truku_do_not_share_a_group_despite_the_prefix(self):
        self.assertEqual(sapolita.group_of("trv-x-tgdy"),
                         "賽德克語 (Seediq/Seejiq/Sediq)")
        self.assertEqual(sapolita.group_of("trv-x-truku"),
                         "太魯閣語 (Truku)")

    def test_a_code_outside_the_table_is_refused_without_any_request(self):
        with self.assertRaises(PipelineError):
            sapolita.group_of("ami_Xiug")  # the translation service's code

    def test_the_table_has_all_sixteen_groups_and_fortytwo_codes(self):
        self.assertEqual(len(set(sapolita.GROUP_OF_CODE.values())), 16)
        self.assertEqual(len(sapolita.GROUP_OF_CODE), 42)


class TestRecognize(unittest.TestCase):
    def test_the_group_is_selected_before_generate_srt_in_one_session(self):
        client = FakeGradioClient()
        text = sapolita.recognize("https://x/sapolita", "/tmp/a.mp3",
                                  "ssf", client=client)
        self.assertIn("族語：a", text)
        kinds = []
        for call in client.calls:
            kinds.append(call[0])
        self.assertEqual(kinds, [sapolita.FN["update_languages"],
                                 sapolita.FN["generate_srt"]])
        self.assertEqual(client.calls[0][2], ["邵語 (Thau)"])

    def test_generate_srt_without_priming_the_session_fails(self):
        client = FakeGradioClient()
        # Skip the priming call a real caller always makes, to pin what
        # the service does when it is skipped.
        with self.assertRaises(PipelineError):
            client.call(
                sapolita.FN["generate_srt"],
                sapolita.TRIGGER["generate_srt"],
                [{"video": {"path": "x"}}, "ssf"])

    def test_an_empty_reply_names_the_code_and_the_file(self):
        client = FakeGradioClient(reply="")
        with self.assertRaises(PipelineError) as caught:
            sapolita.recognize("https://x/sapolita",
                               "/tmp/20210227_058_晨間_Thau_邵.mp3",
                               "ssf", client=client)
        message = str(caught.exception)
        self.assertIn("ssf", message)
        self.assertIn("20210227_058", message)

    def test_the_uploaded_path_not_the_local_one_goes_into_the_request(self):
        client = FakeGradioClient()
        sapolita.recognize("https://x/sapolita", "/tmp/a.mp3", "xsy",
                           client=client)
        _fn, _trigger, data, _timeout = client.calls[1]
        file_data = data[0]["video"]
        self.assertEqual(file_data["path"], "/tmp/gradio/fake/a.mp3")
        self.assertEqual(file_data["orig_name"], "a.mp3")
        self.assertEqual(data[1], "xsy")


if __name__ == "__main__":
    unittest.main()
