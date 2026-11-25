## Context

動機見 proposal.md〈Why〉，行為見各 spec。這裡只記做法要面對的現況：

- **預覽檔的參數已經量好**：`kithann/字幕編輯預覽檔規格_20261027.md`（v1.0）。3.1 硬體指令、3.2 軟體指令、第四節驗收照抄。實測（2021-02-01 晚間 阿美，2880.144 秒、86318 格）：硬體 368 秒、103.9 CPU 核心秒；軟體 354 秒、2888.7 CPU 核心秒；影格數都與原檔相同。規格書的「存放：S3」「檔名 `.preview.mp4`」「起點都是 0」已由使用者裁定改掉，文件由使用者自己改。
- **本機**：`/dev/dri/renderD128` 存在，ffmpeg 有 `h264_vaapi`、`libx264`、`-f hash`。磁碟剩約 38 GB。
- **新聞目錄**：`Kari-SRT/news/smkul.csv` 3153 集、48 個月（2021-01～2024-12），`原始影片檔案位置` 3153 筆全是 `.mkv`。
- **新聞封存檔聲音抽查**（2026-11-18，固定種子 20261118 隨機抽 300 集，每集只下載開頭 12 MB 給 ffprobe）：300 集第一條音軌全部 FLAC、48000 Hz、24-bit（s32）、單聲道；聲音、影像起點全部 0；1 條音軌 151 集、2 條 149 集；300 集全部在定稿區。0／300 → 95% 信心不是 FLAC 的少於 30 集。
- **開會了目錄**：`Kari-SRT/aiyalaeho/smkul.csv` 39 集，加上 `smkul-字幕版型異常.csv` 5 集（083 僅華語字幕；088、090、098、116 無字幕）共 44 集，`原始影片檔案位置` 全部在 `/docker/族語節目-aiyalaeho開會了/`，2026-11-23 比對伺服器檔名 44 集全部對得上。主表 39 集：
  - 23 集 mkv（101–123、164）：MXF 經 mxf2mkv 轉的封存檔（母帶 8 條音軌、7 條相同，留 2 條）。H.264 1920×1080 29.97 yuv420p、交錯（tb）；2 條 FLAC 48 kHz 24-bit 單聲道；起點 0。
  - 16 集 mp4（068–100）：原始交付檔，MXF 已不在。以 `079`（867 MB，整支下載）為例：**H.264 High 4:2:2** 1920×1080 29.97；標記 progressive，但 `idet` 618 格有 610 格是交錯（TFF）；1 條 **AAC** 48 kHz 單聲道；起點 0；有時間碼軌；mp4 的索引在檔尾（抓開頭讀不到）。
- **4:2:2 硬體解不了**：規格書 3.1 的全硬體指令轉 `079` 直接失敗（`Impossible to convert between the formats`）。混合路徑（CPU 解碼 → `format=nv12,hwupload` → `deinterlace_vaapi`、`scale_vaapi`、`h264_vaapi`）前 60 秒 7.3 秒轉完，影格數 1799＝1799，輸出 h264 High、yuv420p、1280×720、progressive、起點 0；同一段軟體路徑 8.3 秒、影格數相同。
- **開會了 mkv 的兩條音軌**（第 60–180 秒平均音量）：101、105、112、120 第一條 −21～−27 dB、第二條 −91 dB；**107（原檔名「無聲音」）第一條 −91 dB、第二條 −25 dB**。原檔的預設播放旗標也在第一條（靜音那條）上。2026-11-23 另做了一支把有聲音的音軌換到前面的 mkv（原樣複製，影像與兩條音軌的 sha256 都與原檔對應相同），使用者上傳到同一資料夾、名為 `107-拉阿魯哇語-雙語字幕.mkv`，原檔已不在，目錄的 `原始影片檔案位置` 已改指新檔。
- **字幕版型異常表 5 集**：083、088、090、098 是 mp4（同主表那 16 集的交付檔，預期一樣是 4:2:2、走混合路徑），116 是 mkv；沒有逐集量過，路徑與音軌都交給自動選擇。116 族語別 `und`，成果檔名 `開會了_116_Unknown_（未知）`。
- **影像起點**：新聞 `20210101_001_午間_Rukai_魯凱` 影像起點 0.033 秒、聲音 0（`kithann/mp4-2/` 16 支裡唯一一支；抽查 300 集 0 支）。照規格書軟體指令轉 5 秒，預覽檔影像起點同樣 0.033。試過 `tpad` 補 0.033 秒黑畫面：起點變 0，但原本 0.033 那格畫面被推到 0.067，後面每格晚一格——所以不補。
- **時間碼軌**：ffmpeg 寫 mp4 預設帶 `tmcd` 軌（母帶的播出時間碼），`-write_tmcd 0` 拿掉。
- **WAV**（實測阿美前 60 秒）：`aresample=24000:resampler=soxr:precision=28`、`-sample_fmt s16`、`pcm_s16le`、`-map_metadata -1 -fflags +bitexact -flags:a +bitexact` → 1,440,000 個樣本（來源 2,880,000 的一半），轉兩次 sha256 相同，檔頭 44 位元組；不加 bitexact 檔頭 98 位元組、帶 ffmpeg 版本。一集 48 分鐘約 138 MB。
- **ffmpeg 雜湊預設先轉 16-bit**：`-f md5` 的值＝`-f s16le | md5sum`≠`-f s32le | md5sum`；`-f hash -hash sha256` 不加格式一樣是 16-bit。加 `-c:a pcm_s32le` 之後＝`-f s32le | sha256sum`。現行 `encode_master.sh`、`archive_batch.py`、`tools/mxf2mkv/run.py` 的 PCM／FLAC 路徑都沒指定 codec。指紋只存在工作目錄的 `<名>.src-a<i>.md5` 小檔，比完即刪；對照表只記結論，**任何地方都沒存指紋值**，改演算法不必遷移資料。
- **現成可重用的程式**：新聞 `scripts/news/episodes.load()`、`paths.check_srt_name`／`month_of`／兩個影片根、`video_names.locate(entry, sftp)`、`video_names.Sftp`（含 `scan()`）、`audio.fetch_video(remote, local)`；開會了 `scripts/aiyalaeho/episodes.load(table, abnormal_table)`（條目有 `srt_name`、`video`）、`scripts/aiyalaeho/paths.check_srt_name`、`TRACKER_STORE`；`scripts/news/sftp.sh`（唯一准用的 SFTP 管道）。
- **mxf2mkv 的批次骨架**在 `tools/mxf2mkv/`：`batch.py`、`report.py`（`close()` 才寫對照表）、`upload.py`、`run.py` 的 `INTERRUPTED_CODES`、`walk.is_safe`。`kithann/mxf2mkv/` 底下有 3 份空的對照表，是中途停掉的執行留下的。
- `scripts/news/sftp.sh` 只設 `ConnectTimeout=20`；本機 `tcp_keepalive_time` 7200、`intvl` 75、`probes` 9。`SFTP_DRY_RUN=1` 只把批次內容印到 stdout。

## Goals / Non-Goals

**Goals:**

- 兩個指令把開會了 44 集、新聞 3153 集的預覽檔和音檔全部做完，可以中斷、重跑續做，十幾天無人看管不會悄悄停住或吃滿磁碟。
- 批次骨架只有一份；mxf2mkv 對外行為除了「對照表逐筆寫入」以外不變。
- 封存的音軌指紋改 SHA-256 並真正涵蓋 24-bit。

**Non-Goals:**

- 不上 S3。
- 不在 Kari-SRT 記產出狀態，不改目錄。
- 不改伺服器上的來源影片（107 換音軌是使用者另外上傳的，不在這個 change）。
- 不記預覽檔、音檔的雜湊。
- 不回頭重驗已經封存的 mkv（見 Risks）。
- 不在單一執行內平行；不提供調整預覽檔、音檔參數的命令列選項。

## Decisions

### 共用骨架放 `tools/sftpbatch/`

批次迴圈、紀錄與對照表、SFTP 上傳從 `tools/mxf2mkv/` 搬到 `tools/sftpbatch/`。不讓新工具直接 import `tools.mxf2mkv.*`（改 mxf2mkv 的人看不出另一支也在用）；不放 `scripts/transcode/`（那裡是「怎麼轉檔」，新聞流程也用）。

搬移原則是**行為不變、只換位置**：`tests/mxf2mkv/test_report.py`、`test_upload.py` 原樣搬到 `tests/sftpbatch/`、只改 import，全綠之後才改逐筆寫入。

### `sftpbatch.batch.run()` 吃現成的工作清單

改成 `run(jobs, report, one_file, key_field, dry_run)`：

- `jobs` 由呼叫端組。mxf2mkv 的 `plan()`（掃資料夾）留在 `tools/mxf2mkv/batch.py`；新工具兩個節目各自組。
- job 只要求 `label`（紀錄裡辨認這一筆）與 `remote`（mxf2mkv 是單一路徑；新工具放兩種產出的路徑，由 `one_file` 自己解讀，`batch` 不碰）。
- `key_field`：mxf2mkv 傳 `"src"`（對照表格式不變），新工具傳 `"srt_name"`。
- `is_safe`、KeyboardInterrupt 整批停、`Exception` 記下來做下一支、有失敗才保留工作目錄，原樣搬來；`INTERRUPTED_CODES` 也搬來。

### 對照表逐筆寫入、原子替換

`report.Run.write(entries)`：整份 JSON 寫到 `<manifest>.tmp`，`os.replace()` 換上去；`batch.run()` 每加一筆就呼叫。`close()` 最後再寫一次並加 `工作目錄`。頂層新增 `已收尾`：`write()` 為 false、`close()` 為 true。

不用 JSONL：對照表要排版過、人打開就看得懂，也要跟現有 mxf2mkv 格式一致。3153 筆約 2 MB，一集 6 分鐘重寫一次，可以忽略。

`open_run()` 改吃 `(folder, stem, header)`：mxf2mkv 傳 `kithann/mxf2mkv/<來源名>/`、`<MMDD-HHMM>_<來源名>`、`{"來源資料夾": …}`；新工具傳 `kithann/mkv2mp4wav/<節目>/`、`<MMDD-HHMM>`、`{"來源": "Kari-SRT/<節目>/smkul.csv"}`。O_EXCL 搶檔名、`-2` 後綴不變。

### 兩個指令、一套核心

```
tools/mkv2mp4wav/
  aiyalaeho.py   python3 -m tools.mkv2mp4wav.aiyalaeho：開會了的工作清單、找來源、產出位置
  news.py        python3 -m tools.mkv2mp4wav.news：新聞的工作清單、找來源、產出位置
  cli.py         兩個指令共用的參數解析與發動（--software、--limit、--dry-run、--work、--report-dir）
  run.py         一集的流程（不知道是哪個節目）
  encode.py / tracks.py / audio.py / verify.py
```

每個節目模組提供同一組三樣東西給 `cli.py`：`jobs(limit)`（讀自己的目錄、排序、組 Job）、`locate(job, sftp, log)`（回傳來源的遠端路徑與標籤）、`listing(sftp)`（試跑用，一次列出遠端已有的產出）。`run.py` 只透過這三樣跟節目打交道。

為什麼不是一個指令加 `--program`：使用者裁定分兩個指令，各自 `--help` 只講自己的事，紀錄資料夾也天然分開。

### 兩個節目的根放各自的 `paths.py`

- `scripts/news/paths.py`：`PREVIEW_ROOT = "/home/news/mp4"`、`WAV_ROOT = "/home/news/wav"`、`preview_path(srt_name)`、`wav_path(srt_name)`（內部先 `check_srt_name`、`month_of`），跟兩個影片根放一起。
- `scripts/aiyalaeho/paths.py`：`PREVIEW_ROOT = "/home/aiyalaeho/mp4"`、`WAV_ROOT = "/home/aiyalaeho/wav"`、`preview_path()`、`wav_path()`（內部先 `check_srt_name`），不分子資料夾。

不開 `--dst-root`。

### 開會了的來源

`scripts/aiyalaeho/episodes.load()` 把 `smkul.csv` 與字幕版型異常表合起來，正好就是這次的範圍（44 集），直接用；測試給它兩張合成的小表。字幕版型異常表的集沒有雙語字幕，但預覽檔可以在字幕編輯器裡補字幕、音檔可以當語料，所以照做。來源路徑是 `"/" + 原始影片檔案位置`，單一位置，伺服器說找不到就記失敗。

### 預覽檔指令：三條路徑

`tools/mkv2mp4wav/encode.py` 的 `command(src, dst, track, path)` 回傳 list，`path` 是：

| 路徑 | 何時 | 濾鏡與解碼 |
|---|---|---|
| `硬體` | 來源 `pix_fmt` 是 yuv420p（新聞、開會了 mkv） | 規格書 3.1 原樣：`-threads 1 -hwaccel vaapi -hwaccel_output_format vaapi`、`deinterlace_vaapi=mode=bob:rate=frame,scale_vaapi=w=1280:h=720:format=nv12` |
| `混合` | 來源不是 yuv420p（開會了 mp4 的 4:2:2） | `-threads 1 -vaapi_device /dev/dri/renderD128`、CPU 單執行緒解碼、`format=nv12,hwupload,deinterlace_vaapi=mode=bob:rate=frame,scale_vaapi=w=1280:h=720:format=nv12`。`-threads 1` 是實作時 e2e 量到才加的：多執行緒解碼在檔尾 flush 一次吐出一批畫格，`hwupload` 報 `Cannot allocate memory`（離開碼 244），合成 300 格只編出 285 格；先前 079 只轉前 60 秒、沒走到檔尾所以沒碰到 |
| `軟體` | 指定 `--software` | 規格書 3.2 原樣 |

三條共同：`-map 0:v:0 -map 0:a:<track>`、規格書的位元率／GOP／AAC 參數、`-fps_mode passthrough`、`-write_tmcd 0`、`-movflags +faststart`、`-nostdin`、`-y`、前綴 `nice -n 15 ionice -c 3`。不用 bash：沒有逐條音軌的迴圈，list 直接拿來比對就是測試。

`subprocess.run(…, timeout=來源時長)`：正常 7–8 倍速，跑滿 1 倍速還沒完就是卡住了。`TimeoutExpired` 為一般失敗；回傳碼在 `INTERRUPTED_CODES` 才轉 KeyboardInterrupt。

起點不另外處理：`-fps_mode passthrough` 已保留每格時間。標記為 progressive 的交錯來源（開會了 mp4）：`deinterlace_vaapi`、`yadif=0:-1:0` 都是每一格都處理，不看標記；但場序是看標記猜的，要在開會了實跑時人工看動態畫面確認。

### 進度與預估剩餘時間：`tools/mkv2mp4wav/progress.py`

使用者裁定預估「算最近 10 支的速度」（2026-11-23）。整批平均會被開頭幾支拖住：網路或伺服器變慢時預估要好幾個小時才跟上；只看最近 10 支，變化在一小時內就反映出來，又不會因為單一支特別慢就大幅跳動。

- `Progress(total, done_before, to_do, clock=time.monotonic, window=10)`：`start()` 印開場那行；`finished(label, result, seconds)` 回傳要印的那一行，結果是「已存在」的不進速度窗、只把剩下要做的減一；`summary()` 回傳結束那行。
- `eta_seconds(recent, remaining)`：`recent` 是最近至多 10 支的秒數，空的回傳 None（印「第一支做完後估算」）。
- `hours_minutes(seconds)`：先四捨五入成整分鐘再拆，59 分 36 秒 → 「1 小時 0 分」。
- 時鐘可注入，測試不用真的等。
- 開跑前的「已完成幾支」用 `program.listing(sftp)`（試跑同一份 ls：新聞 96 次，約一兩分鐘；開會了 2 次）。
- `sftpbatch.batch.run()` 加一個可省略的 `on_done(job, entry, seconds)`；mxf2mkv 不傳，行為與輸出不變。`cli.py` 把 `Progress.finished()` 的那行同時印到終端機與寫進紀錄檔（紀錄檔本來就是 stderr 全文，進度行走同一條）。

### 使用者自己在終端機執行、開跑前檢查

使用者要能在 repo 根目錄自己打指令跑（2026-11-23），指的是這台機器的 VS Code 終端機（devcontainer：有 `/dev/dri/renderD128`、ffmpeg 有 `h264_vaapi`、`.sftp-pass` 在 repo 根）。所以：

- 只用標準函式庫與 repo 內的 `scripts/`，系統 `python3 -m tools.mkv2mp4wav.news` 就能跑，不依賴 `.tox/`。
- `cli.preflight(software)`：`shutil.which()` 查 `ffmpeg`、`ffprobe`、`sftp`；`SFTP_PASS_FILE`（預設 repo 根 `.sftp-pass`）只看存不存在，不開檔；沒加 `--software` 時接著做 VAAPI 探測。缺什麼就印出、離開碼 2，在 `listing()` 之前，所以沒有任何連線或下載。
- README 給可以直接複製的指令：`--dry-run`、`--limit 2`、全跑；Ctrl+C 停、再打同一行續做。新聞全跑十幾天、容器裡沒有 tmux，關掉終端機程式就停，所以另給 `setsid nohup python3 -m tools.mkv2mp4wav.news > /dev/null 2>&1 &` 與 `tail -f` 最新紀錄檔的寫法（輸出都已在紀錄檔裡）。CLAUDE.md 禁用 `nohup &` 是針對 Claude 發動的背景工作（harness 不會通知），使用者自己發動不受影響；Claude 發動時仍一律 `run_in_background: true`。
- 分工：開會了 44 集與新聞 `--limit 200`（約 20 小時）由 Claude 以 `run_in_background` 發動並驗收；新聞全跑由使用者照 README 發動。

### VAAPI 探測一次、整批決定

開跑前 `encode.probe_vaapi()`：`/dev/dri/renderD128` 存在且可讀，並以 lavfi 合成 1 格 1280×720 交給 `h264_vaapi` 編到 null，回傳碼 0 才算可用。沒加 `--software` 而失敗，印原因與「加 --software 改用軟體編碼」、離開碼 2。加了就不探測。不在單集失敗時自動改用軟體：驅動出問題時會變成整批悄悄吃滿 CPU。

### 音軌選擇：`tools/mkv2mp4wav/tracks.py`

`pick(source, tracks, measure)`：從第 0 條開始，用 `ffmpeg -map 0:a:<i> -af volumedetect -f null -` 量整條平均音量，第一條高於 −80 dB 就選它，後面不量。全部不高於 −80 dB → 回傳 `(0, "全部音軌靜音")`：預覽檔用第 0 條，音檔記失敗。`measure` 由呼叫端傳入，測試傳假的。

成本：通常只量第一條；FLAC／AAC 解碼一條 48 分鐘幾秒到十幾秒。−80 dB 的依據：數位靜音量到 −91 dB，有聲音的落在 −21～−27 dB，中間空很大。

### 音檔：`tools/mkv2mp4wav/audio.py`

- `precheck(container, stream)`：mkv → `codec_name == "flac"`；mp4 → `codec_name in ("flac", "aac")`；另外都要 `channels == 1`、`start_time == 0`。否則回傳原因（音檔記失敗，預覽檔照做）。mp4 的 AAC 可以：mp4 有記開頭要略過的樣本數，ffmpeg 解碼時照著略過；mkv 不記，所以 mkv 的 AAC 不行。
- `command(src, dst, track)`：`nice -n 15 ionice -c 3 ffmpeg -nostdin -y -i SRC -map 0:a:<track> -af aresample=24000:resampler=soxr:precision=28 -sample_fmt s16 -c:a pcm_s16le -map_metadata -1 -fflags +bitexact -flags:a +bitexact DST`。不設 dither 參數，即不加抖動。
- 驗收：ffprobe `-of json` 取 `codec_name`、`sample_rate`、`channels`、音軌數、樣本數；`|wav − 來源/2| ≤ 1`。來源樣本數要解碼後的數（mkv 的時間基準是毫秒，`duration_ts` 不是樣本數；mp4 的 AAC 要扣掉略過的樣本）——實作第一步先量出可靠的取法。

### 預覽檔驗收拆成純函式

`tools/mkv2mp4wav/verify.py`：每一項是純函式，吃已解析的 ffprobe JSON（或檔頭位元組），回傳 `(通過, 說明)`；`probe(path)` 薄層實際呼叫 ffprobe。

- 影格數 `-count_packets`（讀完整個檔，2.5 GB 約數十秒）。
- 起點：影像、聲音各自跟來源比，差 0.001 秒以內。
- 時間碼：不可有 `codec_type == "data"` 且 `codec_tag_string == "tmcd"` 的軌。
- `moov`／`mdat`：讀前 4 MB，逐個走頂層 box（4 位元組長度＋4 位元組型別；長度 1 時讀 8 位元組 largesize），不用額外套件。
- 大小上限 `(1800 + 128) × 1000 / 8 × 時長` 位元組：48 分鐘 ≈ 0.69 GB，對上規格書的 0.7 GB。
- 全部項目跑完才回報。

### 單集流程

`tools/mkv2mp4wav/run.py` 的 `one_episode(job, program, work_dir, software, log)`：

1. 兩種產出各問一次 `sftpbatch.upload.already_there()`；都在就回「已存在」，不下載。
2. `program.locate(job, sftp, log)` 找來源。
3. `audio.fetch_video(remote, <work>/<srt_name><副檔名>)` 下載（副檔名照來源，mkv 或 mp4）。
4. ffprobe 來源一次（影格數、起點、時長、`pix_fmt`、各音軌格式）；`tracks.pick()` 選音軌。
5. 缺預覽檔 → 選路徑 → 編碼 → 驗收 → 上傳；缺音檔 → `precheck` → 轉檔 → 驗收 → 上傳。兩段各自 try，互不牽連；KeyboardInterrupt 一律往外丟。
6. `finally`：刪來源影片、`.mp4`、`.wav` 與殘留 `.partial`。
7. 回傳 entry：`來源`（遠端路徑、標籤、位元組數、影格數）、`音軌`（第幾條、平均音量）、`預覽檔`／`音檔`（遠端路徑、位元組數、驗收、結果；預覽檔另有編碼路徑）、整集 `結果`（成功／失敗／已存在；失敗時 `原因` 講出是哪一種）。

新聞不走 `audio.locate()`：它會先看本機 `paths.mkv_path()` 的暫存封存檔，那份屬於切 cue 那一步。

### 試跑

`--dry-run`：新聞是兩個根各自每個月份資料夾 `ls` 一次（`video_names.Sftp.scan()`，48×2 次）；開會了是 `/home/aiyalaeho/mp4`、`/home/aiyalaeho/wav` 各一次。列出每集兩種產出各自會跳過還是會處理。不找來源、不下載。

### 封存指紋改 SHA-256、完整位元深度

- `encode_master.sh`：每條音軌的指紋輸出由 `-f md5 <名>.src-a<i>.md5` 改成 `-f hash -hash sha256 <名>.src-a<i>.sha256`。整數 PCM 路徑 `hash_args=(-c:a pcm_s32le)`；原樣複製路徑維持 `-c:a copy`（比封裝資料）。指紋檔內容 `SHA256=<hex>`。
- `archive_batch.py`、`tools/mxf2mkv/run.py`：讀 `.sha256`；封存端以同樣的 codec 參數重算（FLAC → `pcm_s32le`、copy → `copy`）；清理用的 glob 改 `.src-a*.sha256`。函式名 `_read_md5`、`source_md5s`、`encoded_md5s` 改成 `_read_sha256` 等。
- `audio_tracks.py` 只比字串，不用改。
- 用 ffmpeg 內建 `-f hash -hash sha256`，跟 `sha256sum` 是同一個演算法：同樣的取樣位元組，值完全相同。不改用外部 `sha256sum` 管線，是因為一次 ffmpeg 要同時產出封存檔和 N 條音軌的指紋，管線一次只能接一個輸出。
- 為什麼要 32-bit：FLAC 24-bit 解碼成 s32（下面 8 位元補 0），以 s32 算才涵蓋全部 24 位元；s16 會丟掉下面 8 位元。

### sftp.sh 斷線偵測

`exec sftp` 加 `-o ServerAliveInterval=30 -o ServerAliveCountMax=4`。為了離線測試，`SFTP_DRY_RUN=1` 時另外把將要執行的 sftp 參數印到 stderr（stdout 照舊只有批次內容，既有測試不受影響）。

## 檔案樹

```
Kari-SRT/aiyalaeho/smkul.csv                       只讀（aiyalaeho.py）
Kari-SRT/news/smkul.csv                            只讀（news.py 經 episodes.load()）

SFTP
  /docker/族語節目-aiyalaeho開會了/*.mkv、*.mp4      只讀（aiyalaeho.py 的 locate）
  /home/aiyalaeho/mp4/<成果檔名>.mp4[.partial]      ★ sftpbatch/upload.py；吃 encode.py 的產出
  /home/aiyalaeho/wav/<成果檔名>.wav[.partial]      ★ sftpbatch/upload.py；吃 audio.py 的產出
  /docker/news/mkv/<年-月>/<srt_name>.mkv           只讀（news.py 的 locate 經 video_names.locate）
  /home/news/mkv/<年-月>/<srt_name>.mkv             只讀
  <新聞原始影片檔案位置>                              只讀
  /home/news/mp4/<年-月>/<srt_name>.mp4[.partial]   ★
  /home/news/wav/<年-月>/<srt_name>.wav[.partial]   ★

本機
  /tmp/mkv2mp4wav-<隨機>/                           ★ cli.py 建；成功刪、有失敗留
    <srt_name>.mkv 或 .mp4                          ★ audio.fetch_video 下載；一集結束即刪
    <srt_name>.mp4（預覽檔，與 mp4 來源分開命名）       ★ encode.py 產；一集結束即刪
    <srt_name>.wav                                  ★ audio.py 產；一集結束即刪
  /tmp/mxf2mkv-<隨機>/<名>.src-a<i>.sha256           改：encode_master.sh 產（原 .md5）；比完即刪
  kithann/mkv2mp4wav/aiyalaeho/<MMDD-HHMM>.log、.manifest.json   ★ sftpbatch/report.py；吃 run.py 的 entry，逐集重寫
  kithann/mkv2mp4wav/news/<MMDD-HHMM>.log、.manifest.json        ★ 同上
  kithann/mxf2mkv/<來源名>/<MMDD-HHMM>_<來源名>.manifest.json      改：逐筆重寫、已收尾

tools/
  sftpbatch/
    __init__.py                ★
    batch.py                   ★ 從 mxf2mkv/batch.py 抽出 run()、Job/Result，並搬入 INTERRUPTED_CODES、is_safe
    report.py                  ★ 從 mxf2mkv/report.py 搬來；open_run(folder, stem, header)、Run.write()、已收尾
    upload.py                  ★ 從 mxf2mkv/upload.py 原樣搬來
  mxf2mkv/
    __main__.py                改：import 換成 sftpbatch；組 report 參數
    batch.py                   改：只剩 plan()
    run.py                     改：從 sftpbatch import；指紋讀 .sha256、封存端以 pcm_s32le 重算
    walk.py                    改：is_safe 搬走
    report.py、upload.py       ✖ 搬去 sftpbatch（沒有外部呼叫端，不留轉接層）
    README.md                  改：對照表逐筆寫入、已收尾、指紋 SHA-256 完整位元深度
  mkv2mp4wav/
    __init__.py                ★
    cli.py                     ★ 參數解析、探測 VAAPI、發動 sftpbatch.batch.run(key_field="srt_name")
    aiyalaeho.py               ★ 開會了：jobs()、locate()、listing()、main()
    news.py                    ★ 新聞：jobs()、locate()、listing()、main()
    encode.py                  ★ 預覽檔 command()（硬體／混合／軟體）、choose_path()、probe_vaapi()、encode()
    tracks.py                  ★ pick()：第一條有聲音的音軌
    audio.py                   ★ 音檔 precheck()、command()、convert()、verify()
    verify.py                  ★ 預覽檔驗收純函式、probe()、check_all()
    run.py                     ★ one_episode()
    progress.py                ★ Progress、eta_seconds()、hours_minutes()：總數、進度、最近 10 支估剩餘時間
    README.md                  ★ 兩個指令怎麼跑（使用者可直接複製）、檔案去哪、保證什麼、看進度
scripts/
  news/paths.py                改：PREVIEW_ROOT、WAV_ROOT、preview_path()、wav_path()
  aiyalaeho/paths.py           改：PREVIEW_ROOT、WAV_ROOT、preview_path()、wav_path()
  news/sftp.sh                 改：ServerAlive 兩個選項；SFTP_DRY_RUN 時 sftp 參數印到 stderr
  transcode/encode_master.sh   改：-f hash -hash sha256、PCM 路徑 -c:a pcm_s32le、.sha256
  transcode/archive_batch.py   改：讀 .sha256、封存端同算法、清理 glob
README.md                      改：工具清單加 mkv2mp4wav

tests/
  README.md                    改：總表加兩行，指向 sftpbatch/README.md、mkv2mp4wav/README.md；改 transcode／mxf2mkv 列的檔名與 scenario
  sftpbatch/
    __init__.py、README.md     ★
    test_batch.py              ★ 從 mxf2mkv/test_failure.py 的 TestKeepGoing、TestUnsafeNames、TestWorkDir、TestDryRun 及 test_interrupt.py 的批次中斷部分搬來
    test_report.py             ★ 從 mxf2mkv/test_report.py 搬來＋逐筆寫入、原子替換、已收尾
    test_upload.py             ★ 從 mxf2mkv/test_upload.py 原樣搬來
  mxf2mkv/
    test_failure.py            改：只留 TestLimit 與 plan 相關
    test_interrupt.py          改：只留長度檢查、中斷碼轉換、清指紋檔（.sha256）、__main__ 回 130
    test_report.py、test_upload.py   ✖ 搬去 sftpbatch
  mkv2mp4wav/
    __init__.py、README.md、fakes.py（假的伺服器、編碼器、節目模組）   ★
    test_aiyalaeho_plan.py、test_news_plan.py、test_encode_cmd.py、test_tracks.py、test_audio.py、test_verify.py、test_encoder_choice.py、test_failure.py、test_report.py、test_progress.py、test_preflight.py   ★
  transcode/
    test_encode_master.py      改：指紋輸出 sha256、PCM 路徑帶 pcm_s32le
    test_archive_batch.py      改：讀 .sha256
  news/
    test_paths.py              改：preview_path、wav_path
    test_sftp_cli.py           改：ServerAlive 選項
  aiyalaeho/
    test_paths.py              改：preview_path、wav_path
tests-e2e/
  test_mkv2mp4wav_roundtrip.py ★ 4:2:0 mkv 與 4:2:2 mp4 各一支，軟體路徑必跑；硬體／混合路徑 skipUnless(/dev/dri/renderD128)
  test_mxf2mkv_roundtrip.py    改：指紋 SHA-256；兩條只差下面 8 位元的音軌要兩條都留
```

## spec × scenario × 測試檔

| spec 規定 | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| mkv2mp4wav：兩個指令、照目錄 | 開會了的工作清單是 `smkul.csv` 39 集加字幕版型異常表 5 集（083、088、090、098、116）——只讀主表會漏掉 5 集，而這 5 集正是最需要在字幕編輯器裡補字幕的 | `mkv2mp4wav/test_aiyalaeho_plan.py` |
| mkv2mp4wav：兩個指令、照目錄 | 新聞 3153 集照 srt_name 排序，`--limit 2` 重跑時是同樣兩集，不能照 csv 列序或伺服器 ls 順序 | `mkv2mp4wav/test_news_plan.py` |
| mkv2mp4wav：兩個指令、照目錄 | srt_name 不合規格（新聞集數兩碼、開會了不是 `開會了_<三碼>_`）：那集失敗並指名，下一集照做 | `mkv2mp4wav/test_news_plan.py`、`test_aiyalaeho_plan.py` |
| mkv2mp4wav：位置 | 新聞 `20210103_003_晨間_Hla'alua_拉阿魯哇`、開會了 `開會了_107_Hla'alua_拉阿魯哇` 的撇號和中文完整出現在 mp4、wav 路徑 | `news/test_paths.py`、`aiyalaeho/test_paths.py` |
| mkv2mp4wav：位置 | 新聞 mkv 退到原始位置 `/home/mkv-raw/9月/…`，產出仍放 `2024-10/`；開會了不分子資料夾 | `mkv2mp4wav/test_news_plan.py`、`test_aiyalaeho_plan.py` |
| mkv2mp4wav：試跑 | 新聞每個月份資料夾只 ls 一次（3153 集各連一次約一小時）；開會了兩個資料夾各一次；不找來源、不下載、不建本機檔 | `mkv2mp4wav/test_news_plan.py`、`test_aiyalaeho_plan.py` |
| mkv2mp4wav：找來源 | 新聞三處都沒有：那集失敗、三個路徑寫進紀錄、下一集照做 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：找來源 | 新聞本機 `paths.mkv_path()` 有切 cue 留下的暫存封存檔，也不能拿來用 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：找來源 | 開會了 mp4 來源下載到本機要保留 `.mp4` 副檔名，而且不能跟預覽檔同名互蓋 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：本機只留一集 | 成功、編碼失敗、驗收不過、上傳失敗四種結局，來源、mp4、wav 都要刪（磁碟塞滿過兩次，stage-read 一個月 25–40 GB） | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：各自跳過 | mp4、wav 都已存在：跳過，**沒有呼叫下載**（新聞省 2.5 GB） | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：各自跳過 | mp4 已在、wav 缺：下載、只做 wav，沒有呼叫預覽檔編碼 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：各自上傳 | wav 驗收不過：mp4 照樣上傳，這集記失敗、原因講出是音檔 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：編碼路徑 | 來源 yuv422p（開會了 079）走混合路徑：有 `format=nv12,hwupload`、`-vaapi_device`，沒有 `-hwaccel vaapi`——全硬體指令實測直接失敗 | `mkv2mp4wav/test_encode_cmd.py`、`test_encoder_choice.py` |
| mkv2mp4wav：編碼路徑 | 來源 yuv420p 走全硬體路徑，照規格書 3.1 | `mkv2mp4wav/test_encoder_choice.py` |
| mkv2mp4wav：硬體編碼 | 沒有 `/dev/dri/renderD128` 又沒加 `--software`：開跑前就停、離開碼 2、訊息有 `--software`、一支都沒下載 | `mkv2mp4wav/test_encoder_choice.py` |
| mkv2mp4wav：硬體編碼 | 某集硬體編碼失敗：記那集預覽檔失敗，沒有改用軟體重做；下一集仍是硬體指令 | `mkv2mp4wav/test_encoder_choice.py` |
| mkv2mp4wav：硬體編碼 | 加了 `--software`：不探測 VAAPI，4:2:0、4:2:2 來源都用 libx264 | `mkv2mp4wav/test_encoder_choice.py` |
| mkv2mp4wav：音軌選擇 | 107 換音軌前的原檔第一條 −91 dB、第二條 −25 dB：選第二條，預覽檔與音檔都 `-map 0:a:1`——照「只取第一條」會產出整集靜音 | `mkv2mp4wav/test_tracks.py`、`test_failure.py` |
| mkv2mp4wav：音軌選擇 | 第一條 −24.9 dB：選第一條，**沒有量第二條** | `mkv2mp4wav/test_tracks.py` |
| mkv2mp4wav：音軌選擇 | 全部 −91 dB：音檔失敗「全部音軌靜音」，預覽檔用第一條照做 | `mkv2mp4wav/test_tracks.py` |
| mkv2mp4wav：音軌選擇 | −80 dB 是門檻：−80.0 算靜音、−79.9 算有聲音 | `mkv2mp4wav/test_tracks.py` |
| mkv2mp4wav：預覽檔參數 | 硬體去交錯沒寫 `mode=bob` 會用驅動預設，實測整集少 3 格、起點偏 0.066 秒——硬體、混合路徑都一定要有 `deinterlace_vaapi=mode=bob:rate=frame` | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 混合路徑沒有 `-threads 1`：CPU 多執行緒解碼在檔尾一次吐一批畫格，`hwupload` 報 `Cannot allocate memory`、離開碼 244，合成 300 格只編出 285 格（只轉前 60 秒的試驗測不到） | `mkv2mp4wav/test_encode_cmd.py`、`tests-e2e/test_mkv2mp4wav_roundtrip.py` |
| mkv2mp4wav：預覽檔參數 | 全硬體指令沒有 `-threads 1`，軟解多執行緒跟 VAAPI surface pool 打架，廣播素材上噴 `get_buffer() failed` | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 沒有 `-fps_mode passthrough`，寫 MP4 會補格或丟格、每次 33 毫秒且累積；也不可以出現 `-r` | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 沒有 `-nostdin`，終端機按到 q，ffmpeg 好好收尾出一支短檔（10-06 有 8 支半截 mkv 傳上去） | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 軟體路徑要 `yadif=0:-1:0`（一格出一格、每格都處理，開會了 mp4 標記 progressive 也照樣去交錯）；`yadif=1` 格數翻倍、`deint=1` 會跳過標記 progressive 的格 | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 沒有 `-write_tmcd 0`，預覽檔帶時間碼軌，剪輯軟體從 01:00:00;00 起算、跟 SRT 對不起來 | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 指令裡不可以有 `tpad`、`setpts`：實測 `tpad` 補黑畫面把第一格從 0.033 推到 0.067，整集晚一格 | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔參數 | 沒有 `nice`／`ionice` 前綴，軟體路徑吃滿全部核心（2888 核心秒／集） | `mkv2mp4wav/test_encode_cmd.py` |
| mkv2mp4wav：預覽檔驗收 | 影格數少 3 格 → 不通過，說明寫出兩邊格數 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | `20210101_001_午間_Rukai_魯凱` 來源影像起點 0.033、預覽 0.033 → 通過；預覽 0 → 不通過 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | `field_order` 是 tt、解析度 1920×1080、`pix_fmt` yuv422p、兩條音軌、2 聲道、帶 tmcd 軌 → 各自不通過並講出哪一項 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | `moov` 在 `mdat` 後 → 不通過；頂層 box 長度為 1（64 位元 largesize）要能正確跳過 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | 關鍵格間距 8 秒（x264 預設 GOP）→ 不通過 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | 24 分鐘 0.5 GB → 不通過；只用固定 0.7 GB 會漏掉 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | 時長短 23 分鐘（被停掉的半截檔）→ 不通過 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：預覽檔驗收 | 三項同時不過：三項都列出來，不是只報第一項 | `mkv2mp4wav/test_verify.py` |
| mkv2mp4wav：音檔參數 | 指令要有 `-map 0:a:<選用那條>`、`resampler=soxr:precision=28`、`-sample_fmt s16`、`pcm_s16le`、bitexact 三個旗標；不可有 dither 參數 | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔參數 | 不加 bitexact，WAV 檔頭多 54 位元組 ffmpeg 版本資訊，換版本轉出來就不一樣 | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔參數 | mkv 裡的 AAC → 音檔失敗、不轉檔（mkv 不記略過樣本數，解碼整段偏移）；預覽檔照做 | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔參數 | 開會了 mp4 裡的 AAC（20 集）→ 照常轉——若照「不是 FLAC 就失敗」這 20 集全部做不出音檔 | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔參數 | 來源聲音 2 聲道 → 失敗，不混音 | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔參數 | 來源聲音起點 0.021 秒 → 失敗：WAV 不記起點，照轉整段提早、對不上 SRT | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔驗收 | 樣本數不是來源的一半（差超過 1 個）→ 不通過；來源樣本數不可直接拿 mkv 的 `duration_ts`（毫秒） | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：音檔驗收 | 16000 Hz、2 聲道、pcm_s24le → 各自不通過 | `mkv2mp4wav/test_audio.py` |
| mkv2mp4wav：失敗與中斷 | 編碼跑滿來源時長還沒結束：停掉、記失敗、下一集照做，不當成中斷 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：失敗與中斷 | ffmpeg 離開碼 255／130／-SIGINT：整批停、離開碼 130；外面包了 `nice`／`ionice` 回傳碼仍要認得 | `mkv2mp4wav/test_failure.py` |
| mkv2mp4wav：紀錄 | 兩個指令的預設紀錄各落在 `kithann/mkv2mp4wav/aiyalaeho/`、`news/`，`kithann/mxf2mkv/` 沒有新檔（共用後最容易沿用到 mxf2mkv 的預設路徑） | `mkv2mp4wav/test_report.py` |
| mkv2mp4wav：紀錄 | 每筆鍵為 `srt_name`，有選用音軌與平均音量；預覽檔、音檔各自有路徑／位元組數／驗收／結果，預覽檔有編碼路徑與兩邊影格數 | `mkv2mp4wav/test_report.py` |
| mxf2mkv：紀錄（修改） | 做完第 N 筆就讀得到前 N 筆、`已收尾` false；正常結束 true（現有 3 份空對照表就是中途停掉留下的） | `sftpbatch/test_report.py` |
| mxf2mkv：紀錄（修改） | 寫暫存檔途中當掉，磁碟上的對照表仍是上一次的完整 JSON | `sftpbatch/test_report.py` |
| mxf2mkv：紀錄（既有） | 同一分鐘跑兩次加 `-2`、搶到一半不留孤兒檔、JSON 排版／鍵排序（原樣搬移） | `sftpbatch/test_report.py` |
| mxf2mkv：上傳（既有） | `.partial` → 比位元組數 → 改名；不符不改名；零位元組最終名稱不算完成（原樣搬移） | `sftpbatch/test_upload.py` |
| mxf2mkv：失敗續跑、中斷（既有） | 一支失敗做下一支、危險檔名只擋那一支、有失敗保留工作目錄、試跑不動檔、KeyboardInterrupt 不被吞（原樣搬移） | `sftpbatch/test_batch.py` |
| mxf2mkv：對照表格式不變 | 搬到 sftpbatch 後，mxf2mkv 對照表每筆的鍵仍是 `src` | `sftpbatch/test_batch.py` |
| master-archival：SHA-256 | 指紋輸出是 `-f hash -hash sha256`，檔名 `.sha256`，值 64 個十六進位字元 | `transcode/test_encode_master.py` |
| master-archival：完整位元深度 | PCM 路徑的指紋輸出沒帶 `-c:a pcm_s32le`，ffmpeg 預設先轉 16-bit（實測 `-f md5` ＝ `-f s16le \| md5sum`），下面 8 位元從未驗過 | `transcode/test_encode_master.py` |
| master-archival：完整位元深度 | 封存端重算指紋也要 `pcm_s32le`，兩邊算法不一致會整批誤判不符 | `mxf2mkv/test_interrupt.py`、`transcode/test_archive_batch.py` |
| master-archival：完整位元深度 | 兩條 24-bit 音軌只差最低 8 位元：指紋不同、兩條都留 | `tests-e2e/test_mxf2mkv_roundtrip.py` |
| master-archival：AAC 原樣複製 | copy 路徑仍比封裝資料、不帶 pcm_s32le（解碼 mkv 裡的 AAC 會多一個預備框，每個樣本都對不上） | `transcode/test_encode_master.py` |
| episode-video-location：斷線偵測 | sftp 指令沒有 `ServerAliveInterval=30`、`ServerAliveCountMax=4` → 斷線要 2 小時 11 分才發現（7200＋9×75 秒） | `news/test_sftp_cli.py` |
| episode-video-location：斷線偵測 | `SFTP_DRY_RUN` 的 stdout 仍只有批次內容（既有測試比對 stdout，不可被參數輸出污染） | `news/test_sftp_cli.py` |
| mkv2mp4wav：進度 | 續跑時 1200 支已存在、這次 2 支各 6 分：預計 1951 × 6 分＝195 小時 6 分；把跳過的算進平均會印出不到 1 小時 | `mkv2mp4wav/test_progress.py` |
| mkv2mp4wav：進度 | 前 10 支各 6 分、後 10 支各 9 分：第 20 支後以 9 分估，不是整批平均 7.5 分（使用者裁定看最近 10 支） | `mkv2mp4wav/test_progress.py` |
| mkv2mp4wav：進度 | 做過不到 10 支時以已做的平均；一支都還沒做完印「第一支做完後估算」，不拿固定數字猜 | `mkv2mp4wav/test_progress.py` |
| mkv2mp4wav：進度 | 開跑後才出現在伺服器上的那支：跳過、不進速度窗、剩下要做減一 | `mkv2mp4wav/test_progress.py` |
| mkv2mp4wav：進度 | 59 分 36 秒印「1 小時 0 分」，不印「0 小時 60 分」 | `mkv2mp4wav/test_progress.py` |
| mkv2mp4wav：進度 | 開場那行：只有 mp4 在、wav 不在的算「要做」不算「已完成」；`--limit` 時「全部」是限制後的支數 | `mkv2mp4wav/test_progress.py` |
| mkv2mp4wav：進度 | 進度行也寫進紀錄檔（背景跑時終端機看不到）；mxf2mkv 不傳 `on_done`，輸出不變 | `mkv2mp4wav/test_report.py`、`sftpbatch/test_batch.py` |
| mkv2mp4wav：自己執行 | 換機器 `.sftp-pass` 還沒建：開跑就停、離開碼 2、印路徑不讀內容、沒有連線 | `mkv2mp4wav/test_preflight.py` |
| mkv2mp4wav：自己執行 | PATH 沒有 `ffprobe`：開跑就停、離開碼 2、印出缺什麼 | `mkv2mp4wav/test_preflight.py` |
| 端對端 | 合成 1080i 交錯 4:2:0 mkv（兩條 FLAC，第一條靜音）：軟體路徑預覽檔驗收全過、選第二條音軌、音檔 24000 Hz 16-bit 樣本數＝一半、轉兩次 WAV 逐位元相同 | `tests-e2e/test_mkv2mp4wav_roundtrip.py` |
| 端對端 | 合成 4:2:2 mp4（AAC、標記 progressive）：軟體路徑兩樣都過；有 `/dev/dri/renderD128` 時混合路徑也過 | `tests-e2e/test_mkv2mp4wav_roundtrip.py` |
| 端對端 | 4:2:0 mkv 走全硬體路徑；沒有 `/dev/dri/renderD128` 就 skip 並寫明原因（CI 永遠 skip，本機要過） | `tests-e2e/test_mkv2mp4wav_roundtrip.py` |

## Risks / Trade-offs

- [開會了 mp4 標記 progressive、實際交錯] GPU 去交錯判斷場序靠標記，可能猜錯（畫面會一格一格前後跳）→ 開會了實跑後人工抽看幾集的動態畫面；若有問題，混合路徑在 `hwupload` 前加 `setfield=tff` 修正標記（不影響每格時間）。
- [已經封存的 mkv 只驗過上面 16 位元] FLAC 是無損編碼，下面 8 位元在轉檔時出錯的機會極低；比較可能有影響的是「兩條音軌只差下面 8 位元卻被判成相同、丟掉一條」。要確認得拿母帶重算，母帶多半已不在手邊 → 這次不回頭重驗，只修往後的。
- [新聞全跑十幾天] 中途重開機、斷電 → 跳過以遠端最終名稱為準，重跑直接續做；每次執行各有一份紀錄與對照表。Claude 發動一律 `run_in_background: true`；使用者自己發動照 README（前景或 `setsid nohup`）。
- [伺服器端 sftp 程序卡住、但 sshd 仍回應] ServerAlive 抓不到 → 少見；對照表逐筆寫入、紀錄有時間戳，看得出卡在哪一集。真的遇到再另開 change 加呼叫端逾時。
- [ServerAlive 影響所有用 sftp.sh 的流程] 只有伺服器連續約 2 分鐘沒回應才斷；傳得慢不受影響 → 可接受。
- [影格數驗收要讀完兩支檔案] 每集多約一分鐘 → 規格書規定的驗收，不省。
- [VAAPI 驅動在某些素材上出錯] → 那集預覽檔記失敗；跑完看紀錄，再用 `--software` 補跑（跳過機制讓補跑只做缺的）。
- [−80 dB 門檻誤判] 一整集幾乎沒講話、只有極小環境聲的音軌可能被當成靜音 → 對照表記每集選用的音軌與音量，跑完可以篩「選的不是第一條」的集數人工看。
- [搬移 mxf2mkv 程式、改指紋演算法] 可能改到行為 → 先原樣搬、只改 import、全綠，再加逐筆寫入，再改 SHA-256；每一步跑 unittest 與 e2e。
- [新聞封存檔聲音不是 FLAC 的集數] 抽查 0／300，95% 信心少於 30 集 → 遇到記失敗，全跑後看對照表再決定。

## Migration Plan

1. sftpbatch 原樣搬移 → 逐筆寫入 → 指紋 SHA-256 → sftp.sh 斷線偵測 → 兩個節目的根；每一步全綠。
2. mkv2mp4wav 核心模組照 TDD 做，接著開會了指令。
3. 開會了實跑：`--limit 2` → 全部 44 集（`run_in_background`，約 4.5 小時）；人工在 Firefox／Chrome 看幾集預覽檔（特別是 4:2:2 mp4 的動態畫面）、聽 107 的音檔。
4. 新聞指令；`--limit 2` 實跑（排序第一集就是影像起點 0.033 的魯凱），再 `--limit 200`（`run_in_background`，約 20 小時）驗收。
5. 新聞全跑：使用者照 README 在自己的終端機發動 `python3 -m tools.mkv2mp4wav.news`。

回滾：新工具只新增 `/home/aiyalaeho/{mp4,wav}/`、`/home/news/{mp4,wav}/` 底下的檔，刪掉資料夾即可；其他改動 git 還原即可，沒有資料遷移。
