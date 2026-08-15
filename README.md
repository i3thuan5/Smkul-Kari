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

```
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

## 跑法

```bash
# 語音側：整批（抓音檔→解碼→投影→raw→刪音檔，逐集落地可續跑）
~/.venvs/asrmt/bin/python -m scripts.news.asrmt_batch

# 語音側：單集（預設到 raw；align 延伸用 --step 指名）
~/.venvs/asrmt/bin/python -m scripts.news.asrmt_run <srt_name>

# 影像側：見 scripts/news/README.md 與 Kari-SRT/news/1-ocr/README.md
```

## 驗收（每次改程式後）

```bash
tox -e subtitle-rebuild   # 離線重建全部交付 SRT、逐 byte 比對
tox -e subtitle           # 單元測試（tests/，不含 e2e）
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
