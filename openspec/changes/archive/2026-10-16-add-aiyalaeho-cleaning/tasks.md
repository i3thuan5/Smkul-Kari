## 1. 骨架與路徑

- [x] 1.1 建 `scripts/aiyalaeho/cleaning/__init__.py`、`tests/aiyalaeho/cleaning/__init__.py`
- [x] 1.2 寫 `tests/aiyalaeho/cleaning/test_paths.py`（紅）：各層路徑落在 `kithann/out/aiyalaeho-清洗/` 的 `1-詞庫`…`5-交付`；輸出目錄設在 `Kari-SRT/` 底下時中止並指名路徑、沒有建立任何檔案
- [x] 1.3 實作 `scripts/aiyalaeho/cleaning/paths.py`（綠）

## 2. E樂園 詞表（scripts/lexicon/klokah.py）

- [x] 2.1 `tests/lexicon/fixtures.py` 加合成 E樂園 的小工具：句子 CSV（`dialectId`／`sentenceAb`）、文化篇單字 CSV（`dialect_id`／`word_ab`）、句型篇 XML（`languageId`＋`dialectId`、`wordAb`、`choiceOneAAb`／`choiceOneACh`、`matchAAbA`）、生活會話篇與閱讀書寫篇 XML（語別只在資料夾名；`con_AB1`、`lessonAB`、`Ab_1`、`article_ab`）、語言別編號表（BOM、tab 縮排、空白的第 12 號）
- [x] 2.2 寫 `tests/lexicon/test_klokah.py`（紅）：十種族語欄名都收、華語欄都不收（含 `choiceOneACh`）；`languageId` 與 `dialectId` 不同時歸 `dialectId`；XML 沒有 dialectId 時取資料夾名；`sa / saya / misasa` 拆成三詞；「南勢阿美語」→ `ami-x-iams`、「宜蘭澤敖利泰雅語」→ `tay-x-kls`、「賽夏語」→ `xsy`，剝不出來的語別名指名中止；CSV 找不到語別欄指名中止；`’`／`ʼ` 正規化、大小寫不分；輸出一行一詞、排序固定
- [x] 2.3 實作 `scripts/lexicon/klokah.py`（綠），語言別代號經 `scripts/languages.py` 的 `VARIETIES`／`code_for()`
- [x] 2.4 `tests/lexicon/README.md` 對照表加 E樂園 那幾列

## 3. Kaldi 詞表（scripts/lexicon/kaldi_words.py）

- [x] 3.1 寫 `tests/lexicon/test_kaldi_words.py`（紅）：合成 words.txt，`<eps>`、`<SIL>`、`<UNK>`、`#0`、`<s>`、`</s>` 不進詞表；撇號正規化；快取路徑找不到時指名族語與該去哪裡下載
- [x] 3.2 實作 `scripts/lexicon/kaldi_words.py`（綠）
- [x] 3.3 `tests/lexicon/README.md` 加 Kaldi 詞表那一列

## 4. 讀交付 SRT 與圖條對應（source.py）

- [x] 4.1 寫 `tests/aiyalaeho/cleaning/fixtures.py`：合成 2～3 集的 `3-srt`、`1-cues`（圖條路徑寫舊名 `strips/`）、`2-vision`、`smkul.csv`、`2-strips/` 空白 png
- [x] 4.2 寫 `tests/aiyalaeho/cleaning/test_source.py`（紅）：逐條讀出字幕編號、時間、族語列、華語列（空列為空字串）；相鄰兩個同文字 cue 合成一條時，該字幕編號對到兩個 cue、兩張族語列圖條；cue 清單寫 `strips/…` 時解到 `2-strips/…`
- [x] 4.3 實作 `source.py`，重用 `make_srt.build`／`entries_from`、`srtlib.assemble.chain_with_spans`、`datadirs.strips_dir()`（綠）

## 5. a 項規則清洗（rules.py）

- [x] 5.1 寫 `tests/aiyalaeho/cleaning/test_rules.py`（紅）：冒號不動（`'a'iyalaeho:`、`kapayaka:i'`、`abaw:`）；`’`／`ʼ` → `'`；`mena’   u` 只換撇號、不併空白，且回報為看圖候選；雙撇 `"` 不動；族語、華語連續空白縮成一個；4 點以上刪節號縮成 3 點、3 點不動；華語 `!!`、`??` 縮成一個；空列清洗後仍空；每處修改回報類別（多餘空白、重複標點、撇號）
- [x] 5.2 實作 `rules.py`（綠）

## 6. 語言別推測（dialect.py）

- [x] 6.1 寫 `tests/aiyalaeho/cleaning/test_dialect.py`（紅）：合成詞表與字幕——已標語別的集照標記（即使只領先 3 點）；領先 ≥ 10 點且 ≥ 90% 段同判「高」；領先不足但 ≥ 70% 段同判「中」；段第一名交錯判「混合」；詞次少於 40 的段不算；賽夏直接 `xsy`；代號經 `code_for()`；回傳候選比對用的語別集合（高→一個、中→前兩名、混合→全部、已標記→標記者）
- [x] 6.2 實作 `dialect.py`（綠）

## 7. b、c 候選（candidates.py）

- [x] 7.1 寫 `tests/aiyalaeho/cleaning/test_candidates.py`（紅）：不套 `vocab.fold`（`kaku`／`kako` 是兩個詞形、互列相近寫法）；該集語別權威見過的不列錯字候選（`harem` 在西群 E樂園）；辭典語別與該集不同時看 E樂園；只差一個字母的只列相近、不判錯字；漢字、注音、數字不進候選；大小寫、`ʼ`／`'` 合併成同一詞形但保留原樣；布農不進候選；節目名錯拼跨族語合成一組、建議 `'a'iyalaeho:`；Kaldi 詞表見過的標「族語其他寫法見過」、不給建議；證據欄（集數次數、辭典、E樂園 語別、Kaldi、開會了全語料次數、上字文稿次數、最近似辭典詞條、相近寫法）齊全；依 design 決定四分出「送文字分類」的那些
- [x] 7.2 實作 `candidates.py`（綠），切詞用 `scripts/lexicon/script.words()`、辭典讀 `dictionary.load()`

## 8. Claude 判定的送出與匯入（verdicts.py）

- [x] 8.1 寫 `tests/aiyalaeho/cleaning/test_verdicts.py`（紅）：文字分類分批（每批上限 300；判定類批次照 2026-09-08 裁定「至少 200」）、每個詞形附最多 3 句上下文與證據；已有判定的不再送；匯入時漏列、多列、類別不在「錯字／語言別差異／不同詞／斷詞不同／不確定」、錯字沒建議寫法，都指名批號與詞形中止；看圖逐處送出、附該字幕編號全部 cue 的圖條路徑，圖條不存在指名集數與字幕編號中止；看圖類別只能「OCR 讀錯／播出端錯字／看不出來」
- [x] 8.2 實作 `verdicts.py`（綠）
- [x] 8.3 寫 `brief_text.md`（文字分類判準：五個類別的定義、語言別差異不算錯字、沒把握就標不確定、建議寫法照依據順序）與 `brief_image.md`（看圖判準：比對畫面與文字、分 OCR 讀錯與播出端錯字、`’` 夾空白判是否同一詞、看不清就標看不出來）

## 9. 清洗版與對照表（apply.py）

- [x] 9.1 寫 `tests/aiyalaeho/cleaning/test_apply.py`（紅）：清洗版與交付版逐行比，只有標籤後的文字不同；只套 a 項、看圖判 OCR 讀錯或播出端錯字者、看圖判同一詞的撇號夾空白、節目名統一；語言別差異、不同詞、斷詞不同、不確定、看不出來都不改；以詞為單位替換（`kakoay` 不受 `kako` 影響）、句首大寫保持；對照表一處一列、修改前後是整條該列文字
- [x] 9.2 實作 `apply.py`（綠）

## 10. 交付報表（report.py）

- [x] 10.1 寫 `tests/aiyalaeho/cleaning/test_report.py`（紅）：四份 CSV 的欄名與順序（含「語言別代號」）；處理方式只有四個值；建議寫法依順序（087 取西群 E樂園 而非南王辭典）、判語言別差異者空白且「待討論」；UTF-8 無 BOM、LF；重跑逐 byte 相同
- [x] 10.2 實作 `report.py`（綠），CSV 寫法沿用 `langcheck/report.py` 的 `write_table`

## 11. 命令列與文件

- [x] 11.1 實作 `__main__.py`：詞庫／候選／送判 文字|看圖／匯入 文字|看圖／清洗／報表，各步驟缺上一步產出時指名中止
- [x] 11.2 寫 `tests/aiyalaeho/cleaning/README.md`（本組 spec × scenario × 測試檔對照表，照 design），`tests/README.md` 總表加一行指過去
- [x] 11.3 `scripts/aiyalaeho/README.md` 加「清洗」一節：產出在 kithann/out、不進 Kari-SRT、步驟與指令、清洗版與交付版的差別

## 12. 驗收（程式）

- [x] 12.1 `tox -e flake8`、`tox -e unittest` 全綠；清 `__pycache__` 後再跑一次
- [x] 12.2 `tox -e rebuild`（`rebuild --verify` 通過，且集數＝inventory 未標 pending 的筆數），確認 Kari-SRT 未受影響；`python3 -m scripts.news.name_catalogue --check`

## 13. 實跑（產出在 kithann/out/aiyalaeho-清洗/）

- [x] 13.1 跑「詞庫」：16 個語別 E樂園 詞表、4 族 Kaldi 詞表；記各語別詞數
- [x] 13.2 跑「候選」：記各族候選數、送文字分類的數量、語言別推測結果，對照 design 的量測（085 高、086 高、084 中、087 中、082 混合）
- [x] 13.3 全部批次送文字分類（Opus subagent，平行數照當時規矩），不先試一批、不中途回報（使用者裁定 2026-10-15）
- [x] 13.4 文字分類全部匯入通過
- [x] 13.5 送看圖（Opus subagent），全部匯入通過
- [x] 13.6 跑「清洗」與「報表」；確認 `Kari-SRT/aiyalaeho/` 逐 byte 未變（13.1 開跑前先記下全部檔案的 sha256，這裡再算一次比對；不用 git status，因為平行 session 可能正在改 Kari-SRT 的其他地方）
- [x] 13.7 寫 `kithann/out/aiyalaeho-清洗/README.md`；寫 tuiue 回報：各表筆數、改了幾處（依類別）、待討論幾組、費用、建議下一步

## 14. 人工改判（使用者看過結果後追加，2026-10-15）

- [x] 14.1 寫 `test_report.py` 的人工改判測試（紅）：改判的錯字不產生 Fix；兩份表處理方式「待討論」、依據含「人工改判：理由」、文字分類保留原判；改判檔不存在視為沒有改判；`test_paths.py` 加 `3-判定/人工改判.csv` 位置
- [x] 14.2 實作 `verdicts.load_overrides`、`report` 各處接 overrides、`paths.Layout.overrides`、命令列讀檔（綠）
- [x] 14.3 寫 `3-判定/人工改判.csv`：阿美 odal、pisaodalan（082 可能是南勢寫法）；卑南 zalaw、kazuyu、pukatrelu、Tamalakaw（087 可能是西群寫法）、tatena（087#286 斷詞位置問題）；重跑清洗與報表

## 15. 用詞：「方言」改「語言別」（使用者裁定 2026-10-16）

- [x] 15.1 這次 change 的程式、判準、測試、文件與 kithann 判定檔：分類名「方言」改「語言別差異」，其餘「方言差異／寫法／編號」改「語言別…」；重跑候選、匯入、清洗、報表，數字不變
- [x] 15.2 既有的「方言別正音」一組：`scripts/lexicon/vocab.py`、`scripts/aiyalaeho/langcheck/mark.py` 註解、`tests/lexicon/test_vocab.py`、`tests/aiyalaeho/langcheck/` 的測試說明與 README、`tests/lexicon/README.md`、`tests/README.md`、`scripts/README.md`、`Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/README.md` 改成「語言別」
- [x] 15.3 `aiyalaeho-language-check` delta spec：RENAMED「方言別正音轉換只用於比對」→「語言別正音轉換只用於比對」，另三條 requirement MODIFIED 改用詞
- [x] 15.4 flake8、unittest、aiyalaeho `rebuild --verify` 通過（Kari-SRT README 不在重建範圍，CSV 不變）
- [x] 15.5 其餘三處：`scripts/aiyalaeho/README.md` 影片檔名格式 `NNN-語言[-語言別]-字幕狀態.mp4`、`tests/asrmt/test_dialects.py` 註解、`parallel-corpus-quality` delta spec（MODIFIED「機器翻譯語言碼由靜態表決定」改用詞）
