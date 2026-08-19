# 族語新聞 ASR＋MT 雙語 SRT（乙′ 方案），含語音-字幕對不齊偵測

## Why

已交付的 35 集族語新聞 SRT 只有畫面上燒印的**華語**字幕；族語只存在於
聲音裡，目前完全沒有文字化。要拿這批語料做語音辨識訓練與字幕比對，
需要每集一份「族語＋華語」雙語 SRT，而且時間軸必須跟交付 SRT 逐行同軸，
比對才能是逐行 zip。同時，族語語音與華語字幕本來就可能對不起來
（字幕師改寫、漏譯、時間 lead/lag），需要一套偵測機制把「對不起來的
句子」找出來並歸因，產出才有品質依據。

## What Changes

- **新增 ASR 流程（乙′）**：整集音檔在本機用 vosk＋HF 上的
  `ILRDF/kaldi_formosan_250514_<族>` 模型解碼，拿逐詞時間戳與
  confidence，再把詞投影回 `Kari-SRT/cues/` 既有 cue 時間軸。
  **不逐 cue 切音**——35 集實測 97% cue 間隔 <0.1s、21.9% cue <1s，
  切音會斬詞。
- **新增 MT 流程（雙引擎互證）**：族語→華語與華語→族語兩方向，
  各用兩個引擎——`ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil`
  gradio API（族語特化 NLLB）與 Claude（subagent 批次翻譯）。
  SRT 華語行取主引擎（試點先用 ai-labs），兩引擎譯文都保存、
  在偵測中互證。快取以內容定址（engine, direction, src_lang,
  text），單併發、可中斷續跑。
- **新增雙語 SRT 組裝**：沿用 cue 時間軸，與交付字幕 SRT 逐行
  同 index 同時間戳，SRT 邊界照 CLAUDE.md 0.5s 留白規則。gate 前
  為審查版：每條六行（族語ASR結果、華語OCR字幕翻譯成族語
  ×2 引擎、華語OCR字幕原文、族語ASR結果翻譯華語 ×2 引擎）——
  已花運算的譯文全部留痕、字幕原文併入不跨檔對照；主引擎定案後
  另產正式版兩行「族語：」「華語：」（`5-srt-complete/`），審查版
  （`3-srt-raw/`）保留不覆蓋。
- **BREAKING：Kari-SRT 目錄照「語料→技術→階段」改組**——既有資料
  移入 `news/1-ocr/` 並照產生流程編號（`1-cues`、`2-from_rtf`、
  `3-vision`、`4-vision-rtf`、`5-report`、`6-srt`）；
  `inventory.json` 與 `smkul.csv` 升到 `news/`（進度表增列語音側
  欄，由 store 檔案存在推導）；語音側產出放 `news/2-asr/`；兩技術
  目錄各有 README。資料值逐 byte 不變、只動路徑；主 repo 路徑
  常數隨之更新，`rebuild --verify` 在新路徑必須照樣通過。
- **BREAKING：`scripts/subs2srt` 照共用性拆分**——純像素與 OCR
  工作流歸 `scripts/ocr/`，兩側共用的 SRT 格式與組裝鏈歸
  `scripts/srtlib/`（cuelib.py 與 assemble.py 模組內也拆）；
  tests 鏡射為 `tests/ocr/`、`tests/srtlib/`。舊 import 路徑
  全數失效。
- **新增語音-字幕對不齊偵測**：以時間重疊建「語音句 × 字幕 cue」
  連通塊為比對單位，華語空間管內容（語序免疫的字元比法）、族語空間
  管時間（滑動視窗量偏移曲線）、錨點詞校驗，逐 cue 歸因輸出 JSON。
- **試點 gate**：先做 110 年 2 月新聞的
  `20210201_032_晚間_Amis_阿美` 一集（1,022 cues），產出雙語 SRT＋
  偵測 JSON＋報告；使用者看過報告核可後，才續跑其餘全部已交付
  集數（寫此文時 34 集），放量任務含在本 change（tasks 6.x）。
- 程式照 reorg 慣例分層：引擎新 package `scripts/asrmt/`、族語新聞
  編排放 `scripts/news/`、資料正本進 `Kari-SRT/`（新目錄，鍵用
  `srt_name`）。

## Capabilities

### New Capabilities

- `asr-bilingual-srt`：雙語 SRT 的產出契約——時間軸與交付 SRT 逐行
  同軸、兩行格式、ASR 詞投影規則、MT 快取與續跑、輸出檔的存放位置
  與命名。
- `speech-subtitle-alignment`：對不齊偵測的契約——比對單位（連通塊）、
  兩個比對空間各管什麼、偏移曲線、歸因矩陣的類別、逐 cue 診斷輸出
  的欄位，以及門檻須經人工樣本校準。

### Modified Capabilities

- `srt-data-store`：存放結構改為「語料→技術→階段」分層
  （`news/1-ocr/` 影像側＋`news/2-asr/` 語音側，`inventory.json`
  升到 `news/`），並明文「不同狀態分開存放、不同路徑覆蓋禁止」。
  離線重建保證與資料值不變，僅路徑修訂。（`cue-timing` 不動：
  本 change 只讀 cue 不改 cue。）

## Impact

- **新增**：`scripts/asrmt/`（vosk 解碼、詞投影、MT client、偵測、
  雙語 SRT 組裝）、`scripts/news/` 的批次編排入口、`tests/asrmt/`
  離線單元測試、`Kari-SRT/news/2-asr/`（語音側產出）。
- **遷移**：`Kari-SRT` 既有資料 `mv` 入 `news/1-ocr/` 與 `news/`
  （檔案系統搬移由 Claude 做，git 由使用者 commit）；
  `scripts/news/paths.py` 等路徑常數全面改指新位置。
- **依賴**：新增 Python 套件 `vosk`、`huggingface_hub`（裝在
  `~/.venvs/` 或 tox env，不進系統）；外部服務只剩 MT 一個
  （ASR 全本機，也因此避開 asr-kaldi app 層的 `capitalize()` 與
  阿美 `u→o` 這兩個毀比對的 presentation 處理）。
- **資料來源**：SFTP 的 mp3（一集十幾 MB）；試點第 0 步必驗 mp3
  時間軸與 cue 軸是否同條（2 月 mp3 與 7 月資料夾的 mp4 同源，
  cue 軸卻是從 mxf 母帶切的），不合就改抓 mxf 抽音。
- **與 refine-cue-timing 的關係**：ASR 解碼與 cue 邊界無關，試點
  不必等它；精修落地後只需重投影＋增量 MT（快取內容定址）。偵測的
  偏移解析度在精修前受 ±0.2s 量化限制，報告須註明。
- **git 分工**：程式與資料檔由 Claude 寫；`git add`／`commit`／
  submodule pointer bump 依 CLAUDE.md 由使用者執行。
