# Proposal: restructure-news-pipeline

## Why

族語新聞 pipeline 累積了三類債，各自都出過事或正在冒險：

1. **store 裡有整批已無讀者的歷史產物**。`1-ocr/` 的 `2-from_rtf/`、`4-vision-rtf/`、`5-report/` 是 2021-02 批「文稿供字」路線的遺跡（該路線已裁定廢止）；`2-asr/` 的 `4-srt-ai/`、`5-align/`、`6-srt-complete/` 與 `mt-cache/` 是 align 延伸試點（一集，語意整併效果不佳、裁定不再產）。實測 `4-vision-rtf/` 全部 4,151 條 cue 在 `3-vision/` 都有同名同文字的列，且用 `rebuild.episode_transcripts()` 有無 rtf 各跑一次、16/16 集結果相同——它是 100% 冗餘的，卻仍是 `rebuild`、`split_cue` 的第二資料源，還造成過 resplit 漏改疊層、`rebuild --verify` 才抓到的事故（2026-08-31）。
2. **work dir 的 `cues.json` 被原地改寫**。refine 跑到一半被砍會毀掉粗切時間軸（重生要重新下載 2 GB 影片）；兩個行程同開同一份 manifest 是後寫的贏，無聲。paths helper（`coarse_cues`／`refined_cues`／`cues_to_read`）已做好，寫入端與讀取端還沒切過去。
3. **語音側交付沒有檢查在守**。規格寫 `3-srt-raw` 與影像側交付 SRT 逐行同軸，實測已交付 74 集中 47 集不同軸、15 集根本沒有 `3-srt-raw`，`rebuild --verify` 完全不碰 `2-asr/`，所以爛了兩個月沒人發現。另外入口散亂：`refine_fetch.sh` 指向不存在的 `Kari-SRT/cues/`，本身就是壞的。

## What Changes

- **BREAKING（store 版面）**：刪除 `news/1-ocr/{2-from_rtf,4-vision-rtf,5-report}/` 與 `news/2-asr/{4-srt-ai,5-align,6-srt-complete,mt-cache}/`；`1-ocr/` renumber 成 `1-cues/`、`2-vision/`（原 `3-vision/`）、`3-srt/`（原 `6-srt/`），與《開會了》語料版面一致。資料的 `git rm`／`git mv` 由使用者執行。
- 刪除 rtf 相關程式：`paths.py` 三常數、`rebuild.py` 雙 source、`split_cue.vision_folders()` 第二 root、`publish.py` from_rtf 分支、`reread_tools/fix_rtf.py` 整支、`reread_tools/prompt.py` rtf 段。
- 刪除 align 延伸程式：`asrmt_run.py` 八個延伸步（dialect、mt、claude-batches、claude-ingest、seg-ingest、detect、srt、complete）、`scripts/asrmt/align/` 整包、`tests/asrmt/align/` 整目錄；`speech-subtitle-alignment` capability 整份作廢。試點集 `2-entries` 內已填的 MT 欄位原樣保留。
- work-dir cues 分階段收尾：`scripts/ocr/cli.py` 的 cues stage 寫 `1-cues/`、`refine_cues.py` 寫 `2-refined/`（不再原地改寫）；讀取端 11 支改走 helper；既有 work dir 遷移工具；遷移完拿掉 `cues_to_read()` 舊版面 fallback；「cue 號碼當鍵的物件」清單改由測試守。
- **語音側同軸保護**：`rebuild --verify` 延伸涵蓋 `2-asr/3-srt-raw/`——**兩側 SRT 都存在時**，(index, 時間戳) 序列不同＝fail 且必須修到相同；**只有影像側、語音側還沒做＝正常，不警告也不失敗**（語音側是獨立的一條線，做到哪由 `smkul.csv` 照實反映）。既有 47 集不同軸重投影＋重 render（離線，不重跑 vosk、不重翻譯）。
- **`smkul.csv` 欄位調整**：補 **`成果檔名`**（＝該集 `srt_name`，欄名與《開會了》一致，是每份交付物的定位鍵）；補 **`cues`**（該集交付的時間軸是粗切還是已精修，由 `1-cues/` 的檔推導）；刪 **`文稿位置`**（文稿路線已廢止）與 **`播出時段`**（時段已在成果檔名之內）；欄序重排成「身份 → 素材 → 進度」。新欄照既有規則「只由 store 推導、不手填」，逐 byte 重建保證不因增刪欄而破壞。刪時段與加成果檔名 SHALL 同一步完成——少了時段，`(年度, 集數, 播出日期)` 不再唯一（74 列只有 33 組日期，31 組是一天 2–3 集）。
- **contact sheet 改時間命名**：`sheets/sheet_NNN.png` 是流水號，與 strips 當初的病相同（編號會隨 cue 重編而失真）。strips 已於 2026-08-31 遷移完成（136 個 work dir 全數時間命名），本 change 把 sheet 補上：改為以該 sheet 首格 cue 的起始時間命名，`sheets.json` 仍是 sheet↔cue 的唯一對照。
- 入口重整為三階段：cues（CPU：`fetch_sftp.sh`→verify_band→切 cue→微調）、OCR（Claude：sheet 視覺辨識→ingest→組裝→publish）、asr（CPU：`asrmt_batch`）；`refine_fetch.sh` 刪除（壞的，其補救對象已處理完）。
- `lowpri.be_nice()` 改「補差額到目標值」，修 shell nice 與 Python nice 疊加到 19 的問題。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `srt-data-store`：結構樹刪三個歷史目錄並 renumber；「一個名字找齊一集」scenario 更新；離線重建輸入從「`1-cues/`＋`3-vision/`＋`4-vision-rtf/`」改為「`1-cues/`＋`2-vision/`」；新增「兩側交付都在時，時間軸必須逐條相同」requirement（缺語音側不算錯）；進度表 requirement 拿掉 align 延伸的敘述。
- `asr-bilingual-srt`：移除「條目文字行——審查版與正式版」中審查版／正式版（align 延伸）的要求與「翻譯快取與可續跑」requirement；「逐行同軸」requirement 增加驗證 scenario（納入 `rebuild --verify`）；產出存放清單縮為 `1-words/`、`2-entries/`、`3-srt-raw/`。
- `speech-subtitle-alignment`：**整份移除**（align 延伸試點裁定廢止，唯一產物已刪）。

work-dir cues 分階段與入口三階段屬 `kithann/` 工作區與程式編排，不是 store 契約，無 spec delta。

## Impact

- **Kari-SRT（使用者操作 git）**：`git rm -r` 上列七個目錄；`git mv news/1-ocr/3-vision news/1-ocr/2-vision`、`git mv news/1-ocr/6-srt news/1-ocr/3-srt`。
- **scripts/**：修改 `news/paths.py`、`news/rebuild.py`、`news/split_cue.py`、`news/publish.py`、`news/asrmt_run.py`、`news/reread_tools/prompt.py`、`news/reread_tools/safe_resplit.py`、`news/refine_cues.py`、`ocr/cli.py`、`lowpri.py`、讀取端 11 支（make_srt、make_all、publish、rebuild、gap_sheets、blank_runs、blind_cues、asrmt_run、ocr/transcripts、ocr/sheets、ocr/cuelib）、`news/fetch_sftp.sh`、`news/run_cues.sh`；刪除 `news/reread_tools/fix_rtf.py`、`asrmt/align/`（五模組）、`news/refine_fetch.sh`；新增 work dir 遷移工具、同軸檢查（併入 rebuild）。
- **tests/**：刪 `tests/asrmt/align/`；修改 `tests/news/` 的 test_paths、test_rebuild_sources、test_make_srt、test_pending、test_tracker_home、test_split_cue、test_smkul_asr；新增鎖定測試（單一 vision source 逐 byte）、同軸檢查測試、cue 鍵清單守門測試、work dir 寫入端測試。
- **文件**：Kari-SRT 頂層 README、`news/1-ocr/README.md`（歷史產物一節收斂為結論摘要）、`news/2-asr/README.md`、`scripts/README.md`、`scripts/news/README.md`、`reread_tools/README.md`、`.claude/commands/smkul-news.md`（三階段入口）。
- **平行 session 邊界**：0d 的三支（split_cue、rescan_band、migrate_strips）與 a9 的 aiyalaeho 五支各自的 session 改，不入此 change；work dir 遷移等 a9 通知《開會了》切完才掃。
- **排程限制**：task 有嚴格先後——寫入端要趕在 2021-01 批切 cue 之前；刪除與 renumber 要等 Kari-SRT 現有 staged 遷移 commit 完、`rebuild --verify` 轉綠的空檔。
