## 0. 前置

- [ ] 0.1 確認 `half-res-mask-and-slot-crop` 沒有人還在改 `scripts/ocr/sheets.py`（它已於 2026-09-09 完成落地、42/42，但動手前仍要問過那條線）。重讀 `sheets.py`、`tests/ocr/test_sheets.py`、`tests/news/test_sheet_packing.py` 的現況——`build_sheets` 已多 `row_slots`／`compare_cols` 兩個參數，`_cue_blocks` 回傳已變成四元組，`ink_bbox` 已拆出 `_ink_columns`
- [ ] 0.2 用新的圖條高度（垂直裁切後約 63–71 px，不再是 122）把本 change 量到的張數／視覺 token／費用基準重算一次，記進 `kithann/tuiue/`。先前量到的 36% 是垂直裁切落地前測的保守值

## 1. 圖條的欄裁切：取墨水最多的那一團

- [ ] 1.1 `tests/ocr/test_sheets.py`（紅）：合成一條圖條的欄剖面——背景墨水從 x=0 起一路以 ≤200 px 的空隙連過來、字幕在右邊一團，裁切結果只留字幕那一團；字幕與背景之間的空隙大於 200 px 才算兩團；整條只有一團（字壓在不透明色帶上、遮罩裡幾乎只有字）時輸出與現行 `ink_bbox` 實質相同；每欄墨水少於 3 個畫素的欄不算數；墨水太少（不足 8 欄）時退回整條寬度
- [ ] 1.2 `scripts/ocr/sheets.py`（綠）：`_ink_columns()` 改成先分團（空隙 ≤200 視為同一團、每欄墨水 ≥3）再取墨水總量最多的那一團，維持現有的 `pad` 與邊界夾制，回傳型別不變；`ink_bbox()` 薄殼不動
- [ ] 1.3 改寫 `tests/ocr/test_sheets.py::TestCueBlocksCropping::test_columns_are_still_trimmed_to_any_ink`——它鎖的是舊的「任何墨水都算」語意，本 change 會讓它紅。改成鎖新語意：遠處的孤立墨水不再撐開裁切範圍，但字幕那一團一個畫素都不能少
- [ ] 1.4 確認 `TestSlotCrop` 與 `TestUndecidedShare` 仍綠：上下位置判斷量墨水是在 `compare_cols` 範圍內，與欄裁切互不影響

## 2. 組合圖的寬度：逐張各自算

- [ ] 2.1 `tests/ocr/test_sheets.py`（紅）：一集裡有一條滿版寬的圖條時，只有它所在的那一張變寬，其餘每一張的寬度由它自己那幾條決定；一張的寬度等於 `gutter + 該張最寬圖條 + margin`
- [ ] 2.2 `scripts/ocr/sheets.py`（綠）：`_sheet_width()` 從「全集最大」改成「傳進來的這一批最大」，裝箱時逐張計算

## 3. 高度：落在不會被縮圖的邊界內

- [ ] 3.1 `tests/ocr/test_sheets.py`（紅）：寬 W 的組合圖，高度不得超過 `min(2576, (4784 ÷ ⌈W/28⌉) × 28)`；再加一條圖條就會超過時這一張收尾、那一條放下一張；每一張都滿足 `⌈寬/28⌉ × ⌈高/28⌉ ≤ 4784` 且長邊 ≤ 2576；很寬的圖條使一張只放得下一條時仍要產出，不可無限迴圈
- [ ] 3.2 `scripts/ocr/sheets.py`（綠）：`build_sheets()` 的高度改由上式決定，`megapixels` 參數移除或改為僅供覆寫；`2576`／`4784`／`28` 寫成具名常數，註解記下出處是辨識端的解析層上限、換模型要重量

## 4. 照寬度排序後打包

- [ ] 4.1 `tests/ocr/test_sheets.py`（紅）：排序後 `sheets.json` 的 cue 集合與 `cues.json` 完全一致（無重、無漏、每條恰好一次）；同一張上的圖條寬度相近；gutter 印的編號與時間仍對應該條 cue 自己的值；沒有任何一條 cue 因為排序而被丟掉
- [ ] 4.2 `scripts/ocr/sheets.py`（綠）：裝箱前依圖條寬度排序（全集排序），`sheets.json` 照實記錄每張的 cue
- [ ] 4.3 `tests/ocr/test_sheets.py`（紅→綠）：組合圖檔名取**該張最早**的那條 cue（不是排序後排第一的那條），兩張不得同名，同樣的輸入產同樣的名字；`flush_sheet()` 相應改掉 `batch[0][4]`

## 5. 交付 TSV 照 cue 編號排序

- [ ] 5.1 `tests/news/test_ingest.py`（紅）：`normalise()` 讀進亂序的行（例如 703、612、699）後寫出的檔案照 cue 編號遞增；每一列的編號、列名、文字逐字不變、列數不增不減；空白列的第三欄照樣補回；同一 cue 的多列（《開會了》的 `formosan`／`han`）維持原本的相對次序
- [ ] 5.2 `scripts/news/ingest.py`（綠）：`normalise()` 加排序

## 6. 改寫既有的打包守門

- [ ] 6.1 `tests/news/test_sheet_packing.py`（紅→綠）：現有三條釘的是「1.1 Mpx 上界 2044 寬之下 4 條 × 134 = 536、餘裕 2 px」，前提已被本 change 換掉。改寫成新的不變量：每一張都不會被辨識端縮圖、每一張的寬度只由自己那幾條決定；把 docstring 裡「列高多 1 px 就從 4 條掉到 3 條」那段換成新規則下真正會出事的情形

## 7. 驗收與量測

- [ ] 7.1 `.tox/unittest/bin/python -m unittest discover -s tests/ocr -t .` 與 `-s tests/news` 全綠；`.tox/flake8/bin/flake8 . --count` 為 0
- [ ] 7.2 `rebuild --verify` 通過（它不碰組合圖，這一步是證明本 change 沒有波及交付）；`python3 -m scripts.news.name_catalogue --check` 通過
- [ ] 7.3 對三集不同版型重跑 `cues --sheets`（族語新聞兩集含右緣左移的 046晚、《開會了》一集），量張數、視覺 token、每 cue token，確認落在 design 預期的範圍；數字記進 `kithann/tuiue/`
- [ ] 7.4 抽一集派 Claude Vision 實讀，對 store 正解評分：逐條精確率、掉行、串行三個指標都要與現行相當（先前 140 條的實驗是零掉行零串行）
- [ ] 7.5 **掃出「每條 cue 的實際帳單」對批次大小的曲線**，不是量單一個點。用新的組合圖派 Claude Vision 讀，批次取 4／8／12／16／24 張各跑一次，每次記：每張的視覺 token、該批的 cue 數、尖峰累積 context、依 transcript 精算的實際費用。**精算的三條規矩**（`half-res-mask-and-slot-crop` 那條線踩過的）：(a) usage 依回覆的 `message.id` 歸併，一則帶多個工具呼叫的回覆在 transcript 佔多行、每行都帶同一份 usage，逐行加總會高估約 2.5 倍；(b) `output_tokens` 在 transcript 是串流快照、嚴重低報（寫 checkpoint 那步實際幾千 token，log 常只記 3），要另外用「寫出的檔案內容 ＋ 回報字數」估，並附區間；(c) 價格用 Opus 5 的每 M token：cache 寫入 $6.25、cache 讀 $0.50、output $25。**要掃才看得到最佳點**——每個讀者有約 19k 的固定開銷，批次太小被開銷吃掉、太大被 context 重送吃掉，最佳點在中間。先前用「尖峰 100k」外推是錯的：那是 `half-res-mask-and-slot-crop` 量到的上緣（38 張、單位成本已比平坦區高三成），不是甜蜜點，它的拐點在 24–36 張、約 70–85k
- [ ] 7.5a 跑 7.5 之前先估總額給使用者過目再跑——這一步要派好幾組 Claude Vision 真的去讀，是實花的錢，而且**批次越小組數越多、固定開銷越貴**（同樣的 cue 數，4 張一批要派的讀者數是 24 張一批的六倍）。建議固定一個 cue 範圍（例如 280 條）掃五個點，先算清楚要派幾個讀者、預估多少錢
- [ ] 7.6 把 7.5 的曲線交給 `half-res-mask-and-slot-crop` 那條線，由它重訂 `vision_tools/prompt.py` 的 `SIZE`／`MIN_TAIL` 與 `vision_tools/brief.md` 的「一擺讀 4 張圖條」。三個數字綁在同一條曲線上，分開改會互相打架。**本 change 不改那兩個檔**；`brief.md` 那條要保守，調過頭是恬恬失敗（圖掉出 context，讀者以為看過、寫出憑空生的字）
- [ ] 7.7 文件：`scripts/news/README.md` 記下新的打包規則與「高度上限綁在辨識端的解析層、換模型要重量」；`tests/README.md` 的對照表加本 change 的幾列（表跟著測試放，見 CLAUDE.md）
