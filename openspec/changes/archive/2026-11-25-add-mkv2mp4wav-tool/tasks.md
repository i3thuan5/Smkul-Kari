# Tasks

## 1. 批次骨架搬到 tools/sftpbatch（行為不變）

- [x] 1.1 建 `tools/sftpbatch/__init__.py`、`tests/sftpbatch/__init__.py`；把 `tests/mxf2mkv/test_report.py`、`test_upload.py` 原樣搬到 `tests/sftpbatch/`，import 改指 `tools.sftpbatch`，確認紅（模組還不存在）
- [x] 1.2 把 `tools/mxf2mkv/report.py`、`upload.py` 搬到 `tools/sftpbatch/`（用一般的 `mv`，不用 `git mv`——它會動到 staged，CLAUDE.md 不准），`tools/mxf2mkv/` 內的 import 跟著改；`.tox/unittest/bin/python -m unittest discover -s tests -t .` 全綠
- [x] 1.3 把 `tests/mxf2mkv/test_failure.py`（TestKeepGoing、TestUnsafeNames、TestWorkDir、TestDryRun）與 `test_interrupt.py` 裡批次層的中斷測試搬到 `tests/sftpbatch/test_batch.py`，改成直接組 jobs 呼叫 `sftpbatch.batch.run(jobs, report, one_file, key_field, dry_run)`；加測試：mxf2mkv 的對照表每筆鍵仍是 `src`。確認紅
- [x] 1.4 實作 `tools/sftpbatch/batch.py`（從 `tools/mxf2mkv/batch.py` 抽出 run、Job、Result，搬入 `INTERRUPTED_CODES`、`is_safe`）；`tools/mxf2mkv/batch.py` 只留 `plan()`，`run.py`、`walk.py`、`__main__.py` 改 import；`tests/mxf2mkv/` 剩下的測試照新位置調整。unittest 全綠，`.tox/e2etest/bin/python -m unittest discover -s tests-e2e -t tests-e2e` 全綠
- [x] 1.5 `report.open_run()` 改吃 `(folder, stem, header)`：先改 `tests/sftpbatch/test_report.py` 讓它紅，再改實作與 mxf2mkv 呼叫端；測試比對 mxf2mkv 的紀錄落點與檔名跟改之前完全相同。unittest 全綠

## 2. 對照表逐筆寫入（mxf2mkv-batch 修改）

- [x] 2.1 在 `tests/sftpbatch/test_report.py` 加測試：做完第 N 筆就讀得到前 N 筆且 `已收尾` 為 false；`close()` 後為 true；寫暫存檔途中丟例外，磁碟上的對照表仍是上一次的完整 JSON。確認紅
- [x] 2.2 實作 `Run.write(entries)`（寫 `<manifest>.tmp` 再 `os.replace`）與 `已收尾`，`sftpbatch.batch.run()` 每加一筆就呼叫；unittest 全綠
- [x] 2.3 更新 `tools/mxf2mkv/README.md`（對照表逐筆寫入、`已收尾`、範例 JSON），建 `tests/sftpbatch/README.md`（design 對照表 sftpbatch／mxf2mkv 那幾列），`tests/README.md` 總表加一行指過去，並改正 mxf2mkv 列裡已搬走的測試檔名

## 3. 封存指紋改 SHA-256、完整位元深度（master-archival 修改）

- [x] 3.1 改 `tests/transcode/test_encode_master.py`：`ENCODE_DRY_RUN` 印出的指令裡，每條音軌的指紋輸出是 `-f hash -hash sha256 <名>.src-a<i>.sha256`；PCM 來源帶 `-c:a pcm_s32le`；AAC 來源帶 `-c:a copy`、不帶 `pcm_s32le`；指令裡不再出現 `md5`。確認紅
- [x] 3.2 改 `scripts/transcode/encode_master.sh`（`hash_args`、`.sha256`、註解說明為什麼要 32-bit 並附實測：`-f md5` ＝ `-f s16le | md5sum`）；3.1 綠
- [x] 3.3 改 `tests/transcode/test_archive_batch.py`、`tests/mxf2mkv/test_interrupt.py`：讀 `.sha256`、封存端重算指紋時 PCM 帶 `pcm_s32le`、copy 帶 `copy`、中斷後清掉 `.src-a*.sha256`。確認紅
- [x] 3.4 改 `scripts/transcode/archive_batch.py`、`tools/mxf2mkv/run.py`（函式改名 `_read_sha256`、`source_sha256s`、`encoded_sha256s`，glob 改 `.sha256`）；3.3 綠、unittest 全綠
- [x] 3.5 改 `tests-e2e/test_mxf2mkv_roundtrip.py`：指紋改 SHA-256；加一個合成母帶，兩條 24-bit 音軌只差最低 8 位元，封存後兩條都留、對照表寫「兩軌不同，兩條都留」。先確認在舊算法（不帶 `pcm_s32le`）下會紅，再綠；e2etest 全綠
- [x] 3.6 `grep -rn md5 scripts tools tests tests-e2e` 沒有殘留（與封存無關的若有，逐筆確認後再決定）；`tools/mxf2mkv/README.md`、`scripts/news/README.md` 等文件中講封存指紋的段落改成 SHA-256 與完整位元深度

## 4. sftp.sh 斷線偵測（episode-video-location 新增）

- [x] 4.1 在 `tests/news/test_sftp_cli.py` 加測試：`SFTP_DRY_RUN=1` 時 stderr 印出的 sftp 參數含 `ServerAliveInterval=30`、`ServerAliveCountMax=4`（get、put、ls、mkdir、rename、rmdir、`-` 都要）；stdout 仍只有批次內容。確認紅
- [x] 4.2 改 `scripts/news/sftp.sh`：`exec sftp` 加兩個 `-o`，dry run 時把參數印到 stderr；檔頭註解補一段說明（不設時要 2 小時 11 分才發現）；unittest 全綠

## 5. 兩個節目的產出位置

- [x] 5.1 在 `tests/aiyalaeho/test_paths.py` 加 `preview_path()`、`wav_path()` 測試：`開會了_107_Hla'alua_拉阿魯哇` → `/home/aiyalaeho/mp4/…mp4`、`/home/aiyalaeho/wav/…wav`，撇號與中文完整保留、不分子資料夾、不合規格拒絕、換掉根立刻跟著變。確認紅
- [x] 5.2 `scripts/aiyalaeho/paths.py` 加 `PREVIEW_ROOT`、`WAV_ROOT`、`preview_path()`、`wav_path()`；unittest 全綠
- [x] 5.3 在 `tests/news/test_paths.py` 加同樣的測試（月份取自 srt_name）。確認紅
- [x] 5.4 `scripts/news/paths.py` 加 `PREVIEW_ROOT`、`WAV_ROOT`、`preview_path()`、`wav_path()`；unittest 全綠

## 6. mkv2mp4wav 核心：預覽檔編碼與驗收

- [x] 6.1 建 `tools/mkv2mp4wav/__init__.py`、`tests/mkv2mp4wav/__init__.py`；寫 `tests/mkv2mp4wav/test_encode_cmd.py`：全硬體指令含 `-threads 1 -hwaccel vaapi`、`deinterlace_vaapi=mode=bob:rate=frame`、`scale_vaapi=w=1280:h=720:format=nv12`；混合指令含 `-vaapi_device`、`format=nv12,hwupload,deinterlace_vaapi=mode=bob:rate=frame`、不含 `-hwaccel vaapi`；軟體指令含 `yadif=0:-1:0`、不含 `yadif=1`、`deint=1`；三條都含 `-map 0:a:<選用那條>`、`-fps_mode passthrough`、`-g 30 -bf 0`、`-nostdin`、`-write_tmcd 0`、`+faststart`、`nice -n 15 ionice -c 3` 前綴，不含 `-r`、`tpad`、`setpts`。確認紅
- [x] 6.2 寫 `tests/mkv2mp4wav/test_encoder_choice.py`：yuv420p → 全硬體、yuv422p → 混合；沒有裝置又沒加 `--software` → 離開碼 2、訊息含 `--software`、下載函式沒被呼叫；加 `--software` → 不探測、全用 libx264；單集硬體失敗 → 記失敗、不改軟體、下一集仍硬體。確認紅
- [x] 6.3 實作 `tools/mkv2mp4wav/encode.py`（`command()`、`choose_path()`、`probe_vaapi()`、`encode()`：timeout＝來源時長，`TimeoutExpired` 為一般失敗，回傳碼在 `INTERRUPTED_CODES` 轉 KeyboardInterrupt）；6.1、6.2 綠
- [x] 6.4 寫 `tests/mkv2mp4wav/test_verify.py`，餵假的 ffprobe JSON 與合成的 MP4 檔頭位元組：少 3 格、魯凱起點 0.033 對 0.033 通過／對 0 不通過、field_order tt、1920×1080、yuv422p、兩條音軌、2 聲道、tmcd 軌、moov 在 mdat 後、largesize box、關鍵格間距 8 秒、24 分鐘 0.5 GB、短 23 分鐘、三項同時不過全部列出、全部通過。確認紅
- [x] 6.5 實作 `tools/mkv2mp4wav/verify.py`；6.4 綠

## 7. mkv2mp4wav 核心：音軌選擇與音檔

- [x] 7.1 寫 `tests/mkv2mp4wav/test_tracks.py`（假的 measure）：107 第一條 −91、第二條 −25 → 選第二條；第一條 −24.9 → 選第一條且 measure 只被呼叫一次；全部 −91 → 回傳第一條並標「全部音軌靜音」；−80.0 算靜音、−79.9 算有聲音。確認紅
- [x] 7.2 實作 `tools/mkv2mp4wav/tracks.py`（`pick()`，實際的 measure 用 `volumedetect`）；7.1 綠
- [x] 7.3 先量：對 `kithann/開會了-107/` 那支 mkv 與一支開會了 mp4（下載後量完即刪），確認怎麼取得選用音軌解碼後的正確樣本數（mkv 的 `duration_ts` 是毫秒；mp4 的 AAC 要扣掉略過的樣本），把量到的做法與數字寫進 `audio.py` 的註解
- [x] 7.4 寫 `tests/mkv2mp4wav/test_audio.py`：指令含 `-map 0:a:<選用那條>`、`aresample=24000:resampler=soxr:precision=28`、`-sample_fmt s16`、`-c:a pcm_s16le`、`-map_metadata -1`、`-fflags +bitexact`、`-flags:a +bitexact`、`nice`／`ionice`，不含 dither 參數；precheck：mkv 的 AAC 失敗、mp4 的 AAC 通過、mp4／mkv 的 FLAC 通過、2 聲道失敗、起點 0.021 失敗，各講原因；驗收：樣本數差 2 個不通過、差 1 個通過、16000 Hz／2 聲道／pcm_s24le／兩條音軌各自不通過。確認紅
- [x] 7.5 實作 `tools/mkv2mp4wav/audio.py`（`precheck()`、`command()`、`convert()`、`verify()`）；7.4 綠

## 8. mkv2mp4wav 核心：單集流程與紀錄

- [x] 8.1 寫 `tests/mkv2mp4wav/test_failure.py`（假的節目模組、sftp、fetch、encode、convert、measure）：兩種都已存在不下載、只缺 wav 只做 wav（沒呼叫預覽檔編碼）、wav 失敗 mp4 照傳且原因講出音檔、找不到來源記失敗且路徑入紀錄、mp4 來源下載後保留 `.mp4` 且不跟預覽檔互蓋、選第二條音軌時預覽檔與音檔都用第二條、四種結局都刪來源／mp4／wav、編碼逾時記失敗不算中斷、離開碼 255／130／-SIGINT 整批停回 130。確認紅
- [x] 8.2 寫 `tests/mkv2mp4wav/test_report.py`：每筆鍵為 `srt_name`、有選用音軌與平均音量、預覽檔與音檔各有路徑／位元組數／驗收／結果、預覽檔有編碼路徑與兩邊影格數。確認紅
- [x] 8.3 寫 `tests/mkv2mp4wav/test_progress.py`（注入時鐘）：開場那行的全部／已完成／要做（只有 mp4 在的算要做、`--limit` 後的支數）；跳過 1200 支、做 2 支各 6 分 → 195 小時 6 分；前 10 支 6 分、後 10 支 9 分 → 以 9 分估；不到 10 支取已做的平均；一支都沒做完印「第一支做完後估算」；中途已存在的不進速度窗、剩下要做減一；59 分 36 秒 →「1 小時 0 分」；結束那行有總用時與三種結果支數。`tests/sftpbatch/test_batch.py` 加：有傳 `on_done` 每支呼叫一次、帶秒數，沒傳時行為不變。確認紅
- [x] 8.4 寫 `tests/mkv2mp4wav/test_preflight.py`：`.sftp-pass` 不在 → 離開碼 2、印路徑、沒開檔也沒呼叫 sftp；PATH 沒有 `ffprobe` → 離開碼 2 並指名；加 `--software` 不探測 VAAPI；全部都在 → 通過。`test_report.py` 加：進度行出現在紀錄檔。確認紅
- [x] 8.5 實作 `tools/mkv2mp4wav/progress.py`、`sftpbatch.batch.run()` 的 `on_done`、`tools/mkv2mp4wav/run.py`（`one_episode()`）與 `tools/mkv2mp4wav/cli.py`（參數、`preflight()`、探測 VAAPI、開場列遠端已有的、發動 `sftpbatch.batch.run(key_field="srt_name", on_done=…)`、進度行印到終端機並寫進紀錄檔）；8.1–8.4 綠；用系統 `python3`（不是 `.tox/`）跑 `python3 -m tools.mkv2mp4wav.aiyalaeho --help` 確認不缺套件

## 9. 開會了指令

- [x] 9.1 寫 `tests/mkv2mp4wav/test_aiyalaeho_plan.py`（合成的小 csv）：`smkul.csv` 與字幕版型異常表兩張表的集都進清單、srt_name 排序與 `--limit` 穩定、不合規格的 srt_name 成為失敗 job、來源是 `"/" + 原始影片檔案位置`（mkv 與 mp4 都可）、產出路徑不分子資料夾、試跑兩個產出資料夾各 ls 一次且不下載；`test_report.py` 加：預設紀錄落在 `kithann/mkv2mp4wav/aiyalaeho/`、`kithann/mxf2mkv/` 無新檔。確認紅
- [x] 9.2 實作 `tools/mkv2mp4wav/aiyalaeho.py`（`jobs()`、`locate()`、`listing()`、`main()`）；9.1 綠
- [x] 9.3 寫 `tests-e2e/test_mkv2mp4wav_roundtrip.py` 的開會了部分：ffmpeg lavfi 合成 (a) 1080i 交錯 4:2:0 mkv、兩條 FLAC 24-bit 且第一條靜音，(b) 4:2:2 mp4、AAC、標記 progressive；軟體路徑兩支都要預覽檔 `verify.check_all()` 全過、音檔 `audio.verify()` 全過、(a) 選第二條音軌、同一支轉兩次 WAV 逐位元相同；硬體／混合路徑 `skipUnless(/dev/dri/renderD128)` 並寫明原因。先紅後綠，本機全部要綠
- [x] 9.4 寫 `tools/mkv2mp4wav/README.md`（兩個指令怎麼跑——使用者在 repo 根目錄可以直接複製的 `--dry-run`／`--limit 2`／全跑、Ctrl+C 停與續跑、關掉終端機也繼續跑的 `setsid nohup` 寫法與 `tail -f` 看進度；進度行與預估怎麼算；檔案去哪、保證什麼、`--software` 何時用；新聞那段先寫「下一步」），建 `tests/mkv2mp4wav/README.md`（design 對照表 mkv2mp4wav 那幾列），`tests/README.md` 總表加一行並更新 transcode 列的 scenario，根目錄 `README.md` 工具清單加 mkv2mp4wav；照 README 執行 `python3 -m tools.mkv2mp4wav.aiyalaeho --dry-run`，開場印出全部 44 支／已完成／要做、列出 44 集、輸出跟描述相符
- [x] 9.5 實跑 `python3 -m tools.mkv2mp4wav.aiyalaeho --limit 2`：兩集的 mp4、wav 出現在 `/home/aiyalaeho/mp4/`、`/home/aiyalaeho/wav/`，對照表驗收全過、本機工作目錄已清空；進度行有第幾支與預計剩餘時間；再跑一次確認兩集都記「已存在」且沒有下載、開場印「已完成 2 支」
- [x] 9.6 以 `run_in_background: true` 發動 `python3 -m tools.mkv2mp4wav.aiyalaeho` 跑完 44 集：對照表沒有失敗（有的話逐集查原因、修好再補跑）；107（伺服器上已換成有聲音在前的版本）選的是第 1 條音軌；20 集 mp4 走的是混合路徑；下載幾集預覽檔，人工看 4:2:2 mp4 的動態畫面沒有前後跳格或梳狀紋（有的話照 design 的 Risks 加 `setfield` 修正後重做那 20 集）、聽 107 的音檔有聲音

## 10. 新聞指令

- [x] 10.1 寫 `tests/mkv2mp4wav/test_news_plan.py`（合成的小 csv）：srt_name 排序與 `--limit` 穩定、不合規格的 srt_name 成為失敗 job、撇號路徑、原始位置月份、試跑兩個根各自每月份只 ls 一次且不下載、`locate` 走定稿區 → 暫放區 → 原始位置且不看本機 `paths.mkv_path()`；`test_report.py` 加：預設紀錄落在 `kithann/mkv2mp4wav/news/`。確認紅
- [x] 10.2 實作 `tools/mkv2mp4wav/news.py`（`jobs()`、`locate()`、`listing()`、`main()`）；10.1 綠
- [x] 10.3 `tests-e2e/test_mkv2mp4wav_roundtrip.py` 加新聞部分：合成 4:2:0 mkv、影像起點 0.033、聲音起點 0，預覽檔起點仍 0.033 且驗收全過；全硬體路徑 `skipUnless(/dev/dri/renderD128)`。先紅後綠
- [x] 10.4 `tools/mkv2mp4wav/README.md` 補上新聞那段；照 README 執行 `python3 -m tools.mkv2mp4wav.news --dry-run`，列出的集數等於 `Kari-SRT/news/smkul.csv` 的列數
- [x] 10.5 實跑 `python3 -m tools.mkv2mp4wav.news --limit 2`（排序第一集是影像起點 0.033 的魯凱）：兩集的 mp4、wav 出現在 `/home/news/mp4/2021-01/`、`/home/news/wav/2021-01/`，對照表驗收全過、本機工作目錄已清空；再跑一次確認兩集都記「已存在」且沒有下載
- [x] 10.6 以 `run_in_background: true` 發動 `python3 -m tools.mkv2mp4wav.news --limit 200`（約 20 小時）：對照表沒有失敗（有的話逐集查原因、修好再補跑）；開場與每支的進度行、預計剩餘時間合理（跟實際每支用時對得上）；抽幾集預覽檔看畫面、聽音檔；本機工作目錄已清空、磁碟沒有被吃掉；把 200 支的平均用時與據此推算的全跑時間寫進回覆

## 11. 全套驗收

- [x] 11.1 先清 `__pycache__`；`.tox/flake8/bin/flake8 . --count` 為 0、unittest 全綠、e2etest 全綠、`.tox/rebuild/bin/python -m scripts.news.rebuild --verify` 通過且集數等於 inventory 未標 pending 的筆數、`python3 -m scripts.news.name_catalogue --check` 通過
- [x] 11.2 實跑 mxf2mkv 一支（用 e2e 合成檔或小資料夾 `--limit 1`）：對照表逐筆寫入、`已收尾` 為 true、紀錄落點與檔名跟改動前相同、工作目錄的指紋檔是 `.sha256`

## Workflow follow-up

- 新聞全跑：使用者照 `tools/mkv2mp4wav/README.md` 在自己的終端機發動 `python3 -m tools.mkv2mp4wav.news`（約 13 天以上，前 200 支已做會自動跳過），跑完看對照表的失敗清單；VAAPI 出錯的集數視情況用 `--software` 補跑，新聞封存檔聲音不是 FLAC 的集數交使用者決定；篩出「選用的音軌不是第一條」的集數人工聽一下。
- 使用者自行把《字幕編輯預覽檔規格》的「存放」「檔名」「起點」改成這次的裁定（SFTP、起點跟來源相同、不帶時間碼軌），並補上 4:2:2 來源走混合路徑。
- 審查後歸檔 change，同步 `mkv2mp4wav-batch`、`mxf2mkv-batch`、`master-archival`、`episode-video-location` 四份主 spec。
