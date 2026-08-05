# cue 時間邊界精修至 0.05 秒

## Why

現行 cue 切分以 5fps（0.2 秒格點）取樣，22 集交付 SRT 的時間邊界因此帶有
最大 ±0.2s 的量化誤差（e2e 實測 worst-start ≤ 0.30s）。後續要拿這批字幕
做語音對齊／切音檔，需要 ≤0.05s 的邊界精度；字幕本身的顯示品質也受益。
另外 `verify_band.py` 放寬後的紅帶判準（只擋落在 region 內的邊緣）改完
從未拿任何影片實測過，開新月份前必須補驗——兩件事都要重抓影片，併在
同一個 change 一次做完。

## What Changes

- **新增邊界精修 pass**（`scripts/news/refine_cues.py`）：cue 切分維持
  5fps／`min_stable=2` 不動，另在每個既有邊界 ±0.2s 窗內以 ≥20fps 重新
  解碼字幕帶，逐幀對照左右 cue 的參考 mask 分類（不重跑 segmenter），
  把 start/end 精修到 ≤0.05s。cue 集合、編號、文字完全不變。
- **2 月批次 22 集回頭精修**：逐集自 SFTP 重抓 mxf → 精修 → 刪影片，
  更新 `Kari-SRT/cues/`、重產 `Kari-SRT/srt/`。**BREAKING**：交付 SRT
  的時間戳全面改變（文字不變），`rebuild --verify` 基準隨之更新。
- **新月份流程整合**：`fetch_sftp.sh` 在切 cue 之後、刪影片之前順跑
  精修——影片還在本機時做掉，不必二次下載。
- **SRT 邊界留白**：組裝 SRT 時每句往前後各延伸至多 0.5s，被鄰句與
  0 秒下限截短——與 Kaldi `segment_ctm_edits.py` 的
  `--max-edge-silence-length` 預設（0.5s）對齊，供語音切分留邊。
  留白只作用在 SRT 輸出；`cues.json` 保存真實切換點。
- **把 110 年 2 月做完**：22 集以外的 2 月集數（SFTP `2月` mp4 資料夾）
  全部走完 fetch→cues→精修→視覺辨識→組裝，**不管有沒有文稿**（無文稿
  即全 gap）；2 支上傳不完整的 mxf 改試 mp4 版本。
- **verify_band 紅帶判準實測**：拿紅帶低位（y=917 型，如 1 月卑南）的
  實際影片跑通過案例，並以合成剖面 pin 成單元測試。
- **安全網**：精修後邊界必須落在原值 ±0.2s 內，超出即列名報錯不寫入；
  交錯掃描過渡幀「兩邊都不像」時取不明區段中點。

## Capabilities

### New Capabilities

- `cue-timing`: cue 時間邊界的精度契約——精修後邊界與畫面實際切換點的
  誤差上限、精修不得改動 cue 集合與文字、精修結果的可驗證性（與粗切
  邊界的偏移上限、缺輸入時明確失敗），以及開跑前字幕帶位置驗證的判準。

### Modified Capabilities

（無。`srt-data-store` 的離線重建保證**要求不變**——僅靠主 repo +
Kari-SRT、不碰影片、逐 byte 相同；變的是 Kari-SRT 內 `cues/` 與 `srt/`
的資料值，屬資料更新，不是契約變更。）

## Impact

- **新增**：`scripts/news/refine_cues.py`；`tests/news/test_refine.py`
  （分類邏輯、±0.2s 安全網、過渡幀規則，全部離線 fixture）；
  `tests/news/test_verify_band.py`（紅帶判準合成剖面案例）。
- **修改**：`scripts/news/fetch_sftp.sh`（cues 後接精修再刪影片）、
  `Kari-SRT/cues/*.json` 與 `Kari-SRT/srt/*.srt`（22 集時間戳更新，
  一個 commit 同時換）、`openspec` 基準檔。
- **重跑成本**：22 集各 ~16GB 自 SFTP 重抓（75MB/s，約 4 分鐘/集），
  精修每集約 2,000 個邊界窗；整批無人值守約 2–3 小時。
- **2 月補完成本**：集數以 SFTP 實際盤點為準（mp4 每集 ~2.2GB）；
  視覺辨識為主要開銷（每集約 100+ 張 sheet、每張 ~2,800 tokens），
  開跑前照慣例報估算取得同意。`inventory.json` 需擴充涵蓋新集數，
  新資料同樣進 Kari-SRT。
- **git 分工**：依 CLAUDE.md，Kari-SRT commit 與主 repo pointer bump
  由使用者執行。
