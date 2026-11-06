# Proposal

## Why

上一個 change 把新聞的影片都搬進了 `/home/news/mkv/<年-月>/<成果檔名>.mkv`，並規定程式只在那一個位置找影片。但管理者（root）正在把這些檔案一支一支**搬走**到 `/docker/news/mkv/<年-月>/<成果檔名>.mkv`（`root:root` 755，我們只能讀）。2026-10-31 唯讀量到：`/docker/news/mkv/2021-01` 已有 42 支、`/home` 該月剩 29 支，合計 71 支與搬移清單相同，數字還在變動；全部做完大約要一天以上。最終 `/docker` 是定稿區，`/home/news/mkv` 清空，新批次則先放 `/home`、再由管理者搬過去。

現在的程式碰到已被搬走的集數會報錯（「正規位置找不到、原始位置也沒有」），`video_names check` 也會把這些集數報成缺。要讓流程在搬移進行中與搬完後都讀得到，並且讓兩個根日後能輕易抽換。

另外，準備這個 change 時發現上一個 change 留下一個說法不成立：我曾寫「`rebuild --verify` 會對真實目錄跑 `row_problems`」，實際上全 repo 只有開會了的 `rebuild` 會呼叫它，新聞的 `rebuild --verify` 與 `name_catalogue --check` 都沒有。因此「成果檔名不得重複」、「節目名稱與播出日期對得上」、語言別、列序等目錄檢查在新聞這邊從來沒有真的執行過。

## What Changes

- 兩個全域變數放在 `scripts/news/paths.py`：`VIDEO_ROOT_DOCKER = "/docker/news/mkv"`、`VIDEO_ROOT_HOME = "/home/news/mkv"`，日後抽換只改這兩行。
- 讀影片的順序：`/docker` → `/home` → `原始影片檔案位置`。在 `/docker` 找到就直接用、不多問；只有伺服器回報「找不到」才換下一個；連線逾時、權限錯誤直接報錯，不退。
- 寫入只認 `/home`（`apply`、`probe`、`prune`、`undo` 與改名的伺服器步驟）；`/docker` 是管理者管的唯讀定稿區。
- 改成果檔名（`relabel`／`redate`）依影片現在在哪裡：在 `/home` 就在 `/home` 內 rename；在 `/docker` 就拒絕並提示找管理者；**還在原始位置（新批次的 OCR／whisper 階段）就不動伺服器上的影片**，只改目錄與本機各階段檔案，等語言別確認後 `apply` 才用最終名字搬（這推翻上一個 change 的「順便從原始位置搬到新位置」）。
- `apply`：某集同名檔已在 `/docker`，整個停下、指名、一支都不搬。`check` 把兩個根合起來算；`undo` 對已在 `/docker` 的集數拒絕。
- 目錄檢查真的執行：`name_catalogue --check` 與新聞的 `rebuild --verify` 都加跑 `catalogue_checks.row_problems`（成果檔名不得重複、命名規格、與識別欄推出來一致、節目名稱與日期對得上、語言別、素材位置非空、列序）。手動對真目錄跑過，3,153 列乾淨。
- 刪掉探針失敗時提示的備案路徑 `/home/mkv-raw/news/mkv`（探針已成功，用不到）；測試裡寫死的 `/home/news/mkv` 改成引用常數。
- 文件同步：`Kari-SRT/README.md`、`scripts/README.md`、`scripts/news/README.md`、`tests/news/README.md`、`smkul-catalogue-import` 說明。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `episode-video-location`：影片位置由一個根變成兩個根（讀的順序、寫入只認 `/home`）、找不到時的退路順序、改成果檔名的規則、`apply`／`check`／`undo` 碰到 `/docker` 的處理、探針不再提備案。
- `episode-catalogue`：新增一條——目錄檢查（含成果檔名不得重複）必須由 `name_catalogue --check` 與新聞的 `rebuild --verify` 真正執行。

## Impact

- 程式：`scripts/news/paths.py`、`episodes.py`、`video_names.py`、`opening.py`、`relabel.py`、`redate.py`、`name_catalogue.py`、`rebuild.py`、`transcode/archive_batch.py`；其餘（`audio.py`、`plan_month.py`、`vision_tools/prompt.py`）只讀 `remote` 欄與 `locate`，不改。
- 測試：多支測試檔的預期值改成 `/docker` 優先、路徑改引用常數；新增目錄檢查兩條。
- 資料：Kari-SRT 資料檔不動，只有 README 補說明。
- 伺服器：**不動**。管理者還在搬，這個 change 全程不跑 `video_names` 的 `check`／`apply`／`undo`／`prune`／`probe`，只做唯讀的 `locate` 抽驗。
- 風險：程式改好之前，已被搬走的集數會讀不到（目前沒有別的工作在跑，所以還沒出事）。
