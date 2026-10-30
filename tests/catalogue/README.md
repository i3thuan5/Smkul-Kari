# tests/catalogue/：節目目錄的共同欄位與不變量

`scripts/catalogue_checks.py`（頂層，兩個語料共用）的測試。六張表都用同一組
欄位起頭，所以「前七欄是什麼、怎麼驗」要有一個地方講。

`smkul.csv` 現在是**輸入**不是產出，逐 byte 重算比對失去意義，
`rebuild --verify` 對它的把關換成這幾條不變量。

```bash
.tox/unittest/bin/python -m unittest discover -s tests/catalogue -t .
```

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| episode-catalogue | 播出時段由節目名稱推導（一對一、零例外）；節目名稱不在六個合法名稱之列時指名中止，不可推出空字串——空時段會組出一個沒人找得到的成果檔名 | `test_catalogue_checks.py` |
| episode-catalogue | 三個新名稱「看見族語（午間／晚間／晨間）」各解出對的時段；舊的三個仍解得出，因為 2024-07-31 以前的列還在用 | `test_catalogue_checks.py` |
| episode-catalogue | 半形括號 `看見族語(晚間)` 不認、指名並提示全形，不推空字串（Excel 手打最常犯、看起來幾乎一模一樣）；只寫「看見族語」不帶時段也對不到（三個時段共用同名，推不出是哪個） | `test_catalogue_checks.py` |
| episode-catalogue | 改名不可連動改成果檔名：`看見族語（晚間）` ＋ 2024-12-02 與舊名稱組出同一個 `20241202_337_晚間_Amis_阿美`——連動的話所有 SRT 變孤兒檔 | `test_catalogue_checks.py`、`test_name_catalogue.py` |
| episode-catalogue | 節目名稱要與播出日期相符，界線兩側各測：07-31 配舊名稱過、08-01 配新名稱過；08-01 配舊名稱被擋、07-31 配新名稱被擋（防 `>` 與 `>=` 寫反）；同一張表兩種名稱並存合法 | `test_catalogue_checks.py` |
| episode-catalogue | 日期對照不波及開會了（無播出日期欄）；播出日期空白或格式壞掉時不拋例外、不多報，只留成果檔名與識別欄不一致那一條 | `test_catalogue_checks.py` |
| episode-catalogue | 集數要補三碼：`2021_32_…` 和 `2021_032_…` 排起來位置不同，而且找不到檔 | `test_catalogue_checks.py` |
| episode-catalogue | 還沒切 cue 的集數也推得出成果檔名——一列一建立就有名 | `test_catalogue_checks.py` |
| episode-catalogue | 成果檔名與識別欄推出來的不一致時指名該列，不可就地改寫那一格 | `test_catalogue_checks.py` |
| episode-catalogue | 同表內成果檔名重複要指名 | `test_catalogue_checks.py` |
| episode-catalogue | 列序照成果檔名排——舊表第一列是 2021-02-01、最後一列是 2021-01-06，加一批就整檔重寫（實測四次 75/75、36/36、36/36、73/34） | `test_catalogue_checks.py` |
| episode-catalogue | 每列素材位置欄非空；純文字的句對表用 `來源文字檔檔案位置`，不是 `原始影片檔案位置` | `test_catalogue_checks.py` |
| episode-catalogue | `語言別代號` 不在對照表裡要指名（`amis` 不是代號）；`族語別(中)` 與 `族語別(英)` 對不起來也要指名 | `test_catalogue_checks.py` |
| srt-data-store | 孤兒檔：階段目錄有而目錄表查無該成果檔名時指名 | `test_catalogue_checks.py` |
| srt-data-store | 表裡有 969 列而階段目錄只有 75 集**不是**錯——那是還沒做 | `test_catalogue_checks.py` |
| episode-catalogue | 兩個語料的表頭除了集識別欄之外完全一致；表頭順序不對要指名 | `test_catalogue_checks.py` |
| episode-catalogue | 排除清單每列要寫同一支的保留檔，但「非新聞節目」（`22NL004_066` 其實是原視華語新聞《晚安新聞》）本來就沒有同一支，「原始mxf影片損毀」（`24NL003_190` 等 8 支 mxf 19 GB 只有開頭幾 MB 有資料、其餘全 0，轉出來 0.7 秒）也一樣，留空不算錯——不可為了過檢查硬填一支；這種檔若出現在目錄裡照樣要指名 | `test_catalogue_checks.py` |
