## MODIFIED Requirements

### Requirement: 僅靠已 commit 的資料可離線重建全部 SRT

主 repo（程式）加 Kari-SRT（`news/1-ocr/` 的 `1-cues/`＋`2-vision/`，
與 `news/smkul.csv`）SHALL 足以在不存取原始影片、不呼叫任何模型
的情況下，重建出與 `Kari-SRT/news/1-ocr/3-srt/` 內容逐 byte 相同的
**全部已交付 SRT**。集數隨批次成長，不固定。

要重建哪些集數 SHALL 由 `news/1-ocr/3-srt/` 裡實際有哪些檔決定，
SHALL NOT 由任何欄位或登記檔宣告。節目目錄只提供每一集的識別與
素材位置，SHALL NOT 決定某集該不該有交付物。

`news/smkul.csv` 本身 SHALL NOT 以逐 byte 重算比對——它是輸入而非
產出，內容由人維護。對它的把關改為不變量檢查，見「節目目錄的不變量」。

#### Scenario: 工作目錄全毀後重建

- **WHEN** `kithann/out/` 被整個刪除，僅存主 repo 與 Kari-SRT，
  執行重建流程
- **THEN** 產出的每一個 SRT 與 Kari-SRT 內已 commit 的版本逐 byte 相同，
  過程中不讀取任何 `.mxf`、不發出任何模型呼叫

#### Scenario: 缺件時明確失敗

- **WHEN** 重建流程執行時某集已有 `news/1-ocr/3-srt/<成果檔名>.srt`，
  卻缺少 `news/1-ocr/1-cues/<成果檔名>.json` 或對應 TSV
- **THEN** 該流程以非零狀態結束並指名缺少的檔案，SHALL NOT 產出
  不完整的 SRT 冒充完整交付

#### Scenario: 只做到一半的集數不算缺件

- **WHEN** 某集有 `1-cues/` 的時間軸，但 `3-srt/` 還沒有它的 SRT
- **THEN** 重建驗證照常通過，SHALL NOT 把它報成缺件

### Requirement: aiyalaeho 僅靠已 commit 的資料可離線重建

主 repo（程式）加 Kari-SRT（`aiyalaeho/1-ocr/` 的 `1-cues/`＋`2-vision/`＋
`4-語言檢查/詞庫/`，與 `aiyalaeho/smkul.csv`、`aiyalaeho/smkul-字幕版型異常.csv`）
SHALL 足以在不存取影片、不存取辭典原始檔、不呼叫任何模型的情況下，重建出與
`aiyalaeho/1-ocr/3-srt/` 逐 byte 相同的全部已交付雙列 SRT，以及
`aiyalaeho/1-ocr/4-語言檢查/` 的 `逐條語言標記.csv` 與 `逐集語言分布.csv`。
缺件 SHALL 指名失敗；字幕版型異常集 SHALL NOT 被要求任何 `1-ocr/` 輸入。

兩張語言檢查 CSV 的重建 SHALL 以重建出來的交付 SRT 為輸入，而非 store 內既有的
交付 SRT——上游換版而下游未重產時，這樣才驗得出來。

兩張 smkul CSV SHALL NOT 以逐 byte 重算比對，改以不變量檢查把關。

#### Scenario: 工作目錄全毀後重建

- **WHEN** 工作區被整個刪除，僅存主 repo 與 Kari-SRT，執行本語料的重建驗證
- **THEN** 每個交付 SRT 與兩張語言檢查 CSV 逐 byte 相同，過程不讀影片、
  不讀辭典原始檔、不呼叫模型

#### Scenario: 缺件時明確失敗

- **WHEN** 某集已有交付 SRT，卻缺 `1-cues/<成果檔名>.json` 或 TSV
- **THEN** 重建以非零狀態結束並指名缺少的檔案

#### Scenario: 字幕版型異常集不算缺件

- **WHEN** 某字幕版型異常集在 `1-ocr/` 底下沒有任何檔案，執行重建驗證
- **THEN** 驗證不因它報缺件

#### Scenario: 詞庫缺件時明確失敗

- **WHEN** `4-語言檢查/詞庫/` 缺任一族語別的詞庫檔，執行重建驗證
- **THEN** 驗證以非零狀態結束並指名缺少的族語別，SHALL NOT 靜默跳過該族的集數

### Requirement: 只有精修過的時間軸才進 store

把時間軸放進 `news/1-ocr/1-cues/` 的流程 SHALL 只接受**已精修**的時間軸。
某集的工作目錄只有粗切時間軸（0.2 秒格點、尚未經 25fps 邊界精修）時，
該集 SHALL NOT 入 store；流程 SHALL 指名該集並以非零狀態結束，
SHALL NOT 靜默略過該集的時間軸而讓其餘檔案照樣入庫。

工作目錄完全沒有時間軸時亦同 SHALL 指名中止——「找不到時間軸」與
「時間軸還沒精修」都是不得交付的狀態，兩者 SHALL 各自講清楚是哪
一種。

store 內已有該集的時間軸時：內容與要寫入的一致 SHALL NOT 覆寫，
連檔案本身都不重寫；內容不同才覆寫。一致與否 SHALL 以正規化（排版、
鍵排序）之後的內容比較，SHALL NOT 比工作目錄檔案的原始位元組——
工作目錄那份的鍵是插入順序，直接比會每次都判成不同。

理由：交付 SRT 的每一個時間戳都由這份時間軸推導，而粗切與精修的
精度差一個數量級（0.2 秒 vs 0.05 秒）。兩種精度混在同一個目錄裡，
從檔案本身看不出某一集是哪一種，下游也沒有辦法分別對待。把關口設
在入庫這一步，`1-cues/` 就有一個可以直接宣告的性質：**裡面每一份都
是精修過的**。不覆寫相同內容則是因為曾經一次入庫重寫了 74 個內容
根本沒變的已交付檔案。

#### Scenario: 只有粗切時間軸的集數擋在門外

- **WHEN** 某集的工作目錄只有粗切時間軸，執行入庫流程
- **THEN** 流程指名該集、說明它尚未精修，並以非零狀態結束；
  該集的時間軸沒有進入 store

#### Scenario: 沒有時間軸與沒有精修分開講

- **WHEN** 某集的工作目錄完全沒有時間軸
- **THEN** 流程指名該集並說明是「找不到時間軸」，與「尚未精修」
  是不同的訊息

#### Scenario: 精修過的照常入庫

- **WHEN** 某集的工作目錄有精修過的時間軸，store 還沒有該集
- **THEN** 該份時間軸寫入 `news/1-ocr/1-cues/<年-月>/<成果檔名>.json`

#### Scenario: 內容相同不重寫

- **WHEN** 某集的時間軸已在 store，工作目錄那份正規化後與它相同，
  再次執行入庫流程
- **THEN** 該檔案沒有被重寫

#### Scenario: 內容不同才覆寫

- **WHEN** 某集重切之後時間軸真的改了，再次執行入庫流程
- **THEN** store 內該檔以新內容覆寫

#### Scenario: store 內每一份時間軸都是精修過的

- **WHEN** 檢視 `news/1-ocr/1-cues/` 內任一份時間軸
- **THEN** 它記錄自己已經精修

### Requirement: aiyalaeho 進度表

`aiyalaeho/smkul.csv` SHALL 有下列 9 欄，依此順序：成果檔名、節目名稱、
集數、族語別(英)、族語別(中)、語言別、語言別代號、原始影片檔案位置、
備註。其中：

- 前七欄 SHALL 與其他語料的表同名同序（見 `episode-catalogue`）；
- 本語料查無播出資料、又無語音側，SHALL NOT 設年度、播出日期、
  播出時段欄——無資料的欄不養；日後取得權威播出日期時再增欄記入，
  SHALL NOT 因此改動命名鍵；
- SHALL NOT 設影片長度欄，也 SHALL NOT 設任何記錄處理階段的欄；
- 字幕版型異常集 SHALL NOT 列入本表（見「aiyalaeho 字幕版型異常集另表」）。

#### Scenario: 九欄與成果檔名

- **WHEN** 檢視 `aiyalaeho/smkul.csv`
- **THEN** 欄位恰為上列 9 欄；每列成果檔名由集數與族語別推導得出

#### Scenario: 字幕版型異常集不在本表

- **WHEN** 檢視 `aiyalaeho/smkul.csv`
- **THEN** 沒有任何一列的成果檔名出現在另表中

### Requirement: aiyalaeho 字幕版型異常集另表

`aiyalaeho/smkul-字幕版型異常.csv` SHALL 列出全部字幕版型異常集，
欄位為 `smkul.csv` 的 9 欄原樣、同順序，**不多一欄**。其中：

- 成果檔名 SHALL 作為鍵，不表示存在對應檔案；
- `備註` SHALL NOT 為空，且 SHALL 說明這一集為什麼不是雙語交付
  （`無字幕`、`僅華語字幕`、`版型不符：…`、`人工判定：…` 之一）——
  兩張表欄位相同，`備註` 非空是這張表唯一的自我宣告；
- 編碼、換行與寫法 SHALL 與 `smkul.csv` 相同（Excel 可讀）。

#### Scenario: 九欄且備註非空

- **WHEN** 檢視 `aiyalaeho/smkul-字幕版型異常.csv`
- **THEN** 欄位與 `smkul.csv` 同名同序、共 9 欄；每列 `備註` 非空

#### Scenario: 兩張表互斥且合計完整

- **WHEN** 同時檢視 `smkul.csv` 與 `smkul-字幕版型異常.csv`
- **THEN** 沒有任何 `成果檔名` 同時出現在兩表；兩表合起來就是本語料
  全部有影片的集數

#### Scenario: 備註空白時指名失敗

- **WHEN** 另表某列的 `備註` 為空
- **THEN** 驗證以非零狀態結束並指名該列

### Requirement: 兩側交付都在時，時間軸必須逐條相同

離線重建驗證 SHALL 一併把關語音側：對每個有影像側交付的集數，語音側
**存在的每一個**交付 SRT（`2-srt-raw/`、`3-srt-ai/`、`4-srt-quality/`）
SHALL 只由 store 內容離線重建——`2-srt-raw` 由 `1-words/`＋影像側
時間軸重投影渲染、`3-srt-ai` 由 `2-srt-raw`＋`mt-cache/`、
`4-srt-quality` 由 `3-srt-ai`＋`quality-cache/`——且與店面檔逐 byte
相同；重建結果自然與影像側交付 SRT 的 (index, start/end) 序列逐條
相同。任一檔不同 SHALL 使驗證以非零狀態結束、指名該集與該檔，並
SHALL 修正到相同為止——重投影＋重新 render，不需重新辨識、不需重問
模型。

語音側尚未產出**不是錯誤**：某階段沒有該集的檔時，驗證 SHALL 照常
通過，SHALL NOT 輸出警告。語音側是獨立的一條線，它做到哪由各階段
目錄裡有沒有該集的檔照實反映，SHALL NOT 另設欄位記錄。但店面**有**
某階段的檔而其上游（快取或前一階段）缺件時，那是錯誤。

#### Scenario: 兩側都在但不同軸即失敗

- **WHEN** 某集數兩側 SRT 都存在，但重建出的 `2-srt-raw`
  與店面檔不同
- **THEN** 驗證以非零狀態結束並指名該集與該檔

#### Scenario: 只有影像側交付照樣通過

- **WHEN** 某集數有影像側交付 SRT，`2-srt-raw/` 無該集的檔
- **THEN** 驗證通過，且不輸出任何與該集語音側有關的警告

#### Scenario: 做到一半照樣通過

- **WHEN** 某集有 `2-srt-raw`、`3-srt-ai`，尚無 `4-srt-quality`
- **THEN** 驗證通過，不輸出警告

#### Scenario: 全部同軸且逐 byte 相同則通過

- **WHEN** 每一個有語音側交付的集數，其每個交付檔都重建得逐 byte 相同
- **THEN** 驗證通過

## ADDED Requirements

### Requirement: 各階段做完就各自入庫

`1-cues/`、`2-vision/`、`3-srt/` SHALL 各自在該階段對某一集做完時就進入
Kari-SRT，SHALL NOT 要求整集全部階段完成才准入庫，也 SHALL NOT 要求
同批其他集數的進度。

理由：三個階段每一集都要跑幾十小時，等整集做完才入庫，代表幾十小時的
成果在工作區裡沒有備份地放著——而工作區是 gitignore 的。曾經有一集的
時間軸只剩工作目錄一份，而它的母帶已經刪掉了。

#### Scenario: 視覺辨識還沒讀完，時間軸照樣入庫

- **WHEN** 某集的時間軸已精修，視覺辨識一條 cue 都還沒讀
- **THEN** 該集的時間軸寫入 `1-cues/`，流程不因視覺辨識未完成而擋下

#### Scenario: 一集的階段可以只做到一半

- **WHEN** 檢視 Kari-SRT，某集在 `1-cues/` 有檔、在 `3-srt/` 沒有
- **THEN** 那是正常狀態，任何驗證都 SHALL NOT 因此失敗

### Requirement: 下游階段的集數必為上游的子集

離線重建驗證 SHALL 檢查各階段之間的包含關係：`3-srt/` 的成果檔名集合
SHALL 是 `2-vision/` 的子集，`2-vision/` SHALL 是 `1-cues/` 的子集。

下游有而上游沒有的集數 SHALL 使驗證以非零狀態結束，並指名是哪一集
在哪一層缺——那份交付物重建不出來。上游有而下游沒有 SHALL 視為正常，
那只表示還沒做到那一步。

#### Scenario: 交付 SRT 沒有對應的時間軸

- **WHEN** `3-srt/` 有某集的 SRT，`1-cues/` 沒有該集的時間軸
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層

#### Scenario: 上游多出來的集數不算錯

- **WHEN** `1-cues/` 有 75 集，`3-srt/` 只有 40 集
- **THEN** 驗證通過

### Requirement: 節目目錄的不變量

`news/smkul.csv`、`aiyalaeho/smkul.csv`、`aiyalaeho/smkul-字幕版型異常.csv`
是輸入而非產出，SHALL NOT 以逐 byte 重算比對。離線重建驗證 SHALL 改以
下列不變量把關，任一條不成立時指名該列並以非零狀態結束：

- `成果檔名` 合乎命名規格，同表內唯一，且與同列識別欄互推得出來；
- `語言別代號` 在隨 repo 走的對照表之內；
- `族語別(中)` 與 `族語別(英)` 一對一，對得上對照表；
- 每一列的素材位置欄非空；
- 列序依 `成果檔名` 排；
- 各階段目錄裡每一個檔，其成果檔名在表中找得到（孤兒檔即錯誤）。

表中有而檔案系統沒有的集數 SHALL NOT 視為錯誤——那是還沒做。

以文字為素材、永遠不會有交付 SRT 的表，SHALL 豁免「各階段目錄」
相關的那幾條。

#### Scenario: 有人手改壞一格

- **WHEN** 某列的 `語言別代號` 被改成對照表沒有的值
- **THEN** 驗證指名該列與該欄，說出那個值不在對照表裡

#### Scenario: 孤兒檔被抓到

- **WHEN** `3-srt/` 有一個 SRT，其成果檔名在節目目錄中找不到
- **THEN** 驗證以非零狀態結束並指名該檔

#### Scenario: 還沒做的集數不算錯

- **WHEN** 節目目錄有 969 列，各階段目錄合計只有 75 集
- **THEN** 驗證通過

### Requirement: 時間軸不記機器專屬路徑

`1-cues/` 內的時間軸 SHALL NOT 記錄來源影片在本機的路徑。

理由：那是當時那台機器的暫存位置，換一台機器就沒有意義，卻會讓
Kari-SRT 的內容綁定在一台機器上——同一份資料在另一台機器重算會
得到不同的位元組。每一集的影片位置由節目目錄的 `原始影片檔案位置`
記錄，那是相對於語料根的路徑。

#### Scenario: 時間軸裡沒有本機路徑

- **WHEN** 檢視 `1-cues/` 內任一份時間軸
- **THEN** 裡面沒有任何絕對路徑，也沒有指向工作區的欄位

### Requirement: 不產出逐集 QC 摘要檔

組裝流程 SHALL NOT 在 `3-srt/` 旁邊產出逐集的 QC 摘要檔（cue 數、
有字 cue 數、族語列數、華語列數、SRT 行數）。

理由：沒有任何流程讀它，離線重建驗證也不比對它，而每一個數字都能
從時間軸與交付 SRT 當場算出來。要給人看的逐集數字 SHALL 收進一張
逐集 CSV，一列一集，而不是散成一集一個小檔。

#### Scenario: 組裝之後旁邊沒有摘要檔

- **WHEN** 對某集執行組裝流程
- **THEN** `3-srt/` 底下只有該集的 SRT，沒有同名的 QC 摘要檔

## REMOVED Requirements

### Requirement: 批次進行中的集數以 pending 標記且不參與重建驗證

**Reason**: 登記檔（`inventory.json`）刪除，節目目錄從第一天就涵蓋全部集數，「已登記、尚未交付」這個中間狀態不再存在。某集做到哪由各階段目錄裡有沒有它的檔回答。

**Migration**: 原本靠 pending 跳過的集數，改由「`3-srt/` 有沒有該集的檔」判斷；上游有而下游沒有一律視為還沒做，見「下游階段的集數必為上游的子集」。

### Requirement: store 只在整批完成時定版

**Reason**: 改為各階段做完就各自入庫，不再有「整批定版」這個單位，也不再有 pending 可清。

**Migration**: 見「各階段做完就各自入庫」。

### Requirement: 進度表由定版流程寫入，不由逐集組裝流程寫入

**Reason**: `smkul.csv` 不再是衍生的進度表，而是人維護的節目目錄；沒有任何流程寫它。`cues`、`字幕srt狀態`、`語音辨識模型`、`文稿位置` 四欄一併移除——前三者是處理狀態，改由各階段目錄回答；文稿路線已廢止。

**Migration**: 要看某批做到哪，數各階段目錄裡的檔案；`smkul.csv` 的欄位定義見 `episode-catalogue`。

### Requirement: 整份重寫 inventory 的流程須有明確防護

**Reason**: `inventory.json` 刪除，沒有可整份重寫的登記檔。

**Migration**: 節目目錄由人維護，受版本控制與不變量檢查保護。

### Requirement: 進度表併記影片長度

**Reason**: 影片長度只在切完 cue 之後才算得出來，而節目目錄從第一天就要涵蓋全部集數，該欄對絕大多數列永遠是空的。

**Migration**: 需要長度時從該集的時間軸讀。

### Requirement: 節目目錄正本存於 store

**Reason**: 外部給的 `ilrdf-corpus.csv` 與各語料的交付表合併成同一張表，不再有跨語料的第二份目錄。合併後的目錄仍存於 Kari-SRT，但分屬各語料目錄之下。

**Migration**: 原本從 `ilrdf-corpus.csv` 查的識別、命名與素材位置，改查該語料的 `smkul.csv`；`音檔位置(mp3)`、`音檔位置(wav)`、`文稿位置`、`有無影片`、`播出時段` 五欄不保留，理由見 `episode-catalogue` 與 `asr-bilingual-srt`。
