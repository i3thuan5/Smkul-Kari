#!/usr/bin/env python3
"""ILRDF Kaldi 族語模型的詞表 → 族語詞表（一行一詞的 txt）。

模型在 huggingface 快取：
`~/.cache/huggingface/hub/models--ILRDF--kaldi_formosan_250514_<族>/
snapshots/<hash>/graph/words.txt`，一行「詞 編號」。

**只證明「這族有人這樣寫」**：詞表收了多個語言別（082 阿美的覆蓋率從
辭典的 60% 升到 81%），但沒有標語別，而且來自訓練語料，可能帶著語料
本身的錯字。所以拿來把「辭典查無」再分成「族語其他寫法見過」和
「完全查無」，不拿來決定建議寫法。

前後幾行是模型用的符號（<eps>、<SIL>、<UNK>、#0、<s>、</s>），
不是詞——<UNK> 混進來，所有沒見過的詞都會變成「見過」。
"""
import glob
import os

from scripts.errors import PipelineError
from scripts.lexicon import script

HF_HUB = os.path.expanduser("~/.cache/huggingface/hub")


def _is_symbol(token):
    return token.startswith("<") or token.startswith("#")


def words_of(path):
    """words.txt → set(詞)。切詞跟字幕、辭典同一把尺。"""
    out = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            fields = line.split()
            if not fields or _is_symbol(fields[0]):
                continue
            out.update(script.words(fields[0]))
    return out


def find(model_id, cache=HF_HUB):
    """模型 id（`ILRDF/kaldi_formosan_250514_Puyuma`）→ words.txt 路徑。

    快取有好幾個 snapshot 時取最新改的那個。找不到就指名模型，
    說去哪裡拿——這支不負責下載。
    """
    org, _, name = model_id.partition("/")
    pattern = os.path.join(cache, "models--%s--%s" % (org, name),
                           "snapshots", "*", "graph", "words.txt")
    found = glob.glob(pattern)
    if not found:
        raise PipelineError(
            "huggingface 快取裡沒有 %s 的詞表（%s）；請先下載該模型，"
            "例如 huggingface_hub.snapshot_download(%r)"
            % (model_id, pattern, model_id))
    return max(found, key=os.path.getmtime)
