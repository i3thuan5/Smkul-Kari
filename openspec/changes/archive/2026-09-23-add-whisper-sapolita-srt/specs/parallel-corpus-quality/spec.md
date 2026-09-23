## MODIFIED Requirements

### Requirement: 判定正本內容定址

判定結果 SHALL 以內容定址存入 `Kari-SRT/news/2-asr-kaldi/quality-cache/`（每個裁判一個 JSONL 檔、一列一筆）：鍵為（裁判、prompt 版本、族語行、華語行、機器譯文、前一條字幕、後一條字幕），值為該裁判給的標籤。SHALL NOT 以條目編號或時間戳為鍵——時間軸換版時編號會整批移位。同一鍵 SHALL NOT 重複詢問模型；重投影後材料相同的條目 SHALL 直接命中。

#### Scenario: 重投影後命中

- **WHEN** 時間軸換版、重投影後某條目的五項材料與先前完全相同
- **THEN** 該條不再問模型，標籤由快取取得

#### Scenario: 鄰句改變視為新問題

- **WHEN** 某條目本身不變，但前一條字幕因 cue 分割而改變
- **THEN** 該條視為新的鍵，重新詢問

### Requirement: 3-srt-ai 三行對照格式

`Kari-SRT/news/2-asr-kaldi/3-srt-ai/<年-月>/<srt_name>.srt` 每條 SHALL 恰為三行，依序：`族語ASR結果：`＋族語行、`華語OCR字幕：`＋華語行、`族語ASR結果翻譯華語-ailabs：`＋該族語行的機器譯文。這兩個交付是分析用，行首標籤 SHALL 標明來源；`2-srt-raw` 的短標籤（「族語：」「華語：」）是正式交付，兩邊 SHALL NOT 混用。族語行與華語行的文字 SHALL 與 `2-srt-raw` 同條逐字相同；族語行為空時譯文行 SHALL 保留前綴、文字留空、不呼叫服務。條目編號與時間戳 SHALL 與 `2-srt-raw` 逐條相同。

#### Scenario: 三行齊全

- **WHEN** 某條族語行非空且譯文已在快取
- **THEN** 該條三行齊全，時間戳與 `2-srt-raw` 同條相同

#### Scenario: 無語音條目

- **WHEN** 某條族語行為空
- **THEN** 譯文行只有前綴，且沒有向翻譯服務發出請求

### Requirement: 4-srt-quality 三行格式

`Kari-SRT/news/2-asr-kaldi/4-srt-quality/<年-月>/<srt_name>.srt` 每條 SHALL 恰為三行，依序：`族語ASR結果：`＋族語行、`華語OCR字幕：`＋華語行、`族華對應品質：`＋高／中／低。檔內 SHALL NOT 出現機器譯文。條目編號與時間戳 SHALL 與 `2-srt-raw` 逐條相同。

#### Scenario: 每條都有品質

- **WHEN** 一集的判定完成
- **THEN** 該檔每條第三行為三級之一，條數與 `2-srt-raw` 相同

#### Scenario: 譯文不進品質檔

- **WHEN** 檢視 `4-srt-quality` 任一條
- **THEN** 沒有任何機器譯文文字

### Requirement: 沒有人力校準時的替代驗證與揭露

在沒有懂族語的人核對之前，高的精度 SHALL 以下列兩項替代驗證並把數字記於 `Kari-SRT/news/2-asr-kaldi/README.md`：(1) 構造法——把裁判給高的條目故意配上別條字幕、改動數字、砍掉後半句後重判，SHALL 全部降級，未降級的類型記為裁判盲點；(2) 自我一致——同一批打亂順序重跑，記錄翻牌率。README SHALL 明寫「高的精度未經人工驗證」。判定快取 SHALL 保留足以日後抽樣人核的資訊。

#### Scenario: 探針必須降級

- **WHEN** 一條裁判給高的條目被換上別條的字幕後重判
- **THEN** 新標籤 SHALL NOT 為高

#### Scenario: README 揭露

- **WHEN** 讀 `2-asr-kaldi/README.md` 的品質段
- **THEN** 看得到構造法與自我一致的數字，以及高未經人工驗證的聲明
