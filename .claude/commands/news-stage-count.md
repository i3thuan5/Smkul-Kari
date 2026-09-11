---
description: 統計 Kari-SRT/news 各階段做完幾集，掌握管線進度
argument-hint: "[2021-02]（不填就統計全部月份）"
---

統計 `Kari-SRT/news/` 底下每個階段做完幾集，做成表格。月份篩選：**$ARGUMENTS**（沒給就抓全部）。

## 什麼算一集

每個階段的「一集」在檔案系統上長得不一樣，數檔案數會數錯，要數**去掉副檔名後不重複的檔名**：

| 階段 | 目錄 | 一集長什麼樣 |
|---|---|---|
| 1. cues | `1-ocr/1-cues/<月份>/` | `<集名>.json` 一個檔 |
| 2. vision | `1-ocr/2-vision/<月份>/` | `<集名>/` 一個目錄 |
| 3. OCR SRT | `1-ocr/3-srt/<月份>/` | `<集名>.srt` 一個檔 |
| 4. ASR 逐字 | `2-asr/1-words/<月份>/` | `<集名>.json` 一個檔 |
| 5. ASR 切句 | `2-asr/2-srt-raw/<月份>/` | `<集名>.srt` 一個檔 |
| 6. 雙語 SRT | `2-asr/3-srt-ai/<月份>/` | `<集名>.srt` 一個檔 |
| 7. 品質判斷完成 | `2-asr/4-srt-quality/<月份>/` | `<集名>.srt` 一個檔 |

`2-asr/mt-cache/*.jsonl`、`2-asr/quality-cache/*.jsonl` 是共用快取（機翻、品質判斷結果），不是逐集檔案，**不算進表格**，附註提一下大小就好。

`news/smkul.csv` 是**節目目錄**，涵蓋全部有影片的集數（含還沒做的），所以它的列數是「總共有幾集」，不是「做了幾集」——拿它當分母就好，不要當成某個階段的數字。

## 怎麼數

每個階段、每個月份分開數，例如：

```bash
ls Kari-SRT/news/1-ocr/1-cues/<月份>/*.json 2>/dev/null | wc -l
find Kari-SRT/news/1-ocr/2-vision/<月份> -mindepth 1 -maxdepth 1 -type d | wc -l
ls Kari-SRT/news/1-ocr/3-srt/<月份>/*.srt 2>/dev/null | wc -l
ls Kari-SRT/news/2-asr/1-words/<月份>/*.json 2>/dev/null | wc -l
ls Kari-SRT/news/2-asr/2-srt-raw/<月份>/*.srt 2>/dev/null | wc -l
ls Kari-SRT/news/2-asr/3-srt-ai/<月份>/*.srt 2>/dev/null | wc -l
ls Kari-SRT/news/2-asr/4-srt-quality/<月份>/*.srt 2>/dev/null | wc -l
```

沒有該月份的目錄就跳過（尚未開始），不要當成 0 跟「做完 0 集」混在一起。

## 相鄰階段的落差要點名，不要只列數字

表格數字看不出「差在哪幾集」，人要知道的是**卡在哪裡**、還是**還沒排到**。
每兩個相鄰階段，用去掉副檔名的檔名做集合差，點名哪幾集在前一階段有、
下一階段還沒有：

```bash
comm -23 \
  <(ls Kari-SRT/news/<前一階段>/<月份> | sed -E 's/\.(json|srt|qc\.json)$//' | sort -u) \
  <(ls Kari-SRT/news/<下一階段>/<月份> | sed -E 's/\.(json|srt|qc\.json)$//' | sort -u)
```

（`2-vision` 是目錄，直接 `ls` 目錄名即可，不用去副檔名。）

列出來的集數不多（個位數到十幾集）就整批列名字；很多的話只講數字並附
「還沒排進下一階段」還是「使用者已決定跳過」的判斷依據——後者要有出處
（例如對話裡使用者明講「這幾集先不用做」），不要自己猜。

**下游比上游多是錯，不是進度。** 三個 OCR 階段各自入庫，所以上游跑在前面
是正常的；反過來（`3-srt` 有而 `1-cues` 沒有）表示那份交付物重建不出來，
`rebuild --verify` 會擋下來。看到這種情形要當成問題講，不要寫成「進度」。

## 輸出格式

先出一張表：列＝階段（依管線順序），欄＝月份＋合計，儲存格＝集數。
表格之後接「進度缺口的意義」，逐一點名相鄰階段落差對應到哪幾集、原因
是什麼（還沒排到 / 使用者決定跳過 / 卡住待查）。最後一段附快取檔案的
大小，不列入表格。
