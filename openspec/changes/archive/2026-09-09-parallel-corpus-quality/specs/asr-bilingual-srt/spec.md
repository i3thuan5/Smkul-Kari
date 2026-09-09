## MODIFIED Requirements

### Requirement: 雙語 SRT 與交付 SRT 逐行同軸

每集雙語 SRT 的條目 SHALL 與同一集交付字幕 SRT 的條目一一對應：條數、
編號與 start/end 時間戳完全相等，且交付字幕的華語文字直接併入條目，
不靠跨檔對照。條目 SHALL 由與交付 SRT 同一套組裝規則（同一份
`cues.json`、同樣的同文合併、去頭、間距與 0.5 秒留白規則）推導，而非
另行實作一份時間戳邏輯。每個條目對應的**真實時間窗**（留白前、合併
來源 cue 的聯集範圍）SHALL 供詞投影使用。

同軸性質 SHALL 由離線重建驗證把關（見 srt-data-store 的「語音側交付
可離線逐 byte 重建且與影像側同軸」）：影像側時間軸換版後，語音側
SHALL 由逐詞結果重投影＋重新 render 使兩側恢復同軸，驗證才會通過。
語音側尚未產出的集數不受此約束——這條只在兩側都有交付時成立。

#### Scenario: 逐行 zip 比對成立

- **WHEN** 拿同一集的雙語 SRT 與交付字幕 SRT 逐行配對
- **THEN** 每一對的 index 與 start/end 時間戳完全相等，僅文字行不同

#### Scenario: cues.json 不被改動

- **WHEN** 雙語 SRT 產出完成
- **THEN** 該集 `cues.json` 的內容與產出前逐 byte 相同

#### Scenario: 時間軸換版後失去同軸會被驗證抓到

- **WHEN** 某集語音側**已有** `2-srt-raw`，影像側時間軸更新並重產
  交付 SRT，語音側尚未重投影，執行離線重建驗證
- **THEN** 驗證以非零狀態結束並指名該集；重投影＋重新 render 後
  驗證恢復通過

### Requirement: 整集逐詞辨識結果落地保存

語音辨識 SHALL 對整集音訊連續解碼（不得逐 cue 切割音訊），並把逐詞
結果（詞文字、start、end、confidence）完整存檔。SRT 的族語行只是
此逐詞結果的投影視圖；投影 SHALL 以條目的真實時間窗為準，把每個詞
歸入與其重疊時間最大的條目，不改詞文字與詞序。未落在任何條目內的詞
SHALL 保留在逐詞結果中、不進 SRT。

投影 SHALL 是純函式：同一份逐詞結果與同一條時間軸每次算出相同的
條目。投影結果 SHALL NOT 落地為獨立的中間檔——任何需要它的步驟
（render、翻譯、判定、重建驗證）都當場重算。追查某條族語行的來源
時，SHALL 能由逐詞結果與時間軸重算出組成該行的每個詞及其時間戳與
confidence。

#### Scenario: 中間過程可追溯

- **WHEN** 追查某條目族語行的來源
- **THEN** 由逐詞結果與該集時間軸重算，即得組成該行的每個詞及其
  時間戳與 confidence，不需要任何中間檔

#### Scenario: 逐詞結果可重投影

- **WHEN** cue 時間軸更新（例如邊界精修）後重跑投影
- **THEN** 不需要重新辨識音訊即可從既有逐詞結果產生新的族語行

#### Scenario: 跨界詞歸戶

- **WHEN** 一個詞的時間範圍跨越兩個條目的邊界
- **THEN** 該詞只歸入重疊時間較大的那個條目

#### Scenario: 投影是純函式

- **WHEN** 對同一份逐詞結果與同一條時間軸投影兩次
- **THEN** 兩次結果完全相同

### Requirement: 產出存放於 Kari-SRT

每集產出 SHALL 以 `srt_name` 命名，按產出順序存於
`Kari-SRT/news/2-asr/` 的編號階段目錄：
`1-words/<srt_name>.json`（逐詞辨識結果）、
`2-srt-raw/<srt_name>.srt`（族語／華語兩行對照）、
`3-srt-ai/<srt_name>.srt`（加機器譯文的三行對照）、
`4-srt-quality/<srt_name>.srt`（族華對應品質）。跨集共用的快取存於
`mt-cache/`（機器譯文）與 `quality-cache/`（品質判定），不分月份。
`Kari-SRT/news/2-asr/README.md` SHALL 說明各階段檔案的產出流程與
輸出入對應關係。

#### Scenario: 檔案齊備

- **WHEN** 一集流程完成
- **THEN** `1-words/`、`2-srt-raw/`、`3-srt-ai/`、`4-srt-quality/`
  各目錄下存在該 `srt_name` 的檔案，無其他階段目錄

#### Scenario: 產出順序可讀

- **WHEN** 不熟流程的人瀏覽 `Kari-SRT/news/2-asr/`
- **THEN** 目錄編號即產出順序，README 說明每個檔由哪支程式、
  吃哪些輸入產生

### Requirement: 條目文字行——兩行對照格式

`2-srt-raw/<srt_name>.srt` 每個條目 SHALL 恰為兩行：「族語：」為投影
到該條目的辨識詞按時間順序以空白連接，SHALL NOT 調換順序、增刪或
改寫任何詞；「華語：」為該條目的交付字幕原文，SHALL NOT 改寫。這兩個
短標籤是正式交付的格式，SHALL NOT 換成分析用的來源標籤（那是
`3-srt-ai`、`4-srt-quality` 的事）。條目 SHALL 永遠逐條目輸出、不整併。
條目真實時間窗內沒有任何辨識詞時，「族語：」行 SHALL 保留前綴、文字
留空。檔內 SHALL NOT 出現任何機器翻譯文字。

#### Scenario: 投影完成即可產出

- **WHEN** 投影完成
- **THEN** 兩行對照 SRT 即可 render：每條「族語：」「華語：」，
  時間戳與交付 SRT 相同

#### Scenario: 無語音條目

- **WHEN** 條目真實時間窗內沒有任何辨識詞
- **THEN** 「族語：」行保留前綴、文字為空，「華語：」行照常輸出

## ADDED Requirements

### Requirement: 翻譯快取與可續跑

族語→華語機器翻譯 SHALL 只做這一個方向。譯文 SHALL 以內容定址存於
`Kari-SRT/news/2-asr/mt-cache/`（每個引擎一個 JSONL 檔、一列一筆，
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
