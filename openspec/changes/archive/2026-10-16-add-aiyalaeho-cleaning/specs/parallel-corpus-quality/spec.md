## MODIFIED Requirements

### Requirement: 機器翻譯語言碼由靜態表決定

族語→華語機器翻譯所用的語言碼 SHALL 由程式內一張「族語別(英)→語言碼」靜態表查得，SHALL NOT 逐集偵測語言別。表內沒有的族別 SHALL 指名失敗。

#### Scenario: 族別查表

- **WHEN** 對阿美語的集數做翻譯
- **THEN** 語言碼由表查得，過程沒有任何偵測用的翻譯請求

#### Scenario: 表內沒有的族別

- **WHEN** 某集的族語別不在表內
- **THEN** 流程指名該族別並以非零狀態結束
