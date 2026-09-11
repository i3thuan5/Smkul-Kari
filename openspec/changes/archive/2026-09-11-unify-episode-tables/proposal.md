## Why

`Kari-SRT/` 現在有三份東西在記「有哪些集數」：外部給的節目目錄 `ilrdf-corpus.csv`（1029 列）、兩份 `inventory.json`（133 + 44 筆）、和六張各自長不一樣的 CSV。三份講同一件事，而且**每一份的欄位順序、欄位命名都不同**，join 不起來，人也看不出哪一份是正本。

同時 `news/smkul.csv` 的列序是登記順序不是排序過的（現在第 1 列是 2021-02-01、最後 1 列是 2021-01-06），所以每加一批就整檔重寫——實測改動史四次都是全檔重寫（75/75、36/36、36/36、73/34），diff 讀不出來到底改了什麼。

處理進度已經有 `/news-stage-count` 可以從檔案系統數出來，不必用 CSV 記。所以：**目錄與交付表合一，CSV 只記「有哪些素材」，進度交給檔案系統。**

## What Changes

**BREAKING**：`Kari-SRT/` 的六張 CSV 全部換欄位，兩份 `inventory.json` 與 `ilrdf-corpus.csv` 刪除。舊的欄名與檔案路徑都不再存在。

### 資料

- **刪 `Kari-SRT/ilrdf-corpus.csv`**（14 欄 1029 列），欄位分配到六張表
- **刪 `Kari-SRT/news/inventory.json`（133 筆）與 `Kari-SRT/aiyalaeho/inventory.json`（44 筆）**——量過每一欄都推導得出來，零例外：`slug` 由 `年度_集數3碼_播出日期_播出時段_族英_族中` 組出（133/133）、`file` 是 basename(`原始影片檔案位置`)（133/133）、`pending` 等於 `3-srt/<成果檔名>.srt` 在不在（133/133）；aiyalaeho 那 44 筆對兩張 smkul 表零處對不上
- **刪 74 個 `.qc.json`**——零個生產程式讀它，`rebuild --verify` 也不比對，74 個檔合計 9974 bytes，5 個數字都算得回來
- **`1-cues/*.json` 拿掉 `video` 欄**——114 個檔全是絕對路徑（`/workspaces/Smkul-Kari/kithann/out/stage/…`），把 Kari-SRT 的內容綁在一台機器上
- **六張 CSV 統一前七欄**：`成果檔名`／`節目名稱`／`集識別`／`族語別(英)`／`族語別(中)`／`語言別`／`語言別代號`，任兩張都 join 得起來
- **`news/smkul.csv` 12 欄 75 列 → 11 欄 969 列**，列序照 `成果檔名` 排；涵蓋全部集數（含還沒做的），沒影片的 14 列不進表
- 拿掉的欄位：`影片長度`、`cues`、`字幕srt狀態`、`語音辨識模型`、`有無影片`、`音檔位置(mp3)`、`音檔位置(wav)`、`文稿位置`、`播出時段`（由 `節目名稱` 完全決定，983 列零例外，且已在 `成果檔名` 裡）
- 改名：`影片檔案位置`→`原始影片檔案位置`、`語言代號`→`語言別代號`、`本集族語`→`族語別(中)`、`srt_name` 併入 `成果檔名`、`理由` 併入 `備註`、`集`→`集數`、`來源檔`→`來源文字檔檔案位置`、`來源檔編碼格式`→`來源文字檔編碼格式`

### 流程

- **分階段入庫**：`1-cues`、`2-vision`、`3-srt` 各自做完就可以進 Kari-SRT，不必等整集做完。`publish` 拿掉「視覺辨識全讀完」那道門（`2-vision`、`3-srt` 本來就是各自直接寫進去的）
- **`publish` 只剩一件工作**：把精修過的時間軸放進 Kari-SRT；內容一致就不覆寫，不同才覆寫。不再寫 `smkul.csv`、不再清 `pending`
- **`plan_month` 變唯讀**：列出某月有哪幾集，不寫任何檔
- **語音側音檔改從該集影片抽音軌**，不再另記音檔路徑。影片正本在 SFTP，取音軌時依序找本機暫存原檔、封存 mkv，都沒有才依 `原始影片檔案位置` 取檔——與切 cue 同一條路。量過 mp3 那一欄推導不出來的有 148/983（15%）
- **`rebuild --verify` 的 CSV 部分從「逐 byte 重算比對」改為「不變量檢查」**——表變成輸入而非輸出，逐 byte 比對失去意義。SRT 那邊的保證完全不動

### 程式

- 新增 `scripts/languages.py`（族語別／語言別代號對照表，兩側共用）、`scripts/news/episodes.py`、`scripts/aiyalaeho/episodes.py`
- 刪除 `scripts/news/add_episodes.py`、`scripts/news/migrate_workdirs.py`
- `<slug>.B.work` → `<slug>.work`（`.B` 是已廢除的「第一輪用文稿供字」留下的字母，A 輪不存在了）
- `paths.is_refined()` 簡化成一行（舊版型的 fallback 已無來源）
- `tox.ini` 補跑 `tests/aiyalaeho` 與新的 `tests/languages`（現在 `tox -e unittest` 沒跑到《開會了》的測試）

## Capabilities

### New Capabilities

- `episode-catalogue`：一集一列的節目目錄與交付表合一——六張 CSV 的共同欄位區塊、`成果檔名` 的推導與唯一性、列序、沒影片就不進表、`語言別代號` 的值域與落法

### Modified Capabilities

- `srt-data-store`：節目目錄正本那條需求整條移除；`inventory.json` 不再是重建輸入；`smkul.csv` 從衍生表變輸入表，驗證方式改為不變量檢查；新增分階段入庫與子集不變量 `3-srt ⊆ 2-vision ⊆ 1-cues`；`1-cues` 不再帶 `video`；`.qc.json` 不再產出
- `episode-sourcing`：來源候選清單改由 `news/smkul.csv` 提供；「登記先於抓檔」那條的 pending 機制消失，`plan_month` 變唯讀
- `aiyalaeho-sourcing`：「SHALL NOT 讀 `ilrdf-corpus.csv`」的理由消失（檔案不存在了）；`pending` 標記消失；兩張表欄位相同，異常表以 `備註` 非空區別
- `aiyalaeho-language-check`：兩張 CSV 的欄位改為 15 欄／12 欄，`本集族語` 改名
- `aiyalaeho-text-corpus`：`1-句對.csv` 15 欄；`集` 拆成 `集數` 並補 `成果檔名`；該表的 `成果檔名` 指向不存在的 SRT，不變量須放行
- `asr-bilingual-srt`：音檔來源從目錄記載的 mp3 路徑改為該集影片抽出的音軌，影片依 `原始影片檔案位置` 取得

## Impact

**資料**：`Kari-SRT/` 六張 CSV、114 個 `1-cues/*.json`、刪 3 類檔案（目錄、兩份 inventory、74 個 qc.json）。

**程式**：新增 3 支、刪除 2 支、修改約 25 支，橫跨 `scripts/`（頂層）、`scripts/news/`、`scripts/aiyalaeho/`、`scripts/transcode/`。引擎層 `scripts/ocr/`、`scripts/srtlib/`、`scripts/asrmt/` 不動。

**測試**：新增 3 支測試檔、修改約 17 支、刪除 1 支、新增 `tests/languages/` 一組，`tox.ini` 加兩行。

**風險**：`rebuild --verify` 是唯一的把關（Kari-SRT 是私人 repo，CI 抓不到），而這個 change 同時改「被驗的資料」和「驗的方式」，中間沒有綠燈狀態可以退。任務順序要讓每一步都跑得完驗收。
