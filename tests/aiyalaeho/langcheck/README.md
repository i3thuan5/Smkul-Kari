# tests/aiyalaeho/langcheck/：spec × scenario × 測試檔

《開會了》交付 SRT 逐條的語言判定（`scripts/aiyalaeho/langcheck/`）。全部離線、fixture 合成，不讀 39 集真資料。

辭典本身（讀 xlsx、切詞、命中率）搬到頂層 `scripts/lexicon/` 了，那幾列測試跟著搬到 [tests/lexicon/](../../lexicon/README.md)，因為族語新聞的平行語料也用同一套辭典。

scenario 寫「**會怎麼錯**」，不是功能名。標 ★ 的是規劃或實作階段真的踩到或量到的。

| spec | scenario（會怎麼錯） | 測試檔 |
|---|---|---|
| 別族族語的判定依官方族語辭典 | ★ 只載入「有集數的族語別」，沒有集數那幾族（鄒、邵、噶瑪蘭、撒奇萊雅、卡那卡那富）的話永遠標不出來 | `test_report.py`、`test_rebuild.py` |
| 方言別正音轉換只用於比對 | 轉換後的文字寫進 CSV 的 `族語列` 欄 | `test_report.py`（辭典那一半在 `tests/lexicon/test_vocab.py`） |
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
