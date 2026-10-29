#!/usr/bin/env python3
"""翻譯服務（kari-seejiq-tnpusu-ai-hmjil）兩個方向的用戶端，評測專用。

`scripts.asrmt.mtclient` 刁工只做族→華（使用者裁定 2026-09-04，交付
流程用不著倒爿）；評測愛兩爿攏量，所以另外一支，快取共用 `MTCache`。

服務四個端點（2026-10-28 對 /config 的 dependencies 讀落來）：

    族→華  to_zh_languages (0, trigger 7)  translate   (1, trigger 11)
           [原文, 族語碼, zho_Hant]
    華→族  to_formosan_languages (2, 17)   translate_1 (4, trigger 20)
           [原文, zho_Hant, 族語碼]

兩組下拉選單是無仝的元件，各自愛握手；未握手送非預設碼袂報錯，會靜靜
用預設海岸翻。一擺一句、中間停一下——這是予族人用的公開服務。
"""
import time

from scripts.asrmt import dialects
from scripts.asrmt import gradio
from scripts.errors import PipelineError

ZH = "zho_Hant"
DEFAULT_SERVER = "https://ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil/"

FN = {"to_zh_languages": 0, "translate": 1,
      "to_formosan_languages": 2, "translate_1": 4}
TRIGGER = {"to_zh_languages": 7, "translate": 11,
           "to_formosan_languages": 17, "translate_1": 20}

HANDSHAKE = {"f2z": "to_zh_languages", "z2f": "to_formosan_languages"}
TRANSLATE = {"f2z": "translate", "z2f": "translate_1"}

ENGINE = "ailabs"


class Client(object):
    def __init__(self, base_url=DEFAULT_SERVER, gradio_client=None,
                 pause=1.0, sleep=time.sleep, session_hash=None):
        if gradio_client is None:
            gradio_client = gradio.Client(
                base_url, session_hash or "modeleval%d" % id(self))
        self.client = gradio_client
        self.pause = pause
        self.sleep = sleep
        self._ready = set()
        self._called_before = False

    def _call(self, endpoint, data):
        if self._called_before:
            self.sleep(self.pause)
        self._called_before = True
        return self.client.call(FN[endpoint], TRIGGER[endpoint], data)

    def translate(self, direction, lang, text):
        if direction not in TRANSLATE:
            raise PipelineError("direction %r 毋是 f2z／z2f" % direction)
        if not text.strip():
            return ""
        if (direction, lang) not in self._ready:
            self._call(HANDSHAKE[direction], [dialects.ethnicity_of(lang)])
            self._ready.add((direction, lang))
        if direction == "f2z":
            data = [text, lang, ZH]
        else:
            data = [text, ZH, lang]
        out = self._call(TRANSLATE[direction], data)
        first = out[0] if out else ""
        if not isinstance(first, str):
            raise PipelineError("翻譯服務回傳毋是文字：%r" % (out,))
        return first

    def translate_cached(self, cache, direction, lang, text):
        hit = cache.get(ENGINE, direction, lang, text)
        if hit is not None:
            return hit
        out = self.translate(direction, lang, text)
        cache.put(ENGINE, direction, lang, text, out)
        return out
