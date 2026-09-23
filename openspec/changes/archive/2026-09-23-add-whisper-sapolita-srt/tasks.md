## 1. `2-asr` 改名 `2-asr-kaldi`、刪 move_outdirs

- [x] 1.1 `tests/news/test_paths.py`（紅）：Kari-SRT 與工作目錄的語音側路徑都是 `2-asr-kaldi`；whisper 的 `2-asr-whisper/1-srt-sapolita`、`辨識紀錄.csv`、工作目錄、`主播.csv`、`scripts/news/新聞語言別代號.csv` 各有一個路徑常數
- [x] 1.2 改 `scripts/news/paths.py`（綠）：`ASRMT_WORK`、`ASR_DIR` 改名，新增 whisper 相關常數
- [x] 1.3 `mv Kari-SRT/news/2-asr Kari-SRT/news/2-asr-kaldi`、`mv kithann/out/news/2-asr kithann/out/news/2-asr-kaldi`（不用 git mv）
- [x] 1.4 刪 `scripts/news/move_outdirs.py`、`tests/news/test_move_outdirs.py`，`scripts/README.md` 刪那一列
- [x] 1.5 改文件裡的路徑：`Kari-SRT/README.md`、`Kari-SRT/news/2-asr-kaldi/README.md`、`scripts/news/README.md`、`scripts/asrmt/judge_prompts/README.md`、`.claude/commands/news-stage-count.md`；`tests/asrmt/test_prompt_versions.py` 若寫死路徑一起改
- [x] 1.6 `rebuild --verify`、`unittest`、`flake8`、`name_catalogue --check` 通過（kaldi 那條照舊）

## 2. Gradio 佇列協定（scripts/asrmt/gradio.py）

- [x] 2.1 `tests/asrmt/test_gradio.py`（紅）：假串流先給 estimation、process_starts、三個 heartbeat 才給 process_completed，要回傳 process_completed 的 data；`success: false` 要丟 PipelineError 並帶原始回應
- [x] 2.2 `tests/asrmt/test_gradio.py`（紅）：上傳中文檔名 `20210227_058_晨間_Thau_邵.mp3` 的 multipart 內容正確，回傳伺服器給的路徑原字串
- [x] 2.3 `tests/asrmt/test_gradio.py`（紅）：502／503／504／529 依序重試後成功；404 當場丟不重試
- [x] 2.4 實作 `scripts/asrmt/gradio.py`（綠）：`Client(base_url, session_hash)`、`upload`、`call(fn_index, trigger_id, data, timeout)`、重試；只用標準函式庫
- [x] 2.5 `scripts/asrmt/mtclient.py` 的 `HttpTransport` 改包 `gradio.Client`；`tests/asrmt/test_mtclient.py` 不改照過

## 3. sapolita 用戶端（scripts/asrmt/sapolita.py）

- [x] 3.1 `tests/asrmt/test_sapolita.py`（紅）：辨識 `ssf` 時，假伺服器依序收到 `update_languages("邵語 (Thau)")`、`generate_srt(音檔, "ssf")`，兩次的 session_hash 相同；沒先選族別的假伺服器回 error
- [x] 3.2 `tests/asrmt/test_sapolita.py`（紅）：`ami-x-pswl` 的族別選單值是「阿美語 (’Amis)」（U+2019），`sxr` 是「拉阿魯哇語 (Hla’alua)」
- [x] 3.3 `tests/asrmt/test_sapolita.py`（紅）：`trv-x-tgdy` 查到賽德克、`trv-x-truku` 查到太魯閣；`ami_Xiug` 查不到要丟錯且不發任何請求
- [x] 3.4 `tests/asrmt/test_sapolita.py`（紅）：伺服器回空字串要丟 PipelineError，訊息含語別碼
- [x] 3.5 實作 `scripts/asrmt/sapolita.py`（綠）：16 族選單值表、42 個語別碼 → 族別表（2026-09-18 從伺服器讀下）、`recognize(audio_path, code)` 回傳 SRT 文字

## 4. 取音檔（scripts/news/audio.py）

- [x] 4.1 `tests/news/test_audio.py`（紅）：有 mkv 就不呼叫 SFTP；暫存區裡已有原檔也不用、照樣向 SFTP 取；抽完音軌後自 SFTP 抓來的原檔已刪
- [x] 4.2 `tests/news/test_audio.py`（紅）：kaldi 工作目錄已有 `audio.mp3` 時，whisper 的來源仍是影片，不讀那個檔
- [x] 4.3 `tests/news/test_audio.py`（紅）：SFTP 抓完位元組數跟遠端不符，要指名該集丟錯、刪掉不完整的檔，不抽音軌
- [x] 4.4 實作 `scripts/news/audio.py`（綠）：從 `asrmt_run.audio_source`／`extract_audio`、`asrmt_batch._fetch` 搬過來，來源順序一律「mkv → SFTP」，加位元組數比對，抽完刪原檔
- [x] 4.5 `asrmt_run.py`、`asrmt_batch.py` 改呼叫 `audio.py`；`tests/news/test_asrmt_run.py`、`test_asrmt_batch.py` 照過

## 5. 語別碼表與主播表（資料）

- [x] 5.1 寫 `scripts/news/新聞語言別代號.csv`：欄 `族語別(中)`、`語言別代號`、`語言別`、`依據`，UTF-8、不帶 BOM、LF，16 族（7 族為使用者 2026-09-18 指定：ami-x-pswl、tay-x-sql、pwn-x-pnvn、bnn-x-isbk、trv-x-tgdy、dru-x-ngdr、pyu-x-pym；9 族單一語別照 smkul.csv 代號）
- [x] 5.2 寫 `Kari-SRT/news/主播.csv`：照 `kithann/tuiue/0918/0918-1617-smkul-kari-8e.md` 的主播表，一位主播一列；UTF-8、不帶 BOM、LF

## 6. 逐集與整批（scripts/news/whisper_run.py）

- [x] 6.1 `tests/news/test_whisper_run.py`（紅）：假 sapolita 回傳含「族語：／華語：」兩行與片尾「ʼa ʼa ʼa…」、檔尾沒有換行的文字，存下的 SRT 逐 byte 相同（不補換行、不加 0.5 秒留白），存在 `<年-月>/<成果檔名>.srt`
- [x] 6.2 `tests/news/test_whisper_run.py`（紅）：節目目錄 `ami` 送 `ami-x-pswl`；`族語別(中)` 賽德克（代號 `trv`）送 `trv-x-tgdy`、太魯閣（`trv-x-truku`）送 `trv-x-truku`
- [x] 6.3 `tests/news/test_whisper_run.py`（紅）：新聞語言別代號.csv 缺某族、或代號不在 `scripts/languages.py`，中止並指名，不發請求
- [x] 6.4 `tests/news/test_whisper_run.py`（紅）：OCR 字幕第 2 條「我是Sulryape Gadhu」→ 主播名 `Sulryape Gadhu`；沒有 2-vision、或前 15 條沒有「我是」→「不明」
- [x] 6.5 `tests/news/test_whisper_run.py`（紅）：辨識紀錄欄位與順序；重做同一集覆寫那一列；列序照成果檔名；UTF-8、不帶 BOM、LF（寫出的檔開頭不是 EF BB BF、沒有 \r）
- [x] 6.6 `tests/news/test_whisper_run.py`（紅）：續跑——SRT 與紀錄都在的集跳過；只有 SRT 沒紀錄的集重做
- [x] 6.7 `tests/news/test_whisper_run.py`（紅）：整批依序送、前一集回來才送下一集；一集失敗後繼續、最後非零結束；失敗的集沒有 SRT 也沒有紀錄列，暫存 mp3 與下載的影片都刪掉
- [x] 6.8 實作 `scripts/news/whisper_run.py`（綠）：`python3 -m scripts.news.whisper_run [<成果檔名>…] [--server URL] [--limit N]`，預設正式機

## 7. 文件與驗收

- [x] 7.1 寫 `Kari-SRT/news/2-asr-whisper/README.md`：各層是什麼、從哪裡做出來、誰讀它、語別碼怎麼決定、主播名怎麼取、量測數字（25 倍速、段長）、已知幻覺
- [x] 7.2 `scripts/README.md` 補 `gradio.py`、`sapolita.py`、`audio.py`、`whisper_run.py`、`新聞語言別代號.csv`；`scripts/news/README.md` 補 whisper 這條線的指令
- [x] 7.3 `tests/README.md` 補 design 裡 spec × scenario × 測試檔那幾列
- [x] 7.4 `.claude/commands/news-stage-count.md` 加 whisper 一列
- [x] 7.5 `tox -e flake8`、`tox -e unittest`、`tox -e rebuild`（`rebuild --verify`）、`name_catalogue --check` 全部通過

## 8. 正式機

- [x] 8.1 正式機上跑 1 集（`20210227_058_晨間_Thau_邵`），確認回傳格式與測試機相同、記下辨識秒數
- [x] 8.2 整批 969 集：`run_in_background` 發動，不用 `nohup &`、不用 `pgrep` 輪詢；跑完核對 SRT 數＝紀錄列數＝smkul.csv 筆數，失敗的集數記進 `kithann/TODO.md`
