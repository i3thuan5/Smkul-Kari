"""modeleval.mtboth：翻譯服務兩個方向的握手、參數順序、快取續跑。

`scripts.asrmt.mtclient` 刁工只做族→華（使用者裁定 2026-09-04），
這支是評測專用，兩個方向攏做；佮伊共用 `MTCache`。
"""
import tempfile
import unittest

from scripts.asrmt import mtclient
from scripts.modeleval import mtboth


class FakeGradio(object):
    """Records (fn_index, trigger_id, data); translate echoes the payload."""

    def __init__(self):
        self.calls = []

    def call(self, fn_index, trigger_id, data, timeout=180):
        self.calls.append((fn_index, trigger_id, data))
        if fn_index in (mtboth.FN["to_zh_languages"],
                        mtboth.FN["to_formosan_languages"]):
            return [{"value": "ok"}]
        return ["<%s>" % "|".join(data)]


def make():
    fake = FakeGradio()
    sleeps = []
    client = mtboth.Client(gradio_client=fake, pause=1.0,
                           sleep=sleeps.append)
    return client, fake, sleeps


class TestDirections(unittest.TestCase):
    def test_z2f_primes_the_formosan_dropdown_and_puts_zh_as_source(self):
        """華→族 `translate_1` 的參數順序是 [原文, zho_Hant, 族語碼]，
        佮族→華 [原文, 族語碼, zho_Hant] 相反；握手愛揀第二組下拉選單
        （to_formosan_languages，trigger 17），毋是族→華彼組（7）。"""
        client, fake, _ = make()
        out = client.translate("z2f", "ami_Xiug", "大家好")
        self.assertEqual(fake.calls[0], (2, 17, ["阿美"]))
        self.assertEqual(fake.calls[1],
                         (4, 20, ["大家好", "zho_Hant", "ami_Xiug"]))
        self.assertEqual(out, "<大家好|zho_Hant|ami_Xiug>")

    def test_f2z_uses_the_first_dropdown(self):
        client, fake, _ = make()
        client.translate("f2z", "ami_Sout", "nga'ay ho")
        self.assertEqual(fake.calls[0], (0, 7, ["阿美"]))
        self.assertEqual(fake.calls[1],
                         (1, 11, ["nga'ay ho", "ami_Sout", "zho_Hant"]))

    def test_each_direction_and_code_is_primed_once(self):
        """未握手就送非預設碼，服務袂報錯、會用海岸翻——所以兩個方向
        各自、每個碼攏愛先握手；握過的毋免重握。"""
        client, fake, _ = make()
        client.translate("z2f", "ami_Xiug", "一")
        client.translate("z2f", "ami_Xiug", "二")
        client.translate("f2z", "ami_Xiug", "cecay")
        client.translate("z2f", "ami_Sout", "三")
        fns = []
        for fn, _trigger, _data in fake.calls:
            fns.append(fn)
        self.assertEqual(fns, [2, 4, 4, 0, 1, 2, 4])

    def test_a_pause_separates_calls(self):
        client, _, sleeps = make()
        client.translate("z2f", "ami_Xiug", "一")
        client.translate("z2f", "ami_Xiug", "二")
        self.assertEqual(sleeps, [1.0, 1.0])


class TestCache(unittest.TestCase):
    def test_cached_lines_are_never_resent(self):
        """一批要跑幾點鐘，中途斷去重跑，做過的句袂使閣問服務一擺。"""
        with tempfile.TemporaryDirectory() as folder:
            cache = mtclient.MTCache(folder)
            client, fake, _ = make()
            client.translate_cached(cache, "z2f", "ami_Xiug", "大家好")
            again = mtclient.MTCache(folder)
            client2, fake2, _ = make()
            out = client2.translate_cached(again, "z2f", "ami_Xiug",
                                           "大家好")
            self.assertEqual(out, "<大家好|zho_Hant|ami_Xiug>")
            self.assertEqual(fake2.calls, [])
            self.assertEqual(len(fake.calls), 2)


if __name__ == "__main__":
    unittest.main()
