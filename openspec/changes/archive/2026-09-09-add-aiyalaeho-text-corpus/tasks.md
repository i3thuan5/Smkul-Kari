## 1. 路徑常數

- [x] 1.1 在 `tests/aiyalaeho/test_paths.py` 的「store 版面」那條加測試（紅）：`text/` 與 `1-ocr/` 是 `aiyalaeho/` 底下各自獨立的兩層；`TEXT_PAIRS` 落在 `Kari-SRT/aiyalaeho/text/1-句對.csv`；`TEXT_WORK` 落在 `kithann/out/aiyalaeho-text/`；路徑不得帶路徑成分逃出資料資料夾
- [x] 1.2 在 `scripts/aiyalaeho/paths.py` 加 `TEXT_STORE`、`TEXT_PAIRS`、`TEXT_WORK`、`TEXT_REMOTE`（綠）

## 2. Word 97-2003（OLE2）讀取

- [x] 2.1 寫 `tests/aiyalaeho/text/test_oledoc.py` 的 fixture 輔助：程式化組出一個最小 OLE2 複合檔（header、FAT、miniFAT、目錄、兩個串流），不放二進位檔進 repo
- [x] 2.2 加測試（紅）：走 FAT／miniFAT／目錄取得 `WordDocument` 與 `1Table` 兩個串流
- [x] 2.3 加測試（紅）：`fWhichTblStm` 為 0 時讀 `0Table`、為 1 時讀 `1Table`；選錯就解不出分片表
- [x] 2.4 加測試（紅）：分片表兩種編碼都解得開——壓縮（1 byte／字，`fc` 的 bit 30 為 1）與 UTF-16LE
- [x] 2.5 實作 `scripts/aiyalaeho/text/oledoc.py`（綠）
- [x] 2.6 對 `開會029_四季泰雅族` 那兩個真檔跑一次，確認取出 356 行與 199 行、格式是 `族語//華語`

## 3. 解碼與撇號正規化

- [x] 3.1 加測試（紅）到 `tests/aiyalaeho/text/test_decode.py`：**不得以通用 zip 判定函式決定讀法**——它對 OLE2 回報「是 zip」，這是盤點初期把兩個好檔判成壞檔的原因
- [x] 3.2 加測試（紅）：副檔名選 parser（`.doc`→OLE2、`.docx`→OOXML、`.txt`→純文字），不嗅探內容
- [x] 3.3 加測試（紅）：有 BOM 的 UTF-16 不可被當成 Big5 解；無 BOM 的當 Big5；UTF-8 BOM 不留在輸出
- [x] 3.4 加測試（紅）：docx 取段落——`<w:p>` 一段一行、`<w:br>` 換行、`<w:tab>` 定位
- [x] 3.5 加測試（紅）：`’`（U+2019）與 `‘`（U+2018）都換成 ASCII `'`，輸出不得出現彎撇
- [x] 3.6 加測試（紅）：**解不開就中止並指名是哪個檔、失敗在哪一步**——不改用另一種方式重試、不回空字串當沒事
- [x] 3.7 實作 `scripts/aiyalaeho/text/decode.py`（綠），`.doc` 轉呼叫 `oledoc`

## 4. 排版解析

- [x] 4.1 加測試（紅）到 `tests/aiyalaeho/text/test_parse.py`：同一行雙語，`//` 與 `\\` 兩種分隔符都認
- [x] 4.2 加測試（紅）：時碼行 `00:00:14;15 00:00:17;09 族語\\華語` 拆成四欄，時間**原樣不換算**；沒有時間碼的行兩欄留空
- [x] 4.3 加測試（紅）：多重分隔符照切法表切、`類型` 為 `雙語（多重分隔符，AI切割）`；表中查無時退回切最後一個並標 `雙語（多重分隔符，規則切割）`；四種病（分隔符打兩次、開頭就是分隔符、族語內部自己有、兩條 cue 黏成一行）各一條案例
- [x] 4.4 加測試（紅）：隔行配對——羅馬字行＋漢字行成一列，`類型` 為 `隔行配對`
- [x] 4.5 加測試（紅）：**隔行落單不往下硬配**——羅馬字行後面不是漢字行時單獨成列歸 `僅族語`，不得跳過中間行去抓下一個漢字行
- [x] 4.6 加測試（紅）：族華混在一行又沒有分隔符時不硬切，整行進族語欄歸 `混合`
- [x] 4.7 加測試（紅）：`OS1`、`Bite`、`035101`、`刪除 113208~` 歸 `註記`，仍出列
- [x] 4.8 加測試（紅）：空行與只有空白的行不出列
- [x] 4.9 實作 `scripts/aiyalaeho/text/parse.py`（綠）

## 5. 語言別代號

- [x] 5.1 加測試（紅）到 `tests/aiyalaeho/text/test_lang.py`：**重用 `scripts/aiyalaeho/catalogue.py` 的 `LANGUAGES`／`VARIETIES`**，不另造對照表——拿全部 41 個真實目錄名稱去比對，40 個要能唯一解出代號
- [x] 5.2 加測試（紅）：判得出語言別就用語言別代號，判不出來才退到族語別代號（例如 `開會032_澤敖利泰雅` 要出 `tay-x-sul`，`開會002_布農族` 要出 `bnn`）
- [x] 5.3 加測試（紅）：**代號查不出來時中止並指名**，不留空、不編一個規範表裡沒有的代號
- [x] 5.4 加測試（紅）：`開會036-東布青` 用明確覆寫解出 `bnn`——連同覆寫依據（文字內容裡的「itu Bunun」）一起留在程式的註解或常數旁
- [x] 5.5 實作 `scripts/aiyalaeho/text/lang.py`（綠）
- [x] 5.6 對全部 41 個真實目錄名稱跑一次，確認每一個都解出唯一代號、沒有中止

## 6. 多重分隔符交給 Claude 切

- [x] 6.1 寫 `scripts/aiyalaeho/text/split_prompt.md`：說明四種病的樣子、切法規則、回覆格式（含一行可以回兩組族語華語，代表這行其實是兩句字幕黏成一行）；註明改這個檔就要跳版本
- [x] 6.2 加測試（紅）到 `tests/aiyalaeho/text/test_split.py`：**整批接受或整批拒收**——項目集合與工作表不符、或某個切法把每組族語華語接回來不等於原句，一列都不寫並列出不符項目
- [x] 6.3 加測試（紅）：**鍵是內容不是行號**——行號位移但文字沒變就沿用既有切法；文字有變就視為新問題
- [x] 6.4 加測試（紅）：切法表逐列有 `來源檔,原句,族語,華語`，不執行程式就看得懂
- [x] 6.5 加測試（紅）：**一行真的是兩句字幕黏在一起時輸出兩列**，同一個來源檔與原句、不加序號欄，順序照回覆或處理順序——用 `開會011_排灣族/開會了_#11排灣族_第3段.docx` 第 8 行（`na semalji a'en uta//我也很好奇uri 'ivadaq...//想問問秋梅長老`）這個真實案例當測資
- [x] 6.6 實作 `scripts/aiyalaeho/text/split.py`（綠）：出工作表、收回覆、驗證後寫入 `Kari-SRT/aiyalaeho/text/多重分隔符切法.csv`；`split_table` 的值是一或多組 `(族語,華語)` 的清單
- [x] 6.7 加測試（紅）到 `tests/aiyalaeho/text/test_parse.py`：`parse.py` 查到 split_table 裡長度 2 的清單時輸出兩列，`行號` 相同、`類型` 都是 `雙語（多重分隔符，AI切割）`；實作跟著改（綠）
- [x] 6.8 出工作表（158 筆問題行，去重後 135 筆唯一內容），Claude（opus）判讀——**實際找到 4 個「兩句黏一行」案例**（不是預期的 3 個：開會022 line5、開會026 line59、開會011 line8、開會026 line121 各要回兩組族語華語，其餘 131 筆回一組，另 3 筆純分隔符占位無實際內容回空）；收回覆並匯入，`ingest_reply` 全數驗證通過
- [x] 6.9 人工複核切法表：四種病各抽幾列看，另外系統化掃描全部 135 筆（3+ 連續漢字、羅馬字混入華語兩種訊號）確認沒有漏判；順便發現並修正 6 筆「分隔符打兩次」案例規則預設答案殘留分隔符的問題（AI 判讀應該修掉、不是重複規則切割的髒東西），已清乾淨；`Kari-SRT/aiyalaeho/text/多重分隔符切法.csv` 產出 162 列（158＋4個兩列多出的 4 列）

## 7. 句對 CSV

- [x] 7.1 加測試（紅）到 `tests/aiyalaeho/text/test_pairs.py`：十欄與順序為 `集,來源檔,來源檔編碼格式,行號,類型,語言別代號,族語,華語,開始時間,結束時間`；`語言別代號` 一集之內每一列相同（呼叫 `lang.py` 一次，不是逐列重算）
- [x] 7.2 加測試（紅）：**逐檔照收不去重**——同一集兩個內容相同的來源檔各出一份，以 `來源檔` 區分
- [x] 7.3 加測試（紅）：`來源檔` 是相對上字文稿根的路徑、`行號` 對得回原檔
- [x] 7.4 加測試（紅）：列順序為 `集 → 來源檔 → 行號`，同一批來源重跑逐 byte 相同
- [x] 7.5 加測試（紅）：TAB 換半形空白；含逗號與雙引號的文字由 csv 模組跳脫，欄位不破
- [x] 7.6 加測試（紅）：`類型` 只出現列舉內的八個值；任一來源檔解不開時整批中止，不寫出半份 CSV
- [x] 7.7 實作 `scripts/aiyalaeho/text/pairs.py`（綠），CLI 進入點 `python3 -m scripts.aiyalaeho.text.pairs`，錯誤用 `scripts/errors.py` 的 `PipelineError`

## 8. 下載

- [x] 8.1 寫 `scripts/aiyalaeho/text/fetch.sh`：ls 遠端子目錄、逐檔呼叫 `scripts/news/sftp.sh get` 存到 `TEXT_WORK`；檔頭註解寫清楚為什麼不需要續跑與刪檔（9.2 MB，對比 news 的 2.3 TB）；遠端 `開會025` 底下有一層巢狀「上字」子目錄，改成遞迴列目錄
- [x] 8.2 `bash -n` 與 shellcheck 對這一支乾淨（既有 `kithann/` 底下三個臨時檔的 SC2009／SC2012／SC2148 不算）——實際對真實 SFTP 跑過一次，243 個檔全數抓到，9.2 MB，41 個集目錄

## 9. 產出交付物

- [x] 9.1 跑 `scripts/aiyalaeho/text/fetch.sh` 取回 243 個檔（實跑：真的抓到 243 個，9.2 MB）
- [x] 9.2 跑 `python3 -m scripts.aiyalaeho.text.pairs` 產出 `Kari-SRT/aiyalaeho/text/1-句對.csv`（55,785 列）
- [x] 9.3 核對產出：**235** 個可解析來源檔（243 減 6 個 JPG、2 個 Thumbs.db）全部有出列；`類型` 值全在列舉內、且全部是 `雙語（多重分隔符，AI切割）`（135 筆問題行全數經 AI 判讀，沒有落到規則切割）；`集` 涵蓋 41 集；`語言別代號` 無空白
- [x] 9.4 抽查回溯：隨機取 20 列，照 `來源檔`＋`行號`（隔行配對取行號與行號+1 的視窗）在原檔找得到同一行，20/20 通過
- [x] 9.5 再跑一次確認逐 byte 相同——通過

## 10. 文件

- [x] 10.1 寫 `Kari-SRT/aiyalaeho/text/README.md`：這層是什麼、從哪來、誰讀它、十欄各是什麼、`類型` 八個值的意思與信心差別、`語言別代號` 的判定規則（重用哪個對照表、`開會036-東布青` 為什麼是覆寫）；**「AI切割」那一項要寫明哪個模型、哪一版提示詞、有沒有經人複核**，不含糊帶過；不記 design／task 編號
- [x] 10.2 `Kari-SRT/README.md` 的結構圖補 `aiyalaeho/text/`，並註明這一層離線重建不出來、上游在 SFTP
- [x] 10.3 寫 `tests/aiyalaeho/text/README.md`：照 design.md 那張 spec × scenario × 測試檔對照表；`tests/README.md` 加一行指過去
- [x] 10.4 `scripts/aiyalaeho/README.md` 補一節：上字文稿這條線的跑法與兩支指令

## 11. 驗收

- [x] 11.1 `tox -e unittest`（或 `.tox/unittest/bin/python -m unittest discover -s tests -t .`）全綠——跑過全 repo，離開碼 0
- [x] 11.2 `tox -e flake8` 零違規——跑過全 repo（`.tox/flake8/bin/flake8 . --count` 輸出 0）；途中補了一輪 E128（連續行縮排沒對齊視覺縮排），先前手動檢查行長只顧到 79 字元，沒顧到這條，補上這一課
- [x] 11.3 `tox -e rebuild`（或 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify`）通過——`OK: 74 SRTs + smkul.csv rebuilt byte-identical from Kari-SRT`，確認這條線沒有動到交付 SRT
- [x] 11.4 `git -C Kari-SRT status` 確認 `1-ocr/`、`inventory.json`、兩張進度表都沒有被改到——只有 `README.md`（我改的結構圖）跟新的 `aiyalaeho/text/`（新增，不是修改）
