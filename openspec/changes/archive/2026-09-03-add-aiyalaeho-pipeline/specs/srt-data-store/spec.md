## MODIFIED Requirements

### Requirement: 命名鍵統一為 srt_name

Kari-SRT 內每集資料的目錄與檔名 SHALL 一律使用**該語料定義的** `srt_name`
命名鍵，且一個鍵 SHALL 足以在該語料每個階段目錄定位同一集，無須另查對應表。
各語料的鍵格式與逐集分層：

- **`news/`**：`<播出日期YYYYMMDD>_<集數三位>_<時段>_<族語英>_<族語中>`
  （例 `20210201_032_午間_Atayal_泰雅`）。逐集資料 SHALL 存放於階段目錄下的
  **播出月份**一層（`<年-月>/`，例 `2021-02/`）；月份鍵 SHALL 由 `srt_name`
  的播出日期推導，SHALL NOT 另存一份對應資料。
- **`aiyalaeho/`**：`開會了_<集數三位>_<族語英>_<族語中>`（例
  `開會了_068_Amis_阿美`）。逐集資料 SHALL 直接位於階段目錄下，**不分層**
  ——本語料共四十餘集，無分層必要。

兩語料的鍵 SHALL 無法相撞（一個以 8 碼數字起頭、一個以「開會了_」起頭）。
內部 work dir 的 slug、早期的簡寫（`032午_泰雅`）與攤平檔名
（`rukai_043_b01-03.tsv`）SHALL NOT 出現在 Kari-SRT 內。跨集產物
（比對報告、翻譯快取）與總表（`inventory.json`、`smkul.csv`）SHALL 維持
不分層。

#### Scenario: 一個名字找齊一集的所有資料

- **WHEN** 已知某集的 `srt_name`
- **THEN** `news/1-ocr/6-srt/<年-月>/<srt_name>.srt`、
  `news/1-ocr/1-cues/<年-月>/<srt_name>.json`、
  `news/1-ocr/2-from_rtf/<年-月>/<srt_name>.json`、
  `news/1-ocr/3-vision/<年-月>/<srt_name>/`、
  `news/1-ocr/4-vision-rtf/<年-月>/<srt_name>/`，以及 `news/2-asr/`
  各階段目錄下的同名檔案，全部以同一字串定位，無須另查對應表；月份
  一層由該字串自身推導

#### Scenario: aiyalaeho 一個名字找齊一集的所有資料

- **WHEN** 已知 `開會了_068_Amis_阿美`
- **THEN** `aiyalaeho/1-ocr/1-cues/開會了_068_Amis_阿美.json`、
  `aiyalaeho/1-ocr/2-vision/開會了_068_Amis_阿美/`、
  `aiyalaeho/1-ocr/3-srt/開會了_068_Amis_阿美.srt` 全部以同一字串定位，
  中間沒有月份一層

#### Scenario: 舊命名已遷移

- **WHEN** 在 Kari-SRT 內搜尋舊式命名（slug、`NNN午_族語` 簡寫、
  `*_bNN-NN.tsv` 攤平檔）
- **THEN** 找不到任何一個；早期攤平的 TSV 已改置於
  `news/1-ocr/3-vision/<年-月>/<srt_name>/` 之下

#### Scenario: news 逐集資料依播出月份分層

- **WHEN** 檢視 `news/` 任一階段目錄
- **THEN** 其下第一層是播出月份目錄，逐集檔案位於月份目錄之內，沒有
  任何逐集檔案直接躺在階段目錄下

#### Scenario: 跨集產物與總表不分層

- **WHEN** 檢視比對報告目錄、翻譯快取目錄，以及各語料的
  `inventory.json`、`smkul.csv`
- **THEN** 它們維持在語料層或既有位置，未被加上月份一層

#### Scenario: 分層後仍可離線重建且逐 byte 相同

- **WHEN** 在各自的分層路徑下執行離線重建驗證
- **THEN** 全部交付 SRT 與 store 內已 commit 的版本逐 byte 相同，驗證通過

#### Scenario: 兩語料的鍵不相撞

- **WHEN** 將兩語料全部 `srt_name` 放進同一個集合
- **THEN** 集合大小等於兩語料集數之和，沒有重複

## ADDED Requirements

### Requirement: aiyalaeho 語料的 store 結構

`Kari-SRT/aiyalaeho/` SHALL 為《開會了》語料交付物與不可重生過程資料的唯一
正本，結構如下；編號＝產生順序。本語料 SHALL NOT 有語音側技術目錄——交付
雙列 SRT 的族語文字來自畫面，不經語音辨識。

```
Kari-SRT/aiyalaeho/
├── inventory.json               集數 ↔ 檔名／族語別(英)(中)／語言別／
│                                語言代號／srt_name；pending 語意同 news
├── smkul.csv                    進度表（見「aiyalaeho 進度表」）
└── 1-ocr/                       影像側：燒印字幕抽取
    ├── README.md                檔案架構與各階段輸出入對應
    ├── 1-cues/<srt_name>.json       每集時間軸（真實切換點、無留白）
    ├── 2-vision/<srt_name>/*.tsv    視覺逐字稿（每 cue 兩逝：族語列、han）
    └── 3-srt/<srt_name>.srt         交付雙列字幕（＋<srt_name>.qc.json）
```

同一份資料 SHALL 只有一個路徑；同一產物的不同狀態 SHALL 分開存放，
SHALL NOT 在同一路徑覆蓋——與既有 store 原則相同。

#### Scenario: 交付物只有一個正本

- **WHEN** 尋找《開會了》任一集的交付 SRT、逐字稿或時間軸
- **THEN** 正本位於 `Kari-SRT/aiyalaeho/1-ocr/` 對應階段目錄，主 repo 與
  工作區內沒有第二份正本

#### Scenario: 技術目錄有 README

- **WHEN** 瀏覽 `aiyalaeho/1-ocr/`
- **THEN** README.md 說明檔案架構、產生流程與各階段輸出入對應

### Requirement: aiyalaeho 進度表

`aiyalaeho/smkul.csv` SHALL 有下列 9 欄，依此順序：節目名稱、集數、
族語別(英)、族語別(中)、語言別、語言代號、影片檔案位置、影片長度、
成果檔名。其中：

- 成果檔名 SHALL 為該集的 `srt_name`；
- 影片長度 SHALL 由 `1-cues/` 該集時間軸推導，SHALL NOT 手填；
- 本語料查無播出資料、又無語音側，SHALL NOT 設年度、播出日期、
  播出時段、字幕srt狀態、語音辨識模型欄——無資料的欄不養；日後取得
  權威播出日期時再增欄記入，SHALL NOT 因此改動命名鍵；
- 定版由整批把關通過的流程寫入、工作區另有可隨時刷新的快取版本、
  pending 集數不列入定版表——SHALL 沿用既有進度表要求的語意。

#### Scenario: 九欄與成果檔名

- **WHEN** 檢視定版的 `aiyalaeho/smkul.csv`
- **THEN** 欄位恰為上列 9 欄；每列成果檔名等於該集 `srt_name`

#### Scenario: 影片長度由時間軸推導

- **WHEN** 任何時點重算進度表
- **THEN** 每列影片長度取自該集 `1-cues/` 時間軸，重算結果逐 byte 相同

### Requirement: 0-cue 集數照交付且不擋定版

已登記且影片處理完成、時間軸切出 0 條 cue 的集數（無字幕的集數就是如此），
SHALL 以 0 行 SRT 交付並產生 qc 紀錄；其校讀完成判準 SHALL 視為成立
（空的 cue 集合被空的校讀集合涵蓋），SHALL NOT 使整批定版被擋。

#### Scenario: 無字幕集數走完整批

- **WHEN** 某集切出 0 條 cue，其餘集數皆完成，執行整批定版
- **THEN** 該集交付 0 行 SRT、pending 清除、定版成功，隨後的離線重建驗證
  通過

### Requirement: aiyalaeho 僅靠已 commit 的資料可離線重建

主 repo（程式）加 Kari-SRT（`aiyalaeho/1-ocr/` 的 `1-cues/`＋`2-vision/`，
與 `aiyalaeho/inventory.json`）SHALL 足以在不存取影片、不呼叫任何模型的
情況下，重建出與 `aiyalaeho/1-ocr/3-srt/` 逐 byte 相同的全部已交付雙列 SRT
與 `aiyalaeho/smkul.csv`。缺件 SHALL 指名失敗；pending 集數 SHALL 跳過
——語意同 news 的既有要求，範圍及於本語料。

#### Scenario: 工作目錄全毀後重建

- **WHEN** 工作區被整個刪除，僅存主 repo 與 Kari-SRT，執行本語料的重建驗證
- **THEN** 每個交付 SRT 與 smkul.csv 逐 byte 相同，過程不讀影片、不呼叫模型

#### Scenario: 缺件時明確失敗

- **WHEN** 某已交付集數缺 `1-cues/<srt_name>.json` 或 TSV
- **THEN** 重建以非零狀態結束並指名缺少的檔案
