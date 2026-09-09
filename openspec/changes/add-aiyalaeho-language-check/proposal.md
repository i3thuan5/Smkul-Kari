## Why

《開會了》的交付 SRT 每條兩列，族語列與華語列都來自畫面。但那個「族語列」並不總是本集的族語：39 集 28486 條裡，有 822 條整列空白（畫面上只有一列華語）、1419 條族語與華語夾雜、2 條兩列裝反，還有整段別族來賓講自己族語的段落——122 布農集裡有排灣族來賓講排灣語，華語列自己寫著「我是來自台東賓茂部落的排灣族」。這些條目拿去當本族的平行語料就是錯的，而現在沒有任何地方記錄它們在哪裡。

要回答「這個檔案裡有沒有多語言」不需要模型：空白列由版面幾何決定、夾華語由字元決定、別族族語由官方族語辭典的詞庫比對決定，三者都是離線的純計算。

## What Changes

- 新增交付物 `Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/`：兩張 CSV（逐條、逐集）與 16 族的蒸餾詞庫。
- **逐條資料一律讀 `3-srt/`**，不讀 `1-cues/`、`2-vision/` 或任何中間檔。交付 SRT 已含條號、時間戳與兩列文字，是唯一需要的輸入；自己數 cue 當條號會在有合併的 4 集對歪（094 泰雅合併掉 78 條）。連帶結果：`開始時間` 是 SRT 的時間（**含 0.5 秒留白**），兩列皆空的 cue 不存在。
- **`這列的語言` 是封閉字彙，前三個是事實、第四個是候選**：`無`（畫面只有一列，那一列是華語）、`<族語>語夾華語`、`華語`、`無法確定`（詞庫比對指向別族）。純本集族語的列不進逐條 CSV——那是常態，佔 90.9%。
- **字元分類用 Unicode 類別，不用 ASCII 範圍**。語料裡有 `ʉ`（737 次）、`ē`、`è` 是拉丁字母但不在 `a-z`；`ㄅㄆㄇㄈ` 出現在 4 條族語列，是注音不是漢字。標點與數字不計。
- **別族族語靠官方辭典，不靠語料自己**。SFTP `/docker/族語辭典_單詞與例句/` 有 16 族各一個 xlsx（單字＋詞根＋例句原文，各 4728–33402 筆）。實測三族 19/19 全對，最弱的一集也有 2.4 倍差距；用語料自己當詞庫則只有 33/35，且四個單集族語查不動、布農與卑南互相混淆。
- **南勢阿美要先做正音轉換再比對**：`u→o`、`b→f`、`v→f`，然後對秀姑巒辭典。實測 112、113 各 +17pt（42%→58%、44%→61%），秀姑巒與其他集 +0pt，不誤傷。轉換**只用於比對**，SHALL NOT 改動任何存下來的文字。
- **xlsx 用標準函式庫讀**（`zipfile`＋`xml.etree`），不引進 openpyxl；欄位靠表頭名稱不靠位置。辭典蒸餾成純文字詞庫進 store，否則離線重建跑不起來（xlsx 共 50 MB 留在 SFTP）。

### 新增的檔案與資料夾

```
Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/
├── README.md                    這層是什麼、從哪來、誰讀它；命中率不可跨集比較的理由
├── 詞庫/<族語>.txt              16 檔，一行一詞，由辭典 xlsx 蒸餾（各約 1.1–1.5 萬詞）
├── 逐條語言標記.csv             9 欄，約 2750 列
└── 逐集語言分布.csv             39 列

scripts/aiyalaeho/langcheck/
├── __init__.py
├── script.py                    字元分類：拉丁／漢字／注音（Unicode 類別）
├── dictionary.py                辭典 xlsx → 詞庫 txt（stdlib zipfile＋xml.etree）
├── vocab.py                     詞庫載入、逐族命中率、南勢阿美正音轉換
├── mark.py                      三步 → 逐條標記（只讀 3-srt/）
└── report.py                    兩張 CSV（CLI 進入點）

tests/aiyalaeho/langcheck/
├── __init__.py
├── README.md                    這一組的 spec × scenario × 測試檔對照表
├── test_script.py
├── test_dictionary.py
├── test_vocab.py
├── test_mark.py
└── test_report.py
```

### 修改的檔案

```
scripts/aiyalaeho/paths.py       加 LANGCHECK_STORE／LEXICON_DIR／兩個 CSV 路徑／辭典遠端路徑
scripts/aiyalaeho/rebuild.py     離線重建與逐 byte 驗證涵蓋兩張 CSV
tests/aiyalaeho/test_paths.py    「store 版面」scenario 擴充到 4-語言檢查/
tests/aiyalaeho/test_rebuild.py  兩張 CSV 的重建驗證
tests/README.md                  加一行指到 tests/aiyalaeho/langcheck/README.md
Kari-SRT/aiyalaeho/1-ocr/README.md   流程圖與輸出入對照表補 4-語言檢查/
Kari-SRT/README.md               結構圖補 aiyalaeho/1-ocr/4-語言檢查/
```

## Capabilities

### New Capabilities

- `aiyalaeho-language-check`：《開會了》交付 SRT 逐條的語言判定契約——四級標籤的操作型定義與各自的判定依據、只讀 `3-srt/` 的輸入約束、辭典詞庫的來源與蒸餾、南勢阿美的正音轉換、兩張 CSV 的欄位與語意、離線逐 byte 重建。

### Modified Capabilities

- `srt-data-store`：`aiyalaeho 語料的 store 結構` 的樹狀圖加 `1-ocr/4-語言檢查/`（含詞庫為 store 正本的宣告）；`aiyalaeho 僅靠已 commit 的資料可離線重建` 的重建標的加入兩張 CSV。

## Impact

- **不動既有交付**：`1-cues/`、`2-vision/`、`3-srt/` 一個 byte 都不改，只讀不寫。既有的 `rebuild --verify` 結果不變。
- **不加依賴**：純標準函式庫（`zipfile`、`xml.etree`、`unicodedata`、`csv`）。
- **採購稽核**：辭典來源是原住民族語言研究發展基金會的「16 族前台上線單字」，與既有影片、文稿同一個 SFTP，非新服務、非中國來源、無新套件；照〈外部服務與套件的採購規定〉不需另案稽核，來源與稽核結論寫進 `4-語言檢查/README.md`。
- **成本**：零模型呼叫。一次性下載 50 MB xlsx 蒸餾成詞庫，之後全離線。
- **已知限制**（要寫進 README，不是留白）：辭典一族只收一個方言別，涵蓋率隨方言別浮動（秀姑巒 81%、南勢正音後 58%），所以命中率的絕對值 SHALL NOT 跨集比較；`無法確定` 是候選不是判決，`疑似語言` 只說偏向哪族。
