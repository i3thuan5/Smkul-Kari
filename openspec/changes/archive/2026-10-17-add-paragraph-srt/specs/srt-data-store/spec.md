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
    ├── inventory.json               影片 ↔ 節目資料對應（唯一正本，兩技術共用）
    ├── smkul.csv                    進度表（兩技術共用，見進度表 requirement）
    ├── 1-ocr/                       影像側：燒印字幕抽取（編號＝產生流程）
    │   ├── README.md                    OCR 檔案架構與流程說明
    │   ├── 1-cues/<srt_name>.json       每集時間軸
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
        ├── 1-srt-sapolita/
        │   ├── 辨識紀錄.csv          一集一列
        │   └── <年-月>/<成果檔名>.srt  伺服器回傳原樣
        ├── 2-csv-analysis/
        │   ├── README.md
        │   ├── 校正基準.csv          各族辭典命中率基準（凍結）
        │   └── <年-月>/<成果檔名>.csv  族華段落配對，一組一列，含不採用與原因
        └── 3-srt-paragraph/
            ├── README.md
            └── <年-月>/<成果檔名>.srt  高、中信心的組，族語華語兩行
        （1-srt-sapolita 的契約見 whisper-asr-srt；2、3 見 whisper-parallel-corpus）
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

#### Scenario: whisper 那條的舊目錄名不再存在

- **WHEN** 在 Kari-SRT 內搜尋名為 `2-平行語料` 的目錄
- **THEN** 找不到；配對的 CSV 在 `2-asr-whisper/2-csv-analysis/`，雙語字幕在 `2-asr-whisper/3-srt-paragraph/`

### Requirement: 下游階段的集數必為上游的子集

離線重建驗證 SHALL 檢查各階段之間的包含關係：`3-srt/` 的成果檔名集合 SHALL 是 `2-vision/` 的子集，`2-vision/` SHALL 是 `1-cues/` 的子集。`2-asr-whisper/2-csv-analysis/` 的成果檔名集合 SHALL 同時是 `1-ocr/3-srt/` 與 `2-asr-whisper/1-srt-sapolita/` 的子集；`2-asr-whisper/3-srt-paragraph/` 的成果檔名集合 SHALL 是 `2-csv-analysis/` 的子集。

下游有而上游沒有的集數 SHALL 使驗證以非零狀態結束，並指名是哪一集在哪一層缺——那份交付物重建不出來。上游有而下游沒有 SHALL 視為正常，那只表示還沒做到那一步。

#### Scenario: 交付 SRT 沒有對應的時間軸

- **WHEN** `3-srt/` 有某集的 SRT，`1-cues/` 沒有該集的時間軸
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層

#### Scenario: 上游多出來的集數不算錯

- **WHEN** `1-cues/` 有 75 集，`3-srt/` 只有 40 集
- **THEN** 驗證通過

#### Scenario: 平行語料沒有對應的辨識結果

- **WHEN** `2-csv-analysis/` 有某集的 CSV，`1-srt-sapolita/` 沒有該集的 SRT
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層

#### Scenario: 雙語字幕沒有對應的配對 CSV

- **WHEN** `3-srt-paragraph/` 有某集的 SRT，`2-csv-analysis/` 沒有該集的 CSV
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層

### Requirement: 平行語料層可離線重建

`Kari-SRT/news/2-asr-whisper/2-csv-analysis/` 與 `3-srt-paragraph/` 裡每一集的檔，SHALL 能從下列輸入逐 byte 重建：主 repo（程式）、Kari-SRT（該集的 `1-ocr/1-cues/`、`1-ocr/2-vision/`、`2-asr-whisper/1-srt-sapolita/`（含 `辨識紀錄.csv` 的音長秒）、`news/smkul.csv`、`2-csv-analysis/校正基準.csv`）、`kithann/族語辭典/`。重建 SHALL NOT 呼叫任何模型。

辭典是這條規則唯一的外部來源：`kithann/族語辭典/` 缺檔時，重建 SHALL 從 SFTP 取得後再驗；SFTP 也取不到時，SHALL 指名中止，SHALL NOT 略過這一層而宣告通過。

`scripts.news.rebuild --verify` SHALL 涵蓋這兩層。這兩層沒有檔的集數 SHALL NOT 算錯，那只是還沒做到。

#### Scenario: 有人手改了入庫的 CSV

- **WHEN** 某集 `2-csv-analysis/` 的 CSV 被人改了一格
- **THEN** 重建驗證以非零狀態結束並指名該集

#### Scenario: 換機器沒有辭典

- **WHEN** `kithann/族語辭典/` 不存在，執行重建驗證
- **THEN** 先從 SFTP 取得辭典，再照常逐 byte 比對

#### Scenario: 辭典取不到

- **WHEN** `kithann/族語辭典/` 不存在，SFTP 也連不上
- **THEN** 驗證以非零狀態結束，說明是辭典取不到，而不是宣告通過

#### Scenario: 有人手改了入庫的雙語字幕

- **WHEN** 某集 `3-srt-paragraph/` 的 SRT 被人改了一個字
- **THEN** 重建驗證以非零狀態結束並指名該集

#### Scenario: 舊目錄還在就不驗

- **WHEN** Kari-SRT 裡同時有 `2-asr-whisper/2-平行語料/` 與 `2-csv-analysis/`
- **THEN** 重建驗證以非零狀態結束，指名舊目錄要移除，不宣告通過

## ADDED Requirements

### Requirement: 片頭辨識改語別時清掉語音側產物

片頭辨識查出節目目錄的語別標錯、改了那一集的語別時，語音側用錯的語言做出來的檔 SHALL 一併刪除等重跑：`2-asr-whisper/1-srt-sapolita/`、`2-asr-whisper/2-csv-analysis/`、`2-asr-whisper/3-srt-paragraph/`，以及 kaldi 那條的各層。跟語言無關的影像側檔（`1-ocr/` 各層）SHALL 只改名、內容不動。

#### Scenario: 改語別後雙語字幕也刪掉

- **WHEN** 20210116_016 晚間從排灣改成卑南，改之前 `3-srt-paragraph/` 已有排灣那一集的 SRT
- **THEN** 那份 SRT 被刪除，不會以卑南的檔名留下排灣語辨識做出來的字幕
