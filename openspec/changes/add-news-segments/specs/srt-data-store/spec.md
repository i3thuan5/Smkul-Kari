## MODIFIED Requirements

### Requirement: Kari-SRT 為成果與過程資料的唯一正本

字幕 pipeline 的交付物與不可重生的過程資料 SHALL 存放於 `Kari-SRT/`
submodule，按「**語料 → 技術 → 編號階段**」分層，結構如下；主 repo
SHALL 只含程式、測試與文件，`kithann/` SHALL 維持整個 gitignore
（純工作區）。

```
Kari-SRT/
├── README.md                        總覽：分層說明與資料流
└── news/                            語料：族語新聞（其他語料另開頂層目錄）
    ├── README.md                    news/ 總覽：各層是什麼、從哪裡做出來、誰讀它
    ├── inventory.json               影片 ↔ 節目資料對應（唯一正本，兩技術共用）
    ├── smkul.csv                    進度表（兩技術共用，見進度表 requirement）
    ├── 排除影片.csv                 查過確定不收的原始影片（見 episode-catalogue）
    ├── 1-ocr/                       影像側：燒印字幕抽取（編號＝產生流程）
    │   ├── README.md                    OCR 檔案架構與流程說明
    │   ├── 片頭辨識.csv                 一集一列：片頭語別牌、主播、與目錄相符
    │   ├── 0-segments/<srt_name>.csv    每集段落表（見 news-segments）
    │   ├── 1-cues/<srt_name>.json       每集時間軸（記每條 cue 用哪個區域切）
    │   ├── 2-vision/<srt_name>/*.tsv    視覺逐字稿（文字唯一來源）
    │   └── 3-srt/<srt_name>.srt         交付字幕（＋<srt_name>.qc.json）
    ├── 主播.csv                     一位主播一列：族語別、族語名、漢名、語言別、
    │                                語言別代號、抽聽的集、語別依據
    ├── 2-asr-kaldi/                 語音側（kaldi）：族語語音辨識與對應品質
    │   ├── README.md
    │   ├── 1-words/ 2-srt-raw/ 3-srt-ai/ 4-srt-quality/   逐集階段
    │   └── mt-cache/ quality-cache/                       跨集快取
    │   （階段內容的契約見 asr-bilingual-srt 與 parallel-corpus-quality）
    └── 2-asr-whisper/               語音側（whisper）：sapolita 族語辨識
        ├── README.md
        └── 1-srt-sapolita/
            ├── 辨識紀錄.csv          一集一列
            └── <年-月>/<成果檔名>.srt  伺服器回傳原樣
        （內容的契約見 whisper-asr-srt）
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
  語音側在 `2-asr-kaldi/` 與 `2-asr-whisper/`），`kithann/srt/` 不存在，主 repo 內亦無第二份
  副本，Kari-SRT 頂層亦無殘留的舊位置

#### Scenario: inventory 沒有第二份

- **WHEN** 在主 repo 內搜尋 inventory 資料檔
- **THEN** 找不到；所有取用點都解析到 `Kari-SRT/news/inventory.json`

#### Scenario: 工作區資料不進版本控制

- **WHEN** 檢視主 repo 的 git 追蹤狀態
- **THEN** `kithann/` 之下沒有任何被追蹤的檔案（work dir、log、
  暫存影片皆可重生，不 commit）

#### Scenario: 技術目錄各有 README

- **WHEN** 瀏覽 `news/1-ocr/`、`news/2-asr-kaldi/` 或 `news/2-asr-whisper/`
- **THEN** 各自的 README.md 說明該技術的檔案架構、產生流程與
  輸出入對應，目錄編號即產生順序

#### Scenario: 語料目錄有總覽 README

- **WHEN** 打開 `news/`
- **THEN** `news/README.md` 說明 `smkul.csv`、`主播.csv`、`排除影片.csv`
  與各技術目錄是什麼、從哪裡做出來、誰讀它

#### Scenario: 段落表與片頭辨識在影像側

- **WHEN** 找某集的段落表或片頭辨識結果
- **THEN** 段落表在 `news/1-ocr/0-segments/<年-月>/<srt_name>.csv`，
  片頭辨識在 `news/1-ocr/片頭辨識.csv` 那一列；編號 0 表示段落表
  比時間軸先產出

#### Scenario: 歷史目錄已清除

- **WHEN** 在 Kari-SRT 內搜尋 `2-from_rtf`、`4-vision-rtf`、`5-report`、
  `2-entries`、`3-srt-raw`、`4-srt-ai`、`5-align`、`6-srt-complete`
- **THEN** 找不到任何目錄或檔案；廢止結論記於對應 README

#### Scenario: 舊語音側目錄名不再存在

- **WHEN** 在 Kari-SRT 與 `kithann/out/news/` 內搜尋名為 `2-asr` 的目錄
- **THEN** 找不到；kaldi 那條的資料都在 `2-asr-kaldi/`，whisper 那條在
  `2-asr-whisper/`

#### Scenario: 跨集快取在 store

- **WHEN** 檢視 `news/2-asr-kaldi/`
- **THEN** `mt-cache/` 與 `quality-cache/` 存在，各為每引擎／每裁判
  一個 JSONL 檔

### Requirement: 節目目錄的不變量

`news/smkul.csv`、`aiyalaeho/smkul.csv`、`aiyalaeho/smkul-字幕版型異常.csv`
是輸入而非產出，SHALL NOT 以逐 byte 重算比對。離線重建驗證 SHALL 改以
下列不變量把關，任一條不成立時指名該列並以非零狀態結束：

- `成果檔名` 合乎命名規格，同表內唯一，且與同列識別欄互推得出來；
- `語言別代號` 在隨 repo 走的對照表之內；
- `族語別(中)` 與 `族語別(英)` 一對一，對得上對照表；
- 每一列的素材位置欄非空；
- 每一列的素材位置不在 `排除影片.csv`（有這份表的語料）；
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

#### Scenario: 排除過的檔又被加回來

- **WHEN** `smkul.csv` 某列的素材位置是 `排除影片.csv` 列過的重複檔
- **THEN** 驗證以非零狀態結束，指名該列與排除原因

#### Scenario: 段落表也是階段目錄

- **WHEN** `1-ocr/0-segments/` 有一個段落表，其成果檔名在節目目錄中找不到
- **THEN** 驗證以非零狀態結束並指名該檔

#### Scenario: 還沒做的集數不算錯

- **WHEN** 節目目錄有 969 列，各階段目錄合計只有 75 集
- **THEN** 驗證通過
