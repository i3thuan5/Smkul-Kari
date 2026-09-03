# 《開會了》影像側 pipeline：新語料 aiyalaeho

## Why

《開會了》是語料庫的第二個節目，38 集的畫面上同時燒著**族語正字與華語對照**——族語文本直接可讀，是族語新聞（畫面只有華語）做不到的來源；素材已到齊（伺服器 44 支 mp4，本機 41 支、位元組數逐支相同）。新聞編排把語料細節寫死（8 碼日期命名鍵、月份分層、單列 `han` 組裝、目錄驅動、語音側），照用會全部卡住，需要 aiyalaeho 自己的一條編排線。三層架構（Kari-SRT → tests → scripts）已依 explore 流程逐層經使用者確認（2026-08-30～31）。

## What Changes

- **新增 `scripts/aiyalaeho/` 編排 package**（自 news 複製改；news 程式不動）：`paths.py`、`catalogue.py`（檔名解析＋語言代號表＋整批登記 CLI）、`verify_band.py`（黃底雙槽判準，新寫）、`ingest.py`、`make_srt.py`（雙列組裝＋0.5 s 留白鏈）、`make_all.py`、`tracker.py`（9 欄）、`publish.py`（0-cue 放行）、`rebuild.py`、`presets.json`、README。news 的 `fetch_sftp.sh`／`plan_month.py`／`gap_sheets.py`／`batches.py` 在本語料沒有對應的問題（素材已在本機、無月份批次、sheet 首輪即完整、`ocr.cli pending` 已列未讀），**不複製**。
- **新增 store 語料目錄 `Kari-SRT/aiyalaeho/`**：`inventory.json`、`smkul.csv`（9 欄：節目名稱、集數、族語別(英)(中)、語言別、語言代號、影片檔案位置、影片長度、成果檔名——播出資料與字幕srt狀態／語音辨識模型不設欄）、`1-ocr/{1-cues,2-vision,3-srt}`（緊湊編號＝產生順序；不分層；無語音側技術目錄）。
- **命名鍵**：`開會了_<集數3碼>_<族語別英>_<族語別中>`（例 `開會了_068_Amis_阿美`）。播出日期查無可靠來源（目錄與 xlsx 正本無此欄、mp4 metadata 已被轉檔洗掉、公開網路對不回集數），不入鍵；日後取得日期填進度表欄位、鍵不動。slug＝srt_name。
- **交付 SRT 為雙列**：每條恆兩行帶標籤「族語：／華語：」（與語音側 raw 同款式），皆來自畫面（經人校讀的視覺辨識）；族語列照畫面（夾漢字照錄、正字法符號不正規化）；某列空白仍保留標籤行（例如只出「族語：」），兩列皆空才不出條目。**不做 2-asr**——族語文本畫面就有。
- **登記由資料夾檔名驅動**（`NNN-語言[-變體]-字幕狀態.mp4`），不讀 `ilrdf-corpus.csv`（該檔不動）；有影片就做、目錄裡沒影片的集數不出現也不記錯誤；無字幕集切出 0 cue 就以 0 行 SRT 交付、不擋整批定版。
- **BREAKING（僅版型設定）**：`amis-xiuguluan-bilingual` 這筆 preset 自 `scripts/news/presets.json` **搬**到 `scripts/aiyalaeho/presets.json`，改名 `aiyalaeho-bilingual`、華語列槽 h 60→66（實測三集字底貼邊或超出）；news 檔中原筆刪除——版型知識單一存放，這是本 change 對 news 檔案唯一的改動。

## Capabilities

### New Capabilities

- `aiyalaeho-sourcing`：《開會了》一集的來源與身分——全集清單由資料夾檔名驅動、檔名解析（集數／族語別／語言別／語言代號）、命名鍵、登記 pending、有影片就做。

### Modified Capabilities

- `srt-data-store`：「命名鍵統一為 srt_name」改為各語料自訂鍵格式與分層（news 不變、aiyalaeho 無日期鍵且不分層）；新增 aiyalaeho 的 store 結構、9 欄進度表、0-cue 照交付不擋定版、離線重建保證及於本語料。
- `subtitle-text-source`：新增「開會了交付 SRT 為雙列」與「族語列忠於畫面」兩條要求（既有的校讀供字、文稿不供字、preset 指定生效等要求不變，直接適用）。
- `cue-timing`：新增雙列帶型的切 cue 前驗證判準（兩列各落自己的槽、逐集驗）；既有單列判準不變。

## Impact

**新增**

```
scripts/aiyalaeho/：README.md  paths.py  catalogue.py  verify_band.py  ingest.py
                    make_srt.py  make_all.py  tracker.py  publish.py  rebuild.py  presets.json
tests/aiyalaeho/：  test_paths.py  test_catalogue.py  test_verify_band.py  test_ingest.py
                    test_make_srt.py  test_tracker.py  test_publish.py  test_rebuild.py
Kari-SRT/aiyalaeho/：inventory.json  smkul.csv  1-ocr/{README.md,1-cues/,2-vision/,3-srt/}（apply 時建立）
```

**修改**：`scripts/news/presets.json`（刪 amis-xiuguluan-bilingual 一筆）、`scripts/README.md`（新 package 檔案表）、根 `README.md`（資料夾架構）、`tests/README.md`（spec × scenario 表）、`Kari-SRT/README.md`（語料層說明）。

**依賴**：`add-episode-sourcing`（實作完成、待歸檔）修改了 srt-data-store 的同一條命名鍵要求——先歸檔它，本 change 的 delta 以其歸檔後文本為基準。

**驗收**：`tox -e unittest`／`tox -e flake8`；news 的 `rebuild --verify` 照樣通過（news 未被動到的證明）；068 實資料端對端（登記→切 cue→視覺辨識→ingest→組裝→publish→aiyalaeho rebuild --verify 逐 byte）；隨後**整批做完全部有影片的集數**（本機 41＋伺服器 3，約 44 集），smkul.csv 定版含全部集數。
