# Spec Delta

## ADDED Requirements

### Requirement: 目錄檢查要由日常把關指令真的執行

節目目錄的不變量檢查（成果檔名唯一、成果檔名符合命名規格且與識別欄推導一致、新聞的節目名稱與播出日期對得上、語言別代號在對照表內且族語別中英對得上、素材位置非空、列序照成果檔名排）SHALL 由新聞的 `name_catalogue --check` 與 `rebuild --verify` 兩個把關指令**真的執行**；檢查只存在於程式裡、卻沒有任何把關指令呼叫它，SHALL NOT 視為滿足本規格。有任何一項不符時，把關指令 SHALL 逐行指名「第幾列、哪一項不符」，並以非零狀態結束。

成果檔名重複 SHALL 在目錄這一層被擋下，SHALL NOT 等到搬移影片或組裝時才發現。

#### Scenario: 成果檔名重複被日常把關抓到

- **WHEN** 目錄裡有兩列成果檔名相同，執行 `name_catalogue --check`
- **THEN** 指名這兩列的行號並以非零狀態結束

#### Scenario: 整組檢查都會跑

- **WHEN** 某列的節目名稱與播出日期對不上、或語言別代號不在對照表內、或列序亂掉，執行 `name_catalogue --check`
- **THEN** 逐行指名該列與不符的項目，並以非零狀態結束

#### Scenario: 組裝驗證也跑同一組檢查

- **WHEN** 新聞目錄有上述任何一項不符，執行 `rebuild --verify`
- **THEN** 指名該列與不符的項目，並以非零狀態結束

#### Scenario: 乾淨的目錄通過

- **WHEN** 目錄沒有任何不符
- **THEN** `name_catalogue --check` 與 `rebuild --verify` 都不因這組檢查而失敗
