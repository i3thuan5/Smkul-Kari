# 實作步驟

每個模組先寫測試（紅）再寫實作（綠），照 CLAUDE.md 的 TDD 規定。
測試全部離線、fixture 合成。

## 1. 路徑分層的單一出口

- [x] 1.1 `tests/news/test_paths.py`：寫 `stage_path(stage, srt_name)` 的
      測試——從 srt_name 前 8 碼推出 `YYYY-MM`、組出階段目錄下的月份路徑、
      名字不合法時中止（紅）
- [x] 1.2 `tests/news/test_paths.py`：擴充 store 佈局測試——逐集階段目錄
      多一層月份，`5-report/`、`mt-cache/`、`inventory.json`、`smkul.csv`
      不分層（紅）
- [x] 1.3 `scripts/news/paths.py`：實作 `stage_path()`，階段常數降級為
      基底目錄（綠）
- [x] 1.4 `tox -e flake8`、`tox -e unittest` 通過

## 2. 來源選擇規則

- [x] 2.1 `tests/news/test_sources.py`：分號並列的多來源逐條都查得到
      （現有 bug 的回歸測試）（紅）
- [x] 2.2 `tests/news/test_sources.py`：母帶優先／檔名時段決勝／無法辨識
      的時段字樣不當成另一個時段／同名不同資料夾視為同一份（紅）
- [x] 2.3 `tests/news/test_sources.py`：剩兩條以上時回報「選不出來」與
      候選清單，不丟例外、不取第一條（紅）
- [x] 2.4 `tests/news/test_sources.py`：整批撞檔檢查——兩集選到同一支檔
      時兩集皆不選定，且與處理順序無關（紅）
- [x] 2.5 `scripts/news/sources.py`：實作逐集收斂與整批撞檔檢查，純函式、
      不做 I/O（綠）
- [x] 2.6 `tests/news/test_resolve_slug.py`（由 `test_inventory.py` 改名）：
      `load()` 以整條相對路徑為鍵、分號逐條建索引；`slugify()`／
      `srt_name()` 移入後行為不變（紅→綠）
- [x] 2.7 `scripts/news/resolve_slug.py`：改 `load()`，接收自
      `build_inventory.py` 移入的 `slugify()`／`srt_name()`（綠）
- [x] 2.8 `tox -e flake8`、`tox -e unittest` 通過

## 3. 長度記錄（完整性不自動判定）

- [x] 3.1 量測 35 集的時長分佈與位元率，判斷自動判定站不站得住——
      結論見 design D3：兩條都否決，手抄的 `TRUNCATED` dict 隨
      `build_inventory.py` 一起消失即可
- [x] 3.2 `tests/news/test_tracker_row.py`：進度表加影片長度欄，值由
      `1-cues/` 的時間軸推導；尚未切 cue 的集數留白（紅）
- [x] 3.3 `scripts/news/tracker.py`：實作長度欄（綠）；`make_all`、
      `rebuild` 兩爿取得相同的值
- [x] 3.4 `tox -e flake8`、`tox -e unittest` 通過

## 4. 月份工作單位

- [x] 4.1 `tests/news/test_plan_month.py`：指定月份的集數可跨資料夾選出；
      資料夾中不屬該月的集數不被選入（紅）
- [x] 4.2 `tests/news/test_plan_month.py`：計畫產出時該月集數已以 pending
      寫入 inventory 且帶選定路徑；重跑不重複登記（紅）
- [x] 4.3 `tests/news/test_plan_month.py`：選不出來的集數不寫入 inventory，
      並出現在略過報告；目錄標示無影片者只計總數（紅）
- [x] 4.4 `tests/news/test_plan_month_merge.py`（由
      `test_build_inventory_merge.py` 改名）：合併行為移入後不變（紅→綠）
- [x] 4.5 `scripts/news/plan_month.py`：實作計畫產出，內含自
      `build_inventory.py` 移入的 `merge()`（綠）
- [x] 4.6 `tests/news/test_add_episodes.py`：改吃 `sources.py` 的結果；
      手動指定路徑補做單集這條路仍可用（紅→綠）
- [x] 4.7 `scripts/news/add_episodes.py`：`entry_for()` 改用
      `sources.py`（綠）
- [x] 4.8 `tox -e flake8`、`tox -e unittest` 通過

## 5. 呼叫端全面改走 stage_path()

- [x] 5.1 `tests/news/` 既有測試的 fixture store 路徑加一層月份：
      `test_make_srt.py`、`test_ingest.py`、`test_batches.py`、
      `test_vision_complete.py`、`test_pending.py`、`test_tracker_home.py`、
      `test_tracker_row.py`（紅）
- [x] 5.2 `tests/e2e/fixture.py`、`tests/e2e/test_roundtrip.py`：合成
      store 加一層月份（紅）
- [x] 5.3 影像側呼叫端改走 `paths.stage_path()`：`gap_sheets.py`、
      `batches.py`、`ingest.py`、`make_srt.py`、`make_all.py`（綠）
- [x] 5.4 定版與重建改走 `paths.stage_path()`：`publish.py`、
      `tracker.py`、`rebuild.py`（綠）
- [x] 5.5 語音側呼叫端改走 `paths.stage_path()`：`asrmt_run.py`、
      `asrmt_batch.py`（綠）
- [x] 5.6 全域搜尋確認沒有殘留的舊拼法（階段常數直接 join 檔名）
- [x] 5.7 `tox -e flake8`、`tox -e unittest`、`tox -e e2etest` 通過

## 6. 搬移 Kari-SRT 資料

- [x] 6.1 搬移前先跑一次 `rebuild --verify` 並記下通過的集數，作為對照
- [x] 6.2 `git mv` 逐階段目錄加入月份一層：`1-ocr/` 的 `1-cues`、
      `2-from_rtf`、`3-vision`、`4-vision-rtf`、`6-srt`
- [x] 6.3 `git mv` 逐階段目錄加入月份一層：`2-asr/` 的 `1-words`、
      `2-entries`、`3-srt-raw`、`4-srt-ai`、`5-align`、`6-srt-complete`
- [x] 6.4 確認 `5-report/`、`mt-cache/`、`inventory.json`、`smkul.csv`
      維持原位未被搬動
- [x] 6.5 `rebuild --verify` 在新路徑通過，且集數與 6.1 相同、`6-srt/`
      逐 byte 相同

## 7. 抓檔介面切到月份

- [x] 7.1 `tests/news/test_plan_month.py`：下載清單（`todo()`）來自
      inventory 的 pending 條目、路徑為 corpus 相對、已交付的不再抓、
      別的月份不混入（紅）。註：原本寫在 `test_sftp_cli.py`，但那支測的是
      `sftp.sh` 的參數介面、與月份無關；抓檔清單這件事在 Python 這邊才測得到
- [x] 7.2 `scripts/news/fetch_sftp.sh`：改吃月份、照計畫抓；位元組數
      比對這條防線保留（綠）
- [x] 7.3 `tox -e flake8`、`tox -e unittest` 通過

## 8. 收尾

- [x] 8.1 刪除 `scripts/news/build_inventory.py`（函式已移出）
- [x] 8.2 `scripts/README.md`：`news/` 檔案表更新（新增三支、刪一支）
- [x] 8.3 `scripts/news/README.md`：現況那段會隨批次變的數字改為指向
      正本；`Kari-SRT/srt/`、`vision/` 等舊路徑更正為分層後的路徑
- [x] 8.4 `tests/README.md`：spec × scenario 表新增 `episode-sourcing`
      一區，並更新改名的測試檔
- [x] 8.5 `Kari-SRT/news/1-ocr/README.md`、`2-asr/README.md`：路徑說明
      加入月份一層
- [x] 8.6 `.claude/commands/smkul-news.md`：步驟改為「先出月份計畫、
      再抓檔」，路徑更新
- [x] 8.7 全套驗收：`tox -e rebuild`（或 `.tox/rebuild/bin/python -m
      scripts.news.rebuild --verify`）、`tox -e unittest`、`tox -e flake8`
      全部通過，且重建集數＝inventory 中未標 pending 的筆數

## 9. 真實資料驗證（不改 code，只證明規則成立）

- [x] 9.1 對 2021-01 產出計畫，確認選出 70 集、0 集待判、2 集無影片
      只計總數
- [x] 9.2 對 2021-02 產出計畫，確認已完成的 35 集不重複登記、剩下 28 集
      選出且 0 集待判
- [x] 9.3 對整份目錄產出計畫，確認待判清單與設計所述一致（2 集無法決定、
      3 組撞檔），並把清單交給使用者判定

## 10. 一集做到底（逐集流程）

- [x] 10.1 `tests/news/test_sftp_cli.py`：`put`（兩爿路徑攏檢查、順序
      LOCAL→REMOTE）佮 `mkdir`（`-` 前綴容忍「已經有」）（紅→綠）
- [x] 10.2 `scripts/news/sftp.sh`：加 `put`／`mkdir` 兩个動詞
- [x] 10.3 `tests/news/test_plan_month.py`：`--limit N` 一改干焦登記 N 集，
      略過清單袂予 limit 截斷（紅→綠）
- [x] 10.4 `scripts/news/plan_month.py`：加 `--limit`——`publish` 的
      「全批做完才定版」一字無改，改做逐擺只予伊一集通顧
- [x] 10.5 `scripts/news/fetch_sftp.sh`：來源是 `.mxf` 就留咧母帶，交予
      封存步驟；mp4 照舊切完就刣（省掉第二逝 19 GB 下載）
- [x] 10.6 `tests/transcode/test_archive_batch.py`：暫存檔名對同
      `fetch_sftp.sh`／干焦母帶封存／遠端路徑照播出月份／逐層 mkdir／
      補傳的判準（紅→綠）
- [x] 10.7 `scripts/transcode/archive_batch.py`：`--only`、`--upload-only`、
      `--no-upload`；驗證過才上傳，上傳了比位元組數，紲落才刣母帶
- [x] 10.8 `tests/news/test_asrmt_batch.py`：`--only` 指名彼集連 pending
      嘛做（逐集流程语音側佇 publish 進前）（紅→綠）
- [x] 10.9 `scripts/news/asrmt_batch.py`：加 `--only`
- [x] 10.10 `tests/news/test_asrmt_run.py`：時間軸交付了對 store 提、
      猶未交付對 `.B.work` 提，兩爿攏無就指名失敗（紅→綠）
- [x] 10.11 `scripts/news/asrmt_run.py`：`_cues_path()` 兩爿揣
- [x] 10.12 `tests/news/test_paths.py`：目錄正本徙去 `Kari-SRT/`
      頂層（跨語料，而且 `kithann/` 是 gitignore ê，換機器就無去）
