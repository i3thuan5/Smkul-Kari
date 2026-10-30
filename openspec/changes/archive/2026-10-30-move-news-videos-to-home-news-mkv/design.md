# Design

## Context

現況（2026-10-30 量到）：

- 目錄 `Kari-SRT/news/smkul.csv` 3,153 列，`原始影片檔案位置` 全部是 `home/mkv-raw/…` 的單一路徑（沒有分號候選），分布在 53 個資料夾，48 列的資料夾月份與播出月份不同。伺服器上共 3,171 支影片＝目錄 3,153 支＋排除清單 18 支，沒有第三種。
- 15 支程式、22 支測試檔靠 `原始影片檔案位置` 或 `sources.pick`／`resolve_slug.server_path` 找影片：

```
smkul.csv 原始影片檔案位置 ─▶ sources.pick() 挑檔 ─▶ server_path() ─▶ SFTP
  （audio.py、plan_month.py、vision_tools/prompt.py 各算一遍）
```

- `/home/news/mkv/<年-月>/<成果檔名>.mkv` 本來就是這個 repo 規劃的「封存位置」：`transcode/archive_batch.py` 已有 `remote_archive_path()`、逐層建資料夾的 `remote_dirs_to_make()`，本機封存目錄也是同樣結構。伺服器上目前沒有 `/home/news`。
- 伺服器：`/` 底下 `/home` 對所有人可寫；`df` 顯示 `/home` 與 `/home/mkv-raw` 容量相同，但目錄大小的數字像 btrfs，若 `mkv-raw` 是獨立子卷，跨子卷 rename 會失敗，從 SFTP 看不出來。剩餘空間 5.3 TB、全部影片約 7 TB，複製不可行。
- `sftp.sh` 已有 `rename`／`mkdir`／`ls`，路徑檢查（擋雙引號、反斜線、換行、tab）都已測過；撇號可通過（本次已用真伺服器唯讀驗證過）；每次連線約 0.5～1 秒。
- 動機與範圍見 proposal。

## Goals / Non-Goals

**Goals:**
- 影片位置只由成果檔名決定，全流程只有一個地方算它。
- 搬移安全：只動該動的檔、先寫清單、可還原、可續跑、絕不覆寫、搬完能對伺服器核對。
- 之後改成果檔名時，影片位置不會悄悄和目錄脫節。
- 新位置找不到時退回 `原始影片檔案位置`，讓還沒搬進正式位置的集數（新批次剛匯入、搬移前後）仍然讀得到。

**Non-Goals:**
- 不搬排除清單的 18 支，不搬開會了（`/docker` 是 root 擁有、其他人唯讀，而且有 mp4）。
- 不改 `smkul.csv`（欄位與內容逐 byte 不變）；`原始影片檔案位置` 保留給追蹤與退路用。
- 不在搬移途中刪任何東西；搬空的舊資料夾等全部驗收完才清（D11），而且只刪空的。
- 不新增批次 sftp 指令；不重寫新批次匯入時的挑檔規則（`sources.py` 保留給匯入用）。
- 不處理本機 `kithann/out` 底下已存在的舊暫存檔。

## Decisions

**D1. 位置由成果檔名推導，不新增欄位。** 位置是成果檔名的純函式，所以不必存。替代方案是在 `smkul.csv` 另加「影片檔案位置」欄：要動六張表共用的欄位規格與 22 支測試檔的 fixture，而且欄位會與實際位置漂移，要另外對帳。代價是 D6：改成果檔名時伺服器上的檔要同步搬；但改名只發生在 `relabel`／`redate` 這兩個工具，它們本來就知道舊名，推得出舊位置。

**D2. 全流程取遠端路徑只有一個出口：`episodes.py` 為每集加的 `remote` 欄。** `audio.py`、`plan_month.py`、`vision_tools/prompt.py` 以前各自套挑檔規則再接路徑，現在都讀這一欄；`remote` 由 `paths.video_path(成果檔名)` 算，是**正規位置**；它只是算出來的名字，不保證檔案在。要真正讀檔的地方（D12）再用 `video_names.locate()` 確認，必要時退回原始位置。`entry["video"]`、`entry["file"]` 兩欄仍是原始欄位的值，留作紀錄與退路。

**D3. 算位置的函式放 `scripts/news/paths.py`，從 `transcode/archive_batch.py` 搬來。** 它是流程到處都要用的東西，不該藏在處理 mxf 母帶的支線裡。`archive_batch` 留別名（`remote_archive_path` 等），值逐字相同，既有測試不用改預期。

**D4. 逐支搬，用現有 `sftp.sh rename`／`mkdir`，不新增批次指令。** 3,153 次連線約 40 分鐘，放背景跑、可續跑。替代方案是 `sftp.sh -` 一個連線搬一百支：它直接收整份批次檔、繞過 `check_path`，得自己重寫一份路徑驗證；省下的是約 40 分鐘的一次性等待，不值得為此多一條要維護的檢查。

**D5. 先探針再全部。** 探針把一支含撇號的拉阿魯哇真檔搬過去再搬回來，一次驗兩件事：跨資料夾 rename 可行（排除子卷限制）、撇號在真伺服器上也行。探針失敗就停止，回報使用者決定備案：新樹改放 `/home/mkv-raw/news/mkv/`（同一子卷內）。備案要改的只有 `VIDEO_ROOT` 一個常數。

**D6. `relabel`／`redate` 一併 rename 伺服器上的檔：伺服器那步先做，舊名稱的正規位置與原始位置都不存在才拒絕。** 先做伺服器是因為它最可能失敗（網路、權限）、失敗時本機還沒動。現在位置用 `locate()` 找：正規位置在就從那裡搬；不在但原始位置在，表示這集還沒搬進正式位置，就從原始位置搬到**新名稱的**正規位置（順便完成搬移）；兩個都不在才拒絕，這樣目錄與伺服器不會悄悄分家，新批次也不必先搬才能改名。伺服器成功後本機失敗，試著搬回舊位置再報錯，搬不回就印出現在位置。

**D7. 搬移清單放 `kithann/out/news/video-rename/<時間>.csv`（gitignore），不放 Kari-SRT。** 舊位置就是 `原始影片檔案位置`、新位置是成果檔名算出來的，兩邊都能重算，放進正本等於多一份會漂移的拷貝；清單只是這一次動作的紀錄、還原與續跑用。每組記舊位置、新位置、搬前大小（供核對）。

**D8. 工具把「怎麼對伺服器下指令」當參數傳進來，測試傳假的。** 全部測試離線；真伺服器只在 apply 階段的探針、搬移、核對三個動作碰到。

**D9. 刪 `plan_month._light_copy`。** 它是為 2021-02 的 mxf 太大而寫的（改抓同集的 mp4／mkv 轉檔）。現在每列都是單一 mkv，這段不會再被走到。`Report.skipped` 欄位保留（呼叫端還在讀），但規劃不再產生待判項目，永遠是空的。

**D10. 本機暫存檔名由來源原名變成 `<成果檔名>.mkv`。** `paths.staged_path`／`prompt.py` 取遠端路徑的 basename，路徑換了暫存檔名自然跟著變，跟 SRT、預覽檔同名；不需要另外改程式。

**D11. 搬空的舊資料夾在全部驗收完之後的最後一步清掉，只刪空的（使用者 2026-10-30 指定）。** 搬移途中與驗收期間資料夾都留著，萬一要 `undo` 還原才不必重建；等 `check` 與驗收都過了才清。刪的範圍是搬移清單裡各檔舊位置所在的資料夾與它們在 `/home/mkv-raw/` 底下的上層，由深到淺，**永遠不碰 `/home/mkv-raw` 本身**。雙重保險：先列出資料夾內容確認真的是空的才送 `rmdir`，而且 `sftp.sh rmdir` 不吞錯——伺服器遇到非空資料夾本來就會拒絕，那個失敗會直接報錯。含排除檔的資料夾自然不空，留著。預設只列出會刪哪些，要明確指定才真的刪。因為 `sftp.sh` 目前沒有 `rmdir`，要新增這個子動作。

**D12. 新位置找不到才退回 `原始影片檔案位置`（使用者 2026-10-30 指定）。** `video_names.locate(成果檔名)` 先查正規位置，伺服器回報「找不到」才查原始位置（套用匯入時的挑檔規則，因為原始欄可能有分號候選），兩個都沒有就報錯並同時指名兩個路徑；回傳實際使用的路徑、大小與來源（正規／原始）。三個真正要讀檔的接點用它：`audio.video_source`（抽音）、`opening.grab_remote` 的呼叫端（片頭補抓）、`fetch_sftp.sh`（它原本就先查大小，查不到才報 FAIL，在那裡叫一支小指令 `video_names locate` 取退路）；讀者說明文字（`prompt.py`）產生時也用它。`plan_month` 仍是離線唯讀，只列正規位置。兩個細節：
- **只有「找不到」才退。** 連線逾時、權限錯誤等其他失敗一律報錯，不退——否則網路一抖就去讀一個可能過時的位置。判斷靠 sftp 回報的「not found」。現有 `audio._remote_size` 會把所有失敗都當成「沒有」，這次一併改正。
- **退的時候要大聲說。** 輸出一行「退回原始位置：<路徑>」，不能悄悄讀。理由見風險。

**D13. `episode-sourcing`「選不出來的集數略過並回報」那一條限縮到「新批次匯入時」。** 封存前逐條核對主規格時發現：這一條原本寫「批次結束時報出、不寫入 inventory」，而批次規劃已不再挑檔、不會有「選不出來」，`inventory` 也早已不存在；不改的話主規格會描述一個已經沒有的行為。改成匯入檢查時的規則，其餘內容不變。

## 檔案樹

**第一層：Kari-SRT（資料）與伺服器**

```
Kari-SRT/
├── README.md              ✎改  補「影片在伺服器的哪裡」：位置由成果檔名推導，
│                               原始影片檔案位置欄只記交付時的原路徑
├── news/
│   ├── README.md          ✎改  同上，指向根 README
│   ├── smkul.csv          ＝不動  原始影片檔案位置欄原樣保留，逐 byte 不變
│   └── 排除影片.csv        ＝不動  18 支原地不動
└── 其餘階段目錄（1-ocr/、2-asr-*/ …） ＝不動：以成果檔名為鍵，成果檔名沒變

伺服器（不在 repo）：
/home/news/mkv/<年-月>/<成果檔名>.mkv   ★新  48 個月份資料夾、3,153 支（搬進來）
/home/mkv-raw/…                         ✎  只剩排除的 18 支；搬空的舊資料夾保留
kithann/out/news/video-rename/<時間>.csv ★新  舊→新清單（gitignore）
```

**第二層：tests/（測試）**

```
tests/
├── news/
│   ├── test_video_names.py     ★新  搬移工具：規劃、執行、探針、續跑、還原、核對、rename_episode
│   ├── test_paths.py           ✎改  新增「由成果檔名算位置」
│   ├── test_episodes.py        ✎改  新增 remote 欄
│   ├── test_audio.py           ✎改  影片來源改由 remote 欄、找不到退回原始位置
│   ├── test_opening.py         ✎改  grab-remote 先 locate
│   ├── test_plan_month.py      ✎改  規劃與待辦清單的路徑；刪 _light_copy 相關
│   ├── test_vision_prompt.py   ✎改  暫存檔名與下載指令
│   ├── test_sftp_cli.py        ✎改  補 rename 的撇號＋中文案例；新增 rmdir
│   ├── test_relabel.py         ✎改  改語別時伺服器的檔一併 rename
│   ├── test_redate.py          ✎改  改日期（可能跨月）時同上
│   ├── test_sources.py         ＝不動  挑檔規則留給新批次匯入
│   └── README.md               ✎改  補下方對照表
└── transcode/test_archive_batch.py ✎改  封存位置函式搬走後值不變
```

**第三層：scripts/（程式）**

```
scripts/
├── news/
│   ├── paths.py            ✎改  VIDEO_ROOT、video_path()、video_dir()、video_dirs_to_make()
│   ├── video_names.py      ★新  plan｜probe｜apply｜check｜undo｜prune｜locate｜rename_episode
│   ├── episodes.py         ✎改  每集加 remote 欄
│   ├── audio.py            ✎改  video_source 先用 remote、找不到才退回原始位置（locate）；_remote_size 分清「找不到」與其他失敗
│   ├── opening.py          ✎改  grab-remote 的呼叫端先 locate，remote_size 的「找不到」才退
│   ├── plan_month.py       ✎改  plan／todo／opening_todo 改用 remote（離線，只列正規位置）；刪 _light_copy
│   ├── fetch_sftp.sh       ✎改  大小表查不到某集時，呼叫 video_names locate 取退路；找不到才 FAIL
│   ├── vision_tools/prompt.py ✎改  remote_of 改用 remote；說明文字「抓 mp4」改「抓 mkv」
│   ├── relabel.py          ✎改  先 rename 伺服器檔（從 locate 到的位置搬到新名稱的正規位置）
│   ├── redate.py           ✎改  同上
│   ├── sources.py          ＝不動
│   ├── resolve_slug.py     ＝不動  server_path 仍給原始路徑、排除清單比對、開會了用
│   └── sftp.sh             ✎改  新增 rmdir 子動作（不吞錯、路徑檢查同其他子動作）
├── transcode/archive_batch.py ✎改  remote_archive_* 改成 paths 的別名
├── README.md、news/README.md  ✎改  「影片來源」「跑法」改寫
.claude/commands/smkul-news.md              ✎改  plan_month 不再用 sources 規則
.claude/commands/smkul-catalogue-import.md  ✎改  新批次匯入後多一步「搬進正式位置」
```

`video_names.py` 的動作：

```
plan   目錄 3,153 列 ─▶ (舊, 新) 3,153 組      舊＝原始影片檔案位置、新＝video_path(成果檔名)
       排除 18 支不進；擋：同舊位置兩列／同新位置兩列／不在 /home/mkv-raw
probe  一支真檔：逐層 mkdir → 搬過去 → 確認 → 搬回 → 確認
apply  先寫清單，再逐支搬；續跑：新有舊無＝跳過；舊有新無＝搬；兩邊都有＝停；都沒有＝指名
check  ls 48 個月份資料夾＋舊位置：新位置恰 3,153 支、大小同清單、舊位置只剩排除 18 支
undo   依清單反向搬；舊位置被佔用就拒絕
prune  （最後一步）清掉搬空的舊資料夾：只刪空的、由深到淺、不碰 /home/mkv-raw；預設只列出
locate 成果檔名   先查正規位置，伺服器回「找不到」才查原始位置；都沒有就報錯並指名兩處
                  連線失敗等其他錯誤不退；退回時印「退回原始位置」
rename_episode(舊名, 新名)  給 relabel／redate：從 locate 到的位置搬到新名稱的正規位置；
                            兩處都沒有就拒絕
```

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| episode-video-location | 位置只由成果檔名決定：`20210101_001_午間_Rukai_魯凱` → `/home/news/mkv/2021-01/…mkv`；年-月取自成果檔名，不取自原資料夾（48 列原資料夾月份與播出月份不同，如 20241001_275 原放在 9 月資料夾） | `test_paths.py` |
| episode-video-location | 成果檔名不合規格（空字串、集數兩碼）時拒絕算位置，不可組出沒人找得到的路徑 | `test_paths.py` |
| episode-video-location | 含撇號又含中文的名稱（195 個拉阿魯哇）：rename 批次指令兩個參數都完整保留撇號；含雙引號的路徑兩個參數都被擋 | `test_sftp_cli.py` |
| episode-video-location | 規劃對每一列產生一組（舊→新）：舊位置來自 `原始影片檔案位置`、新位置由成果檔名算；總組數等於目錄列數 | `test_video_names.py` |
| episode-video-location | 排除的影片不動：排除清單上的路徑（含與目錄所用影片串流相同的 20241002S2000.mkv）絕不出現在規劃裡 | `test_video_names.py` |
| episode-video-location | 兩列指到同一個舊檔、或算出同一個新路徑，整份規劃拒絕、一個都不搬 | `test_video_names.py` |
| episode-video-location | 只處理 `/home/mkv-raw/` 底下的列；路徑在別處（如開會了的 `/docker/…`）的列拒絕 | `test_video_names.py` |
| episode-video-location | 資料夾逐層建（`/home/news` 不存在時整句失敗）；每個月份資料夾只建一次，不是 3,153 次；已存在不算錯 | `test_video_names.py` |
| episode-video-location | 先寫清單再搬第一支：搬到一半中斷時清單已完整存在；預設只規劃，不送任何指令 | `test_video_names.py` |
| episode-video-location | 續跑：新有舊無＝跳過；舊有新無＝搬；兩邊都有＝停下不覆寫；兩邊都沒有＝指名該列 | `test_video_names.py` |
| episode-video-location | 探針：過去失敗就什麼都不再做並提示跨子卷備案；過去成功但搬回失敗，要明講檔案現在在哪 | `test_video_names.py` |
| episode-video-location | 還原：依清單反向搬；舊位置被佔用時拒絕，不覆寫 | `test_video_names.py` |
| episode-video-location | 線上核對：新位置恰為目錄每列各一支、大小與清單相同、舊位置只剩排除清單上的檔；多出或缺少的逐一指名；排除清單記的檔已不在伺服器、或不在 `/home/mkv-raw` 底下，都不算問題（真資料：22 列有 4 列搬進前就沒了、1 列在 `/docker/…`） | `test_video_names.py` |
| episode-video-location | 清空資料夾只刪空的：含排除檔的資料夾（非空）不刪；預設只列出不刪；要明確指定才真的刪 | `test_video_names.py` |
| episode-video-location | 清空資料夾由深到淺（子資料夾空了，上層才可能空），而且永遠不刪 `/home/mkv-raw` 本身 | `test_video_names.py` |
| episode-video-location | 列出時看起來是空的，但伺服器上其實有檔（列出後有人放了東西）：`rmdir` 的失敗不吞，整個停下來並指名該資料夾 | `test_video_names.py`、`test_sftp_cli.py` |
| episode-video-location | `rmdir` 子動作：路徑是獨立引數、含雙引號被擋、失敗要有非零結束碼（不像 mkdir 前面加 `-` 吞錯） | `test_sftp_cli.py` |
| episode-video-location | 正規位置在，就用它：`原始影片檔案位置` 空白或亂寫都不影響；本機已有封存 mkv 時仍優先用 | `test_audio.py`、`test_video_names.py` |
| episode-video-location | 正規位置「找不到」才退回原始位置：搬移前或新批次尚未搬的集數仍讀得到；退回時印出「退回原始位置：…」；兩處都沒有就報錯，同時指名兩個路徑 | `test_video_names.py`、`test_audio.py`、`test_opening.py` |
| episode-video-location | 連線逾時、權限錯誤這類「不是找不到」的失敗不退回，直接報錯（網路一抖就讀到過時位置是最糟的情形）；現有 `_remote_size` 把所有失敗都當成沒有，要改正 | `test_video_names.py`、`test_audio.py` |
| episode-video-location | 原始欄有分號候選時，退路依匯入時的挑檔規則選一支（不取第一條） | `test_video_names.py` |
| episode-video-location | 改成果檔名時伺服器的檔跟著 rename：跨月時月份資料夾也換；伺服器那步先做、失敗整個不動本機；正規位置沒有但原始位置還在，就從原始位置搬到新名稱的正規位置；兩處都沒有才拒絕 | `test_relabel.py`、`test_redate.py`、`test_video_names.py` |
| episode-sourcing | 執行時先用推導位置：正規位置存在時，不論目錄列有多條候選或空白，取得的都是推導位置；規劃（離線）列出的是推導位置 | `test_audio.py`、`test_plan_month.py` |
| episode-sourcing | 挑檔規則仍照舊（母帶優先、時段字樣、同名不同資料夾、一檔一集），只是留給新批次匯入 | `test_sources.py`（不動，維持綠） |
| episode-sourcing | 本機暫存檔名由 `20241202S2000.mkv` 變成 `<成果檔名>.mkv`，讀者的下載指令用新位置 | `test_vision_prompt.py`、`test_paths.py` |
| episode-video-location | 封存位置函式只有一份：搬到共用處後 `archive_batch` 算出的值與以前逐字相同 | `test_archive_batch.py` |

## Risks / Trade-offs

- **跨子卷 rename 失敗** → 探針先擋，失敗就停；備案改 `VIDEO_ROOT` 一個常數，新樹放 `/home/mkv-raw/news/mkv/`。
- **搬到一半中斷** → 清單先寫完、續跑依現況判斷、從不覆寫。
- **搬移期間程式讀不到影片** → 程式改完與搬移在同一個 change 裡做，順序是先改程式與測試、再探針、再全部搬、再核對；使用者確認目前沒有其他 session 在動，不會有人在搬到一半時讀舊路徑。
- **改成果檔名時伺服器與本機分家** → D6 的順序（伺服器先做、正規與原始位置都不存在才拒絕、失敗退回）。
- **撇號與中文在批次指令裡出錯** → 已用真伺服器唯讀驗證 ls 的回報路徑完整保留；rename 的引號規則加測試；探針用含撇號的真檔再驗一次。
- **退路讀到過時的檔**：原語會若日後在舊資料夾重新交付、重用同一個檔名（卻是別的內容），而正規位置恰好沒有，退路會悄悄讀到錯的檔 → 退回時一定印出「退回原始位置」、只在「找不到」時退、搬移完成後正規位置全數到位，退路只剩新批次匯入前後的短暫空窗；既有的位元組數比對與字幕帶驗證（`verify_band`）仍在。
- **fetch_sftp.sh 的退路只有 Python 部分有單元測試**：shell 只負責呼叫 `video_names locate`，以 `bash -n` 檢查語法，並在搬移完成前（兩處都還在）對一集真實執行確認接得上。
- **清資料夾刪錯東西** → 只刪空的（先列內容確認、`rmdir` 不吞錯）、不碰 `/home/mkv-raw` 本身、預設只列出、放在全部驗收之後。
- **約 40 分鐘的逐支搬移被別的事打斷** → 背景執行、可續跑；這段時間不要啟動其他讀伺服器的工作。

## Migration Plan

1. 先跑一遍現有測試記下基準，再逐模組先寫測試（紅）、寫程式（綠），每完成一步立刻跑對應測試。
2. 對真目錄做規劃（唯讀）：預期 3,153 組、48 個月份資料夾、0 個衝突、排除 18 支不在內，數字不符就停。
3. 探針一支含撇號的真檔；失敗就停止，回報使用者決定備案。
4. 全部搬移（背景、可續跑），接著線上核對。
5. 驗收：`rebuild --verify`、單元測試、flake8、`name_catalogue --check`，再對一集真的 `locate` 一次（確認取到新位置、來源顯示「正規」）。
6. 最後一步（驗收都過了才做）：`prune` 清掉搬空的舊資料夾；之後 `undo` 搬回的檔案要先重建資料夾，所以放在最後。
7. 回復：清資料夾之前依搬移清單 `undo` 反向搬回；`smkul.csv` 沒有被動過，不需要還原。
