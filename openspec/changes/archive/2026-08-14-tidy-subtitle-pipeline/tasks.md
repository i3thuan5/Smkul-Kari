驗收指令（`tox` 不在 PATH 時用括號內那條）：

- 單元測試 `tox -e subtitle`（`.tox/subtitle/bin/python -m unittest discover -s tests/<pkg> -t .`）
- 離線重建 `tox -e subtitle-rebuild`（`.tox/subtitle-rebuild/bin/python -m scripts.news.rebuild --verify`）
- 風格 `tox -e flake8`

**每一組結束都要三條全綠，而且 `git -C Kari-SRT status` 必須乾淨。**

**驗收一律用推導的，不要記死數字。** 別的 session 隨時可能在做影片，集數會在重構
期間變動（寫這份計畫時是 35 集，隨時可能變成 48）。所以驗收條件是
「`rebuild --verify` 通過，且它報的集數 ＝ store inventory 中非 pending 的筆數」，
不是「跟開工時一樣是 N 集」。記死數字會在別人做完一批之後變成假紅燈——那正是本次
要修的三個缺陷的同一種錯誤。

**每一組開工前先跑**，與上一組結束時不同就先重讀受影響的檔案：

```bash
git log --oneline -1
git -C Kari-SRT log --oneline -1 && git -C Kari-SRT status --short
```

**第 0–2 組要連續做完，開工前先跟使用者確認這段期間不開新批次**——`pending` 機制
還沒建好，這期間有人跑 `add_episodes` 會讓 `rebuild --verify` 立刻紅，而第 1 組
還會刪掉一個別人正在寫的檔。第 2 組一落地就可以跟做影片並行。

## 0. 先讓安全網在整段重構期間都能綠

- [x] 0.1 確認起點乾淨：三條驗收指令全綠、`git -C Kari-SRT status` 乾淨、`rebuild --verify` 報的集數 ＝ store inventory 筆數 ＝ `Kari-SRT/srt/smkul.csv` 列數（三者相等即可，不記絕對值）；並與使用者確認第 0–2 組期間不開新批次
- [x] 0.2 新增 `scripts/news/tracker.py`，把 `FIELDS`／`tracker_row()`／`write_tracker()` 從 `make_all.py` 搬過去（純搬移）
- [x] 0.3 `make_all.py`／`publish.py`／`rebuild.py` 改 `from scripts.news import tracker`，不再為了 tracker 而 `import make_all`
- [x] 0.4 `paths.py` 新增進度表快取路徑常數（`kithann/out/` 之下）
- [x] 0.5 `make_all.main()` 改把 `smkul.csv` 寫進快取路徑，不再寫 `Kari-SRT/srt/`；結束時印出該路徑
- [x] 0.6 `publish.py` 用 `tracker.write_tracker()` 把 `smkul.csv` 定版寫進 `Kari-SRT/srt/`
- [x] 0.7 補測試：`make_all` 不碰 store 的 `smkul.csv`；`publish` 才寫它
- [x] 0.8 驗收三條全綠

## 1. `inventory.json` 遷入 Kari-SRT（純搬檔）

- [x] 1.1 **前置檢查，不可略過**（這是唯一會毀掉別人工作的一步）：兩份 inventory 逐字相同、`git -C Kari-SRT status` 乾淨、且沒有任何集數處於「已登記但未校讀完成」。任一項不符就是有人正在做，停下來協調，不要硬刪
- [x] 1.2 `paths.INVENTORY` 改指 `Kari-SRT/inventory.json`；刪除 `scripts/news/inventory.json`
- [x] 1.3 `grep -rn inventory.json scripts/` 確認沒有殘留的硬編路徑；`run_cues.sh` 透過 `paths --var INVENTORY` 取值，確認仍正確
- [x] 1.4 `publish.py` 移除 `copy2(paths.INVENTORY → Kari-SRT/inventory.json)` 那行（來源與目的地已是同一個檔）
- [x] 1.5 `build_inventory.py` 加防護：改為合併式（不刪既有條目），或要求明示旗標才整份重寫；預設不得覆蓋 `add_episodes` 登記的集數
- [x] 1.6 補測試：`build_inventory` 預設不會移除既有條目
- [x] 1.7 驗收三條全綠；`git -C Kari-SRT status` 必須乾淨（這一組不該動到 store 的內容）

## 2. `pending` 語意與 `publish` 整批把關

- [x] 2.1 先寫會紅的測試：inventory 內有 `pending` 集數時，`rebuild --verify` 應跳過它們並通過；且該集數不出現在重建的 `smkul.csv` 裡
- [x] 2.2 `rebuild.check_inputs()` 與 tracker 列產生流程跳過 `pending` 集數；確認 2.1 轉綠
- [x] 2.3 先寫會紅的測試：未標記 `pending` 的集數缺件時仍須失敗（`pending` 不得成為繞過缺件檢查的手段）
- [x] 2.4 `add_episodes.py` 新增條目時寫入 `"pending": true`（含取代 `truncated` 條目的那條路徑）
- [x] 2.5 先寫會紅的測試：有 `pending` 集數未校讀完成時，`publish` 應中止且不寫任何檔案
- [x] 2.6 `publish.main()` 改成先整批把關（每個 `pending` 集數皆須校讀完成），全數通過才進入寫入階段；寫入時清除 `pending` 旗標；失敗時列出集數並回非零
- [x] 2.7 `make_all` 產出的快取進度表列出含 `pending` 在內的全部集數與各自狀態
- [x] 2.8 驗收三條全綠

## 3. 另外兩個缺陷，加一條回歸測試

- [x] 3.1 補回歸測試（`da2f0b3` 已修，但無測試）：`.work/transcripts.json` 不存在而 `.B.work` 校讀完成時，`make_one` 應產 SRT 而非回「待處理」
- [x] 3.2 先寫會紅的測試：`auto` 子命令傳入 `--preset`／`--presets` 時，`stage_cues` 應收到；另加結構性測試斷言 `auto` 的參數集合 ⊇ `cues` 的參數集合
- [x] 3.3 `cli.stage_auto()` 改由 `vars(args)` 衍生 Namespace 後覆寫必要欄位，不再手抄清單；確認 3.2 轉綠
- [x] 3.4 動手前重跑唯讀檢查：掃當下 inventory 內每一集，確認校讀紀錄的編號集合都落在 cues 編號集合內（design.md 寫的是當時 35 集的結果，期間可能有新批次）
- [x] 3.5 先寫會紅的測試：校讀紀錄筆數足夠但含不屬於該集的編號時，`vision_complete` 應回 False
- [x] 3.6 `make_all.vision_complete()` 改比對編號集合；確認 3.5 轉綠
- [x] 3.7 驗收三條全綠；另跑 `publish --check`，確認「ready 的集數 ＋ pending 未完成的集數 ＝ inventory 筆數」，且改嚴 `vision_complete` 之後沒有任何原本 ready 的集數變成未完成

## 4. 刪除文稿路徑

- [x] 4.1 刪 `scripts/news/align.py`、`rtf.py`、`rtf_sheets.py`、`compare_rtf.py`、`check_align.py`
- [x] 4.2 刪 `tests/align/`、`tests/rtf/`；`tox.ini` 的 `subtitle` env 移除這兩個 discover 行
- [x] 4.3 `make_srt.py` 移除 `--rtf`／`--rtf-out` 參數、`build()` 的 aligner 分支、`entries_from(records, "rtf")` 這條與 qc 內的 `interpolated`／`rtf_chars`／`rtf_srt_lines` 欄位
- [x] 4.4 `make_all.py` 移除 rtf 分支與 `RTF_DIR`
- [x] 4.5 `gap_sheets.py` 移除 `--no-rtf` 旗標與 aligner 呼叫，改為一律把全部 cue 放上 sheet；`from_rtf.json` 仍寫出但恆為 `[]`
- [x] 4.6 確認 `paths.py` 內 `KARI_FROM_RTF`／`KARI_VISION_RTF` 保留（rebuild 與歷史索引需要），只清掉真正無人使用的常數
- [x] 4.7 驗收三條全綠——特別確認 `rebuild --verify` 仍逐 byte 相同（aligner 本就不參與重建，變紅代表刪過頭）
- [x] 4.8 刪除 commit `4e12851`「程式重整理」；其 parent `da2f0b3` 即最後一個含比較程式的版本，文件已指向它

## 5. 拆 `cli.py`（嚴格純搬移）

- [x] 5.1 建 `scripts/subs2srt/detect.py`：搬 `load_presets`、`match_preset`、`detect_band`、`region_from_profile`、`merge_bands`、`split_lines`、`probe_or_die`、`grab_frame`、`grab_burst`、`stable_text_mask`
- [x] 5.2 建 `scripts/subs2srt/sheets.py`：搬 `LABEL_FONT`、`ink_bbox`、`build_sheets`、`flush_sheet`
- [x] 5.3 建 `scripts/subs2srt/ocr.py`：搬 `TESS_COMMON`、`prep_for_tesseract`、`run_tesseract`、`clean_text`、`ocr_tesseract`、`ocr_claude_api`、`default_prompt`
- [x] 5.4 建 `scripts/subs2srt/assemble.py`：搬 `read_manifest`、`load_transcripts`、`merge_repeats`、`apply_gap_rules`、`parse_transcript_tsv`、`glossary_tokens`、`SPECIAL_MARKS`、`VERIFIED_NAME`、`load_verified`、`save_verified`
- [x] 5.5 `cli.py` 只留 9 個 `stage_*` 與 `build_parser`／`add_srt_options`／`add_cue_options`／`main`，改 import 新模組
- [x] 5.6 下游改 import：`make_srt.py` → `assemble`；`gap_sheets.py` → `sheets`；全 repo 不再有為了拿純函式而 `import cli` 的地方
- [x] 5.7 `tests/subs2srt/` 隨拆檔更新 import；`tox.ini` 若需新增 discover 路徑一併補
- [x] 5.8 用 `git diff --stat` 核對：新檔行數合計與原 `cli.py` 相符（差額只該來自 import 行與模組 docstring）
- [x] 5.9 驗收三條全綠

## 6. 拆 Python 內部的 subprocess

- [x] 6.1 先補測試：`ingest` 的匯入路徑端對端（造小 work dir → 匯入 TSV → 斷言 `transcripts.json` 與 `verified.json` 內容），這段目前完全沒覆蓋
- [x] 6.2 `assemble.py` 新增 `import_tsv(work, source, replace=False)`，把 `cli.stage_import` 的核心搬進去；`stage_import` 改為呼叫它
- [x] 6.3 `ingest.py` 改直接呼叫 `assemble.import_tsv()`，移除 subprocess 與 `PY`
- [x] 6.4 `make_srt.py` 抽出 `run(work, out, ...) -> qc dict`；`main()` 只做 argparse、寫 `.qc.json`、印 JSON
- [x] 6.5 `make_all.make_one()` 改直接呼叫 `make_srt.run()`，移除 subprocess、stdout 解析與 80 字截斷的錯誤處理
- [x] 6.6 `rebuild.rebuild_one()` 同上
- [x] 6.7 確認 `paths.VENV_PY` 的使用者只剩 `fetch_sftp.sh:23` 與 `run_cues.sh:23`（`grep -rn VENV_PY`），本次**不動它**；理由見 design.md D6
- [x] 6.8 驗收三條全綠；另確認 `rebuild --verify` 現在全程在同一個直譯器內完成

## 7. 文件與收尾

- [x] 7.1 `scripts/news/README.md`：改寫文稿章節為「已於 commit `<sha>` 移除，其 parent 為最後一個含比較程式的版本」；更新檔案表（刪 5 支、加 `tracker.py`）；更新流程步驟（`--no-rtf` 已成唯一行為、`inventory.json` 在 Kari-SRT、`pending` 的意思、`smkul.csv` 由 `publish` 定版）
- [x] 7.2 `.claude/commands/smkul-news.md` 與 `.claude/skills/video-subtitle-srt/`：同步文稿路徑的移除與新的流程順序
- [x] 7.3 `README.md` 的「換機器要帶什麼」一節更新：`inventory.json` 已隨 submodule 走，不必另外搬
- [x] 7.4 決定 `migrate_kari.py` 的去處（`oneoff/` 或原地標註），依 design.md Open Questions
- [x] 7.5 決定是否在 `CLAUDE.md` 補 tox fallback 指令，依 design.md Open Questions
- [x] 7.6 全套最終驗收：三條指令全綠、`git -C Kari-SRT status` 乾淨、`rebuild --verify` 報的集數 ＝ store inventory 中非 pending 的筆數 ＝ `smkul.csv` 列數（推導比對，不比對開工時的數字）
