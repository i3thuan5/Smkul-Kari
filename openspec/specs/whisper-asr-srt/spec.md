# whisper-asr-srt Specification

## Purpose

把族語新聞節目目錄的每一集送 sapolita（whisper 族語辨識服務）取得 SRT，原樣存進 Kari-SRT，並逐集記下送出的語別與主播，作為族華平行語料的族語那一側。

## Requirements

### Requirement: 伺服器回傳的 SRT 原樣存放

每集 SHALL 以 `成果檔名` 命名，存於 `Kari-SRT/news/2-asr-whisper/1-srt-sapolita/<年-月>/<成果檔名>.srt`（`<年-月>` 取自播出日期）。檔案內容 SHALL 與 sapolita 回傳的文字逐 byte 相同：分段、時間戳、每段的「族語：」「華語：」兩行、片尾配樂處的幻覺文字，SHALL NOT 重排、合併、刪除或改寫，SHALL NOT 加 SRT 邊界留白。

理由：這一層是伺服器回應的正本，重跑要花伺服器時間，而且伺服器上的模型會更新；任何整理放到下一層做，這一層才能用來比較、重做。

伺服器的段落起訖是 VAD 切出的語音實際邊界、沒有留白（Formosan-AI `asr/subtitles.py` 只把秒數換成毫秒）。這一層 SHALL 保存這個真實邊界，是「SRT 邊界各延伸 0.5 秒」規定的例外，比照時間軸資料（`cues.json`）；要留白的 SRT SHALL 由下游從這一層算出，SHALL NOT 回寫這一層。使用者裁定 2026-09-18。

#### Scenario: 存檔與回傳相同

- **WHEN** 一集辨識完成
- **THEN** 存下的 SRT 與伺服器回傳的文字逐 byte 相同，段數與時間戳都沒有變

#### Scenario: 片尾幻覺照存

- **WHEN** 伺服器回傳的最後幾段是配樂處的幻覺（例：整段「ʼa ʼa ʼa…」，或出現別族的句子）
- **THEN** 照樣存下，不刪不改

#### Scenario: 檔尾照原樣

- **WHEN** 伺服器回傳的文字最後一段後面沒有換行
- **THEN** 存下的檔最後一個 byte 也不是換行

#### Scenario: 不加邊界留白

- **WHEN** 檢查任一段的起訖時間
- **THEN** 與伺服器回傳的時間相同，沒有往外延伸 0.5 秒

### Requirement: 語別碼依新聞語言別代號表決定

送 sapolita 的語別碼 SHALL 依 `scripts/news/新聞語言別代號.csv` 決定：該表一族一列，欄位為 `族語別(中)`、`語言別代號`、`語言別`、`依據`，同一族的所有集數 SHALL 用同一個語別碼。表內每個 `語言別代號` SHALL 是 sapolita 選單上有的語別碼，也 SHALL 查得到於 repo 內的族語別／語言別代號對照表。

節目目錄某一集的族語別在表上查不到、或表上的代號在對照表查不到時，SHALL 中止並指名該集或該列，SHALL NOT 送出、SHALL NOT 猜一個代號。

#### Scenario: 多語別的族換成語別碼

- **WHEN** 節目目錄某集的 `語言別代號` 是 `ami`（只記到族語別）
- **THEN** 送出表上阿美那一列的語別碼 `ami-x-pswl`

#### Scenario: 賽德克與太魯閣不混淆

- **WHEN** 節目目錄某集的 `語言別代號` 是 `trv`（賽德克），另一集是 `trv-x-truku`（太魯閣）
- **THEN** 前者送 `trv-x-tgdy`，後者送 `trv-x-truku`；兩者都查表決定，不看代號前綴

#### Scenario: 表上查不到就中止

- **WHEN** 某集的族語別在新聞語言別代號表上沒有對應列
- **THEN** 流程指名該集並以非零狀態結束，不送出任何請求

### Requirement: 送出前先選族別

sapolita 的語別選單綁在連線 session 上。每一次辨識 SHALL 在同一個 session 先選該語別所屬的族別，再送辨識；族別 SHALL 依語別碼查表得出，SHALL NOT 由代號前綴推測；族別選單值 SHALL 與伺服器上的字串一字不差（例：「阿美語 (’Amis)」的撇號是 U+2019）。

#### Scenario: 非預設族別

- **WHEN** 辨識一集邵語（`ssf`）
- **THEN** 同一個 session 先選「邵語 (Thau)」再送辨識，伺服器接受並回傳 SRT

### Requirement: 伺服器錯誤要指名中止

伺服器回報錯誤、回報不成功、或回傳空字串時，SHALL 指名該集與送出的語別碼中止該集，SHALL NOT 寫出 SRT、SHALL NOT 寫入辨識紀錄。整批執行時，一集失敗 SHALL 報告後續做下一集，最後以非零狀態結束。

#### Scenario: 伺服器回錯誤

- **WHEN** 伺服器對某集回傳 error 且沒有任何訊息
- **THEN** 輸出指名該集與語別碼的錯誤，該集沒有 SRT 也沒有紀錄列

### Requirement: 一次只送一集

對 sapolita SHALL 一次只有一個辨識請求在進行，SHALL NOT 平行送出多集。

#### Scenario: 整批依序送

- **WHEN** 整批執行多集
- **THEN** 前一集的結果收到之後，才送下一集

### Requirement: 辨識紀錄

`Kari-SRT/news/2-asr-whisper/1-srt-sapolita/辨識紀錄.csv` SHALL 一集一列，欄位為：`成果檔名`、`語言別代號`（實際送出的語別碼）、`主播名`、`伺服器`、`辨識日期`（CST）、`音長秒`、`段數`。列序 SHALL 依 `成果檔名` 排序。同一集重做 SHALL 覆寫該列，SHALL NOT 多出一列。

`主播名` SHALL 取自該集 OCR 字幕的開頭（前 15 條）裡「我是」後面的文字；取不到（沒有該集的 OCR 字幕，或開頭沒有「我是」）SHALL 寫「不明」，SHALL NOT 留空。

#### Scenario: 主播名從字幕取

- **WHEN** 某集 OCR 字幕第 2 條是「我是Sulryape Gadhu」
- **THEN** 該集的主播名是 `Sulryape Gadhu`

#### Scenario: 取不到寫不明

- **WHEN** 某集沒有 OCR 字幕，或開頭 15 條沒有「我是」（例：雅美新聞）
- **THEN** 該集的主播名是「不明」

#### Scenario: 重做覆寫同一列

- **WHEN** 已有紀錄的一集重新辨識
- **THEN** 紀錄表該集仍只有一列，內容是新的結果

### Requirement: 可續跑

一集 SHALL 在 SRT 與紀錄列都存在時才算做完；整批執行 SHALL 跳過做完的集。只有 SRT、沒有紀錄列的集（寫到一半中斷）SHALL 重做。

#### Scenario: 中斷後重跑

- **WHEN** 整批做到一半中斷後重跑
- **THEN** SRT 與紀錄都在的集數不再送伺服器，其餘的照順序做

#### Scenario: 寫到一半的集重做

- **WHEN** 某集有 SRT 但紀錄表沒有該列
- **THEN** 該集重新辨識，完成後 SRT 與紀錄列都在

### Requirement: 音檔來源

辨識用的音檔 SHALL 由該集影片抽出音軌取得，來源依序為本機封存 mkv、SFTP 上節目目錄的 `原始影片檔案位置`；SHALL NOT 使用 kaldi 工作目錄裡既有的 `audio.mp3`。自 SFTP 取得的影片 SHALL 比對位元組數，不符 SHALL 指名該集中止。抽完音軌後，自 SFTP 取得的影片 SHALL 刪除。

#### Scenario: 有封存 mkv 就不下載

- **WHEN** 某集有本機封存 mkv
- **THEN** 音軌自 mkv 抽出，不向 SFTP 索取

#### Scenario: 下載不完整

- **WHEN** 自 SFTP 取得的影片位元組數與遠端不符
- **THEN** 流程指名該集中止，不送辨識

#### Scenario: 不用 kaldi 的音檔

- **WHEN** kaldi 工作目錄裡已有該集的 `audio.mp3`
- **THEN** 仍由影片抽音軌，不讀那個檔

### Requirement: 主播表

`Kari-SRT/news/主播.csv` SHALL 一位主播一列，欄位為：`族語別(中)`、`主播族語名`、`主播漢名`、`語言別`、`語言別代號`、`抽聽的集`、`語別依據`。語別查不到時 `語言別代號` SHALL 寫族語別代號，`語別依據` SHALL 寫明查不到（例：「網頁未載」），SHALL NOT 留空。

#### Scenario: 網頁有寫語別

- **WHEN** 主播專區寫明 Ohay Sewana 播的是海岸阿美語
- **THEN** 該列 `語言別代號` 為 `ami-x-pswl`，`語別依據` 記網址與查詢日期

#### Scenario: 網頁沒寫語別

- **WHEN** 主播專區沒寫 Tasaw Watan 的語別
- **THEN** 該列 `語言別代號` 為 `tay`，`語別依據` 寫「網頁未載」
