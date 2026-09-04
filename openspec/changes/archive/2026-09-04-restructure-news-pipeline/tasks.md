# Tasks: restructure-news-pipeline

## 1. work-dir 寫入端（搶時效：趕在 2021-01 批切 cue 之前）

- [x] 1.1 寫測試（紅）：`ocr cli` cues stage 把 `cues.json` 寫進 `<work>/1-cues/`；`refine_cues` 把結果寫進 `<work>/2-refined/`、`1-cues/cues.json` 逐 byte 不動；fixture 合成
- [x] 1.2 改 `scripts/ocr/cli.py`（cues 寫 `1-cues/`）與 `scripts/news/refine_cues.py`（寫 `2-refined/`，不原地改寫）讓測試綠
- [x] 1.3 `fetch_sftp.sh`、`run_cues.sh` 跟上新版面；跑 `tox -e unittest`、`tox -e flake8` 全綠
- [x] 1.4 通知使用者：寫入端已上，2021-01 批可以發動

## 1-2. `Kari-SRT/` 只收精修過的時間軸（緊接寫入端，補上 publish 的沉默分支）

- [x] 1-2.1 寫測試（紅）：publish 讀時間軸走 `cues_to_read()`（新版面的 work dir 找得到）；精修過的照常複製；只有粗切的＝指名該集、說「尚未精修」、非零離開且 store 不動；完全沒有＝指名該集、說「找不到時間軸」、非零離開
- [x] 1-2.2 改 `scripts/news/publish.py`：cues 的複製脫離 `from_rtf` 那個「沒有就 continue」的共用迴圈，換成上面三個明確結果
- [x] 1-2.3 驗收：四項全套；確認 store 內 74 份時間軸每一份都帶精修旗標

## 2. 刪除歷史目錄＋renumber（等 submodule 遷移 commit 完、verify 綠的空檔）

- [x] 2.1 寫鎖定測試（先綠，防退化）：`rebuild` 只讀單一 vision source 的重建結果＝雙 source（fixture 合成雙 source 同文字情境）
- [x] 2.2 刪 rtf 程式：`rebuild.py` 單 source、`split_cue.vision_folders()` 單 root、`publish.py` from_rtf 分支、`reread_tools/fix_rtf.py` 整支、`prompt.py` rtf 段；同步拆 `test_rebuild_sources`、`test_make_srt`、`test_pending`、`test_tracker_home`、`test_split_cue` 的 rtf 段
- [x] 2.3 刪 align 程式：`asrmt_run.py` 八個延伸步與 align import、`scripts/asrmt/align/` 整包、`tests/asrmt/align/` 整目錄；拆 `test_smkul_asr` 的 align touch；`scripts/README.md` 對照表同步
- [x] 2.4 改 `paths.py`：刪 `KARI_FROM_RTF`／`KARI_VISION_RTF`／`KARI_REPORT`／`MT_CACHE`，`KARI_VISION`→`2-vision`、`SRT_DIR`→`3-srt`；`safe_resplit.py` hardcode 跟上；`test_paths` 先改（紅）再讓它綠
- [x] 2.5 使用者執行：`git rm -r` 七個目錄、`git mv` 兩個 renumber（指令由 2.4 完成後整理給使用者）
- [x] 2.6 驗收：`rebuild --verify` 逐 byte 全過且集數＝inventory 非 pending 筆數、`unittest`、`flake8`、`name_catalogue --check`；repo 全域 grep 確認無 `3-vision`／`6-srt`／`vision-rtf`／`from_rtf`／`srt-ai`／`srt-complete` 殘留（歸檔的 change 文件除外）
- [x] 2.7 spec delta 生效後文件同步：Kari-SRT 頂層 README、`1-ocr/README.md`（歷史產物節收斂為結論摘要）、`2-asr/README.md`、`scripts/news/README.md`、`reread_tools/README.md`

## 3. work-dir 讀取端與清單守門

- [x] 3.1 寫測試（紅）：「cue 號碼當鍵」物件清單守門——`cues.json`、`sheets.json`、`transcripts.json`、`2-vision/b*.tsv` 四項，改編號的程式必須全動（用 registry 或共用函式讓測試能列舉）
- [x] 3.2 讀取端 11 支改走 `cues_to_read()` 等 helper：`make_srt`、`make_all`、`publish`、`rebuild`、`gap_sheets`、`blank_runs`、`blind_cues`、`asrmt_run`、`ocr/transcripts`、`ocr/sheets`、`ocr/cuelib`（每支：現有測試先跑紅的補測試，再改）
- [x] 3.3 `lowpri.be_nice()` 改補差額到目標值：先寫測試（模擬已 nice 過的行程，斷言不再累加），再改實作
- [x] 3.4 驗收：四項全套（rebuild --verify／unittest／flake8／name_catalogue）

## 4. 既有 work dir 遷移（等 a9 通知《開會了》整批切完）

- [x] 4.1 寫測試（紅）：遷移工具把平的 `cues.json` 搬進 `1-cues/`（已微調的搬 `2-refined/`）、冪等、不動已是新版面的 work dir
- [x] 4.2 寫 `migrate_workdirs.py` 讓測試綠；實跑核對過（news 75 个、《開會了》40 个，兩爿平版面攏賰 0 个）
- [x] 4.3 拿掉 `cues_to_read()` 的舊版面 fallback（先改測試預期，再刪碼）；四項驗收

## 5. 語音側同軸保護（TDD：檢查先紅，修到全綠）

- [x] 5.1 寫測試（紅→綠用 fixture）：同軸序列比對——兩側都在且同軸＝通過；兩側都在但 (index,時間戳) 岔開＝fail 指名該集與第一個岔點；**只有影像側、無 `3-srt-raw`＝通過且不警告**；pending 集數跳過
- [x] 5.2 把檢查併入 `rebuild --verify`；對真 store 跑一次，記錄紅名單（預期：兩側都有的集數裡 47 集不同軸，以當時 store 為準；缺語音側的不列入）
- [x] 5.3 驗證「重投影即可」：挑一集不同軸的跑 `asrmt_run --step entries` → `--step raw`，確認恢復同軸且只讀 cues＋1-words
- [x] 5.4 不同軸集數全部重投影＋重 render（離線批次，`&&` 串、`run_in_background` 發動；不重跑 vosk、不重翻譯）
- [x] 5.5 驗收：`rebuild --verify` 全綠；使用者執行 submodule commit
- [x] 5.6 `.claude/commands/smkul-news.md` 與 `2-asr/README.md` 寫明規則：兩側都有就必須同軸，語音側還沒做不算錯

## 5-2. contact sheet 改時間命名

- [x] 5-2.1 寫測試（紅）：sheet 檔名由該 sheet 首格 cue 的起始時間推導（`t<毫秒八碼>.png`）；`sheets.json` 的 sheet↔cue 對照仍正確；舊流水號檔名認得出來（比照 `stripname.is_ordinal`）
- [x] 5-2.2 改產生端（`scripts/ocr/sheets.py`／`gap_sheets.py`）讓測試綠
- [x] 5-2.3 遷移既有 work dir 的 sheet 檔名（沿用 strips 遷移的作法，冪等、前後數量核對）；`batches.py`、`reread_tools` 等讀 sheet 檔名的地方跟上
- [x] 5-2.4 四項驗收；`scripts/news/README.md` 記下改名理由與遷移數量

## 5-3. `smkul.csv` 欄位調整（加 `成果檔名`、`cues`；刪 `文稿位置`、`播出時段`；重排順序）

- [x] 5-3.1 寫測試（紅）：欄位清單與順序＝`年度, 集數, 播出日期, 節目名稱, 族語別(英), 族語別(中), 影片檔案位置, 影片長度, 成果檔名, cues, 字幕srt狀態, 語音辨識模型`；無 `文稿位置`、無 `播出時段`
- [x] 5-3.2 寫測試（紅）：`cues` 欄由 `1-cues/<年-月>/<srt_name>.json` 推導——已精修／粗切／檔不在留白；`成果檔名` 欄＝該列 `srt_name`；兩欄皆不手填（fixture 合成 store）
- [x] 5-3.3 寫測試（紅）：同一播出日期的多集（午間／晚間／晨間）各成一列且以成果檔名分辨得出來——刪時段與加成果檔名是同一步，不得只做一半
- [x] 5-3.4 改 `scripts/news/tracker.py`（`FIELDS`、列組裝、刪 `文稿位置` 與 `播出時段` 分支）讓測試綠；`inventory.json` 的同名欄位不動
- [x] 5-3.5 使用者重跑定版產生新版 `smkul.csv` 並 commit（欄位變動會使既有的表對不起來，`rebuild --verify` 要在新表落地後才會綠）
- [x] 5-3.6 驗收：`rebuild --verify` 重建出的 `smkul.csv` 與 store 內新版逐 byte 相同；四項全套；`scripts/news/README.md`、`Kari-SRT/README.md` 的欄位說明跟上

## 6. 入口三階段重整

- [x] 6.1 刪 `refine_fetch.sh`；repo grep 確認無引用
- [x] 6.2 文件重整為三階段入口（cues＝CPU／OCR＝Claude／asr＝CPU，各入口吃什麼資源、產什麼）：`scripts/news/README.md`、`.claude/commands/smkul-news.md`
- [x] 6.3 最終驗收：四項全套＋`test_readme_covers_scripts` 綠；向使用者回報完工狀態與剩餘手動步驟（若有）
