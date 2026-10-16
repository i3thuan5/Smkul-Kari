## Context

動機與範圍見 proposal.md，行為契約見 specs/aiyalaeho-cleaning/spec.md。這裡只記實作方式與量測到的資料性質。

現況：
- 《開會了》交付 SRT 在 `Kari-SRT/aiyalaeho/1-ocr/3-srt/`，每條恆兩行（`族語：`、`華語：`），由 `1-cues`（時間軸）＋`2-vision`（文字）經 `make_srt` 組成；組裝時相鄰同文字的 cue 會被 `merge_repeats` 併成一條。
- 讀字規範 `scripts/aiyalaeho/brief.md` 要求照畫面抄：`’` 與 `'` 是量測確認過的不同符號，節目名的播出端錯拼也照抄。這次清洗不改 Kari-SRT，所以這條規範不動；清洗版與交付版的差別寫在 README。
- 辭典蒸餾在 `Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/詞庫/<族語>.txt`（`scripts/lexicon/dictionary.py` 產），一族只收一個語別。
- `kithann/E樂園/` 是族語E樂園教材匯出；文字檔（CSV、XML）已解到 `kithann/E樂園-解壓/`（90 MB）。語言別編號表在 `kithann/E樂園/E樂園方言編號.txt`（有 BOM、tab 縮排，第 12 號空白）。
- ILRDF Kaldi 族語模型在 `~/.cache/huggingface/hub/models--ILRDF--kaldi_formosan_250514_<族英文名>/snapshots/*/graph/words.txt`：Amis 42,503 行、Atayal 30,976、Puyuma 23,132、Saisiyat 8,409。
- 原生圖條在 `kithann/out/aiyalaeho/<srt_name>.work/2-strips/`（10 集都在）。

量到的資料性質（2026-10-15）：

| 項目 | 數字 |
|---|---|
| 族語列雙空白 | 9 集合計約 60 條（082 22、087 20） |
| 華語列雙空白 | 22 條（086 12） |
| 全語料 `’` | 10 行，全部是「`’` 後接 1～4 個空白」 |
| 刪節號 | 081 `Padaka...........`、`......`、`Sipulun...` |
| 華語重複標點 | 全語料 1 處（`試試看!!`） |
| 族語列夾漢字 | 約 430 條 |
| 辭典覆蓋率（詞次） | 068 81%、082 60%、084 80%、079 89%、092 94%、085 87%、091 86%、086 76%、087 31% |
| 辭典查無詞形 | 阿美 1,063、泰雅 649、卑南 1,484、賽夏 303 |
| 再扣 E樂園（任一語別） | 711、442、1,191、222 |
| 再扣 Kaldi 詞表 | 533、366、1,150、219 |
| 跨集只差一個字母的詞對 | 阿美 621、泰雅 441、卑南 279、賽夏 113 |
| a 項清洗後相鄰兩條變相同 | 0 處 |

## Goals / Non-Goals

**Goals:**
- 一條指令一個步驟，產出可以從 Kari-SRT＋E樂園＋Kaldi 詞表＋`3-判定/` 重跑出逐 byte 相同的結果。
- Claude 判定是唯一不確定的步驟，結果存檔；重跑不重判。
- 清洗版與交付版逐條對得上，對照表引用的字幕編號就是交付版的編號。

**Non-Goals:**
- 不改 Kari-SRT、不改 `brief.md`、不進 `tox -e rebuild` 的驗證範圍（產出在 kithann，gitignore）。
- 不處理華語錯字、大小寫規範、族語列裡的漢字。
- 不為 Kaldi 詞表或 E樂園 另外寫下載程式：兩者缺檔時中止並說明去哪裡拿。

## Decisions

### 一、清洗直接改交付 SRT 的文字行，不重組

替代方案是複製 `2-vision` TSV、在 cue 層清洗、用 `make_srt` 重組。不採用：文字被清洗成一樣的相鄰兩條會被 `merge_repeats` 併掉，字幕編號位移，對照表引用的編號就和交付版對不上。a 項量過 0 處，但 b、c 統一拼寫可能造成。逐條替換文字行，編號、時間行、空行逐 byte 不變。

字幕編號 → cue 的對應（看圖要用）另外算：用 `make_srt.build` 讀 Kari-SRT 的 `1-cues`＋`2-vision`，經 `entries_from` 與 `srtlib.assemble.chain_with_spans` 得到每個編號的真實區間，再找落在區間內的 cue。圖條路徑經 `datadirs.strips_dir()` 解：cue 清單裡寫的是舊名 `strips/…`，實際目錄是 `2-strips/`。

### 二、E樂園 依欄名規則辨認族語欄

欄名有十種以上寫法（`wordAb`、`sentenceAAb`、`lessonAB`、`con_AB1`、`word_AB1`、`Ab_1`、`article_ab`、`matchAAbA`、`sentenceAb`、`word_ab`）。規則：欄名以 `Ab`／`AB`／`_ab` 結尾、或後面只接數字或一個大寫字母（`AbA`、`AB1`）、或含 `_AB`／`Ab_` 者算族語欄。不用「含 ch 算華語」，因為 `choiceOneAAb` 的 ch 是 choice。

語別取自 `dialectId`／`dialect_id`；XML 沒有就取所在資料夾名（生活會話篇 `<語言別編號>/conversation.xml`、閱讀書寫篇 `<語言別編號>/reading.xml`）。不用 `languageId`。

語別全名剝掉「族名＋語」字尾（「南勢阿美語」→「南勢」、「宜蘭澤敖利泰雅語」→「宜蘭澤敖利」），經 `languages.VARIETIES`／`code_for()` 取代號；「賽夏語」剝完是空，退 `xsy`。

替代方案：手寫一張欄名清單。不採用：新教材一加欄位就恬恬漏掉；規則加上「找不到族語欄就中止」比較安全。

### 三、語言別推測的門檻

覆蓋率＝該集族語列詞次中、出現在該語別 E樂園 詞表的比例。每 60 條一段，段內詞次少於 40 的段不算。

- **高**：全集第一名領先第二名 ≥ 10 個百分點，且 ≥ 90% 的段第一名相同。
- **中**：未達高，但 ≥ 70% 的段第一名相同。
- **混合**：其餘。

依據：085 領先 38 點、086 領先 49 點（高）；084 領先 3 點、10 段全同（中）；087 領先 2 點、8／10 段同（中）；082 6／10 段（混合）。已標記的 068 只領先 3 點，所以已標記者一律照標記、不推測。

### 四、哪些候選送 Claude

1. 該集語別權威見過（辭典語別與該集相同時看辭典，否則看 E樂園 該集語別；判中看前兩名、混合看全部語別）→ 不送，不列錯字。
2. 權威沒有、但 E樂園 其他語別見過 → 不送，辭典比對表標「其他語別見過」、處理方式「待討論」。
3. 只有 Kaldi 詞表見過 → 不送，辭典比對表標「族語其他寫法見過」、處理方式「不改」。
4. 完全查無 → 送文字分類。
5. 跨集相近寫法（大小寫不分、撇號正規化後編輯距離 1、詞長 ≥ 4）只列在候選表的「相近寫法」欄、給 Claude 當上下文，不另外決定送不送。分組只在候選這一層做語言別差異對（兩邊都有語別證據、語別不重疊）；含送判詞的組等判完，在報表那一層照「錯字 → 建議寫法」分組。實作時量到：送判詞經「差一個字母」一路連鎖，卑南會串成 68 個詞的一組，拼寫不一致表讀不懂。

文字分類每批 300 個詞形（判定類批次的固定開銷遠大於逐列成本，照使用者 2026-09-08 對判定批次「至少 200、愈大愈好」的裁定；實作時由 150 改 300）；看圖每批 60 處。每個詞形附：最多 3 句出現的族語列＋華語列、出現集數與次數、該集語別、各項證據、相近寫法與次數。輸出 CSV：詞形、類別、建議寫法、理由。

看圖：文字分類判「錯字」者，**逐處**送（OCR 讀錯是逐處的事），加上全部 `’` 夾空白的行。每處附族語列與華語列文字、該字幕編號全部 cue 的族語列圖條路徑。輸出 CSV：成果檔名、字幕編號、詞形、類別、畫面上的寫法、理由。

subagent 一律 Opus；平行數照現行規矩（token 緊時一次一個）。判準寫在 `brief_text.md`、`brief_image.md`，派工時提示裡要帶「語言別差異不修改、看不出來就標看不出來」。

### 五、建議寫法的取法

依序：該集語別權威收錄的寫法 ＞ 開會了全語料（Kari-SRT 該族全部已交付集）出現次數最多者 ＞ 上字文稿（`Kari-SRT/aiyalaeho/text/1-句對.csv` 該族族語欄）出現次數最多者。Kaldi 詞表不參與。判語言別差異的不給。文字分類給的建議寫法與這個順序衝突時，以順序為準，並在理由欄記下 Claude 的建議。

### 六、CSV 寫法

UTF-8 無 BOM、LF，與第2-1期交付的 `開會了清單.csv` 及 `4-語言檢查/` 一致。列排序固定（成果檔名、字幕編號、詞形）。寫法沿用 `langcheck/report.py` 的 `write_table`。

## 完整檔案樹

```
kithann/out/aiyalaeho-清洗/
├── README.md                              手寫；各層是什麼、從哪裡做出來、誰讀它；清洗版與交付版的差別
├── 1-詞庫/
│   ├── E樂園/<語別>.txt                   klokah.py ← kithann/E樂園-解壓/、E樂園方言編號.txt
│   └── Kaldi詞表/<族語>.txt               kaldi_words.py ← ~/.cache/huggingface/…/graph/words.txt
├── 2-候選/<族語>.csv                      candidates.py＋dialect.py ← 3-srt、smkul.csv、4-語言檢查/詞庫、1-詞庫、text/1-句對.csv
├── 3-判定/
│   ├── 文字分類/<族語>/待判-bNN.csv        verdicts.py（送判）← 2-候選
│   ├── 文字分類/<族語>/bNN.csv            Claude subagent ← 待判、brief_text.md
│   ├── 看圖/<族語>/待判-bNN.csv            verdicts.py（送判）← 文字分類判定、3-srt、1-cues、2-vision、2-strips
│   └── 看圖/<族語>/bNN.csv                Claude subagent ← 待判、圖條、brief_image.md
├── 4-清洗版/<srt_name>.srt                apply.py ← 3-srt、rules.py、3-判定
└── 5-交付/
    ├── 修改前後對照表.csv                 apply.py
    ├── 拼寫不一致表.csv                   report.py ← 2-候選、3-判定
    ├── 辭典比對表.csv                     report.py ← 2-候選、3-判定
    └── 語言別推測表.csv                   report.py ← dialect.py 的結果

scripts/lexicon/
├── klokah.py                              ★新
└── kaldi_words.py                         ★新

scripts/aiyalaeho/
├── README.md                              改：加「清洗」一節
└── cleaning/                              ★新
    ├── __init__.py
    ├── __main__.py                        命令列：詞庫／候選／送判 文字|看圖／匯入 文字|看圖／清洗／報表
    ├── paths.py                           輸出各層路徑；拒絕 Kari-SRT 底下的寫入目標
    ├── source.py                          讀交付 SRT 兩列；字幕編號 → cue → 圖條
    ├── rules.py                           a 項
    ├── dialect.py                         語言別推測
    ├── candidates.py                      b、c 候選與證據
    ├── verdicts.py                        送判分批、匯入驗證
    ├── brief_text.md                      文字分類判準
    ├── brief_image.md                     看圖判準
    ├── apply.py                           清洗版 SRT＋修改前後對照表
    └── report.py                          另外三份 CSV

tests/
├── README.md                              改：總表加一行指向 aiyalaeho/cleaning/
├── lexicon/
│   ├── README.md                          改：加 E樂園、Kaldi 詞表的列
│   ├── fixtures.py                        改：合成 E樂園 CSV／XML、words.txt
│   ├── test_klokah.py                     ★新
│   └── test_kaldi_words.py                ★新
└── aiyalaeho/cleaning/                    ★新
    ├── __init__.py
    ├── README.md                          本組對照表
    ├── fixtures.py                        合成 3-srt、1-cues、2-vision、smkul.csv、詞表、圖條
    ├── test_paths.py
    ├── test_source.py
    ├── test_rules.py
    ├── test_dialect.py
    ├── test_candidates.py
    ├── test_verdicts.py
    ├── test_apply.py
    └── test_report.py
```

## 各產出檔的格式範例

使用者 2026-10-15 確認的格式。字幕、編號、時間、次數、證據取自真資料；Claude 判定那兩份是預期的寫法。實作以這裡的欄名、欄序、值域為準。

### README.md（節錄）

```
# 開會了族語字幕清洗（試做）

回應第2-1期驗收承辦第 3 點 a–d。Kari-SRT 只讀，這裡的東西都可以從 Kari-SRT、E樂園、Kaldi 詞表加上 3-判定/ 重跑出來。

| 目錄 | 是什麼 | 誰做的 | 吃什麼 |
| 1-詞庫/ | E樂園 各語別詞表、Kaldi 各族詞表 | 程式 | kithann/E樂園-解壓/、Kaldi 模型 |
| 2-候選/ | 每個族語詞形一列，證據並排 | 程式 | 3-srt、辭典、1-詞庫、上字文稿 |
| 3-判定/ | Claude 的文字分類與看圖判定 | Claude Opus | 2-候選、原生圖條 |
| 4-清洗版/ | 清洗後的 SRT，編號與時間和交付版一樣 | 程式 | 3-srt、3-判定 |
| 5-交付/ | 給承辦的四份 CSV | 程式 | 以上全部 |
```

### 1-詞庫/E樂園/西群卑南語.txt

一行一詞、排序固定、撇號已正規化、全小寫。檔名用 E樂園 的語別全名。

```
...
harem
...
likavung
...
mena'u
...
```

### 1-詞庫/Kaldi詞表/卑南.txt

同上格式，檔名用族語別（跟 4-語言檢查/詞庫/ 一致）。

```
...
harem
...
likavung
...
```

### 2-候選/卑南.csv

```
詞形,出現集數,各集次數,辭典,E樂園見過的語別,Kaldi詞表,開會了全語料次數,上字文稿次數,最接近的辭典詞條,相近寫法,初篩
harem,087,087:41,無,建和;知本;西群,有,61,16,garem,garem（086:46）,該集語別見過
Likavungg,087,087:2,無,,無,2,0,,Likavung（087:10;106:1）,送文字分類
```

初篩的值：該集語別見過、其他語別見過、只有Kaldi詞表見過、送文字分類。

### 3-判定/文字分類/卑南/待判-b01.csv（程式產，送給 Claude）

```
詞形,出現集數,該集語別,辭典,E樂園見過的語別,Kaldi詞表,相近寫法,上下文
Likavungg,087,西群;知本,無,,無,Likavung（087:10;106:1）,"087#188 族語：ay harem pukatelu mawnanta kazu i Likavungg nanta 李芳媚 李老師／華語：接著介紹利嘉部落的李芳媚老師 | 087#190 族語：kemazu i kanta i  Likavungg／華語：我們利嘉部落也是一樣"
```

### 3-判定/文字分類/卑南/b01.csv（Claude 寫回）

```
詞形,類別,建議寫法,理由
Likavungg,錯字,Likavung,同集另寫 Likavung 10 次，華語是利嘉部落；E樂園 知本、西群、建和都收 likavung；多打一個 g
```

類別只能是：錯字、語言別差異、不同詞、斷詞不同、不確定。

### 3-判定/看圖/卑南/待判-b01.csv（程式產，送給 Claude）

```
成果檔名,字幕編號,詞形,建議寫法,族語列,華語列,圖條
開會了_087_Pinuyumayan_卑南,188,Likavungg,Likavung,ay harem pukatelu mawnanta kazu i Likavungg nanta 李芳媚 李老師,接著介紹利嘉部落的李芳媚老師,kithann/out/aiyalaeho/開會了_087_Pinuyumayan_卑南.work/2-strips/t00819000_formosan.png
開會了_087_Pinuyumayan_卑南,376,mena’   u,mena'u,zi harem mu kemani ku mena’   u kana temakesi na lralrak,放眼看這些上族語課的學生,kithann/out/aiyalaeho/開會了_087_Pinuyumayan_卑南.work/2-strips/t01771600_formosan.png
```

一條字幕由好幾個 cue 合成時，圖條欄用分號列出全部。

### 3-判定/看圖/卑南/b01.csv（Claude 寫回）

```
成果檔名,字幕編號,詞形,類別,畫面上的寫法,理由
開會了_087_Pinuyumayan_卑南,188,Likavungg,播出端錯字,Likavungg,畫面上確實是兩個 g，讀字沒錯
開會了_087_Pinuyumayan_卑南,376,mena’   u,播出端錯字,mena’ u,畫面是彎撇加一個全形字距，同一個詞 mena'u
```

類別只能是：OCR 讀錯、播出端錯字、看不出來。

### 4-清洗版/開會了_087_Pinuyumayan_卑南.srt（第 376 條）

交付版：

```
376
00:29:31,480 --> 00:29:40,760
族語：zi harem mu kemani ku mena’   u kana temakesi na lralrak
華語：放眼看這些上族語課的學生
```

清洗版（編號、時間、標籤不變，只有文字不同；harem 是西群寫法，不改）：

```
376
00:29:31,480 --> 00:29:40,760
族語：zi harem mu kemani ku mena'u kana temakesi na lralrak
華語：放眼看這些上族語課的學生
```

### 5-交付/修改前後對照表.csv

```
成果檔名,字幕編號,開始時間,結束時間,列,修改前,修改後,類別,依據
開會了_086_Pinuyumayan_卑南,8,"00:01:16,760","00:01:18,920",華語,稍待一會兒  我們即將共同來探討,稍待一會兒 我們即將共同來探討,多餘空白,連續空白縮成一個（畫面斷句保留）
開會了_087_Pinuyumayan_卑南,188,"00:13:39,000","00:13:45,320",族語,ay harem pukatelu mawnanta kazu i Likavungg nanta 李芳媚 李老師,ay harem pukatelu mawnanta kazu i Likavung nanta 李芳媚 李老師,播出端錯字,同集 Likavung 10 次；E樂園 知本／西群／建和收 likavung；看圖確認畫面就是 Likavungg
開會了_087_Pinuyumayan_卑南,376,"00:29:31,480","00:29:40,760",族語,zi harem mu kemani ku mena’   u kana temakesi na lralrak,zi harem mu kemani ku mena'u kana temakesi na lralrak,撇號,彎撇換直撇；看圖判定 mena'u 是同一個詞，併掉字距
```

類別：多餘空白、重複標點、撇號、OCR 讀錯、播出端錯字、節目名。時間是交付 SRT 的時間（含 0.5 秒留白）。

### 5-交付/拼寫不一致表.csv

一組相近寫法佔好幾列，每列一種寫法。

```
族語別,組別,寫法,各集次數,辭典,E樂園見過的語別,文字分類,建議寫法,處理方式,依據
阿美,阿美-012,kako,068:26;084:16;082:6,有,秀姑巒;海岸;馬蘭;恆春,語言別差異,,待討論,082 混合語別；kaku 只見於南勢 E樂園，是南勢寫法
阿美,阿美-012,kaku,082:17,無,南勢,語言別差異,,待討論,082 混合語別；kaku 只見於南勢 E樂園，是南勢寫法
卑南,卑南-031,Likavung,087:10;106:1,無,知本;西群;建和,,Likavung,建議統一,地名利嘉；E樂園 該集語別收錄
卑南,卑南-031,Likavungg,087:2,無,,錯字,Likavung,已修改,看圖確認播出端多打一個 g
```

### 5-交付/辭典比對表.csv

只列「與辭典不同」或「辭典查無」的詞。

```
族語別,詞形,辭典狀態,最接近的辭典詞條,E樂園見過的語別,Kaldi詞表,出現次數,第一次出現,族語列,華語列,處理方式,依據
卑南,harem,近似,garem,建和;知本;西群,有,087:41,開會了_087_Pinuyumayan_卑南#188,ay harem pukatelu mawnanta kazu i Likavungg nanta 李芳媚 李老師,接著介紹利嘉部落的李芳媚老師,待討論,辭典只收南王卑南語（garem）；087 推測西群，西群 E樂園 收 harem，屬語言別差異
```

辭典狀態：近似（有編輯距離 1 的辭典詞條）、查無。

### 5-交付/語言別推測表.csv

```
成果檔名,族語別(中),smkul標記語別,推測語別,語言別代號,把握,各語別覆蓋率,分段第一名,依據
開會了_086_Pinuyumayan_卑南,卑南,,南王,pyu-x-pym,高,南王 76%;知本 27%;西群 25%;建和 23%,南王 15/15 段,第一名領先 49 點
開會了_087_Pinuyumayan_卑南,卑南,,西群,pyu,中,南王 34%;知本 53%;西群 55%;建和 43%,西群 8/10 段,第一名只領先 2 點；講者提到 Mulivelivek（初鹿）、Likavung（利嘉）
```

語言別代號照 CLAUDE.md：有確定語言別（高、已標記）才用語言別代號，判「中」「混合」退族語別代號（pyu、ami），推測的語別寫在「推測語別」欄（使用者確認 2026-10-15）。

## spec × scenario × 測試檔對照表

★＝這次 explore 實際量到或踩到的。

| spec 條目 | scenario（會怎麼錯） | 測試檔 |
|---|---|---|
| E樂園 依語別蒸餾詞表 | ★ 族語欄名十種寫法（`wordAb`、`sentenceAAb`、`lessonAB`、`con_AB1`、`Ab_1`、`article_ab`、`matchAAbA`…），只認一種會漏掉大半篇 | `lexicon/test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 用「欄名含 ch」認華語，`choiceOneAAb` 的 ch 是 choice，族語句被丟掉 | `lexicon/test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 句型篇有 `languageId`（12）和 `dialectId`（38），拿錯就把卑南四個語別混成一個 | `lexicon/test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 生活會話篇、閱讀書寫篇的語別只寫在資料夾名，XML 裡沒有 dialectId | `lexicon/test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 文化篇單字表欄名是 `dialect_id`、`word_ab`，跟句子表不同；找不到要指名中止，不可恬恬產生空表 | `lexicon/test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ `sa / saya / misasa` 是三個異體，整串當一個詞就三個都對不上 | `lexicon/test_klokah.py` |
| E樂園 依語別蒸餾詞表 | ★ 語言別編號表有 BOM、tab 縮排、第 12 號空白；「南勢阿美語」要剝成「南勢」才查得到代號，「賽夏語」退 xsy，剝不出來要指名中止 | `lexicon/test_klokah.py` |
| Kaldi 詞表只證明存在 | ★ `<eps>`、`<SIL>`、`<UNK>`、`#0`、`<s>`、`</s>` 混進詞表，`<UNK>` 變成見過的詞 | `lexicon/test_kaldi_words.py` |
| Kaldi 詞表只證明存在 | 只有 Kaldi 詞表見過的詞被拿去當建議寫法 | `aiyalaeho/cleaning/test_candidates.py` |
| 產出只寫 kithann/out | 寫入目標落在 Kari-SRT 底下沒擋，交付資料被改 | `aiyalaeho/cleaning/test_paths.py` |
| Claude 判定的送出與匯入 | ★ cue 清單的圖條路徑寫舊名 `strips/`，實際目錄是 `2-strips/`，照清單拼找不到 | `aiyalaeho/cleaning/test_source.py` |
| Claude 判定的送出與匯入 | ★ 一條字幕由多個同文字 cue 合成，看圖只送第一個 cue 的圖條 | `aiyalaeho/cleaning/test_source.py` |
| a 項規則清洗 | ★ 冒號被當詞尾標點刪掉（`'a'iyalaeho:`、`kapayaka:i'`、`abaw:`） | `aiyalaeho/cleaning/test_rules.py` |
| a 項規則清洗 | ★ `’` 後夾空白（087 `mena’   u`）被規則自己併掉，沒等看圖 | `aiyalaeho/cleaning/test_rules.py` |
| a 項規則清洗 | ★ 雙撇 `"`（085 `"awsa'`、092 `'a"iy`）被當重複標點或撇號正規化 | `aiyalaeho/cleaning/test_rules.py` |
| a 項規則清洗 | ★ 華語斷句空白（086 12 條）被整個刪掉，而不是縮成一個 | `aiyalaeho/cleaning/test_rules.py` |
| a 項規則清洗 | ★ 刪節號：3 點被縮掉，或 081 `Padaka...........` 沒縮成 3 點 | `aiyalaeho/cleaning/test_rules.py` |
| a 項規則清洗 | ★ 族語列本來空的（082 171 條）清洗後標籤行不見 | `aiyalaeho/cleaning/test_rules.py` |
| 語言別推測 | ★ 已標語別的 068（只領先 3 點）被重推成「中」 | `aiyalaeho/cleaning/test_dialect.py` |
| 語言別推測 | ★ 只領先 1～5 點（084、087）被判「高」 | `aiyalaeho/cleaning/test_dialect.py` |
| 語言別推測 | ★ 各段第一名交錯（082）被判成全集最高的南勢，而不是「混合」 | `aiyalaeho/cleaning/test_dialect.py` |
| 語言別推測 | 賽夏只有一個語別卻跑推測；語言別代號另造對照表 | `aiyalaeho/cleaning/test_dialect.py` |
| b、c 項候選與證據 | ★ 套 `vocab.fold` 語言別正音，082 `kaku` 被折成 `kako`，語言別差異從表上消失 | `aiyalaeho/cleaning/test_candidates.py` |
| b、c 項候選與證據 | ★ 用錯語別的證據：087 `harem` 對南王辭典被列成錯字 | `aiyalaeho/cleaning/test_candidates.py` |
| b、c 項候選與證據 | ★ 只差一個字母（`kamo`／`kamok`、`mita`／`mita'`、`qani`／`kani`）被直接判錯字 | `aiyalaeho/cleaning/test_candidates.py` |
| b、c 項候選與證據 | ★ 族語列的漢字（約 430 條）、注音、數字進了候選 | `aiyalaeho/cleaning/test_candidates.py` |
| b、c 項候選與證據 | ★ 節目名錯拼（`'a'iylaeho:`、`'a'alaeho:`…）分散在各族語，沒合成一組 | `aiyalaeho/cleaning/test_candidates.py` |
| b、c 項候選與證據 | 大小寫不同（`Likavung`／`likavung`）被當兩個詞形；辭典的 `ʼ` 與字幕的 `'` 對不起來 | `aiyalaeho/cleaning/test_candidates.py` |
| b、c 項候選與證據 | 布農只有 1 集卻進了 b、c 候選 | `aiyalaeho/cleaning/test_candidates.py` |
| Claude 判定的送出與匯入 | 判定漏列、多列、類別不在字彙裡，被恬恬吞掉 | `aiyalaeho/cleaning/test_verdicts.py` |
| Claude 判定的送出與匯入 | 判「錯字」沒有建議寫法 | `aiyalaeho/cleaning/test_verdicts.py` |
| Claude 判定的送出與匯入 | 重跑把已判過的又送一次 | `aiyalaeho/cleaning/test_verdicts.py` |
| Claude 判定的送出與匯入 | 圖條不存在卻送出空路徑 | `aiyalaeho/cleaning/test_verdicts.py` |
| 清洗版 SRT | ★ 在 cue 層清洗後重組，相鄰同文字被併掉、字幕編號位移 | `aiyalaeho/cleaning/test_apply.py` |
| 清洗版 SRT | 判語言別差異、不同詞、不確定、看不出來的被改掉（違反 d 項） | `aiyalaeho/cleaning/test_apply.py` |
| 清洗版 SRT | 以字串替換改到別的詞裡面（`kako` → `kaku` 改到 `kakoay`）；句首大寫改完變小寫 | `aiyalaeho/cleaning/test_apply.py` |
| 交付 CSV | 同一條改好幾處只記一列，看不出改了哪裡 | `aiyalaeho/cleaning/test_apply.py` |
| 交付 CSV | 處理方式出現四個值以外的字 | `aiyalaeho/cleaning/test_report.py` |
| 交付 CSV | 建議寫法沒照依據順序（087 取了南王辭典而不是西群 E樂園）；判語言別差異也給了建議 | `aiyalaeho/cleaning/test_report.py` |
| 交付 CSV | 欄名不是「語言別代號」；有 BOM 或 CRLF；重跑列順序不同、byte 不同 | `aiyalaeho/cleaning/test_report.py` |

## Risks / Trade-offs

- [E樂園 是教材，詞彙量有限（各語別 1,500～4,000 句），口語、人名、地名多半沒有] → 不在權威裡的詞不直接判錯，交 Claude 分類；分類也沒把握的標「不確定」、進待討論。
- [語言別推測的門檻是用這 10 集量出來的，樣本小] → 推測表附各語別覆蓋率與分段結果，讓人看得出把握；已標語別的不推測。
- [082 混合語別，用全部阿美語別當權威會放過一些真錯字] → 寧可漏抓也不把語言別差異改掉，這是 d 項的要求。
- [Claude 文字分類可能把語言別差異判成錯字] → 錯字一律再看圖；只有看圖確認是「OCR 讀錯」或「播出端錯字」才改，其餘都只列表。
- [Kaldi 詞表來自訓練語料，可能本身有錯字] → 只用來標「見過」，不決定寫法、不改字。
- [kithann/ 是 gitignore，換機器產出會不見] → 3-判定 是唯一花錢做出來的，其他都能重跑；試做結果確定要交付時再談是否進 Kari-SRT。

## Migration Plan

不涉及既有資料。試做版交使用者看過後，再決定要不要交付承辦、要不要另開 change 回寫 Kari-SRT。
