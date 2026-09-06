#!/usr/bin/env python3
"""Which language code the translation service should be asked for.

One static table, keyed by the inventory's 族語別(英). It used to be
detected per episode -- fifty lines translated under each of the five
Amis codes, best score wins -- and the pilot measured all five as a tie
(mean content score 0.063 across the board). So the detection was 250
requests to a public service in exchange for a coin flip, and it is gone.

Where the codes come from: the service's own two dropdowns, read on
2026-09-05. The 族別 one is fixed at sixteen; the 語別 one is repopulated
by a handshake call for whichever 族別 is chosen, so the full list is one
handshake per ethnicity. They are not derivable and not guessable -- ask
for a code the service does not know and it does not complain, it
translates with something else.

**賽德克's codes begin with `trv_`** (trv_Delu, trv_Duda, trv_Tegu), the
same prefix as 太魯閣 (trv_Truk). Reading the ethnicity off the prefix --
which is what the client used to do -- sends Seediq to the Truku
dropdown, whose only code is trv_Truk. Hence `ethnicity_of` is a lookup
in the table below, not a prefix rule.

Multi-dialect ethnicities take the service's own default, which is what
a person using the app gets. Amis is the exception: it takes ami_Xiug
(秀姑巒) because the pilot episode's 706 translated lines are cached
under that key and the five are of equal quality -- changing it would
throw the cache away for nothing.
"""
from scripts.errors import PipelineError

# code -> 服務ê族別選單值。2026-09-05 對服務ê下拉選單抄
# 落來（16 族、42 个碼）。
SERVICE_LANGS = {
    "ami_Coas": "阿美",
    "ami_Heng": "阿美",
    "ami_Mala": "阿美",
    "ami_Sout": "阿美",
    "ami_Xiug": "阿美",
    "bnn_Junq": "布農",
    "bnn_Kaqu": "布農",
    "bnn_Luan": "布農",
    "bnn_Tanq": "布農",
    "bnn_Zhuo": "布農",
    "ckv_Kava": "噶瑪蘭",
    "dru_Dawu": "魯凱",
    "dru_Dona": "魯凱",
    "dru_East": "魯凱",
    "dru_Maol": "魯凱",
    "dru_Wans": "魯凱",
    "dru_Wuta": "魯凱",
    "pwn_Cent": "排灣",
    "pwn_East": "排灣",
    "pwn_Nrth": "排灣",
    "pwn_Sout": "排灣",
    "pyu_Jian": "卑南",
    "pyu_Nanw": "卑南",
    "pyu_Xiqu": "卑南",
    "pyu_Zhib": "卑南",
    "ssf_Thao": "邵",
    "sxr_Saar": "拉阿魯哇",
    "szy_Saki": "撒奇萊雅",
    "tao_Yami": "雅美",
    "tay_Four": "泰雅",
    "tay_Seko": "泰雅",
    "tay_Wand": "泰雅",
    "tay_Wens": "泰雅",
    "tay_Yzea": "泰雅",
    "tay_Zeao": "泰雅",
    "trv_Delu": "賽德克",
    "trv_Duda": "賽德克",
    "trv_Tegu": "賽德克",
    "trv_Truk": "太魯閣",
    "tsu_Tsou": "鄒",
    "xnb_Kana": "卡那卡那富",
    "xsy_Sais": "賽夏",
}

CHOSEN = {
    "Amis": "ami_Xiug",
    "Atayal": "tay_Four",
    "Bunun": "bnn_Junq",
    "Cou": "tsu_Tsou",
    "Hla'alua": "sxr_Saar",
    "Kanakanavu": "xnb_Kana",
    "Kavalan": "ckv_Kava",
    "Paiwan": "pwn_Cent",
    "Pinuyumayan": "pyu_Jian",
    "Rukai": "dru_Dawu",
    "Sakizaya": "szy_Saki",
    "SaySiyat": "xsy_Sais",
    "Seediq": "trv_Delu",
    "Thau": "ssf_Thao",
    "Truku": "trv_Truk",
    "Yami": "tao_Yami",
}


def lang_of(ethnicity_en):
    """The service language code for this episode's ethnicity."""
    if ethnicity_en not in CHOSEN:
        raise PipelineError(
            "族語別 %r 無佇語言碼表內底——`scripts/asrmt/dialects.py` "
            "愛補一逝（碼愛對服務ê選單抄，袂使家己編）" % ethnicity_en)
    return CHOSEN[ethnicity_en]


def ethnicity_of(lang_code):
    """The 族別 dropdown value the handshake must select for this code."""
    if lang_code not in SERVICE_LANGS:
        raise PipelineError(
            "語言碼 %r 服務無提供——看 `dialects.SERVICE_LANGS`"
            % lang_code)
    return SERVICE_LANGS[lang_code]
