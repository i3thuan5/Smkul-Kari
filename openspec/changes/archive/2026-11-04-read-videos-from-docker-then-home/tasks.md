# Tasks

## 1. 先跑現有測試，記下基準

- [x] 1.1 跑 `.tox/unittest/bin/python -m unittest discover -s tests -t .`、`.tox/flake8/bin/flake8 . --count`、`python3 -m scripts.news.name_catalogue --check`，記下通過的測試數、flake8 數字、不合列數。驗證：三者都通過（目前基準：2755 項、flake8 為 0、不合 0 列）
- [x] 1.2 背景跑 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify`（約 6 分鐘，`run_in_background`）。驗證：輸出兩行 OK（3153 支 SRT 逐 byte 相同、655 集平行語料相同），這就是基準
- [x] 1.3 手動對真目錄跑 `catalogue_checks.row_problems`（唯讀，離線）。驗證：回傳空清單（3,153 列沒有任何問題），確認 §8 接上之後不會立刻失敗

## 2. 兩個全域變數與讀的順序（`paths.py`、`archive_batch.py`）

- [x] 2.1 先寫測試：`tests/news/test_paths.py` 補 `VIDEO_ROOT_DOCKER`／`VIDEO_ROOT_HOME`、`video_path` 仍是 `/home` 的寫入位置、`video_read_paths` 是 `[/docker…, /home…]`、**換掉兩個根的值後所有路徑跟著變**（用 `mock.patch.object` 改全域變數，防有人在別處寫死）、舊的 `VIDEO_ROOT` 不存在；留一個寫死的規格範例。驗證：跑 `test_paths`，新案例紅
- [x] 2.2 實作：`paths.py` 拆 `VIDEO_ROOT`、加 `video_read_paths`（呼叫時才讀全域變數）；`archive_batch.py` 的 `REMOTE_ARCHIVE_ROOT` 改引用 `paths.VIDEO_ROOT_HOME`。驗證：`test_paths`、`test_archive_batch` 綠；全部 unittest 與 flake8 仍綠

## 3. 每集的 `remote` 欄（`episodes.py`）

- [x] 3.1 先寫測試：`tests/news/test_episodes.py` 的 `remote` 欄改成 `video_read_paths(名稱)[0]`（`/docker`），原始欄空白或多條候選都不影響；換根後 `remote` 跟著變。驗證：跑 `test_episodes`，新案例紅
- [x] 3.2 實作：`entry_of` 的 `remote` 改成讀的順序第一個。驗證：`test_episodes` 綠；`test_plan_month`、`test_audio`、`test_vision_prompt` 預期值先會紅（`/home` → `/docker`），留到 §6 處理；其餘 unittest 與 flake8 仍綠

## 4. 搬移工具（`video_names.py`，一項一項來；怎麼對伺服器下指令仍由外面傳入，測試傳假的）

- [x] 4.1 `locate`：先寫測試（`/docker` 有就用、只問一次；`/docker` 找不到才問 `/home`；兩個根都沒有才退回原始位置並印「退回原始位置」；三處都沒有，訊息指名三個路徑；查 `/docker` 逾時不換；管理者搬到一半的混合情形；來源標籤 docker／home／原始；CLI `locate` 印出標籤），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.2 `rename_episode`／`rename_back`：先寫測試（在 `/home` → `/home` 內 rename、跨月建資料夾；在 `/docker` → 拒絕並提示找管理者、伺服器不動；在原始位置 → 伺服器不動、`moved=False`、`rename_back` 不退沒搬的；三處都沒有 → 拒絕並指名三個路徑；名稱沒變不搬），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.3 `apply`：先寫測試（某集同名檔已在 `/docker` → 整個停下、指名、一支都不搬、伺服器沒有任何寫入；其餘舊案例不變），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.4 `check` 與 `undo`：先寫測試（`check`：兩個根合起來恰為目錄每列各一支、同名在兩個根都有要指名、缺與多逐一指名；`undo`：已在 `/docker` 的集數拒絕並指名、其餘照搬），再實作。驗證：`test_video_names` 先紅後綠
- [x] 4.5 對伺服器的寫入只發生在 `/home`：先寫測試（用會記錄指令的假伺服器，跑規劃、探針、搬移、還原、清空資料夾、改名，確認所有 mkdir／rename／rmdir 的路徑都不在 `/docker` 底下），再視需要修正。驗證：`test_video_names` 綠
- [x] 4.6 刪掉 `FALLBACK_ROOT` 與探針失敗訊息裡的備案路徑：先改測試（探針失敗訊息仍提示可能是跨子卷、不再出現 `/home/mkv-raw/news/mkv`），再改程式。驗證：`test_video_names` 先紅後綠；每做完一項都跑全部 unittest 與 flake8

## 5. 接上流程

- [x] 5.1 `opening.py`：先在 `tests/news/test_opening.py` 補（傳 `/docker` 路徑呼叫也有退路、傳 `/home` 路徑也有；人家自己指定的路徑沒有），再改 `_located` 的判斷為「路徑是 `video_read_paths` 之一」。驗證：`test_opening` 先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 5.2 `relabel.py`／`redate.py`：先改 `test_relabel.py`、`test_redate.py`（影片在 原始位置／`/home`／`/docker`／都沒有 四種各一例；`/docker` 與都沒有時目錄與本機各階段檔案不動；原始位置時目錄與本機照改而伺服器不動；本機失敗時只退有搬的），再改程式跟著 `rename_episode` 的 `moved`。驗證：兩支測試先紅後綠，全部 unittest 與 flake8 仍綠

## 6. 其餘測試的預期值

- [x] 6.1 `test_audio.py`、`test_plan_month.py`、`test_vision_prompt.py`：預期路徑改成 `/docker` 優先（`entry["remote"]`、規劃與待辦清單、`remote_of`、`asked` 的斷言），路徑一律引用 `paths.VIDEO_ROOT_*`，不寫死。驗證：三支測試綠；全部 unittest 與 flake8 仍綠
- [x] 6.2 其餘測試裡寫死的 `/home/news/mkv`（`test_redate.py`、`test_video_names.py`、`test_opening.py`、`test_episodes.py`、`test_archive_batch.py`）改成引用常數；`test_paths.py` 保留一個寫死的規格範例；`test_sftp_cli.py` 的路徑只是引號與批次指令的樣本，維持原樣。驗證：`grep -rn "/home/news/mkv" tests` 只剩 `test_paths.py` 的範例與 `test_sftp_cli.py` 的樣本；全部 unittest 與 flake8 仍綠

## 7. 目錄檢查真的執行（`name_catalogue.py`、`rebuild.py`）

- [x] 7.1 先寫測試：`tests/news/test_name_catalogue.py` 補（兩列成果檔名重複 → `--check` 指名兩個行號並 exit 1；節目名稱與日期對不上、語言別代號不在表內、列序亂掉各一例 → exit 1 並逐行指名；乾淨目錄 → exit 0），再改 `name_catalogue --check` 加跑 `catalogue_checks.row_problems`。驗證：`test_name_catalogue` 先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 7.2 先寫測試：現有涵蓋新聞 `rebuild --verify` 的測試（`tests/news/test_rebuild_sources.py`；不合適就新增 `test_rebuild_catalogue.py`）補「目錄有成果檔名重複或其他不符 → `rebuild` 指名該列並以非零結束」「乾淨目錄不因此失敗」，再改 `scripts/news/rebuild.py`，在 `main` 讀目錄後先跑 `row_problems`，有問題逐行印出並 raise，比照 `scripts/aiyalaeho/rebuild.py`。驗證：該測試先紅後綠，全部 unittest 與 flake8 仍綠
- [x] 7.3 對真目錄跑 `python3 -m scripts.news.name_catalogue --check`。驗證：不合 0 列、`row_problems` 0 個問題、exit 0（與 1.3 一致）

## 8. 文件同步

- [x] 8.1 更新 `Kari-SRT/README.md`（「影片在伺服器的哪裡」那一節：讀的順序、只寫 `/home`、`/docker` 是管理者管的唯讀定稿區、新批次流程圖、兩個根是 `paths.py` 的兩個全域變數）、`scripts/README.md`（`paths.py`、`video_names.py`、`episodes.py`、`opening.py`、`relabel.py`、`redate.py`、`name_catalogue.py`、`rebuild.py` 有變的列）、`scripts/news/README.md`（〈影片現在放哪裡〉整節改寫）、`tests/news/README.md`（補 design 對照表那幾列）。驗證：`tests/news/test_readme_covers_scripts.py` 通過；文件裡不再說「正規位置＝`/home/news/mkv`」或「改名時順便從原始位置搬」（用 grep 確認）
- [x] 8.2 更新 `.claude/commands/smkul-catalogue-import.md`：新批次流程改成「轉 mkv → OCR／whisper／語言別 → `apply` 改名進 `/home/news/mkv` → 管理者搬 `/docker`」，並加「目錄檢查（含成果檔名重複）要過」。驗證：說明讀起來與實際指令一致，指令名稱用 `--help` 對過

## 9. 驗收與紀錄

- [x] 9.1 唯讀抽驗 `locate`（不寫伺服器）：對兩集各跑一次 `python3 -m scripts.news.video_names locate`——一集管理者已搬進 `/docker`（例如 2021-01 已在 `/docker` 的那幾集之一）、一集還在 `/home`（例如 2021-02）。驗證：來源分別顯示 docker 與 home，路徑與大小正確；`/docker` 那集 stdout 只有一行、沒有「退回」訊息
- [x] 9.2 重跑 1.1、1.2 的全部檢查。驗證：與基準相同（unittest 數量多出的只有本次新增案例、flake8 為 0、不合 0 列、`rebuild --verify` 兩行 OK）；`git -C Kari-SRT diff --stat news/smkul.csv news/排除影片.csv` 沒有差異
- [x] 9.3 在 `kithann/tuiue/<MMDD>/` 寫回覆紀錄：做了什麼、基準與驗收數字、管理者搬移進度（量到的數字與時間）、`locate` 抽驗結果、**我先前「`rebuild --verify` 會跑 `row_problems`」那句話不成立、這次補上**、全程沒有對伺服器寫入。驗證：檔案存在且內容含上述各項

> 9.1 實測（2026-11-04，帳號已恢復）：抽驗 10 集（2021-01～2024-12 各月），來源皆為 docker、stdout 一行、無「退回」訊息；管理者已把全部搬完，伺服器上已無 `/home` 的集數可驗，`home` 與原始位置兩條路由單元測試涵蓋。

## Workflow follow-up

- 全部完成後依使用者指示執行 `/opsx:archive`，規格需要就 sync：`episode-video-location` 六條 MODIFIED 與一條 ADDED、`episode-catalogue` 一條 ADDED 併進主規格
