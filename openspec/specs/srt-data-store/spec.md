# srt-data-store Specification

## Purpose

定義字幕抽取成果與過程資料的存放契約：哪些資料放在 Kari-SRT submodule、
用什麼命名鍵、哪些必須進版本控制，以及「僅靠已 commit 的資料就能離線重建
全部交付 SRT」的保證。

## Requirements

### Requirement: Kari-SRT 為成果與過程資料的唯一正本

字幕 pipeline 的交付物與不可重生的過程資料 SHALL 存放於 `Kari-SRT/`
submodule，按「**語料 → 技術 → 編號階段**」分層，結構如下；主 repo
SHALL 只含程式、測試與文件，`kithann/` SHALL 維持整個 gitignore
（純工作區）。

```
Kari-SRT/
├── README.md                        總覽：分層說明與資料流
└── news/                            語料：族語新聞（其他語料另開頂層目錄）
    ├── inventory.json               影片 ↔ 節目資料對應（唯一正本，兩技術共用）
    ├── smkul.csv                    進度表（兩技術共用，見進度表 requirement）
    ├── 1-ocr/                       影像側：燒印字幕抽取（編號＝產生流程）
    │   ├── README.md                    OCR 檔案架構與流程說明
    │   ├── 1-cues/<srt_name>.json       每集時間軸
    │   ├── 2-vision/<srt_name>/*.tsv    視覺逐字稿（文字唯一來源）
    │   └── 3-srt/<srt_name>.srt         交付字幕（＋<srt_name>.qc.json）
    └── 2-asr/                       語音側：族語語音辨識與對應品質
        ├── README.md
        ├── 1-words/ 2-srt-raw/ 3-srt-ai/ 4-srt-quality/   逐集階段
        └── mt-cache/ quality-cache/                       跨集快取
        （階段內容的契約見 asr-bilingual-srt 與 parallel-corpus-quality）
```

同一份資料 SHALL 只有一個路徑；同一產物的不同狀態 SHALL 分開存放於
不同目錄，SHALL NOT 在同一路徑覆蓋。每個技術目錄 SHALL 有自己的
README，說明其檔案架構、產生流程與各階段輸出入對應。

已廢止路線的歷史產物（文稿供字索引、C-pass 普查逐字稿、文稿 vs 視覺
比對報告、投影中間檔、align 延伸試點的審查版／偵測／整併版）SHALL
NOT 存在於 store——其結論以文字記於對應 README，檔案本體只存在於
git 歷史。跨集快取（機器譯文、品質判定）是正本，SHALL 存在於 store。

`inventory.json` 是由節目目錄衍生的資料，SHALL 只存在於 store。主 repo 內
SHALL NOT 存在第二份 inventory；所有讀寫 inventory 的程式與腳本 SHALL 透過
單一路徑常數指向 store 那份。語料知識性質的設定檔（例如版型 preset）不受此
限，那是程式的一部分而非衍生資料。

#### Scenario: 交付物只有一個正本

- **WHEN** 尋找任何一集的交付 SRT、逐字稿或節目資料對應
- **THEN** 正本位於 `Kari-SRT/news/` 對應位置（影像側在 `1-ocr/`、
  語音側在 `2-asr/`），`kithann/srt/` 不存在，主 repo 內亦無第二份
  副本，Kari-SRT 頂層亦無殘留的舊位置

#### Scenario: inventory 沒有第二份

- **WHEN** 在主 repo 內搜尋 inventory 資料檔
- **THEN** 找不到；所有取用點都解析到 `Kari-SRT/news/inventory.json`

#### Scenario: 工作區資料不進版本控制

- **WHEN** 檢視主 repo 的 git 追蹤狀態
- **THEN** `kithann/` 之下沒有任何被追蹤的檔案（work dir、log、
  暫存影片皆可重生，不 commit）

#### Scenario: 技術目錄各有 README

- **WHEN** 瀏覽 `news/1-ocr/` 或 `news/2-asr/`
- **THEN** 各自的 README.md 說明該技術的檔案架構、產生流程與
  輸出入對應，目錄編號即產生順序

#### Scenario: 歷史目錄已清除

- **WHEN** 在 Kari-SRT 內搜尋 `2-from_rtf`、`4-vision-rtf`、`5-report`、
  `2-entries`、`3-srt-raw`、`4-srt-ai`、`5-align`、`6-srt-complete`
- **THEN** 找不到任何目錄或檔案；廢止結論記於對應 README

#### Scenario: 跨集快取在 store

- **WHEN** 檢視 `news/2-asr/`
- **THEN** `mt-cache/` 與 `quality-cache/` 存在，各為每引擎／每裁判
  一個 JSONL 檔

### Requirement: aiyalaeho 語料的 store 結構

`Kari-SRT/aiyalaeho/` SHALL 為《開會了》語料交付物與不可重生過程資料的唯一
正本，結構如下；編號＝產生順序。本語料 SHALL NOT 有語音側技術目錄——交付
雙列 SRT 的族語文字來自畫面，不經語音辨識。

```
Kari-SRT/aiyalaeho/
├── inventory.json               集數 ↔ 檔名／族語別(英)(中)／語言別／
│                                語言代號／srt_name／理由／影片長度
│                                （後兩欄僅字幕版型異常集有值）；pending 語意同 news
├── smkul.csv                    進度表：雙語集（見「aiyalaeho 進度表」）
├── smkul-字幕版型異常.csv       另表：字幕版型異常集（見「aiyalaeho 字幕版型異常集另表」）
└── 1-ocr/                       影像側：燒印字幕抽取
    ├── README.md                檔案架構與各階段輸出入對應
    ├── 1-cues/<srt_name>.json       每集時間軸（真實切換點、無留白）
    ├── 2-vision/<srt_name>/*.tsv    視覺逐字稿（每 cue 兩逝：族語列、han）
    ├── 3-srt/<srt_name>.srt         交付雙列字幕（＋<srt_name>.qc.json）
    └── 4-語言檢查/                  逐條語言判定（只讀 3-srt/ 產出）
        ├── README.md                資料來源、誰讀它、判定的限制
        ├── 詞庫/<族語>.txt          官方族語辭典蒸餾的詞庫，一行一詞
        ├── 逐條語言標記.csv         非本集族語的條目，一條一列
        └── 逐集語言分布.csv         逐集各標籤的計數
```

同一份資料 SHALL 只有一個路徑；同一產物的不同狀態 SHALL 分開存放，
SHALL NOT 在同一路徑覆蓋——與既有 store 原則相同。`1-ocr/` 底下 SHALL NOT
為字幕版型異常集存放任何檔案。

`4-語言檢查/詞庫/` SHALL 為 store 正本：它由外部辭典蒸餾而來，不是本語料
的衍生視圖，沒有它判定就無法離線重跑。辭典原始檔 SHALL NOT 進入 store。

#### Scenario: 交付物只有一個正本

- **WHEN** 尋找《開會了》任一集的交付 SRT、逐字稿或時間軸
- **THEN** 正本位於 `Kari-SRT/aiyalaeho/1-ocr/` 對應階段目錄，主 repo 與
  工作區內沒有第二份正本

#### Scenario: 技術目錄有 README

- **WHEN** 瀏覽 `aiyalaeho/1-ocr/`
- **THEN** README.md 說明檔案架構、產生流程與各階段輸出入對應

#### Scenario: 字幕版型異常集在技術目錄留不下痕跡

- **WHEN** 在 `aiyalaeho/1-ocr/` 底下尋找任一字幕版型異常集的檔案
- **THEN** 找不到時間軸、逐字稿或 SRT；該集只出現在 inventory 與另表

#### Scenario: 詞庫在 store 內

- **WHEN** 在沒有網路、也沒有辭典原始檔的環境重跑語言判定
- **THEN** `4-語言檢查/詞庫/` 底下每個族語別都有詞庫檔，判定得以完成

### Requirement: 命名鍵統一為 srt_name

Kari-SRT 內每集資料的目錄與檔名 SHALL 一律使用 `srt_name`
（`<播出日期YYYYMMDD>_<集數三位>_<時段>_<族語英>_<族語中>`，例
`20210201_032_午間_Atayal_泰雅`）。內部 work dir 的 slug、早期的簡寫
（`032午_泰雅`）與攤平檔名（`rukai_043_b01-03.tsv`）SHALL NOT 出現在
Kari-SRT 內。

逐集資料 SHALL 存放於階段目錄下的**播出月份**一層（`<年-月>/`，例
`2021-02/`）。月份鍵 SHALL 由 `srt_name` 的播出日期推導，SHALL NOT
另存一份對應資料。總表（`inventory.json`、`smkul.csv`）SHALL 維持
不分層。

#### Scenario: 一個名字找齊一集的所有資料

- **WHEN** 已知某集的 `srt_name`
- **THEN** `news/1-ocr/3-srt/<年-月>/<srt_name>.srt`、
  `news/1-ocr/1-cues/<年-月>/<srt_name>.json`、
  `news/1-ocr/2-vision/<年-月>/<srt_name>/`，以及 `news/2-asr/`
  各階段目錄下的同名檔案，全部以同一字串定位，無須另查對應表；月份
  一層由該字串自身推導

#### Scenario: 舊命名已遷移

- **WHEN** 在 Kari-SRT 內搜尋舊式命名（slug、`NNN午_族語` 簡寫、
  `*_bNN-NN.tsv` 攤平檔）
- **THEN** 找不到任何一個；早期攤平的 TSV 已改置於
  `news/1-ocr/2-vision/<年-月>/<srt_name>/` 之下

#### Scenario: 逐集資料依播出月份分層

- **WHEN** 檢視任一階段目錄
- **THEN** 其下第一層是播出月份目錄，逐集檔案位於月份目錄之內，沒有
  任何逐集檔案直接躺在階段目錄下

#### Scenario: 總表不分層

- **WHEN** 檢視 `inventory.json`、`smkul.csv`
- **THEN** 它們維持在語料層原位，未被加上月份一層

#### Scenario: 分層後仍可離線重建且逐 byte 相同

- **WHEN** 在新的分層路徑下執行離線重建驗證
- **THEN** 全部交付 SRT 與分層前逐 byte 相同，驗證通過

### Requirement: 僅靠已 commit 的資料可離線重建全部 SRT

主 repo（程式）加 Kari-SRT（`news/1-ocr/` 的 `1-cues/`＋`2-vision/`，
與 `news/smkul.csv`）SHALL 足以在不存取原始影片、不呼叫任何模型
的情況下，重建出與 `Kari-SRT/news/1-ocr/3-srt/` 內容逐 byte 相同的
**全部已交付 SRT**。集數隨批次成長，不固定。

要重建哪些集數 SHALL 由 `news/1-ocr/3-srt/` 裡實際有哪些檔決定，
SHALL NOT 由任何欄位或登記檔宣告。節目目錄只提供每一集的識別與
素材位置，SHALL NOT 決定某集該不該有交付物。

`news/smkul.csv` 本身 SHALL NOT 以逐 byte 重算比對——它是輸入而非
產出，內容由人維護。對它的把關改為不變量檢查，見「節目目錄的不變量」。

#### Scenario: 工作目錄全毀後重建

- **WHEN** `kithann/out/` 被整個刪除，僅存主 repo 與 Kari-SRT，
  執行重建流程
- **THEN** 產出的每一個 SRT 與 Kari-SRT 內已 commit 的版本逐 byte 相同，
  過程中不讀取任何 `.mxf`、不發出任何模型呼叫

#### Scenario: 缺件時明確失敗

- **WHEN** 重建流程執行時某集已有 `news/1-ocr/3-srt/<成果檔名>.srt`，
  卻缺少 `news/1-ocr/1-cues/<成果檔名>.json` 或對應 TSV
- **THEN** 該流程以非零狀態結束並指名缺少的檔案，SHALL NOT 產出
  不完整的 SRT 冒充完整交付

#### Scenario: 只做到一半的集數不算缺件

- **WHEN** 某集有 `1-cues/` 的時間軸，但 `3-srt/` 還沒有它的 SRT
- **THEN** 重建驗證照常通過，SHALL NOT 把它報成缺件

### Requirement: aiyalaeho 僅靠已 commit 的資料可離線重建

主 repo（程式）加 Kari-SRT（`aiyalaeho/1-ocr/` 的 `1-cues/`＋`2-vision/`＋
`4-語言檢查/詞庫/`，與 `aiyalaeho/smkul.csv`、`aiyalaeho/smkul-字幕版型異常.csv`）
SHALL 足以在不存取影片、不存取辭典原始檔、不呼叫任何模型的情況下，重建出與
`aiyalaeho/1-ocr/3-srt/` 逐 byte 相同的全部已交付雙列 SRT，以及
`aiyalaeho/1-ocr/4-語言檢查/` 的 `逐條語言標記.csv` 與 `逐集語言分布.csv`。
缺件 SHALL 指名失敗；字幕版型異常集 SHALL NOT 被要求任何 `1-ocr/` 輸入。

兩張語言檢查 CSV 的重建 SHALL 以重建出來的交付 SRT 為輸入，而非 store 內既有的
交付 SRT——上游換版而下游未重產時，這樣才驗得出來。

兩張 smkul CSV SHALL NOT 以逐 byte 重算比對，改以不變量檢查把關。

#### Scenario: 工作目錄全毀後重建

- **WHEN** 工作區被整個刪除，僅存主 repo 與 Kari-SRT，執行本語料的重建驗證
- **THEN** 每個交付 SRT 與兩張語言檢查 CSV 逐 byte 相同，過程不讀影片、
  不讀辭典原始檔、不呼叫模型

#### Scenario: 缺件時明確失敗

- **WHEN** 某集已有交付 SRT，卻缺 `1-cues/<成果檔名>.json` 或 TSV
- **THEN** 重建以非零狀態結束並指名缺少的檔案

#### Scenario: 字幕版型異常集不算缺件

- **WHEN** 某字幕版型異常集在 `1-ocr/` 底下沒有任何檔案，執行重建驗證
- **THEN** 驗證不因它報缺件

#### Scenario: 詞庫缺件時明確失敗

- **WHEN** `4-語言檢查/詞庫/` 缺任一族語別的詞庫檔，執行重建驗證
- **THEN** 驗證以非零狀態結束並指名缺少的族語別，SHALL NOT 靜默跳過該族的集數

### Requirement: 校讀完成的判準比對編號集合

判斷一集校讀是否完成 SHALL 比對校讀紀錄的 cue 編號集合與該集時間軸的 cue
編號集合，兩者相等才算完成。SHALL NOT 只比對兩者的數量。

理由：數量相等不蘊含集合相等。若校讀紀錄殘留了已不存在的舊編號，數量可以
湊足而實際仍有 cue 未讀，該集會被誤判為完成並定版進 store。

#### Scenario: 數量湊足但編號不符時判為未完成

- **WHEN** 某集的校讀紀錄筆數不少於 cue 數，但其中含有不屬於該集時間軸的編號
- **THEN** 該集判為校讀未完成，不得清除其 pending 標記

### Requirement: aiyalaeho 進度表

`aiyalaeho/smkul.csv` SHALL 有下列 9 欄，依此順序：成果檔名、節目名稱、
集數、族語別(英)、族語別(中)、語言別、語言別代號、原始影片檔案位置、
備註。其中：

- 前七欄 SHALL 與其他語料的表同名同序（見 `episode-catalogue`）；
- 本語料查無播出資料、又無語音側，SHALL NOT 設年度、播出日期、
  播出時段欄——無資料的欄不養；日後取得權威播出日期時再增欄記入，
  SHALL NOT 因此改動命名鍵；
- SHALL NOT 設影片長度欄，也 SHALL NOT 設任何記錄處理階段的欄；
- 字幕版型異常集 SHALL NOT 列入本表（見「aiyalaeho 字幕版型異常集另表」）。

#### Scenario: 九欄與成果檔名

- **WHEN** 檢視 `aiyalaeho/smkul.csv`
- **THEN** 欄位恰為上列 9 欄；每列成果檔名由集數與族語別推導得出

#### Scenario: 字幕版型異常集不在本表

- **WHEN** 檢視 `aiyalaeho/smkul.csv`
- **THEN** 沒有任何一列的成果檔名出現在另表中

### Requirement: aiyalaeho 字幕版型異常集另表

`aiyalaeho/smkul-字幕版型異常.csv` SHALL 列出全部字幕版型異常集，
欄位為 `smkul.csv` 的 9 欄原樣、同順序，**不多一欄**。其中：

- 成果檔名 SHALL 作為鍵，不表示存在對應檔案；
- `備註` SHALL NOT 為空，且 SHALL 說明這一集為什麼不是雙語交付
  （`無字幕`、`僅華語字幕`、`版型不符：…`、`人工判定：…` 之一）——
  兩張表欄位相同，`備註` 非空是這張表唯一的自我宣告；
- 編碼、換行與寫法 SHALL 與 `smkul.csv` 相同（Excel 可讀）。

#### Scenario: 九欄且備註非空

- **WHEN** 檢視 `aiyalaeho/smkul-字幕版型異常.csv`
- **THEN** 欄位與 `smkul.csv` 同名同序、共 9 欄；每列 `備註` 非空

#### Scenario: 兩張表互斥且合計完整

- **WHEN** 同時檢視 `smkul.csv` 與 `smkul-字幕版型異常.csv`
- **THEN** 沒有任何 `成果檔名` 同時出現在兩表；兩表合起來就是本語料
  全部有影片的集數

#### Scenario: 備註空白時指名失敗

- **WHEN** 另表某列的 `備註` 為空
- **THEN** 驗證以非零狀態結束並指名該列

### Requirement: 只有精修過的時間軸才進 store

把時間軸放進 `news/1-ocr/1-cues/` 的流程 SHALL 只接受**已精修**的時間軸。
某集的工作目錄只有粗切時間軸（0.2 秒格點、尚未經 25fps 邊界精修）時，
該集 SHALL NOT 入 store；流程 SHALL 指名該集並以非零狀態結束，
SHALL NOT 靜默略過該集的時間軸而讓其餘檔案照樣入庫。

工作目錄完全沒有時間軸時亦同 SHALL 指名中止——「找不到時間軸」與
「時間軸還沒精修」都是不得交付的狀態，兩者 SHALL 各自講清楚是哪
一種。

store 內已有該集的時間軸時：內容與要寫入的一致 SHALL NOT 覆寫，
連檔案本身都不重寫；內容不同才覆寫。一致與否 SHALL 以正規化（排版、
鍵排序）之後的內容比較，SHALL NOT 比工作目錄檔案的原始位元組——
工作目錄那份的鍵是插入順序，直接比會每次都判成不同。

理由：交付 SRT 的每一個時間戳都由這份時間軸推導，而粗切與精修的
精度差一個數量級（0.2 秒 vs 0.05 秒）。兩種精度混在同一個目錄裡，
從檔案本身看不出某一集是哪一種，下游也沒有辦法分別對待。把關口設
在入庫這一步，`1-cues/` 就有一個可以直接宣告的性質：**裡面每一份都
是精修過的**。不覆寫相同內容則是因為曾經一次入庫重寫了 74 個內容
根本沒變的已交付檔案。

#### Scenario: 只有粗切時間軸的集數擋在門外

- **WHEN** 某集的工作目錄只有粗切時間軸，執行入庫流程
- **THEN** 流程指名該集、說明它尚未精修，並以非零狀態結束；
  該集的時間軸沒有進入 store

#### Scenario: 沒有時間軸與沒有精修分開講

- **WHEN** 某集的工作目錄完全沒有時間軸
- **THEN** 流程指名該集並說明是「找不到時間軸」，與「尚未精修」
  是不同的訊息

#### Scenario: 精修過的照常入庫

- **WHEN** 某集的工作目錄有精修過的時間軸，store 還沒有該集
- **THEN** 該份時間軸寫入 `news/1-ocr/1-cues/<年-月>/<成果檔名>.json`

#### Scenario: 內容相同不重寫

- **WHEN** 某集的時間軸已在 store，工作目錄那份正規化後與它相同，
  再次執行入庫流程
- **THEN** 該檔案沒有被重寫

#### Scenario: 內容不同才覆寫

- **WHEN** 某集重切之後時間軸真的改了，再次執行入庫流程
- **THEN** store 內該檔以新內容覆寫

#### Scenario: store 內每一份時間軸都是精修過的

- **WHEN** 檢視 `news/1-ocr/1-cues/` 內任一份時間軸
- **THEN** 它記錄自己已經精修

### Requirement: 兩側交付都在時，時間軸必須逐條相同

離線重建驗證 SHALL 一併把關語音側：對每個有影像側交付的集數，語音側
**存在的每一個**交付 SRT（`2-srt-raw/`、`3-srt-ai/`、`4-srt-quality/`）
SHALL 只由 store 內容離線重建——`2-srt-raw` 由 `1-words/`＋影像側
時間軸重投影渲染、`3-srt-ai` 由 `2-srt-raw`＋`mt-cache/`、
`4-srt-quality` 由 `3-srt-ai`＋`quality-cache/`——且與店面檔逐 byte
相同；重建結果自然與影像側交付 SRT 的 (index, start/end) 序列逐條
相同。任一檔不同 SHALL 使驗證以非零狀態結束、指名該集與該檔，並
SHALL 修正到相同為止——重投影＋重新 render，不需重新辨識、不需重問
模型。

語音側尚未產出**不是錯誤**：某階段沒有該集的檔時，驗證 SHALL 照常
通過，SHALL NOT 輸出警告。語音側是獨立的一條線，它做到哪由各階段
目錄裡有沒有該集的檔照實反映，SHALL NOT 另設欄位記錄。但店面**有**
某階段的檔而其上游（快取或前一階段）缺件時，那是錯誤。

#### Scenario: 兩側都在但不同軸即失敗

- **WHEN** 某集數兩側 SRT 都存在，但重建出的 `2-srt-raw`
  與店面檔不同
- **THEN** 驗證以非零狀態結束並指名該集與該檔

#### Scenario: 只有影像側交付照樣通過

- **WHEN** 某集數有影像側交付 SRT，`2-srt-raw/` 無該集的檔
- **THEN** 驗證通過，且不輸出任何與該集語音側有關的警告

#### Scenario: 做到一半照樣通過

- **WHEN** 某集有 `2-srt-raw`、`3-srt-ai`，尚無 `4-srt-quality`
- **THEN** 驗證通過，不輸出警告

#### Scenario: 全部同軸且逐 byte 相同則通過

- **WHEN** 每一個有語音側交付的集數，其每個交付檔都重建得逐 byte 相同
- **THEN** 驗證通過

### Requirement: store 內的資料檔人打開就讀得懂

`Kari-SRT/` 內每個資料檔 SHALL 以人可直接閱讀為準：JSON SHALL 排版
過（多行縮排、鍵排序、非 ASCII 不轉義），使 diff 能逐行看出改動；
一列一筆的 JSONL 快取不縮排，但 SHALL 鍵排序、非 ASCII 不轉義。給人
看的交付用 SRT／CSV 文字格式，行首標籤用中文全名，SHALL NOT 用縮寫
或代號。目錄用「編號-內容」命名，編號即製作先後。

#### Scenario: JSON 逐行可 diff

- **WHEN** 店面某個 JSON 檔的一個欄位改了值
- **THEN** diff 只顯示那一行

#### Scenario: 中文不轉義

- **WHEN** 打開店面任一 JSON 或 JSONL 檔
- **THEN** 中文與族語字元原樣可讀，沒有 `\uXXXX`

### Requirement: 各階段做完就各自入庫

`1-cues/`、`2-vision/`、`3-srt/` SHALL 各自在該階段對某一集做完時就進入
Kari-SRT，SHALL NOT 要求整集全部階段完成才准入庫，也 SHALL NOT 要求
同批其他集數的進度。

理由：三個階段每一集都要跑幾十小時，等整集做完才入庫，代表幾十小時的
成果在工作區裡沒有備份地放著——而工作區是 gitignore 的。曾經有一集的
時間軸只剩工作目錄一份，而它的母帶已經刪掉了。

#### Scenario: 視覺辨識還沒讀完，時間軸照樣入庫

- **WHEN** 某集的時間軸已精修，視覺辨識一條 cue 都還沒讀
- **THEN** 該集的時間軸寫入 `1-cues/`，流程不因視覺辨識未完成而擋下

#### Scenario: 一集的階段可以只做到一半

- **WHEN** 檢視 Kari-SRT，某集在 `1-cues/` 有檔、在 `3-srt/` 沒有
- **THEN** 那是正常狀態，任何驗證都 SHALL NOT 因此失敗

### Requirement: 下游階段的集數必為上游的子集

離線重建驗證 SHALL 檢查各階段之間的包含關係：`3-srt/` 的成果檔名集合
SHALL 是 `2-vision/` 的子集，`2-vision/` SHALL 是 `1-cues/` 的子集。

下游有而上游沒有的集數 SHALL 使驗證以非零狀態結束，並指名是哪一集
在哪一層缺——那份交付物重建不出來。上游有而下游沒有 SHALL 視為正常，
那只表示還沒做到那一步。

#### Scenario: 交付 SRT 沒有對應的時間軸

- **WHEN** `3-srt/` 有某集的 SRT，`1-cues/` 沒有該集的時間軸
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層

#### Scenario: 上游多出來的集數不算錯

- **WHEN** `1-cues/` 有 75 集，`3-srt/` 只有 40 集
- **THEN** 驗證通過

### Requirement: 節目目錄的不變量

`news/smkul.csv`、`aiyalaeho/smkul.csv`、`aiyalaeho/smkul-字幕版型異常.csv`
是輸入而非產出，SHALL NOT 以逐 byte 重算比對。離線重建驗證 SHALL 改以
下列不變量把關，任一條不成立時指名該列並以非零狀態結束：

- `成果檔名` 合乎命名規格，同表內唯一，且與同列識別欄互推得出來；
- `語言別代號` 在隨 repo 走的對照表之內；
- `族語別(中)` 與 `族語別(英)` 一對一，對得上對照表；
- 每一列的素材位置欄非空；
- 列序依 `成果檔名` 排；
- 各階段目錄裡每一個檔，其成果檔名在表中找得到（孤兒檔即錯誤）。

表中有而檔案系統沒有的集數 SHALL NOT 視為錯誤——那是還沒做。

以文字為素材、永遠不會有交付 SRT 的表，SHALL 豁免「各階段目錄」
相關的那幾條。

#### Scenario: 有人手改壞一格

- **WHEN** 某列的 `語言別代號` 被改成對照表沒有的值
- **THEN** 驗證指名該列與該欄，說出那個值不在對照表裡

#### Scenario: 孤兒檔被抓到

- **WHEN** `3-srt/` 有一個 SRT，其成果檔名在節目目錄中找不到
- **THEN** 驗證以非零狀態結束並指名該檔

#### Scenario: 還沒做的集數不算錯

- **WHEN** 節目目錄有 969 列，各階段目錄合計只有 75 集
- **THEN** 驗證通過

### Requirement: 時間軸不記機器專屬路徑

`1-cues/` 內的時間軸 SHALL NOT 記錄來源影片在本機的路徑。

理由：那是當時那台機器的暫存位置，換一台機器就沒有意義，卻會讓
Kari-SRT 的內容綁定在一台機器上——同一份資料在另一台機器重算會
得到不同的位元組。每一集的影片位置由節目目錄的 `原始影片檔案位置`
記錄，那是相對於語料根的路徑。

#### Scenario: 時間軸裡沒有本機路徑

- **WHEN** 檢視 `1-cues/` 內任一份時間軸
- **THEN** 裡面沒有任何絕對路徑，也沒有指向工作區的欄位

### Requirement: 不產出逐集 QC 摘要檔

組裝流程 SHALL NOT 在 `3-srt/` 旁邊產出逐集的 QC 摘要檔（cue 數、
有字 cue 數、族語列數、華語列數、SRT 行數）。

理由：沒有任何流程讀它，離線重建驗證也不比對它，而每一個數字都能
從時間軸與交付 SRT 當場算出來。要給人看的逐集數字 SHALL 收進一張
逐集 CSV，一列一集，而不是散成一集一個小檔。

#### Scenario: 組裝之後旁邊沒有摘要檔

- **WHEN** 對某集執行組裝流程
- **THEN** `3-srt/` 底下只有該集的 SRT，沒有同名的 QC 摘要檔
