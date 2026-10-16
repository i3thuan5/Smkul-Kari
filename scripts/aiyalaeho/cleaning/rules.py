"""a 項規則清洗：撇號、多餘空白、重複標點。

一條規則一步，每一步記下修改前後，對照表才能一處一列、看得出改了
哪裡。其餘字元原樣保留，尤其：

  冒號      是詞的一部分（'a'iyalaeho:、賽夏 kapayaka:i'、泰雅 abaw:），
            `kithann/規範/` 沒有把它當標點的規定，辭典也照收
  雙撇 "    是真的符號（085 "awsa'），讀字規範量測確認過
  ’ 夾空白  只換撇號、空白照一般規則縮成一個，**不併**——是不是同一個
            詞要看圖（apostrophe_gaps 列出來送判）
"""
import collections
import re

Step = collections.namedtuple("Step", "kind before after")
Gap = collections.namedtuple("Gap", "raw cleaned joined")

APOSTROPHE = "'"
CURLY = "’ʼ"

# ’ 後面接空白、再接字：087「mena’   u」、085「qu ’  san」。
GAP = re.compile(r"\S*[" + CURLY + r"] +\S+")


def _apostrophes(text):
    out = text
    for mark in CURLY:
        out = out.replace(mark, APOSTROPHE)
    return out


def _spaces(text):
    return re.sub(r" {2,}", " ", text)


def _punctuation(text):
    # 4 點以上縮成 3 點；剛好 3 點是正常刪節號（使用者同意 2026-10-15）。
    out = re.sub(r"\.{4,}", "...", text)
    return re.sub(r"([!?！？])\1+", r"\1", out)


RULES = (("撇號", _apostrophes), ("多餘空白", _spaces),
         ("重複標點", _punctuation))


def clean(text):
    """(清洗後, [Step…])。沒改到就是原字串加空 list。"""
    steps = []
    current = text
    for kind, rule in RULES:
        after = rule(current)
        if after != current:
            steps.append(Step(kind, current, after))
            current = after
    return current, steps


def apostrophe_gaps(text):
    """這一列裡「’ 後夾空白」的每一處：原樣、規則清洗後、併起來的寫法。"""
    out = []
    for match in GAP.finditer(text):
        raw = match.group(0)
        cleaned = clean(raw)[0]
        joined = re.sub(r"' +", "'", cleaned)
        out.append(Gap(raw, cleaned, joined))
    return out
