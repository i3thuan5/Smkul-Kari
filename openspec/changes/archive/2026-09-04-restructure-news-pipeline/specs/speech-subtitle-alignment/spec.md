# speech-subtitle-alignment Delta

本 capability 整份作廢：它描述的「族語語音與華語字幕對不齊偵測」是
align 延伸的一部分，該延伸只在一集試點過（語意整併效果不佳），使用者
裁定廢止；偵測程式（`scripts/asrmt/align/`）、產物（`5-align/`）與
下游讀者（審查版偵測行、語意整併）全數刪除。歸檔時 SHALL 將
`openspec/specs/speech-subtitle-alignment/` 整個移除。

## REMOVED Requirements

### Requirement: 比對單位是字幕的華語語意句

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移；程式與產物已刪，歷史在 git 可查。

### Requirement: 內容相似度在華語空間量測

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移。

### Requirement: 時間偏移在族語空間量測

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移。

### Requirement: 錨點詞校驗

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移。

### Requirement: 低分條目的配對恢復

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移。

### Requirement: 逐條目歸因輸出

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移。

### Requirement: 門檻經人工校準才有效

**Reason**: align 延伸廢止，偵測不再執行。門檻須經校準的原則本身仍
適用於其他把關（另行處理，見門檻重校 change）。
**Migration**: 無需遷移。

### Requirement: 偵測是唯讀的

**Reason**: align 延伸廢止，偵測不再執行。
**Migration**: 無需遷移。
