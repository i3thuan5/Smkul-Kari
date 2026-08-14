## MODIFIED Requirements

### Requirement: Kari-SRT 為成果與過程資料的唯一正本

字幕 pipeline 的交付物與不可重生的過程資料 SHALL 存放於 `Kari-SRT/`
submodule，結構如下；主 repo SHALL 只含程式、測試與文件，`kithann/`
SHALL 維持整個 gitignore（純工作區）。

```
Kari-SRT/
├── inventory.json               影片 ↔ 節目資料對應（唯一正本）
├── srt/<srt_name>.srt           交付字幕（全部已交付集數）
├── srt/smkul.csv                進度表
├── report/rtf-vs-vision.md|.json 文稿 vs 視覺比對報告（單一版本，歷史證據）
├── cues/<srt_name>.json         每集時間軸
├── from_rtf/<srt_name>.json     哪些 cue 曾由文稿供字（歷史索引，不再新增）
├── vision/<srt_name>/*.tsv      第一輪視覺逐字稿
└── vision-rtf/<srt_name>/*.tsv  C-pass 普查逐字稿
```

`inventory.json` 是由節目目錄衍生的資料，SHALL 只存在於 store。主 repo 內
SHALL NOT 存在第二份 inventory；所有讀寫 inventory 的程式與腳本 SHALL 透過
單一路徑常數指向 store 那份。語料知識性質的設定檔（例如版型 preset）不受此
限，那是程式的一部分而非衍生資料。

#### Scenario: 交付物只有一個正本

- **WHEN** 尋找任何一集的交付 SRT、逐字稿或節目資料對應
- **THEN** 正本位於 `Kari-SRT/` 對應位置，`kithann/srt/` 不存在，
  主 repo 內亦無第二份副本

#### Scenario: inventory 沒有第二份

- **WHEN** 在主 repo 內搜尋 inventory 資料檔
- **THEN** 找不到；所有取用點都解析到 `Kari-SRT/inventory.json`

#### Scenario: 工作區資料不進版本控制

- **WHEN** 檢視主 repo 的 git 追蹤狀態
- **THEN** `kithann/` 之下沒有任何被追蹤的檔案（work dir、log、
  暫存影片皆可重生，不 commit）

### Requirement: 僅靠已 commit 的資料可離線重建全部 SRT

主 repo（程式）加 Kari-SRT（`cues/` + `vision/` + `vision-rtf/` +
`inventory.json`）SHALL 足以在不存取原始影片、不呼叫任何模型的情況下，
重建出與 `Kari-SRT/srt/` 內容逐 byte 相同的**全部已交付 SRT** 與 `smkul.csv`。
集數隨批次成長，不固定。

#### Scenario: 工作目錄全毀後重建

- **WHEN** `kithann/out/` 被整個刪除，僅存主 repo 與 Kari-SRT，
  執行重建流程
- **THEN** 產出的每一個 SRT 與 Kari-SRT 內已 commit 的版本逐 byte 相同，
  過程中不讀取任何 `.mxf`、不發出任何模型呼叫

#### Scenario: 缺件時明確失敗

- **WHEN** 重建流程執行時某集缺少 `cues/<srt_name>.json` 或對應 TSV
- **THEN** 該流程以非零狀態結束並指名缺少的檔案，SHALL NOT 產出
  不完整的 SRT 冒充完整交付

## ADDED Requirements

### Requirement: 批次進行中的集數以 pending 標記且不參與重建驗證

尚未完成的集數 SHALL 在 inventory 內標記為 pending。重建驗證與進度表列的
產生 SHALL 跳過 pending 集數：不要求其交付品與輸入存在，也不為其產生進度表列。

pending 與既有兩個標記語意不重疊，SHALL 分別使用：來源不完整而永不交付者、
已交付但來源短缺者、以及本批尚未完成者。

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

### Requirement: store 只在整批完成時定版

清除 pending 標記並定版進度表的流程 SHALL 先檢查 inventory 內每一個 pending
集數是否已校讀完成。只要有任何一集未完成，該流程 SHALL 以非零狀態結束並指名
那些集數，SHALL NOT 寫入任何檔案。

#### Scenario: 有集數未完成時整個中止

- **WHEN** inventory 內有 pending 集數的校讀尚未完成
- **THEN** 流程以非零狀態結束並列出那些集數，store 內容一個 byte 都沒動

#### Scenario: 整批完成後 store 自洽

- **WHEN** 全部 pending 集數皆已完成，流程成功寫入
- **THEN** inventory 內不再有 pending 標記，且隨即執行重建驗證會通過

### Requirement: 進度表由定版流程寫入，不由逐集組裝流程寫入

`smkul.csv` SHALL 列出 inventory 內全部非 pending 的集數。逐集產出 SRT 的
流程 SHALL NOT 直接寫入 store 內的 `smkul.csv`；它 SHALL 把進度表寫進工作區
作為可隨時刷新的快取，且該快取版本 SHALL 併同列出 pending 集數與其進度，
供人查看批次做到哪。store 內那一份 SHALL 由整批把關通過的定版流程寫入。

理由：mid-batch 的「卡在哪一步」只存在於工作目錄，而重建流程沒有工作目錄，
重建不出那些狀態字串。把它留在快取版本，store 那份就只含可重建的內容。

#### Scenario: 批次進行中仍可查進度

- **WHEN** 一批集數尚未全部完成，執行逐集組裝流程
- **THEN** 工作區內的進度表更新並列出含 pending 在內的全部集數與各自狀態，
  store 內的 `smkul.csv` 不變，重建驗證仍然通過

#### Scenario: 定版後的進度表可逐 byte 重建

- **WHEN** 整批完成並定版後執行重建驗證
- **THEN** 重建出的 `smkul.csv` 與 store 內已 commit 的版本逐 byte 相同

### Requirement: 校讀完成的判準比對編號集合

判斷一集校讀是否完成 SHALL 比對校讀紀錄的 cue 編號集合與該集時間軸的 cue
編號集合，兩者相等才算完成。SHALL NOT 只比對兩者的數量。

理由：數量相等不蘊含集合相等。若校讀紀錄殘留了已不存在的舊編號，數量可以
湊足而實際仍有 cue 未讀，該集會被誤判為完成並定版進 store。

#### Scenario: 數量湊足但編號不符時判為未完成

- **WHEN** 某集的校讀紀錄筆數不少於 cue 數，但其中含有不屬於該集時間軸的編號
- **THEN** 該集判為校讀未完成，不得清除其 pending 標記

### Requirement: 整份重寫 inventory 的流程須有明確防護

任何會整份重寫 inventory 的流程 SHALL NOT 在預設情況下覆蓋既有條目。它
SHALL 以合併方式運作，或要求呼叫端明示同意才進行整份重寫。

理由：inventory 遷入 store 之後即為正本。掃描本機資料夾產生 inventory 的
流程若整份重寫，會刪掉所有由其他來源登記的集數——而那個資料夾掛載點已不存在
於當前環境。

#### Scenario: 掃描流程不會靜默刪除既有集數

- **WHEN** 執行掃描本機資料夾的 inventory 產生流程，而 inventory 內已有
  其他來源登記的集數
- **THEN** 那些集數不被移除；若流程無法以合併方式進行，則中止並說明需要
  何種明示同意
