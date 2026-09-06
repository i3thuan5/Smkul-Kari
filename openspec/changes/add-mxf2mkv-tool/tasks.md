## 1. 先把網子架好

- [x] 1.1 Spike：確認 ffmpeg 的 lavfi 合成得出「3 秒、mpeg2video、兩條 pcm_s24le 音軌」的 mxf，且 `ffprobe` 讀得出兩條音軌。做不出來就改用 `.mov`，並在 design 的 Risks 那節記下實際採用的容器與原因。
- [x] 1.2 `tox.ini` 的 `unittest` env 加上 `discover -s tests/transcode`，跑 `.tox/unittest/bin/python -m unittest discover -s tests/transcode -t .`，確認既有 46 個測試在 CI 環境（只有 numpy 與 Pillow）全綠。有紅的先修好再往下——那是動 `encode_master.sh` 之前唯一的護欄。

## 2. `scripts/transcode/audio_tracks.py`：N 軌決策純函式

- [x] 2.1 開 `tests/mxf2mkv/__init__.py` 與 `tests/mxf2mkv/test_audio.py`，寫「一條音軌不做去留判斷」「兩軌 md5 相同 → 留一軌」「兩軌不同 → 兩軌都留」「三軌中兩條相同 → 留兩軌」「來源與封存 md5 不符 → 回報不相符並指出是哪一軌」五組測試。**跑起來要紅**（模組還不存在）。
- [x] 2.2 寫 `scripts/transcode/audio_tracks.py`：吃來源 md5 列表與封存 md5 列表，回傳「是否逐位元相符」「重複分組」「該留的軌索引」「一句給人看的說明」。零 I/O。跑到綠。
- [x] 2.3 補「給人看的說明」的測試與實作：兩軌相同時是「兩軌相同，留一軌」，不同時是「兩軌不同，兩條都留」，三軌以上要把軌數寫進去。這句話會進對照表，是日後決定拿哪一條音軌做語音辨識的依據。

## 3. `scripts/transcode/encode_master.sh`：一趟 ffmpeg、N 軌通吃

- [x] 3.1 開 `tests/transcode/test_encode_master.py`，測 dry-run 印出的 ffmpeg 參數：1 軌／2 軌／3 軌各自的 `-map` 與 md5 輸出要展開成幾個、對應到哪一軌；來源是整數 PCM 時走 flac、其他走 copy。**跑起來要紅**。
- [x] 3.2 給 `encode_master.sh` 加 dry-run 開關（比照 `sftp.sh` 的 `SFTP_DRY_RUN=1`：印出要送出的 ffmpeg 指令就結束），跑到 3.1 綠。
- [x] 3.3 改 `encode_master.sh` 的本體：`ffprobe` 數出音軌數，`-map` 依實際軌數展開，每軌加一個 `-f md5` 輸出，全部在同一次 ffmpeg 呼叫裡。移除開頭那趟「比對兩條音軌」的預先讀取，以及結尾那趟自己做的驗證——兩者都改由呼叫端用 md5 檔完成。
- [x] 3.4 改參數契約：輸出從「一個 dst 檔案」改為「一個工作目錄加一個名字」，產出 `<名>.all.mkv` 與 `<名>.src-a<i>.md5`。更新腳本開頭的註解：保留既有 CRF／pix_fmt／FLAC 的實測來歷（那些理由沒變），加上「為什麼是一趟」與「為什麼不再自己決定音軌去留」。
- [x] 3.5 `.tox/flake8/bin/flake8` 與 `bash shellcheck.sh` 跑過。

## 4. `scripts/transcode/archive_batch.py`：跟著新契約走

- [x] 4.1 在 `tests/transcode/test_archive_batch.py` 加測試：`_encode()` 走完三段（編碼＋算 md5 → `audio_tracks` 決定去留 → `-c copy` 重新封裝），音訊不相符時丟出 `PipelineError` 且不留成品在正式位置。**跑起來要紅**。
- [x] 4.2 改 `_encode()` 走三段流程，跑到綠。`O_EXCL` 鎖、`.partial.mkv` 改名、SFTP 抓檔、時長比對、上傳與刪除全部不動。
- [x] 4.3 跑 `.tox/unittest/bin/python -m unittest discover -s tests/transcode -t .`，46＋筆全綠。

## 5. `tools/mxf2mkv/walk.py`：掃描與路徑對應

- [x] 5.1 開 `tests/mxf2mkv/test_paths.py`：來源根 basename 進遠端路徑、子資料夾相對路徑照抄、副檔名換 `.mkv`、非 `.mxf` 略過、檔名含引號／反斜線／控制字元要拒絕。**紅**。
- [x] 5.2 開 `tests/mxf2mkv/test_scan.py`：遞迴掃描的順序穩定、遠端已存在且位元組數相符則跳過、位元組數不符（半截上傳）要重做。**紅**。
- [x] 5.3 寫 `tools/mxf2mkv/__init__.py` 與 `walk.py`，跑到 5.1、5.2 綠。

## 6. `tools/mxf2mkv/report.py`：紀錄與對照表

- [x] 6.1 開 `tests/mxf2mkv/test_report.py`：落點是 `kithann/mxf2mkv/<來源名>/`（外層只有來源名）、檔名帶 CST 日期時間與來源名、同一來源第二次執行放進同一個目錄且不動舊檔、檔名相撞時加 `-2` 後綴、對照表是 `ensure_ascii=False, indent=2, sort_keys=True` 的 JSON、每筆欄位齊全（來源相對路徑與位元組數、遠端路徑與位元組數、來源音軌數、保留音軌數、音軌說明、是否逐位元相符、耗時、結果）。**紅**。
- [x] 6.2 寫 `report.py`，跑到綠。建檔用 `O_EXCL`，撞名加後綴重試。時間用 `TZ=Asia/Taipei`。

## 7. `tools/mxf2mkv/upload.py`：送上 SFTP

- [x] 7.1 開測試（放 `tests/mxf2mkv/test_scan.py` 或另開檔）：以 `SFTP_DRY_RUN=1` 驗指令拼法——逐層 `mkdir` 由外而內、`put` 的兩個路徑是分開的引數、上傳後讀遠端位元組數。**紅**。
- [x] 7.2 寫 `upload.py`，呼叫 `scripts/news/sftp.sh`，跑到綠。位元組數不符要丟錯。

## 7b. `sftp.sh` 加 `rename`（實作當中發現的）

跳過的判準原本規劃比對位元組數，但成品幾個位元組要轉完才知道，而轉檔正是跳過要省下的時間。改成上傳暫名、位元組數對了才改名，「最終名稱存在」本身就是完整的證據。使用者裁定 2026-09-06。

- [x] 7b.1 `tests/news/test_sftp_cli.py` 加 `rename` 的測試：兩個路徑各自引號、都過 `check_path`、剛好吃兩個引數、**不加** `mkdir` 那個開頭的 `-`。**紅**。
- [x] 7b.2 `scripts/news/sftp.sh` 加 `rename` 動詞，更新用法字串與檔頭註解，跑到綠。既有的 `test_unknown_verb_is_refused` 拿 `rename` 當未知動詞，改用別的。
- [x] 7b.3 `upload.py` 改走 `put` 到 `<遠端>.partial` → 比對位元組數 → `rename`；加 `already_there()` 當跳過判準。
- [x] 7b.4 spec 的兩個 scenario 與 design 同步更新機制描述。

## 8. `tools/mxf2mkv/run.py` 與 `__main__.py`：串起來

- [x] 8.1 開 `tests/mxf2mkv/test_failure.py`：一支失敗要記錄原因並繼續下一支、批次結束時有失敗則離開碼非零、全成功或全跳過則為零、失敗時工作目錄保留並印出路徑。**紅**。
- [x] 8.2 寫 `run.py`：一支的完整流程（`encode_master.sh` → `audio_tracks` → remux → `upload`），成功後刪掉該支的全部本機產物，回傳結果紀錄。
- [x] 8.3 寫 `__main__.py`：參數與預設值（`--src` 必填、`--dst-root /home/mkv-raw`、`--work` 以 `mkdtemp(prefix="mxf2mkv-", dir="/tmp")` 產生、`--report-dir kithann/mxf2mkv`、`--crf 23`、`--limit 0`、`--dry-run`），序列處理不提供 `-j`，正常結束刪工作目錄、有失敗則保留。跑到 8.1 綠。
- [x] 8.4 測 `--dry-run`：列出每支的來源、遠端路徑與「會處理／會跳過」，且不建立、修改或刪除任何本機或遠端檔案，也不送出會改變遠端狀態的指令。

## 9. 端到端

- [x] 9.1 寫 `tests/e2e/test_mxf2mkv_roundtrip.py`：用 1.1 的做法合成小 mxf（兩軌相同一份、兩軌不同一份、三軌一份），跑完整條，斷言音訊逐位元相符、保留軌數分別是 1／2／依重複情形而定；產物跑完刪除，git 不留 mxf。
- [x] 9.2 `.tox/e2etest/bin/python -m unittest discover -s tests/e2e -t .` 全綠。

## 10. 文件

- [x] 10.1 寫 `tools/mxf2mkv/README.md`：這是什麼、怎麼跑（含一行可複製的指令）、產出在哪、失敗了去哪看。不記 design／task 編號。
- [x] 10.2 更正 `.claude/skills/video-subtitle-srt/壓縮率分析.md`：第 23 行「這批兩軌 MD5 相同」是拿一支量的；補上 63 支全數 ffprobe 的結果（35 支一軌、28 支兩軌、無多聲道、無超過兩軌）與兩軌差異的實測數字。
- [x] 10.3 `scripts/README.md` 的 `transcode/` 那段補上新的三段流程與 `tools/mxf2mkv/` 的關係。
- [x] 10.4 確認整份 change 沒有留下 `requirements.txt` 或任何新的 Python 套件。

## 11. 驗收

- [x] 11.1 `.tox/flake8/bin/flake8 . --count`、`bash shellcheck.sh`、`.tox/rebuild/bin/python -m scripts.news.rebuild --verify`、`python3 -m scripts.news.name_catalogue --check` 全過。集數以「`rebuild --verify` 說的集數＝inventory 裡沒標 `pending` 的筆數」推算，不記死數字。
- [x] 11.2 `.tox/unittest/bin/python -m unittest discover` 對 `tests/ocr`、`tests/srtlib`、`tests/asrmt`、`tests/news`、`tests/transcode`、`tests/mxf2mkv` 全綠。
- [ ] 11.3 真跑一次：對一個只放兩三支母帶的資料夾跑 `--dry-run`，確認路徑對應正確；再實跑，確認遠端結構、對照表內容、本機清乾淨。這一步要使用者自己執行（隨身硬碟與 SFTP 憑證都在他那邊），把指令寫進 `kithann/tuiue/` 的回覆檔。
- [x] 11.4 `shellcheck.sh` 的 `find` 只排除 `./venv/`，會掃到 `kithann/` 底下三千多支舊 session 的臨時指令檔——跑兩分多鐘而且**永遠是紅的**，`tox -e shellcheck` 因此不是個能用的關卡。排除清單改成跟 `tox.ini` 的 flake8 那節一致（`.git`／`.tox`／`venv`／`kithann`／`scratchpad`），並用 `-prune` 而非 `-not -path`。順帶設 `LC_ALL=C.utf8`：容器 locale 是 POSIX，shellcheck 要印出含漢字的原始碼行時會失敗成 `commitBuffer: invalid argument`，真正的訊息被蓋掉。使用者裁定 2026-09-06。
