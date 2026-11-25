## Why

字幕編輯器要在瀏覽器裡邊看影片邊改 SRT，但手上的影片不能直接拿去用：MKV 不是瀏覽器格式、交錯畫面有梳狀紋、位元率和 GOP 太大跳轉很慢。《字幕編輯預覽檔規格》（`kithann/字幕編輯預覽檔規格_20261027.md`）已經把預覽 mp4 的參數和驗收量好了。另外會議決定，語音辨識訓練要一份 WAV 24 kHz／16-bit／單聲道的音檔（2026-11-23）。兩者都從同一支影片做，而最貴的是把影片從 SFTP 抓下來（新聞每集約 2.5 GB、3153 集約 7.9 TB），所以一次下載同時產出兩樣。《開會了》（44 集：主表 39 集＋字幕版型異常表 5 集）與新聞都要做，開會了集數少，先做。

mxf2mkv 已經有一副跑了兩個月、踩過坑的批次骨架（失敗續跑、Ctrl+C 整批停、`.partial` 上傳、紀錄與對照表），新工具要同樣的保證，不應該再寫一份。mxf2mkv 的對照表要整批結束才寫——`kithann/mxf2mkv/` 底下已經有 3 份是空檔，就是執行中途停掉留下的；新工具新聞全跑估計 13 天以上，這個缺口兩邊一起補。

量測時還發現兩個既有問題，一起修：

- **封存的「音訊逐位元相符」其實只驗了上面 16 位元。** ffmpeg 的 `-f md5` 預設先把聲音轉成 16-bit 再算（實測：`-f md5` 的值等於 `-f s16le | md5sum`，不等於 `-f s32le | md5sum`），封存檔的聲音是 24-bit，下面 8 位元出錯不會被發現，兩條音軌只差在下面 8 位元時也會被當成相同而丟掉一條。使用者裁定雜湊全部改用 SHA-256，這次一併改成以完整位元深度計算。
- **`scripts/news/sftp.sh` 連上之後沒有斷線偵測**，對方消失時要等系統 TCP keepalive 約 2 小時 11 分（7200＋9×75 秒）才發現。

## What Changes

- **新工具 `tools/mkv2mp4wav/`，兩個指令**：`python3 -m tools.mkv2mp4wav.aiyalaeho`（開會了）、`python3 -m tools.mkv2mp4wav.news`（新聞）。各自照自己的目錄逐集（開會了是 `smkul.csv` 加 `smkul-字幕版型異常.csv`，新聞是 `smkul.csv`），從 SFTP 找到影片、下載一次，產出兩樣並各自驗收、各自上傳，再刪掉本機檔。
  - 開會了：來源是 `原始影片檔案位置`（24 集 mkv、20 集 mp4），產出放 `/home/aiyalaeho/mp4/<成果檔名>.mp4`、`/home/aiyalaeho/wav/<成果檔名>.wav`。
  - 新聞：來源依定稿區 → 暫放區 → 原始位置找，產出放 `/home/news/mp4/<年-月>/<srt_name>.mp4`、`/home/news/wav/<年-月>/<srt_name>.wav`。
  - 預覽檔：參數照規格書（720p、VBR 1200/1800 kbps、GOP 30、無 B 格、逐格去交錯、`-fps_mode passthrough`、AAC 128k 單聲道、faststart），不寫時間碼軌；起點照來源（不補黑畫面）。
  - 預設只用 VAAPI 硬體編碼，依來源自動選路徑：4:2:0 全硬體；4:2:2（開會了 mp4，硬體解不了）CPU 解碼、硬體去交錯縮放編碼。加 `--software` 才整批改用 libx264。
  - 音軌選用第一條有聲音的（整條平均高於 −80 dB）——開會了 107 的原檔第一條是靜音、聲音在第二條（伺服器上已換成有聲音在前的版本，但不能保證別集沒有同樣情形）。
  - 音檔：soxr 重取樣成 24 kHz、降成 16-bit（不加抖動）、單聲道、bitexact 檔頭。mkv 來源的聲音必須是 FLAC；mp4 來源的 AAC 照 mp4 的時間解碼。
  - 終端機與紀錄檔印出全部幾支、已完成幾支、這次要做幾支；每做完一支印進度與預計還要幾小時幾分（以最近 10 支真的有做的平均速度估，跳過的不算）。
  - 使用者在 repo 根目錄用系統的 `python3` 就能自己執行，不需要 tox venv；開跑前檢查 ffmpeg／ffprobe／sftp、密碼檔、硬體編碼，缺什麼就在下載前停下並講明。README 給可以直接複製的指令。新聞由 Claude 實跑到 `--limit 200` 驗收，全跑由使用者照 README 自己發動。
- **新共用 package `tools/sftpbatch/`**：mxf2mkv 的批次迴圈、紀錄與對照表、SFTP 上傳搬過來，兩支工具共用；紀錄分開放（`kithann/mxf2mkv/`、`kithann/mkv2mp4wav/aiyalaeho/`、`kithann/mkv2mp4wav/news/`）。
- **對照表逐筆寫入**（mxf2mkv 也是）：每處理完一筆就重寫一次（暫存檔＋改名），中途當掉已完成的紀錄仍在、檔案仍是完整 JSON；加 `已收尾` 欄位。
- **封存的音軌指紋改 SHA-256、以完整位元深度計算**：`scripts/transcode/encode_master.sh`、`scripts/transcode/archive_batch.py`、`tools/mxf2mkv/run.py`。整數 PCM 以 32-bit 取樣算；原樣複製的音軌（AAC）照舊算封裝資料。
- **`scripts/news/sftp.sh` 加 `ServerAliveInterval=30`、`ServerAliveCountMax=4`**：伺服器連續約 2 分鐘沒有回應就斷線，所有用它的流程一起受益。
- **`scripts/news/paths.py`、`scripts/aiyalaeho/paths.py`** 各加自己節目的預覽檔與音檔的根。
- **不新增任何 Python 套件**：只用既有的 `ffmpeg`／`ffprobe`／`sftp`。
- 產出做了沒有**不記在 Kari-SRT**；伺服器上有沒有最終名稱就是答案。

## Capabilities

### New Capabilities

- `mkv2mp4wav-batch`：開會了與新聞的影片轉預覽 mp4 與訓練用 WAV 的批次——兩個指令各照自己的目錄逐集、找來源與下載、兩種產出的位置與命名、編碼路徑的選擇、音軌選擇、預覽檔與音檔的參數與驗收、各自跳過與上傳、失敗續跑與中斷、本機只留一集、紀錄與對照表、試跑。

### Modified Capabilities

- `mxf2mkv-batch`：〈執行紀錄與對照表〉改成每處理完一支就寫入，中途當掉時已完成的紀錄仍然完整可讀。
- `master-archival`：〈音訊逐位元相符才算封存成功〉明定指紋用 SHA-256，且以來源完整位元深度計算，不得先降成 16-bit。
- `episode-video-location`：新增〈伺服器連線斷掉要在數分鐘內發現〉。

## Impact

### 資料落點

```
Kari-SRT/aiyalaeho/smkul.csv                     只讀
Kari-SRT/aiyalaeho/smkul-字幕版型異常.csv         只讀
Kari-SRT/news/smkul.csv                          只讀；Kari-SRT 底下不新增、不改任何檔

SFTP（開會了）
  /docker/族語節目-aiyalaeho開會了/*.mkv、*.mp4     只讀（原始影片檔案位置）
  /home/aiyalaeho/mp4/<成果檔名>.mp4               ★ 上傳中叫 .mp4.partial
  /home/aiyalaeho/wav/<成果檔名>.wav               ★ 上傳中叫 .wav.partial

SFTP（新聞）
  /docker/news/mkv/<年-月>/<srt_name>.mkv         只讀，第 1 順位（抽查 300 集全部在這裡）
  /home/news/mkv/<年-月>/<srt_name>.mkv           只讀，第 2 順位
  原始影片檔案位置（/home/mkv-raw/…mkv）            只讀，第 3 順位
  /home/news/mp4/<年-月>/<srt_name>.mp4           ★
  /home/news/wav/<年-月>/<srt_name>.wav           ★

本機
  /tmp/mkv2mp4wav-<隨機>/                         ★ 同時最多一支來源影片＋一支 mp4＋一支 wav
  kithann/mkv2mp4wav/aiyalaeho/<MMDD-HHMM>.log、.manifest.json   ★
  kithann/mkv2mp4wav/news/<MMDD-HHMM>.log、.manifest.json        ★
  kithann/mxf2mkv/<來源名>/…manifest.json          改：逐筆寫入
```

### 程式與測試

```
tools/
  sftpbatch/                 ★ __init__.py、batch.py、report.py、upload.py
  mxf2mkv/                   改 __main__.py、batch.py、run.py、walk.py、README.md；✖ report.py、upload.py（搬去 sftpbatch）
  mkv2mp4wav/                ★ __init__.py、cli.py、aiyalaeho.py、news.py、encode.py、tracks.py、audio.py、verify.py、run.py、progress.py、README.md
scripts/
  news/paths.py              改：PREVIEW_ROOT、WAV_ROOT、preview_path()、wav_path()
  aiyalaeho/paths.py         改：PREVIEW_ROOT、WAV_ROOT、preview_path()、wav_path()
  news/sftp.sh               改：ServerAlive 兩個選項；SFTP_DRY_RUN 時把 sftp 參數印到 stderr
  transcode/encode_master.sh 改：指紋 SHA-256、完整位元深度、檔名 .sha256
  transcode/archive_batch.py 改：讀寫 .sha256、封存端指紋同樣算法
README.md                    改：工具清單加 mkv2mp4wav
tests/
  README.md                  改：總表加兩行，指向 sftpbatch/、mkv2mp4wav/ 的 README
  sftpbatch/                 ★ README.md、test_batch.py、test_report.py、test_upload.py
  mxf2mkv/                   改 test_failure.py、test_interrupt.py；✖ test_report.py、test_upload.py（搬去 sftpbatch）
  mkv2mp4wav/                ★ README.md、test_aiyalaeho_plan.py、test_news_plan.py、test_encode_cmd.py、test_tracks.py、test_audio.py、test_verify.py、test_encoder_choice.py、test_failure.py、test_report.py、test_progress.py、test_preflight.py
  transcode/                 改 test_encode_master.py、test_archive_batch.py
  news/                      改 test_paths.py、test_sftp_cli.py
  aiyalaeho/                 改 test_paths.py
tests-e2e/
  test_mkv2mp4wav_roundtrip.py  ★ 合成交錯影片（4:2:0 mkv、4:2:2 mp4）走軟體路徑；有 /dev/dri/renderD128 才多跑硬體路徑
  test_mxf2mkv_roundtrip.py     改：指紋改 SHA-256；加「只差下面 8 位元的兩條音軌不可被當成相同」
```

### 規模

開會了 44 集：約 4.5 小時。新聞 3153 集：硬體編碼約 13.4 天（一集 368 秒，規格書實測），下載約 7.9 TB；上傳預覽檔約 1.6–2.2 TB、音檔約 435 GB（一集約 138 MB），合計約 2.0–2.6 TB（使用者確認伺服器空間足夠）。開會了與新聞前 200 集由 Claude 以 `run_in_background` 發動；新聞全跑由使用者在自己的終端機發動。
