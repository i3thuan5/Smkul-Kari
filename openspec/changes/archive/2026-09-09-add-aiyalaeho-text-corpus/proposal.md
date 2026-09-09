# 《開會了》上字文稿轉成族華平行語料

## Why

原語會給的《開會了》**上字文稿**（製作用的雙語字幕原稿）躺在 SFTP 上沒人用：`/docker/ilrdf-corpus/族語節目/開會了_a_iyalaeho=上字文稿/`，41 集、243 個檔、9.2 MB。裡面是**別人已經打好的族語與華語對照**，約 5.5 萬列句對——影像側花 39 集、每集約 236 萬 token 的視覺辨識才換到 28,048 條，這批的取得成本是 0，而且集號（001–045）和手上影片（068–164）**零重疊**，等於白撿 55% 的平行語料，內容還是完全不同的受訪者與題目。

沒人用的原因是它難讀：編碼有 Big5、UTF-16、UTF-8 三種，格式有 docx、Word 97 的 doc、純文字，排版有四種不相容的寫法，而且 Word 的自動更正把族語正字的喉塞音 `'` 換成了彎撇 `’`（docx 裡 15,411 個彎撇對 11,459 個 ASCII 撇號，**一半以上的喉塞音是壞的**）。要拿來訓練或判定之前，這些都得先弄乾淨。

## What Changes

- 新增 `scripts/aiyalaeho/text/`：從 SFTP 取檔，解碼、正規化、解析成句對 CSV。
- 新增交付物 `Kari-SRT/aiyalaeho/text/1-句對.csv`：十欄，逐檔照收不去重，`來源檔` 欄可回溯到原檔的哪一行。
- **新增 `語言別代號` 欄**，依 `kithann/規範/族語及語言別名稱 - *名稱.csv` 兩份規範——有確定語言別就用語言別，不知道就退到族語別。重用 `scripts/aiyalaeho/catalogue.py` 既有的 `LANGUAGES`／`VARIETIES` 對照表，不另造一份；41 個目錄名稱裡 40 個比對表就解得出來，剩 `開會036-東布青` 靠文字內容裡「itu Bunun」這句覆寫成布農語。這條規則記進 CLAUDE.md，日後任何 CSV 要標語言都照這個做。
- **副檔名決定用哪個 parser，不嗅探內容；解不開就中止並指名**。那兩個 `.doc` 是真正的 Word 97-2003（OLE2 複合檔），不是壞檔；不可拿 `zipfile.is_zipfile()` 當分派器——它對 OLE2 回傳 `True`（Word 把佈景主題當一小段 zip 塞在 OLE 檔尾）。自己寫 OLE2＋Word97 分片表的讀取，**不引進新套件**。
- **喉塞音一律正規化成 ASCII `'`**（`’`、`‘` 都換）。
- **一行有多個分隔符的 158 行交給 Claude（opus）切**，切法存成 `多重分隔符切法.csv` 供人複核，`類型` 標 `雙語（多重分隔符，AI切割）`；規則切的標 `雙語（多重分隔符，規則切割）`，**兩種來歷都寫在 `類型` 上**。「AI切割」是哪個模型、哪一版提示詞、有沒有人複核，寫進資料層的 README。照現有 `judge.py` 的規矩：Claude 的產出以檔案交回、程式驗證後匯入，整批接受或整批拒收，鍵是內容不是行號。
- **時間碼原樣保存，不換算成秒**。8 集附了 `HH:MM:SS;FF`（25 個檔、drop-frame 與 non-drop 混用），但那 41 集沒有影片可驗，現在換算等於先寫死一個沒人驗過的數字。
- 這批文稿**不進交付 SRT**，只當平行語料——與現有 `subtitle-text-source` 的「文稿不供字」同一條規矩。
- 不做離線重建驗證：上游在 SFTP，`rebuild --verify` 涵蓋不到，重跑就是重下載。

### 新增的檔案與資料夾

```
scripts/aiyalaeho/text/
├── __init__.py
├── fetch.sh                     SFTP → kithann 暫存（ls 子目錄、逐檔 get）
├── oledoc.py                    Word 97-2003（OLE2）→ 正文
├── decode.py                    來源檔 → UTF-8（副檔名分派、BOM 定編碼、撇號正規化、解不開就中止）
├── lang.py                      集的目錄名稱 → 語言別代號（重用 catalogue.LANGUAGES／VARIETIES）
├── parse.py                     一個檔的文字 → 一串列（四種排版型）
├── split_prompt.md              多重分隔符怎麼切：規則與四種病的樣子
├── split.py                     出工作表、收 Claude 的回覆、驗證後匯入
└── pairs.py                     掃目錄 → 1-句對.csv（CLI 進入點）

tests/aiyalaeho/text/
├── __init__.py
├── README.md                    spec × scenario × 測試檔對照表（這一組的）
├── test_oledoc.py
├── test_decode.py
├── test_lang.py
├── test_parse.py
├── test_split.py
└── test_pairs.py

Kari-SRT/aiyalaeho/text/
├── README.md                    這層是什麼、從哪來、誰讀它
├── 多重分隔符切法.csv           158 列，Claude（opus）切的，人可複核
└── 1-句對.csv                   交付物

openspec/specs/aiyalaeho-text-corpus/spec.md   （歸檔時由本 change 的 delta 產生）
```

### 修改的檔案

```
scripts/aiyalaeho/paths.py       加 TEXT_STORE／TEXT_PAIRS／TEXT_WORK／TEXT_REMOTE
tests/aiyalaeho/test_paths.py    「store 版面」那條 scenario 擴充到 text/
tests/README.md                  加一行指到 tests/aiyalaeho/text/README.md（表本身放那邊）
Kari-SRT/README.md               結構圖補 aiyalaeho/text/
```

## Capabilities

### New Capabilities

- `aiyalaeho-text-corpus`：《開會了》上字文稿的取得、解碼、解析與交付格式——來源格式判斷、喉塞音正規化、四種排版型的解讀、句對 CSV 的欄位與列順序，以及「文稿只當平行語料、不供字」的界線。

### Modified Capabilities

（無。現有 `subtitle-text-source` 的「文稿不供字」不變，本 change 落在它的同一側；`srt-data-store` 的交付與重建保證也不受影響——這批東西不進 `1-ocr/`，也不進 `rebuild --verify`。）

## Impact

- **資料**：`Kari-SRT/aiyalaeho/text/` 新增一層，約 5.5 萬列的 CSV。`aiyalaeho/1-ocr/`、`inventory.json`、`smkul.csv` 全部不動——001–045 沒有影片，本來就不在 inventory 裡（inventory 是檔名驅動的，每筆都要有 mp4）。
- **程式**：只新增一個 subpackage，既有模組僅 `paths.py` 加常數。
- **依賴**：不新增任何套件。OLE2 與 docx 都用標準函式庫讀（`zipfile`、`xml.etree`、`struct`）；環境裡沒有 `antiword`、`catdoc`、LibreOffice、`olefile`，也不需要。
- **驗收**：`tox -e unittest`、`tox -e flake8`、`tox -e shellcheck`（`fetch.sh` 要過）。注意 shellcheck 這個 env **目前基準線就是紅的**——`kithann/` 底下三個臨時檔在報 SC2009／SC2012／SC2148，與本 change 無關。
- **範圍外**：`/docker/ilrdf-corpus/族語新聞/110年2月_族語新聞文稿`（RTF、逐則新聞一個檔）由另一條 session 處理，本 change 不碰。
