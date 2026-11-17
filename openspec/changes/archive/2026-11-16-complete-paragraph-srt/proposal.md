# Proposal

## Why

族語新聞的段落雙語字幕（`2-asr-whisper/3-srt-paragraph/`）與平行語料（`2-csv-analysis/`）只做了 2021-01～10 的 657 集，但 OCR 與 whisper 已經做完全部 3153 集；範圍寫死在 `pairs_run` 裡，剩下 2496 集（含範圍內 10-21 補 OCR 後漏跑的 6 集）沒有產出，也沒有交件。全量試算 3153 集 330 秒、0 集出錯，分層比例穩定（舊範圍保留 47.4%，2021-11～2024-07 為 44.6%，2024-08 起「看見族語」為 48.2%），可以直接放大。

放大前查出魯凱主播 Lavoras Tavelengae（戴領袖，42 集週五午間）講的是萬山 Oponoho 語，不是目錄記的霧台：本人 Medium 自介明寫萬山，E樂園 魯凱六語言別詞表比對主播開場 42/42 集最像萬山（萬山 0.437、霧台 0.074）。官方辭典每族只收一個語言別，魯凱收霧台，所以她的集數 85% 被判不採用。另外 sapolita 伺服器在 2026-09-24 之後改版，族語別選單值拿掉括號英文名，現有程式送出會被拒。

## What Changes

- 平行語料拿掉月份範圍：`1-ocr/3-srt/` 與 `1-srt-sapolita/` 兩側都有的集數就做；整批產出 2021-01～2024-12。**BREAKING**（行為）：place_cue、offband_backfill、rebroadcast_port 改了任何月份的 OCR SRT，都會連帶重產該集段落字幕。
- 校正基準維持凍結，原本 16 族的值不動；表加「語言別代號」欄，新增萬山（`dru-x-opnh`）一列。`--recalibrate` 改為只補缺的列；要全量重算須先刪表。**BREAKING**（`--recalibrate` 語意）。
- 萬山的集數，本族辭典改用官方魯凱辭典與 E樂園 萬山詞表的聯集。E樂園 從 `kithann/E樂園-解壓/` 現抽，不另存；有萬山的集而 E樂園 不在時，產出與重建都指名中止。
- `relabel` 新增「只換語言別」：族語別不變、成果檔名不變，改目錄的語言別與語言別代號並記依據，刪掉用錯語言別做出來的 whisper SRT、辨識紀錄那一列、平行語料、段落字幕。Lavoras 42 集改萬山 `dru-x-opnh`，whisper 重跑。
- 修 `sapolita.py` 的族語別選單值，跟改版後的伺服器一字不差。
- 抽查工具（`paragraph_export --spot-sample`）可指定批次資料夾、可每族抽 N 組、不覆寫既有批次；只抽高信心，新月份抽 240 組（2021-11～2022-12、2023、2024-01～07 各 48；看見族語隨機 48、每族 3 組 48）。
- 交件：export 2021-03～2024-12 到 `kithann/out/news/雙語字幕/`；清單改為列出交件資料夾裡全部的集；修交件 README 的時間描述（CSV 時間含前後 0.5 秒留白）。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `whisper-parallel-corpus`：範圍改為兩側都有就做；校正基準按語言別代號查、只補缺的列；萬山用官方辭典加 E樂園 詞表。
- `whisper-asr-srt`：族別選單值改成伺服器改版後的字串；語別碼補上「目錄填了經查證的非保底語言別就送那個」（程式 10-23 起已是如此，spec 未跟上，這次萬山重跑依賴它）。
- `srt-data-store`：平行語料層的重建輸入加 E樂園（有萬山的集才需要）；改語言別時語音側產物要刪掉等重跑，範圍從「改族語別」擴到「只改語言別」。

## Impact

檔案與資料夾結構（★新／改）：

```
Kari-SRT/news/
├── smkul.csv                              改：Lavoras 42 集 語言別、語言別代號、備註
├── 主播.csv                               改：Lavoras 那列（萬山、依據）
└── 2-asr-whisper/
    ├── README.md                          改：語別碼、sapolita 改版
    ├── 1-srt-sapolita/<月>/…魯凱.srt      改 42 檔（萬山重跑）；辨識紀錄.csv 改 42 列
    ├── 2-csv-analysis/
    │   ├── README.md                      改：範圍、萬山、校正基準
    │   ├── 校正基準.csv                   改：加語言別代號欄、加萬山一列
    │   └── <月>/<成果檔名>.csv            ★新 2496 集；改 Lavoras 2021 年那幾集
    └── 3-srt-paragraph/<月>/<成果檔名>.srt ★新／改，與上對應
kithann/out/news/
├── 雙語字幕/                              ★新 2021-03～2024-12；改 清單、README
└── 雙語字幕-抽查/<批次>/                  ★新 五個批次資料夾
scripts/
├── datadirs.py                            改：E樂園 路徑常數
├── aiyalaeho/cleaning/paths.py            改：E樂園 路徑改從 datadirs 取
├── asrmt/sapolita.py                      改：族別選單值
├── mt/calibration.py、tier.py             改
└── news/lexicon_fetch.py、pairs_run.py、rebuild.py、relabel.py、paragraph_export.py、
         place_cue.py、offband_backfill.py、rebroadcast_port.py   改
tests/
├── asrmt/test_sapolita.py                 改
├── mt/test_run.py、test_calibration.py、test_lexicon.py、test_paragraph_export.py、README.md  改
└── news/test_relabel.py、test_rebuild_pairs.py、test_place_cue.py、test_offband_backfill.py、
         test_rebroadcast_port.py、README.md   改
```

- 外部服務：sapolita（已稽核）重跑 42 集；不引進新套件、新服務。
- 模型費用：產出本身不呼叫模型；抽查 240 組交 Opus 判，約 US$19。
- 重建驗證 `rebuild --verify` 每次多約 5～6 分鐘（3153 集平行語料）。
