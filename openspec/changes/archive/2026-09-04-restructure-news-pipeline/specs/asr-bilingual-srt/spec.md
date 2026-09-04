# asr-bilingual-srt Delta

## MODIFIED Requirements

### Requirement: 雙語 SRT 與交付 SRT 逐行同軸

每集雙語 SRT 的條目 SHALL 與同一集交付字幕 SRT 的條目一一對應：條數、
編號與 start/end 時間戳完全相等，且交付字幕的華語文字直接併入條目，
不靠跨檔對照。條目 SHALL 由與交付 SRT 同一套組裝規則（同一份
`cues.json`、同樣的同文合併、去頭、間距與 0.5 秒留白規則）推導，而非
另行實作一份時間戳邏輯。每個條目對應的**真實時間窗**（留白前、合併
來源 cue 的聯集範圍）SHALL 保留供詞投影使用。

同軸性質 SHALL 由離線重建驗證把關（見 srt-data-store 的「兩側交付都
在時，時間軸必須逐條相同」）：影像側時間軸換版後，語音側 SHALL 重
投影＋重新 render 使兩側恢復同軸，驗證才會通過。語音側尚未產出的
集數不受此約束——這條只在兩側都有交付時成立。

#### Scenario: 逐行 zip 比對成立

- **WHEN** 拿同一集的雙語 SRT 與交付字幕 SRT 逐行配對
- **THEN** 每一對的 index 與 start/end 時間戳完全相等，僅文字行不同

#### Scenario: cues.json 不被改動

- **WHEN** 雙語 SRT 產出完成
- **THEN** 該集 `cues.json` 的內容與產出前逐 byte 相同

#### Scenario: 時間軸換版後失去同軸會被驗證抓到

- **WHEN** 某集語音側**已有** `3-srt-raw`，影像側時間軸更新並重產
  交付 SRT，語音側尚未重投影，執行離線重建驗證
- **THEN** 驗證以非零狀態結束並指名該集；重投影＋重新 render 後
  驗證恢復通過

### Requirement: 整集逐詞辨識結果落地保存

語音辨識 SHALL 對整集音訊連續解碼（不得逐 cue 切割音訊），並把逐詞
結果（詞文字、start、end、confidence）完整存檔。SRT 的族語行只是
此逐詞結果的投影視圖；投影 SHALL 以條目的真實時間窗為準，把每個詞
歸入與其重疊時間最大的條目，不改詞文字與詞序，並記錄跨條目邊界的
詞數供診斷。未落在任何條目內的詞 SHALL 保留在逐詞結果中、不進 SRT。

投影結果 SHALL 落地為獨立的條目檔：每個條目記其真實時間窗、歸入的
詞（可回指逐詞結果）、族語行文字、straddle 計數，與該條目的交付
字幕華語文字。雙語 SRT SHALL 可僅由條目檔重組，不需重新解碼。

#### Scenario: 中間過程可追溯

- **WHEN** 追查某條目族語行的來源
- **THEN** 條目檔指出組成該行的每個詞及其時間戳與 confidence

#### Scenario: 逐詞結果可重投影

- **WHEN** cue 時間軸更新（例如邊界精修）後重跑投影
- **THEN** 不需要重新辨識音訊即可從既有逐詞結果產生新的族語行

#### Scenario: 跨界詞歸戶

- **WHEN** 一個詞的時間範圍跨越兩個條目的邊界
- **THEN** 該詞只歸入重疊時間較大的那個條目，並被計入 straddle 診斷
  計數

### Requirement: 產出存放於 Kari-SRT

每集產出 SHALL 以 `srt_name` 命名，按產出順序存於
`Kari-SRT/news/2-asr/` 的編號階段目錄：
`1-words/<srt_name>.json`（逐詞辨識結果）、
`2-entries/<srt_name>.json`（投影中間過程）、
`3-srt-raw/<srt_name>.srt`（交付：族語／華語兩行對照）。
流程 SHALL 止於 `3-srt-raw/`——它就是語音側交付物。
`Kari-SRT/news/2-asr/README.md` SHALL 說明各階段檔案的產出流程與
輸出入對應關係。

#### Scenario: 檔案齊備

- **WHEN** 一集流程完成
- **THEN** `1-words/`、`2-entries/`、`3-srt-raw/` 各目錄下存在該
  `srt_name` 的檔案，無其他階段目錄

#### Scenario: 產出順序可讀

- **WHEN** 不熟流程的人瀏覽 `Kari-SRT/news/2-asr/`
- **THEN** 目錄編號即產出順序，README 說明每個檔由哪支程式、
  吃哪些輸入產生

## ADDED Requirements

### Requirement: 條目文字行——兩行對照格式

`3-srt-raw/<srt_name>.srt` 每個條目 SHALL 恰為兩行：「族語：」為投影
到該條目的辨識詞按時間順序以空白連接，SHALL NOT 調換順序、增刪或
改寫任何詞；「華語：」為該條目的交付字幕原文，SHALL NOT 改寫。條目
SHALL 永遠逐條目輸出、不整併。條目真實時間窗內沒有任何辨識詞時，
「族語：」行 SHALL 保留前綴、文字留空。檔內 SHALL NOT 出現任何
機器翻譯文字。

#### Scenario: 投影完成即可產出

- **WHEN** 投影完成
- **THEN** 兩行對照 SRT 即可 render：每條「族語：」「華語：」，
  時間戳與交付 SRT 相同

#### Scenario: 無語音條目

- **WHEN** 條目真實時間窗內沒有任何辨識詞
- **THEN** 「族語：」行保留前綴、文字為空，「華語：」行照常輸出

## REMOVED Requirements

### Requirement: 條目文字行——審查版與正式版

**Reason**: align 延伸試點（審查版六行、語意整併正式版）效果不佳，
使用者裁定廢止；唯一試點集的產物已自 store 刪除，交付一律止於
`3-srt-raw/`。兩行對照格式的存續要求改立為「條目文字行——兩行對照
格式」。

**Migration**: 無需遷移。試點產物與 align 程式已刪，`3-srt-raw/` 依
新 requirement 繼續產出；歷史檔案在 git 歷史可查。

### Requirement: 翻譯快取與可續跑

**Reason**: 機器翻譯只服務 align 延伸（審查版譯文與偵測），延伸廢止
後翻譯不再是本 capability 的一部分；`mt-cache/` 已自 store 刪除。

**Migration**: 無需遷移。條目檔內試點集已填的譯文欄位原樣保留、
不再讀取；快取檔案在 git 歷史可查。
