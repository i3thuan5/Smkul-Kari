#!/usr/bin/env python3
"""sapolita client: one audio file plus a 語言別代號, in; a SRT, out.

sapolita is ILRDF's whisper 族語辨識 Gradio app. It has three endpoints
(`update_languages`, `generate_srt`, `export_srt` -- the last one only
packages the textbox into a downloadable file, so this module never
calls it) and a language dropdown scoped to the session: asking
`generate_srt` for a non-default code before selecting its 族別 gets
`event: error` on the SSE stream with no message at all (measured
2026-09-18 against the test instance). So every call here opens a fresh
`gradio.Client` and always primes it with `update_languages` first.

The 16-族/42-碼 table below is transcribed from the app's own source
(`i3thuan5/Formosan-AI`, `asr/languages.py`, commit `04569de`,
2026-09-18) -- not retyped from the rendered page, which is how the
彎撇 (U+2019, not `'`) in group labels like 「阿美語 (’Amis)」 and
「拉阿魯哇語 (Hla’alua)」 stays exact. Guessing at a code the service
does not know does not raise; it silently falls back to something else
(dialects.py's docstring notes the same failure mode on the translation
service), so `group_of` refuses anything not in this table rather than
passing it through.
"""
import os
import uuid

from scripts.asrmt import gradio
from scripts.errors import PipelineError

# code -> 族別選單值。抄自 asr/languages.py 的 LANGUAGE_GROUPS。
GROUP_OF_CODE = {}


def _group(label, *codes):
    for code in codes:
        GROUP_OF_CODE[code] = label


_group(
    "阿美語 (’Amis)",
    "ami-x-iams", "ami-x-skl", "ami-x-pswl", "ami-x-frng", "ami-x-pld")
_group(
    "泰雅語 (Tayal)",
    "tay-x-sql", "tay-x-sul", "tay-x-cql", "tay-x-kls", "tay-x-mtuw",
    "tay-x-plngw")
_group(
    "排灣語 (Paiwan)",
    "pwn-x-kcdsn", "pwn-x-vnrn", "pwn-x-pnvn", "pwn-x-ynvl")
_group(
    "布農語 (Bunun)",
    "bnn-x-td", "bnn-x-bkh", "bnn-x-vtn", "bnn-x-bnz", "bnn-x-isbk")
_group(
    "卑南語 (Pinuyumayan)",
    "pyu-x-pym", "pyu-x-ktrp", "pyu-x-mkzy", "pyu-x-ksvk")
_group(
    "魯凱語 (Rukai)",
    "dru-x-trmk", "dru-x-ngdr", "dru-x-lbw", "dru-x-kgdv", "dru-x-tldr",
    "dru-x-opnh")
_group("鄒語 (Cou)", "tsu")
_group("賽夏語 (SaySiyat)", "xsy")
_group("雅美語 (Yami)", "tao")
_group("邵語 (Thau)", "ssf")
_group("噶瑪蘭語 (Kebalan)", "ckv")
_group("太魯閣語 (Truku)", "trv-x-truku")
_group("撒奇萊雅語 (Sakizaya)", "szy")
_group(
    "賽德克語 (Seediq/Seejiq/Sediq)",
    "trv-x-td", "trv-x-tgdy", "trv-x-trk")
_group("拉阿魯哇語 (Hla’alua)", "sxr")
_group("卡那卡那富語 (Kanakanavu)", "xnb")

# 三個端點的 fn_index／trigger_id（config 讀下的 dependencies，
# 2026-09-18）。export_srt 用不到，不收錄。
FN = {"update_languages": 0, "generate_srt": 1}
TRIGGER = {"update_languages": 8, "generate_srt": 12}

# 整集辨識要等的時間：測試機量到 116 秒（25 倍速），留給正式機與
# 長集數餘裕。
RECOGNIZE_TIMEOUT = 900


def group_of(code):
    """The 族別 dropdown value this 語言別代號 selects, or a refusal.

    Never guessed from the code's prefix: 賽德克 (trv-x-tgdy) and
    太魯閣 (trv-x-truku) share the `trv` prefix, and a prefix rule would
    send 賽德克 to 太魯閣's dropdown -- exactly the bug the translation
    service's `dialects.ethnicity_of` docstring already names.
    """
    if code not in GROUP_OF_CODE:
        raise PipelineError(
            "語言別代號 %r 毋捌是 sapolita ê選單值——愛先確定代號對，"
            "才通改 scripts/asrmt/sapolita.py ê表" % code)
    return GROUP_OF_CODE[code]


def _file_data(uploaded_path, orig_name):
    return {"video": {"path": uploaded_path,
                      "meta": {"_type": "gradio.FileData"},
                      "orig_name": orig_name}}


def recognize(base_url, audio_path, code, session_hash=None,
              timeout=RECOGNIZE_TIMEOUT, client=None):
    """One audio file, one 語言別代號, in; sapolita's raw SRT text, out.

    A fresh session every call (`session_hash` defaults to a new random
    one) -- the dropdown priming is per-session, and nothing here is
    meant to be reused across episodes the way `mtclient.MTClient` reuses
    a translation session across many lines.
    """
    group = group_of(code)
    if client is None:
        if session_hash is None:
            session_hash = "sapolita-%s" % uuid.uuid4().hex[:16]
        client = gradio.Client(base_url, session_hash)
    client.call(
        FN["update_languages"], TRIGGER["update_languages"], [group])
    uploaded = client.upload(audio_path)
    data = client.call(
        FN["generate_srt"], TRIGGER["generate_srt"],
        [_file_data(uploaded, os.path.basename(audio_path)), code],
        timeout=timeout)
    text = data[0] if data else ""
    if not text:
        raise PipelineError(
            "sapolita 無回傳文字（語別碼 %r，音檔 %s）" % (code, audio_path))
    return text
