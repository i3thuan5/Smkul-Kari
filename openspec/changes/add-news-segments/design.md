## Context

動機見 proposal.md。這裡只寫 explore 階段量到、會影響做法的事（2026-09-23～24，24 集試做＋4 支 2024 影片量紅條＋3 集畫面分類實驗）。

- **字幕帶與紅條**：字幕帶 y 722–844（`titv-news`，h 122）；偏上 721–787、偏下 787–836，`sheet.row_slots` 分界列 65（＝y 787）、pad 6。2024 年紅條上緣固定在 y 851／852，其上約 40 列是暗紅（R 30–100、G=B=0）；偏下字幕黑框最下緣 840–841。**2021 年紅條上緣在 846／848**（`presets.json` 的 note、`verify_band.py` 的量測紀錄），所以下緣 848 不能全部年份共用——這是寫 design 時對照既有 preset 才發現的，spec 已改成「依版型的紅條位置決定」。
- **畫面分類實驗**（scratchpad `shotclass/`，只用 ffmpeg＋numpy）：每秒一格 160×90 縮圖、y 0–700；台標在不在 → 其他；紅條連續 20 秒以上 → 主播段；比棚內參考格（色塊差中位數，門檻 0.05）→ 攝影棚／主播外景；其餘外景新聞。獨立抽查 105 格對 104 格；錯的那格是 183 結尾 14 秒的主播外景段。縮圖第 t 格實際是 t+0.5 秒的畫面（ffmpeg `fps=1` 取樣點在區間中央），抽原圖對照要用 `-ss t.5`。
- **2021 年版型**：左下角是會變動的天氣框＋語別牌，不是固定台標；「VS」雙人名條的紅條約 50 秒；棚內佈景跟 2023 年不同。所以第一層只問「節目框在不在」，第二層只看 x ≥ 480。
- **帶外字幕實測**：島語時間對白置中 y≈960–1050、x≈620–1300；部落信箱旁白 y 913–967、詩句族語 y 608–640、華語 y 663–703、三行版第三行 y 712–752；2021 帶外專題 y≈950–1002；開場蒙太奇斜體 y≈705–838，左右不定。
- **既有工具**：`rescan_band.py` 已能對一集的一段時間用別的 region 重切、接回時間軸，並在時間軸加 `rescanned` 欄；但它是「讀完字之後」的補救路徑，範圍內 cue 要重讀、TSV 要重新對映。
- **work dir 已用到 `5-transcripts/`**（`1-cues/ 2-strips/ 3-refined/ 4-sheets/ 5-transcripts/`），新增的兩層接在後面：`6-opening/`、`7-shots/`（第三層確認時寫的是 5-、6-，照實際既有編號順延）。
- **`fetch_sftp.sh` 列伺服器檔案時只收 `.mp4`／`.mxf`**，`/home/mkv-raw` 的 `.mkv` 會被當成「伺服器頂懸無」——24 集試做是用 scratchpad 的 `pilot_cut.sh` 繞過去的，整批前一定要修。
- **2021 年片頭補做**：本機封存 mkv 只有 2021-02。2021 年伺服器上是 mp4、moov 在檔尾；`curl --netrc -r` 抓前 60 MB＋後 16 MB 寫進 `truncate -s <大小>` 的稀疏檔，20／30／40 秒三格解得出來（已驗證）。檔案大小用 `sftp.sh ls` 取，`curl -I` 拿不到。

## Goals / Non-Goals

**Goals:**

- 新集數切 cue 時一次產出段落表、片頭三格、判不準的截格，影片刪掉之後不必再抓。
- 帶外段落在讀字前補切，讀字只讀一次。
- 2021 年 660 集補做片頭辨識，不整支下載。
- 整批 2021-11～2024-12 的 1-ocr／3-srt 與 whisper 做完。

**Non-Goals:**

- whisper 照段落換語別（島語時間、他族插播）——段落表記下單元語別，辨識留給下一個 change。
- 2021 年既有 656 集不重切、不重新分類；段落表只補 `TODO.md` 已知的 15 集帶外專題。
- 紅條族語、諺語字卡不收。
- 不為 16 族各做語別牌樣板。
- 不加新套件。

## Decisions

### 一、畫面分類：像素規則為主，判不準的交 Claude Vision

兩層判準見 `news-segments` spec。取特徵（`shots.py`）與判段（`segments.py`）分開：取特徵要解碼影片，判段是純邏輯、可以用合成的逐秒特徵離線測。逐秒特徵存 work dir `7-shots/features.npz`（縮圖不存，太大；只存每格的「節目框分數、純紅條列數與上緣、對各參考格的色塊差中位數、各單元標誌分數」），判段規則改了可以不解碼重跑。

參考格放 `scripts/news/shot_refs/<年>/*.png`（160×90），跟 `presets.json` 同一層：是版型知識、隨 repo 走，不是產出資料。每年、每種佈景（坐姿、站姿、文化小辭典）2–3 張，單元標誌（島語時間、部落信箱）各一張裁切樣板。

替代方案：
- 「反覆出現的鏡位＝主播」：長篇專題的受訪者鏡位也反覆出現（176 嘉明湖），否決。
- 全部交 Claude Vision：一集 2,900 秒，逐秒讀太貴；像素規則已經 99%，只把判不準的 10–30 格交出去。

### 二、第二層只看 x ≥ 480，「其他」改由第一層的節目框判

使用者裁定裁掉左邊 25%，兩年同一套規則。第一層原本靠「左下角台標不見」判「其他」，裁掉之後這個線索要保留在第一層自己看：第一層只看左下角一小塊，問「有沒有框」（2021 天氣框、2023 台標都是在畫面固定位置的半透明深色框，用框邊的邊緣強度判在不在，不比內容）。要先用 2021、2023 各重跑一次 spike 量準確度，達不到 95% 就調判準，這是 tasks 裡的一條。

### 三、判不準的格在影片刪除前截好

`fetch_sftp.sh` 的 `process_episode` 切 cue＋精修之後、刪影片之前，依序跑：`opening grab`（20／30／40 秒三格，1920 寬原圖存 `6-opening/`）→ `shots`（逐秒特徵）→ `segments`（判段、寫 work dir 的 `0-segments.csv`，並列出判不準的秒數）→ 截判不準的格（原圖存 `7-shots/judge/`）→ `segment_recut`（帶外段落補切）→ 刪影片。這樣讀者確認時不用重抓。

### 四、帶外補切放在讀字之前，由 `segment_recut.py` 負責

重切與接回時間軸的純函式（範圍內 cue 換掉、範圍外逐條對映、重新編號）從 `rescan_band.py` 搬到共用位置 `scripts/news/splice.py`，`rescan_band.py` 與 `segment_recut.py` 都從那裡 import，行為不變（`test_rescan_band.py` 不改就要過）。

`segment_recut` 對段落表上每一段帶外段落，用對應 preset 切那一段，接回時間軸；因為還沒讀字，重新編號沒有代價。時間軸的記法：

- 頂層加 `areas`：`{"島語時間": {"preset": "titv-news-island", "region": [...]}, ...}`，只列這集用到的；
- 用非預設區域切出的 cue 加 `"area": "島語時間"`；預設區域（字幕帶）的 cue 不加欄位。

補切出來的那一段也要用同一個 preset 精修後才接回——store 只收精修過的時間軸（`srt-data-store`），接回粗切的段會被 `publish` 擋下。

沒有補切的集數時間軸跟現行逐 byte 相同（spec 的「沒有帶外段落的集數」）。`rebuild` 不需要讀 `area`——SRT 只看時間與 TSV 文字——但圖條與組合圖要照 `area` 用對的區域排版，讀者說明也要提示「這幾條是置中的帶外字幕」。

已讀完字的 2021 年 15 集帶外專題照舊走 `rescan_band.py`：重抓影片、從 Kari-SRT 時間軸重建 work dir、重切、補讀。

替代方案「每集多跑一次只看帶外區域的全程切 cue」：多一倍解碼，而且 2024 紅條（族語標題、名牌）就在同一區，誤切多，否決。

### 五、帶外區域的 preset

`presets.json` 加四組，都用 `outline: true`，比對範圍依字的對齊方式：

| preset | region（x, y, w, h） | 比對欄 | 用在 |
|---|---|---|---|
| `titv-news-island` | 0, 940, 1920, 120 | 置中 560–1360 | 島語時間 |
| `titv-news-mailbox` | 0, 600, 1920, 380 | 全寬 | 部落信箱 |
| `titv-news-montage` | 0, 690, 1920, 190 | 全寬 | 單元片頭（開場蒙太奇） |
| `titv-news-offband` | 0, 930, 1920, 110 | 置中 560–1360 | 2021 帶外專題 |

數字取實測範圍再各放 10–20 px。部落信箱範圍會吃到 2024 紅條（y 851 起），所以它的 `sheet` 宣告排除色（純紅），讀者說明也要講「紅條上的族語不收」。

### 六、字幕帶下緣：新增 `titv-news-848`，不改 `titv-news`

`titv-news` 維持 h 122（2021 年紅條上緣 846／848）。新增 `titv-news-848`（h 126，其餘相同）。哪一年用哪個由實測決定：tasks 裡先對 2022-01、2023-06～12、2024 各抽 2 集跑 `verify_band` 量紅條上緣，上緣 ≥ 850 的年份用 848。`fetch_sftp.sh` 仍然要明確 `--preset`，由 `plan_month` 依月份印出建議 preset（對照表放 `presets.json` 的一個 `by_month` 欄位，是資料不是程式），帶位把關照舊擋錯。

### 七、字幕上下位置判斷法：跨分界留整條高、排除純紅列

`sheets.slot_crop` 加兩個 preset 參數：`row_slots.straddle`（墨水越過分界超過幾列就退回全高，預設 0＝不啟用，舊語料逐畫素不變）與 `row_slots.exclude`（排除色判準，`{"r_min":20,"gb_max":25,"r_minus_g":15}`；有宣告才生效）。排除色只影響判定用的遮罩，圖條畫素不動。`titv-news`／`titv-news-848` 都開 `straddle: 8`、`exclude`；`amis-titv-news` 不動。

「資料畫面」標籤在左側（x < 400），判定本來就用置右字幕比對遮罩範圍的墨水（`_cue_blocks` 的 `narrow`），加一個測試鎖住，不改程式。

### 八、片頭辨識：`opening.py` 三個子命令

- `grab <work|video> [--sparse <remote>]`：截 20／30／40 秒三格到 `6-opening/`。`--sparse` 給 2021 補做：`curl --netrc -r 0-60M` ＋ `-r <size-16M>-` 寫進 `truncate -s <size>` 的稀疏檔，截完刪掉。
- `sheet <月份>`：多集三格拼成 Claude Vision 輸入組合圖（每集一列三格，縮到 640 寬；一張 8 集），讀者寫 TSV：`成果檔名<TAB>秒數<TAB>語別牌<TAB>主播`。
- `ingest <tsv>`：寫 `Kari-SRT/news/1-ocr/片頭辨識.csv`（照成果檔名排序、覆寫同名列），跟 `smkul.csv` 族語別、`主播.csv` 比對，印出「不符」「判不準」「新主播」三張清單；有「不符」時以非零狀態結束，`fetch_sftp` 下游（OCR 那個 subagent）看到就不讀這集。

`fetch_sftp.sh` 加 `--opening-only`：不切 cue，只對已入庫的集數做 `grab --sparse`，給 2021 年補做。2021 年 660 集約 76 MB × 660 ≈ 50 GB 下載，比整支下載（約 1.4 TB）少兩個數量級。

### 九、讀者說明

`vision_tools/prompt.py` 加兩種讀者說明（`--kind opening`、`--kind segments`）：

- 片頭辨識：讀左下角語別牌、主播自介「我是…」；語別牌只寫中文族名；三格都看不到就寫 `判不準`。
- 段落確認：每格附候選類型，讀者回答類型與依據；主播段看不看得到棚內佈景、有沒有「島語時間／○○族語」標誌、語別牌是不是換了。

讀者一律用 opus（記憶：視覺辨識 subagent 用 opus）。

### 十、段落表入庫

`segments.py` 寫 work dir `0-segments.csv`，讀者確認後 `segments.py apply <tsv>` 改寫同一檔的 `類型`／`依據`。`publish.py` 發布時連同時間軸複製到 `Kari-SRT/news/1-ocr/0-segments/<年-月>/<成果檔名>.csv`；驗證（欄位、類型、首尾相接）放 `segments.py` 的 `check()`，`publish` 與 `rebuild --verify` 都呼叫它。孤兒檔檢查把 `0-segments/` 當成一個階段目錄。

### 十一、排除清單的把關

`catalogue_checks.py` 加一條：讀 `排除影片.csv`，把目錄的 `原始影片檔案位置`（分號並列的每一條）用 `resolve_slug.server_path()` 換成絕對路徑後比對。`name_catalogue --check` 與 `rebuild --verify` 已經呼叫 `catalogue_checks`，不必另外接線。

### 十二、最後兩個 task 的執行方式

- **2024-12 試做**：照整批的方式跑一個月，量「一集從下載到 whisper 的時間」「判不準格數」「帶外補切段數」，用來估整批。
- **整批**：主 session 開兩個 subagent。
  - **切 cue 的 subagent**：依月份序 `fetch_sftp.sh <月> --preset <建議>` 一個月接一個月，用 `run_in_background: true` 發動、`&&` 串接，不停；每月做完寫一行進度到 `kithann/out/news/logs/cut-progress.tsv`。
  - **OCR 的 subagent**：主 session 用排程每個整點喚醒它；它讀 `cut-progress.tsv` 與各 work dir，挑「切好、片頭相符、段落已確認、還沒讀字」的集數，做 片頭／段落確認 → `batches` → 讀者（opus）→ `ingest` → `make_srt` → `publish`，接著 `whisper_run`，最後 `rebuild --verify`、`name_catalogue --check`。一個整點做不完就下一個整點接著做（每一步都可續跑）。
  - 兩者都不刪別人的東西；OCR subagent 只讀 work dir，影片由切 cue 那邊負責刪。

## 檔案樹（★新／改；標明誰產出、吃什麼）

```
Kari-SRT/news/
├── README.md                     ★新  手寫
├── 主播.csv                      改   手寫；opening ingest 印「新主播」提示
├── 排除影片.csv                  （已建）手寫；catalogue_checks 讀
├── smkul.csv                     （不變）
└── 1-ocr/
    ├── README.md                 改   手寫
    ├── 片頭辨識.csv              ★新  opening.py ingest ← 讀者 TSV＋smkul.csv＋主播.csv
    ├── 0-segments/<年-月>/<srt_name>.csv  ★新  publish.py ← work dir 0-segments.csv
    ├── 1-cues/<年-月>/<srt_name>.json     改   publish.py ← work dir 時間軸（多 areas／area）
    ├── 2-vision/                 （不變）
    └── 3-srt/                    （不變）

kithann/out/news/1-ocr/<年-月>/<slug>.work/   （work dir，不進版控）
├── 0-segments.csv                ★新  segments.py ← 7-shots/features.npz；segments.py apply ← 讀者 TSV
├── 1-cues/ 2-strips/ 3-refined/ 4-sheets/ 5-transcripts/   （既有；segment_recut 改 1-cues、補 2-strips）
├── 6-opening/{20,30,40}.png      ★新  opening.py grab ← 影片
└── 7-shots/
    ├── features.npz              ★新  shots.py ← 影片＋shot_refs/
    └── judge/<秒>.png            ★新  shots.py judge ← 影片＋0-segments.csv 的判不準秒數

scripts/
├── ocr/sheets.py                 改   row_slots.straddle、row_slots.exclude
├── catalogue_checks.py           改   排除清單
└── news/
    ├── presets.json              改   titv-news-848、四組帶外 preset、by_month、straddle／exclude
    ├── paths.py                  改   EXCLUDED_STORE、OPENING_STORE、SEGMENTS_STORE、work dir 的 6-opening/ 7-shots/
    ├── shots.py                  ★新  影片 → 逐秒特徵；judge 截格
    ├── shot_refs/<年>/*.png      ★新  參考格、單元標誌樣板（手工從影片截）
    ├── segments.py               ★新  特徵 → 段落表；apply 讀者結果；check 驗證
    ├── splice.py                 ★新  從 rescan_band 搬出的重切接回純函式
    ├── segment_recut.py          ★新  段落表 → 帶外補切
    ├── opening.py                ★新  grab／sheet／ingest
    ├── rescan_band.py            改   改從 splice import
    ├── publish.py                改   段落表入庫
    ├── rebuild.py                改   呼叫 segments.check
    ├── plan_month.py             改   印建議 preset
    ├── fetch_sftp.sh             改   .mkv 列檔、切 cue 後的片頭／段落／補切、--opening-only
    ├── vision_tools/prompt.py    改   --kind opening／segments
    ├── vision_tools/brief.md     改   帶外字幕、紅條族語不收
    └── README.md                 改   新模組與流程

tests/
├── README.md                     改   總表加一行指向 tests/news/README.md
├── ocr/test_sheets.py            改
├── ocr/test_presets.py           改
├── catalogue/test_catalogue_checks.py  改（第二層原寫 test_name_catalogue.py；把關在 catalogue_checks，測試跟著模組放）
└── news/
    ├── README.md                 ★新  這次的 spec × scenario 列
    ├── test_shot_features.py     ★新
    ├── test_segments.py          ★新
    ├── test_opening.py           ★新
    ├── test_segment_recut.py     ★新
    ├── test_rescan_band.py       （不改，要照樣過）
    ├── test_publish_gate.py      改   段落表入庫與驗證
    ├── test_fetch_sftp_config.py 改   .mkv 列檔
    └── test_vision_prompt.py     改   兩種新讀者說明
tests-e2e/test_roundtrip.py       （不改；動到組合圖裁切與時間軸，一定要跑）
```

## spec × scenario × 測試檔對照表

| spec | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| news-segments | 2021 年左下角天氣框會換城市與溫度，拿台標樣板比內容會把 26 分鐘判成「其他」——第一層只問框在不在 | test_shot_features.py |
| news-segments | 紅條上方約 40 列暗紅（R 30–100、G=B=0），用 R>150 只找到 3–9 格且位置錯——要用純紅 | test_shot_features.py |
| news-segments | 縮圖第 t 格是 t+0.5 秒的畫面，截判不準的格用 `-ss t` 會差半秒、截到隔壁鏡頭 | test_shot_features.py |
| news-segments | 棚內右側虛擬螢幕換內容，整格平均距離超過門檻——要用色塊差中位數 | test_shot_features.py |
| news-segments | 裁到 x ≥ 480 之後左下角線索沒了，「其他」要靠第一層自己看，不能從第二層推 | test_shot_features.py |
| news-segments | 176 嘉明湖專題同一受訪者鏡位出現十幾次，「反覆出現＝主播」會誤判 | test_segments.py |
| news-segments | 人名條只中斷 2 秒就接上主播段，被併成一段越界（183 42:01–42:04） | test_segments.py |
| news-segments | 183 結尾主播段只有 14 秒，沒到 20 秒門檻被判外景——12–25 秒標判不準 | test_segments.py |
| news-segments | 2021 年「VS」雙人名條紅條約 50 秒，被當成攝影棚 | test_segments.py |
| news-segments | 7/14 拉阿魯哇那集的島語時間教泰雅語，單元語別只看目錄會記錯 | test_segments.py |
| news-segments | `202409015S0800` 第 2300 秒後是排灣，要記他族插播並記語別 | test_segments.py |
| news-segments | 段落有 5 秒縫或重疊，自動補齊會把錯藏起來——要擋下指名 | test_segments.py |
| news-segments | 類型寫成「棚內」這種非正式名稱，要擋下 | test_segments.py |
| news-segments | `24NL003_160_Paiwan` 片頭是賽德克主播 Awe Nawi——語別不符要停、非零結束 | test_opening.py |
| news-segments | 三格都還在片頭動畫讀不到語別牌，不能當相符 | test_opening.py |
| news-segments | 賽夏 'okay a 'ataw hayawan 不在 主播.csv，要提示、不擋 | test_opening.py |
| news-segments | 2021 mp4 的 moov 在檔尾，只抓前段解不開——稀疏檔要含前 60 MB＋後 16 MB，且位元組數對得上伺服器 | test_opening.py |
| cue-timing | 島語時間對白置中（x≈620–1300），置右比對遮罩（1250–1790）切不出來 | test_segment_recut.py |
| cue-timing | 部落信箱三行版第三行 y 712–752 跨過帶子上緣，區域要涵蓋 600 起 | test_segment_recut.py |
| cue-timing | 補切在讀字之後做要重新編號、TSV 對到別條——補切一定在讀字之前 | test_segment_recut.py |
| cue-timing | 時間軸沒記 area，重建或補讀時對不回哪條用哪個區域 | test_segment_recut.py |
| cue-timing | 沒有帶外段落的集數，時間軸要跟現行逐 byte 相同 | test_segment_recut.py |
| cue-timing | 下緣放 850 碰到紅條過渡列（2024 紅條上緣 851／852）——下緣 848 | ocr/test_presets.py |
| cue-timing | 2021 年紅條上緣 846／848，用 848 版型會把紅條切進字幕帶——titv-news 維持 844 | ocr/test_presets.py |
| subtitle-text-source | 文化小辭典 y 770–837 跨分界 787，判成偏下切掉字頂 8–17 px——跨分界留整條高 | ocr/test_sheets.py |
| subtitle-text-source | 紅條與暗紅過渡列的墨水被算進字幕、判錯位——純紅列不算墨水，圖條畫素不變 | ocr/test_sheets.py |
| subtitle-text-source | 2024「資料畫面」標籤在左側偏上位 y 740–792，跟偏下對白同時出現 | ocr/test_sheets.py |
| subtitle-text-source | 沒宣告 straddle／exclude 的語料（開會了、amis-titv-news）要逐畫素不變 | ocr/test_sheets.py |
| episode-catalogue | 整檔 sha256 不同但串流雜湊相同的重複檔（23NL004_174_Paiwan）被加回目錄 | catalogue/test_catalogue_checks.py |
| episode-catalogue | 目錄欄位沒有開頭斜線、排除清單有，比對要換成同一個絕對路徑 | catalogue/test_catalogue_checks.py |
| srt-data-store | `0-segments/` 有一個成果檔名不在目錄的段落表（孤兒檔） | test_publish_gate.py |
| srt-data-store | 段落表隨時間軸入庫，內容相同不重寫 | test_publish_gate.py |
| （既有缺口） | `/home/mkv-raw` 的 .mkv 被列檔程式當成「伺服器頂懸無」 | test_fetch_sftp_config.py |

## 實作時的修正（2026-09-24）

實作與量測推翻或補足了上面幾項，程式與 spec 已照這裡改：

- **字幕帶有三種版型，不是兩種。** 逐月抽 2 集量（41 集）：2021-11～2024-07 對白平台 y 799–838、白細邊 849／850、紅條 852，用 `titv-news-848`（2021-11 的母帶也是這種，不是只有 2024）；**2024-08 起字幕置中、平台 y 880–889、白細邊 932、紅條 938**，新增 `titv-news-2024-08`（y 840–930、比對欄 560–1360、不錨右）。
- **`by_month` 改成每個 preset 自己宣告 `months`**：`presets.json` 的頂層鍵都會被當成 preset 迭代，多一個 `by_month` 會被當成一個壞掉的 preset。`fetch_sftp.sh` 沒給 `--preset` 就照月份（`plan_month --preset`）。
- **紅條、節目框、語別牌的位置由 preset 的 `shots` 宣告**（新版型位置都不同）。
- **節目框在不在不需要每年的樣板**：用該集自己的中位數框、2×2 區塊中位數，門檻 0.12。
- **比棚內參考格用區塊差的第 25 百分位**：2021 的棚右側大螢幕佔一半以上，中位數分不開。
- **只有「長紅條＋比中棚內」自動判攝影棚**；不像棚內的長紅條段（戶外主播、2021「VS」受訪者）、沒有紅條只像棚內的段都交讀者。抽查四集各 50 格：第一層 200/200，自動判定的格全對，交讀者 0–22%。
- **段落邊界修到鏡頭**：`shots` 另存每格 105 塊的區塊色（`picture`）；他族插播看 `badge`（語別牌 vs 開頭 600 秒）。
- **`straddle` 定 6（＝pad）**：越過分界超過 pad 的每一列都會被裁掉。紅條排除只看遮罩以外的背景像素（紅條上白字很寬時，一列的紅色不到一半）。
- **部落信箱 preset 不宣告 `exclude`**：帶外 preset 沒有上下位置判斷，排除色不起作用。`titv-news-offband` 沿用 `rescan_band` 驗過的 420,910,1500,122。
- **`rescan_band` 的重切讀錯路徑**（讀 `<out>/cues.json`，分階段後在 `1-cues/`），搬到 `splice.recut` 時修掉。
- **`name_catalogue --check` 接上排除清單**：新聞的 `rebuild` 本來沒有跑目錄不變量。
- **2024-08 新版型的畫面分類還沒校準**：主播段標題條是偏粉的紅（RGB 約 140/56/55），受訪者人名條是純紅而且常掛 20 秒以上，舊版型「長紅條＝主播段」不成立。

## Risks / Trade-offs

- [第一層改看「框在不在」後準確度未知] → tasks 先用 2021、2023 重跑 spike 量，未達 95% 就調判準再往下做。
- [參考格要每年、每種佈景準備，2022、2024 佈景可能又不同] → 沒比中參考格但像主播的段落一律判不準交讀者；讀者確認多了就補參考格。
- [2022–2023 紅條上緣未量] → tasks 先量，量出來再定 `by_month`；選錯的由帶位把關擋下。
- [整批跑數天，兩個 subagent 之間靠檔案交接] → 每一步可續跑；OCR subagent 只挑「切好且片頭相符」的集數；進度寫檔，session 被洗掉也看得到。
- [判不準格多時讀者成本上升] → 2024-12 試做先量每集判不準格數再估整批。
- [段落表對 2021 年只補 15 集] → README 寫明 2021 年大部分集數沒有段落表是正常的，驗證不把「沒有段落表」當缺件。

## Migration Plan

- 既有 680 集時間軸格式不變（`area` 只加在補切的 cue）。
- `titv-news` 不改，既有集數的 `rebuild --verify` 逐 byte 不變。
- 2021 年片頭辨識補做只加 `片頭辨識.csv` 的列，不動其他檔。
- 回退：新 preset 與新欄位都是加的，刪掉即回到現行。

## Open Questions

- 2022–2023 年紅條上緣的實測值（決定 `by_month`，tasks 裡量）。
- 2022、2024 年棚內佈景需要幾張參考格（實作時邊量邊補）。
