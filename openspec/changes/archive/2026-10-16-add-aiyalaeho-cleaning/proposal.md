## Why

第2-1期驗收交出後，承辦要求對《開會了》已交付的 10 集（阿美 3、賽夏 2、泰雅 2、卑南 2、布農 1）做字幕清洗：(a) 修正多餘空白與重複標點；(b) 比對同一族語各集的單詞拼寫，列出不一致與建議寫法；(c) 比對族語辭典，列出與辭典不同或查無的詞；(d) 提供修改前後對照表，語言別差異與無法確認者另行標示、不直接修改。b、c 只做「多於 1 則影片」的語言，即阿美、賽夏、泰雅、卑南 9 集。

難處在於官方辭典一族只收一個語別（阿美＝秀姑巒、泰雅＝賽考利克、卑南＝南王），而這 9 集不全是那個語別：087 卑南的辭典覆蓋率只有 31%、082 阿美 60%。「與辭典不同」大多是語言別差異，不是錯字；同一族語各集「只差一個字母」的詞對（阿美 621、泰雅 441、卑南 279、賽夏 113 組）裡也混著錯字、整集一致的語言別寫法（082 `kaku` 對其他集 `kako`）和本來就不同的詞（`kamo`／`kamok`）。只靠編輯距離列表會把語言別差異當錯字改掉，違反 d 項。

`kithann/E樂園` 是族語E樂園的教材匯出，43 個語別逐句標了語言別編號（本次 4 族 16 語別，各 1,500～4,000 句），可以拿來判定各集語別、並把「該語別見過的寫法」從錯字候選中排除。用已標語別的集數驗證過：068 秀姑巒、091 賽考利克、112／113 南勢都判對。

## What Changes

- **產出全部放 `kithann/out/aiyalaeho-清洗/`，Kari-SRT 只讀、一個檔都不改**（使用者裁定 2026-10-15）。不回寫 `2-vision`、不重建 `3-srt` 與 `4-語言檢查`、`smkul.csv` 的語言別也不寫回。
- **a 項規則清洗，10 集全做**：彎撇號 `’`、`ʼ` 正規化成 `'`；連續空白縮成一個（族語列、華語列都是；華語列的空白是畫面斷句，縮成一個、不刪）；刪節號 4 點以上縮成 3 點、3 點不動；重複的華語驚嘆號、問號縮成一個。**冒號是詞的一部分**（`'a'iyalaeho:`、賽夏 `kapayaka:i'`、泰雅辭典 `abaw:`），不當標點、不動。`’` 後面夾空白的（全語料 10 行，如 087 `mena’   u`）只換撇號，空白要回看圖條判定是不是同一個詞才併。
- **語言別推測**：每集對 E樂園 各語別詞彙算覆蓋率，並每 60 條分段看第一名是否穩定，判「高／中／混合」。實測：085 賽考利克（87%，次高 49%）、086 南王（76%，其他 23～27%）判高；084 偏海岸（80% 對秀姑巒 77%）、087 偏西群（55% 對知本 53%）判中；082 分段第一名在南勢與秀姑巒／馬蘭之間交錯，判混合。已標語別的集照標記、不重推。
- **b、c 候選與證據**：每個族語詞形一列，並排出現集數與次數、辭典有無、E樂園哪些語別見過、ILRDF Kaldi 模型詞表有無、開會了全語料次數、上字文稿次數、最接近的辭典詞條、其他集的相近寫法。比對不套 `vocab.fold` 的語言別正音（會把 `kaku` 折成 `kako`，語言別差異就從表上消失）。節目名 `'a'iyalaeho:` 的錯拼跨族語分組。
- **規則先篩，剩下的交 Claude（Opus）分類**：該集語別的 E樂園 見過的詞，判為語言別寫法、不算錯；其餘分成錯字／語言別差異／不同詞／斷詞不同／不確定，附建議寫法與理由（四族合計約 2,270 個詞形，約 15 批）。
- **錯字回看原生圖條**（Opus），分成 OCR 讀錯／播出端錯字／看不出來；只有前兩者進清洗版。
- **建議寫法依據順序**：該集語別的權威（辭典語別相同用辭典，不同用 E樂園 該語別）＞ 開會了全語料出現次數 ＞ 上字文稿出現次數。Kaldi 詞表只證明「這族有人這樣寫」，不決定寫法。判語言別差異的不給建議、標待討論。
- **清洗版直接改交付 SRT 的文字行**，不在 cue 層改完再重組：重組時文字變得一樣的相鄰兩條會被 `merge_repeats` 併掉，字幕編號位移，對照表就對不上。清洗版的編號行、時間行和交付版逐 byte 相同。
- **交付四份 CSV**：修改前後對照表、拼寫不一致表、辭典比對表、語言別推測表。處理方式欄只用「已修改／建議統一／待討論／不改」。UTF-8 無 BOM、LF，跟第2-1期交付的 CSV 一致。

### 新增的檔案與資料夾

```
kithann/out/aiyalaeho-清洗/              （gitignore，不進 repo）
├── README.md
├── 1-詞庫/E樂園/<語別>.txt、Kaldi詞表/<族語>.txt
├── 2-候選/<族語>.csv
├── 3-判定/文字分類/<族語>/、看圖/<族語>/
├── 4-清洗版/<srt_name>.srt
└── 5-交付/修改前後對照表.csv、拼寫不一致表.csv、辭典比對表.csv、語言別推測表.csv

scripts/lexicon/
├── klokah.py                    E樂園 CSV＋XML → 各語別詞表
└── kaldi_words.py               Kaldi words.txt → 各族詞表

scripts/aiyalaeho/cleaning/
├── __init__.py、__main__.py
├── paths.py、source.py、rules.py、dialect.py、candidates.py
├── verdicts.py、brief_text.md、brief_image.md
├── apply.py、report.py

tests/lexicon/
├── test_klokah.py、test_kaldi_words.py（fixtures.py、README.md 改）

tests/aiyalaeho/cleaning/
├── __init__.py、README.md、fixtures.py
├── test_paths.py、test_source.py、test_rules.py、test_dialect.py
├── test_candidates.py、test_verdicts.py、test_apply.py、test_report.py
```

修改：`scripts/aiyalaeho/README.md`（加「清洗」一節）、`tests/README.md`（總表加一行）、`tests/lexicon/README.md`、`tests/lexicon/fixtures.py`。

## Capabilities

### New Capabilities

- `aiyalaeho-cleaning`：《開會了》交付字幕的清洗試做——E樂園與 Kaldi 詞表蒸餾、規則清洗、語言別推測、拼寫候選、Claude 文字分類與看圖判定、清洗版 SRT 與四份交付 CSV。

### Modified Capabilities

- `aiyalaeho-language-check`：只改用詞，行為不變。使用者 2026-10-16 裁定不再用「方言」、一律用「語言別」：requirement「方言別正音轉換只用於比對」改名為「語言別正音轉換只用於比對」，另外三條 requirement 內文的「方言別」改成「語言別」。辭典詞庫仍只被讀取，Kari-SRT 的資料與交付流程不變（`4-語言檢查/README.md` 的說明文字跟著改用詞）。
- `parallel-corpus-quality`：只改用詞，行為不變。requirement「機器翻譯語言碼由靜態表決定」內文「SHALL NOT 逐集偵測方言」改為「逐集偵測語言別」（同一裁定）。

## Impact

- **資料**：只新增 `kithann/out/aiyalaeho-清洗/`；Kari-SRT 不動，`tox -e rebuild` 結果不變。讀取來源：`Kari-SRT/aiyalaeho/1-ocr/{1-cues,2-vision,3-srt,4-語言檢查/詞庫}`、`Kari-SRT/aiyalaeho/text/1-句對.csv`、`Kari-SRT/aiyalaeho/smkul.csv`、`kithann/E樂園-解壓/`、`kithann/out/aiyalaeho/<srt_name>.work/2-strips/`、`~/.cache/huggingface` 的 ILRDF Kaldi 模型 `words.txt`。
- **依賴**：不新增套件；E樂園 XML 用標準函式庫 `xml.etree`。E樂園 與 ILRDF 模型都是原語會出品，已在 `add-asr-bilingual-srt` 稽核通過。
- **費用**：Claude Opus subagent，文字分類約 15 批、看圖估一兩百處；平行數照現行規矩（token 緊時一次一個）。
- **對外**：產出是給承辦的試做版，待使用者看過才決定要不要交付、要不要回寫 Kari-SRT。
