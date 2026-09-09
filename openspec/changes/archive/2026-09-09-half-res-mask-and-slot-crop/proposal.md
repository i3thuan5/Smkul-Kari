# 切 cue 的遮罩只看字幕實際落點，圖條只留有字的那一位

## Why

族語新聞的切 cue 有兩個量過的浪費。**一是切太碎**：全 store 76,547 條 cue 裡 19,034 條（24.9%）的文字和前一條完全相同，是同一句字幕被切成好幾塊，每一塊都要 Claude Vision 讀一次；根因是遮罩比對看整條 1920×122 的字幕帶，帶裡大半是會動的畫面（亮蕨葉、報紙、白襯衫），雜訊把「字沒變」的遮罩距離推到 0.17–0.43，正好跨過 0.35 的門檻。**二是圖條有一半是空的**：新聞字幕只用字幕帶裡偏上或偏下其中一位，但每一條圖條都是整條 122 px 高，另一位的留白照樣佔掉 Claude Vision 輸入組合圖的高度預算。

量測顯示兩件事都能治，而且治法互不相干、可以疊：新聞字幕**靠右對齊在 x≈1736**（27 集的右緣中位數 1735–1737），所以比對遮罩只看右邊那一塊就夠；字幕**90.6% 落在偏上或偏下其中一位**（27 集 1,080 條圖條），所以圖條可以只留有字的那一位。

現在做的理由是還有集數可以受益：inventory 133 集裡 74 集已交付，**59 集 pending、其中 58 集還沒切 cue**（全部 2021-01），全語料照 catalogue 是 983 集。已交付的不重切，所以晚做一天就少一天的受益集數。

## What Changes

- **切 cue 的遮罩改半解析度**：`text_mask` 改吃 `rgb[::2, ::2]`，`outline_size` 9→5、`band_probe` 的 x／w 減半、`min_ink` 依面積換算，切換門檻維持 0.35。切 cue 與事後精修共用同一支函式。兩個語料都適用。實測每格 17.62 → 3.67 ms，切割品質三個指標都在雜訊範圍內。
- **新增「置右字幕比對遮罩」**：切 cue 比對相鄰影格時，只看 preset 宣告的那一塊（新聞 x 1250–1790、列 4–114），範圍外的畫素不參與切點判斷。**圖條與 Claude Vision 輸入組合圖完全不受影響**——讀到的畫素一個都沒少。四集實測重覆對降 44–69%，而且吞句同時降（051晚 87→43）。與半解析度疊起來每格 1.08 ms，比現行快 16.3 倍。
- **`verify_band` 新增欄剖面把關**：現有的解碼迴圈裡多算一條欄方向的墨水剖面（不多花解碼時間），從中找「右崖」；量到的右崖偏離 preset 宣告值超過容許量就拒切。這補的是「版型變了但沒人發現」的破口——27 集裡有一集（046晚）右緣在 1631 而非 1736。
- **新增「字幕上下位置判斷法」**：Claude Vision 輸入組合圖的圖條，依該條 cue 的墨水落在偏上還是偏下裁掉另一位的留白（分界列 65、上下各留 6 px）。兩位墨水比值小於 2.0、或墨水太少判不出來時**退回全高**，也就是現況。墨水用置右字幕比對遮罩的欄範圍量。組合圖張數 −33～40%，Opus 讀圖精確率不變。
- **《開會了》只吃半解析度**，不設置右字幕比對遮罩、不做上下位置判斷法：它的字幕壓在不透明的漸層帶上，背景本來就進不了遮罩（三集實測重覆對 0／0／78），做了只會換來新的吞句；圖條裁切則會切薄族語列的撇號（實測族語列精確率 98.6%→76.8%）。
- **Claude Vision 批次大小 72→24**：`vision_tools/prompt.py` 的 `SIZE` 72→24、`MIN_TAIL` 24→8。依回覆 id 歸併重算，一批 72 張比三批 24 張貴 1.5–1.9 倍，因為每一輪呼叫都要重送整段變長的對話。
- **新增 `tools/cuescore/`**：離線評分工具，吃 `cues.json` 與 vision TSV，算「重覆對／吞句／漏切」三個指標，不需要影片。它是這一輪效益數字的可重現形式，也是日後任何人改切割參數時唯一能量出好壞的東西。
- **不改的**：已交付的 74 集不重切；store 目錄版面、交付 SRT 與 TSV 格式完全不變；`rebuild --verify` 逐 byte 結果不變。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cue-timing`：「切 cue 的遮罩裁到量得的帶上，圖條不裁」這條目前寫死是**列**、來源是**量測**，而且要求 Claude Vision 輸入組合圖的裁切範圍不得改變。三點都要改：比對範圍推廣到**列與欄兩軸**、來源可以是**preset 宣告**（不限量測）、那句「組合圖裁切不得改變」收斂為「不因遮罩限制而改變」（圖條的裁切另有規矩，見下）。另新增一條：帶位驗證要能對**欄**方向的字幕落點把關。
- `subtitle-text-source`：新增一條「圖條裁切只裁留白，不裁字」——組合圖的圖條可以裁掉沒有字的那一位，但判不出來時必須退回全高，且任何情形都不得裁掉字幕畫素。

## Impact

### Kari-SRT（資料）

- **store 版面不變、交付格式不變、已交付集數不重切。**
- **`cues.json` 不新增任何鍵**（使用者裁定 2026-09-09）。新參數的正本是 preset，由呼叫端明確指定版型後流到各消費端；切完一集寫出來的 `cues.json`，鍵集合與改動前完全相同。既有的 `mask.band_rows`（量測得來、逐集不同）維持現況記在 manifest——分界原則是「量測來的記 manifest，宣告來的留 preset」。
- 因此**只有 `refine_cues` 一支**要新增 `--preset`／`--presets`（它是兩個語料共用的，《開會了》的批次腳本也直接呼叫它），未指定時中止而非靜默用不同參數；`gap_sheets` 與 `rescan_band` 是新聞專用，直接讀新聞 preset，呼叫端不必改。

### scripts／tools

- 修改：`scripts/ocr/cuelib.py`（`MaskSpec` 加三個欄位、新增 `scaled()` 與 `frame_mask()`；三個欄位刻意不進 `to_dict()`／`from_dict()`）、`scripts/ocr/cli.py`（改呼叫 `frame_mask`、`--mask-scale`、把 preset 的 `row_slots` 傳給 `build_sheets`）、`scripts/ocr/sheets.py`（`build_sheets` 收 `row_slots`、上下位置判斷、回報逐集判不出來的比率）、`scripts/news/refine_cues.py`（加 `--preset`／`--presets`）、`scripts/news/gap_sheets.py` 與 `scripts/news/rescan_band.py`（同上）、`scripts/news/fetch_sftp.sh`（呼叫 refine 時傳 preset）、`scripts/news/verify_band.py`（欄剖面與把關）、`scripts/news/presets.json`、`scripts/aiyalaeho/presets.json`、`scripts/news/vision_tools/prompt.py`。
- 新增：`tools/cuescore/`（`__init__.py`、`score.py`、`README.md`）。
- **不動**：`scripts/ocr/cuelib.py` 的 `text_mask` 本體與 `band_rows`（`finish-aiyalaeho-batch` 的成果，本 change 疊在它上面）、`blank_runs.py`、`blind_cues.py`、`reread.py`（維持全解析、全帶）。

### tests

- 修改：`tests/ocr/test_mask.py`、`test_segmenter.py`、`test_sheets.py`、`test_presets.py`、`test_auto_options.py`、`tests/news/test_verify_band.py`、`test_refine.py`、`test_vision_prompt.py`。
- 新增：`tests/tools/test_cuescore.py` 與 `tests/tools/README.md`（該目錄自己那幾列的 spec × scenario 表）。
- 不動：`tests/ocr/test_cuelib_band_rows.py`、`test_band_rows_option.py`。

### 文件

`scripts/README.md`、`scripts/news/README.md`、`tests/README.md`（總表加一行指向 `tests/tools/`）、`.claude/commands/smkul-news.md`。

### 排程

58 集尚未切 cue 的 2021-01 若在本 change 落地前先切，就享受不到 CPU 與切割品質的改善（已切的不重切）。要不要等，由使用者決定。
