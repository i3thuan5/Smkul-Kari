## MODIFIED Requirements

### Requirement: 語別碼依新聞語言別代號表決定

送 sapolita 的語別碼 SHALL 依 `scripts/news/新聞語言別代號.csv` 決定：該表一族一列，欄位為 `族語別(中)`、`語言別代號`、`語言別`、`依據`，是每族的保底語別碼。表內每個 `語言別代號` SHALL 是 sapolita 選單上有的語別碼，也 SHALL 查得到於 repo 內的族語別／語言別代號對照表。

節目目錄那一列的 `語言別代號` 是同族底下的語言別（不是只記到族語別）時，SHALL 送那一列的代號——非保底的語言別要有網頁證據才填進目錄。那一列的語言別屬於別族時，SHALL 指名該集中止。

節目目錄某一集的族語別在表上查不到、或表上的代號在對照表查不到時，SHALL 中止並指名該集或該列，SHALL NOT 送出、SHALL NOT 猜一個代號。

#### Scenario: 多語別的族換成語別碼

- **WHEN** 節目目錄某集的 `語言別代號` 是 `ami`（只記到族語別）
- **THEN** 送出表上阿美那一列的語別碼 `ami-x-pswl`

#### Scenario: 賽德克與太魯閣不混淆

- **WHEN** 節目目錄某集的 `語言別代號` 是 `trv`（賽德克），另一集是 `trv-x-truku`（太魯閣）
- **THEN** 前者送 `trv-x-tgdy`，後者送 `trv-x-truku`；兩者都查表決定，不看代號前綴

#### Scenario: 目錄填了查證過的語言別就送那個

- **WHEN** 魯凱某集的目錄 `語言別代號` 是 `dru-x-opnh`（萬山），保底是 `dru-x-ngdr`
- **THEN** 送出 `dru-x-opnh`

#### Scenario: 表上查不到就中止

- **WHEN** 某集的族語別在新聞語言別代號表上沒有對應列
- **THEN** 流程指名該集並以非零狀態結束，不送出任何請求

### Requirement: 送出前先選族別

sapolita 的語別選單綁在連線 session 上。每一次辨識 SHALL 在同一個 session 先選該語別所屬的族別，再送辨識；族別 SHALL 依語別碼查表得出，SHALL NOT 由代號前綴推測；族別選單值 SHALL 與伺服器上的字串一字不差。伺服器 2026-09-24 之後的選單值是只有中文的族語名（例：「阿美語」「魯凱語」），不帶括號英文名。

#### Scenario: 非預設族別

- **WHEN** 辨識一集邵語（`ssf`）
- **THEN** 同一個 session 先選「邵語」再送辨識，伺服器接受並回傳 SRT

#### Scenario: 選單值不帶英文名

- **WHEN** 辨識一集魯凱語
- **THEN** 送出的族別是「魯凱語」，不是「魯凱語 (Rukai)」——後者伺服器會回「not in the list of choices」
