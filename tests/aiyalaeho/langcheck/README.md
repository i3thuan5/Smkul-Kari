# tests/aiyalaeho/langcheck/：spec × scenario × 測試檔

《開會了》交付 SRT 逐條的語言判定（`scripts/aiyalaeho/langcheck/`）。全部離線、fixture 合成——不讀 39 集真資料，也不讀辭典原始檔（`fixtures.py` 會合成一個最小的 xlsx）。

scenario 寫「**會怎麼錯**」，不是功能名。標 ★ 的是規劃或實作階段真的踩到或量到的。

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
| 別族族語的判定依官方族語辭典 | ★ 只載入「有集數的族語別」，沒有集數那幾族（鄒、邵、噶瑪蘭、撒奇萊雅、卡那卡那富）的話永遠標不出來 | `test_report.py`、`test_rebuild.py` |
| 方言別正音轉換只用於比對 | ★ 拿轉換後取代原樣，秀姑巒（辭典所收者）反而變差 | `test_vocab.py` |
| 方言別正音轉換只用於比對 | ★ 轉換套到所有阿美集，秀姑巒的命中率被灌水 | `test_vocab.py` |
| 方言別正音轉換只用於比對 | 轉換後的文字寫進 CSV 的 `族語列` 欄 | `test_vocab.py`、`test_report.py` |
| 逐條語言判定只讀交付 SRT | ★ 讀 `2-vision/` 自己數 cue 當條號，遇到合併的集（094 併掉 78 條）整批對歪 | `test_mark.py` |
| 逐條語言判定只讀交付 SRT | 起迄時間戳被當成真實切換點（實際含 0.5 秒留白），或只抄了開始時間 | `test_mark.py`、`test_report.py` |
| 這列的語言——四級的操作型定義 | 夾雜的標籤帶了族語別名稱（`卑南語夾華語`／`泰雅語夾華語`），每族一個寫法，篩不齊 | `test_mark.py`、`test_report.py` |
| 這列的語言——四級的操作型定義 | ★ 兩列裝反的條目判成 `華語`，明明有族語卻漏掉 | `test_mark.py` |
| 逐條語言標記 CSV | 純族語的列被略過，表不再是逐條完整的 | `test_report.py` |
| 這列的語言——四級的操作型定義 | 事實類的列（純族語／族語夾雜華語／華語）也填了疑似語言與命中率 | `test_mark.py` |
| 這列的語言——四級的操作型定義 | ★ 沒有詞數門檻，一兩個詞的短列命中率非 0 即 100，標出四千多條雜訊 | `test_mark.py` |
| 這列的語言——四級的操作型定義 | ★ 沒有差距門檻，賽德克對太魯閣只差 7%（同一語言的兩個方言）也被標出來 | `test_mark.py` |
| 逐條語言標記 CSV | 欄序或欄名與 spec 不符，或列沒依成果檔名＋字幕編號排序 | `test_report.py` |
| 逐條語言標記 CSV | 寫兩次得到不同的 byte（重建驗證會永遠失敗） | `test_report.py` |
| 逐集語言分布 CSV | ★ 四個計數欄之和不等於字幕條數 | `test_report.py` |
| 逐集語言分布 CSV | `smkul.csv` 有的集在分布表缺席 | `test_report.py` |
| 兩張 CSV 可離線逐 byte 重建 | 手改 CSV 後重建驗證仍然通過 | `test_rebuild.py` |
| 兩張 CSV 可離線逐 byte 重建 | ★ 拿 store 既有的交付 SRT 當輸入，上游換版下游沒跟驗不出來 | `test_rebuild.py` |
| aiyalaeho 語料的 store 結構 | 某集的族語別沒有詞庫，那集靜默全判成純族語或全判成別族 | `test_rebuild.py`、`test_report.py` |

`test_rebuild.py` 與 `test_paths.py` 在上一層（`tests/aiyalaeho/`），因為它們測的是整個語料的重建與版面，不只這一組。
