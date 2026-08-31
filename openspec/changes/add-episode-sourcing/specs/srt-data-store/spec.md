## MODIFIED Requirements

### Requirement: 命名鍵統一為 srt_name

Kari-SRT 內每集資料的目錄與檔名 SHALL 一律使用 `srt_name`
（`<播出日期YYYYMMDD>_<集數三位>_<時段>_<族語英>_<族語中>`，例
`20210201_032_午間_Atayal_泰雅`）。內部 work dir 的 slug、早期的簡寫
（`032午_泰雅`）與攤平檔名（`rukai_043_b01-03.tsv`）SHALL NOT 出現在
Kari-SRT 內。

逐集資料 SHALL 存放於階段目錄下的**播出月份**一層（`<年-月>/`，例
`2021-02/`）。月份鍵 SHALL 由 `srt_name` 的播出日期推導，SHALL NOT
另存一份對應資料。跨集產物（比對報告、翻譯快取）與總表
（`inventory.json`、`smkul.csv`）SHALL 維持不分層。

#### Scenario: 一個名字找齊一集的所有資料

- **WHEN** 已知某集的 `srt_name`
- **THEN** `news/1-ocr/6-srt/<年-月>/<srt_name>.srt`、
  `news/1-ocr/1-cues/<年-月>/<srt_name>.json`、
  `news/1-ocr/2-from_rtf/<年-月>/<srt_name>.json`、
  `news/1-ocr/3-vision/<年-月>/<srt_name>/`、
  `news/1-ocr/4-vision-rtf/<年-月>/<srt_name>/`，以及 `news/2-asr/`
  各階段目錄下的同名檔案，全部以同一字串定位，無須另查對應表；月份
  一層由該字串自身推導

#### Scenario: 舊命名已遷移

- **WHEN** 在 Kari-SRT 內搜尋舊式命名（slug、`NNN午_族語` 簡寫、
  `*_bNN-NN.tsv` 攤平檔）
- **THEN** 找不到任何一個；早期攤平的 TSV 已改置於
  `news/1-ocr/3-vision/<年-月>/<srt_name>/` 之下

#### Scenario: 逐集資料依播出月份分層

- **WHEN** 檢視任一階段目錄
- **THEN** 其下第一層是播出月份目錄，逐集檔案位於月份目錄之內，沒有
  任何逐集檔案直接躺在階段目錄下

#### Scenario: 跨集產物與總表不分層

- **WHEN** 檢視比對報告目錄、翻譯快取目錄，以及 `inventory.json`、
  `smkul.csv`
- **THEN** 它們維持在原來的位置，未被加上月份一層

#### Scenario: 分層後仍可離線重建且逐 byte 相同

- **WHEN** 在新的分層路徑下執行離線重建驗證
- **THEN** 全部交付 SRT 與分層前逐 byte 相同，驗證通過

## ADDED Requirements

### Requirement: 進度表併記影片長度

`smkul.csv` SHALL 為每一集列出影片長度。該欄 SHALL 由 store 內
`news/1-ocr/1-cues/` 該集時間軸所記的長度推導，SHALL NOT 手填——任何
時點重算皆得相同內容，逐 byte 重建不因增欄而破壞。

長度只是記錄，SHALL NOT 用來判斷該集是否完整或是否交付。

#### Scenario: 長度由時間軸推導

- **WHEN** 重算進度表
- **THEN** 每一集的長度欄取自該集在 `1-cues/` 的時間軸，重建流程僅讀
  store 即推導出逐 byte 相同的欄值

#### Scenario: 尚無時間軸的集數留白

- **WHEN** 某集尚未切 cue，`1-cues/` 還沒有它的檔
- **THEN** 該集長度欄為空字串，與其他欄的留白規則一致

### Requirement: 節目目錄正本存於 store

`ilrdf-corpus.csv`（節目目錄：每一集的族語別、播出資料與影片檔案位置）
SHALL 存於 Kari-SRT，且 SHALL NOT 只存在於工作區。它跨語料（同時列出
族語新聞與族語節目），因此 SHALL 置於 store 頂層而非任一語料目錄下。

理由：它是外部給的來源資料，重生不出來——正本的正本是 SFTP 上的一份
xlsx——而每一個新月份要做哪些集、每一集叫什麼名字、配哪一支檔，全部
由它推導。放在 gitignore 的工作區，換一台機器就沒了。

它不是交付物，離線重建流程 SHALL NOT 依賴它（重建只讀
`inventory.json` 與各階段目錄）。

#### Scenario: 目錄隨資料走

- **WHEN** 在一台只 clone 主 repo 與 Kari-SRT 的機器上規劃新月份
- **THEN** 節目目錄讀得到，該月的集數與各自的來源路徑推導得出來

#### Scenario: 離線重建不依賴目錄

- **WHEN** 節目目錄不存在而執行離線重建驗證
- **THEN** 驗證照常通過——重建只用得到 `inventory.json` 與各階段目錄
