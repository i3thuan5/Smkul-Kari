## 0. 前置

- [x] 0.1 確認 `half-res-mask-and-slot-crop` 沒有人還在改 `scripts/ocr/sheets.py`（它已於 2026-09-09 完成落地、42/42，但動手前仍要問過那條線）。重讀 `sheets.py`、`tests/ocr/test_sheets.py`、`tests/news/test_sheet_packing.py` 的現況——`build_sheets` 已多 `row_slots`／`compare_cols` 兩個參數，`_cue_blocks` 回傳已變成四元組，`ink_bbox` 已拆出 `_ink_columns`
- [x] 0.2 用新的圖條高度（垂直裁切後約 63–71 px，不再是 122）把本 change 量到的張數／視覺 token／費用基準重算一次，記進 `kithann/tuiue/`。先前量到的 36% 是垂直裁切落地前測的保守值

## 1. 圖條的欄裁切：取墨水最多的那一團

- [x] 1.1 `tests/ocr/test_sheets.py`（紅）：合成一條圖條的欄剖面——背景墨水從 x=0 起一路以 ≤200 px 的空隙連過來、字幕在右邊一團，裁切結果只留字幕那一團；字幕與背景之間的空隙大於 200 px 才算兩團；整條只有一團（字壓在不透明色帶上、遮罩裡幾乎只有字）時輸出與現行 `ink_bbox` 實質相同；每欄墨水少於 3 個畫素的欄不算數；墨水太少（不足 8 欄）時退回整條寬度
- [x] 1.2 `scripts/ocr/sheets.py`（綠）：`_ink_columns()` 改成先分團（空隙 ≤200 視為同一團、每欄墨水 ≥3）再取墨水總量最多的那一團，維持現有的 `pad` 與邊界夾制，回傳型別不變；`ink_bbox()` 薄殼不動
- [x] 1.3 改寫 `tests/ocr/test_sheets.py::TestCueBlocksCropping::test_columns_are_still_trimmed_to_any_ink`——它鎖的是舊的「任何墨水都算」語意，本 change 會讓它紅。改成鎖新語意：遠處的孤立墨水不再撐開裁切範圍，但字幕那一團一個畫素都不能少
- [x] 1.4 確認 `TestSlotCrop` 與 `TestUndecidedShare` 仍綠：上下位置判斷量墨水是在 `compare_cols` 範圍內，與欄裁切互不影響

## 2. 組合圖的寬度：逐張各自算

- [x] 2.1 `tests/ocr/test_sheets.py`（紅）：一集裡有一條滿版寬的圖條時，只有它所在的那一張變寬，其餘每一張的寬度由它自己那幾條決定；一張的寬度等於 `gutter + 該張最寬圖條 + margin`
- [x] 2.2 `scripts/ocr/sheets.py`（綠）：`_sheet_width()` 從「全集最大」改成「傳進來的這一批最大」，裝箱時逐張計算

## 3. 高度：落在不會被縮圖的邊界內

- [x] 3.1 `tests/ocr/test_sheets.py`（紅）：寬 W 的組合圖，高度不得超過 `min(2576, (4784 ÷ ⌈W/28⌉) × 28)`；再加一條圖條就會超過時這一張收尾、那一條放下一張；每一張都滿足 `⌈寬/28⌉ × ⌈高/28⌉ ≤ 4784` 且長邊 ≤ 2576；很寬的圖條使一張只放得下一條時仍要產出，不可無限迴圈
- [x] 3.2 `scripts/ocr/sheets.py`（綠）：`build_sheets()` 的高度改由上式決定，`megapixels` 參數移除或改為僅供覆寫；`2576`／`4784`／`28` 寫成具名常數，註解記下出處是辨識端的解析層上限、換模型要重量

## 4. 照寬度排序後打包

- [x] 4.1 `tests/ocr/test_sheets.py`（紅）：排序後 `sheets.json` 的 cue 集合與 `cues.json` 完全一致（無重、無漏、每條恰好一次）；同一張上的圖條寬度相近；gutter 印的編號與時間仍對應該條 cue 自己的值；沒有任何一條 cue 因為排序而被丟掉
- [x] 4.2 `scripts/ocr/sheets.py`（綠）：裝箱前依圖條寬度排序（全集排序），`sheets.json` 照實記錄每張的 cue
- [x] 4.3 `tests/ocr/test_sheets.py`（紅→綠）：組合圖檔名取**該張最早**的那條 cue（不是排序後排第一的那條），兩張不得同名，同樣的輸入產同樣的名字；`flush_sheet()` 相應改掉 `batch[0][4]`

## 5. 交付 TSV 照 cue 編號排序

- [x] 5.1 `tests/news/test_ingest.py`（紅）：`normalise()` 讀進亂序的行（例如 703、612、699）後寫出的檔案照 cue 編號遞增；每一列的編號、列名、文字逐字不變、列數不增不減；空白列的第三欄照樣補回；同一 cue 的多列（《開會了》的 `formosan`／`han`）維持原本的相對次序
- [x] 5.2 `scripts/news/ingest.py`（綠）：`normalise()` 加排序

## 6. 改寫既有的打包守門

- [x] 6.1 `tests/news/test_sheet_packing.py`（紅→綠）：現有三條釘的是「1.1 Mpx 上界 2044 寬之下 4 條 × 134 = 536、餘裕 2 px」，前提已被本 change 換掉。改寫成新的不變量：每一張都不會被辨識端縮圖、每一張的寬度只由自己那幾條決定；把 docstring 裡「列高多 1 px 就從 4 條掉到 3 條」那段換成新規則下真正會出事的情形

## 7. 驗收與量測

- [x] 7.1 `.tox/unittest/bin/python -m unittest discover -s tests/ocr -t .` 與 `-s tests/news` 全綠；`.tox/flake8/bin/flake8 . --count` 為 0（2026-09-09：ocr 175 條全綠、flake8 0；`tests/news` 727 條裡唯一紅的 `test_readme_covers_scripts` 是別條線新增的 `scripts/aiyalaeho/langcheck/*` 還沒進 README，與本 change 無關）
- [x] 7.2 `rebuild --verify` 通過（它不碰組合圖，這一步是證明本 change 沒有波及交付）；`python3 -m scripts.news.name_catalogue --check` 通過
- [x] 7.3 對三集不同版型重跑 `cues --sheets`（族語新聞兩集含右緣左移的 046晚、《開會了》一集），量張數、視覺 token、每 cue token，確認落在 design 預期的範圍；數字記進 `kithann/tuiue/`
- [x] 7.4 抽一集派 Claude Vision 實讀，對 store 正解評分：逐條精確率、掉行、串行三個指標都要與現行相當（先前 140 條的實驗是零掉行零串行）
- [x] 7.5 用新的組合圖派一組 Claude Vision 實讀，**只試一個批次大小**（使用者裁定 2026-09-09：不掃五個點，挑最划算的那個試，好就定案）。挑法：批次大小要讓尖峰累積 context 落在拐點以內——`half-res-mask-and-slot-crop` 量到的拐點是 24–36 張、尖峰約 70–85k，而本 change 的組合圖每條 cue 約 0.30k context、每個讀者固定開銷約 19k，所以先算 `(75k − 19k) ÷ 0.30k ≈ 190 條 cue` 當目標，再依 7.3 量到的每張條數換算成張數。跑完記：每張視覺 token、該批 cue 數、尖峰累積 context、依 transcript 精算的實際費用，以及對 store 正解的逐條精確率／掉行／串行。**精算的三條規矩**（`half-res-mask-and-slot-crop` 那條線踩過的）：(a) usage 依回覆的 `message.id` 歸併，一則帶多個工具呼叫的回覆在 transcript 佔多行、每行都帶同一份 usage，逐行加總會高估約 2.5 倍——實作時不要留「沒有 id 就退回物件 id」的 fallback，沒有 id 要明確報錯；(b) `output_tokens` 在 transcript 是串流快照、嚴重低報（寫 checkpoint 那步實際幾千 token，log 常只記 3），要另外用「寫出的檔案內容 ＋ 回報字數」估，並附區間；(c) 價格用 Opus 5 的每 M token：cache 寫入 $6.25、cache 讀 $0.50、output $25
- [x] 7.6 把 7.5 的曲線交給 `half-res-mask-and-slot-crop` 那條線，由它重訂 `vision_tools/prompt.py` 的 `SIZE`／`MIN_TAIL` 與 `vision_tools/brief.md` 的「一擺讀 4 張圖條」。三個數字綁在同一條曲線上，分開改會互相打架。**本 change 不改那兩個檔**；`brief.md` 那條要保守，調過頭是恬恬失敗（圖掉出 context，讀者以為看過、寫出憑空生的字）
- [x] 7.7 文件：`scripts/news/README.md` 記下新的打包規則與「高度上限綁在辨識端的解析層、換模型要重量」；`tests/README.md` 的對照表加本 change 的幾列（表跟著測試放，見 CLAUDE.md）

## 8. 圖條最寬剪到送圖上限以內（使用者裁定 2026-09-10）

- [x] 8.1 `tests/ocr/test_sheets.py`（紅）：整條發亮的圖條不得做出超過 2000 px 的組合圖；左邊那團亮背景就算墨水量贏過字幕也不可以贏得裁切（要在算 ink 之前剪，算完再夾擋不住）；本來就不寬的圖條一個畫素都不准動；**空白圖條**（沒有墨水可裁）也要剪，不然它會以整個 1920 出去
- [x] 8.2 `scripts/ocr/sheets.py`（綠）：`MAX_TILE = LONG_EDGE − GUTTER − TILE_MARGIN − SPARE`（1866），`_ink_columns()` 先丟掉最左邊那幾欄再算；`_cue_blocks()` 的「沒有墨水」那條路也套同一個上限；`GUTTER`／`TILE_MARGIN` 從區域變數提成具名常數
- [x] 8.3 改寫 `tests/news/test_sheet_packing.py` 的最壞情形：2044／1820／13 條改成 1990／1848／13 條，並把「最寬那張超過 2000」改成「連最寬那張都在 2000 以內」
- [x] 8.4 三集重跑確認：張寬上界從 2044 掉到 1990，張數與視覺 token 不變或略降（058晨 51 張 105,914、046晚 17 張 34,980、開會了 111 70 張 152,586）
