# tests/lexicon/：官方族語辭典（spec × scenario × 測試檔）

`scripts/lexicon/`：原語會 16 族官方族語辭典的讀取（xlsx）、切詞、逐族命中率與方言別正音。《開會了》的語言檢查與族語新聞的平行語料都用它，所以放頂層。原本在 `scripts/aiyalaeho/langcheck/`，內容沒改，只搬位置。

全部離線、fixture 合成：`fixtures.py` 會合成一個最小的 xlsx（字串放 sharedStrings、儲存格用 `t="s"` 指過去，跟真檔同一種寫法），不讀 50 MB 的真辭典。

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
| 方言別正音轉換只用於比對 | ★ 拿轉換後取代原樣，秀姑巒（辭典所收者）反而變差 | `test_vocab.py` |
| 方言別正音轉換只用於比對 | ★ 轉換套到所有阿美集，秀姑巒的命中率被灌水 | `test_vocab.py` |
| 方言別正音轉換只用於比對 | 轉換後的文字寫進 CSV 的 `族語列` 欄 | `test_vocab.py`（另見 `tests/aiyalaeho/langcheck/test_report.py`） |
