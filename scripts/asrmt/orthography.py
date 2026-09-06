#!/usr/bin/env python3
"""Make the machine translation's character forms match the corpus.

The service's output is mostly traditional, but not consistently: it
mixes in Japanese variants and a few simplified forms. Counted over the
whole cache (350,948 hanzi) against the broadcaster's own subtitles
(444,835 hanzi, an independent control produced by people typing for
this audience):

    pair        translation   broadcast
    裡／裏      2491／221     1197／2
    說／説      2264／4       1710／0
    讚／讃        56／8         13／0
    沒／没      1205／5       1098／0
    樣／样      1628／1       1391／0

The broadcaster is all but perfectly consistent; the model is not.
`説` and `讃` are Japanese glyph variants and `没`／`样` are simplified
-- none of the four is Taiwanese usage. `裏` is a legitimate older
traditional form, kept here as well because this corpus writes `裡`
everywhere else and a deliverable that mixes both reads as sloppy
rather than as a choice.

**This runs at render time, not on the cache.** The cache means "what
the service said", and rewriting it would stop it being that. The
delivered file is what a person reads, and it follows the corpus. The
byte-for-byte rebuild is unaffected -- normalising is part of the
render, so producing the file again gives the same bytes.

How to spot more: encode each hanzi as big5 and as gb2312. Neither
working means a variant or a Japanese form; only gb2312 working means a
simplified codepoint. Both buckets need a human's eye afterwards --
`祢` (a Christian honorific), `叁` (the formal numeral) and `噻` are all
absent from big5 and all perfectly good Taiwanese usage. The broadcast
subtitles are the control: a character the station printed is fine
whatever the codecs think.
"""

# 毋著ê字形 → 這个語料ê字形。一个方向爾爾，袂使做環。
FIXES = {
    "没": "沒",   # 簡體
    "样": "樣",   # 簡體
    "説": "說",   # 日文字形
    "讃": "讚",   # 日文字形
    "裏": "裡",   # 正體舊體，這个語料統一用「裡」
}


def normalise(text):
    """The same text in this corpus's character forms."""
    out = []
    for char in text:
        out.append(FIXES.get(char, char))
    return "".join(out)
