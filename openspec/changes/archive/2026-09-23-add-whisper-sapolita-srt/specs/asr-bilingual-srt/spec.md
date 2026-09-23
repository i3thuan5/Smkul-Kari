## MODIFIED Requirements

### Requirement: 產出存放於 Kari-SRT

每集產出 SHALL 以 `srt_name` 命名，按產出順序存於
`Kari-SRT/news/2-asr-kaldi/` 的編號階段目錄：
`1-words/<srt_name>.json`（逐詞辨識結果）、
`2-srt-raw/<srt_name>.srt`（族語／華語兩行對照）、
`3-srt-ai/<srt_name>.srt`（加機器譯文的三行對照）、
`4-srt-quality/<srt_name>.srt`（族華對應品質）。跨集共用的快取存於
`mt-cache/`（機器譯文）與 `quality-cache/`（品質判定），不分月份。
`Kari-SRT/news/2-asr-kaldi/README.md` SHALL 說明各階段檔案的產出流程與
輸出入對應關係。

#### Scenario: 檔案齊備

- **WHEN** 一集流程完成
- **THEN** `1-words/`、`2-srt-raw/`、`3-srt-ai/`、`4-srt-quality/`
  各目錄下存在該 `srt_name` 的檔案，無其他階段目錄

#### Scenario: 產出順序可讀

- **WHEN** 不熟流程的人瀏覽 `Kari-SRT/news/2-asr-kaldi/`
- **THEN** 目錄編號即產出順序，README 說明每個檔由哪支程式、
  吃哪些輸入產生

### Requirement: 翻譯快取與可續跑

族語→華語機器翻譯 SHALL 只做這一個方向。譯文 SHALL 以內容定址存於
`Kari-SRT/news/2-asr-kaldi/mt-cache/`（每個引擎一個 JSONL 檔、一列一筆，
鍵為引擎、方向、語言碼、原文）：同一鍵 SHALL NOT 重複呼叫服務；
中斷後重跑 SHALL 從快取接續。空的族語行 SHALL NOT 送翻。服務
SHALL 一次一個請求、請求之間固定停頓；暫時性閘道錯誤 SHALL 重試，
其餘錯誤 SHALL 指名中止。

#### Scenario: 命中不呼叫服務

- **WHEN** 某族語行已在快取
- **THEN** 不向服務發出請求，譯文由快取取得

#### Scenario: 中斷後接續

- **WHEN** 一集翻到一半中斷後重跑
- **THEN** 已翻的行全部命中，只有未翻的行發出請求

#### Scenario: 空行不送翻

- **WHEN** 條目族語行為空
- **THEN** 不發出請求，譯文為空字串

### Requirement: 音檔由該集影片抽出，不另記音檔位置

語音側要辨識的音檔 SHALL 由該集的**影片**抽出音軌取得，SHALL NOT 依賴
節目目錄記錄任何音檔路徑——節目目錄 SHALL NOT 有音檔位置欄。

影片的正本在遠端；取音軌的來源 SHALL 依序為本機封存 mkv、依節目目錄的
`原始影片檔案位置` 自遠端取檔，SHALL NOT 看本機暫存區裡既有的原檔。自遠端
取得的原檔 SHALL 比對位元組數，不符 SHALL 指名該集中止；抽完音軌後 SHALL
刪除該原檔（一支約 2.2 GB，磁碟放不下累積）。遠端也取不到時 SHALL 指名
該集並以非零狀態結束，SHALL NOT 靜默跳過。

whisper 那條（見 whisper-asr-srt）用同一個取音檔的來源順序。

理由：外部編目資料的音檔路徑推導不出來——量過 983 列，只有 835 列的
音檔與影片同資料夾同主檔名，69 列主檔名不同（影片帶族語前綴、音檔沒有），
64 列根本不同資料夾，15% 無規則可循。影片位置那一欄是整條流程都在用的，
音軌從它抽就不必再養第二份只服務單一步驟、又推導不出來的路徑。

#### Scenario: 有封存 mkv 就直接抽

- **WHEN** 某集有本機封存 mkv，執行語音側辨識
- **THEN** 音軌自 mkv 抽出，過程不向遠端索取任何檔案

#### Scenario: 暫存區的原檔不用、抓來的用完就刪

- **WHEN** 某集沒有封存 mkv，暫存區裡有一份切 cue 時留下的原檔
- **THEN** 仍自遠端取檔；抽完音軌後，自遠端取得的原檔已刪除

#### Scenario: 影片不在本機時自遠端取

- **WHEN** 某集沒有封存 mkv，執行語音側辨識
- **THEN** 依節目目錄的 `原始影片檔案位置` 自遠端取得影片後抽出音軌

#### Scenario: 遠端也取不到時指名中止

- **WHEN** 某集的影片本機沒有、遠端依 `原始影片檔案位置` 也取不到
- **THEN** 流程指名該集並以非零狀態結束

#### Scenario: 節目目錄沒有音檔欄

- **WHEN** 檢視節目目錄的表頭
- **THEN** 沒有任何記錄音檔位置的欄位
