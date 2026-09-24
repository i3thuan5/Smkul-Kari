## 1. 目錄把關與路徑

- [ ] 1.1 `tests/catalogue/test_catalogue_checks.py`（紅）：`smkul.csv` 某列素材位置是 `排除影片.csv` 的 `23NL004_174_族語晚間新聞_Paiwan.mkv` 時，檢查指名該列、排除原因「重複檔」與保留檔；目錄欄位沒有開頭斜線（`home/mkv-raw/...`）也要比對得到；`/docker/ilrdf-corpus` 舊根目錄的簡寫換算後比對；分號並列的多來源逐條比
- [ ] 1.2 `tests/catalogue/test_catalogue_checks.py`（紅）：`排除影片.csv` 某列 `同一支的保留檔` 空白時指名該列
- [ ] 1.3 實作 `scripts/catalogue_checks.py` 的排除清單檢查（綠），用 `resolve_slug.server_path()` 換絕對路徑
- [ ] 1.4 `tests/news/test_paths.py`（紅）：`EXCLUDED_STORE`（`news/排除影片.csv`）、`OPENING_STORE`（`1-ocr/片頭辨識.csv`）、`SEGMENTS_STORE`（`1-ocr/0-segments`）、work dir 的 `6-opening/`、`7-shots/`、`0-segments.csv` 各有常數或 `--*-of` 查詢
- [ ] 1.5 改 `scripts/news/paths.py`（綠）
- [ ] 1.6 `tests/news/test_fetch_sftp_config.py`（紅）：`/home/mkv-raw/113/12月/xxx.mkv` 在列檔結果裡有大小，不會被當成「伺服器頂懸無」
- [ ] 1.7 改 `scripts/news/fetch_sftp.sh` 列檔收 `.mkv`（綠）

## 2. 字幕上下位置判斷法與字幕帶下緣

- [ ] 2.1 `tests/ocr/test_sheets.py`（紅）：合成圖條字在 y 770–837（相對帶頂 48–115），跨分界 65 超過 8 列 → 退回全高；只越過 3 列 → 照舊裁偏下
- [ ] 2.2 `tests/ocr/test_sheets.py`（紅）：字在偏上，帶底 4 列是純紅（R 180、G=B=0）＋上方暗紅（R 60、G=B=0）→ 判偏上；沒宣告 `exclude` 時同一張圖判法跟現行相同；有宣告時圖條畫素逐畫素不變
- [ ] 2.3 `tests/ocr/test_sheets.py`（紅）：左側 x < 400 偏上位有「資料畫面」標籤、右側偏下有對白 → 裁偏下，標籤不讓對白被裁掉
- [ ] 2.4 `tests/ocr/test_sheets.py`（紅）：沒宣告 `straddle`／`exclude` 的 preset（`amis-titv-news`、開會了）組合圖逐畫素不變
- [ ] 2.5 實作 `scripts/ocr/sheets.py` 的 `row_slots.straddle`、`row_slots.exclude`（綠）
- [ ] 2.6 對 2022-01、2023-06～12、2024 各月抽 2 集（mkv 用 curl 只抓前 200 MB）跑 `verify_band` 量紅條上緣，結果寫進 `presets.json` 的 note 與 `by_month`
- [ ] 2.7 `tests/ocr/test_presets.py`（紅）：`titv-news-848` 的 region 下緣是 848、其餘參數跟 `titv-news` 相同；`titv-news` 下緣仍是 844；兩者都宣告 `straddle`、`exclude`；`by_month` 每個月份的值都是存在的 preset 名
- [ ] 2.8 改 `scripts/news/presets.json`（綠）：`titv-news-848`、`by_month`、`straddle: 8`、`exclude`
- [ ] 2.9 `tests/news/test_plan_month.py`（紅）：`plan_month 2024-12` 印出建議 preset `titv-news-848`；2021 月份印 `titv-news`
- [ ] 2.10 改 `scripts/news/plan_month.py`（綠）
- [ ] 2.11 `tests/news/test_verify_band.py`（紅）：2021 年紅條上緣 846 的合成剖面配 `titv-news-848` → 把關失敗

## 3. 逐秒特徵（scripts/news/shots.py）

- [ ] 3.1 `tests/news/test_shot_features.py`（紅）：左下角節目框內容換了（合成天氣框換字）仍判「框在」；框整個不見判「框不在」
- [ ] 3.2 `tests/news/test_shot_features.py`（紅）：合成畫面上方 40 列暗紅（R 30–100、G=B=0）、851 起純紅 → 紅條上緣回報 851，暗紅列不算
- [ ] 3.3 `tests/news/test_shot_features.py`（紅）：x < 480 的內容怎麼變，第二層特徵都不變
- [ ] 3.4 `tests/news/test_shot_features.py`（紅）：棚內參考格的右側虛擬螢幕區換成別的內容，色塊差中位數仍低於 0.05
- [ ] 3.5 `tests/news/test_shot_features.py`（紅）：第 t 格對應的截圖時間是 t+0.5 秒
- [ ] 3.6 實作 `scripts/news/shots.py`（綠）：逐秒 160×90 縮圖解碼、特徵寫 `7-shots/features.npz`；`judge` 子命令依秒數截 1920 寬原圖
- [ ] 3.7 從 2021、2023、2024 試做影片截參考格與單元標誌樣板，放 `scripts/news/shot_refs/<年>/`
- [ ] 3.8 用 2021（2 集，含 VS 名牌那集）、2023（182、183、176）重跑 spike，每集獨立抽 50 格人工比對，量第一層「框在不在」與整體類型準確度；未達 95% 調判準後重量，結果寫進 `scripts/news/README.md`

## 4. 段落表（scripts/news/segments.py）

- [ ] 4.1 `tests/news/test_segments.py`（紅）：同一鏡位反覆出現十幾次、沒有紅條 → 外景新聞
- [ ] 4.2 `tests/news/test_segments.py`（紅）：主播段中間 2 秒人名條不切段；人名條之後的外景不併進主播段
- [ ] 4.3 `tests/news/test_segments.py`（紅）：紅條 14 秒的段 → 判不準、列出秒數；紅條 30 秒且比中棚內參考格 → 攝影棚
- [ ] 4.4 `tests/news/test_segments.py`（紅）：2021 年 VS 名牌 50 秒、不像棚內 → 不是攝影棚
- [ ] 4.5 `tests/news/test_segments.py`（紅）：島語時間標誌出現的段 → 島語時間，單元語別照讀者回報（泰雅）而不是整集語別
- [ ] 4.6 `tests/news/test_segments.py`（紅）：中段語別牌特徵跟開頭不同 → 他族插播候選，交讀者；讀者回報排灣後段落記「他族插播／排灣」
- [ ] 4.7 `tests/news/test_segments.py`（紅）：`check()` 擋下 5 秒縫、重疊、類型「棚內」、`單元語別` 空白、`依據` 不在表列，逐項指名檔與列
- [ ] 4.8 實作 `scripts/news/segments.py`（綠）：特徵 → work dir `0-segments.csv`、判不準清單；`apply <tsv>`；`check()`

## 5. 帶外補切（scripts/news/splice.py、segment_recut.py）

- [ ] 5.1 把 `rescan_band.py` 的重切接回純函式搬到 `scripts/news/splice.py`，`rescan_band.py` 改 import；`tests/news/test_rescan_band.py` 不改照過
- [ ] 5.2 `tests/news/test_segment_recut.py`（紅）：段落表有一段島語時間 → 那段的 cue 換成用 `titv-news-island` 切的，範圍外的 cue 逐條不變、重新編號連續；補切的 cue 帶 `area`，頂層 `areas` 只列用到的
- [ ] 5.3 `tests/news/test_segment_recut.py`（紅）：時間軸已經有 `5-transcripts/` 或 `verified.json`（已讀字）時拒跑，指名改用 `rescan_band`
- [ ] 5.4 `tests/news/test_segment_recut.py`（紅）：段落表沒有帶外段落 → 時間軸逐 byte 不變
- [ ] 5.5 `tests/news/test_segment_recut.py`（紅）：補切那段沒精修就接回 → 拒絕；精修過才接
- [ ] 5.6 `tests/ocr/test_presets.py`（紅）：`titv-news-island`／`titv-news-offband` 比對欄置中（涵蓋 x 620–1300）；`titv-news-mailbox` 涵蓋 y 600–980 且宣告 `exclude`；`titv-news-montage` 涵蓋 y 690–880
- [ ] 5.7 改 `presets.json` 加四組帶外 preset（綠）；實作 `scripts/news/segment_recut.py`（綠）
- [ ] 5.8 組合圖與讀者說明照 `area` 排版與提示（`scripts/ocr/sheets.py` 讀 cue 的 `area` 取對應 preset 的比對欄）；`tests/ocr/test_sheets.py` 加一條：帶 `area` 的 cue 用置中欄裁

## 6. 片頭辨識（scripts/news/opening.py）

- [ ] 6.1 `tests/news/test_opening.py`（紅）：`grab` 對合成影片截 20／30／40 秒三格到 `6-opening/`
- [ ] 6.2 `tests/news/test_opening.py`（紅）：`--sparse` 組出的 curl 指令是 `-r 0-62914559` 與 `-r <size-16777216>-`、用 `--netrc`、指令裡沒有密碼；稀疏檔大小等於伺服器大小，不符時丟錯
- [ ] 6.3 `tests/news/test_opening.py`（紅）：`ingest` 讀到 `24NL003_160_Paiwan` 那集語別牌「賽德克」→ `與目錄相符` 為否、非零結束、列出目錄與畫面語別
- [ ] 6.4 `tests/news/test_opening.py`（紅）：三格都 `判不準` → `畫面語別牌` 記判不準、`與目錄相符` 不記相符
- [ ] 6.5 `tests/news/test_opening.py`（紅）：主播 'okay a 'ataw hayawan 不在 `主播.csv` → 列出提示、這集不擋
- [ ] 6.6 `tests/news/test_opening.py`（紅）：同一集重跑 `ingest` 覆寫同名列，檔案照成果檔名排序
- [ ] 6.7 實作 `scripts/news/opening.py`（綠）：`grab`、`sheet`、`ingest`
- [ ] 6.8 `tests/news/test_vision_prompt.py`（紅）：`--kind opening`、`--kind segments` 的讀者說明含必要規矩（語別牌只寫中文族名、判不準怎麼寫、紅條族語不收）
- [ ] 6.9 改 `scripts/news/vision_tools/prompt.py`、`brief.md`（綠）

## 7. 接進流程與入庫

- [ ] 7.1 `tests/news/test_publish_gate.py`（紅）：段落表隨時間軸入庫到 `0-segments/<年-月>/`；內容相同不重寫；`check()` 失敗時不入庫；`0-segments/` 的孤兒檔被 `rebuild --verify` 抓到；沒有段落表的集數不算缺件
- [ ] 7.2 改 `scripts/news/publish.py`、`scripts/news/rebuild.py`（綠）
- [ ] 7.3 改 `scripts/news/fetch_sftp.sh`：切 cue＋精修後、刪影片前依序跑 `opening grab` → `shots` → `segments` → `shots judge` → `segment_recut`；任一步失敗記 WARN、保留影片不刪（`.keep`），方便重跑
- [ ] 7.4 `fetch_sftp.sh` 加 `--opening-only`：只對已入庫集數跑 `opening grab --sparse`；`tests/news/test_fetch_sftp_config.py` 加一條：`--opening-only` 不呼叫 `cues`
- [ ] 7.5 `scripts/news/README.md` 補新模組與流程（`test_readme_covers_scripts` 會檢查）

## 8. 資料與文件

- [ ] 8.1 `Kari-SRT/news/README.md`（新）：`smkul.csv`、`主播.csv`、`排除影片.csv`、`1-ocr/`、`2-asr-*` 各是什麼、從哪裡做出來、誰讀它；會隨批次變動的數字指向正本
- [ ] 8.2 `Kari-SRT/news/1-ocr/README.md`：片頭辨識、段落表、cue 的 `area`；2021 年大部分集數沒有段落表是正常的
- [ ] 8.3 `Kari-SRT/news/主播.csv` 補 'okay a 'ataw hayawan（賽夏；抽聽的集 2023-06-28、07-04、08-19、2024-06-25）
- [ ] 8.4 `tests/news/README.md`（新）放本次 spec × scenario × 測試檔對照表；`tests/README.md` 總表加一行指過去
- [ ] 8.5 `kithann/TODO.md` 更新「2022–2024 新母帶」一節：24 列已核對（6 列已改）、176 已接好、帶外單元改由段落表處理
- [ ] 8.6 `.claude/commands/smkul-catalogue-import.md` 的〈sftp 路徑欄位〉改寫成已由 `server_path()` 處理；`/smkul-news` 流程加片頭辨識、段落確認兩步

## 9. 補做 2021 年

- [ ] 9.1 2021 年 660 集用 `fetch_sftp.sh --opening-only` 截三格（`274` 壞檔跳過），讀者讀片頭，`opening ingest`；不符的集數修 `smkul.csv` 並在 `備註` 寫依據
- [ ] 9.2 2021 年 15 集帶外專題：依 `TODO.md` 已知時段人工填段落表（`依據` 記人工），走 `rescan_band.py` 用 `titv-news-offband` 重切、補讀、入庫

## 10. 驗收

- [ ] 10.1 `tox -e flake8`、`tox -e unittest`、`tox -e e2etest`、`tox -e rebuild`（`rebuild --verify` 集數 ＝ inventory 裡沒標 pending 的筆數）、`name_catalogue --check` 全過

## 11. 試做 2024 年 12 月

- [ ] 11.1 2024-12 全部集數跑 `fetch_sftp.sh 2024-12 --preset <plan_month 建議>`（run_in_background），片頭辨識、段落確認、帶外補切、讀字（opus）、`ingest`、`make_srt`、`publish`，再跑 `whisper_run`；量每集從下載到 whisper 的時間、判不準格數、帶外補切段數，寫進 tuiue 報告並估整批時間；驗收同 10.1

## 12. 全部新聞影片

- [ ] 12.1 其餘月份（2021-11～2024-11，排除已完成的集數）做 1-ocr／3-srt 與 whisper，由兩個 subagent 分工：切 cue 的 subagent 依月份序 `fetch_sftp.sh` 一個月接一個月、不停，每月做完寫一行到 `kithann/out/news/logs/cut-progress.tsv`；OCR 的 subagent 每個整點被喚醒，挑切好、片頭相符、段落已確認、還沒讀字的集數做讀字（opus）→ `ingest` → `make_srt` → `publish` → `whisper_run`，做不完下一個整點接著做；全部做完後驗收同 10.1，並跑 `/news-stage-count`
