## Why

切 cue 與精修是整條線上最耗機器的一段：量到一集（48 分鐘、約 819 個邊界）要 77 核心分鐘，其中 59 分鐘花在精修——一個邊界開一支 ffmpeg，819 次啟動的固定成本（每次約 3.4 核心秒：開行程、建執行緒池、讀 86,400 格的 MP4 索引）就吃掉 46 分鐘，真正解畫面的只有 13 分鐘。

同時量到兩件會讓資料悄悄失準的事：來源影片全部是 29.97 fps（NTSC），但切 cue 與精修都用 `fps=5`／`fps=25` 重新取樣，而 `fps` 濾鏡挑到的畫面比它標記的時間晚約 0.067 秒（兩格）——時間軸的 `sample_ts` 因此對不上它判斷的那一格，讀者照它抽格會抽到上一句（TODO 裡 179午 那條的根源）。

工作目錄也到了該整理的時候：`kithann/out/mxf/` 底下 400 多個 work dir 平鋪、`mxf-logs/` 1326 個檔平鋪，名字還留著「mxf」但裡面沒有任何 mxf 檔。

## What Changes

- **切 cue 與精修改用來源原生格率**：一支 ffmpeg 解出原生格，Python 每 0.2 秒挑最接近的一格餵給切段狀態機（判準不變），精修則用原生格距 0.033 秒（現為 0.04 秒）。探不到格率（可變格率）時當作 29.97。
- **精修從「一個邊界一支 ffmpeg」改成「一集一支 ffmpeg」**：用 `select` 一次放行全部邊界視窗，時間戳取自 `showinfo` 的真實 pts；輸出加 `-fps_mode passthrough`（否則 ffmpeg 會補重複格，畫面數與時間戳對不上）。實測七集（1–7 月各一集）：與現行做法的邊界差中位 0.01 秒、p95 0.022 秒，超過 0.05 秒的約 0.5%。
- **`sample_ts` 記真實畫面時間**，不再記 0.2 秒格點。已入庫集數不回補（使用者裁定：接受差異）。
- **ffmpeg 每支限 2 執行緒、同時跑 6 集**：量到預設執行緒（自己抓 8–9 核）要多燒 49% CPU；2 執行緒每核效率 0.98。並行度做成可調，不寫死。
- **`refine_cues` 維持獨立的第二趟**，可單獨重跑，不與切 cue 綁死。
- **`kithann/out/` 重整**：族語新聞的工作資料收進 `kithann/out/news/`，全部照 `<年-月>` 分層；work dir 內部階段照產生先後編號。
- **開會了（aiyalaeho）共用同一套引擎**：取樣與精修程式碼共用，其 work dir 也因此多出精修階段；資料夾位置這次不動。
- **`tests/e2e/` 搬到 `tests-e2e/`**，`tox -e unittest` 改成一次掃 `tests/`（不再逐目錄列出，避免新開目錄忘了加就悄悄沒跑）。
- **BREAKING**：work dir 的階段資料夾改名（`strips/` → `2-strips/`、`2-refined/` → `3-refined/`、`sheets/` → `4-sheets/`），時間軸裡的 `images` 相對路徑跟著改。使用者裁定：等 8–9 月 OCR 做完、work dir 暫存刪掉之後才套用，不做舊資料遷移。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cue-timing`：精修取樣密度改以來源原生格率表述（現行條文寫「取樣間隔 SHALL ≤ 0.05 秒」）；新增「取樣時間必須是該格的真實時間」與「粗切取樣以 0.2 秒為目標、取最接近的來源格」兩條；精修一集一支 ffmpeg 的失敗必須整集中止、不得產出部分結果。
- `srt-data-store`：work dir 的階段命名與位置（編號階段、`<年-月>` 分層、收進 `kithann/out/news/`）。

## Impact

**程式**

```
scripts/ocr/decode.py          ★新  ffmpeg 讀取：原生格率串流、select 視窗、
                                    showinfo 時間戳、-fps_mode passthrough
                                    （cuelib 的 stream_region 搬過來）
scripts/ocr/sampling.py        ★新  每 0.2 秒挑最接近的一格
scripts/ocr/refine.py          ★新  邊界判斷（從 news/refine_cues.py 搬引擎部分）
scripts/ocr/cuelib.py           改  只留遮罩與切段
scripts/ocr/cli.py              改  cues 改吃原生格、sample_ts 記真實時間
scripts/news/refine_cues.py     改  變薄：CLI 與驗收留著，判斷改呼叫引擎
scripts/news/paths.py           改  work dir 位置與階段名
scripts/news/move_outdirs.py   ★新  一次性搬家（dry-run、只搬清單內的、搬完自檢）
scripts/news/fetch_sftp.sh      改  並行度、ffmpeg 執行緒數
scripts/datadirs.py             改  階段常數
```

**測試**

```
tests-e2e/                     ★新  由 tests/e2e/ 搬出（含 29.97 合成影片）
tests/ocr/test_sampling.py     ★新
tests/news/test_move_outdirs.py ★新
tests/ocr/test_segmenter.py     改
tests/news/test_refine.py       改
tests/news/test_paths.py        改
tests/news/test_workdir_writers.py 改
tox.ini、.travis.yml、tests/README.md 改
```

**資料**

```
Kari-SRT/news/1-ocr/1-cues/<年-月>/<集名>.json
    新切的集數：images 記 "2-strips/…"、sample_ts 記真實時間
    已入庫集數：不動

kithann/out/news/1-ocr/<年-月>/<集名>.work/{1-cues,2-strips,3-refined,4-sheets,5-transcripts}/
kithann/out/news/2-asr/<年-月>/      （原 asrmt/）
kithann/out/news/logs/<年-月>/       （原 mxf-logs/，一集三個檔照舊）
kithann/out/news/mkv/<年-月>/        （原 mkv/，126 GB）
kithann/out/news/stage*/             （stage、stage-read、stage-band、stage-rows）
kithann/out/aiyalaeho*               不動
```

**時程**：資料夾搬家與階段改名，要等 8–9 月切 cue 與 OCR 全部做完、work dir 暫存刪掉之後才執行。程式面的取樣與精修改動可以先做。
