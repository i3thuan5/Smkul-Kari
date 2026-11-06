# Design

## Context

現況（2026-10-31 唯讀量到）：

- 管理者（`root`）正在把 `/home/news/mkv/<月>/<名>.mkv` 一支一支**搬走**（`mv`，不是複製）到 `/docker/news/mkv/<月>/<名>.mkv`。`/docker/news`、`/docker/news/mkv` 與月份資料夾都是 `root:root` 755，檔案本身保留擁有者 `ilrdf-corpus` 與原修改時間；我們的帳號在 `/docker` 底下不能建、不能搬、不能刪。
- 2021-01 這個月做到一半：`/docker` 42 支＋`/home` 29 支＝71 支，與上一個 change 的搬移清單一致，兩邊沒有同名重複；前後量了三次，`/docker` 那邊從 37 → 41 → 42。其餘 47 個月份都還在 `/home`（`/home/news/mkv` 共 3,116 支）。
- 最終狀態（使用者確認）：`/docker/news/mkv` 是定稿區、`/home/news/mkv` 清空；新批次（只限新聞）的流程是：交付的 mxf 轉成 mkv 放 `/home/mkv-raw/`（影片在原始位置）→ 切 cue、OCR、whisper、確認語言別（可能 `relabel`）→ 語言別確認後才 `apply` 改名進 `/home/news/mkv` → 管理者到一個階段後搬到 `/docker`。
- 程式現況：所有取檔都經 `video_names.locate`，它只查 `paths.video_path(名稱)`（`/home` 那個）再退到原始位置；`episodes.py` 的 `remote` 欄也是 `/home` 那個；`opening._located` 靠「傳進來的路徑等於 `paths.video_path(名稱)`」判斷有沒有退路。已被搬走的集數會全部報錯。
- 目錄檢查現況：`catalogue_checks.row_problems` 有成果檔名重複、命名規格、與識別欄一致、節目名稱與日期、語言別、素材位置非空、列序等檢查，但全 repo 只有 `scripts/aiyalaeho/rebuild.py` 呼叫它；`name_catalogue --check` 只比對成果檔名欄與推導值、再看排除清單。手動對真目錄跑過 `row_problems`，3,153 列沒有任何問題。

## Goals / Non-Goals

**Goals:**
- 搬移進行中與搬完後，流程都讀得到影片；兩個根日後能只改兩行就抽換。
- 寫入不誤闖 `/docker`；碰到只能由管理者處理的情形，明確拒絕、指名。
- 新批次流程裡，語言別確認之前不動伺服器上的影片。
- 目錄檢查在新聞這邊真的執行，成果檔名重複擋在目錄。

**Non-Goals:**
- 不對伺服器動手：管理者還在搬，不跑 `video_names` 的 `check`／`apply`／`undo`／`prune`／`probe`。
- 不防「搬移途中 `/docker` 出現半截檔」：使用者說搬的時候不會跑別的指令，直接讀 `/docker`。
- 不處理管理者之後怎麼搬新批次（那是他們的流程）。
- 不改 `catalogue_checks.py` 本身（檢查早就在，只是沒人呼叫）。

## Decisions

**D1. 兩個全域變數，`paths.py` 唯一定義。** `VIDEO_ROOT_DOCKER = "/docker/news/mkv"`、`VIDEO_ROOT_HOME = "/home/news/mkv"`，舊的 `VIDEO_ROOT` 拆掉。`video_path()`／`video_dir()`／`video_dirs_to_make()` 維持原名，意義明講成**寫入位置**（`HOME`）；新增 `video_read_paths(名稱)` 回傳 `[DOCKER 的路徑, HOME 的路徑]`。它在**呼叫時**才讀全域變數，不事先存成元組，所以日後換根、或測試改值都立刻生效。替代方案是再加一個 `VIDEO_READ_ROOTS` 元組常數：改了兩個根卻忘了改元組就悄悄漂開，不採用。

**D2. `locate` 依 `video_read_paths` 的順序問，最後才退回原始位置。** 在 `/docker` 找到就直接用、不多問 `/home`；只有伺服器回報「找不到」才換下一個；逾時、權限錯誤直接報錯不退（沿用上一個 change 的 `Sftp.stat` 分辨）。只有退到原始位置才印「退回原始位置」；來源標籤 `docker`／`home`／`原始`（由路徑開頭對全域變數判斷）；三處都沒有，錯誤訊息指名三個路徑。因為管理者用 `mv` 搬，兩邊不會同時有同一支，所以順序只影響多問幾次，不影響正確性。

**D3. `entry["remote"]` 改成 `video_read_paths(名稱)[0]`（`/docker` 那個）。** 它是 `plan_month --todo` 交給 `fetch_sftp.sh` 的路徑，也是整個流程「預期影片在哪」的唯一出口。搬完之後絕大多數集數都在 `/docker`，用它當預期位置，`fetch_sftp.sh` 列資料夾大小時直接命中；搬移期間在 `/home` 的集數，大小表查不到，照原設計叫 `video_names locate` 取退路。

**D4. `opening._located` 的「有退路」判斷改成「傳進來的路徑是 `video_read_paths(名稱)` 之一」。** 這是一個會悄悄壞掉的地方：D3 之後 `remote` 是 `/docker` 路徑，原本的 `paths.video_path(name) == remote` 變成不相等，片頭補抓會把它當成「人家自己指定的路徑」而失去退路，卻不會報錯。要有測試守住。

**D5. 寫入只認 `/home`；`rename_episode` 依影片現在在哪分四種。** `locate` 的來源標籤決定：`home` → 在 `/home` 內 rename 到新名稱位置（跨月建資料夾，照舊）；`docker` → 拒絕，訊息講明「影片在管理者管的唯讀 `/docker`，改名請找管理者」，伺服器、目錄、本機各階段檔案都不動；`原始` → 伺服器不動，只回傳 `moved=False`，目錄與本機照改，等 `apply` 才用最終名字搬；三處都沒有 → 拒絕並指名。`rename_back` 只退「有搬的」（`moved=True`）。「原始 → 不動」推翻上一個 change 的「順便從原始位置搬到新名稱的正規位置」，因為使用者確認的新批次流程是語言別確認後才改名進 `/home`，改名是整個流程的最後一步。

**D6. `apply` 碰到某集同名檔已在 `/docker`，整個停下、一支都不搬。** 與「新舊位置兩邊都有」同一種處理（先檢查、再動手，避免兩個根各有一支）。實作上對規劃涉及的每個月份，列一次 `/docker/news/mkv/<月>`（資料夾不存在視為空），不是逐支問。`probe`、`prune` 只動 `/home`，不變。

**D7. `check` 把兩個根合起來算；`undo` 對已在 `/docker` 的集數拒絕。** `check` 的「到位」＝兩個根合起來恰為目錄每列各一支（同名在兩個根都有也要指名）、大小與清單相同，舊位置只剩排除檔，規則不變。`undo` 對該集在 `/docker` 的拒絕並指名（沒有寫入權限），其餘照搬。

**D8. 目錄檢查接上 `name_catalogue --check` 與新聞的 `rebuild --verify`。** 兩處都加跑 `catalogue_checks.row_problems`（成果檔名不得重複、命名規格、與識別欄推出來一致、節目名稱與日期、語言別、素材位置非空、列序），有問題逐行印出並以非零狀態結束；`rebuild --verify` 比照 `scripts/aiyalaeho/rebuild.py` 的做法。這兩處本來就是 CLAUDE.md 驗收清單裡的把關，檢查接在這裡才算真的執行。重複的成果檔名也因此擋在目錄，不必等到 `apply` 規劃時才發現。

**D9. 刪掉探針的備案提示與 `FALLBACK_ROOT`。** 探針已經成功（跨資料夾 rename 可行），備案「新樹放 `/home/mkv-raw/news/mkv/`」用不到；探針失敗的訊息保留「可能是跨子卷」的提示，不再指向備案路徑。`archive_batch.REMOTE_ARCHIVE_ROOT` 改引用 `paths.VIDEO_ROOT_HOME`（值不變）。

**D10. 測試裡的路徑改引用常數。** 約 9 支測試檔寫死 `/home/news/mkv/…`，日後換根會一起壞；改成引用 `paths.VIDEO_ROOT_*`。例外兩處：`test_paths.py` 保留一個寫死的規格範例；`test_sftp_cli.py` 的路徑只是拿來測引號與批次指令的樣本，跟根無關，維持原樣。

## 檔案樹

**第一層：Kari-SRT（資料）**

```
Kari-SRT/
├── README.md        ✎改  「影片在伺服器的哪裡」那一節：
│                         ・讀：/docker/news/mkv → /home/news/mkv → 原始影片檔案位置
│                         ・寫：只有 /home/news/mkv；/docker 是管理者管的唯讀定稿區
│                         ・新批次流程圖（原始位置 → OCR／whisper／語言別 → apply → 管理者搬）
│                         ・兩個根是 paths.py 的兩個全域變數
└── 其餘（news/smkul.csv、排除影片.csv、各階段目錄）＝不動
伺服器 ＝ 不動（唯讀 locate 抽驗而已）
```

**第二層：tests/（測試）**

```
tests/
├── news/
│   ├── test_paths.py          ✎改  兩個根、讀的順序、寫的位置、換根只改常數
│   ├── test_episodes.py       ✎改  remote 欄＝讀的順序第一個
│   ├── test_video_names.py    ✎改  locate 順序與標籤；apply／check／undo／rename_episode；刪備案
│   ├── test_audio.py          ✎改  先 /docker、再 /home、再原始
│   ├── test_opening.py        ✎改  兩個根的推導位置都有退路
│   ├── test_plan_month.py     ✎改  規劃與待辦清單列出 /docker 路徑
│   ├── test_vision_prompt.py  ✎改  remote_of 順序與常數
│   ├── test_relabel.py        ✎改  影片在 原始位置／home／docker／都沒有，四種
│   ├── test_redate.py         ✎改  同上
│   ├── test_name_catalogue.py ✎改  --check 加跑 row_problems（含成果檔名重複）
│   ├── test_rebuild_*.py      ✎改  --verify 對新聞目錄也跑 row_problems（現有涵蓋 --verify 的那支）
│   ├── test_sftp_cli.py、test_fetch_sftp_config.py ＝不動
│   └── README.md              ✎改  補下表
└── transcode/test_archive_batch.py ＝不動（寫入位置的值沒變）
```

**第三層：scripts/（程式）**

```
scripts/
├── news/
│   ├── paths.py           ✎改  VIDEO_ROOT_DOCKER／VIDEO_ROOT_HOME；video_read_paths()
│   ├── episodes.py        ✎改  remote ＝ video_read_paths(名稱)[0]
│   ├── video_names.py     ✎改  locate／rename_episode(moved)／apply／check／undo；刪 FALLBACK_ROOT
│   ├── opening.py         ✎改  _located：路徑是 video_read_paths 之一就有退路
│   ├── relabel.py、redate.py ✎改  跟著 rename_episode 的 moved
│   ├── name_catalogue.py  ✎改  --check 加跑 row_problems
│   ├── rebuild.py         ✎改  --verify 對新聞目錄也跑 row_problems
│   └── audio.py、plan_month.py、vision_tools/prompt.py ＝不動
├── transcode/archive_batch.py ✎改  REMOTE_ARCHIVE_ROOT = paths.VIDEO_ROOT_HOME
├── README.md、news/README.md  ✎改  兩個根、讀寫規則、新批次流程
.claude/commands/smkul-catalogue-import.md ✎改  新批次流程與「目錄檢查要過」
```

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| episode-video-location | 兩個根是兩個全域變數：把 `VIDEO_ROOT_DOCKER`、`VIDEO_ROOT_HOME` 換成別的值，`video_path`、`video_read_paths`、每集的 `remote` 欄全部跟著變（防有人在別處又寫死 `/docker/news/mkv`） | `test_paths.py`、`test_episodes.py` |
| episode-video-location | 讀的順序 `/docker` → `/home`、寫的位置只有 `/home`：`video_path` 是 `/home` 那個，`video_read_paths` 是 `[/docker…, /home…]` | `test_paths.py` |
| episode-video-location | `locate`：`/docker` 有就用、只問一次；`/docker` 回「找不到」才問 `/home`；兩個根都沒有才退回原始位置並印「退回原始位置」；三處都沒有，訊息指名三個路徑 | `test_video_names.py`、`test_audio.py` |
| episode-video-location | 管理者搬到一半：同一批集數有的在 `/docker`、有的在 `/home`，兩種都找得到；來源標籤分得出 docker、home、原始 | `test_video_names.py` |
| episode-video-location | 查 `/docker` 時逾時或權限錯誤：直接報錯，不去問 `/home`（網路一抖就讀到別的位置） | `test_video_names.py`、`test_audio.py` |
| episode-video-location | 片頭補抓：傳進來的路徑是兩個根之一的推導位置就有退路，人家自己指定的路徑沒有；用 `/docker` 路徑呼叫也要有退路（防 `remote` 改成 `/docker` 後悄悄失去退路） | `test_opening.py` |
| episode-video-location | 改成果檔名時影片在 `/home`：在 `/home` 內 rename 到新名稱位置，跨月建資料夾 | `test_video_names.py`、`test_relabel.py`、`test_redate.py` |
| episode-video-location | 改成果檔名時影片在 `/docker`：拒絕並提示找管理者，伺服器不動、目錄與本機各階段檔案也不動 | `test_video_names.py`、`test_relabel.py`、`test_redate.py` |
| episode-video-location | 改成果檔名時影片還在原始位置（新批次 OCR／whisper 階段）：伺服器上的影片不動，只改目錄與本機，`moved=False`，等 `apply` 才用最終名字搬；`rename_back` 不退沒搬的 | `test_video_names.py`、`test_relabel.py`、`test_redate.py` |
| episode-video-location | 改成果檔名時三處都沒有影片：拒絕並指名三個路徑 | `test_video_names.py`、`test_relabel.py` |
| episode-video-location | `apply`：某集同名檔已在 `/docker`，整個停下並指名、一支都不搬 | `test_video_names.py` |
| episode-video-location | `check`：到位＝兩個根合起來恰為目錄每列各一支、大小與清單相同；同名在兩個根都有、缺的、多的逐一指名 | `test_video_names.py` |
| episode-video-location | `undo`：已在 `/docker` 的集數拒絕並指名，其餘照搬 | `test_video_names.py` |
| episode-video-location | 對伺服器的寫入只發生在暫放區：規劃、探針、搬移、還原、清空資料夾、改成果檔名，送出的寫入指令（mkdir／rename／rmdir）路徑都不在 `/docker` 底下 | `test_video_names.py` |
| episode-video-location | 探針失敗的訊息仍提示可能是跨子卷，但不再指向 `/home/mkv-raw/news/mkv` 備案 | `test_video_names.py` |
| episode-sourcing | 規劃（離線）列出 `/docker` 路徑；本機暫存檔名不論檔在哪個根都是 `<成果檔名>.mkv`，只有退回原始位置才是原名 | `test_plan_month.py`、`test_audio.py`、`test_vision_prompt.py` |
| episode-catalogue | `name_catalogue --check` 抓成果檔名重複：兩列同名時指名兩個行號並 exit 1（`apply` 只能擋在搬移當下，先擋在目錄，重複的名稱就進不了流程） | `test_name_catalogue.py` |
| episode-catalogue | `name_catalogue --check` 也跑整組 `row_problems`：節目名稱與日期對不上、語言別代號不在表內、列序亂掉都要 exit 1 並逐行指名 | `test_name_catalogue.py` |
| episode-catalogue | 新聞的 `rebuild --verify` 對目錄也跑同一組檢查，有問題指名那一列（目前只有開會了在跑，新聞完全沒跑） | `test_rebuild_*.py` |

## Risks / Trade-offs

- **改好之前，已被搬走的集數讀不到** → 目前沒有別的工作在跑；程式改完全部測試綠就解除。
- **搬移途中的短暫視窗**：`/docker` 優先又不防半截檔。使用者說他搬的時候不會執行其他指令，所以不防；若日後情況變了，才需要補「`/docker` 找到時順便確認 `/home` 沒有同名檔」。
- **目錄檢查接上後，目前沒有問題的 3,153 列日後可能被新規則擋下**：這是目的；每個失敗訊息都指名行號與原因。接上當下已手動驗證乾淨，任務裡也會用真目錄再跑一次。
- **`rename_episode` 對「原始位置」不再搬**：改了一個上一個 change 明文寫的行為。新批次流程裡，`apply` 才是搬進正式位置的唯一動作；若有人用 `relabel` 改了語言別卻忘了跑 `apply`，影片會留在原始位置，直到 `apply` 為止；`locate` 仍讀得到，所以不會壞。
- **上一個 change 的文件有一句不成立**（「`rebuild --verify` 會跑日期對照檢查」）→ 這次補上實作，並在回覆紀錄裡明講。

## Migration Plan

1. 先跑一遍現有測試記基準，再逐模組先寫測試（紅）、寫程式（綠），每完成一步立刻跑對應測試與全部 unittest。
2. 接上目錄檢查後，對真目錄跑 `name_catalogue --check` 與 `rebuild --verify`，確認 3,153 列通過。
3. **全程不動伺服器**：只做唯讀的 `video_names locate` 抽驗（一集在 `/docker`、一集在 `/home`）。
4. 驗收：`unittest`、`flake8`、`name_catalogue --check`、`rebuild --verify` 與基準比對，寫回覆紀錄。
5. 回復：這個 change 只改程式、測試與文件，沒有資料與伺服器變動；有問題用 `git restore` 還原檔案即可。
