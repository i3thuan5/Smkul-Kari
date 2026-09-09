# tests/aiyalaeho/text/：spec × scenario × 測試檔對照

《開會了》上字文稿平行語料這一組的測試。跟 `tests/README.md` 總表同一套規矩：檔名管定位（`test_project.py` ↔ `project.py`），這張表管照流程理解。scenario 寫「會出錯的具體情形」，不是功能名——寫法見 `CLAUDE.md`〈TDD 規定〉。

全部離線、fixture 合成。`test_oledoc.py` 最重——fixture 要程式化組出一個最小的 OLE2 複合檔（header＋FAT＋目錄＋兩個串流），不可放二進位檔進 repo。

| spec | scenario | 測試檔 |
|---|---|---|
| aiyalaeho-text-corpus | **`zipfile.is_zipfile()` 對 OLE2 回傳 True，不可據此當成 docx**（Word 把佈景主題當一小段 zip 放在 OLE 檔尾；盤點初期就是這樣把兩個好檔判成壞檔） | `test_decode.py` |
| aiyalaeho-text-corpus | 副檔名選 parser（`.doc`→OLE2、`.docx`→OOXML、`.txt`→純文字），不嗅探內容 | `test_decode.py` |
| aiyalaeho-text-corpus | **解不開就中止並指名**——不改用另一種方式重試、不寫半份 CSV、不記一列然後繼續 | `test_decode.py`、`test_pairs.py` |
| aiyalaeho-text-corpus | UTF-16 有 BOM 的檔（58 個）不可被當成 Big5 解；無 BOM 的當 Big5；UTF-8 BOM 不留在輸出 | `test_decode.py` |
| aiyalaeho-text-corpus | docx 取段落：`<w:p>` 一段一行、`<w:br>` 換行、`<w:tab>` 定位 | `test_decode.py` |
| aiyalaeho-text-corpus | 彎撇 `’`（U+2019）與 `‘`（U+2018）一律換成 ASCII `'`——docx 有 15,411 個彎撇對 11,459 個 ASCII，一半以上的喉塞音是壞的 | `test_decode.py` |
| aiyalaeho-text-corpus | OLE2：走 FAT／miniFAT／目錄取到 `WordDocument` 與 `1Table` 兩個串流 | `test_oledoc.py` |
| aiyalaeho-text-corpus | OLE2：`fWhichTblStm` 決定用 `0Table` 還是 `1Table`，選錯就解不出分片表 | `test_oledoc.py` |
| aiyalaeho-text-corpus | OLE2：分片表兩種編碼都要——壓縮（1 byte／字）與 UTF-16LE；中文走後者，英數可能走前者 | `test_oledoc.py` |
| aiyalaeho-text-corpus | 同一行雙語，`//` 與 `\\` 兩種分隔符都認（時碼檔用 `\\`） | `test_parse.py` |
| aiyalaeho-text-corpus | 時碼行拆成四欄，時間**原樣不換算**——drop-frame 與 non-drop 混用，沒有影片驗不了換算 | `test_parse.py` |
| aiyalaeho-text-corpus | **只有一個時碼（無結束時間）的行只填開始時間**——開會031、032 有幾個檔整份是這個格式，一開始漏了這條分支，1,130 列的族語欄開頭黏著原始時碼字串 | `test_parse.py` |
| aiyalaeho-text-corpus | **時碼抽出來之後才判斷這行的類型，不可以在「內容判不出類型」時拿還帶著時碼的原始行重判**——開會004 一整段逐行帶時碼的純華語旁白就是這樣被抓到的：324 列的時碼字串跑進族語或華語欄，即使加了單時碼支援也還在，直到把時碼抽取搬到判斷之前才修好 | `test_parse.py` |
| aiyalaeho-text-corpus | 有時碼、無內容的行（該窗口沒有話要說）歸 `註記`，不是 `混合` | `test_parse.py` |
| aiyalaeho-text-corpus | 多重分隔符（158 行）照切法表切、標 `雙語（多重分隔符，AI切割）`；表中查無就退回切最後一個並標 `雙語（多重分隔符，規則切割）`——**兩種來歷都寫在 `類型` 上**，不留看不出來歷的值 | `test_parse.py` |
| aiyalaeho-text-corpus | **切法整批接受或整批拒收**——項目集合不符、或某個切法接回來不等於原句，一列都不寫（半批接受會把切法安到別的句子上） | `test_split.py` |
| aiyalaeho-text-corpus | **切法以內容為鍵不以行號為鍵**——重下載後行號位移但文字沒變就沿用；`judge.py` 記過這個教訓（重投影一次，第 304 條變成 309 條） | `test_split.py` |
| aiyalaeho-text-corpus | 切法表逐列有來源檔、原句、族語、華語，不執行程式就看得懂 | `test_split.py` |
| aiyalaeho-text-corpus | **一行真的是兩句字幕黏在一起時（158 行裡實測 4 行是這樣）切法表可以給出兩列**，不因為要湊成一列硬黏在一起或丟掉其中一句；不加序號欄，順序就是列在檔案裡的順序 | `test_split.py`、`test_parse.py` |
| aiyalaeho-text-corpus | **判斷「族語段落裡的漢字是不是完整子句」不能只看字數**——借詞與專有名詞（黑膠唱片、鈴鈴唱片公司、南信彥、多元文化）常常也有 3 個字以上，但不是子句；要看有沒有主詞動詞、讀起來自己是不是一句話 | `test_split.py` |
| aiyalaeho-text-corpus | 隔行配對：羅馬字行＋漢字行成一列（全語料實測涵蓋率 74.8%，落單的歸僅族語／僅華語，不是配對失敗） | `test_parse.py` |
| aiyalaeho-text-corpus | **隔行落單不往下硬配**——歌謠襯字歸 `僅族語`，跳過中間行去抓下一個漢字行會把不相干的兩句黏起來 | `test_parse.py` |
| aiyalaeho-text-corpus | 族華混在一行又沒有分隔符 → 不硬切，整行進族語欄、歸 `混合` | `test_parse.py` |
| aiyalaeho-text-corpus | 註記判定：`OS1`、`Bite`、`035101`、`刪除 113208~` 歸 `註記`，仍留在 CSV | `test_parse.py` |
| aiyalaeho-text-corpus | 空行不出列 | `test_parse.py` |
| aiyalaeho-text-corpus | **語言別代號重用 `catalogue.py` 的 `LANGUAGES`／`VARIETIES`**，不另造一份表——40/41 集光靠目錄名稱比對既有表就解得出來 | `test_lang.py` |
| aiyalaeho-text-corpus | 判得出語言別就用語言別代號，判不出來才退到族語別代號，不得憑空指定 | `test_lang.py` |
| aiyalaeho-text-corpus | 連族語別都查不出來、或混了大量不同族語選不出代表時落到 `und`（ISO 639 標準答案，不是自己發明的代碼），`und` 走跟 `開會036-東布青` 一樣的 `OVERRIDES` 機制，不是自動退的預設值 | `test_lang.py` |
| aiyalaeho-text-corpus | 目錄名稱與內容都比對不出任何代號時中止並指名，不留空不亂猜——`開會036-東布青` 就是這樣才靠內容裡「itu Bunun」這句話覆寫成布農語，不是規則自動解出來的 | `test_lang.py` |
| aiyalaeho-text-corpus | CSV 十欄與順序；`類型` 只出現列舉內的八個值；TAB（2,238 行）換半形空白；逗號（65 行）與雙引號（20 行）由 csv 模組跳脫 | `test_pairs.py` |
| aiyalaeho-text-corpus | **逐檔照收不去重**——同一集的 txt 與 docx 內容相同也各出一份，`來源檔` 分得開 | `test_pairs.py` |
| aiyalaeho-text-corpus | 列順序固定（集 → 來源檔 → 行號），重跑逐 byte 相同 | `test_pairs.py` |
| aiyalaeho-text-corpus | 每列回溯得到出處：`來源檔` 是相對上字文稿根的路徑、`行號` 對得回原檔 | `test_pairs.py` |
| aiyalaeho-text-corpus | 上字文稿不供字：產出後 `1-ocr/` 與兩張進度表一個位元組都沒動 | `../test_paths.py`（store 版面：`text/` 與 `1-ocr/` 各自獨立） |
