#!/usr/bin/env python3
"""一逝族語文字對逐族ê詞庫，看伊上倚佗一族。

判定「這逝敢是本集ê族語」ê全部憑據。詞庫來自官方族語辭典
（見 dictionary.py），毋是本語料家己——用語料家己ê時，干焦一集
ê族語（太魯閣、賽德克、魯凱、拉阿魯哇）無詞庫通用，布農佮卑南
閣會互相濫。改用辭典了後，量過ê三族整集判定 19/19 攏著。

**排名用詞庫命中率，無做規模校正。** 捌試過「命中率 ÷ 該族詞庫
佔全部ê比例」（lift），量了較䆀：整集判定 34/39，生ê命中率是
37/39。太魯閣詞庫 35565 詞、佔全部 18.9%，除落去就規个坐落尾，
123 彼集 696 條去予標 685 條。合成測試過、真實資料歹去——就是
repo 家己記過ê彼个教訓（judge_prompts/README v7）。

詞庫規模ê偏差是有，毋過予真訊號崁過去矣：排名排毋著彼兩集
（賽德克 vs 太魯閣、布農 vs 卑南）攏是語言學上真正相倚ê，毋是
規模造成ê。真正著擋雜訊ê是**門檻**（見 mark.py），毋是校正。

**方言別愛先正音。** 辭典一族干焦收一个方言別（阿美收秀姑巒）。
南勢阿美 `u→o`、`b→f`、`v→f` 了後才對，實測 112、113 各 +17pt
（42%→58%、44%→61%），秀姑巒佮別集 +0pt。

轉換是**加法毋是取代**：原樣抑是轉換後，任一个中就算中。取代ê
話，辭典家己收ê彼个方言別會變較䆀——`kako` 轉了變 `kaka`，辭典
無收。

轉換表干焦囥量過ê彼條。別族ê對應規則莫先臆，拄著才加。
"""

# 語言代號 → 正音轉換（照順序做）。使用者裁定 2026-09-09：南勢阿美
# u→o、b→f、v→f，然後對秀姑巒辭典。
FOLDS = {
    "ami-x-iams": (("u", "o"), ("b", "f"), ("v", "f")),
}


def fold(word, language_code):
    """照方言別正音。無彼條規則就原樣送轉去。"""
    rules = FOLDS.get(language_code or "")
    if not rules:
        return word
    out = word
    for source, target in rules:
        out = out.replace(source, target)
    return out


def scores(words, lexicons, language_code=None):
    """逐族ê**詞庫命中率**：這逝ê詞有幾成佇彼族ê詞庫內底。

    `words` 無改動——正音是比對ê時才做ê，輸出ê文字愛照原樣
    （仝 asr-bilingual-srt「辨識文字忠實輸出」彼條ê精神）。
    """
    out = {}
    for tribe in lexicons:
        out[tribe] = 0.0
    if not words:
        return out
    for tribe, lexicon in lexicons.items():
        hit = 0
        for word in words:
            if word in lexicon or fold(word, language_code) in lexicon:
                hit += 1
        out[tribe] = hit / len(words)
    return out


def best(words, lexicons, language_code=None):
    """(上倚彼族, 伊ê詞庫命中率)。攏無中就 (None, 0.0)。

    平分ê時揀名排頭前彼个，結果才會逐擺仝款（CSV 愛逐 byte 重
    建會著）。
    """
    rates = scores(words, lexicons, language_code)
    tribe = None
    top = 0.0
    for name in sorted(rates):
        if rates[name] > top:
            tribe = name
            top = rates[name]
    if tribe is None:
        return None, 0.0
    return tribe, top
