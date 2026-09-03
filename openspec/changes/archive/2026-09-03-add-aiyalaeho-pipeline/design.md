# 設計：aiyalaeho（《開會了》）影像側編排線

## Context

動機見 proposal.md — Why。左右做法的現況與限制：

- **素材已在本機**：`kithann/開會了/` 41 支 mp4（68 GB），位元組數與伺服器
  逐支相同；只有 116（無字）、119／122（混雜）三支在伺服器上、本機沒有。
  影片是使用者自己的副本，處理後**不刪**（與 news 的「切完即刪」相反）。
- **版型量測**（12 取樣點 × 38 集）：全部同一版型（黃紅漸層不透明帶、
  族語列上／華語列下），但整帶逐集漂移——標準位置族語 ~896–930／華語
  ~954–991，最偏的 117 在 918–947／966–1008，094 的華語字底到 1011。
  既有 preset 槽（族語 888–948、華語 948–1008）對 094／117／111 貼邊或
  超出 3 px。
- **引擎不用動**：`scripts/ocr/`（雙列切分、per-line strips、TSV 列名驗證）
  與 `scripts/srtlib/`（組裝鏈、0.5 s 留白）本來就語料無關；068 七月的
  A.work＋planB-vision.srt 就是同一引擎切讀出來的。
- **news 批次進行中**（多個平行 session 在改 news 側）：本 change 對 news
  檔案的改動只有 `presets.json` 刪一筆；news 的 `rebuild --verify` 必須
  全程綠。
- **`add-episode-sourcing`（實作完成、待歸檔）** 修改了 srt-data-store 的
  「命名鍵統一為 srt_name」——本 change 的 MODIFIED delta 以其歸檔後的文本
  為基準，歸檔順序：先它、後本 change。
- **語言代號規範的正本在 `kithann/規範/`**（gitignore，換機器會不見），
  所以對照表必須進程式碼與測試，不能執行時讀那兩個 csv。
- 目錄（`ilrdf-corpus.csv`）對本語料過時且不齊（43 列標無影片但影片在、
  068／164 無列、無日期），故檔名驅動；目錄不動。

## Goals / Non-Goals

**Goals**

- 一條 aiyalaeho 自己的編排線，達到與 news 同等的核心保證：主 repo＋
  Kari-SRT 離線重建全部交付 SRT 逐 byte 相同。
- 068 以實資料走通端對端（登記→切 cue→視覺辨識→ingest→組裝→定版→重建）。
- 068 之後整批做完：全部有影片的集數（本機 41 支＋伺服器 3 支，約 44 集）
  走到定版與重建全綠（使用者裁定 2026-08-31）。
- news 側行為零改變（唯一檔案改動是 presets.json 搬走一筆）。

**Non-Goals**

- 不做語音側（2-asr）——族語文本畫面就有，使用者裁定。
- 不收「上字文稿」（第 001–045 集，與影片零交集）——另案的文本語料。
- 不回填播出日期（拿到權威表再填 smkul.csv 欄，鍵不動）。
- 不開整批視覺辨識的派工 slash command（`/smkul-aiyalaeho` 比照
  `/smkul-news`，等批次真的要跑再開）。
- 不抽 news／aiyalaeho 的共用層（使用者裁定甲案；見 D3）。

## Decisions

### D1 — 檔名驅動，不讀目錄

全集清單＝來源資料夾的 mp4 檔名；`catalogue.py` 解析檔名成
集數／族語別／語言別／語言代號，登記 CLI 寫 pending 進 inventory。

*為什麼*：目錄對本語料缺日期、缺 068／164、43 列標「無影片」但影片在；
修目錄是外部正本、歸人。檔名是這批素材唯一完整、一致的事實來源
（`NNN-語言[-變體]-字幕狀態.mp4`，41 支全部照這個型）。

*替代方案*：修目錄再目錄驅動——否決，目錄不是我們的檔案，改了與正本的
正本（xlsx）就分岔。

### D2 — 命名鍵不含日期

`開會了_<集數3碼>_<族語別英>_<族語別中>`。追查過的日期來源全數落空：
xlsx 正本「開會了」分頁只有序列／節目名稱／集數／備註；mp4 是 libx264
重轉、creation_time 洗掉；公開網路（原視新聞網系列頁、YouTube、VOD）
對不回播出集數。等日期會卡整條線；鍵一旦定案就不再動，日期屬於進度表
欄位。

### D3 — 複製一套（甲案），不抽共用

`scripts/aiyalaeho/` 自 news 複製改，news 一行不動（presets.json 除外）。

*為什麼*：使用者裁定。news 批次進行中且有平行 session 在改，抽共用層
（動 news 11 支）風險大；複製的漂移代價以「逐支盤點砍掉沒有存在理由的
四支＋各自測試釘行為」壓低。

*替代方案*：乙（語料描述物件、一條程式路徑）——正確但此刻動 news 太多；
丙（只抽兩處）——半套抽象。若日後開第三個語料再議乙。

### D4 — 盤點：news 那套有四支不複製

- `fetch_sftp.sh`：素材已在本機；缺的 3 支手動 `sftp.sh get`。
- `plan_month.py`／`sources.py`／`resolve_slug.py` 的角色：檔名即事實、
  一集一支檔、無月份——併成 `catalogue.py` 一支（解析＋對照表＋登記 CLI）。
- `gap_sheets.py`：`.work`／`.B.work` 之分是文稿時代歷史；這裡
  `cues --sheets` 首輪即完整，單一工作目錄到底。防覆蓋照舊：ingest 匯入過
  （verified.json 非空）的工作目錄，重切前擋下。
- `batches.py`：`ocr.cli pending` 已列未讀 sheet；分批派工在提示端。

### D5 — 0-cue 集數放行

news 的 `vision_complete` 寫 `bool(wanted) and wanted <= read`，0 cue 回
False，publish 永遠被卡。aiyalaeho 版語意改成「cue 編號集合被校讀集合涵蓋」
（空集合成立），無字幕集以 0 行 SRT 交付。編號集合比對（不是數量）的既有
判準不變。

### D6 — preset 搬家＋華語槽加寬

`amis-xiuguluan-bilingual` → `scripts/aiyalaeho/presets.json` 改名
`aiyalaeho-bilingual`；華語列槽 `h` 60→66（y 72–138，補到 region 底），
依據：094 字底 1011、117／111 字底 1008 貼邊。region `[0,876,1920,138]`
與遮罩參數不動。**上面那列的名字由 `ami` 改成 `formosan`**（實作時定
的）：這個 preset 服務十一種族語，把每一集的上列都叫 `ami` 對其中
37 集是錯的；列名進 TSV、進 ingest 的驗證、也進 rebuild，錯的名字會
一路帶著走。同時拿掉該列的 tesseract `whitelist`（只允許拉丁字母，
而實際畫面夾漢字，留著會誤導）。news 檔中原筆刪除——版型知識單一存放；`match` 欄不再
依賴（一律 `--preset` 指定，檔名比對在這批素材上不可信是 news 已踩過
的坑）。

### D7 — 雙槽帶前驗（`verify_band.py` 新寫，不複製 news 版）

news 版的兩個地標（對白平台、紅帶上緣）在黃帶版型上不存在。新判準：
取樣若干幀，量帶區的逐列 ink 剖面，找出文字列的實際範圍；要求每個
文字列完整落在 preset 宣告的對應槽內（容許整帶位移，量測值直接與槽界
比）。單位是**集**（位移是逐集屬性）。套到單列新聞帶會因族語槽量無
文字列或列越槽界而 FAIL。取樣走既有 `cuelib.stream_region`。

### D6b — 列高就停在 60＋64，莫閣為著裝箱縮族語槽

contact sheet 的裝箱預算是 `1.10 MP ÷ sheet 寬`，sheet 寬是
`108 + 該集最寬ê ink 圖條 + 16`，所以**逐集無仝**：068 是 1970（預算
558），滿版ê集數是 2044（預算 538）。這馬ê列高 60＋64（block 138）佇
1970 下底囥 4 條、佇 2044 下底囥 3 條。

族語槽若對 60 縮做 56（block 134），逐集攏保證 4 條，規批省三分之一ê
閱讀量。**否決**：量著ê族語列上頂懸是 893，槽頂縮到 892 賰 1 px；族語
ê `^` 標記就是khǹg佇字身上頂懸彼幾逝，削著ê拄好是這批語料上要緊ê
符號。成本ê差別換袂過拼寫ê正確。

逐集實際囥幾條，看該集ê `sheets.json`。

### D7b — 檔名解析不出來時略過並回報，不中止整批

實作時翻案（spec 已同步改）：原本寫「無法解析即整批中止」，但三支較早
上傳的檔（`116ALL_無字`、`119-混雜`、`122-混雜`）名內沒有族語別，
一支歹名不該讓四十餘集無法登記。改成略過並指名回報；人看過影片後用
`catalogue --language <檔名>=<族語別中>` 指定族語別補登記，指定的值
對照族語別表驗證，查無即拒絕。

### D8 — 語言代號表寫進 `catalogue.py`，測試逐條釘

正本（`kithann/規範/` 兩個 csv）是 gitignore 的，執行時讀不保證在。
表只有 16 筆，寫成模組常數；三個判讀（變體未註→族語級、德路固→
`trv-x-trk`、非霧台→語言別照錄＋代號 `dru`）各有測試。規範若更新，
改常數、跑測試。

### D8b — 交付兩行帶標籤「族語：／華語：」，空列保留標籤行

使用者裁定 2026-08-31：族語列無字幕時輸出「族語：」空標籤行，不省行。
款式與語音側 `3-srt-raw` 一致——讀 SRT 的人不用猜哪行是哪語、也分得出
「這列沒有字幕」與「漏了一行」；同文合併與逐 byte 重建都以兩行合成後
的文字為準。與七月 planB-vision.srt（無標籤、空列省行）比對文字時去
標籤再比。

### D9 — slug＝srt_name

news 的 slug≠srt_name 是「work dir 已被長時解碼引用、改名會孤兒化」的
歷史包袱；新語料沒有這段歷史，一個名字走到底，少一張對應表。

### D10 — 進度表另一張，只設有資料的 9 欄

`aiyalaeho/smkul.csv` 與 `news/smkul.csv` 各自一張（各語料自己定版、自己
重建）。欄位只設 9 欄：節目名稱、集數、族語別(英)、族語別(中)、語言別、
語言代號、影片檔案位置、影片長度、成果檔名——播出資料（年度／日期／
時段）與字幕srt狀態、語音辨識模型**不設欄**：本語料查無播出資料、無
語音側，交付與否看成果檔名與 SRT 本身（使用者裁定 2026-08-31）。欄名
沿 news 用字，日後要串總表語意對得上；拿到權威播出日期再增欄，增欄只
動 tracker 一處；日後若出現 partial 這類註記需求，屆時再議狀態欄。

## 檔案樹

`+` 新增、`~` 修改；未列出者不動。

### 程式（scripts/）

```
scripts/
├── news/
│   └── presets.json              ~ 刪 amis-xiuguluan-bilingual 一筆（搬走）
├── README.md                     ~ aiyalaeho/ 檔案表（test_readme_covers_scripts 擋漏）
└── aiyalaeho/
    ├── README.md                 + 語料編排總覽與跑法
    ├── __init__.py               + package 空殼
    ├── paths.py                  + 語料常數：store 各階段目錄、INVENTORY、TRACKER_STORE／
    │                               TRACKER_CACHE、WORK、check_srt_name（開會了_[0-9]{3}_…）、
    │                               stage_path（不分層）；版面與保護沿 scripts/datadirs.py
    ├── catalogue.py              + 檔名解析（集數／族語別／語言別／語言代號）＋語言代號
    │                               對照表＋整批登記 CLI（吃：資料夾檔名清單；吐：inventory
    │                               pending 條目）
    ├── verify_band.py            + 雙槽帶前驗（吃：影片＋preset；吐：PASS／FAIL＋量測值）
    ├── ingest.py                 + TSV 驗證匯入（吃：2-vision 的 b*.tsv＋work dir 的
    │                               sheets.json；吐：transcripts.json／verified.json；
    │                               cue↔sheet 歸屬稽核、補尾端 tab）
    ├── make_srt.py               + 雙列組裝（吃：cues.json＋transcripts.json；吐：
    │                               3-srt 的 .srt＋.qc.json；走 srtlib.chain_with_spans
    │                               含 0.5 s 留白）
    ├── make_all.py               + 整批組裝＋進度表工作版（吐：kithann 快取 smkul.csv）
    ├── tracker.py                + 9 欄進度表列組法（make_all／publish／rebuild 三方共用）
    ├── publish.py                + 整批把關（0-cue 放行）→清 pending→遷 cues→定版 smkul.csv
    ├── rebuild.py                + 離線重建全部雙列 SRT＋smkul.csv、逐 byte 驗證
    └── presets.json              + aiyalaeho-bilingual（region 同、華語槽 h 66）
```

### 測試（tests/）

```
tests/
├── README.md                     ~ spec × scenario 表加 aiyalaeho 一節
└── aiyalaeho/
    ├── __init__.py               + 
    ├── test_paths.py             + store 版面（頂層 aiyalaeho/、1-cues/2-vision/3-srt、
    │                               不分層）；srt_name 格式；路徑保護
    ├── test_catalogue.py         + 檔名解析逐款（變體、括號註記、無字幕、混雜、錯檔名
    │                               整批中止）；語言代號對照逐條（含三個判讀）；整批登記
    │                               pending、重跑不重複、目錄無列照登
    ├── test_verify_band.py       + 合成剖面：兩列在槽內過／整帶下移仍過／套單列版型擋／
    │                               逐集判定
    ├── test_ingest.py            + 兩逝一 cue；列名錯、cue 不在 sheet 整批拒收；補 tab
    ├── test_make_srt.py          + 恆兩行帶標籤（族語：／華語：）／空列保留標籤行／兩列空不出／合併比合成
    │                               字串／0.5 s 留白／qc 計數
    ├── test_tracker.py           + 9 欄逐欄；成果檔名＝srt_name；長度由 1-cues 推導；
    │                               無播出資料與語音側欄（不設）
    ├── test_publish.py           + 0-cue 集 0 行交付不擋整批；未完成整批不寫；定版後
    │                               pending 清除
    └── test_rebuild.py           + 雙列 TSV 逐 byte 重建；缺件指名；pending 跳過
```

### 資料（Kari-SRT，apply 時建立；每檔由哪支程式產、吃什麼）

```
Kari-SRT/
├── README.md                     ~ 語料層說明加 aiyalaeho/
└── aiyalaeho/
    ├── inventory.json            + catalogue.py 登記 CLI 產；吃 資料夾檔名清單；
    │                               publish.py 清 pending 時回寫
    ├── smkul.csv                 + publish.py 產（定版）；吃 inventory＋1-cues；
    │                               rebuild.py 重算比對
    └── 1-ocr/
        ├── README.md             + 檔案架構與輸出入對應（不記 design／task 編號）
        ├── 1-cues/<srt_name>.json    + ocr.cli cues（--preset aiyalaeho-bilingual）＋
        │                               refine_cues 產；吃 mp4；publish 自 work dir 遷入
        ├── 2-vision/<srt_name>/bNN.tsv + 視覺辨識 subagent 直接寫；吃 contact sheet；
        │                               ingest.py 驗證匯入 work dir
        └── 3-srt/<srt_name>.srt      + make_srt.py 產（含 .qc.json）；吃 1-cues＋2-vision
```

### 工作區（kithann/，gitignore，可重生）

```
kithann/out/aiyalaeho/<srt_name>.work/   cues.json、strips/、sheets/、sheets.json、
                                         transcripts.json、verified.json
kithann/out/aiyalaeho/logs/              各步驟 log
kithann/out/aiyalaeho/smkul.csv          進度表工作版（make_all 產）
```

## Risks / Trade-offs

- [複製一套與 news 慢慢漂移] → 各自測試釘行為；真正共用的演算法都在
  引擎（ocr／srtlib），不複製；日後第三個語料再議抽共用。
- [`amis-xiuguluan-bilingual` 被別處引用（測試、文件、舊 work dir 的
  manifest）] → apply 時先全 repo grep；manifest 內是參數快照、不依賴
  preset 名，文件（SKILL.md、kithann 筆記）改提新名。
- [雙槽判準誤擋（整帶漂移超出容忍）] → FAIL 訊息帶量測數字，人工覆核後
  調 preset 槽界；不靜默放行、不自動退回偵測。
- [068 試跑 work dir（cues 已切）與正式流程銜接] → 登記後直接沿用
  `kithann/out/aiyalaeho/開會了_068_Amis_阿美.work`；slug＝srt_name 使
  目錄名不變。
- [Excel 相容] → smkul.csv 沿 news 的 utf-8-sig＋CRLF 慣例（tracker
  write 共用寫法）。
- [混雜兩支（119／122）版型沒人看過，硬切會切在錯的地方] → 排進整批但
  先下載、切前人工看 sheet_001；雙槽帶前驗逐集擋下異常者，報使用者裁定
  而非硬切。
- [整批視覺辨識約 240 批、24 小時級，中途可能被額度或連線打斷] → 每步
  可續跑（切 cue 跳過已有 cues.json、`ocr.cli pending` 列未讀 sheet、
  ingest 逐集匯入）；開跑前先把集數／批數／時數說出來。

## Migration Plan

無資料搬移（全新語料目錄）。順序：`add-episode-sourcing` 先歸檔（本
change 的 srt-data-store delta 以其後文本為基準）→ 本 change apply →
068 端對端驗收。回退：刪 `scripts/aiyalaeho/`＋`tests/aiyalaeho/`＋
`Kari-SRT/aiyalaeho/`，把 preset 那筆放回 news/presets.json，news 不受
影響。
