# Proposal

## Why

伺服器上新聞的 mkv（目錄 3,153 列）散在 `/home/mkv-raw/` 底下 53 個資料夾，檔名是原語會交付時留下的，格式不一（`20241201S0800.mkv`、`24NL004_365_族語晚間新聞_阿美族.mkv`、`21NL004_37晚間族語新聞.mkv`……），有的檔名還打錯；資料夾的月份也跟播出月份對不上（48 列）。要找一集的影片只能靠 `smkul.csv` 的 `原始影片檔案位置` 加上一套挑檔規則，影片和 SRT、預覽檔又不同名。成果檔名早已是這個語料的定位鍵，影片也該照它命名、照播出月份分資料夾，跟 3-srt 一個排法。

## What Changes

- 伺服器上目錄裡的 3,153 支 mkv，用 **rename（移動）** 搬到 `/home/news/mkv/<年-月>/<成果檔名>.mkv`（年-月取自成果檔名；例：`/home/mkv-raw/110.01-110.10/1月原始mxf檔/20210101S1100.mkv` → `/home/news/mkv/2021-01/20210101_001_午間_Rukai_魯凱.mkv`）。複製不可行：全部約 7 TB，伺服器只剩 5.3 TB。
- 排除影片.csv 的 18 支與開會了的影片不動。
- `smkul.csv` 的 `原始影片檔案位置` 欄原樣保留、逐 byte 不變：作追蹤紀錄，也是新位置找不到時的退路——流程先找由成果檔名推導的位置，伺服器回報「找不到」才退回這一欄（連線失敗、權限錯誤不退，直接報錯）。
- 影片位置改由成果檔名推導（不新增欄位）；整條流程取遠端路徑只有一個出口。
- 新增搬移工具（規劃、探針、執行、核對、還原）：先搬一支含撇號的真檔過去再搬回來，確認跨資料夾 rename 可行才做全部；執行前先寫「舊 → 新」清單，可還原、可中斷續跑。
- 改成果檔名（改語別、改日期）時，伺服器上的檔一併 rename；新位置與原始位置都找不到才拒絕。
- 全部搬完、驗收通過後，最後一步清掉搬空的舊資料夾（只刪空的；含排除檔的資料夾自然不空，留著）。
- 刪除 2021-02 mxf 輕量副本的死程式；封存位置的算法從 `transcode/` 那條支線搬到流程共用處。
- 文件同步：`Kari-SRT/README.md`、`scripts/README.md`、`scripts/news/README.md`、`smkul-news` 與 `smkul-catalogue-import` 說明、`tests/news/README.md`。

## Capabilities

### New Capabilities

- `episode-video-location`：一集影片在伺服器上放哪裡、怎麼搬過去、搬的過程怎麼保證可還原與可核對，以及改成果檔名時影片怎麼跟著動。

### Modified Capabilities

- `episode-sourcing`：流程取影片位置改成先用由成果檔名推導的位置，找不到才退回 `原始影片檔案位置`（退路依匯入時的挑檔規則選一支）；批次規劃（離線）改為直接列出推導出的位置。

## Impact

- 伺服器：`/home/news/mkv/` 新增 48 個月份資料夾、3,153 支檔；`/home/mkv-raw/` 只剩排除的 18 支，搬空的舊資料夾最後清掉。這是第一次對伺服器做寫入（含建資料夾、搬檔與刪空資料夾）。
- 資料：`Kari-SRT` 的資料檔一個 byte 都不改（`smkul.csv`、排除影片.csv 與各階段目錄不動），只有 README 補說明。
- 程式：`scripts/news/paths.py`、`episodes.py`、`audio.py`、`plan_month.py`、`opening.py`、`fetch_sftp.sh`、`vision_tools/prompt.py`、`relabel.py`、`redate.py`、`transcode/archive_batch.py`，新增 `scripts/news/video_names.py`。
- 測試：新增 `tests/news/test_video_names.py`，多支既有測試的預期值改成新位置。
- 風險：跨子卷 rename 可能失敗（探針先擋，備案是新樹放 `/home/mkv-raw/news/mkv/`）；搬移期間不能有人用舊路徑讀影片（現在沒有其他 session 在動）。
