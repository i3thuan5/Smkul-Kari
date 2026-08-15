# srt-data-store（delta）

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
    │   ├── 2-from_rtf/<srt_name>.json   哪些 cue 曾由文稿供字（歷史索引）
    │   ├── 3-vision/<srt_name>/*.tsv    第一輪視覺逐字稿
    │   ├── 4-vision-rtf/<srt_name>/*.tsv C-pass 普查逐字稿
    │   ├── 5-report/rtf-vs-vision.md|.json 文稿 vs 視覺比對報告（歷史證據）
    │   └── 6-srt/<srt_name>.srt         交付字幕（＋<srt_name>.qc.json）
    └── 2-asr/                       語音側：語音辨識＋機器翻譯
        └── （內部階段目錄的契約見 asr-bilingual-srt）
```

同一份資料 SHALL 只有一個路徑；同一產物的不同狀態（如審查版與
正式版）SHALL 分開存放於不同目錄，SHALL NOT 在同一路徑覆蓋。
每個技術目錄 SHALL 有自己的 README，說明其檔案架構、產生流程與
各階段輸出入對應。

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

### Requirement: 命名鍵統一為 srt_name

Kari-SRT 內每集資料的目錄與檔名 SHALL 一律使用 `srt_name`
（`<播出日期YYYYMMDD>_<集數三位>_<時段>_<族語英>_<族語中>`，例
`20210201_032_午間_Atayal_泰雅`）。內部 work dir 的 slug、早期的簡寫
（`032午_泰雅`）與攤平檔名（`rukai_043_b01-03.tsv`）SHALL NOT 出現在
Kari-SRT 內。

#### Scenario: 一個名字找齊一集的所有資料

- **WHEN** 已知某集的 `srt_name`
- **THEN** `news/1-ocr/6-srt/<srt_name>.srt`、
  `news/1-ocr/1-cues/<srt_name>.json`、
  `news/1-ocr/2-from_rtf/<srt_name>.json`、
  `news/1-ocr/3-vision/<srt_name>/`、
  `news/1-ocr/4-vision-rtf/<srt_name>/`，以及 `news/2-asr/` 各階段
  目錄下的同名檔案，全部以同一字串定位，無須另查對應表

#### Scenario: 舊命名已遷移

- **WHEN** 在 Kari-SRT 內搜尋舊式命名（slug、`NNN午_族語` 簡寫、
  `*_bNN-NN.tsv` 攤平檔）
- **THEN** 找不到任何一個；早期攤平的 TSV 已改置於
  `news/1-ocr/3-vision/<srt_name>/` 之下

### Requirement: 僅靠已 commit 的資料可離線重建全部 SRT

主 repo（程式）加 Kari-SRT（`news/1-ocr/` 的 `1-cues/`＋`3-vision/`＋
`4-vision-rtf/`，與 `news/inventory.json`）SHALL 足以在不存取原始影片、
不呼叫任何模型的情況下，重建出與 `Kari-SRT/news/1-ocr/6-srt/` 內容
逐 byte 相同的**全部已交付 SRT** 與 `news/smkul.csv`。集數隨批次成長，
不固定。

#### Scenario: 工作目錄全毀後重建

- **WHEN** `kithann/out/` 被整個刪除，僅存主 repo 與 Kari-SRT，
  執行重建流程
- **THEN** 產出的每一個 SRT 與 Kari-SRT 內已 commit 的版本逐 byte 相同，
  過程中不讀取任何 `.mxf`、不發出任何模型呼叫

#### Scenario: 缺件時明確失敗

- **WHEN** 重建流程執行時某集缺少 `news/1-ocr/1-cues/<srt_name>.json`
  或對應 TSV
- **THEN** 該流程以非零狀態結束並指名缺少的檔案，SHALL NOT 產出
  不完整的 SRT 冒充完整交付

### Requirement: 進度表由定版流程寫入，不由逐集組裝流程寫入

`smkul.csv` SHALL 位於 `news/smkul.csv`（語料層，兩技術共用），列出
inventory 內全部非 pending 的集數，且 SHALL 併記語音側（`2-asr/`）
逐集進度。語音側進度欄 SHALL 僅由 store 內 `news/2-asr/` 各階段檔案
的存在與否推導，SHALL NOT 手填狀態字串——任何時點重算皆得相同內容，
逐 byte 重建保證不因增欄而破壞。逐集產出流程（影像側與語音側皆同）
SHALL NOT 直接寫入 store 內的 `smkul.csv`；它 SHALL 把進度表寫進
工作區作為可隨時刷新的快取，且該快取版本 SHALL 併同列出 pending
集數與其進度，供人查看批次做到哪。store 內那一份 SHALL 由整批把關
通過的定版流程寫入。

理由：mid-batch 的「卡在哪一步」只存在於工作目錄，而重建流程沒有
工作目錄，重建不出那些狀態字串。把它留在快取版本，store 那份就只含
可重建的內容——語音側欄改用「檔案存在與否」推導，同樣只依賴 store。

#### Scenario: 批次進行中仍可查進度

- **WHEN** 一批集數尚未全部完成，執行逐集組裝流程
- **THEN** 工作區內的進度表更新並列出含 pending 在內的全部集數與各自狀態，
  store 內的 `smkul.csv` 不變，重建驗證仍然通過

#### Scenario: 定版後的進度表可逐 byte 重建

- **WHEN** 整批完成並定版後執行重建驗證
- **THEN** 重建出的 `smkul.csv` 與 store 內已 commit 的版本逐 byte 相同

#### Scenario: 語音側進度欄由 store 推導

- **WHEN** 某集 `2-asr/3-srt-raw/` 已有檔而 `2-asr/5-srt-complete/`
  尚無，重算進度表
- **THEN** 該集語音側欄顯示對應的階段值，且重建流程僅讀 store 即
  推導出逐 byte 相同的欄值
