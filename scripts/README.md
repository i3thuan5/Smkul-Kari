# scripts/：程式分層（照共用性）

資料夾定位見根 README；這裡列到檔案。原則：引擎 package 語料無關、
編排歸 `news/`、兩側共用的東西住 `srtlib/`。

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
| `paths.py` | 全部路徑的單一出處（`--var` 供 shell 取值） |
| `asrmt_batch.py` | 語音側整批：逐集 抓音檔→解碼→投影→raw→刪音檔 |
| `asrmt_run.py` | 語音側單集步驟（預設 words→entries→raw；align 延伸 `--step` 指名） |
| `anchors_ami.json` | 阿美語錨點表（數詞＋借詞專名，拼法對照模型 lexicon） |
| `build_inventory.py`／`add_episodes.py`／`resolve_slug.py` | 集數登記與命名 |
| `fetch_sftp.sh`／`run_cues.sh`／`refine_fetch.sh`／`sftp.sh`／`sftp-askpass.sh` | 影像側抓檔與切 cue（密碼只以檔案存在） |
| `refine_cues.py`／`verify_band.py` | cue 邊界精修、字幕帶前驗 |
| `gap_sheets.py`／`batches.py`／`ingest.py` | 視覺辨識批次的出題與收卷 |
| `make_srt.py`／`make_all.py`／`publish.py`／`tracker.py`／`rebuild.py` | 組裝、定版、進度表、離線重建驗證 |
| `presets.json` | 版型知識（哪個節目哪種帶位） |

## aiyalaeho/、transcode/

《開會了》編排預留位；母帶轉檔小工具（`encode_master.sh`）。
