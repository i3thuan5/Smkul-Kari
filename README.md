# Smkul-Kari：原視族語新聞字幕語料 pipeline

對原視族語新聞做兩件事，產出同一條時間軸上的字幕語料：

- **影像側（OCR）**：把燒在畫面上的華語字幕抽成 SRT。
- **語音側（ASR）**：把族語語音整集辨識、投影到與交付字幕逐行
  同軸的條目，產出「族語×華語」對照 SRT（`3-srt-raw`，預設終點）。

資料正本在 `Kari-SRT/` submodule（語料 → 技術 → 編號階段分層），
程式照共用性分 package。核心保證：主 repo＋Kari-SRT 即可離線
重建全部交付 SRT、逐 byte 相同（`rebuild --verify`）。

## 資料夾架構

只列到資料夾；檔案層級各見 [scripts/README.md](scripts/README.md)、
[tests/README.md](tests/README.md)、[Kari-SRT/README.md](Kari-SRT/README.md)。

```text
scripts/                 程式（照共用性分 package）
├── ocr/                     影像側引擎（燒印字幕抽取）
├── srtlib/                  兩側共用：SRT 格式與組裝鏈（同軸保證的心臟）
├── asrmt/                   語音側引擎——預設線（每支影片都跑，到 raw）
│   └── align/               align 延伸（翻譯、偵測、審查、整併；指名才跑）
├── news/                    族語新聞編排（單集／整批入口、路徑單一出處）
├── aiyalaeho/               《開會了》語料預留
└── transcode/               母帶轉檔小工具

tests/                   測試（鏡射 scripts 分包；全離線）
├── ocr/  srtlib/  news/  e2e/
└── asrmt/
    └── align/

Kari-SRT/                資料正本（submodule；語料 → 技術 → 編號階段）
└── news/
    ├── 1-ocr/               影像側階段資料
    └── 2-asr/               語音側階段資料（預設止於 3-srt-raw）
```

## 執行方法

### 新聞全做

```bash
# 語音側：整批（抓音檔→解碼→投影→raw→刪音檔，逐集落地可續跑）
~/.venvs/asrmt/bin/python -m scripts.news.asrmt_batch

# 語音側：單集（預設到 raw；align 延伸用 --step 指名）
~/.venvs/asrmt/bin/python -m scripts.news.asrmt_run <srt_name>

# 影像側：見 scripts/news/README.md 與 Kari-SRT/news/1-ocr/README.md
```

### 母帶封存（mxf → mkv）

把目錄裡每一支 mxf 母帶轉成可長期保存、又還能重跑 pipeline 的 mkv
（CRF 23／yuv420p／FLAC，規格與量測見
`.claude/skills/video-subtitle-srt/壓縮率分析.md`）。與字幕工作各自獨立，
不必等 OCR 做到哪裡。

```bash
# 先看要做什麼（不會動任何東西）
python3 -m scripts.transcode.archive_batch --list

# 開始轉（可中斷、可續跑；已經有 mkv 的自動跳過）
python3 -m scripts.transcode.archive_batch --all-masters

# 只做前 3 支試試（--limit 對 --list 一樣有效）
python3 -m scripts.transcode.archive_batch --all-masters --limit 3

# 只轉本機，先不上傳伺服器
python3 -m scripts.transcode.archive_batch --all-masters --no-upload
```

每一集：抓母帶 → 轉檔 → 驗時長 → 上傳 → 刪母帶。產出兩份，
`kithann/out/mkv/` 與 SFTP `/home/news/mkv/<年-月>/`。

- **一集約 25 分鐘**（下載 4＋轉檔 20＋上傳 1），磁碟峰值是一支母帶
  （最大約 19.7 GB）加一支 mkv，做完就刪母帶。
- **轉完會驗**：用 `ffprobe` 量 mkv 實際時長，跟 `1-ocr/1-cues/` 的時間軸
  比對，差太多就刪掉那支 mkv 並報錯——母帶只上傳一半時，`ffprobe` 讀
  header 照樣宣稱完整，只有逐幀解碼才看得出來。
- **可以跟別的流程同時跑**：一集一把鎖（`O_EXCL`），搶到同一集的那個會
  印「別人在轉」跳過，不會互相刪檔。

## 驗收（每次改程式後）

```bash
tox -e rebuild    # 離線重建全部交付 SRT、逐 byte 比對
tox -e unittest   # 單元測試（tests/，不含 e2e）
tox -e flake8
```

`tox` 不在 PATH 時直接用 `.tox/` 內的 venv（見 CLAUDE.md）。

## 開發環境

```bash
python -m venv venv
source venv/bin/activate   # ta̍k-kái攏ài開，才來開發
pip install tox
```

套件版本管理用 [pip-tools](https://github.com/jazzband/pip-tools)：
`requirements.in` 記直接依賴，`pip-compile` 產 `requirements.txt`
鎖全部版本；語音側另有 `~/.venvs/asrmt`（vosk、huggingface_hub、
ckiptagger）與 `~/.venvs/subs2srt`（numpy、Pillow）兩個工作 venv。
