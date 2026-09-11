## Context

動機見 proposal.md。這裡只記幾個會影響實作順序與檔案配置的現況：

- `rebuild --verify` 是唯一的把關（Kari-SRT 是私人 repo，CI 抓不到 submodule）。這個 change **同時改「被驗的資料」和「驗的方式」**，中間沒有一個綠燈狀態可以退回去。
- `news/inventory.json` 有 18 個模組在讀，用到的欄位次數是 `srt_name` 40、`slug` 17、`truncated` 14、`pending` 4、`video` 3，其餘個位數。
- `2-vision/` 由 Claude Vision 那端直接寫進 Kari-SRT、`3-srt/` 由組裝流程直接寫進去；只有 `1-cues/` 走 publish。所以「分階段入庫」差的只是 publish 的一道門。
- 量過的資料性質（scenario 的來源）：`播出時段` 由 `節目名稱` 決定 983/983、`slug` 推導 133/133、`file` = basename(video) 133/133、`pending` ≡ `3-srt` 檔在不在 133/133、`1-cues` 的 `video` 欄 114/114 是絕對路徑、`qc.json` 零個生產程式讀、`1-句對.csv` 的 `來源檔` 前綴 = `集` 55785/55785、mp3 路徑推導不出來 148/983。

## Goals / Non-Goals

**Goals:**

- 讓「有哪些集數」只有一份正本，而且那份正本就是交付表
- 六張 CSV 的前七欄逐 byte 一致，任兩張 join 得起來
- 讓每個階段各自入庫，不必等整集做完
- 換掉 CSV 的驗法時，SRT 的逐 byte 保證一格都不鬆

**Non-Goals:**

- 不動引擎層（`scripts/ocr/`、`scripts/srtlib/`、`scripts/asrmt/`）——它們語料無關，這次不碰
- 不把程式碼識別字裡的 `store` 改成 `Kari-SRT`（CLAUDE.md 的用詞規定只管文件與講話）
- 不改 SRT 的組裝邏輯，也不重跑任何一集的視覺辨識
- 不補 2022 年度或尚未處理月份的任何處理，只是讓它們在目錄裡有一列

## Decisions

### 1. `episodes.py` 維持 inventory 的 entry 形狀，不改呼叫端

18 個模組的 `entry["slug"]`、`entry["srt_name"]` 全部原樣保留，只把 `paths.load_inventory()` 換成 `episodes.load()`。`slug`／`file`／`pending` 在讀表時現場推導。

**為什麼不順便改成 dataclass 或改欄名**：那會把一個資料模型改動變成 18 個模組的全面改寫，而 `rebuild --verify` 在這個 change 中途是半失效的——改動越大越難定位是哪一步弄壞的。形狀不變，diff 就只剩「哪裡讀資料」這一件事。

**替代方案**：讓每個呼叫端各自讀 CSV。否決——那是把一份契約散成 18 份。

### 2. 語言代號對照表抽到 `scripts/languages.py`

`LANGUAGES`、`VARIETIES`、`code_for()` 從 `scripts/aiyalaeho/catalogue.py` 搬到頂層，加反查（代號 → 族語別、代號 → 語言別）。

**為什麼抽出來而不是互 import**：新聞側現在也要 `語言別代號`。現有的跨 package 依賴方向是 aiyalaeho → news（`catalogue.py` 取用 `news.refine_cues.probe_duration`），news → aiyalaeho 是反方向。頂層的定位跟 `datadirs.py` 同一條理由：兩邊都不擁有它，而且 `ocr/` 引擎刻意不依賴 `news/`。

**替代方案**：複製一份到 news。CLAUDE.md 明文禁止（「不要另外造一份」）。

### 3. CSV 的把關從逐 byte 換成不變量，SRT 那邊完全不動

`smkul.csv` 從產出變成輸入，逐 byte 重算比對失去意義。改驗六條不變量（見 srt-data-store 的「節目目錄的不變量」）。

**為什麼這樣不算放鬆**：逐 byte 比對只會說「`smkul.csv` 對不上」；不變量檢查會說「第 412 列的 `語言別代號` `amis` 不在對照表裡」。前者抓得到任何改動但說不出哪裡錯，後者抓得到所有會讓下游壞掉的改動並指名。唯一真正失去的是「有人改了一格合法的值」——那是人維護表格本來就該能做的事。

### 4. 誤刪偵測換成子集不變量，接受它抓不到刪檔

分階段入庫之後，「還沒做」和「做了又不見」在檔案上長得一樣。子集不變量 `3-srt ⊆ 2-vision ⊆ 1-cues` 只抓得到下游多出來的情形。

**為什麼接受**：使用者裁定——Kari-SRT 在版本控制下，刪檔用 git 追得回來，而且 `/news-stage-count` 的數字人看得出來（`1-cues` 75、`3-srt` 74）。用一個狀態欄換這件事，就把剛拿掉的東西又裝回去。

### 5. 音檔改從該集影片抽音軌，影片沿用既有的下載路徑

`mp3_remote()` 與 `_mp3_cell_path()` 整個拿掉。音軌改用 ffmpeg 從**該集的影片**抽出。

影片的正本在 SFTP 上，不是本機——這條流程本來就要把它下載下來切 cue（`fetch_sftp.sh` 依節目目錄的 `原始影片檔案位置` 取檔，落在 `kithann/out/stage/`）。所以 ASR 取音軌的來源依序是：本機暫存的原檔、封存 mkv（`kithann/out/mkv/`），兩者都沒有時**依 `原始影片檔案位置` 從 SFTP 下載**，走的是跟切 cue 同一條路、同一組憑證。

**為什麼不保留一欄 `原始音檔案位置`**：使用者裁定。量過推導可行性——只有 835/983 的音檔與影片同資料夾同主檔名，69 列主檔名不同（影片帶族語前綴、音檔沒有），64 列根本不同資料夾——那一欄推導不出來，只能人維護，而且只服務單一步驟。影片位置那一欄是整條流程都在用的，音軌從它抽就不必再養第二份路徑。

**代價**：影片不在本機時，ASR 要下載的是 GB 級的影片而不是幾十 MB 的 mp3。但影片在切 cue 階段就已經下載過，兩步排在一起就只下載一次；真的要單獨重跑 ASR 時多花的是頻寬，不是正確性。

### 6. publish 的「內容一致不覆寫」比正規化後的字串

比較對象是 `redump_store.dump(manifest)` 的輸出，不是 work dir 檔案的原始位元組。

**為什麼**：work dir 那份 JSON 的鍵是插入順序、store 那份是排序過的。曾經因為直接 `shutil.copy2`，一次 publish 重寫了 74 個內容根本沒變的已交付檔案。比原始檔會讓這條規則等於沒寫。

### 7. 任務順序讓每一步都跑得完驗收

分三段推進，每段結束時 `rebuild --verify` 都是綠的：

1. **清雜訊**（不動 CSV 欄位）：刪 `.qc.json`、刪 `migrate_workdirs.py`、`is_refined()` 簡化、`.B.work` → `.work`、`1-cues` 拿掉 `video`。現有逐 byte 驗法照舊通過。
2. **換驗法**（先改驗、再改資料）：`rebuild --verify` 同時接受舊表與不變量，加子集檢查。
3. **換資料**：六張表重寫、刪目錄與兩份 inventory、`episodes.py` 上線、publish／plan_month 改動、舊驗法拆除。

**為什麼先換驗法**：反過來的話，資料一改完驗收就紅，接下來每一步都在黑暗中前進。

## 完整檔案樹

```
scripts/
├── languages.py                    ★新  族語別／語言別代號對照表＋反查
│                                        吃：無（表隨 repo 走）
├── catalogue_checks.py             ★新  六張表的共同欄位＋逐列不變量
│                                        吃：讀好的列；由兩支 rebuild 呼叫
├── datadirs.py                      改  只改註解（inventory／catalogue 不存在了）
├── errors.py  lowpri.py                 不動
├── ocr/  srtlib/  asrmt/                不動（語料無關）
├── news/
│   ├── episodes.py                 ★新  吃 news/smkul.csv → entry dict
│   │                                    推導 slug／file／pending／播出時段
│   ├── add_episodes.py             ✖刪  手動登記 pending，概念消失
│   ├── migrate_workdirs.py         ✖刪  一次性搬遷，已掃完
│   ├── paths.py                     改  拿掉 CATALOGUE／INVENTORY／load_inventory
│   │                                    is_refined() 簡化成一行
│   ├── tracker.py                   改  FIELDS 11 欄；拿掉 cue_grade／asr_model／
│   │                                    video_length／vision_status／is_pending
│   ├── publish.py                   改  只搬 1-cues；拿掉視覺門；一致不覆寫
│   ├── plan_month.py                改  唯讀，吃 smkul.csv
│   ├── resolve_slug.py              改  吃 smkul.csv
│   ├── sources.py                   改  候選清單吃 smkul.csv 的原始影片檔案位置
│   ├── name_catalogue.py            改  --check 驗 smkul.csv 的 成果檔名 欄
│   ├── rebuild.py                   改  子集不變量＋CSV 不變量檢查
│   ├── make_srt.py                  改  不寫 .qc.json
│   ├── asrmt_run.py                 改  音檔改從影片抽；.B.work → .work
│   └── gap_sheets.py  ingest.py  batches.py  rescan_band.py
│       blank_runs.py  migrate_strips.py     改  .B.work → .work
├── aiyalaeho/
│   ├── episodes.py                 ★新  吃兩張 smkul 表 → entry dict
│   ├── paths.py  tracker.py  publish.py  rebuild.py   改
│   ├── catalogue.py                 改  語言表搬走，改成 import
│   ├── make_srt.py  make_all.py     改  不寫 .qc.json
│   ├── langcheck/report.py          改  表頭 15 欄／12 欄
│   └── text/pairs.py                改  15 欄、集→集數、補成果檔名
└── transcode/archive_batch.py       改  只吃 smkul.csv（原本吃三份）

tests/
├── languages/
│   ├── __init__.py                 ★新
│   ├── README.md                   ★新  這組的 spec × scenario × 測試檔幾列
│   └── test_languages.py           ★新
├── catalogue/
│   ├── __init__.py                 ★新
│   ├── README.md                   ★新  同上
│   └── test_catalogue_checks.py    ★新
├── news/
│   ├── test_episodes.py            ★新
│   ├── test_migrate_workdirs.py    ✖刪
│   └── test_tracker_columns.py  test_tracker_row.py  test_publish_gate.py
│       test_publish_refined_only.py  test_plan_month.py  test_rebuild_sources.py
│       test_paths.py  test_sources.py  test_resolve_slug.py  test_pending.py
│       test_make_srt.py  test_name_catalogue.py  test_asrmt_run.py      改
├── aiyalaeho/
│   ├── test_episodes.py            ★新
│   ├── test_tracker.py  test_publish.py  test_rebuild.py  test_paths.py
│   │   test_catalogue.py                                                改
│   ├── langcheck/test_report.py                                         改
│   └── text/test_pairs.py                                               改
├── transcode/test_archive_batch.py                                      改
└── README.md                        改  結構圖＋指到 tests/languages/README.md

tox.ini                              改  unittest 補 tests/aiyalaeho、tests/tools、
                                         tests/languages、tests/catalogue

Kari-SRT/
├── ilrdf-corpus.csv                ✖刪
├── news/
│   ├── inventory.json              ✖刪
│   ├── smkul.csv                    改  11 欄 969 列，列序照成果檔名
│   │                                    人維護；不變量由 rebuild --verify 驗
│   └── 1-ocr/
│       ├── 1-cues/<月>/<名>.json     改  拿掉 video 欄；由 publish 放入
│       ├── 2-vision/<名>/b*.tsv          Claude Vision 直接寫入
│       └── 3-srt/<月>/<名>.srt       改  同名 .qc.json 刪除；由組裝流程直接寫入
└── aiyalaeho/
    ├── inventory.json              ✖刪
    ├── smkul.csv                    改  9 欄
    ├── smkul-字幕版型異常.csv        改  9 欄（理由併入備註）
    ├── 1-ocr/3-srt/<名>.srt          改  同名 .qc.json 刪除
    ├── 1-ocr/4-語言檢查/逐條語言標記.csv   改  15 欄  ← report.py 吃重建的 SRT
    ├── 1-ocr/4-語言檢查/逐集語言分布.csv   改  12 欄  ← 同上
    └── text/1-句對.csv               改  15 欄  ← pairs.py 吃上字文稿暫存目錄
```

各 `Kari-SRT/` 子目錄的 README 要同步改：欄位表、「誰讀它」那幾段、以及不再提 `inventory.json` 與節目目錄。

## spec × scenario × 測試檔對照表

| spec | scenario | 測試檔 |
|---|---|---|
| episode-catalogue | 加一批不可以整檔重寫：列序照 `成果檔名` 排（舊表四次改動全是全檔重寫 75/75、36/36、36/36、73/34） | `news/test_tracker_columns.py` |
| episode-catalogue | `播出時段` 由 `節目名稱` 推導（983 列零例外）；節目名稱不在三種新聞之列時指名中止，不可推出空字串 | `news/test_episodes.py` |
| episode-catalogue | `slug` 推導集數要補 3 碼（`2021_032_…` 不是 `2021_32_…`），133 筆零例外 | `news/test_episodes.py` |
| episode-catalogue | `成果檔名` 與識別欄互推不一致時指名中止，不可就地改寫那一格 | `news/test_name_catalogue.py` |
| episode-catalogue | 沒影片的列不進表（新聞 983→969；開會了 80 缺帶、89/97/124 重播消失） | `news/test_episodes.py`、`aiyalaeho/test_episodes.py` |
| episode-catalogue | `語言別` 空不是錯——新聞 983 列只有 1 列（`魯凱語-霧台`）查得出變體 | `languages/test_languages.py`、`news/test_episodes.py` |
| episode-catalogue | `太魯閣` 的代號是 `trv-x-truku`（變體代號），不可因為帶 `-x-` 就改成 `trv` | `languages/test_languages.py` |
| episode-catalogue | 16 種族語別全部查得到代號；查不到時指名該列，不留空也不編一個 | `languages/test_languages.py` |
| srt-data-store | `file` 是 basename(`原始影片檔案位置`)，但該欄 122 列是分號黏的候選清單，不可直接 basename 整格 | `news/test_episodes.py`、`news/test_sources.py` |
| srt-data-store | `pending` 由 `3-srt/<成果檔名>.srt` 在不在推導（133 筆零例外） | `news/test_episodes.py` |
| srt-data-store | 子集不變量 `3-srt ⊆ 2-vision ⊆ 1-cues`；下游多出來要指名是哪一集在哪一層缺 | `news/test_rebuild_sources.py`、`aiyalaeho/test_rebuild.py` |
| srt-data-store | `1-cues` 有而 `3-srt` 沒有是正常（分階段入庫），驗證不得報缺件 | `news/test_rebuild_sources.py` |
| srt-data-store | publish 比的是 `redump_store.dump()` 正規化後的字串——比 work dir 原始檔會每次判成不同（曾一次重寫 74 個沒變的檔） | `news/test_publish_refined_only.py` |
| srt-data-store | 粗切時間軸擋在門外；視覺辨識沒讀完**不擋**（那道門拿掉了） | `news/test_publish_gate.py` |
| srt-data-store | `1-cues/*.json` 不再有 `video` 欄（原本 114 個檔全是絕對路徑，把資料綁在一台機器上） | `news/test_rebuild_sources.py`、`news/test_redump_store.py` |
| srt-data-store | 組裝之後 `3-srt/` 旁邊沒有 `.qc.json`（零個生產程式讀它，只有一個測試在斷言它存在） | `news/test_make_srt.py`、`aiyalaeho/test_publish.py` |
| srt-data-store | 孤兒檔：`3-srt/` 有檔而目錄查無該 `成果檔名` 時指名失敗 | `news/test_rebuild_sources.py` |
| srt-data-store | 兩張開會了表欄位完全相同，只能靠在哪個檔分辨 → 異常表每列 `備註` 非空，空白要指名 | `aiyalaeho/test_tracker.py` |
| episode-sourcing | `plan_month` 唯讀：跑完 Kari-SRT 一個 byte 都沒變（原本會寫 pending 條目） | `news/test_plan_month.py` |
| episode-sourcing | 分號並列的候選逐條都查得回那一列，不因取字串尾段只剩最後一條 | `news/test_sources.py`、`news/test_resolve_slug.py` |
| aiyalaeho-sourcing | 沒有影片的集數不留痕——不在清單、不在兩張表、也沒有錯誤訊息 | `aiyalaeho/test_catalogue.py` |
| aiyalaeho-sourcing | 欄名是 `語言別代號` 不是 `語言代號`；`德路固` 是 `trv-x-trk`，不可混成太魯閣的 `trv-x-truku` | `aiyalaeho/test_catalogue.py`、`languages/test_languages.py` |
| aiyalaeho-language-check | 表頭 15 欄／12 欄；`本集族語` 併入 `族語別(中)`，不得再以該名出現 | `aiyalaeho/langcheck/test_report.py` |
| aiyalaeho-language-check | 前七欄與 `smkul.csv` 同一集那一列逐欄相同 | `aiyalaeho/langcheck/test_report.py` |
| aiyalaeho-text-corpus | `集` 拆 `集數` 要吃兩種分隔：`開會001_賽夏族`（底線）與 `開會041-旅北阿美`（連字號） | `aiyalaeho/text/test_pairs.py` |
| aiyalaeho-text-corpus | 尾段（主題字樣）不另設欄位——`來源文字檔檔案位置` 前綴已含它，55785 列零例外 | `aiyalaeho/text/test_pairs.py` |
| aiyalaeho-text-corpus | `成果檔名` 指向不存在的 SRT（`開會了_001_SaySiyat_賽夏`），不變量要放行 | `aiyalaeho/text/test_pairs.py`、`aiyalaeho/test_rebuild.py` |
| aiyalaeho-text-corpus | 由 `語言別代號` 反查補齊 `族語別(英)`／`族語別(中)`／`語言別`（`ami-x-frng` → Amis／阿美／馬蘭） | `languages/test_languages.py`、`aiyalaeho/text/test_pairs.py` |
| asr-bilingual-srt | 音檔從本機影片抽音軌，過程不向外部主機索取音檔；影片一份都不在時指名中止 | `news/test_asrmt_run.py` |

## Risks / Trade-offs

**驗收中途是半失效的** → 任務分三段（決策 7），先換驗法再換資料，每段結束都跑得完 `rebuild --verify`。

**`smkul.csv` 從 75 列變 969 列，是一次大量的資料產生** → 由既有的 `ilrdf-corpus.csv` 一次轉出，轉出程式保留在 change 目錄下當作一次性腳本，不進 `scripts/`；轉出後以不變量檢查驗過才算數。

**`.B.work` → `.work` 會撞到既有工作目錄** → 現況 work dir 是 0 個（已驗證），所以這次沒有要搬遷的東西；但改名要連 `already_read()` 那道防覆寫保護一起搬過去，否則重跑 `gap_sheets` 會蓋掉已校讀的 transcripts。

**音檔改從影片抽，單獨重跑 ASR 時要下載 GB 級的影片而非幾十 MB 的 mp3** → 取音軌時依序找本機暫存原檔、封存 mkv，都沒有才從 SFTP 取；切 cue 與 ASR 排在一起就只下載一次。SFTP 也取不到時指名中止，不靜默跳過。

**六張表同時改欄位，中間任一張沒跟上就 join 不起來** → 前七欄由同一份程式產生（`episodes.py` 與 `languages.py`），不在六個地方各寫一次。

**`tests/aiyalaeho` 本來就沒進 `tox -e unittest`** → 這次補上；補上之後可能會暴露既有的失敗，那是好事，但要算進工時。
