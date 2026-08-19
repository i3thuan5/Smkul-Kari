# asr-bilingual-srt Specification

## Purpose

族語新聞每集一份「族語（語音辨識）＋華語（機器翻譯）」雙語 SRT 的產出
契約：時間軸與交付字幕 SRT 逐行同軸、逐詞辨識結果落地保存、翻譯快取
可續跑、產出忠實於辨識原文。

## Requirements

### Requirement: 雙語 SRT 與交付 SRT 逐行同軸

每集雙語 SRT 的條目 SHALL 與同一集交付字幕 SRT 的條目一一對應：條數、
編號與 start/end 時間戳完全相等，且交付字幕的華語文字直接併入
審查版條目，不靠跨檔對照。條目 SHALL 由與交付 SRT 同一套組裝
規則（同一份 `cues.json`、同樣的同文合併、去頭、間距與 0.5 秒留白
規則）推導，而非另行實作一份時間戳邏輯。每個條目對應的**真實時間窗**
（留白前、合併來源 cue 的聯集範圍）SHALL 保留供詞投影與偵測使用。

#### Scenario: 逐行 zip 比對成立

- **WHEN** 拿同一集的雙語 SRT 與交付字幕 SRT 逐行配對
- **THEN** 每一對的 index 與 start/end 時間戳完全相等，僅文字行不同

#### Scenario: cues.json 不被改動

- **WHEN** 雙語 SRT 產出完成
- **THEN** 該集 `cues.json` 的內容與產出前逐 byte 相同

### Requirement: 條目文字行——審查版與正式版

雙語 SRT 有三個階段產物，SHALL 分檔存放、SHALL NOT 同路徑覆蓋。
**對照版**（`3-srt-raw/<srt_name>.srt`）：每個條目兩行
「族語：」「華語：」——與正式版同格式（族語＝辨識詞原序連接、
華語＝交付字幕原文），不含任何翻譯，投影完成即可產出；永遠逐條目
不整併，是正式版整併前的對照基準。**審查版**（`4-srt-ai/<srt_name>.srt`）：每個條目六行、順序
固定——
「族語ASR結果：」「華語OCR字幕翻譯成族語-ailabs：」
「華語OCR字幕翻譯成族語-claude：」「華語OCR字幕：」
「族語ASR結果翻譯華語-ailabs：」「族語ASR結果翻譯華語-claude：」
——已花運算的譯文全部留痕，交付字幕的華語文字也直接併入
（「華語OCR字幕：」行），不需跨檔對照；偵測完成後 SHALL 附第七行
「偵測：<歸類>」，讓 ok／mismatch 在播放器裡直接可見。
**正式版**（`6-srt-complete/<srt_name>.srt`）：每條恰兩行，且
SHALL 只由原始材料組成——「族語：」為辨識詞按時間順序連接，
SHALL NOT 調換順序、增刪或改寫任何詞；「華語：」為交付字幕原文
依序連接，SHALL NOT 改寫或調序。整併規則：偵測歸 `ok` 的條目
SHALL 維持逐條目；所屬語意句塊含任何非 `ok` 條目者，該塊 SHALL
整併為一條（時間＝塊首 start 至塊尾 end），故正式版與對照版條數
不必然相同。正式版 SHALL NOT 含任何機器翻譯文字（譯文只存在於
審查版與偵測紀錄）；產出正式版 SHALL NOT 修改或刪除對照版與
審查版。三版 SHALL 皆可僅由條目檔與翻譯快取離線重組；兩方向
各引擎的譯文與主引擎標記 SHALL 記於條目檔。條目真實時間窗內沒有任何辨識詞時，
ASR 行與其譯文行 SHALL 保留前綴、文字留空且不送翻譯；
「華語OCR字幕翻譯成族語」兩行不受影響。

#### Scenario: 對照版先行

- **WHEN** 投影完成而翻譯尚未進行
- **THEN** 對照版即可產出：每條目「族語：」「華語：」兩行、格式
  與正式版一致，時間戳與交付 SRT 相同

#### Scenario: 審查版六行並列附偵測行

- **WHEN** 主引擎尚未定案，條目真實時間窗內有辨識詞且偵測已跑過
- **THEN** 該條目輸出上述六行（ASR 行是投影詞按時間排序以空白
  連接，「翻譯成族語」兩行是字幕華語經各引擎的族語譯文，
  「華語OCR字幕」行照錄交付字幕原文，「翻譯華語」兩行是 ASR
  族語經各引擎的華語譯文），另附「偵測：<歸類>」一行

#### Scenario: 正式版只由原始材料組成

- **WHEN** 核可後 render 正式版
- **THEN** `6-srt-complete/` 每條兩行「族語：」「華語：」，內容
  只來自辨識詞與字幕原文的原序連接，任何引擎的譯文都不出現在
  檔內；`3-srt-raw/` 與 `4-srt-ai/` 逐 byte 不變

#### Scenario: 問題句整併、乾淨句保留

- **WHEN** 某語意句塊內有條目被歸為 `mismatch`（或任何非 `ok`
  類），另一塊全數 `ok`
- **THEN** 前者整塊併成一條（華語＝塊內字幕依序連接、族語＝塊內
  辨識詞依時序連接），後者維持逐條目，兩者都不含譯文

#### Scenario: 無語音條目

- **WHEN** 條目真實時間窗內沒有任何辨識詞
- **THEN** 「族語ASR結果：」與兩個「族語ASR結果翻譯華語-*：」行
  保留前綴、文字為空且不對空字串呼叫翻譯；「華語OCR字幕：」與
  「華語OCR字幕翻譯成族語-*：」三行照常輸出

### Requirement: 整集逐詞辨識結果落地保存

語音辨識 SHALL 對整集音訊連續解碼（不得逐 cue 切割音訊），並把逐詞
結果（詞文字、start、end、confidence）完整存檔。SRT 的族語行只是
此逐詞結果的投影視圖；投影 SHALL 以條目的真實時間窗為準，把每個詞
歸入與其重疊時間最大的條目，不改詞文字與詞序，並記錄跨條目邊界的
詞數供診斷。未落在任何條目內的詞 SHALL 保留在逐詞結果中、不進 SRT。

投影結果 SHALL 落地為獨立的條目檔：每個條目記其真實時間窗、歸入的
詞（可回指逐詞結果）、族語行文字、straddle 計數、該條目的交付
字幕華語文字，與翻譯 meta（語別碼、主引擎標記、兩方向各引擎的
譯文）。雙語 SRT SHALL 可僅由條目檔與翻譯快取重組，不需重新解碼或
重新翻譯。

#### Scenario: 中間過程可追溯

- **WHEN** 追查某條目族語行的來源
- **THEN** 條目檔指出組成該行的每個詞及其時間戳與 confidence，
  以及該行送翻譯時使用的語別碼

#### Scenario: 逐詞結果可重投影

- **WHEN** cue 時間軸更新（例如邊界精修）後重跑投影
- **THEN** 不需要重新辨識音訊即可從既有逐詞結果產生新的族語行

#### Scenario: 跨界詞歸戶

- **WHEN** 一個詞的時間範圍跨越兩個條目的邊界
- **THEN** 該詞只歸入重疊時間較大的那個條目，並被計入 straddle 診斷
  計數

### Requirement: 辨識文字忠實輸出

族語行 SHALL 忠實保留辨識器輸出的文字，不得施加任何 presentation
處理——包括大小寫正規化（如首字大寫、其餘轉小寫）、字元取代（如阿美語
u→o）、自動加標點。

#### Scenario: 專有名詞大小寫保留

- **WHEN** 辨識結果含大寫開頭的專有名詞於句中
- **THEN** SRT 族語行與逐詞結果中該詞的大小寫原樣保留

### Requirement: 翻譯快取與可續跑

機器翻譯 SHALL 以（引擎、方向、來源語別、原文）為鍵做快取：相同鍵
不得重複翻譯；流程中斷後重跑 SHALL 從快取續作，已完成的翻譯不重做；
對翻譯服務的請求 SHALL 維持單一併發。使用的來源語別碼與引擎 SHALL
記錄在產出中。

#### Scenario: 中斷續跑

- **WHEN** 翻譯進行到一半中斷後重新執行
- **THEN** 已翻譯過的 cue 不再產生對外請求，僅剩餘的 cue 送翻譯

#### Scenario: 時間軸更新後快取仍命中

- **WHEN** cue 邊界精修使時間戳改變但某 cue 的族語文字不變
- **THEN** 該 cue 的翻譯直接取自快取，不產生對外請求

### Requirement: 音檔時間軸驗證

產出流程 SHALL 在辨識前驗證音檔與 cue 時間軸屬同一條時間軸（至少
比對音檔時長與該集 cue 軸的預期時長），不符 SHALL 指名中止、不得
靜默套用。

#### Scenario: 音檔時長不符

- **WHEN** 下載的音檔時長與該集 cue 軸預期時長差異超過容許值
- **THEN** 流程中止並指出該集與兩個時長數值，不產出任何 SRT

### Requirement: 產出存放於 Kari-SRT

每集產出 SHALL 以 `srt_name` 命名，按產出順序存於
`Kari-SRT/news/2-asr/` 的編號階段目錄：
`1-words/<srt_name>.json`（逐詞辨識結果）、
`2-entries/<srt_name>.json`（投影中間過程）、
`3-srt-raw/<srt_name>.srt`（對照版兩行）、
`4-srt-ai/<srt_name>.srt`（審查版雙語 SRT）、
`5-align/<srt_name>.json` 與 `5-align/<srt_name>.md`（偵測診斷與
人可讀摘要，契約見 speech-subtitle-alignment）、
`6-srt-complete/<srt_name>.srt`（正式版雙語 SRT，主引擎定案後）。
**預設流程 SHALL 止於 `3-srt-raw/`**（words → entries → raw）；
`4-srt-ai/`、`5-align/`、`6-srt-complete/` 屬 align 延伸，SHALL
只在被指名時執行（使用者裁定：正式版整併效果不佳，之後集數不再
產）。翻譯快取 SHALL 保存於 `Kari-SRT/news/2-asr/mt-cache/`（跨集
共用，非階段目錄）。`Kari-SRT/news/2-asr/README.md` SHALL 說明各階段
檔案的產出流程與輸出入對應關係。

#### Scenario: 檔案齊備（預設流程）

- **WHEN** 一集預設流程完成
- **THEN** `1-words/`、`2-entries/`、`3-srt-raw/` 各目錄下存在該
  `srt_name` 的檔案；`4-srt-ai/`、`5-align/`、`6-srt-complete/`
  僅在 align 延伸被指名執行過的集數出現

#### Scenario: 產出順序可讀

- **WHEN** 不熟流程的人瀏覽 `Kari-SRT/news/2-asr/`
- **THEN** 目錄編號即產出順序，README 說明每個檔由哪支程式、
  吃哪些輸入產生
