# scripts/：程式分層（照共用性）

資料夾定位見根 README；這裡列到檔案。原則：引擎 package 語料無關、
編排歸 `news/`、兩側共用的東西住 `srtlib/`。

## errors.py——唯一對人丟的例外（頂層，兩側共用）

`PipelineError`：操作者、store 抑是外部服務出錯，講予人知然後停。
以前 48 个函式庫函式直接丟 `SystemExit`——彼是 `BaseException`，
`except Exception` 掠袂著，等於恬恬繞過別人ê錯誤處理；而且
`asrmt_batch` 為著「跳過這集、繼續落一集」，愛掠 `BaseException` 來做
一般ê流程控制。

無人佇 CLI 邊界kā它換轉去 `SystemExit`（使用者裁定）：沒接的例外會
印 traceback、離開碼 1。堆疊會講是佗一个檢查掠著ê、是啥物叫伊，批次
做一半停落來ê時，彼比一逝清氣ê訊息較有路用。

## datadirs.py——repo 版面與參數保護（頂層，兩側共用）

`ROOT`／`kithann/`／`Kari-SRT/` 三個位置，加上 CLI 參數的保護：
`check_name`（名字不得帶路徑成分）、`check_under`（路徑只准落在
`kithann/`、`Kari-SRT/`、系統暫存目錄——**不是** repo 底下都可以，
`scripts/` 與 `openspec/` 是程式碼與規格，不是資料）。

放頂層是因為 `ocr/` 刻意不依賴 `news/`：這裡放的是 repo 版面與參數
驗證，兩邊都不擁有；語料專屬的路徑（stage、inventory、catalogue）
留在 `news/paths.py`。

## ocr/——影像側引擎（燒印字幕抽取）

| 檔 | 做什麼 |
|---|---|
| `cuelib.py` | 像素核心：遮罩、區域運算、取樣、cue 切分（Segmenter） |
| `band.py` | 字幕帶位置偵測（preset 載入與帶位判準） |
| `ocr.py` | tesseract 輸出清理 |
| `sheets.py` | contact sheet 產生（給視覺辨識讀） |
| `transcripts.py` | 視覺逐字稿帳本：TSV 驗證匯入、transcripts.json／verified.json |
| `cli.py` | `python -m scripts.ocr.cli`：detect／cues／ocr／srt／auto 五階段 |

## srtlib/——兩側共用

| 檔 | 做什麼 |
|---|---|
| `srt.py` | SRT 格式：時間戳、render、parse |
| `assemble.py` | 組裝鏈：同文合併、間距規則、0.5s 留白、`chain_with_spans`（條目↔真實窗對照——影像側交付與語音側 raw 跑同一條鏈，同軸因此逐 byte 成立） |

## asrmt/——語音側引擎（預設線：到 raw 為止）

| 檔 | 做什麼 |
|---|---|
| `asr.py` | vosk 整集解碼 → 逐詞時間戳＋confidence（1-words） |
| `project.py` | 詞按真實窗 max-overlap 歸戶條目（2-entries） |
| `bisrt.py` | raw render：「族語：／華語：」兩行（3-srt-raw，預設終點） |

### asrmt/align/——align 延伸（指名才跑）

| 檔 | 做什麼 |
|---|---|
| `mtclient.py` | ai-labs gradio 翻譯 client（session handshake、502 重試）＋內容定址 mt-cache |
| `claude_mt.py` | Claude 批次翻譯：編號批次檔＋整批對帳 ingest |
| `dpalign.py` | 時間帶限單調 DP（1-1／1-2／2-1／2-2 合併、sim 注入、純函式） |
| `detect.py` | 語意句塊、內容分數、δ 偏移、CKIP 錨點對位、歸類矩陣、merge_groups |
| `render.py` | 審查版六行＋偵測行（4-srt-ai）、語意整併版（6-srt-complete） |

## news/——族語新聞編排

| 檔 | 做什麼 |
|---|---|
| `paths.py` | 語料路徑的單一出處（`--var` 供 shell 取值；版面與保護轉出自 `scripts/datadirs.py`） |
| `asrmt_batch.py` | 語音側整批：逐集 抓音檔→解碼→投影→raw→刪音檔 |
| `asrmt_run.py` | 語音側單集步驟（預設 words→entries→raw；align 延伸 `--step` 指名） |
| `anchors_ami.json` | 阿美語錨點表（數詞＋借詞專名，拼法對照模型 lexicon） |
| `build_inventory.py`／`add_episodes.py`／`resolve_slug.py` | 集數登記與命名 |
| `fetch_sftp.sh`／`run_cues.sh`／`refine_fetch.sh`／`sftp.sh`／`sftp-askpass.sh` | 影像側抓檔與切 cue（密碼只以檔案存在；`sftp.sh` 收動詞＋獨立參數，路徑不進指令字串） |
| `refine_cues.py`／`verify_band.py` | cue 邊界精修、字幕帶前驗 |
| `gap_sheets.py`／`batches.py`／`ingest.py` | 視覺辨識批次的出題與收卷 |
| `make_srt.py`／`make_all.py`／`publish.py`／`tracker.py`／`rebuild.py` | 組裝、定版、進度表、離線重建驗證 |
| `presets.json` | 版型知識（哪個節目哪種帶位） |

## aiyalaeho/、transcode/

《開會了》編排預留位；母帶轉檔小工具（`encode_master.sh`）。
