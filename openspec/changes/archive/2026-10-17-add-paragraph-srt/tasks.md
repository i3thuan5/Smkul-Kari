## 1. 組的時間與補洞（scripts/mt/overlap.py）

- [x] 1.1 test_overlap.py 先寫紅：span 只看語音段（055 撒奇萊雅 27.6 秒字幕那種：字幕比語音早 5 秒開始，span 的開始是語音的開始）；相鄰兩組不重疊、剛好相接算相接
- [x] 1.2 test_overlap.py 先寫紅：補洞（拉阿魯哇 003 晨間那種：長字幕蓋住的幾段短語音各不到 10%，補進頭尾之間那一組）；組外的落單段不補；被補的段從 lonely 清單拿掉
- [x] 1.3 test_overlap.py 先寫紅：配對看真實邊界——前一段 10.0 結束、後一段 10.8 開始、字幕 10.1–12.0 只歸後一段、不合併
- [x] 1.4 改 overlap.span、max_overlap_groups，1.1–1.3 轉綠
- [x] 1.5 test_overlap.py 先寫紅：padded_spans——不採用組限制延伸（10.0／10.4 → 兩邊都 10.2）；落單段限制延伸（19.8／20.0 → 19.9）；相接延伸 0；夾在 0 與音長之間；延伸前範圍重疊就指名中止
- [x] 1.6 寫 overlap.padded_spans（整集語音排成一條時間軸交給 srtlib.assemble.pad_edges），1.5 轉綠
- [x] 1.7 跑 tests/mt 全部，修補洞連帶影響的 tuning、features、goldalign 測試 fixture（只修 fixture 與期望值，不改調參結論）
- [x] 1.8 test_pairs.py 先寫紅：row 寫的是呼叫端傳入的時間（不自己呼叫 span）；補洞後族語照時間順序接、語音段數跟著變
- [x] 1.9 改 pairs.row 的簽名，1.8 轉綠

## 2. 雙語字幕引擎（scripts/mt/paragraph_srt.py）

- [x] 2.1 新開 tests/mt/test_paragraph_srt.py 先寫紅：輸入是 CSV 列；不採用組不進 SRT、編號連續；時間照抄 CSV（不採用組 10.4、高信心 10.0 結束時，SRT 是 CSV 的 10.2，不是重算的 10.5）；兩行標籤、文字跟 CSV 逐字相同；沒有高中信心組就是空檔；逐 byte 可重現
- [x] 2.2 寫 scripts/mt/paragraph_srt.py（CSV 列 → SRT 字串），2.1 轉綠

## 3. 目錄改名與整批（scripts/news/paths.py、pairs_run.py）

- [x] 3.1 test_paths.py 先寫紅：PAIRS_DIR 指 2-asr-whisper/2-csv-analysis、PARAGRAPH_SRT 指 2-asr-whisper/3-srt-paragraph、LEGACY_PAIRS_DIR 指 2-平行語料
- [x] 3.2 改 paths.py，3.1 轉綠
- [x] 3.3 test_run.py 先寫紅：寫到 2-csv-analysis；同一輪寫出 3-srt-paragraph、SRT 文字與時間跟 CSV 逐字相同；舊目錄還在就指名中止；辨識紀錄.csv 沒有該集或音長秒空白就指名中止
- [x] 3.4 test_run.py 先寫紅（兩種時間拿錯）：CSV 寫延伸後的時間（30.0–40.0、鄰居在 2 秒外 → 29.5–40.5）；開場組看真實語音開始（真實 90.3／延伸 89.8 不算，真實 89.8／延伸 89.3 算；89 秒字幕、91 秒語音不算）；features 的 duration 是真實的 10.0 不是 11.0；空隙裡的字幕整批跑下來也不合併
- [x] 3.5 改 pairs_run.py（讀音長；episode_csv 算 padded_spans 傳給 pairs.row；SRT 用同一批列；opening_samples 只用 span），3.3、3.4 轉綠

## 4. 重建驗證與改語別（scripts/news/rebuild.py、relabel.py）

- [x] 4.1 test_rebuild_pairs.py 先寫紅：3-srt-paragraph 原樣逐 byte 通過、手改一個字指名該集；3-srt-paragraph 有、2-csv-analysis 沒有要指名；還沒產的不算錯；舊目錄並存要失敗並指名；辨識紀錄.csv 缺音長要指名該集，不可宣告通過
- [x] 4.2 改 rebuild.py（pairs_problems 一次比兩層、pairs_containment 加 3 ⊆ 2、舊目錄偵測），4.1 轉綠
- [x] 4.3 test_relabel.py 先寫紅：改語別後 3-srt-paragraph 那集也刪、2-csv-analysis 用新目錄名
- [x] 4.4 改 relabel.py 的 REMOVE，4.3 轉綠

## 5. 交件與抽查（scripts/news/paragraph_export.py）

- [x] 5.1 新開 tests/mt/test_paragraph_export.py 先寫紅（從 test_bilingual_srt.py 搬交件、抽查那幾條並改寫）：--export 從 Kari-SRT 複製 SRT 與 CSV、清單的條數＝高＋中、時長用 CSV 時間（含留白）；抽查只抽高信心、同種子同一批；核對 CSV 跟重算的組時比的是延伸後的時間——正常的 CSV 要通過（拿真實時間比會全部判錯）、手改過的要拒絕；指定月份沒有集數要中止
- [x] 5.2 寫 scripts/news/paragraph_export.py，5.1 轉綠
- [x] 5.3 刪 scripts/news/bilingual_srt.py、tests/mt/test_bilingual_srt.py；pairs_tune.py、tier.py 註解裡的目錄名改成 2-csv-analysis

## 6. 文件

- [x] 6.1 scripts/README.md（mt/ 表加 paragraph_srt、改 overlap；news/ 表改 pairs_run、加 paragraph_export、刪 bilingual_srt）、scripts/mt/README.md
- [x] 6.2 tests/README.md 總表、tests/mt/README.md 對照表（照 design 的 spec × scenario × 測試檔表改寫 overlap、pairs、run 幾列，加 paragraph_srt、paragraph_export 兩列，刪 bilingual_srt 那列）
- [x] 6.3 跑 tox -e flake8、tox -e unittest 全過（含 test_readme_covers_scripts）

## 7. 資料搬移與重產（Kari-SRT）

- [x] 7.1 用 ps 括號寫法（`pgrep -f '[p]airs_run'`、`'[w]hisper_run'`）確認沒有行程在寫平行語料，再把 Kari-SRT/news/2-asr-whisper/2-平行語料/ 用一般 mv 改名為 2-csv-analysis/
- [x] 7.2 pairs_run 整批重產 CSV 與 SRT（不下 --recalibrate），確認 校正基準.csv 逐 byte 不變
- [x] 7.3 寫一個 scratchpad 小腳本比對新舊 CSV（舊版從 git HEAD 讀）：每集組數相同、時間兩欄變、其他欄只在補洞的組變；數出信心層級變動的組數
- [x] 7.4 重跑 tools/mtgold/sweep.py，取 10% 那列的正確率與詞召回；跟 93.7%／0.545 差超過 1 個百分點就停下來報告，否則更新 README
- [x] 7.5 2-csv-analysis/README.md：時間定義改成語音段再延伸 0.5 秒（鄰居是全部語音段、真實邊界去 1-srt-sapolita 查）、刪「相鄰兩組會重疊」那段改成不重疊、加補洞一節、可信度與開會了表換新數字、註明調參是補洞前量的；檔案表、離線重建、包含規則改新目錄名
- [x] 7.6 寫 3-srt-paragraph/README.md（從 CSV 挑高中信心、時間照抄 CSV 已含延伸、誰讀它）；改 2-asr-whisper/README.md、news/README.md、Kari-SRT/README.md 的目錄名與流程圖

## 8. 驗收

- [x] 8.1 tox -e rebuild（rebuild --verify）通過，集數＝目錄裡沒標 pending 的筆數，且平行語料與 3-srt-paragraph 的集數相同
- [x] 8.2 python3 -m scripts.news.name_catalogue --check 通過；tox -e unittest、tox -e flake8 全過
- [x] 8.3 用 paragraph_export --export 2021-01 2021-02 產一份到 kithann/out，跟補件版比：條數跟補件版（7,735）的差只來自補洞那些組的層級變動；不含留白的語音時長約 44.98 小時（explore 量的，補洞前），差異同樣只能來自那些組
- [x] 8.4 回覆檔寫到 kithann/tuiue/<MMDD>/，列出可以 git add 的檔案（主 repo 與 Kari-SRT 分開），以及要通知 whisper 那條線的事
