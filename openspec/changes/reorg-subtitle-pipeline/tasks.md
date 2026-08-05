# reorg-subtitle-pipeline 任務

標記 `【使用者】` 的步驟含 git add／commit 等 CLAUDE.md 禁止 Claude 執行的
指令，由使用者操作（Claude 準備好指令內容）。

## 1. 前置快照（改動前的基準）

- [x] 1.1 確認無進行中工作：無 subs2srt／ingest 相關程序、C-pass 已全數匯入
      （每集 `verified.json` 覆蓋全部 cue）✓ 22 集 20,108 cue 全 verified
- [x] 1.2 對現有 `kithann/srt/*.srt` 與 `smkul.csv` 建立 SHA-256 快照清單，
      存於 change 目錄（重建驗證的 byte 基準）→ `baseline-sha256.txt`
- [x] 1.3 全 repo grep `ilrdf-srt`、`wenkao`、`/workspaces/Corpus-Cleanup`、
      `.claude/skills/video-subtitle-srt/scripts` 建立引用清單，
      作為 8.4 完成檢查的對照 → `refs-baseline.txt`（另發現 tox.ini
      2 處舊引擎路徑）
- [x] 1.4 確認 `ilrdf-srt/vision/`、`ilrdf-srt/vision-wenkao/` 仍為
      untracked（無 git 備份）：遷移全程只複製、不移動；原位置保留到
      5.2 驗證通過；第一個備份點是 4.6 的 Kari-SRT commit
      ✓ 229 檔、0 tracked

## 2. wenkao → rtf 改名（原位置，先改後搬）

- [x] 2.1 檔案改名：`wenkao.py`→`rtf.py`、`wenkao_sheets.py`→`rtf_sheets.py`、
      `compare_wenkao.py`→`compare_rtf.py`；更新彼此 import
- [x] 2.2 CLI 旗標 `--wenkao`／`--wenkao-out` → `--rtf`／`--rtf-out`；
      work dir 內 `from_wenkao.json` 改讀寫 `from_rtf.json`
      （既有檔案由 2.3 一次改名）
- [x] 2.3 一次性改名 22 個 work dir 內的 `from_wenkao.json` → `from_rtf.json`；
      `ilrdf-srt/vision-wenkao/` → `ilrdf-srt/vision-rtf/`
- [x] 2.4 更新 `ilrdf-srt/README.md` 與 `kithann/srt/wenkao-vs-vision.*`
      檔名（→ `rtf-vs-vision.*`）及文內引用
- [x] 2.5 驗證：`make_all.py` 重跑後輸出與 1.2 快照逐 byte 相同
- [x] 2.6 【使用者】commit「rename wenkao → rtf」（與 3.8 併入 745efda「refactor」）

## 3. 程式搬移與 package 化

- [x] 3.1 建立 `scripts/`、`scripts/subs2srt/`、`scripts/news/`、
      `scripts/aiyalaeho/`（僅 README 佔位）含 `__init__.py`
- [x] 3.2 引擎搬移：`cuelib.py`、`subs2srt.py`→`cli.py` 移入
      `scripts/subs2srt/`；`presets.json` 移入 `scripts/news/`；
      `match_preset()` 與 CLI 增加 preset 路徑參數（design D1）
- [x] 3.3 新增 `scripts/news/paths.py`：ROOT 由 `__file__` 推導、
      `ILRDF_CORPUS` 環境變數覆寫、提供 `--var` 查詢介面（design D2）
- [x] 3.4 `ilrdf-srt/*.py` 移入 `scripts/news/`；刪除全部
      `sys.path.insert`，改正常 package import；絕對路徑改走 `paths.py`
      （以 1.3 的 grep 清單為準，勿漏 `resolve_slug.py`、`verify_band.py`）
- [x] 3.5 `run_cues.sh`、`fetch_sftp.sh`、`sftp.sh` 移入 `scripts/news/`
      並改由 `paths.py --var` 取路徑（`fetch_sftp.sh` 的 `ROOT` 指向舊機
      workspace，目前在本機跑不起來）；清掉寫死的舊 scratchpad STAGE
      預設值
- [x] 3.6 `.claude/skills/video-subtitle-srt/SKILL.md` 改寫為說明書：
      指令範例全部指向 `scripts/`，敘明程式碼已遷出；
      `.claude/commands/smkul-news.md` 的指令路徑同步改指 `scripts/`
- [x] 3.7 驗證：`python -m scripts.news.make_all` 輸出與 1.2 快照相同；
      flake8 通過（含新的 CLAUDE.md for-loop 風格）
- [x] 3.8 刪除 `ilrdf-srt/` 內的**程式檔**與 `.claude/.../scripts/`
      （selftest.py 留待 6.x 拆完再刪）；**`ilrdf-srt/vision/`、
      `vision-rtf/` 絕不可刪**——untracked 無備份，留待 4.2 遷移、
      5.2 驗證通過後由 5.3 收尾；【使用者】commit「move
      engine+orchestration into scripts/」✓ 745edfa

## 4. Kari-SRT 資料遷移（design D3）

- [x] 4.1 撰寫 `scripts/news/migrate_kari.py`：由 `inventory.json` 生成
      slug／簡寫／攤平檔 → `srt_name` 對照，執行以下搬移
- [x] 4.2 TSV 遷移（**複製，不移動**——來源 untracked 無備份，見 1.4）：
      `vision/`、`vision-rtf/` → `Kari-SRT/vision/<srt_name>/`、
      `Kari-SRT/vision-rtf/<srt_name>/`；攤平檔拆回 `bNN.tsv`；
      對帳：TSV cue 聯集 == 各集 `verified.json` cue 集合
- [x] 4.3 work dir 撈檔：`cues.json` → `Kari-SRT/cues/<srt_name>.json`、
      `from_rtf.json` → `Kari-SRT/from_rtf/<srt_name>.json`
- [x] 4.4 交付物遷移：`kithann/srt/*.srt`、`smkul.csv`、`rtf-vs-vision.*`
      → `Kari-SRT/srt/`；`inventory.json` → `Kari-SRT/inventory.json`
- [x] 4.5 `paths.py` 增加 KARI 相關路徑；`make_all.py` 輸出目標改
      `Kari-SRT/srt/`；`ingest.py`／`batches.py` 的 TSV 預設位置改 Kari-SRT
- [x] 4.6 【使用者】在 Kari-SRT 內 commit 資料；主 repo `git submodule add`
      （remote 由使用者提供）＋ commit pointer
      ✓ 資料 commit 5650a24、pointer 已入 745edfa；`.gitmodules`
      由 Claude 補寫＋`submodule init` 註冊，待併入最終 commit

## 5. 重建驗證（design D4，spec 的可執行形式）

- [x] 5.1 實作 `python -m scripts.news.rebuild --verify`：從 Kari-SRT 資料
      在暫存目錄重組全部 SRT + smkul.csv，與 `Kari-SRT/srt/` 逐 byte 比對；
      缺件即非零退出並列名（不產出不完整交付）
- [x] 5.2 執行驗證：模擬 `kithann/out` 不存在（改名頂替）跑 `rebuild
      --verify` 全數通過，證明離線閉環
- [x] 5.3 驗證通過後刪除 `kithann/srt/`（design D7）與 `ilrdf-srt/`
      殘餘（`vision/`、`vision-rtf/` 原位置，此時 Kari-SRT 已 commit、
      有備份）；確認 `kithann/` 無任何被 git 追蹤的檔案
      ✓ 刪後 rebuild --verify 仍逐 byte 通過、kithann 0 tracked
- [ ] 5.4 【使用者】commit「retire kithann/srt; canonical data in Kari-SRT」

## 6. selftest 拆解（design D6）

- [x] 6.1 建 `tests/` 骨架（各子目錄含 `__init__.py`）；合成影片工具函數
      移入 `tests/e2e/` 共用模組
- [x] 6.2 51 個既有測試按主題拆入 `tests/cuelib/`（mask／segmenter／
      region／srt_format）與 `tests/subs2srt/`（sheets／merge_repeats／
      ocr_prep），每檔約 200 行；全數通過後刪 `selftest.py`
- [x] 6.3 e2e round-trip 移入 `tests/e2e/test_roundtrip.py`

## 7. 新增單元測試（全部離線）

- [x] 7.1 `tests/rtf/`：合成 Big5 RTF fixture 驗 decode、`is_cjk_line`、
      markup 剝除
- [x] 7.2 `tests/align/`：normalise／3-gram 投票／LIS backbone／snap／tidy；
      `test_no_interpolation.py` pin「不內插、不切旁白」教訓
      （含 `000多種的植物種類` 真實案例）
- [x] 7.3 `tests/news/test_ingest.py`：空白列補 tab、
      「cue 不在 sheet 上整批拒收」
- [x] 7.4 `tests/news/test_inventory.py`：集數／時段解析、`1100` 日期前綴
      陷阱、srt_name 格式
- [x] 7.5 `tests/news/test_gap_guard.py`：`already_read()` 拒絕覆蓋已校讀
      work dir（事故 regression）
- [x] 7.6 `tests/news/test_make_srt.py`：`drop_leader`、來源優先序、
      rebuild 缺件時的明確失敗（spec scenario）
- [x] 7.7 `tests/news/test_batches.py` 與 `tests/news/test_paths.py`
- [x] 7.8 `tests/subs2srt/test_presets.py`：preset 路徑參數化後的匹配行為

## 8. 設定與收尾

- [x] 8.1 tox：`subtitle` env → `unittest discover -s tests`（排除 e2e）、
      `subtitle-e2e` → `tests/e2e/`；flake8 涵蓋 `scripts/` 與 `tests/`
- [x] 8.2 檢查並更新 `.travis.yml`／CI 引用的舊路徑
- [x] 8.3 README 隨遷移更新：`scripts/news/README.md`（原 ilrdf-srt/
      README；修正兩處既有錯誤——slash command 名稱 `/ilrdf-month` →
      `/smkul-news`、「換機器要帶什麼」中 vision TSV「已進 git」的
      不實描述改為指向 Kari-SRT）、`Kari-SRT/README.md`（資料結構
      說明）、根 README 若有引用
- [x] 8.4 完成檢查：對照 1.3 清單，全 repo grep `ilrdf-srt`、`wenkao`、
      `/workspaces/Corpus-Cleanup`、舊 `.claude` script 路徑 → 零殘留
      （歷史文件與 change 目錄除外）
- [x] 8.5 全套測試最終執行：tox flake8 + subtitle + subtitle-e2e +
      `rebuild --verify`
- [ ] 8.6 【使用者】最終 commit（tests + config）
