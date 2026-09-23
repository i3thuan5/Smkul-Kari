## Context

動機見 proposal.md〈Why〉。這裡只記做法所需的現況與量測。

**現況（一集 48 分鐘、約 819 個邊界）**

```
切 cue     ffmpeg 解整集 → fps=5 濾鏡重新取樣 → 14,400 格 → 狀態機
           同一趟寫出圖條（狀態機留每條 cue 最好的一格）
精修       819 支 ffmpeg，各自 -ss 跳到邊界，fps=25 取 13 格
```

**這次量到的數字（同一台機器，量測時另有批次在跑，比例可信、絕對值偏保守）**

| 量測 | 結果 |
|---|---|
| 來源格率（3 支 mp4、3 支 mkv、2 段 mxf） | 全部 30000/1001 = 29.97 |
| 解碼成本 | 每 120 秒影片 42.7 核心秒（預設執行緒） |
| 一個精修視窗（跳轉＋解 0.48 秒） | 實際 0.79 秒、**4.35 核心秒**——其中約 3.4 秒是 ffmpeg 啟動固定成本 |
| 遮罩 | 每格 3.25 毫秒（單核） |
| 執行緒效率 | 1 緒 31.6 核心秒／2 緒 32.4／4 緒 37.1／8 緒 40.8／16 緒 46.0（同一份工） |
| `fps=5` 濾鏡挑到的畫面 | 比它標記的時間**晚約 0.067 秒（兩格）**，偏移量隨集長緩慢漂移 |
| 新舊精修結果差異（7 集、1–7 月各一） | 中位 0.010 秒、p95 0.022 秒、超過 0.05 秒約 0.5% |
| CONFIRM=3 的影響 | 放棄精修的邊界從 10–23 個增為 24–65 個（精度變差） |

**一集的 CPU 帳**

| | 解碼 | 精修 | 遮罩 | 合計 |
|---|---|---|---|---|
| 現在（預設執行緒） | 17 | 59 | 1.4 | 77 核心分鐘 |
| 本設計（2 執行緒） | 13＋13 | — | 1.4 | **27 核心分鐘** |

## Goals / Non-Goals

**Goals**

- 一集的機器成本從 77 降到約 27 核心分鐘，整批吞吐量從約 12 集／小時提高到約 26 集／小時。
- 取樣時間與判斷用畫面一致（修掉 `sample_ts` 對不上的問題）。
- 精修維持獨立的第二趟，可單獨重跑。
- 工作目錄可讀：照月份與編號階段分層。

**Non-Goals**

- 不追求把切 cue 與精修併成單一趟解碼（設計 A）。下游 OCR 約 10 集／小時，26 已足夠；A 需要環形緩衝與因果延遲補償，且失敗時會安靜退化。
- 不重切、不重修已入庫的集數；不回補已入庫的 `sample_ts`。
- 不動開會了的工作目錄位置（只共用引擎程式碼）。

## Decisions

### 一、兩趟解碼，不是一趟

一集跑兩支 ffmpeg：第一趟切 cue，第二趟精修。

- **為什麼不是現在的 819 支**：每支的固定成本 3.4 核心秒 × 819 ≈ 46 核心分鐘，是整條線最大的浪費。
- **為什麼不是一支**（設計 A）：切 cue 是因果的——要看到後面幾格才能確認前面是邊界，此時精修要的畫面已流過管線，必須自備環形緩衝。緩衝太短時程式不會壞、只會放棄精修並沿用粗切值，是安靜退化。省下的第二趟解碼（17 核心分鐘）換來的吞吐量提升在 OCR 這個瓶頸前用不到。
- **代價**：比 A 多解一次整集。接受。

### 二、取樣改以真實時間戳為準

第一趟以原生格率解碼，Python 端依目標時間（k × 0.2 秒）取**最接近**的來源格，時間記該格的真實 pts。

- **為什麼不用 `fps=5` 濾鏡**：量到它挑的畫面比標記時間晚約 0.067 秒，且偏移隨集長漂移。時間軸因此記了一個沒有任何畫面對應的時刻。
- **為什麼不是「固定每 6 格取一格」**：29.97 ÷ 5 = 5.994，固定跳 6 格每步偏 0.0002 秒，一集尾端累積約 0.6 秒。
- **後果**：新切的集數與舊集數的取樣相位不同（差約兩格），cue 集合可能有極少數差異。1–9 月不重切，故為新舊並存，寫入 README。

### 三、精修用 `select` 一次放行所有視窗

第二趟解整集，濾鏡鏈為 `crop → select('between(t,a1,b1)+…') → showinfo`，輸出 rawvideo。

- **時間戳來源**：`showinfo` 印在 stderr 的 `pts_time`，與 stdout 的畫面依序配對。不可用「起點＋第幾格÷fps」推算——select 之後畫面之間有跳號。
- **`-fps_mode passthrough` 是必要的**：預設 rawvideo 輸出為固定格率，ffmpeg 會補重複格填滿 select 挑掉的空檔，畫面數與時間戳就對不上。這次實驗踩過（畫面 832、時間戳 166）。
- **`-nostats`**：進度列與 showinfo 會印在同一行，不關掉會漏抓時間戳。這次也踩過。
- **濾鏡字串很長**（819 個視窗約 25 KB），以 `-filter_script` 傳檔案，不放在命令列。
- **視窗重疊**：相鄰邊界不到 0.48 秒時視窗重疊，同一格 select 只輸出一次，兩個邊界各自依時間取用，不得重複計數。

### 四、CONFIRM 維持 2

量到改成 3 會讓放棄精修的邊界倍增（10–23 → 24–65），這些邊界退回 0.2 秒精度。判準本身不隨格率改變。

### 五、ffmpeg 每支 2 執行緒、同時 6 集

- 2 執行緒的每核效率 0.98，預設（8–9 核）只有 0.67——同一份工多燒 49% CPU。
- 16 核 ÷（2 執行緒 ＋ 約 0.5 核的 Python 端）≈ 6 集。
- 並行度與執行緒數做成可調（環境變數），預設值照本機量測，換機器可改。

### 六、程式分層

引擎層（`scripts/ocr/`）不認識任何一個語料，編排層（`scripts/news/`）只管怎麼排。因此：解碼、取樣、邊界判斷放引擎層；「哪一集、放哪裡、驗收怎麼算」留在編排層。開會了與族語新聞共用引擎層。

### 七、資料夾搬家

一次性腳本，先 dry-run 印出要搬什麼，再實際搬，搬完自檢（舊路徑不再有檔案、新路徑數量相符）。時程上排在 8–9 月 OCR 做完、work dir 暫存刪除之後。

## 檔案樹

```
scripts/
├── ocr/                                引擎層
│   ├── decode.py                  ★新  ffmpeg 讀取。輸入：影片路徑、區域、
│   │                                   （可選）視窗清單。輸出：(真實時間, 畫面)
│   │                                   串流。含 -fps_mode passthrough、-nostats、
│   │                                   -filter_script、showinfo 解析、執行緒數旗標
│   ├── sampling.py                ★新  目標間隔 → 取最接近的來源格。
│   │                                   輸入：時間戳串流與目標間隔；輸出：要判斷的格
│   ├── refine.py                  ★新  邊界判斷。輸入：視窗內的格與粗切邊界；
│   │                                   輸出：新邊界或「無法分辨」。由 refine_cues.py
│   │                                   與（未來）開會了共用
│   ├── cuelib.py                   改  只留遮罩與切段狀態機（stream_region 搬到 decode.py）
│   ├── cli.py                      改  cues 子命令改用 decode＋sampling；
│   │                                   產出 1-cues/cues.json、2-strips/、sample_ts 為真實時間
│   └── band.py、sheets.py 等        不動
├── news/                               編排層
│   ├── refine_cues.py              改  第二趟的 CLI：讀 1-cues → 呼叫 decode（select 視窗）
│   │                                   ＋refine → 寫 3-refined/cues.json；±0.2 驗收、
│   │                                   整集原子寫入、統計分開計數
│   ├── paths.py                    改  work dir 位置（news/1-ocr/<年-月>/）、階段常數
│   ├── move_outdirs.py            ★新  一次性搬家。輸入：現有 kithann/out；
│   │                                   輸出：搬完的新結構＋自檢報告
│   ├── fetch_sftp.sh               改  並行集數、ffmpeg 執行緒數（可調）
│   └── 其餘                         不動
└── datadirs.py                      改  階段常數 1-cues/2-strips/3-refined/4-sheets/5-transcripts

tests/                                  全部離線、fixture 合成
├── ocr/test_sampling.py           ★新
├── ocr/test_decode.py             ★新
├── ocr/test_segmenter.py           改
├── news/test_refine.py             改
├── news/test_paths.py              改
├── news/test_workdir_writers.py    改
└── news/test_move_outdirs.py      ★新
tests-e2e/                         ★新  由 tests/e2e/ 整個搬出（fixture.py、
                                        test_roundtrip.py、test_mxf2mkv_roundtrip.py），
                                        另加一支 29.97 fps 的合成影片
tox.ini                             改  unittest 改為一次 discover tests/；e2etest 指向 tests-e2e/
.travis.yml、tests/README.md        改  路徑
CLAUDE.md                           改  驗收清單加 tox -e e2etest

資料（由誰產、吃什麼）
kithann/out/news/1-ocr/<年-月>/<slug>.work/
├── 1-cues/cues.json          ← scripts.ocr.cli cues      吃：影片、preset
├── 2-strips/<格名>.png       ← scripts.ocr.cli cues      吃：同一趟解碼的畫面
├── 3-refined/cues.json       ← scripts.news.refine_cues  吃：影片、1-cues
├── 4-sheets/…、sheets.json   ← scripts.news.gap_sheets   吃：2-strips、3-refined
└── 5-transcripts/…           ← scripts.news.ingest       吃：Claude Vision TSV
kithann/out/news/logs/<年-月>/<slug>.{get,cues,refine}.log  ← fetch_sftp.sh
Kari-SRT/news/1-ocr/1-cues/<年-月>/<srt_name>.json              ← scripts.news.publish（吃 3-refined）
```

## spec × scenario × 測試檔

| spec | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| cue-timing | 固定每 6 格取一格，29.97 ÷ 5 = 5.994，一集尾端偏 0.6 秒 | `ocr/test_sampling.py` |
| cue-timing | 取樣時間記成 k×0.2，實際畫面晚 0.067 秒（179午 抽格抽到上一句的根源） | `ocr/test_sampling.py` |
| cue-timing | 來源 25 fps 時仍要每 0.2 秒一格，不可變成每 8 格 | `ocr/test_sampling.py` |
| cue-timing | 格率宣告為 0/0 時當 29.97，但時間仍以真實 pts 為準 | `ocr/test_sampling.py` |
| cue-timing | 同一格同時最接近兩個目標時間，被判斷兩次 | `ocr/test_sampling.py` |
| cue-timing | rawvideo 預設補重複格，畫面數與時間戳對不上（實驗踩過：832 對 166） | `ocr/test_decode.py` |
| cue-timing | 進度列與 showinfo 同一行，時間戳漏抓（實驗踩過） | `ocr/test_decode.py` |
| cue-timing | 兩個邊界視窗重疊，中間的格要分給兩個邊界，不可只算一次 | `ocr/test_decode.py` |
| cue-timing | 邊界在 0.1 秒處，視窗左緣被檔頭截掉，格數不足時沿用粗切值 | `news/test_refine.py` |
| cue-timing | 解碼中途死掉，已算的邊界不可寫入 | `news/test_refine.py` |
| cue-timing | 「取不到畫面」與「無法分辨」被合併成同一個數字回報 | `news/test_refine.py` |
| cue-timing | 把原生格率全部餵進狀態機，min_stable=2 變成 0.067 秒，轉場被切成獨立 cue | `ocr/test_segmenter.py` |
| srt-data-store | work dir 直接落在 `1-ocr/` 底下、沒有月份層 | `news/test_paths.py` |
| srt-data-store | 跨年集數（2021-12 與 2022-01）月份層取錯 | `news/test_paths.py` |
| srt-data-store | 精修寫進舊的 `2-refined/`，讀的人看 `3-refined/` 讀到空的 | `news/test_workdir_writers.py` |
| srt-data-store | 圖條寫進 `strips/`，時間軸卻記 `2-strips/`，組合圖抓不到圖 | `news/test_workdir_writers.py` |
| srt-data-store | 搬家把 `stage-read/` 這種暫存當成產物搬進 `1-ocr/`，或漏搬 log | `news/test_move_outdirs.py` |
| srt-data-store | 搬完之後程式仍寫舊路徑，新舊並存 | `news/test_move_outdirs.py` |

端對端（`tests-e2e/`）：合成影片燒入已知 SRT → 跑完整流程抽回 → 逐 cue 比對時間。這次新增 29.97 fps 的 fixture，因為單元測試餵的是合成資料，只有它能抓到「取樣相位錯了」「時間戳記錯了」這類問題。

## Risks / Trade-offs

- **新舊切法並存** → 1–9 月與 10 月以後的取樣相位差約兩格，cue 集合可能有極少數差異。寫入 `Kari-SRT/news/1-ocr/README`，並在 proposal 記明是有意為之。
- **少數邊界與舊做法差超過 0.05 秒（約 0.5%）** → 都落在 0.06–0.17 秒，且多為 joint（兩側都有字、最敏感的那種）。規格只保證與真實切換點的誤差，不保證與舊結果一致；使用者已裁定接受。
- **搬家動到 400 多個 work dir 與 1326 個 log** → 先 dry-run、再搬、搬完自檢；且排在 work dir 暫存刪除之後執行，實際要搬的量會小得多。
- **`rebuild --verify` 蓋不到這次的改動** → 它用已入庫的時間軸重建 SRT，不重跑切 cue 與精修。所以驗收必須加 `tox -e e2etest`。
- **並行 6 集同時讀 6 支影片** → 使用者確認是 SSD，不設額外限制；並行度可調，出問題就降。

## Migration Plan

1. 程式面（取樣、精修、執行緒與並行度）先做完、通過驗收。
2. 等 8–9 月切 cue 與 OCR 全部完成、驗收過，刪掉 work dir 暫存。
3. 執行 `move_outdirs.py --dry-run`，確認清單。
4. 實際搬家，跑自檢。
5. 之後的月份（10 月起）用新結構與新取樣。

回退：搬家前的結構可由同一支腳本反向搬回（舊→新的對應是一對一）。程式面若要回退，新舊做法在同一份 1-cues 上都能跑，重跑精修即可。

## Open Questions

- ffmpeg 執行緒數與並行集數的預設值，等機器閒下來再量一次確認（現有數字在機器忙碌時量得，偏保守）。這不影響規格與任務拆分。
