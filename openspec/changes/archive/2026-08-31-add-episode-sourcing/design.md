# 設計：一集配一支檔、月份工作單位、store 照月份分層

## Context

動機見 proposal.md — Why。這裡只列會左右做法的現況與限制：

- `ilrdf-corpus.csv` 是唯一的目錄正本，1,029 列、1,100 條路徑。來源欄
  以分號並列多條路徑者 122 列；目前 `resolve_slug.load()` 以
  `os.path.basename(整串)` 建索引，只索引得到最後一條。
- 資料夾與播出月份不是一對一：6 個播出月份跨兩個資料夾，
  `110.1-110.10/7月/` 的 140 條中有 66 條是 2 月的節目。
- 影片走 SFTP、切完 cue 立刻刪除，磁碟峰值＝一支影片＋work dir。所以
  「掃本機資料夾建 inventory」這條路已經沒有東西可掃。
- `inventory.json` 是逐欄位重建後寫回的，`paths.py` 對未宣告欄位會中止
  （`tests/news/test_paths.py`）——這是既有防線，本設計刻意不去動它。
- 完整性的實測基礎（35 集）：母帶常態約 6.30 MB/s，兩支不完整者為
  2.83、3.44 MB/s；時長從 673.8 s 到 2960 s 都有，且不成族（見 D3）。
- 三個引擎 package（`ocr/`、`srtlib/`、`asrmt/`）刻意與語料無關，不得
  讓它們知道目錄檔存在。

## Goals / Non-Goals

**Goals**

- 換一個月份只換一個參數，`scripts/` 不必動。
- 會選錯的地方全部變成「明講的規則 + 選不出來就略過」，不留安靜取第
  一條的路徑。
- 逐集判定（哪支檔、完不完整）只存在於資料側；程式側只留規則與門檻。
- 階段目錄的路徑組法收斂成單一出口，日後再加分層只改一處。

**Non-Goals**

- 不改視覺辨識、SRT 組裝、語音側任何演算法；本設計不碰引擎 package。
- 不改 `presets.json` 與版型判準（`verify_band.py` 那條防線原樣保留）。
- 不自動修正目錄的編目錯誤——規則只負責「選得出來」或「說選不出來」，
  修目錄是人的事。
- 不處理 `族語節目/開會了/`（46 列無播出日期），本設計只涵蓋族語新聞。

## Decisions

### D1 — 選擇規則做成純函式，與 I/O 分離

`sources.py` 只吃「目錄列 + 候選路徑清單」，吐「選定路徑」或「略過
原因」。不讀檔、不連線、不寫 inventory。

*為什麼*：這是整個 change 裡唯一會安靜做錯的地方，必須能用合成 fixture
把四條規則與各種歹例（分號、時段錯字、同名不同夾、兩集撞一支）全部
釘死。混進 I/O 就只能靠端對端測試，那對這種組合爆炸沒有覆蓋力。

*替代方案*：把規則寫進 `add_episodes.py` 既有的 `entry_for()`。否決——
那支同時在讀 inventory、組條目、決定新增或取代，規則塞進去就測不動。

### D2 — 一支檔只准一集用，這條在「全月一起看」的層次判

規則 1–3 是逐集可判的，規則 4（撞檔）必須看過整個月才知道。因此
`sources.py` 提供兩層 API：逐集的候選收斂，與整批的撞檔檢查；
`plan_month.py` 先跑前者、再跑後者。

*為什麼*：目錄裡實際有三組兩集指到同一支檔（都在 2021-03）。若只逐集
判，先處理到的那一集會把檔案取走，後一集才報錯——誰先誰後決定誰拿到，
這是不可重現的行為。

### D3 — 完整性不自動判定，只記錄長度

`truncated` 與 `partial` 維持人工註記；影片長度記進 `smkul.csv`，由人
自行判讀。

*為什麼*：原設計要做兩條自動判定，實作時兩條都站不住。

時長那條：把 35 集的時長列出來，「兩個時長族」的假設對不起來——673.8 s
（已標 partial）、1440–1500 s（13 集，春節那週的短版）、**2118 s（1 集，
已交付、無標記）**、2880–2960 s（20 集）。2118 s 那集卡在兩族中間，cue
密度（0.366／秒）與正常集數（0.377）一樣，任何族的門檻都會把它誤判。

位元率那條判得準（完整母帶 6.30 MB/s，兩支壞的 2.83／3.44），而且它擋的
是別的東西：**伺服器上那份本身就不完整**，這種情況遠端 size 等於本機
size、`ffprobe` 也照樣宣稱完整，位元組數比對擋不住。但它只有母帶量得出
基準值（mp4 沒有），也就是說只對 2 月那批有效；為它多養一個模組、一組
門檻、一份測試，換到的把關面太窄。已知的兩支壞母帶當初就是人發現的，
這條路維持原樣，手抄的 `TRUNCATED` dict 則隨 `build_inventory.py` 一起
消失。

*替代方案*：時長兩族 ±10%（35 集就有 1 個假警報）、與同批同時段兄弟集
比對（判得準，門檻要持續維護）、保留位元率模組並接進 `fetch_sftp.sh`。
三個都否決。

### D5 — 月份鍵從 `srt_name` 推導，不另存

`stage_path(stage, srt_name)` 取 `srt_name` 前 8 碼（`YYYYMMDD`）組出
`YYYY-MM`。目錄與檔名因此帶有重複資訊。

*為什麼*：重複是刻意的。目錄讓人一眼看出這個月做了多少、git diff 依月份
成塊；檔名讓單一字串仍能定位一集（`srt-data-store` 既有要求）。多存一份
對應表則會引入「兩份真相要同步」的問題——`paths.py` 的註解已經因為
inventory 曾有兩份而寫過一次教訓。

### D6 — `stage_path()` 是階段目錄的唯一出口

階段常數（`KARI_CUES` 等）降級為「基底目錄」，11 支程式一律改呼叫
`paths.stage_path()` 取實際路徑，並在其中走既有的 `check_name`。

*為什麼*：分層若散落在 11 支程式裡，日後任何調整都要再改 11 次，而且
漏掉一支的症狀是「組裝出空字幕」——不會報錯。收斂成一個出口後，
`tests/news/test_paths.py` 一支測試就守得住。

### D7 — `fetch_sftp.sh` 照計畫抓，遠端 `ls` 仍保留

參數改為播出月份；下載清單來自 inventory 中該月的 pending 條目。遠端
`ls` 不取消，但只 ls 計畫碰到的資料夾，用途從「決定要抓什麼」縮成
「取得位元組數以驗證下載完整」。

*為什麼*：位元組數比對是既有的防線（下載截斷 `ffprobe` 看不出來），
不能因為有了計畫就省掉。但「要抓什麼」由計畫決定，跨資料夾才成立。

### D8 — `build_inventory.py` 收起來，函式各歸其位

`slugify()`／`srt_name()` 移入 `resolve_slug.py`（命名的單一出處，
`slug_for()` 本來就在那），`merge()` 移入 `plan_month.py`（合併進
inventory 是計畫的事），掃描本機資料夾的部分與 `TRUNCATED` dict 一併
刪除。

*為什麼*：留一支沒人跑的程式，下一個讀 code 的人得先弄清楚它還算不算
數；而它是 `add_episodes` 的 import 來源，看起來又像還在服役。

### D9 — 保留「手動指定路徑」補做單集的入口

`add_episodes.py` 改吃 `sources.py` 的結果，但直接給路徑的用法不刪。

*為什麼*：略過的集數（全語料 2 集無法決定 + 3 組撞檔）判完以後就是走
這條補做。沒有這條，人判完了也沒有地方把判斷放進去。

## 檔案樹

`+` 新增、`~` 修改、`-` 刪除、`→` 搬移；未列出者不動。

### 程式

```
scripts/
├── datadirs.py                       （不動）
├── errors.py                         （不動）
├── ocr/  srtlib/  asrmt/             （不動：引擎與語料無關）
├── README.md                       ~ news/ 檔案表更新
└── news/
    ├── sources.py                  + 選擇規則（純函式）
    │      吃：目錄列＋候選路徑清單
    │      吐：選定路徑，或略過原因＋候選清單
    ├── plan_month.py               + 月份計畫
    │      吃：播出月份、ilrdf-corpus.csv、inventory.json
    │      吐：pending 條目寫回 inventory；略過清單印給人看
    │      內含：自 build_inventory 移入的 merge()
    ├── paths.py                    ~ 加 stage_path(stage, srt_name)
    ├── resolve_slug.py             ~ load() 改整條路徑索引
    │                                 接收 slugify()／srt_name()
    ├── add_episodes.py             ~ 改吃 sources.py；保留手動指定路徑
    ├── build_inventory.py          - 刪除（函式移出後）
    ├── fetch_sftp.sh               ~ 參數改月份，照計畫抓
    ├── gap_sheets.py               ~ ┐
    ├── batches.py                  ~ │
    ├── ingest.py                   ~ │
    ├── make_srt.py                 ~ │ 唯一改動：階段路徑
    ├── make_all.py                 ~ ├ 改呼叫 paths.stage_path()
    ├── publish.py                  ~ │
    ├── tracker.py                  ~ │ ＋長度欄（由 1-cues 推導）
    ├── rebuild.py                  ~ │
    ├── asrmt_run.py                ~ │
    ├── asrmt_batch.py              ~ ┘
    ├── presets.json                  （不動）
    ├── run_cues.sh                   （不動：本機那條路仍在）
    ├── verify_band.py                （不動）
    ├── refine_cues.py                （不動）
    └── README.md                   ~ 現況數字改指向正本、舊路徑更正
```

### 測試（鏡射模組名）

```
tests/
├── README.md                       ~ spec × scenario 表新增 episode-sourcing
├── news/
│   ├── test_sources.py             + 分號多來源／母帶優先／時段決勝／
│   │                                 時段錯字／同名不同夾／撞檔兩集皆略過／
│   │                                 略過不進 inventory
│   ├── test_plan_month.py          + 跨資料夾選集／非本月不選／
│   │                                 登記先於下載／重跑不重複登記／
│   │                                 無影片者僅計數
│   ├── test_paths.py               ~ store 佈局含月份層；stage_path 推導與
│   │                                 名稱保護
│   ├── test_add_episodes.py        ~ 改吃 sources.py；手動指定路徑仍可用
│   ├── test_sftp_cli.py            ~ fetch 改吃月份計畫
│   ├── test_inventory.py           → 隨 slugify／srt_name 移入，改名為
│   │                                 test_resolve_slug.py
│   ├── test_build_inventory_merge.py → 隨 merge() 移入，改名為
│   │                                 test_plan_month_merge.py
│   ├── test_make_srt.py            ~ ┐
│   ├── test_ingest.py              ~ │
│   ├── test_batches.py             ~ │ fixture 的 store 路徑
│   ├── test_vision_complete.py     ~ ├ 加一層月份
│   ├── test_pending.py             ~ │
│   ├── test_tracker_home.py        ~ │
│   └── test_tracker_row.py         ~ ┘
├── e2e/
│   ├── fixture.py                  ~ 合成 store 加一層月份
│   └── test_roundtrip.py           ~ 同上
└── ocr/  srtlib/  asrmt/             （不動）
```

### 資料（Kari-SRT，內容零改動、只動路徑）

```
Kari-SRT/
├── ilrdf-corpus.csv                  （節目目錄正本，跨語料所以在頂層；
│                                       重建不讀它，規劃新月份要它）
└── news/
├── inventory.json                    （不分層；plan_month／add_episodes／
│                                       publish 寫；truncated／partial 人工註記）
├── smkul.csv                         （不分層；publish 寫；＋影片長度欄，
│                                       由 1-cues 的時間軸推導）
├── 1-ocr/
│   ├── 1-cues/       2021-02/<srt_name>.json        ← fetch_sftp（cues 階段）
│   ├── 2-from_rtf/   2021-02/<srt_name>.json        ← 歷史產物，不再產生
│   ├── 3-vision/     2021-02/<srt_name>/bNN.tsv     ← 視覺辨識＋ingest
│   ├── 4-vision-rtf/ 2021-02/<srt_name>/bNN.tsv     ← 歷史產物，不再產生
│   ├── 5-report/     rtf-vs-vision.{json,md}        （不分層：跨集）
│   └── 6-srt/        2021-02/<srt_name>.srt|.qc.json ← make_all／publish
└── 2-asr/
    ├── 1-words/      2021-02/<srt_name>.json        ← asrmt（asr 階段）
    ├── 2-entries/    2021-02/<srt_name>.json        ← asrmt（投影階段）
    ├── 3-srt-raw/    2021-02/<srt_name>.srt         ← asrmt（render，交付終點）
    ├── 4-srt-ai/     2021-02/<srt_name>.srt         ← align 延伸，指名才產
    ├── 5-align/      2021-02/<srt_name>.{json,md}   ← align 延伸，指名才產
    ├── 6-srt-complete/ 2021-02/<srt_name>.srt       ← align 延伸，指名才產
    └── mt-cache/     *.jsonl                        （不分層：跨集共用）
```

`kithann/`（gitignore）不在本設計範圍內變動結構；work dir 仍為
`out/mxf/<slug>.work`，只是內容改由計畫驅動產生。

## Risks / Trade-offs

- **搬 35 集的檔案把資料弄壞** → 搬移前後各跑一次
  `rebuild --verify`，並逐 byte 比對 `6-srt/`。這條進不了 CI（Kari-SRT
  是私有 repo），所以列為明確的驗收任務，不是順手做。
- **11 支程式改路徑時漏掉一支** → 症狀是組裝出空字幕、不會報錯。緩解：
  階段常數降級為基底目錄後，任何仍用舊拼法的呼叫點會拼出不存在的路徑
  而失敗；再加上 `test_paths.py` 守著唯一出口。
- **規則在未來的月份選錯** → 已用整份目錄模擬：931 集中 917 集規則直接
  決定、50 集屬同名不同夾（規則 3 收掉）、2 集無法決定、3 組撞檔、14 集
  無影片。2021 年 1–2 月待判為 0。但這是對**目錄**的模擬，目錄本身若與
  伺服器實況不符仍會落空——位元組數比對與 `verify_band` 是後續防線。
- **門檻寫在程式裡，調整仍要改 code** → 接受。門檻是引擎知識，且改門檻
  本來就該經 review；被消滅的是逐集判定，那才是每月都會變的東西。
- **`build_inventory.py` 刪除後，若日後又需要掃本機資料夾** → 從
  git 歷史取回即可；為了一個已經沒有輸入的流程留一支活程式，代價更高。

## Migration Plan

1. 先做程式側（新模組＋`stage_path()`），此時 store 尚未搬，測試以
   fixture 涵蓋新舊兩種佈局中的新佈局。
2. 搬 Kari-SRT：`git mv` 逐階段目錄，內容不動。
3. 搬完立刻跑 `rebuild --verify` 與 `tox -e unittest`、`tox -e flake8`。
4. 通過後才刪 `build_inventory.py`、才把 `fetch_sftp.sh` 切到月份介面。
5. 回滾：步驟 2 的搬移是純 `git mv`，`git revert` 即可還原；程式側與資料
   側分成兩批提交，互不牽連。
