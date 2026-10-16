# tests/lexicon/：官方族語辭典（spec × scenario × 測試檔）

`scripts/lexicon/`：原語會 16 族官方族語辭典的讀取（xlsx）、切詞、逐族命中率與語言別正音；另有族語E樂園教材（分語別）與 ILRDF Kaldi 模型詞表的蒸餾。《開會了》的語言檢查與族語新聞的平行語料都用它，所以放頂層。原本在 `scripts/aiyalaeho/langcheck/`，內容沒改，只搬位置。

全部離線、fixture 合成：`fixtures.py` 會合成一棵縮小的 E樂園 解壓目錄、一份 words.txt，以及一個最小的 xlsx（字串放 sharedStrings、儲存格用 `t="s"` 指過去，跟真檔同一種寫法），不讀 50 MB 的真辭典。

scenario 寫「**會怎麼錯**」。標 ★ 的是實作或量測時真的踩到的。

| spec | scenario（會怎麼錯） | 測試檔 |
|---|---|---|
| 書寫系統依 Unicode 類別分類 | ★ 用 ASCII 範圍分類，`ʉ`（語料裡 737 次）、`ē`、`è` 被當成非拉丁字母 | `test_script.py` |
| 書寫系統依 Unicode 類別分類 | ★ 注音 `ㄅㄆㄇㄈ`（4 條族語列有）歸進漢字，整列誤判成夾華語 | `test_script.py` |
| 書寫系統依 Unicode 類別分類 | ★ 標點與數字計入，`1000 kamini ni 投資` 判成華語而不是夾華語 | `test_script.py` |
| 書寫系統依 Unicode 類別分類 | ★ 詞庫與字幕用不同的切詞法，命中率一起低下去，看起來像「辭典涵蓋不足」其實是尺不同 | `test_script.py` |
| 別族族語的判定依官方族語辭典 | xlsx 欄位靠位置取，欄序一變全錯 | `test_dictionary.py` |
| 別族族語的判定依官方族語辭典 | ★ 辭典的 `ʼ`（U+02BC）沒正規化成 `'`，跟字幕的喉塞音對不起來 | `test_dictionary.py` |
| 別族族語的判定依官方族語辭典 | ★ 只收 `單字` 欄不收 `例句原文`，涵蓋率掉一截 | `test_dictionary.py` |
| 別族族語的判定依官方族語辭典 | ★ 改用 lift 校正詞庫規模，詞庫最大的太魯閣反而永遠墊底，整集被打成無法確定 | `test_vocab.py` |
| 別族族語的判定依官方族語辭典 | 命中率相同時取的族語別隨執行變動，CSV 重建不出同樣的 byte | `test_vocab.py` |
| 別族族語的判定依官方族語辭典 | 只有一集的族語別被略過或標成查不動 | `test_vocab.py` |
| 語言別正音轉換只用於比對 | ★ 拿轉換後取代原樣，秀姑巒（辭典所收者）反而變差 | `test_vocab.py` |
| 語言別正音轉換只用於比對 | ★ 轉換套到所有阿美集，秀姑巒的命中率被灌水 | `test_vocab.py` |
| 語言別正音轉換只用於比對 | 轉換後的文字寫進 CSV 的 `族語列` 欄 | `test_vocab.py`（另見 `tests/aiyalaeho/langcheck/test_report.py`） |
| E樂園 依語別蒸餾詞表 | ★ 族語欄名十幾種寫法（`wordAb`、`sentenceAAb`、`lessonAB`、`con_AB1`、`Ab_1`、`article_ab`、`matchAAbA` 的 Ab 在中間），只認一種會漏掉大半篇 | `test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 用「欄名含 ch」認華語，`choiceOneAAb` 的 ch 是 choice，族語句被當華語丟掉 | `test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 句型篇 `languageId`（12，族）和 `dialectId`（38，語別）拿錯，卑南四個語別混成一個 | `test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 生活會話篇、閱讀書寫篇的語別只寫在資料夾名，XML 裡沒有 dialectId | `test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 文化篇單字表欄名是 `dialect_id`、`word_ab`；有族語欄卻找不到語別欄要指名中止，不可恬恬產生空表 | `test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ `sa / saya / misasa` 是三個異體，整串當一個詞就三個都對不上 | `test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 語言別編號表有 BOM、tab 縮排、第 12 號空白；「南勢阿美語」剝成「南勢」才查得到代號，「東排灣語」要整個名字查，「賽夏語」退 `xsy`，對不上的指名中止 | `test_klokah.py` |
| Kaldi 詞表只證明存在 | ★ `<eps>`、`<SIL>`、`<UNK>`、`#0`、`<s>`、`</s>` 混進詞表，`<UNK>` 讓所有沒見過的詞都變成見過 | `test_kaldi_words.py` |
| Kaldi 詞表只證明存在 | 快取沒有該模型時要指名模型與怎麼下載，不可產生空詞表 | `test_kaldi_words.py` |
