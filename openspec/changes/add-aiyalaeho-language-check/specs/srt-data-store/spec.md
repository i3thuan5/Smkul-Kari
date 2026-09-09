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

### Requirement: aiyalaeho 僅靠已 commit 的資料可離線重建

主 repo（程式）加 Kari-SRT（`aiyalaeho/1-ocr/` 的 `1-cues/`＋`2-vision/`＋
`4-語言檢查/詞庫/`，與 `aiyalaeho/inventory.json`）SHALL 足以在不存取影片、
不存取辭典原始檔、不呼叫任何模型的情況下，重建出與 `aiyalaeho/1-ocr/3-srt/`
逐 byte 相同的全部已交付雙列 SRT、`aiyalaeho/smkul.csv`、
`aiyalaeho/smkul-字幕版型異常.csv`，以及 `aiyalaeho/1-ocr/4-語言檢查/` 的
`逐條語言標記.csv` 與 `逐集語言分布.csv`。缺件 SHALL 指名
失敗；pending 集數 SHALL 跳過；字幕版型異常集 SHALL NOT 被要求任何 `1-ocr/`
輸入，其另表列僅由 inventory 推導——語意同 news 的既有要求，範圍及於本語料。

兩張 CSV 的重建 SHALL 以重建出來的交付 SRT 為輸入，而非 store 內既有的
交付 SRT——上游換版而下游未重產時，這樣才驗得出來。

#### Scenario: 工作目錄全毀後重建

- **WHEN** 工作區被整個刪除，僅存主 repo 與 Kari-SRT，執行本語料的重建驗證
- **THEN** 每個交付 SRT、`smkul.csv`、`smkul-字幕版型異常.csv` 與兩張語言
  檢查 CSV 逐 byte 相同，過程不讀影片、不讀辭典原始檔、不呼叫模型

#### Scenario: 缺件時明確失敗

- **WHEN** 某已交付集數缺 `1-cues/<srt_name>.json` 或 TSV
- **THEN** 重建以非零狀態結束並指名缺少的檔案

#### Scenario: 字幕版型異常集不算缺件

- **WHEN** 某字幕版型異常集在 `1-ocr/` 底下沒有任何檔案，執行重建驗證
- **THEN** 驗證不因它報缺件；其另表列由 inventory 重建且逐 byte 相同

#### Scenario: 另表被改動時報差異

- **WHEN** store 內的 `smkul-字幕版型異常.csv` 與由 inventory 重算的內容不同
- **THEN** 重建驗證以非零狀態結束並指名該表

#### Scenario: 詞庫缺件時明確失敗

- **WHEN** `4-語言檢查/詞庫/` 缺任一族語別的詞庫檔，執行重建驗證
- **THEN** 驗證以非零狀態結束並指名缺少的族語別，SHALL NOT 靜默跳過該族的集數
