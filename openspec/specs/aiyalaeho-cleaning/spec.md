# aiyalaeho-cleaning Specification

## Purpose

《開會了》已交付字幕的清洗試做契約：依承辦要求的 a–d 四項，修正可程式化的空白與標點、列出同族語跨集與對辭典的拼寫差異、判定各集語別，並把錯字、語言別差異、無法確認者分開處理。語言別差異與無法確認者只列表供討論、不修改；全部產出放 kithann/out，Kari-SRT 只讀。

## Requirements

### Requirement: 產出只寫 kithann/out，Kari-SRT 只讀

清洗的全部產出 SHALL 寫在 `kithann/out/aiyalaeho-清洗/` 底下，各層目錄依產出順序編號：`1-詞庫/`、`2-候選/`、`3-判定/`、`4-清洗版/`、`5-交付/`，另有 `README.md` 說明各層是什麼、從哪裡做出來、誰讀它。

`Kari-SRT/` SHALL 只被讀取。任何寫入目標落在 `Kari-SRT/` 底下時 SHALL 中止並指名該路徑，SHALL NOT 寫出部分檔案。

#### Scenario: 寫入目標落在 Kari-SRT 底下

- **WHEN** 輸出目錄被設成 `Kari-SRT/aiyalaeho/1-ocr/` 底下的某處
- **THEN** 程式中止、指名該路徑，`Kari-SRT/` 底下沒有任何檔案被建立或改動

#### Scenario: 跑完 Kari-SRT 不變

- **WHEN** 清洗的全部步驟跑完
- **THEN** `Kari-SRT/` 底下每個檔案與跑之前逐 byte 相同

### Requirement: E樂園 依語別蒸餾詞表

`1-詞庫/E樂園/` SHALL 每個語別一個檔、一行一詞，由 E樂園 教材的句子 CSV 與 XML 的族語欄蒸餾。範圍 SHALL 涵蓋阿美、泰雅、卑南、賽夏四族的全部語別（阿美 5、泰雅 6、卑南 4、賽夏 1）。

- 族語欄 SHALL 依欄名辨認，涵蓋實際出現的各種寫法（`wordAb`、`sentenceAAb`、`lessonAB`、`con_AB1`、`word_AB1`、`Ab_1`、`article_ab`、`matchAAbA`、`sentenceAb`、`word_ab`）；華語欄 SHALL NOT 進詞表。欄名裡的 `ch` 不可作為華語的判準（`choiceOneAAb` 的 ch 屬於 choice）。
- 語別 SHALL 取自 `dialectId`／`dialect_id` 欄；XML 沒有該欄時取自所在資料夾名（語言別編號）。SHALL NOT 用 `languageId`（那是族語別）。
- 語言別編號對應語別全名，依 E樂園 語言別編號表；語別全名（如「南勢阿美語」）SHALL 剝成語言別名稱（「南勢」）後經既有語言別對照表取得語言別代號；沒有變體的族語（「賽夏語」）退族語別代號。對不上任何語言別時 SHALL 中止並指名。
- 一格內以 `/` 分隔的異體（`sa / saya / misasa`）SHALL 拆成各自的詞。
- 撇號 SHALL 與字幕同一套正規化（`’`、`ʼ` → `'`），大小寫不分。

#### Scenario: 族語欄名不一致

- **WHEN** 一份 XML 的族語句子放在 `matchAAbA`、另一份放在 `article_ab`
- **THEN** 兩者的詞都進該語別的詞表

#### Scenario: choice 開頭的族語欄

- **WHEN** 句型篇有 `choiceOneAAb` 與 `choiceOneACh` 兩欄
- **THEN** 前者進詞表，後者不進

#### Scenario: languageId 與 dialectId 不同

- **WHEN** 一筆句型篇資料 `languageId` 是 12、`dialectId` 是 38
- **THEN** 該筆歸語言別編號 38（南王卑南語），不歸 12

#### Scenario: 欄名找不到

- **WHEN** 一份 CSV 既沒有 `dialectId` 也沒有 `dialect_id` 欄
- **THEN** 中止並指名該檔，不產生空的詞表

### Requirement: Kaldi 詞表只證明存在

`1-詞庫/Kaldi詞表/` SHALL 每族一個檔，由 ILRDF Kaldi 族語模型的詞表蒸餾，SHALL 排除模型用的特殊符號（`<eps>`、`<SIL>`、`<UNK>`、`#0`、`<s>`、`</s>`）。

Kaldi 詞表 SHALL 只用來標示「這族有人這樣寫」，SHALL NOT 用來決定建議寫法，也 SHALL NOT 用來判定語言別。

#### Scenario: 特殊符號不進詞表

- **WHEN** 模型詞表開頭是 `<eps>`、`<SIL>`、`<UNK>`，結尾是 `#0`、`<s>`、`</s>`
- **THEN** 這六個都不在蒸餾出來的詞表裡

#### Scenario: 只有 Kaldi 詞表見過

- **WHEN** 一個詞辭典與 E樂園 都沒有、只有 Kaldi 詞表有
- **THEN** 候選標為「族語其他寫法見過」，建議寫法欄空白

### Requirement: a 項規則清洗

規則清洗 SHALL 套用到交付的 10 集，對族語列與華語列做下列處理，其餘字元 SHALL 原樣保留：

- 彎撇號 `’`（U+2019）與 `ʼ`（U+02BC）換成 `'`。
- 連續兩個以上空白縮成一個。華語列的空白是畫面斷句，SHALL 縮成一個、SHALL NOT 刪除。
- 刪節號：4 個以上的 `.` 縮成 3 個；剛好 3 個不動。
- 華語列連續重複的驚嘆號、問號縮成一個。

冒號 SHALL 視為詞的一部分，SHALL NOT 刪除或縮減。雙撇號 `"` SHALL 原樣保留。`’` 後面緊接空白者，規則清洗 SHALL 只換撇號、SHALL NOT 併掉空白；是否併成一個詞 SHALL 由看圖判定決定。

族語列或華語列原本是空的，清洗後 SHALL 仍是空的，該條的標籤行 SHALL 保留。

#### Scenario: 冒號不被當標點

- **WHEN** 族語列是 `'a'iyalaeho: kapayaka:i'`
- **THEN** 清洗後兩個冒號都還在

#### Scenario: 彎撇號後夾空白

- **WHEN** 族語列是 `zi harem mu kemani ku mena’   u kana`
- **THEN** 規則清洗後是 `zi harem mu kemani ku mena' u kana`，該處同時列為看圖候選

#### Scenario: 華語斷句空白

- **WHEN** 華語列是 `稍待一會兒  我們即將共同來探討`
- **THEN** 清洗後是 `稍待一會兒 我們即將共同來探討`

#### Scenario: 刪節號

- **WHEN** 族語列分別是 `Padaka...........`、`Sipulun...`
- **THEN** 清洗後分別是 `Padaka...`、`Sipulun...`

#### Scenario: 雙撇號是真的符號

- **WHEN** 族語列含 `"awsa'`
- **THEN** 清洗後 `"` 原樣保留

### Requirement: 語言別推測

每集 SHALL 推測語言別：以該集族語列的詞次，算出在該族各語別 E樂園 詞表中的覆蓋率，並每 60 條分一段看各段第一名。判定 SHALL 為下列之一：

- **高**：全集第一名領先第二名達門檻，且各段第一名一致。
- **中**：全集第一名領先不足門檻，但多數段的第一名是同一個語別。
- **混合**：各段第一名在不同語別之間交錯，沒有一個語別佔多數段。

`smkul.csv` 已標語別的集 SHALL 照標記，SHALL NOT 重新推測。只有一個語別的族語（賽夏）SHALL 直接給該族代號，把握記為「單一語別」。語言別代號 SHALL 經既有語言別對照表取得。

候選比對要用的「該集語別」：高 → 該語別；中 → 前兩名語別；混合 → 該族全部語別；已標記 → 標記的語別。

#### Scenario: 已標語別不重推

- **WHEN** 一集在 `smkul.csv` 標了秀姑巒，而推測時秀姑巒只比海岸高 3 個百分點
- **THEN** 判定照標記給秀姑巒，不降成「中」

#### Scenario: 第一名只贏幾個百分點

- **WHEN** 一集海岸 80%、秀姑巒 77%，各段第一名都是海岸
- **THEN** 判「中」，不判「高」

#### Scenario: 各段第一名交錯

- **WHEN** 一集全集各語別都在 53～59%，十段裡南勢第一的有六段、其餘四段是秀姑巒或馬蘭
- **THEN** 判「混合」，不挑全集最高的南勢

### Requirement: b、c 項候選與證據

`2-候選/<族語>.csv` SHALL 只涵蓋多於 1 集的族語（阿美、賽夏、泰雅、卑南），每個族語詞形一列，並排下列證據：出現的集數與各集次數、辭典有無、E樂園 哪些語別見過、Kaldi 詞表有無、開會了全語料（Kari-SRT 全部已交付集）出現次數、上字文稿出現次數、最接近的辭典詞條、其他集的相近寫法。

- 詞形比對 SHALL 大小寫不分、撇號正規化後比較；SHALL NOT 套用任何語言別正音轉換。報表 SHALL 保留字幕上的原樣。
- 族語列裡的漢字、注音、數字 SHALL NOT 進候選。
- 該集語別的 E樂園 詞表見過的詞 SHALL 判為語言別寫法、不列為錯字候選。
- 只差一個字母的詞對 SHALL 只列為相近寫法，SHALL NOT 據此判為錯字。
- 節目名 `'a'iyalaeho:` 的各種錯拼 SHALL 跨族語合併成一組。
- 布農（只有 1 集）SHALL NOT 進 b、c 候選，但 a 項照做。

#### Scenario: 語言別正音不可套用

- **WHEN** 082 寫 `kaku` 17 次，其他集寫 `kako` 48 次
- **THEN** 兩者是兩個詞形、並列為相近寫法，不被折成同一個

#### Scenario: 用錯語別的證據

- **WHEN** 087 判中（西群、知本），`harem` 南王辭典沒有、西群 E樂園 有
- **THEN** `harem` 判為語言別寫法，不列為錯字候選

#### Scenario: 只差一個字母的不同詞

- **WHEN** `kamo` 與 `kamok` 都出現在多集
- **THEN** 兩者列為相近寫法，交給文字分類判定，不自動判錯字

#### Scenario: 族語列夾漢字

- **WHEN** 族語列是 `ai na pukatrelu mau nanta zekalr i Likavung i 李芳媚老師`
- **THEN** `李芳媚老師` 不進候選

#### Scenario: 節目名跨族語錯拼

- **WHEN** 排灣集有 `'a'iylaeho:`、泰雅集有 `'a'alaeho:`、其他集有 `'a'iyalaeho:`
- **THEN** 三者合成一組，建議寫法 `'a'iyalaeho:`

### Requirement: Claude 判定的送出與匯入

不能靠規則判定的候選 SHALL 分批送 Claude（Opus）做文字分類；判為錯字者與彎撇號夾空白者 SHALL 再送 Claude（Opus）看原生圖條。判定結果 SHALL 存在 `3-判定/`，重跑時已判過的 SHALL NOT 再送。

- 文字分類的類別 SHALL 恰為：錯字、語言別差異、不同詞、斷詞不同、不確定。判「錯字」SHALL 附建議寫法；每一列 SHALL 附理由。
- 看圖判定的類別 SHALL 恰為：OCR 讀錯、播出端錯字、看不出來。
- 匯入時，判定少了某個送出的候選、多了不在送出清單裡的詞、或類別不在上列之中，SHALL 中止並指名是哪一批哪一個詞。
- 看圖送出的每一處 SHALL 附該字幕編號對應的全部 cue 的原生圖條路徑（一條字幕可能由多個 cue 合成）；圖條不存在 SHALL 中止並指名集數與字幕編號。

#### Scenario: 判定漏列

- **WHEN** 一批送出 150 個詞，匯入的判定只有 149 列
- **THEN** 中止並指名缺的那個詞與批號

#### Scenario: 錯字沒有建議寫法

- **WHEN** 一列判「錯字」但建議寫法空白
- **THEN** 中止並指名該列

#### Scenario: 一條字幕由多個 cue 合成

- **WHEN** 要看圖的字幕編號是由兩個相鄰同文字的 cue 合成
- **THEN** 送出的那一處附兩個 cue 的族語列圖條

#### Scenario: 重跑只送新的

- **WHEN** 已有 10 批判定、候選又多了 30 個詞
- **THEN** 送判只產生涵蓋那 30 個詞的批次

### Requirement: 人工改判

使用者看過結果後，可以在 `3-判定/人工改判.csv`（欄：族語別、詞形、理由）列出要改判待討論的錯字詞形。列在其中的詞 SHALL NOT 在清洗版修改；兩份表的處理方式 SHALL 為「待討論」，依據欄 SHALL 寫出「人工改判：<理由>」，文字分類欄 SHALL 保留 Claude 的原判。檔案不存在時視為沒有改判。

#### Scenario: 語言別差異疑慮改判待討論

- **WHEN** 人工改判列了阿美 `odal`（082 整集一致不寫撇號，可能是南勢寫法），而文字分類判它錯字、看圖確認畫面就是 odal
- **THEN** 清洗版裡 `odal` 原樣保留；拼寫不一致表與辭典比對表的 `odal` 文字分類是「錯字」、處理方式是「待討論」、依據含「人工改判」

### Requirement: 清洗版 SRT

`4-清洗版/<srt_name>.srt` SHALL 由交付的 `3-srt/<srt_name>.srt` 逐條替換文字行而成：編號行、時間行、空行、標籤（`族語：`、`華語：`）SHALL 與交付版逐 byte 相同，只有標籤後的文字可以不同。

套用的修改 SHALL 只有：a 項規則清洗、看圖判為「OCR 讀錯」或「播出端錯字」的錯字訂正、看圖判定為同一詞的撇號夾空白合併、節目名錯拼統一。判為語言別差異、不同詞、斷詞不同、不確定、看不出來者 SHALL NOT 修改。

替換 SHALL 以詞為單位，SHALL NOT 改到其他詞的一部分；原詞首字母大寫者，改後 SHALL 保持首字母大寫。

#### Scenario: 編號與時間不變

- **WHEN** 清洗版產出
- **THEN** 逐行比對交付版，只有 `族語：`、`華語：` 之後的文字有差異

#### Scenario: 語言別差異不修改

- **WHEN** `kaku` 文字分類判「語言別差異」
- **THEN** 清洗版裡 `kaku` 原樣保留

#### Scenario: 以詞為單位替換

- **WHEN** 錯字 `kako` 要改成 `kaku`，同一列還有 `kakoay`
- **THEN** 只有獨立的 `kako` 被改，`kakoay` 不變

#### Scenario: 句首大寫

- **WHEN** 錯字 `Ngaay` 要依建議改成 `nga'ay`
- **THEN** 清洗版寫 `Nga'ay`

### Requirement: 交付 CSV

`5-交付/` SHALL 有四份 CSV，SHALL 為 UTF-8 無 BOM、LF 換行，同樣的輸入重跑 SHALL 逐 byte 相同（列順序固定）。需要標記語言別的欄，欄名 SHALL 為「語言別代號」。

- **修改前後對照表**：清洗版每一處修改一列，含成果檔名、字幕編號、開始時間、結束時間、列（族語／華語）、修改前（整條該列文字）、修改後、類別（多餘空白、重複標點、撇號、OCR 讀錯、播出端錯字、節目名）、依據。同一條改了好幾處 SHALL 一處一列。
- **拼寫不一致表**：同族語跨集的相近寫法一組，含各寫法的集數與次數、辭典有無、E樂園 見過的語別、文字分類結果、建議寫法、處理方式。
- **辭典比對表**：與辭典不同或查無的詞，含辭典狀態（近似／查無）、最接近的辭典詞條、E樂園 見過的語別、Kaldi 詞表有無、出現位置與上下文（族語列＋華語列）、處理方式。
- **語言別推測表**：每集一列，含成果檔名、族語別、smkul 標記的語別、推測語別、語言別代號、把握（高／中／混合／已標記／單一語別）、各語別覆蓋率、分段第一名、依據。「語言別代號」只在把握為高或已標記時填語言別代號；中、混合 SHALL 填族語別代號，推測的語別只寫在「推測語別」欄。

處理方式欄 SHALL 恰為：已修改、建議統一、待討論、不改。

建議寫法 SHALL 依此順序取：該集語別的權威（辭典語別與該集語別相同用辭典，不同用 E樂園 該語別）＞ 開會了全語料出現次數 ＞ 上字文稿出現次數。判為語言別差異者 SHALL NOT 給建議寫法，處理方式為「待討論」。

#### Scenario: 處理方式字彙

- **WHEN** 報表產出
- **THEN** 處理方式欄每一格都是四個值之一

#### Scenario: 辭典與該集語別不同

- **WHEN** 087（西群）的一組寫法，南王辭典收 A、西群 E樂園 收 B
- **THEN** 建議寫法取 B

#### Scenario: 語言別差異不給建議

- **WHEN** 一組寫法文字分類判「語言別差異」
- **THEN** 建議寫法空白、處理方式「待討論」

#### Scenario: 把握為中的語言別代號

- **WHEN** 087 推測西群、把握「中」
- **THEN** 語言別推測表的推測語別是「西群」、語言別代號是 `pyu`，不是 `pyu-x-mkzy`

#### Scenario: 重跑逐 byte 相同

- **WHEN** 同樣的輸入跑兩次報表
- **THEN** 四份 CSV 兩次逐 byte 相同
