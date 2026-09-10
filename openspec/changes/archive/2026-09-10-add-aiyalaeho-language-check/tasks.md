## 1. 路徑與骨架

- [x] 1.1 先寫 `tests/aiyalaeho/test_paths.py` 的新 scenario（紅）：`4-語言檢查/` 三個位置由 `paths` 給出，store 版面缺詞庫目錄時指名失敗
- [x] 1.2 `scripts/aiyalaeho/paths.py` 加 `LANGCHECK_STORE`、`LEXICON_DIR`、`LANGCHECK_MARKS`、`LANGCHECK_DIST`、辭典遠端目錄常數（綠）
- [x] 1.3 建 `scripts/aiyalaeho/langcheck/__init__.py` 與 `tests/aiyalaeho/langcheck/__init__.py`

## 2. 字元分類（script.py）

- [x] 2.1 寫 `tests/aiyalaeho/langcheck/test_script.py`（紅）：`ʉ`／`ē`／`è` 計為拉丁字母；`ㄅㄆㄇㄈ` 不計為漢字；標點與數字不計入任一類；`1000 kamini ni 投資` 判為「有拉丁也有漢字」
- [x] 2.2 實作 `script.py`：依 Unicode 一般類別與碼位範圍分出拉丁／漢字／注音（綠）

## 3. 辭典蒸餾（dictionary.py）

- [x] 3.1 寫 `tests/aiyalaeho/langcheck/test_dictionary.py`（紅）：用合成的最小 xlsx fixture——欄位靠表頭名稱定位（欄序打亂仍正確）、`ʼ` 與 `’` 正規化成 `'`、`單字`＋`詞根`＋`例句原文` 三欄都收（只收單字時詞數變少）、詞庫輸出一行一詞且排序穩定
- [x] 3.2 實作 `dictionary.py`：`zipfile`＋`xml.etree` 讀 xlsx（含 sharedStrings），蒸餾成詞庫 txt（綠）
- [x] 3.3 加 xlsx fixture 產生器到 `tests/aiyalaeho/langcheck/`（合成，不放真辭典）

## 4. 詞庫比對與正音轉換（vocab.py）

- [x] 4.1 寫 `tests/aiyalaeho/langcheck/test_vocab.py`（紅）：詞庫規模差 7 倍時最大者 SHALL NOT 因規模勝出；只有一集的族語別照常判定；南勢阿美 `u→o`／`b→f`／`v→f` 後命中率上升；原樣或轉換後任一命中即算（取代會讓辭典所收方言別變差）；轉換只按語言代號套用，不套到其他阿美集；轉換不改動輸出文字
- [x] 4.2 實作 `vocab.py`：詞庫載入、逐族命中率（含規模校正）、依語言代號查正音轉換表（綠）

## 5. 逐條標記（mark.py）

- [x] 5.1 寫 `tests/aiyalaeho/langcheck/test_mark.py`（紅）：只讀 `3-srt/`（fixture 只提供 SRT 與 smkul 列，不提供 cues／vision）；條號取自 SRT，含合併的 fixture 也對得上；族語列空白且華語列有字 → `無`；有拉丁有漢字 → `<族語>語夾華語`；全漢字無拉丁 → `華語`；純拉丁且本集族語為首 → 不輸出；純拉丁但別族為首 → `無法確定`＋`疑似語言`；事實類三種不填疑似語言與命中率
- [x] 5.2 實作 `mark.py`：解析交付 SRT、依 §2–§4 判定，產出逐條標記（綠）

## 6. 兩張 CSV（report.py）

- [x] 6.1 寫 `tests/aiyalaeho/langcheck/test_report.py`（紅）：逐條 CSV 九欄的欄名與順序、列依成果檔名＋字幕編號排序、`開始時間` 等於 SRT 時間戳（含留白）、`族語列` 與 SRT 逐字相同；逐集 CSV 五個計數欄之和等於字幕條數、`smkul.csv` 每一集都有一列
- [x] 6.2 實作 `report.py`：兩張 CSV 的產出與 CLI 進入點（綠）

## 7. 離線重建

- [x] 7.1 寫 `tests/aiyalaeho/test_rebuild.py` 的新 scenario（紅）：手改 CSV 任一格後驗證以非零狀態結束並指名該檔；重建以**重建出來的**交付 SRT 為輸入（上游換版下游沒跟要驗得出來）；詞庫缺任一族時指名失敗、不靜默跳過
- [x] 7.2 `scripts/aiyalaeho/rebuild.py` 把兩張 CSV 納入重建與逐 byte 比對（綠）

## 8. 取辭典、產詞庫

- [x] 8.1 從 SFTP 取 16 個辭典 xlsx 到工作區（`scripts/news/sftp.sh get`，逐檔）
- [x] 8.2 跑 `dictionary.py` 產出 `4-語言檢查/詞庫/<族語>.txt` × 16，人工抽看兩三個檔確認是一行一詞的族語
- [x] 8.3 核對每個族語別都有詞庫檔，且 `smkul.csv` 出現過的族語別全部涵蓋

## 9. 產出與文件

- [x] 9.1 跑 `report.py` 產出兩張 CSV
- [x] 9.2 寫 `Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/README.md`：這層是什麼、從哪來、誰讀它；命中率不可跨集比較的理由；`無法確定` 是候選不是判決；詞庫來源、蒸餾方式與採購稽核結論
- [x] 9.3 `Kari-SRT/aiyalaeho/1-ocr/README.md` 流程圖與輸出入對照表補 `4-語言檢查/`
- [x] 9.4 `Kari-SRT/README.md` 結構圖補該目錄
- [x] 9.5 `tests/README.md` 加一行指到 `tests/aiyalaeho/langcheck/README.md`
- [x] 9.6 寫 `tests/aiyalaeho/langcheck/README.md`：spec × scenario × 測試檔對照表（照 design 那張）

## 10. 驗收

- [x] 10.1 `.tox/flake8/bin/flake8 . --count` 為 0
- [x] 10.2 `.tox/unittest/bin/python -m unittest discover -s tests/aiyalaeho -t .` 全綠，其餘測試組不退步
- [x] 10.3 `.tox/rebuild/bin/python -m scripts.aiyalaeho.rebuild --verify` 通過，且涵蓋兩張 CSV
- [x] 10.4 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify` 仍通過（族語新聞不受影響）
- [x] 10.5 `python3 -m scripts.news.name_catalogue --check` 無不合
- [x] 10.6 抽驗 068 與 082：兩集在逐條 CSV 的條目數與 explore 階段量到的分布一致（068 空白 69、夾漢字 48；082 空白 171、夾漢字 106）
