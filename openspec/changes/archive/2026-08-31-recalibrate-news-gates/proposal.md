# Proposal: recalibrate-news-gates

## Why

族語新聞的三個進料把關共用同一個病：**門檻寫死、用極少樣本校的、量測方法改過沒重校、失敗方向安靜（放過壞檔而不是誤擋好檔）**。

- `verify_band.py` 的 `SPIKE = 2.0` 是 4 集校的，且量測從全幅寬改為含 BUG_MARGIN 後沒重校（docstring 自己承認）。現場證據：README 記某集比值 3.12，2026-08-31 實跑同一支檔是 1.78——從門檻上方掉到下方。news 的失敗方向危險：比值低會判定「無紅帶」而跳過「紅帶不可落在 region 內」的檢查，等於放過會把受訪者名條切成 cue 的壞檔。
- `blank_runs.py` 的「連續空白 ≥40 條」是照 054–059 批（94–147 條）的規模訂的。2021-01 的 006 有 12 條 cue 的字幕印在字幕帶**上方**，落在門檻下面抓不到；而單看長度分不開——同集良性的空鏡連續空白有 13 條，比病灶還長。真正能分的證據是「圖條頂端有被切掉下緣的墨」，可離線量、不用影片。
- `blind_cues.py` 的 `LONG = 6.0`：以《開會了》083 實測 `risky()` 召回率 12/25，漏掉的兩類（短騎線 cue、5 秒藏 3 句）結構上抓不到；`LONG` 應改可調參數（a9 建議），並記錄結構性侷限。

時效：這三個把關都作用在批次進料，2021-01（58 集）切 cue 前重校完才有把關效果；與 restructure-news-pipeline 程式面幾乎不重疊（僅 `blank_runs.py`、`blind_cues.py` 在該 change 讀取端清單內，錯開時間即可），可平行進行。

## What Changes

- 用本機 63 支存檔 mkv 離線全量重量 verify_band 指標（實測單支約 41 秒牆鐘、4 分鐘 CPU，循序約 45 分鐘，nice 執行），依全量分布重定 `SPIKE`（或改判準），校準資料記入量測紀錄文件。
- `blank_runs.py` 增加「region 頂端切緣墨」證據判準，抓上方字幕型病灶；連續長度降級為排序輔助，不再單獨當閘。
- `blind_cues.py` 的 `LONG` 改為可調參數（預設值不變），文件記兩類結構性漏抓與 `spread` 只能排序不能當閘的實測結論。
- 校準結果與量測方法記入 `scripts/news/README.md` 的量測紀錄，含樣本數——「這個門檻是幾集校的」要能被回答。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cue-timing`：「批次切 cue 前驗證字幕帶位置」增加校準要求（門檻以足量樣本校準、量測方法改變後重校、「無紅帶」判定不得靜默跳過 region 檢查而不留量測證據）；新增「帶外字幕偵測」requirement（校讀輔助必須把「region 頂端有切緣墨」的 cue 列入人工複查）。

`blind_cues` 參數化屬實作層，無 spec delta。

## Impact

- **scripts/**：`news/verify_band.py`（SPIKE 或判準、量測證據輸出）、`news/blank_runs.py`（切緣墨判準）、`news/blind_cues.py`（LONG 參數化）、`news/README.md`（量測紀錄）。
- **tests/**：`tests/news/` 對應三支的測試（合成 fixture：帶比值分布、頂端切墨圖條、參數化 risky 清單）。
- **資源**：一次性 CPU 量測約 45 分鐘（nice、可與其他工作平行）；不動 store、不動 work dir 版面，與 restructure-news-pipeline 僅 `blank_runs.py`／`blind_cues.py` 兩檔需錯開修改時間。
