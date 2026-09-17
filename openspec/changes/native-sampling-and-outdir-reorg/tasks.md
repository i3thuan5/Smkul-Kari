## 1. 前置確認

- [x] 1.1 確認切 cue 已經全部做完（8 月與 9 月兩條線都收工、沒有還在跑的集數）；還在跑就等它跑完，不要在批次寫入 work dir 的時候動結構
- [x] 1.2 確認已切好的集數 OCR 全部讀完並入庫（`7–9月完成 N／N`），還沒讀完的先讀完
- [x] 1.3 逐個 work dir 檢查有沒有半成品（有 `1-cues/` 卻沒 `3-refined/`、有組合圖卻沒讀完、TSV 只有一批等），把集數與狀況記進 `kithann/TODO.md`
- [x] 1.4 跑一輪收尾（組 SRT、`rebuild --verify`、`name_catalogue --check`）確認交付資料完整
- [x] 1.5 刪掉已驗收集數的 work dir 檔案，只留 TODO 點名要保留的

## 2. 解碼層（scripts/ocr/decode.py）

- [x] 2.1 `tests/ocr/test_decode.py`（紅）：rawvideo 預設補重複格時，畫面數與時間戳數量不符要當場失敗，不可把錯位的畫面交出去
- [x] 2.2 `tests/ocr/test_decode.py`（紅）：showinfo 與進度列印在同一行時，時間戳仍要全部抓到（一行多筆）
- [x] 2.3 `tests/ocr/test_decode.py`（紅）：兩個重疊的視窗，中間那幾格要分別交給兩個視窗，且同一格只解碼一次
- [x] 2.4 `tests/ocr/test_decode.py`（紅）：視窗數多到濾鏡字串過長時，改走 `-filter_script` 檔案，不塞命令列
- [x] 2.5 `tests/ocr/test_decode.py`（紅）：解碼程序非零結束時要拋出並指名，不可回傳半套畫面
- [x] 2.6 實作 `scripts/ocr/decode.py`（綠）：原生格率串流、select 視窗、showinfo 時間戳、`-fps_mode passthrough`、`-nostats`、執行緒數參數
- [x] 2.7 把 `cuelib.stream_region` 搬進 `decode.py`，`cuelib` 只留遮罩與切段；更新所有呼叫端（`cli.py`、`blank_runs.py`、`reread*`、`rescan_band.py` 等）
- [x] 2.8 `tox -e flake8`、`tox -e unittest` 通過

## 3. 取樣（scripts/ocr/sampling.py）

- [x] 3.1 `tests/ocr/test_sampling.py`（紅）：29.97 fps、48 分鐘，以 0.2 秒為目標取樣，最後一個取樣點與目標的差距仍小於一個來源格距（防「固定每 6 格」的累積偏移）
- [x] 3.2 `tests/ocr/test_sampling.py`（紅）：取樣回報的時間是該格的真實時間，不是目標格點
- [x] 3.3 `tests/ocr/test_sampling.py`（紅）：來源 25 fps 時仍是每 0.2 秒一格
- [x] 3.4 `tests/ocr/test_sampling.py`（紅）：同一格同時最接近兩個目標時間時只交出一次
- [x] 3.5 `tests/ocr/test_sampling.py`（紅）：格率宣告為 `0/0` 時以 29.97 當既定值繼續，時間仍取真實 pts
- [x] 3.6 實作 `scripts/ocr/sampling.py`（綠）
- [x] 3.7 `tests/ocr/test_segmenter.py`（紅→綠）：加一條——把原生格率逐格餵進狀態機時 `min_stable=2` 只有 0.067 秒，轉場會被切成獨立 cue；本設計必須是每 0.2 秒一格才餵

## 4. 切 cue 改用原生格率（scripts/ocr/cli.py）

- [x] 4.1 `tests/ocr/test_ocr_prep.py` 或新測試（紅）：`cues` 產出的 `sample_ts` 為真實畫面時間、`sample_fps` 欄位語意更新
- [x] 4.2 實作（綠）：`cues` 改走 `decode` ＋ `sampling`，圖條仍由狀態機保留的最佳畫面寫出
- [x] 4.3 以一集已入庫的集數實跑，確認 cue 條數與現行結果差異在預期範圍（極少數相位差），把實際差異數字記進 `Kari-SRT/news/1-ocr/README`
- [x] 4.4 `tox -e flake8`、`tox -e unittest` 通過

## 5. 精修改成一集一支 ffmpeg（scripts/ocr/refine.py、scripts/news/refine_cues.py）

- [x] 5.1 `tests/news/test_refine.py`（紅）：邊界在 0.1 秒處、視窗被檔頭截短，格數不足時沿用粗切值並計入「取不到畫面」
- [x] 5.2 `tests/news/test_refine.py`（紅）：解碼中途失敗時整集不寫入、以非零結束
- [x] 5.3 `tests/news/test_refine.py`（紅）：回報要把「取不到畫面而沿用」與「無法分辨而沿用」分開計數
- [x] 5.4 `tests/news/test_refine.py`（紅）：精修以原生格距判斷（29.97 → 0.033 秒），不再重新取樣到 25
- [x] 5.5 把邊界判斷（`label_frames`、`transition_time`、`boundaries_of`）搬到 `scripts/ocr/refine.py`（綠），`refine_cues.py` 只留 CLI、±0.2 驗收與原子寫入
- [x] 5.6 `refine_cues.py` 改用 `decode` 的 select 視窗一次取畫面（綠）
- [x] 5.7 拿 1–7 月各一集重跑，與 explore 階段量到的差異分布比對（中位 0.010、p95 0.022、>0.05 約 0.5%），數字對不上要查清楚才往下走
- [x] 5.8 `tox -e flake8`、`tox -e unittest` 通過

## 6. 執行緒與並行度（scripts/news/fetch_sftp.sh）

- [x] 6.1 ffmpeg 執行緒數改為可調，預設 2（量到 2 緒每核效率 0.98、預設 8–9 緒只有 0.67）
- [x] 6.2 批次並行集數改為可調，預設 6
- [x] 6.3 機器閒置時重量一次解碼成本與執行緒效率，確認預設值；數字寫進 `scripts/news/README.md`

## 7. 測試目錄重整

- [x] 7.1 `tests/e2e/` 整個搬到 `tests-e2e/`，更新兩個測試檔的 docstring
- [x] 7.2 `tox.ini`：`unittest` 改為一次 `discover -s tests`，`e2etest` 指向 `tests-e2e/`
- [x] 7.3 `.travis.yml`、`tests/README.md` 路徑更新
- [x] 7.4 `tests-e2e/fixture.py` 增加 29.97 fps 的合成影片，端對端比對時間（現有 fixture 的格率若非 29.97，兩種都要跑）
- [x] 7.5 `tox -e unittest`、`tox -e e2etest` 通過
- [x] 7.6 CLAUDE.md 的驗收清單加入 `tox -e e2etest`

## 8. 工作目錄結構（paths、datadirs）

- [x] 8.1 `tests/news/test_paths.py`（紅）：work dir 落在 `kithann/out/news/1-ocr/<年-月>/`，平鋪在 `1-ocr/` 底下要失敗
- [x] 8.2 `tests/news/test_paths.py`（紅）：跨年（2021-12 與 2022-01）分別落在各自月份
- [x] 8.3 `tests/news/test_workdir_writers.py`（紅）：階段改名為 `1-cues`／`2-strips`／`3-refined`／`4-sheets`／`5-transcripts`，寫錯階段要抓得到
- [x] 8.4 `tests/news/test_workdir_writers.py`（紅）：時間軸記的圖條相對路徑與實際資料夾一致
- [x] 8.5 實作（綠）：`scripts/datadirs.py` 階段常數、`scripts/news/paths.py` 位置與月份層
- [x] 8.6 `asrmt`／log／mkv／stage 的位置常數一併改到 `kithann/out/news/` 之下
- [x] 8.7 `tox -e flake8`、`tox -e unittest` 通過

## 9. 一次性搬家（scripts/news/move_outdirs.py）

- [x] 9.1 `tests/news/test_move_outdirs.py`（紅）：只搬清單內的東西，`stage-read/` 這種暫存不可被當成產物搬進 `1-ocr/`
- [x] 9.2 `tests/news/test_move_outdirs.py`（紅）：log 不可漏搬，且不可搬進 work dir 內
- [x] 9.3 `tests/news/test_move_outdirs.py`（紅）：搬完自檢——舊路徑不再有檔案、新路徑數量相符，不符要非零結束
- [x] 9.4 實作（綠）：`--dry-run` 先印清單，實際搬家，搬完自檢
- [x] 9.5 `tox -e flake8`、`tox -e unittest` 通過

## 10. 上線

- [x] 10.1 確認第 1 組的前置都做完（切 cue 與 OCR 收工、半成品已記進 TODO、work dir 暫存已清）
- [x] 10.2 執行 `move_outdirs.py --dry-run`，核對清單
- [x] 10.3 實際搬家並跑自檢
- [x] 10.4 `tox -e rebuild`、`tox -e flake8`、`tox -e unittest`、`tox -e e2etest`、`name_catalogue --check` 全部通過
- [x] 10.5 以 10 月第一集實跑完整流程（切 cue → 精修 → 入庫），確認新結構與新取樣都正常
- [x] 10.6 更新 `scripts/news/README.md` 的量測數字（吞吐量、每集成本）與 `Kari-SRT/news/1-ocr/README` 的新舊切法說明
