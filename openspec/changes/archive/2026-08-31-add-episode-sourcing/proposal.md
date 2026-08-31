# 一集配一支檔：來源選擇規則化、工作單位改播出月份、store 照月份分層

## Why

2021 年 2 月那 35 集是一集一集用手配出來的：哪一支檔對哪一集、哪支母帶
傳不完整，都是人看過以後寫進程式或用手打進指令。要繼續做 1 月（70 集）
以及後面十幾個月（約 1,065 集），這套做法每個月都會逼人改 `scripts/`，
而且有兩個地方會**安靜地做錯**：

- `ilrdf-corpus.csv` 的「影片檔案位置」欄有 122 列是分號黏起來的多來源，
  但 `resolve_slug.load()` 對整串取 `basename`，只索引得到最後一條——
  **78 個檔名查不到**（涉及 72 集，其中 63 集是 2 月），查不到就退回檔名
  stem，slug 與 metadata 全空，而且不報錯。
- 同一列可能列出好幾條候選（編目時沒把握），程式沒有政策就取第一條。
  例如 2021-02-06 晚間排灣列了四條，第一條檔名寫「午間」——照現在的行為
  會拿午間那支影片去做晚間這集，整集字幕錯位，沒有任何檢查會發現。

另外兩件事現在也綁在程式碼裡：`build_inventory.py` 用一個手抄的
`TRUNCATED` dict 記「哪兩支母帶傳不完整」，下個月再遇到一支就得再改一次
程式；`fetch_sftp.sh` 的工作單位是「SFTP 資料夾」，但**資料夾不等於月份**
——有 6 個播出月份跨兩個資料夾（2021-02 散在 `2月原始mxf檔` 與 `7月`），
而 `7月/` 底下 140 條裡有 66 條其實是 2 月的節目。

## What Changes

- **新增來源選擇規則**（`scripts/news/sources.py`）：從目錄的候選清單
  選出這集要用的那一支，四條規則依序套用——
  1. **mxf 母帶優先**（有 mxf 就不看 mp4）
  2. **檔名裡的時段要跟這集的時段相符**（「五間」這種錯字算作無時段，
     不得當成另一個時段）
  3. 剩下的候選若**只是同一個檔名放在不同資料夾**，視為同一份，任取
  4. **一支檔只准一集用**——兩集選到同一支，兩集都略過
  仍剩兩條以上就**略過該集並列入報告**，不中止整批；目錄本來就標示
  無影片的（14 集）不算待判，報告末尾一行帶過。
- **完整性不自動判定**：`truncated`（來源不完整）與 `partial`（來源
  本身就短）維持人工註記。原本規劃的兩條自動判定，實作時量過都站不住
  ——時長不成族（48 分 21 集、24 分 13 集，還有一集 2,118 秒卡在中間且
  已交付），位元率只有母帶量得出基準、只擋伺服器端的半截檔。手抄的
  `TRUNCATED` dict 隨 `build_inventory.py` 一併消失，這是原本要解的問題。
  改為**在 `smkul.csv` 記錄影片長度**（由 `1-cues/` 的時間軸推導），
  由人自行判讀。
- **新增月份工作單位**（`scripts/news/plan_month.py`）：吃 `2021-01`，
  從目錄選出該月全部集數（可跨資料夾），逐集帶遠端路徑，寫成 pending
  條目進 `inventory.json`——**登記發生在抓檔之前**，抓檔照計畫走。
  `fetch_sftp.sh` 的參數從資料夾改成月份。
- **BREAKING：Kari-SRT 逐集資料照播出月份分一層目錄**——
  `1-ocr/{1-cues,2-from_rtf,3-vision,4-vision-rtf,6-srt}` 與
  `2-asr/{1-words,2-entries,3-srt-raw,4-srt-ai,5-align,6-srt-complete}`
  底下加一層 `<年-月>/`（例：`1-cues/2021-02/<srt_name>.json`）。
  跨集的 `1-ocr/5-report/`、`2-asr/mt-cache/` 與總表
  `inventory.json`、`smkul.csv` 維持平的。月份鍵從 `srt_name` 前 8 碼推，
  不另存一份。資料值逐 byte 不變、只動路徑。
- **BREAKING：`build_inventory.py` 收起來**——它掃的是本機
  `~/ilrdf-corpus/2月/` 資料夾，而影片現在走 SFTP、切完 cue 就刪，沒有
  資料夾可掃。`slugify()`／`srt_name()` 移入 `resolve_slug.py`（命名的
  單一出處），`merge()` 移入 `plan_month.py`，手抄的 `TRUNCATED` dict
  刪除。
- **修 `resolve_slug.load()`**：改用整條相對路徑當鍵，分號多來源逐條
  建索引。
- **節目目錄搬進 store**：`ilrdf-corpus.csv` 從 gitignore 的
  `kithann/tongan/` 搬到 `Kari-SRT/ilrdf-corpus.csv`（跨語料，所以放
  頂層）。它重生不出來，而每個新月份的規劃全靠它；放在工作區換一台
  機器就沒了。離線重建不讀它，實測拿掉它 `rebuild --verify` 照樣過。
- `paths.py` 新增 `stage_path(stage, srt_name)` 作為階段目錄取用的單一
  出口；11 支拼路徑的程式全部改走它。

## Capabilities

### New Capabilities

- `episode-sourcing`：一集配哪一支檔、一批的工作單位是什麼。涵蓋選擇
  規則的優先序與決勝、選不出來時的略過與回報、完整性維持人工註記而
  只記錄長度、播出月份作為批次單位且登記先於抓檔。

### Modified Capabilities

- `srt-data-store`：「命名鍵統一為 srt_name」這條要求擴充——逐集資料
  的存放位置從「階段目錄下平放」改為「階段目錄下依播出月份分一層」，
  月份鍵由 `srt_name` 推導；跨集產物與總表不分層。離線重建、pending
  語意、整批定版等其他要求不變。

## Impact

**新增檔案**

```
scripts/news/sources.py          來源選擇規則（純函式）
scripts/news/plan_month.py       月份計畫：選集→寫 pending→出略過報告
tests/news/test_sources.py
tests/news/test_plan_month.py
```

**修改檔案**

```
scripts/news/paths.py            加 stage_path()；階段常數改為基底；
                                 CATALOGUE 指向 store
scripts/news/resolve_slug.py     load() 改路徑索引；接收 slugify/srt_name
scripts/news/add_episodes.py     改用 sources.py；保留手動指定路徑那條
scripts/news/fetch_sftp.sh       參數改月份，照計畫抓，只 ls 計畫碰到的夾
scripts/news/gap_sheets.py       ┐
scripts/news/batches.py          │
scripts/news/ingest.py           │
scripts/news/make_srt.py         │ 只有一種改動：
scripts/news/make_all.py         ├ 拼階段路徑的地方改呼叫 paths.stage_path()
scripts/news/publish.py          │
scripts/news/tracker.py          │
scripts/news/rebuild.py          │
scripts/news/asrmt_run.py        │
scripts/news/asrmt_batch.py      ┘
scripts/README.md                news/ 檔案表更新
scripts/news/README.md           現況數字改為指向正本；舊路徑更正
tests/README.md                  spec × scenario 表新增 episode-sourcing
tests/news/test_paths.py         store 佈局與 stage_path
tests/news/test_add_episodes.py  改吃 sources.py 的結果
tests/news/test_build_inventory_merge.py → 隨 merge() 移入 plan_month
tests/news/test_inventory.py     → 隨 slugify/srt_name 移入 resolve_slug
tests/news/test_make_srt.py      ┐
tests/news/test_ingest.py        │
tests/news/test_batches.py       │ fixture 的 store 路徑加一層月份
tests/news/test_vision_complete.py
tests/news/test_pending.py       │
tests/news/test_tracker_home.py  │
tests/news/test_tracker_row.py   ┘
tests/e2e/fixture.py             合成 store 加一層月份
tests/e2e/test_roundtrip.py
```

**刪除檔案**

```
scripts/news/build_inventory.py  （函式移出後刪除）
```

**資料搬移（Kari-SRT，內容零改動）**

```
kithann/tongan/ilrdf-corpus.csv  →  Kari-SRT/ilrdf-corpus.csv
Kari-SRT/news/1-ocr/{1-cues,2-from_rtf,3-vision,4-vision-rtf,6-srt}/
    <srt_name>…  →  2021-02/<srt_name>…
Kari-SRT/news/2-asr/{1-words,2-entries,3-srt-raw,4-srt-ai,5-align,
                     6-srt-complete}/
    <srt_name>…  →  2021-02/<srt_name>…
Kari-SRT/news/1-ocr/5-report/、2-asr/mt-cache/、
Kari-SRT/news/{inventory.json,smkul.csv}          維持原位
```

**驗收**：`rebuild --verify` 在新路徑照樣通過、`6-srt/` 逐 byte 相同，
是搬移沒有破壞的唯一證明（Kari-SRT 是私有 repo，這條進不了 CI）。

**不受影響**：`scripts/ocr/`、`scripts/srtlib/`、`scripts/asrmt/` 三個
引擎 package 一行不動——它們本來就與語料無關。`presets.json` 不動。
