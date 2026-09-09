"""集的來源目錄名稱 → `語言別代號`。

有確定語言別就用語言別，不知道就用族語別——這條規則記在 CLAUDE.md
（〈CSV 的「語言別代號」欄位〉），任何 CSV 要標語言都照這個做。

**重用既有的表，不另造一份。** `scripts.aiyalaeho.catalogue` 的
`LANGUAGES`（族語別 → 英文拼法、ISO 639 代號）與 `VARIETIES`（族語別 →
{語言別用字: 代號}）已經是 `kithann/規範/族語及語言別名稱 - *名稱.csv`
抄進程式碼的正本，換機器不會不見。這裡直接拿目錄名稱去跟這兩份表的
用字比對子字串：語言別優先，退到族語別；規範改了，兩邊一起改一起跑
測試就好，不用維護第二份表。

驗證過：41 個真實目錄名稱裡，40 個這樣比對就唯一解得出代號，沒有任何
一個撞出兩個不同的代號（見 `tests/aiyalaeho/text/test_lang.py`）。剩
`開會036-東布青` 目錄名稱三個字都不在任一個規範用詞裡，靠讀轉出來的
文字才知道——見下面 `OVERRIDES`。

**連族語別都查不出來、或一份資料混了大量不同的族語選不出代表時**，
代號落到 ISO 639-2／639-3 的 `und`（undetermined）——這是標準本來就
有的答案，`catalogue.py` 的 116 集（無語言卡、無字幕，真的查不出來）
已經是這樣處理的先例，不是自己發明的代碼。`und` 一樣走 `OVERRIDES`
這個機制：先照規範表和內容證據去查，查不到才落到 `und`，而且要留下
「為什麼查不出來」的依據——不是 `resolve()` 自動退的預設值。
"""
from scripts.aiyalaeho.catalogue import LANGUAGES
from scripts.aiyalaeho.catalogue import VARIETIES
from scripts.errors import PipelineError

# 目錄名稱查不到任何族語別或語言別用字、只能靠內容判斷的例外。**只放
# 規則解不出來的**，不是給全部 41 集另建一張手工表——多一集要加進來，
# 先試 resolve() 解不解得出來，解不出來才進這裡。
#
# 開會036-東布青：轉出來的文字第一段就是
#     「itu Bunun tuza tu maza madadaingaz a makuuni maia maivahvah tu
#      tuhna tan」（布農族耆老拿著獸骨秉告祖靈）
# 逐字唸出「Bunun」；其餘語句用了 `uninang`（謝謝，跟 007 布農集同一個
# 詞）與 `is-` 開頭的氏族名（`isMahasan`、`isTanda`，布農氏族名慣用
# 前綴）。「東布青」應是「東部布農青年（會）」的縮寫。
OVERRIDES = {
    "開會036-東布青": "bnn",
}
OVERRIDE_EVIDENCE = {
    "開會036-東布青": (
        "轉出文字「itu Bunun tuza tu maza madadaingaz a makuuni maia "
        "maivahvah tu tuhna tan」逐字唸出 Bunun；另有 uninang（謝謝）與 "
        "is- 開頭的布農氏族名（isMahasan、isTanda）"
    ),
}


def resolve(folder_name):
    """folder_name（來源目錄名稱）→ 語言別代號或族語別代號。

    查不出來就中止並指名，不留空、不編一個規範表裡沒有的代號。
    """
    if folder_name in OVERRIDES:
        return OVERRIDES[folder_name]

    variety_hits = set()
    for table in VARIETIES.values():
        for word, code in table.items():
            if word and word in folder_name:
                variety_hits.add(code)
    if variety_hits:
        if len(variety_hits) > 1:
            raise PipelineError(
                "%r 同時符合規範表裡兩個以上不同的語言別：%s"
                % (folder_name, "、".join(sorted(variety_hits))))
        return next(iter(variety_hits))

    language_hits = set()
    for name, (_, code) in LANGUAGES.items():
        if name and name in folder_name:
            language_hits.add(code)
    if language_hits:
        if len(language_hits) > 1:
            raise PipelineError(
                "%r 同時符合規範表裡兩個以上不同的族語別：%s"
                % (folder_name, "、".join(sorted(language_hits))))
        return next(iter(language_hits))

    raise PipelineError(
        "%r 查不到任何規範表裡的族語別或語言別用字，也沒有 OVERRIDES 覆寫"
        "——需要先讀內容確認語言、再補進 OVERRIDES（附依據）" % folder_name)
