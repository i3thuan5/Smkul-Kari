# srt-data-store 差異規格

## Purpose

定義字幕抽取成果與過程資料的存放契約：哪些資料放在 Kari-SRT submodule、
用什麼命名鍵、哪些必須進版本控制，以及「僅靠已 commit 的資料就能離線重建
全部交付 SRT」的保證。

## ADDED Requirements

### Requirement: Kari-SRT 為成果與過程資料的唯一正本

字幕 pipeline 的交付物與不可重生的過程資料 SHALL 存放於 `Kari-SRT/`
submodule，結構如下；主 repo SHALL 只含程式、測試與文件，`kithann/`
SHALL 維持整個 gitignore（純工作區）。

```
Kari-SRT/
├── inventory.json               影片 ↔ 節目資料對應
├── srt/<srt_name>.srt           交付字幕（22 集）
├── srt/smkul.csv                進度表
├── srt/rtf-vs-vision.md|.json   文稿 vs 視覺比對報告
├── cues/<srt_name>.json         每集時間軸
├── from_rtf/<srt_name>.json     哪些 cue 曾由文稿供字
├── vision/<srt_name>/*.tsv      第一輪視覺逐字稿
└── vision-rtf/<srt_name>/*.tsv  C-pass 普查逐字稿
```

#### Scenario: 交付物只有一個正本

- **WHEN** 尋找任何一集的交付 SRT 或逐字稿
- **THEN** 正本位於 `Kari-SRT/` 對應目錄，`kithann/srt/` 不存在，
  主 repo 內亦無第二份副本

#### Scenario: 工作區資料不進版本控制

- **WHEN** 檢視主 repo 的 git 追蹤狀態
- **THEN** `kithann/` 之下沒有任何被追蹤的檔案（work dir、log、
  暫存影片皆可重生，不 commit）

### Requirement: 命名鍵統一為 srt_name

Kari-SRT 內每集資料的目錄與檔名 SHALL 一律使用 `srt_name`
（`<播出日期YYYYMMDD>_<集數三位>_<時段>_<族語英>_<族語中>`，例
`20210201_032_午間_Atayal_泰雅`）。內部 work dir 的 slug、早期的簡寫
（`032午_泰雅`）與攤平檔名（`rukai_043_b01-03.tsv`）SHALL NOT 出現在
Kari-SRT 內。

#### Scenario: 一個名字找齊一集的所有資料

- **WHEN** 已知某集的 `srt_name`
- **THEN** `srt/<srt_name>.srt`、`cues/<srt_name>.json`、
  `from_rtf/<srt_name>.json`、`vision/<srt_name>/`、
  `vision-rtf/<srt_name>/` 全部以同一字串定位，無須另查對應表

#### Scenario: 舊命名已遷移

- **WHEN** 在 Kari-SRT 內搜尋舊式命名（slug、`NNN午_族語` 簡寫、
  `*_bNN-NN.tsv` 攤平檔）
- **THEN** 找不到任何一個；早期攤平的 TSV 已改置於
  `vision/<srt_name>/` 之下

### Requirement: 僅靠已 commit 的資料可離線重建全部 SRT

主 repo（程式）加 Kari-SRT（`cues/` + `vision/` + `vision-rtf/` +
`inventory.json`）SHALL 足以在不存取原始影片、不呼叫任何模型的情況下，
重建出與 `Kari-SRT/srt/` 內容逐 byte 相同的全部 22 個 SRT 與 `smkul.csv`。

#### Scenario: 工作目錄全毀後重建

- **WHEN** `kithann/out/` 被整個刪除，僅存主 repo 與 Kari-SRT，
  執行重建流程
- **THEN** 產出的 22 個 SRT 與 Kari-SRT 內已 commit 的版本逐 byte 相同，
  過程中不讀取任何 `.mxf`、不發出任何模型呼叫

#### Scenario: 缺件時明確失敗

- **WHEN** 重建流程執行時某集缺少 `cues/<srt_name>.json` 或對應 TSV
- **THEN** 該流程以非零狀態結束並指名缺少的檔案，SHALL NOT 產出
  不完整的 SRT 冒充完整交付
