# tests/sftpbatch/：批次骨架（mxf2mkv、mkv2mp4wav 共用）

`tools/sftpbatch/` 是從 `tools/mxf2mkv/` 搬出來的批次迴圈（`batch.py`）、紀錄與對照表（`report.py`）、SFTP 上傳（`upload.py`），兩支工具共用一份。這裡的測試大部分是跟著程式從 `tests/mxf2mkv/` 原樣搬來的。

| spec | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| mxf2mkv-batch：失敗續跑 | 一支失敗做下一支、離開碼最後才講；危險檔名（引號、反斜線、控制字元）只擋那一支，成果檔名的撇號（`Hla'alua`）不可擋；有失敗保留工作目錄並印出路徑；試跑不建任何檔 | `test_batch.py` |
| mxf2mkv-batch：中斷 | Ctrl+C 不可被「記下來、做下一支」吞掉：整批停、紀錄寫「中斷」 | `test_batch.py` |
| mxf2mkv-batch：對照表格式不變 | 迴圈搬到 sftpbatch 後，mxf2mkv 對照表每筆的鍵仍是 `src`；mkv2mp4wav 用 `srt_name` | `test_batch.py`、`../mxf2mkv/test_failure.py` |
| mkv2mp4wav-batch：成果檔名不合規格 | 目錄某列名稱不合規格：那集記失敗並指名，不交給 worker、不組遠端路徑，下一集照做 | `test_batch.py` |
| mkv2mp4wav-batch：一集內一種產出失敗 | worker 回傳 `結果: 失敗`（不是丟例外）也要算進失敗，離開碼才不會說一切順利 | `test_batch.py` |
| mxf2mkv-batch：對照表逐筆寫入 | 做完第 N 筆就讀得到前 N 筆、`已收尾` false；正常結束 true（`kithann/mxf2mkv/` 有 3 份空對照表，就是整批結束才寫、中途停掉留下的） | `test_report.py` |
| mxf2mkv-batch：對照表逐筆寫入 | 寫暫存檔寫到一半當掉：磁碟上的對照表仍是上一次的完整 JSON，不留 `.tmp` | `test_report.py` |
| mxf2mkv-batch：紀錄不覆蓋 | 同一分鐘跑兩次加 `-2`；兩個名字只搶到一個時不留孤兒 `.log`；JSON 排版、中文不轉義、鍵排序 | `test_report.py` |
| mxf2mkv-batch：紀錄落點 | 搬移後 mxf2mkv 的紀錄仍是 `<report>/<來源名>/<MMDD-HHMM>_<來源名>.log`、`.manifest.json` | `../mxf2mkv/test_failure.py` |
| mxf2mkv-batch：上傳 | `.partial` → 比位元組數 → 改名；不符不改名；零位元組的最終名稱不算完成；遠端資料夾由外而內逐層建 | `test_upload.py` |
