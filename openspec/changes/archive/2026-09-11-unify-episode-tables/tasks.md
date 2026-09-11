## 1. 第一段：清雜訊（不動 CSV 欄位，現有逐 byte 驗法照舊通過）

- [x] 1.1 改 `tests/aiyalaeho/test_publish.py` 的 qc.json 斷言：從「有寫出來」改成「不存在」（紅）
- [x] 1.2 加 `tests/news/test_make_srt.py` 的 scenario：組裝之後 `3-srt/` 旁邊沒有同名 `.qc.json`（紅）
- [x] 1.3 拿掉 `news/make_srt.py`、`aiyalaeho/make_srt.py`、`aiyalaeho/make_all.py` 寫 `.qc.json` 的三處（綠）
- [x] 1.4 刪掉 Kari-SRT 底下 74 個 `.qc.json`（新聞 2021-02 的 35 個、開會了 39 個；2021-01 本來就沒有）
- [x] 1.5 加 `tests/news/test_redump_store.py` 的 scenario：時間軸不含絕對路徑、不含指向工作區的欄位（紅）
- [x] 1.6 `publish_one` 寫入前拿掉時間軸的 `video` 欄；一次性轉出既有 114 個 `1-cues/*.json`（綠）
- [x] 1.7 改 `tests/news/test_paths.py`：`is_refined()` 只認 `2-refined/` 存在，舊版型旗標不再是判準（紅）
- [x] 1.8 `paths.is_refined()` 簡化成一行（綠）
- [x] 1.9 刪 `scripts/news/migrate_workdirs.py` 與 `tests/news/test_migrate_workdirs.py`
- [x] 1.10 `.B.work` → `.work`：改 `gap_sheets.py`、`ingest.py`、`batches.py`、`rescan_band.py`、`blank_runs.py`、`migrate_strips.py`、`asrmt_run.py`、`paths.work_dirs()`，並把 `already_read()` 的防覆寫保護搬到合併後的單一目錄
- [x] 1.11 `tox.ini` 的 unittest 補 `tests/aiyalaeho` 佮 `tests/tools`（兩組攏無佇彼內底）；補上了後 415＋10 條本底就全綠，無舊failure
- [x] 1.12 跑第一段驗收：`rebuild --verify`（news 與 aiyalaeho）、`flake8`、`unittest` 全綠

## 2. 第二段：共用的語言代號對照表

- [x] 2.1 開 `tests/languages/__init__.py` 與 `tests/languages/test_languages.py`，寫 16 種族語別查得到代號、`太魯閣→trv-x-truku` 不可退成 `trv`、`德路固 trv-x-trk` 不可混成 `trv-x-truku`、查不到時指名（紅）
- [x] 2.2 寫代號反查：`ami-x-frng` → Amis／阿美／馬蘭，代號不在表內時指名（紅）
- [x] 2.3 建 `scripts/languages.py`，把 `LANGUAGES`、`VARIETIES`、`code_for()` 從 `aiyalaeho/catalogue.py` 搬過來並加反查（綠）
- [x] 2.4 `aiyalaeho/catalogue.py` 改成 import `scripts.languages`，`tests/aiyalaeho/test_catalogue.py` 照舊全綠
- [x] 2.5 `tox.ini` 的 unittest 補 `tests/languages`；寫 `tests/languages/README.md`（該組的 spec × scenario × 測試檔幾列）
- [x] 2.6 `tests/README.md` 的結構圖加 `languages/`，總表加一行指過去

## 3. 第三段：驗法先換（此時舊表還在，兩種驗法並存）

- [x] 3.1 寫 `tests/news/test_rebuild_sources.py` 的子集不變量 scenario：`3-srt` 有而 `1-cues` 沒有要指名該集與缺的那一層；`1-cues` 75 而 `3-srt` 40 要通過（紅）
- [x] 3.2 `news/rebuild.py` 加子集檢查，並把「要重建哪些集數」的來源從 inventory 的非 pending 改成 `3-srt/` 實際有哪些檔（綠）
- [x] 3.3 `aiyalaeho/rebuild.py` 同上（紅→綠）
- [x] 3.4 寫不變量檢查的測試：`成果檔名` 規格與唯一性、`語言別代號` 值域、`族語別` 中英一對一、素材位置欄非空、列序、孤兒檔（紅）
- [x] 3.5 實作 `scripts/catalogue_checks.py`（六張表的共同欄位＋逐列不變量），純文字語料用 `來源文字檔檔案位置` 當素材欄；**接進兩支 `rebuild.py` 移到 5.11**——表還是舊欄位，這時接上去會當場紅，順序要「先有新表再驗新表」
- [x] 3.6 跑第三段驗收：新舊驗法並存下 `rebuild --verify` 全綠

## 4. 第四段：讀取層換人（`episodes.py`）

- [x] 4.1 寫 `tests/news/test_episodes.py`：`slug` 集數補 3 碼、`播出時段` 由 `節目名稱` 推導且對不到時指名中止、`file` 不可直接 basename 分號候選清單、`pending` 由 `3-srt` 檔在不在推導（紅）
- [x] 4.2 建 `scripts/news/episodes.py`，回傳與舊 inventory 相同形狀的 entry dict（綠）
- [x] 4.3 寫 `tests/aiyalaeho/test_episodes.py`：兩張表合起來讀、沒影片的集數不在其中（紅）
- [x] 4.4 建 `scripts/aiyalaeho/episodes.py`（綠）
- [x] 4.5 把 18 個呼叫端的 `paths.load_inventory()` 換成 `episodes.load()`，`entry[...]` 一律不動
- [x] 4.6 跑驗收：兩份 inventory 還在但已無人讀，`rebuild --verify` 全綠

## 5. 第五段：資料換版

- [x] 5.1 寫一次性轉出腳本（放 change 目錄，不進 `scripts/`）：`ilrdf-corpus.csv` ＋ 既有六張表 → 新版六張表
- [x] 5.2 轉出 `news/smkul.csv`（11 欄 969 列，列序照 `成果檔名`），以不變量檢查驗過
- [x] 5.3 轉出 `aiyalaeho/smkul.csv`（9 欄）與 `smkul-字幕版型異常.csv`（9 欄，`理由` 併入 `備註`、每列非空）
- [x] 5.4 改 `news/tracker.py`：`FIELDS` 11 欄，拿掉 `cue_grade`／`asr_model`／`video_length`／`vision_status`／`skipped_status`／`is_pending`；測試先紅後綠
- [x] 5.5 改 `aiyalaeho/tracker.py`：9 欄、兩表同欄、異常表 `備註` 非空的檢查；測試先紅後綠
- [x] 5.6 改 `aiyalaeho/langcheck/report.py` 表頭為 15 欄／12 欄，前七欄取自節目目錄；測試先紅後綠
- [x] 5.7 重產 `逐條語言標記.csv` 與 `逐集語言分布.csv`，逐 byte 驗法照舊適用
- [x] 5.8 改 `aiyalaeho/text/pairs.py`：15 欄、`集`→`集數`（吃底線與連字號兩種）、補 `成果檔名`／`節目名稱`／四個語言欄、`來源檔` 兩欄改名；測試先紅後綠
- [x] 5.9 重產 `text/1-句對.csv`（55785 列）
- [x] 5.10 刪 `Kari-SRT/ilrdf-corpus.csv`、`news/inventory.json`、`aiyalaeho/inventory.json`
- [x] 5.11 把 `catalogue_checks` 的不變量檢查接進兩支 `rebuild.py`（新表就位之後）

## 6. 第六段：流程換版

- [x] 6.1 寫 `tests/news/test_publish_gate.py` 的新 scenario：視覺辨識一條都沒讀，時間軸照樣入庫（紅）
- [x] 6.2 `publish.py` 拿掉 `vision_complete` 那道門（綠）
- [x] 6.3 寫 `tests/news/test_publish_refined_only.py`：內容相同不重寫（連 mtime 都不動）、不同才覆寫、比的是 `redump_store.dump()` 正規化後的字串（紅）
- [x] 6.4 `publish_one` 加「一致不覆寫」；拿掉 `write_deliverable_tracker` 與 `clear_pending`（綠）
- [x] 6.5 `aiyalaeho/publish.py` 同步改動
- [x] 6.6 寫 `tests/news/test_plan_month.py`：跑完 Kari-SRT 一個 byte 都沒變、重跑輸出相同（紅）
- [x] 6.7 `plan_month.py` 改唯讀、吃 `smkul.csv`（綠）
- [x] 6.8 `resolve_slug.py`、`sources.py` 改吃 `smkul.csv`；測試先紅後綠
- [x] 6.9 `name_catalogue.py` 的 `--check` 改驗 `news/smkul.csv` 的 `成果檔名` 欄；測試先紅後綠
- [x] 6.10 刪 `scripts/news/add_episodes.py` 與 `tests/news/test_add_episodes.py`
- [x] 6.11 `transcode/archive_batch.py` 改成只吃 `smkul.csv`；測試先紅後綠

## 7. 第七段：語音側音檔換來源

- [x] 7.1 寫 `tests/news/test_asrmt_run.py`：影片已在本機暫存區或封存 mkv 就直接抽、都沒有才依 `原始影片檔案位置` 自遠端取、遠端也取不到時指名中止（紅）
- [x] 7.2 `asrmt_run.py` 拿掉 `mp3_remote()` 與 `_mp3_cell_path()`，改用 ffmpeg 抽音軌，取檔順序為本機暫存原檔 → 封存 mkv → 依 `原始影片檔案位置` 自 SFTP 取（綠）

## 8. 第八段：收尾與驗收

- [x] 8.1 拆掉 `rebuild.py` 裡對舊表的逐 byte 比對，只留不變量檢查；兩張語言檢查 CSV 的逐 byte 比對保留
- [x] 8.2 改 `Kari-SRT/README.md` 與各子目錄 README：欄位表、誰讀它、不再提 `inventory.json` 與節目目錄
- [x] 8.3 改 `scripts/README.md`（新增與刪除的模組）、`scripts/news/README.md`、`scripts/aiyalaeho/README.md`
- [x] 8.4 改 `.claude/commands/smkul-news.md` 與 `.claude/commands/news-stage-count.md`：流程裡的 publish 與 plan_month 行為、階段目錄的語意
- [x] 8.5 `datadirs.py` 的註解拿掉 inventory／catalogue 的指涉
- [x] 8.6 全套驗收：`rebuild --verify`（news 與 aiyalaeho）、`flake8`、`unittest`（含新補的兩組）、`name_catalogue --check` 全綠
- [x] 8.7 用 `/news-stage-count` 對一次各階段集數，確認與節目目錄推算一致
