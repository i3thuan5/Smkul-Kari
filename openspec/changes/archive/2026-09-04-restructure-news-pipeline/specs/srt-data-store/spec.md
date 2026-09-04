# srt-data-store Delta

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
    └── 2-asr/                       語音側：族語語音辨識
        └── （內部階段目錄的契約見 asr-bilingual-srt）
```

同一份資料 SHALL 只有一個路徑；同一產物的不同狀態 SHALL 分開存放於
不同目錄，SHALL NOT 在同一路徑覆蓋。每個技術目錄 SHALL 有自己的
README，說明其檔案架構、產生流程與各階段輸出入對應。

已廢止路線的歷史產物（文稿供字索引、C-pass 普查逐字稿、文稿 vs 視覺
比對報告、align 延伸試點產物與翻譯快取）SHALL NOT 存在於 store——
其結論以文字記於對應 README，檔案本體只存在於 git 歷史。

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
  `4-srt-ai`、`5-align`、`6-srt-complete`、`mt-cache`
- **THEN** 找不到任何目錄或檔案；廢止結論記於對應 README

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
與 `news/inventory.json`）SHALL 足以在不存取原始影片、不呼叫任何模型
的情況下，重建出與 `Kari-SRT/news/1-ocr/3-srt/` 內容逐 byte 相同的
**全部已交付 SRT** 與 `news/smkul.csv`。集數隨批次成長，不固定。

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
用哪個模型辨識。該欄 SHALL 僅由 store 內 `news/2-asr/3-srt-raw/`
是否已有該集的檔推導：有就是辨識器名稱、無就留白，SHALL NOT 手填
——任何時點重算皆得相同內容，逐 byte 重建保證不因增欄而破壞。
`3-srt-raw/` 之前的中間檔（`1-words/`、`2-entries/`）SHALL NOT 使該
欄有值。逐集產出流程（影像側與語音側皆同）SHALL NOT 直接寫入 store
內的 `smkul.csv`；它 SHALL 把進度表寫進工作區作為可隨時刷新的快取，
且該快取版本 SHALL 併同列出 pending 集數與其進度，供人查看批次做到
哪。store 內那一份 SHALL 由整批把關通過的定版流程寫入。

理由：mid-batch 的「卡在哪一步」只存在於工作目錄，而重建流程沒有
工作目錄，重建不出那些狀態字串。把它留在快取版本，store 那份就只含
可重建的內容——語音側欄改用「檔案存在與否」推導，同樣只依賴 store。
欄位記模型而非版本階段：交付只有一版，讀表的人要知道的是這條族語
文字是哪個辨識器產的，中間階段對他無從據以行動。

`smkul.csv` SHALL 併記**成果檔名**（該集的 `srt_name`），欄名與
《開會了》語料的進度表一致。它是每一份交付物的定位鍵，讀表的人
拿它就能在任一階段目錄下找到該集的檔，不必另查對應表，也是同一天
多集之間唯一的分辨依據——`smkul.csv` SHALL NOT 另設播出時段欄，
時段已在成果檔名之內。

`smkul.csv` SHALL 併記**時間軸狀態**（欄名 `cues`），說明該集交付的
時間軸是粗切的還是已精修的。該欄 SHALL 僅由 store 內
`news/1-ocr/1-cues/<年-月>/<srt_name>.json` 推導：檔內記為已精修就
說已精修、未精修就說粗切、檔不存在就留白，SHALL NOT 手填。

`smkul.csv` SHALL NOT 再有**文稿位置**欄。文稿路線已裁定廢止（文稿
不作為文字來源），該欄對讀表的人不再指向任何可據以行動的東西；
inventory 內由節目目錄帶進來的同名欄位不受此條約束。

#### Scenario: 批次進行中仍可查進度

- **WHEN** 一批集數尚未全部完成，執行逐集組裝流程
- **THEN** 工作區內的進度表更新並列出含 pending 在內的全部集數與各自狀態，
  store 內的 `smkul.csv` 不變，重建驗證仍然通過

#### Scenario: 定版後的進度表可逐 byte 重建

- **WHEN** 整批完成並定版後執行重建驗證
- **THEN** 重建出的 `smkul.csv` 與 store 內已 commit 的版本逐 byte 相同

#### Scenario: 語音辨識模型欄由 store 推導

- **WHEN** 某集 `2-asr/3-srt-raw/` 已有檔，重算進度表
- **THEN** 該集語音側欄顯示辨識器名稱，且重建流程僅讀 store 即
  推導出逐 byte 相同的欄值

#### Scenario: 只做到中間階段的集數留白

- **WHEN** 某集只有 `2-asr/1-words/`、`2-asr/2-entries/`，`3-srt-raw/`
  尚無，重算進度表
- **THEN** 該集語音側欄為空字串

#### Scenario: 成果檔名即定位鍵

- **WHEN** 讀表的人拿某一列的成果檔名去找該集的檔
- **THEN** 各階段目錄下同名的檔都以該字串定位得到，無須另查對應表

#### Scenario: 同一天多集靠成果檔名分辨

- **WHEN** 同一個播出日期有兩集以上（午間／晚間／晨間），檢視進度表
- **THEN** 那幾列以成果檔名分辨得出來，表內沒有播出時段欄

#### Scenario: 時間軸狀態由 store 推導

- **WHEN** 某集的 `1-cues/` 時間軸記為已精修，重算進度表
- **THEN** `cues` 欄顯示已精修；該欄僅讀 store 即重算得出逐 byte
  相同的值

#### Scenario: 只有粗切時間軸的集數照實顯示

- **WHEN** 某集交付的時間軸未經精修
- **THEN** `cues` 欄顯示粗切，SHALL NOT 顯示成已精修或留白

#### Scenario: 文稿位置欄已移除

- **WHEN** 檢視 `news/smkul.csv` 的欄位
- **THEN** 沒有文稿位置欄；重建驗證仍然通過

## ADDED Requirements

### Requirement: 只有精修過的時間軸才進 store

定版流程 SHALL 只把**已精修**的時間軸寫入 `news/1-ocr/1-cues/`。某集
的工作目錄只有粗切時間軸（0.2 秒格點、尚未經 25fps 邊界精修）時，
該集 SHALL NOT 入 store；流程 SHALL 指名該集並以非零狀態結束，
SHALL NOT 靜默略過該集的時間軸而讓其餘檔案照樣入庫。

工作目錄完全沒有時間軸時亦同 SHALL 指名中止——「找不到時間軸」與
「時間軸還沒精修」都是不得交付的狀態，兩者 SHALL 各自講清楚是哪
一種。

理由：交付 SRT 的每一個時間戳都由這份時間軸推導，而粗切與精修的
精度差一個數量級（0.2 秒 vs 0.05 秒）。兩種精度混在同一個目錄裡，
從檔案本身看不出某一集是哪一種，下游也沒有辦法分別對待。把關口設
在入庫這一步，`1-cues/` 就有一個可以直接宣告的性質：**裡面每一份都
是精修過的**。

#### Scenario: 只有粗切時間軸的集數擋在門外

- **WHEN** 某集的工作目錄只有粗切時間軸，執行定版流程
- **THEN** 流程指名該集、說明它尚未精修，並以非零狀態結束；
  該集的時間軸沒有進入 store

#### Scenario: 沒有時間軸與沒有精修分開講

- **WHEN** 某集的工作目錄完全沒有時間軸
- **THEN** 流程指名該集並說明是「找不到時間軸」，與「尚未精修」
  是不同的訊息

#### Scenario: 精修過的照常入庫

- **WHEN** 某集的工作目錄有精修過的時間軸
- **THEN** 該份時間軸寫入 `news/1-ocr/1-cues/<年-月>/<srt_name>.json`，
  定版照常完成

#### Scenario: store 內每一份時間軸都是精修過的

- **WHEN** 檢視 `news/1-ocr/1-cues/` 內任一份時間軸
- **THEN** 它記錄自己已經精修

### Requirement: 兩側交付都在時，時間軸必須逐條相同

離線重建驗證 SHALL 一併檢查語音側交付與影像側交付的同軸性：某集
**兩側的 SRT 都存在**時，`news/2-asr/3-srt-raw/` 與影像側交付 SRT 的
(index, start/end 時間戳) 序列 SHALL 逐條完全相同；不同 SHALL 使驗證
以非零狀態結束、指名該集與第一個相異的條目，並 SHALL 修正到相同為止
——語音側可由條目檔重投影＋重新 render，不需重新辨識。

語音側尚未產出**不是錯誤**：影像側交付 SRT 存在而 `3-srt-raw/` 沒有
該集的檔時，驗證 SHALL 照常通過，SHALL NOT 輸出警告。語音側是獨立
的一條線，它做到哪由 `smkul.csv` 的「語音辨識模型」欄照實反映，不是
影像側交付的前提。

#### Scenario: 兩側都在但不同軸即失敗

- **WHEN** 某非 pending 集數兩側 SRT 都存在，但 (index, 時間戳) 序列
  不同
- **THEN** 驗證以非零狀態結束並指名該集與第一個相異的條目

#### Scenario: 只有影像側交付照樣通過

- **WHEN** 某非 pending 集數有影像側交付 SRT，`3-srt-raw/` 無該集的檔
- **THEN** 驗證通過，且不輸出任何與該集語音側有關的警告

#### Scenario: 兩側都在且同軸則通過

- **WHEN** 每一個兩側都有交付的集數，其序列皆逐條相同
- **THEN** 驗證通過
