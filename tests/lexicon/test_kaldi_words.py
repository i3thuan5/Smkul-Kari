"""ILRDF Kaldi 族語模型的詞表 → 族語詞表。

只拿來標「這族有人這樣寫」：模型詞表收了多個語言別（082 阿美的覆蓋率
從辭典的 60% 升到 81%），但沒有標語別，也可能有訓練語料自己的錯字，
所以不拿來決定建議寫法。
"""
import os
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.lexicon import kaldi_words
from tests.lexicon import fixtures


def fake_cache(root, model="ILRDF/kaldi_formosan_250514_Puyuma"):
    org, name = model.split("/")
    path = os.path.join(root, "models--%s--%s" % (org, name), "snapshots",
                        "abc123", "graph", "words.txt")
    return fixtures.write_text(path, fixtures.KALDI_WORDS)


class TestWords(unittest.TestCase):
    def setUp(self):
        self.path = fake_cache(tempfile.mkdtemp(prefix="kaldi-"))

    def test_model_symbols_are_not_words(self):
        # <UNK> 混進詞表，所有沒見過的詞都變成「見過」。
        words = kaldi_words.words_of(self.path)
        for symbol in ("<eps>", "<sil>", "<unk>", "#0", "<s>", "</s>",
                       "eps", "sil", "unk"):
            self.assertNotIn(symbol, words)

    def test_real_words_are_kept_normalised(self):
        words = kaldi_words.words_of(self.path)
        self.assertEqual(words, {"garem", "harem", "mena'u", "likavung"})


class TestFind(unittest.TestCase):
    def test_finds_the_snapshot_by_model_id(self):
        root = tempfile.mkdtemp(prefix="kaldi-")
        path = fake_cache(root)
        self.assertEqual(
            kaldi_words.find("ILRDF/kaldi_formosan_250514_Puyuma", root),
            path)

    def test_missing_model_names_the_model(self):
        root = tempfile.mkdtemp(prefix="kaldi-")
        with self.assertRaises(PipelineError) as caught:
            kaldi_words.find("ILRDF/kaldi_formosan_250514_Amis", root)
        self.assertIn("kaldi_formosan_250514_Amis", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
