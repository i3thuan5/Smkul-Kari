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
| episode-catalogue | 播出時段由節目名稱推導（983 列零例外）；節目名稱不在三種新聞之列時指名中止，不可推出空字串——空時段會組出一個沒人找得到的成果檔名 | `test_catalogue_checks.py` |
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
