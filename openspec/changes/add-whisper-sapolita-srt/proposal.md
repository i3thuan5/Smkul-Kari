## Why

族語語音辨識已經堪用，但族語→華語翻譯很差，缺的是訓練語料。族語新聞正好有族語發音與華語燒印字幕，可以做成族華平行語料。原本語音側用 kaldi（vosk）辨識；現在另有自己開發的 whisper 族語辨識服務 sapolita，辨識效果較好。所以先把 `smkul.csv` 全部 969 集送 sapolita 取得 SRT，作為之後配平行語料的族語那一側。

## What Changes

### 資料

- **BREAKING**：`Kari-SRT/news/2-asr/` 改名 `Kari-SRT/news/2-asr-kaldi/`，跟新的 whisper 目錄對稱；工作目錄 `kithann/out/news/2-asr/` 同步改名 `2-asr-kaldi/`。
- 新增 `Kari-SRT/news/2-asr-whisper/`：
  - `README.md`：各層是什麼、從哪裡做出來、誰讀它。
  - `1-srt-sapolita/<年-月>/<成果檔名>.srt`：sapolita 回傳的 SRT **原樣**存檔。每段「族語：」（辨識結果）、「華語：」（服務自己的機器翻譯）兩行；分段、標籤、片尾配樂處的幻覺都不改，也不加 0.5 秒留白。
  - `1-srt-sapolita/辨識紀錄.csv`：一集一列，記成果檔名、實際送出的語言別代號、主播名、伺服器、辨識日期（CST）、音長秒、段數。
- 新增 `Kari-SRT/news/主播.csv`：一位主播一列，記族語別、主播族語名、主播漢名、語言別、語言別代號、抽聽的集、語別依據。

### 語別

- sapolita 對 7 個多語別的族要選語別，`smkul.csv` 只記到族語別。新增 `scripts/news/新聞語言別代號.csv`（16 族 → 送 sapolita 的語別碼）。多語別 7 族用：海岸阿美 `ami-x-pswl`、賽考利克泰雅 `tay-x-sql`、中排灣 `pwn-x-pnvn`、郡群布農 `bnn-x-isbk`、德固達雅賽德克 `trv-x-tgdy`、霧台魯凱 `dru-x-ngdr`、南王卑南 `pyu-x-pym`。同一族所有集數用同一個語別碼，因為新聞裡除了主播還有記者，一集不是只有一個人在講。
- 主播名每集從該集 OCR 字幕開頭的「我是…」取，取不到就寫「不明」。辨識紀錄同時記主播名與送出的代號，日後發現語別選錯，可以挑出那幾集重做。

### 程式

- 新增 `scripts/asrmt/gradio.py`：Gradio 佇列協定（上傳、queue/join、讀串流），從 `mtclient.py` 抽出來，翻譯服務與 sapolita 共用。
- 新增 `scripts/asrmt/sapolita.py`：sapolita 用戶端。
- 新增 `scripts/news/audio.py`：取音檔（封存 mkv → SFTP，抓來的原檔抽完音軌就刪），kaldi 與 whisper 兩條線共用；不再看暫存區既有的原檔，whisper 也不用 kaldi 工作目錄裡的 `audio.mp3`。
- 新增 `scripts/news/whisper_run.py`：逐集／整批辨識，一次送一集，可續跑。
- 刪除 `scripts/news/move_outdirs.py`：一次性搬家已做完，以後用不到。
- 伺服器一次只送一集，不平行送。測試機（tshi5v100）只用來做這次的 spike，正式跑一律用正式機 `https://ai-labs.ilrdf.org.tw/sapolita/`。

## Capabilities

### New Capabilities

- `whisper-asr-srt`：把節目目錄的每一集送 sapolita 辨識——語別碼怎麼決定、SRT 原樣存放、辨識紀錄的欄位與主播名來源、續跑、一次一集、取音檔的來源。

### Modified Capabilities

- `srt-data-store`：語音側目錄 `2-asr/` 改名 `2-asr-kaldi/`；store 結構加上 `2-asr-whisper/` 與 `主播.csv`。
- `asr-bilingual-srt`：產出與翻譯快取的路徑跟著改名；取音檔改成「封存 mkv → SFTP」，不再先看暫存區的原檔，抓來的原檔用完就刪。
- `parallel-corpus-quality`：判定快取、`3-srt-ai`、`4-srt-quality`、README 的路徑跟著改名。

## Impact

- **資料**：`Kari-SRT/news/2-asr/` 整個目錄改名；新增 `2-asr-whisper/`（969 集 SRT＋一張紀錄表）與 `主播.csv`。
- **程式**：新增 `scripts/asrmt/gradio.py`、`scripts/asrmt/sapolita.py`、`scripts/news/audio.py`、`scripts/news/whisper_run.py`、`scripts/news/新聞語言別代號.csv`；修改 `scripts/asrmt/mtclient.py`、`scripts/news/paths.py`、`scripts/news/asrmt_run.py`、`scripts/news/asrmt_batch.py`；刪除 `scripts/news/move_outdirs.py`。
- **文件**：`scripts/README.md`、`scripts/news/README.md`、`tests/README.md`、`Kari-SRT/README.md`、`Kari-SRT/news/2-asr-kaldi/README.md`、`.claude/commands/news-stage-count.md`。
- **外部服務**：sapolita（ILRDF 族語 AI 成果網站，whisper 族語模型由我方團隊開發）。不加新的 Python 套件，HTTP 用標準函式庫。
- **機器時間**：約 900 集要從 SFTP 重抓影片（一支約 2.2 GB，總計約 2 TB、下載約 8 小時）。伺服器每集約 2 分鐘，969 集一集接一集約 32 小時（測試機實測，正式機未量）。一集抓完、辨識完才抓下一集，下載不跟辨識重疊。
