# Tasks

## 1. 先跑現有測試，記下基準

- [x] 1.1 跑 `.tox/unittest/bin/python -m unittest discover -s tests -t .`、`.tox/flake8/bin/flake8 . --count`、`python3 -m scripts.news.name_catalogue --check`，把通過的測試數、flake8 數字、不合列數記進回覆紀錄。驗證：三者都通過（目前基準：2618 項、flake8 為 0、不合 0 列）
- [x] 1.2 背景跑 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify`（約 6 分鐘，`run_in_background`）。驗證：輸出兩行 OK（3153 支 SRT 逐 byte 相同、655 集平行語料相同），這就是基準

## 2. 封存位置算法搬到共用處（`paths.py`、`archive_batch.py`）

- [x] 2.1 先寫測試：`tests/news/test_paths.py` 補 `video_path`／`video_dir`／`video_dirs_to_make`（`20210101_001_午間_Rukai_魯凱` → `/home/news/mkv/2021-01/…mkv`、月份取自成果檔名而非原資料夾如 `20241001_275`、含撇號名稱、不合規格的名稱拒絕）；`tests/transcode/test_archive_batch.py` 加「`remote_archive_*` 的值與搬移前逐字相同」。驗證：跑這兩支測試檔，`test_paths` 的新案例紅
- [x] 2.2 實作：`paths.py` 加 `VIDEO_ROOT` 與三個函式；`archive_batch.py` 的 `remote_archive_*`、`remote_dirs_to_make` 改成引用它們的別名。驗證：`test_paths`、`test_archive_batch` 綠；全部 unittest 與 flake8 仍綠

## 3. 每集的 `remote` 欄（`episodes.py`）

- [x] 3.1 先寫測試：`tests/news/test_episodes.py` 補 `entry["remote"]` 等於 `video_path(成果檔名)`、`video`／`file` 欄仍是原始欄位的值、工作區名不變。驗證：跑 `test_episodes`，新案例紅
- [x] 3.2 實作：`entry_of` 加 `remote` 欄。驗證：`test_episodes` 綠；全部 unittest 與 flake8 仍綠

## 4. 搬移工具（`scripts/news/video_names.py`，一項一項來）

怎麼對伺服器下指令由外面傳進來，測試一律傳假的，全部離線。

- [x] 4.1 `plan`：先寫 `tests/news/test_video_names.py` 的規劃案例（每列恰好一組、排除清單上的路徑不進、兩列同舊位置或同新位置整份拒絕、不在 `/home/mkv-raw/` 的列拒絕、月份取自成果檔名），再實作。驗證：跑 `test_video_names`，先紅後綠
- [x] 4.2 `locate`：先寫測試（正規位置在就用它且不看原始欄；伺服器回「找不到」才退回原始位置並印「退回原始位置」；兩處都沒有報錯並指名兩個路徑；逾時、權限錯誤等非「找不到」不退；原始欄多條候選依挑檔規則選一支），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.3 `apply`：先寫測試（先寫清單再搬第一支；預設不送指令；逐層建資料夾且每月只建一次、已存在不報錯；第三支失敗時清單完整；續跑四種現況：新有舊無跳過／舊有新無搬／兩邊都有停下不覆寫／都沒有指名），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.4 `probe`：先寫測試（過去成功並搬回、最後狀態與探針前相同；過去失敗就停止並提示跨子卷備案；搬回失敗要明講檔案現在在哪），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.5 `check`：先寫測試（全部到位；缺檔指名並以非零結束；多出的檔逐一指名；大小與清單相同），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.6 `undo`：先寫測試（依清單反向搬；舊位置被佔用時拒絕不覆寫），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.7 `rename_episode`：先寫測試（正規位置在就從那裡搬到新名稱的正規位置；正規沒有、原始有，從原始位置搬；兩處都沒有拒絕；跨月時建月份資料夾），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.8 `prune`：先寫測試（只刪空的、含排除檔的資料夾不刪、由深到淺、永遠不刪 `/home/mkv-raw`、預設只列出、刪除失敗不吞並指名該資料夾），再實作（`Sftp` 加 `scan`／`rmdir`）。驗證：`test_video_names` 先紅後綠
- [x] 4.9 指令列（`plan`／`probe`／`apply`／`check`／`undo`／`prune`／`locate`）：先寫測試（`plan` 是預設且不送指令；`apply` 必須明確指定；`locate` 印出路徑、大小與來源），再實作。驗證：`test_video_names` 先紅後綠；每做完一項都跑全部 unittest 與 flake8

## 5. 接上流程（一個一個接，每個都先寫測試）

- [x] 5.1 `tests/news/test_sftp_cli.py` 補 `rename` 的撇號＋中文案例與雙引號兩個參數都被擋。驗證：跑 `test_sftp_cli`；這是對現有行為的特徵測試，預期直接綠，若紅就是現有程式有漏洞，先修
- [x] 5.2 `audio.py`：先在 `test_audio.py` 補（影片來源先用正規位置、本機已有封存 mkv 仍優先、找不到才退回、`_remote_size` 分清「找不到」與其他失敗），再改程式（用 `locate`）。驗證：`test_audio` 先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 5.3 `opening.py`：先在 `tests/news/test_opening.py` 補（`grab-remote` 的呼叫端先 locate、找不到才退），再改。驗證：`test_opening` 先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 5.4 `plan_month.py`：先改 `test_plan_month.py`（規劃與待辦清單列出正規位置、規劃不對伺服器發指令、刪掉 `_light_copy` 相關案例），再改程式並刪 `_light_copy`、不再呼叫 `sources.resolve`。驗證：`test_plan_month` 先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 5.5 `vision_tools/prompt.py`：先改 `test_vision_prompt.py`（暫存檔名是 `<成果檔名>.mkv`、下載指令用實際找到的位置、說明文字是 mkv），再改程式。驗證：`test_vision_prompt` 先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 5.6 `fetch_sftp.sh`：大小表查不到某集時呼叫 `python3 -m scripts.news.video_names locate`，取不到才 FAIL。驗證：`bash -n scripts/news/fetch_sftp.sh` 語法通過；`tests/news/test_fetch_sftp_config.py` 仍綠；`locate` 本身的行為由 4.2、4.8 的測試保證
- [x] 5.7 `sftp.sh` 新增 `rmdir`：先在 `test_sftp_cli.py` 補（路徑是獨立引數、含雙引號被擋、批次指令是 `rmdir "路徑"` 而且**不**加前導 `-` 以免吞錯），再改 `sftp.sh`。驗證：`test_sftp_cli` 先紅後綠
- [x] 5.8 `relabel.py`／`redate.py`：先在 `test_relabel.py`、`test_redate.py` 補（改成果檔名時伺服器上的影片一併 rename、伺服器那步先做、失敗整個不動本機、兩處都沒有拒絕、本機失敗時試著搬回），再改程式（現有案例改傳假的 sftp，不連網）。驗證：兩支測試先紅後綠，全部 unittest 與 flake8 仍綠

## 6. 文件同步

- [x] 6.1 更新 `Kari-SRT/README.md`（影片在伺服器的哪裡、原始欄的用途）、`scripts/README.md`（`video_names.py` 與 `paths.py`、`plan_month`、`audio` 等有變的列）、`scripts/news/README.md`（「影片來源」「跑法」改寫、刪 2021-02 輕量副本的說明）、`tests/news/README.md`（補對照表，與 design 一致）。驗證：`tests/news/test_readme_covers_scripts.py` 通過；文件裡不再有「先抓 mp4」「輕量副本」這類過時說法（用 grep 確認）
- [x] 6.2 更新 `.claude/commands/smkul-news.md`（規劃不再用挑檔規則、抓檔會先 locate）與 `.claude/commands/smkul-catalogue-import.md`（新批次匯入後多一步 `video_names plan`／`apply`，才算收進來）。驗證：兩份說明讀起來與實際指令一致，指令名稱用 `--help` 對過

## 7. 對真伺服器動作（程式與測試全綠之後才做）

- [x] 7.1 對真目錄跑 `python3 -m scripts.news.video_names plan`（唯讀）。驗證：3,153 組、48 個月份資料夾、0 個衝突、排除的 18 支不在內；數字不符就停止，不做 7.2 起的任何步驟
- [x] 7.2 `probe`：對一支含撇號的拉阿魯哇真檔，搬到 `/home/news/mkv/<年-月>/` 再搬回。驗證：兩次都成功、檔案大小前後相同、狀態與探針前一致；**過去那一步失敗就停止，不做 7.3 起的步驟**，把訊息與備案（新樹改放 `/home/mkv-raw/news/mkv/`）寫進回覆紀錄
- [x] 7.3 `apply`：背景執行（`run_in_background`），搬全部 3,153 支（約 40 分鐘，可中斷續跑）。驗證：結束訊息顯示全部完成、清單檔存在於 `kithann/out/news/video-rename/`
- [x] 7.4 `check`：對伺服器核對。驗證：新位置 3,153 支、大小皆與清單相同、`/home/mkv-raw/` 只剩排除的 18 支，無多出或缺少
- [x] 7.5 抽驗 `locate`：對三集（含一集拉阿魯哇撇號名稱、一集跨月的 `20241001_275_晚間_Amis_阿美`、一集 2021-01）各跑一次。驗證：來源都顯示「正規」、大小與清單相同

## 8. 驗收與紀錄

- [x] 8.1 重跑 1.1、1.2 的全部檢查。驗證：與基準相同（unittest 數量多出的只有本次新增案例、flake8 為 0、不合 0 列、`rebuild --verify` 兩行 OK）；`git -C Kari-SRT diff --stat news/smkul.csv news/排除影片.csv` 沒有任何差異（逐 byte 不變）
- [x] 8.2 在 `kithann/tuiue/<MMDD>/` 寫回覆紀錄：做了什麼、基準與驗收數字、探針與搬移的結果、備案是否啟用、`fetch_sftp.sh` 的退路只驗了語法與 Python 部分這一點、搬空的舊資料夾保留。驗證：檔案存在且內容含上述各項

## 9. 最後一步：清掉搬空的舊資料夾

- [x] 9.1 `prune`（預設只列出）。驗證：列出的資料夾都是搬移清單裡舊位置所在或其上層，沒有 `/home/mkv-raw` 本身，含排除檔的資料夾不在列表內
- [x] 9.2 `prune` 真的刪（數量不多，前景即可）。驗證：伺服器上 `/home/mkv-raw/` 只剩含排除檔的資料夾，排除的 18 支原封不動，再跑一次 `check` 仍通過
- [x] 9.3 把清除結果補進 8.2 寫的回覆紀錄（刪了哪些資料夾、剩哪些）。驗證：紀錄檔含這一段

## Workflow follow-up

- 全部完成後依使用者指示執行 `/opsx:archive`，規格需要就 sync：把本 change 的 delta 併進 `openspec/specs/episode-sourcing/spec.md`，並新增 `openspec/specs/episode-video-location/spec.md`
