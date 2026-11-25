# tests/mkv2mp4wav/：開會了與新聞的預覽 mp4、訓練用 WAV

`tools/mkv2mp4wav/` 的單元測試；外部動作（下載、ffprobe、量音量、編碼、轉音檔、上傳）都在 `fakes.py` 換成假的，全部離線。用真的 ffmpeg 走一集的在 `tests-e2e/test_mkv2mp4wav_roundtrip.py`（軟體路徑必跑；全硬體、混合路徑要有 `/dev/dri/renderD128`）。批次迴圈、對照表、上傳的測試在 [../sftpbatch/README.md](../sftpbatch/README.md)。

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
