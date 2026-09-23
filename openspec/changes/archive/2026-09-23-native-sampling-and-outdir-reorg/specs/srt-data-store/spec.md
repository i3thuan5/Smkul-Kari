## ADDED Requirements

### Requirement: 工作目錄照語料、月份、編號階段分層

工作區（`kithann/out/`）的每一集資料 SHALL 依「語料 → 月份 → 集」分層，
集內再依**編號階段**分資料夾，編號即產出順序。族語新聞的工作資料
SHALL 位於 `kithann/out/news/` 之下：

```
kithann/out/news/1-ocr/<年-月>/<slug>.work/
    1-cues/        粗切時間軸
    2-strips/      逐 cue 圖條
    3-refined/     精修後時間軸
    4-sheets/      Claude Vision 輸入組合圖與其索引
    5-transcripts/ 校讀結果
kithann/out/news/2-asr/<年-月>/      語音側工作資料
kithann/out/news/logs/<年-月>/       逐集逐步驟的執行紀錄
kithann/out/news/mkv/<年-月>/        封存用整集影片
kithann/out/news/stage*/<年-月>/     暫存影片與量測用中間檔
```

work dir 以 slug（`<年度>_<集數>_<播出日期>_…`）命名，月份取 slug 內的
播出日期，不取年度欄；不以 srt_name 命名，因為交付檔名改動時不可讓
做到一半的 work dir 找不到。

同一集的檔案 SHALL NOT 平鋪在階段資料夾的上一層。資料夾名稱 SHALL
反映內容：不得以早期的來源格式（如 `mxf`）命名一個不含該格式檔案的
資料夾。

逐集的執行紀錄 SHALL 與 work dir 分開存放，SHALL NOT 放在 work dir
之內——紀錄從下載那一步就開始寫（那時 work dir 還不存在），而 work dir
在驗收後會被刪除，紀錄要留得比它久。

時間軸內記錄的圖條路徑 SHALL 與實際階段資料夾一致。

#### Scenario: 每一集都在自己的月份層底下

- **WHEN** 檢視 `kithann/out/news/1-ocr/`
- **THEN** 其下是 `<年-月>` 資料夾，work dir 在月份資料夾之內，
  SHALL NOT 直接出現在 `1-ocr/` 底下

#### Scenario: 跨年的月份各自分開

- **WHEN** 同時存在 2021 年 12 月與 2022 年 1 月的集數
- **THEN** 兩者分別落在 `2021-12/` 與 `2022-01/`

#### Scenario: 階段編號即產出順序

- **WHEN** 檢視任一 work dir
- **THEN** 資料夾依序為 `1-cues/`、`2-strips/`、`3-refined/`、
  `4-sheets/`、`5-transcripts/`，且各階段的產物只出現在自己的資料夾內

#### Scenario: 時間軸記的圖條路徑抓得到檔案

- **WHEN** 依時間軸某條 cue 記錄的圖條相對路徑，到該集 work dir 取檔
- **THEN** 檔案存在

#### Scenario: 執行紀錄不隨 work dir 消失

- **WHEN** 某集通過驗收、其 work dir 已被刪除
- **THEN** 該集的下載、切 cue、精修紀錄仍在 `news/logs/<年-月>/`
