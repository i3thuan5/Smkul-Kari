# srt-data-store Delta

## MODIFIED Requirements

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
    └── 3-srt/<srt_name>.srt         交付雙列字幕（＋<srt_name>.qc.json）
```

同一份資料 SHALL 只有一個路徑；同一產物的不同狀態 SHALL 分開存放，
SHALL NOT 在同一路徑覆蓋——與既有 store 原則相同。`1-ocr/` 底下 SHALL NOT
為字幕版型異常集存放任何檔案。

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

### Requirement: aiyalaeho 僅靠已 commit 的資料可離線重建

主 repo（程式）加 Kari-SRT（`aiyalaeho/1-ocr/` 的 `1-cues/`＋`2-vision/`，
與 `aiyalaeho/inventory.json`）SHALL 足以在不存取影片、不呼叫任何模型的
情況下，重建出與 `aiyalaeho/1-ocr/3-srt/` 逐 byte 相同的全部已交付雙列 SRT、
`aiyalaeho/smkul.csv` 與 `aiyalaeho/smkul-字幕版型異常.csv`。缺件 SHALL 指名
失敗；pending 集數 SHALL 跳過；字幕版型異常集 SHALL NOT 被要求任何 `1-ocr/`
輸入，其另表列僅由 inventory 推導——語意同 news 的既有要求，範圍及於本語料。

#### Scenario: 工作目錄全毀後重建

- **WHEN** 工作區被整個刪除，僅存主 repo 與 Kari-SRT，執行本語料的重建驗證
- **THEN** 每個交付 SRT、`smkul.csv` 與 `smkul-字幕版型異常.csv` 逐 byte
  相同，過程不讀影片、不呼叫模型

#### Scenario: 缺件時明確失敗

- **WHEN** 某已交付集數缺 `1-cues/<srt_name>.json` 或 TSV
- **THEN** 重建以非零狀態結束並指名缺少的檔案

#### Scenario: 字幕版型異常集不算缺件

- **WHEN** 某字幕版型異常集在 `1-ocr/` 底下沒有任何檔案，執行重建驗證
- **THEN** 驗證不因它報缺件；其另表列由 inventory 重建且逐 byte 相同

#### Scenario: 另表被改動時報差異

- **WHEN** store 內的 `smkul-字幕版型異常.csv` 與由 inventory 重算的內容不同
- **THEN** 重建驗證以非零狀態結束並指名該表

### Requirement: 批次進行中的集數以 pending 標記且不參與重建驗證

尚未完成的集數 SHALL 在 inventory 內標記為 pending。重建驗證與進度表列的
產生 SHALL 跳過 pending 集數：不要求其交付品與輸入存在，也不為其產生進度表列。

pending 與既有三個標記語意不重疊，SHALL 分別使用：來源不完整而永不交付者、
已交付但來源短缺者、字幕版型異常而不進雙語交付者（aiyalaeho 的理由欄）、
以及本批尚未完成者。

理由：inventory 是 store 的一部分，而登記必須發生在校讀之前（後續步驟要靠它
查對每集的命名）。若不區分「已交付」與「進行中」，store 一登記新集數就會宣告
自己缺件，而偵測缺件正是重建驗證的核心能力。

#### Scenario: 批次進行中 store 仍然自洽

- **WHEN** 新一批集數已登記進 inventory 並標記 pending，其交付品尚未產生，
  此時執行重建驗證
- **THEN** 驗證通過：pending 集數被跳過，重建出的進度表與 store 內已 commit
  的版本逐 byte 相同

#### Scenario: 未標記 pending 的集數缺件時仍然失敗

- **WHEN** 某集未標記 pending，但其 `cues/` 或逐字稿不存在
- **THEN** 重建驗證以非零狀態結束並指名該集——pending 是登記用的宣告，
  不得成為繞過缺件檢查的手段

#### Scenario: 字幕版型異常集的 pending 於定版時清除

- **WHEN** 某字幕版型異常集登記時為 pending，整批定版成功
- **THEN** 其 pending 被清除，且它出現在 store 版的另表中

### Requirement: store 只在整批完成時定版

清除 pending 標記並定版進度表的流程 SHALL 先檢查 inventory 內每一個 pending
集數是否已校讀完成；字幕版型異常集 SHALL 視為已完成，SHALL NOT 對其要求
時間軸、逐字稿或 SRT。只要有任何一集未完成，該流程 SHALL 以非零狀態結束
並指名那些集數，SHALL NOT 寫入任何檔案。

#### Scenario: 有集數未完成時整個中止

- **WHEN** inventory 內有 pending 集數的校讀尚未完成
- **THEN** 流程以非零狀態結束並列出那些集數，store 內容一個 byte 都沒動

#### Scenario: 整批完成後 store 自洽

- **WHEN** 全部 pending 集數皆已完成，流程成功寫入
- **THEN** inventory 內不再有 pending 標記，且隨即執行重建驗證會通過

#### Scenario: 字幕版型異常集不擋定版

- **WHEN** inventory 內有字幕版型異常集，其 `1-ocr/` 底下沒有任何檔案，其餘
  集數皆完成
- **THEN** 定版成功，該集不被列為未完成

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
  pending 集數不列入定版表——SHALL 沿用既有進度表要求的語意；
- 字幕版型異常集 SHALL NOT 列入本表（見「aiyalaeho 字幕版型異常集另表」）。

#### Scenario: 九欄與成果檔名

- **WHEN** 檢視定版的 `aiyalaeho/smkul.csv`
- **THEN** 欄位恰為上列 9 欄；每列成果檔名等於該集 `srt_name`

#### Scenario: 影片長度由時間軸推導

- **WHEN** 任何時點重算進度表
- **THEN** 每列影片長度取自該集 `1-cues/` 時間軸，重算結果逐 byte 相同

#### Scenario: 字幕版型異常集不在本表

- **WHEN** 檢視定版的 `aiyalaeho/smkul.csv`
- **THEN** 沒有任何一列對應 inventory 內理由非空的集數；本表列數加另表
  列數等於 inventory 內非 pending 的條目數

## ADDED Requirements

### Requirement: aiyalaeho 字幕版型異常集另表

`aiyalaeho/smkul-字幕版型異常.csv` SHALL 列出全部非 pending 的字幕版型異常集，
欄位為 `smkul.csv` 的 9 欄原樣、同順序，再加第 10 欄「理由」，值 SHALL 為
inventory 所記的理由（`無字幕`、`僅華語字幕`、`版型不符：…`、`人工判定：…`
之一），SHALL NOT 為空。其中：

- 成果檔名 SHALL 為該集的 `srt_name`，作為鍵，不表示存在對應檔案；
- 影片長度 SHALL 取自 inventory 所記、由工具寫入的時長，SHALL NOT 手填；
- 編碼、換行與寫法 SHALL 與 `smkul.csv` 相同（Excel 可讀）；
- 定版由整批把關通過的流程寫入、工作區另有可隨時刷新的快取版本（含
  pending 者）、pending 集數不列入定版表——語意同 `smkul.csv`；
- 本表 SHALL 可僅由 inventory 逐 byte 重建。

#### Scenario: 十欄與理由

- **WHEN** 檢視定版的 `aiyalaeho/smkul-字幕版型異常.csv`
- **THEN** 前 9 欄與 `smkul.csv` 同名同序，第 10 欄為理由，每列理由非空且
  等於 inventory 該筆的理由

#### Scenario: 影片長度來自 inventory

- **WHEN** 任何時點重算另表
- **THEN** 每列影片長度取自 inventory 該筆所記的時長，重算結果逐 byte 相同，
  過程不讀影片

#### Scenario: 兩張表互斥且合計完整

- **WHEN** 同時檢視定版的 `smkul.csv` 與 `smkul-字幕版型異常.csv`
- **THEN** 沒有任何 `srt_name` 同時出現在兩表；兩表列數之和等於 inventory
  內非 pending 的條目數

## REMOVED Requirements

### Requirement: 0-cue 集數照交付且不擋定版

**Reason**：這條在正式流程裡走不到——校讀完成的紀錄只在匯入逐字稿時才會
寫出，切出 0 條 cue 的集數沒有逐字稿可匯入，永遠沒有那份紀錄，校讀完成判準
不會成立；既有測試是靠 fixture 直接寫檔才通過。而且實務上無字幕集並不會
切出 0 條 cue（攝影棚亮景讓帶偵測一直觸發，切出數百條雜訊 cue）。就算走得
通，進度表也會多出成果檔名指向空 SRT 的列，看表的人分不出「畫面本來沒字幕」
與「讀失敗」。

**Migration**：無字幕集與其他走不了雙列雙語流程的集數改依 aiyalaeho-sourcing
「有影片就做」分流，附理由列入「aiyalaeho 字幕版型異常集另表」，不切 cue、
不交付、不擋定版。校讀完成判準「cue 編號集合被校讀集合涵蓋」本身不變（空
集合成立仍是它的自然結果），只是不再有任何交付路徑依賴這一點。
