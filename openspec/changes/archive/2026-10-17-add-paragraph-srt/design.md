## Context

- 動機見 proposal.md〈Why〉，要求見兩份 delta spec。
- 現在的配對引擎在 `scripts/mt/`：`overlap.max_overlap_groups` 分組、`overlap.span` 算組的時間、`pairs.row` 寫 CSV 一列。`scripts/news/pairs_run.py` 是整批入口，`measured()` 一次算出一集的組、語音段、字幕、特徵，`episode_csv()` 寫成 CSV。`rebuild.pairs_problems()` 用同一個 `episode_csv()` 逐 byte 比對。
- `overlap.span` 有四個使用者：`pairs.row`（CSV 的時間）、`pairs_run.opening_samples`（校正基準的前 90 秒）、`features.group_features`（`duration`，只給實驗看）、`bilingual_srt.check_span`（抽查時核對 CSV 跟重算的組）。
- `overlap.max_overlap_groups` 另外兩個使用者：`scripts/mt/tuning.py`（調合併門檻）、`tools/mtgold/sweep.py`（《開會了》標準答案量測）。
- `scripts/news/bilingual_srt.py` 是第二期第一批補件時先寫的：從 CSV 讀時間、用 `srtlib.assemble.pad_edges` 留白、輸出到 `kithann/out/news/雙語字幕/`，另有高信心抽查。當時 CSV 時間會重疊，靠 `pad_edges` 的中點相接蓋過去。
- 使用者裁定（2026-10-16）：CSV 的時間也延伸 0.5 秒，鄰居是整集全部語音段；先配對、後延伸（段落越短越好）；CLAUDE.md〈SRT 產出規定〉已改成涵蓋這份 CSV。
- explore 量到的資料性質（2021 年 1–2 月 133 集、15,751 組；校正基準用全部 656 集）：
  - 改用語音段後：85% 的組時間會變，開始往後中位數 0 秒、p90 1.0 秒，結束往前中位數 0.2 秒、p90 1.4 秒，最多 35 秒；相鄰重疊 5,393 → 0 處，剛好相接 1,793 處。
  - 有洞的組 91 組、被夾的段 123 段（中位數 0.64 秒、1 個詞，最多 7 個詞）；91 組裡高信心 30、中信心 19、不採用 42。
  - 落單語音段 1,258 段；高中信心組 15,470 個邊界有 244 個的留白會伸進落單段。
  - 校正基準：前 90 秒改看語音段，656 集只有 2 組跨線，重算只差泰雅 0.0002。
  - 先延伸再配對：組數 15,751 → 12,927、高中信心組 7,735 → 6,780、留下的族語詞 359,000 → 352,200、組長中位數 16.7 → 20.4 秒、6 段以上的組 1.3% → 4.3%、27% 的字幕換組。

## Goals / Non-Goals

**Goals:**

- 兩種時間分得清楚、各有一個出處：真實時間給配對、補洞、校正基準、特徵；延伸後的時間只給 CSV 與 SRT 的輸出。
- 組的時間、補洞、延伸都只在 `overlap.py` 定義一次，CSV、SRT、校正基準、標準答案量測拿到的是同一組配對。
- SRT 是 CSV 的純函式（挑高中信心那幾列），跟 CSV 同一輪產出，`rebuild --verify` 用同一次重算比對兩層。
- 交件與抽查不再自己產 SRT，只讀 Kari-SRT。

**Non-Goals:**

- 不重做合併門檻的調參（要 1,343 組裁判）；10% 沿用，README 註明是補洞前量的。
- 不重算 `校正基準.csv`（凍結的設計不變）。另外量到凍結表跟現在資料重算已有差距（魯凱 0.2667 → 0.30），要不要重算另案決定。
- 不改幻覺規則。抽查判低的組多半是重複片段散在一段裡、沒達到三成門檻，另案處理。
- 不動已交的 `kithann/驗收/第2-1期/補件內容/新聞/`。

## 檔案樹

```
CLAUDE.md                              改（已改）：〈SRT 產出規定〉留白也涵蓋 2-csv-analysis 的時間

Kari-SRT/news/2-asr-whisper/
├── README.md                          改：流程圖與目錄名稱
├── 1-srt-sapolita/                    不動；辨識紀錄.csv 的音長秒是 CSV 的輸入
├── 2-csv-analysis/                    改名（原 2-平行語料/）
│   ├── README.md                      改：時間定義（語音段＋延伸）、補洞、可信度重量
│   ├── 校正基準.csv                    不動（pairs_run --recalibrate 才寫）
│   └── <年-月>/<成果檔名>.csv          pairs_run 產；吃 1-srt-sapolita（含辨識紀錄.csv 的音長秒）、1-ocr/1-cues、1-ocr/2-vision、smkul.csv、校正基準.csv、kithann/族語辭典
└── 3-srt-paragraph/                   ★新
    ├── README.md                      ★新
    └── <年-月>/<成果檔名>.srt          pairs_run 同一輪產；只吃同一集的 CSV 列

scripts/
├── README.md                          改：mt/、news/ 兩張表
├── srtlib/assemble.py                 不動（pad_edges 直接重用）
├── mt/
│   ├── README.md                      改
│   ├── overlap.py                     改：max_overlap_groups 補洞；span 只看語音段（真實）；★padded_spans（延伸後）
│   ├── pairs.py                       改：row 的時間由呼叫端傳入（延伸後），不再自己呼叫 span
│   ├── features.py                    不動（duration 取 span，真實）
│   ├── tuning.py                      不動（經 max_overlap_groups 受補洞影響）
│   └── paragraph_srt.py               ★新：一集的 CSV 列 → SRT 字串（挑高中信心，時間照抄）
└── news/
    ├── paths.py                       改：PAIRS_DIR 指 2-csv-analysis；★PARAGRAPH_SRT；★LEGACY_PAIRS_DIR（只用來偵測）
    ├── pairs_run.py                   改：讀音長、算 padded_spans、同一輪寫 CSV 與 SRT；開場組用 span；舊目錄還在就中止
    ├── rebuild.py                     改：3-srt-paragraph 重建；包含規則；舊目錄還在就失敗
    ├── relabel.py                     改：REMOVE 換新目錄名、加 3-srt-paragraph
    ├── pairs_tune.py                  改：docstring 的目錄名
    ├── bilingual_srt.py               ✖刪：SRT 改由 pairs_run 產；交件、抽查搬到 paragraph_export.py
    └── paragraph_export.py            ★新：--export（從 Kari-SRT 複製 SRT 與 CSV、產一集一列清單到 kithann/out）、--spot-sample、--spot-report

tools/mtgold/sweep.py                  不動；補洞後重跑，更新 2-csv-analysis/README.md 的開會了數字

tests/
├── README.md                          改：總表〈mt〉那行
├── mt/
│   ├── README.md                      改：對照表
│   ├── test_overlap.py                改：span 只看語音段、補洞、padded_spans、配對不看延伸後的時間
│   ├── test_pairs.py                  改：時間照傳入的寫；補洞後族語照時間順序接
│   ├── test_run.py                    改：寫到 2-csv-analysis；CSV 時間是延伸後、開場組看真實；同一輪寫 SRT；舊目錄、音長
│   ├── test_paragraph_srt.py          ★新
│   ├── test_paragraph_export.py       ★新（取代 test_bilingual_srt.py 的交件、抽查部分）
│   └── test_bilingual_srt.py          ✖刪：拆進上面兩個
└── news/
    ├── test_paths.py                  改：目錄名稱
    ├── test_rebuild_pairs.py          改：路徑；3-srt-paragraph 重建與包含規則；舊目錄還在就失敗；缺音長
    └── test_relabel.py                改：3-srt-paragraph 也刪
```

## Decisions

### 一、兩種時間，兩個函式，各有固定的使用者

| 時間 | 出處 | 使用者 |
| :---- | :---- | :---- |
| 真實時間 | `overlap.span(group, segments)`：組內語音段的最早開始、最晚結束 | 配對與補洞（本來就只看段落與 cue 的真實邊界）、校正基準的前 90 秒、`features` 的 duration、抽查請求 |
| 延伸後的時間 | `overlap.padded_spans(groups, segments, duration)`：整集一次算完，回傳每組延伸後的起訖 | CSV 的開始、結束時間；SRT 照抄 CSV |

延伸後的時間只在 `pairs_run.episode_csv` 一處算出來、一處傳給 `pairs.row`；`pairs.row` 不再自己呼叫 span，所以它寫的一定是呼叫端給的那個時間。`opening_samples` 只呼叫 span。SRT 不接觸語音段，只讀 CSV 列。

這樣切的原因是「拿錯」有兩個方向、各會靜靜地出錯：

- 輸出拿到真實時間：CSV 少了留白，看起來完全正常，只有對照影片才發現。
- 計算拿到延伸後的時間：校正基準多收 90.0–90.5 秒開始的組、凍結表對不上；配對若吃到延伸後的段落，組數會從 15,751 變 12,927。

所以兩個方向都各寫一個測試（見第八節對照表最後幾列），用「兩種時間會給出不同答案」的 fixture，拿錯就紅。

另一個做法是 `span` 加一個 `padded=True` 參數：一個函式兩種意思，呼叫端少寫一個參數就拿錯，而且整集延伸需要所有組與音長，不是一組自己算得出來的。不採用。

### 二、先配對、後延伸

量測見 Context 最後一點：先延伸會讓不到 1 秒的空隙被填滿、原本只碰到一邊的字幕兩邊都壓到而合併，組變長、留下的內容反而少，而且 10% 的調參、開會了標準答案、校正基準都要重做。兩種順序算出來的時間完全相同（每段都跟整集全部語音一起延伸，組的頭尾就是某段語音的頭尾），差別只在配對，所以延伸放在最後、只碰輸出。

### 三、補洞放在 max_overlap_groups 裡

配對規則只有一份：交付、標準答案量測、調參看到的都是同一種組。放在 `pairs_run` 的話，`tools/mtgold/sweep.py` 量到的正確率就不是交付的配對了。

補洞只補「第一段到最後一段之間、沒有歸進任何組的段」。各組的真實語音範圍不會交錯（133 集量過，相鄰重疊 0 處），所以夾在中間的段不會屬於另一組；萬一遇到（該段已在別組），不搬動。

代價：`tuning.py` 也會受影響。10% 的調參不重做：補洞動到的組只佔 0.6%，而調參比的是「跨界字幕兩邊的段併不併」，補洞補的是沒有字幕歸給它的段，兩件事不重疊。README 註明調參是補洞前量的。

### 四、延伸：整集語音排成一條時間軸，交給 pad_edges

`padded_spans` 把整集全部語音（每一組的真實語音範圍、加上補洞後仍落單的段）依時間排成一條時間軸，整條交給 `srtlib.assemble.pad_edges`，再取出各組那幾格。真實範圍不重疊，`pad_edges` 的「太近就中點相接、夾在 0 與音長之間」正好是 CLAUDE.md 的規則，跟 `1-ocr/3-srt/` 用的是同一個函式。

延伸前的組範圍若重疊（例如給它舊規則的時間），`padded_spans` 指名中止，不靠 `pad_edges` 的中點相接蓋過去——那正是 `bilingual_srt` 原本的做法，這次拿掉。

另一個做法是只把組當鄰居（`bilingual_srt` 的做法）：244 個邊界會伸進落單段的語音，不採用。

### 五、SRT 由 pairs_run 同一輪產，是 CSV 的純函式

`paragraph_srt` 只吃一集的 CSV 列：挑高中信心、時間照抄、兩行標籤。它不碰語音段與音長，所以不可能「只拿高中信心的組重算延伸」——那會讓不採用的組與落單段不再限制延伸。`pairs_run` 寫完 CSV 文字，用同一批列產 SRT；`rebuild.pairs_problems` 一次重算、比兩層，失敗時指名是哪一層。

### 六、交件與抽查搬到 paragraph_export.py

`bilingual_srt.py` 拆掉，不是改名：它的核心（從 CSV 產 SRT）已經由正式管線取代，剩下的「複製到 kithann/out、產一集一列清單、高信心抽查」是交件時才用的工具，不入 Kari-SRT。名字跟 `3-srt-paragraph` 對齊。

- 清單的時長用 CSV 的時間（延伸後），README 寫明含留白，跟交付的 SRT 一致。
- 抽查要重算組（請求列要用語音段與字幕原文），核對「CSV 跟重算的組對不上就拒絕」時，比的是 CSV 時間與重算的**延伸後**時間——這是第一節「拿錯」的一個實例，測試要涵蓋。

### 七、舊目錄名：偵測到就中止

改名後若 `2-平行語料/` 還在（平行 session 用舊程式跑了一輪、或搬移沒做完），`pairs_run` 與 `rebuild --verify` 都指名中止，不讓兩份並存。`paths.LEGACY_PAIRS_DIR` 只為了這個偵測存在，沒有程式寫它。

### 八、spec × scenario × 測試檔

| spec | scenario（會出錯的具體情形） | 測試檔 |
| :---- | :---- | :---- |
| whisper-parallel-corpus | 20210224_055 撒奇萊雅「對於醫療能有更多的選擇」在配樂空檔掛 27.6 秒，把組的時間拉早 5 秒；133 集最多差 35 秒——組的時間只看語音段 | test_overlap.py |
| whisper-parallel-corpus | 舊規則 133 集相鄰重疊 5,393 處；改後真實範圍不可重疊，剛好相接（1,793 處）不算重疊 | test_overlap.py |
| whisper-parallel-corpus | 拉阿魯哇 003 晨間 13.2 秒的字幕蓋住 185–187 三段短語音，各不到 10% 被丟出組外、卻在組的時間裡——要補進組；組外的落單段不可拉進來（133 集 91 組、123 段） | test_overlap.py |
| whisper-parallel-corpus | 不採用的組也是語音：10.0 秒結束、下一個不採用組 10.4 秒開始，兩邊都只延到 10.2 秒 | test_overlap.py |
| whisper-parallel-corpus | 落單語音段 1,258 段，244 個邊界的留白會伸進去——鄰居要是整集全部語音段（19.8／20.0 → 19.9） | test_overlap.py |
| whisper-parallel-corpus | 語音剛好相接（相差 0）的兩組，延伸 0、照樣相接；第一組 0.2 秒開始夾到 0；最後一組在音長前 0.1 秒結束夾到音長 | test_overlap.py |
| whisper-parallel-corpus | 延伸前的組範圍重疊（舊規則的時間）要中止，不可在中點相接後照樣產出（bilingual_srt 原本就是這樣蓋過去的） | test_overlap.py |
| whisper-parallel-corpus | 補洞後族語仍照時間順序接（不是補在最後）、一個空格；語音段數跟著變；CSV 寫的是傳進來的時間 | test_pairs.py |
| whisper-parallel-corpus | 同一輪寫出 CSV 與 SRT；SRT 的族語、華語、時間跟 CSV 逐字相同 | test_run.py |
| whisper-parallel-corpus | 舊的 2-平行語料/ 還在要指名中止，不可兩份並存（改名時平行 session 可能還用舊程式寫舊路徑） | test_run.py |
| whisper-parallel-corpus | 辨識紀錄.csv 沒有該集或音長秒空白——指名中止，不可不夾音長就產出 CSV | test_run.py |
| whisper-parallel-corpus | 不採用組在 10.4 秒開始、高信心組在 10.0 秒結束：SRT 那條要是 CSV 的 10.2 秒，不是只看高中信心重算的 10.5 秒 | test_paragraph_srt.py |
| whisper-parallel-corpus | 不採用的組不進 SRT、編號連續；一集沒有高中信心的組，仍寫空檔，表示產過 | test_paragraph_srt.py |
| whisper-parallel-corpus | 交件：從 Kari-SRT 複製、清單的條數＝高＋中、時長用 CSV 時間（含留白）；抽查只抽高信心、同種子抽到同一批 | test_paragraph_export.py |
| srt-data-store | 3-srt-paragraph 有 SRT、2-csv-analysis 沒有 CSV——指名該集與缺的那一層 | test_rebuild_pairs.py |
| srt-data-store | 3-srt-paragraph 被手改一個字——rebuild --verify 指名該集；還沒產的集數不算錯 | test_rebuild_pairs.py |
| srt-data-store | 2-平行語料/ 與 2-csv-analysis/ 並存——rebuild --verify 失敗並指名舊目錄 | test_rebuild_pairs.py |
| srt-data-store | 20210116_016 晚間排灣改卑南：3-srt-paragraph 那集也要刪，不可用卑南的檔名留下排灣語辨識的字幕 | test_relabel.py |
| srt-data-store | 目錄常數指到 2-csv-analysis、3-srt-paragraph，舊名只留偵測用 | test_paths.py |
| 兩種時間拿錯 | 輸出拿到真實時間：一組語音 30.0–40.0、前後鄰居都在 2 秒外，CSV 要寫 29.5–40.5，寫成 30.0–40.0 就紅 | test_run.py |
| 兩種時間拿錯 | 校正基準拿到延伸後的時間：一組真實開始 90.3 秒（延伸後 89.8 秒），不可算開場組；另一組真實 89.8 秒（延伸後 89.3 秒）要算 | test_run.py |
| 兩種時間拿錯 | 配對拿到延伸後的段落：前一段 10.0 秒結束、後一段 10.8 秒開始、字幕 10.1–12.0 秒——只歸後一段、不合併（延伸後兩段在 10.4 相接，字幕會壓到前一段） | test_overlap.py、test_run.py |
| 兩種時間拿錯 | features 的 duration 拿到延伸後的時間：30.0–40.0 的組 duration 要是 10.0，不是 11.0 | test_run.py |
| 兩種時間拿錯 | 抽查核對拿到真實時間：CSV 是延伸後的，跟重算的真實時間比會全部判成「對不上」——要跟延伸後的比，正常的 CSV 要通過、手改過的要拒絕 | test_paragraph_export.py |

## Risks / Trade-offs

- [平行 session 在改名那一刻跑 pairs_run，寫到舊路徑] → 偵測到舊目錄就中止（決策七）；apply 時挑那條線沒在跑的空檔搬目錄、重產，做完先跟那條線說一聲。
- [補洞改變 91 組的族語文字，信心層級可能變] → 重產後比對新舊 CSV，數出層級變動的組數寫進 README；變動只在這 91 組內才算對。
- [《開會了》標準答案 93.7% 是補洞前量的] → 重跑 `tools/mtgold/sweep.py`，用新數字更新 README；若明顯變差（超過 1 個百分點）先停下來報告，不直接寫進去。
- [CSV 不再存真實時間] → 真實邊界在 `1-srt-sapolita/` 原樣保留，`語音段數` 與組內段落都查得回來；README 寫明 CSV 的時間含留白、怎麼查回真實邊界。
- [Kari-SRT diff 很大（656 集 CSV 時間全變、656 集 SRT 新增、目錄改名）] → CSV 只有時間兩欄全變，其他欄只有補洞的 91 組附近會變；用逐欄比對的小腳本確認，再交給使用者 commit。
- [已交的補件是舊時間] → 不動，README 與交件說明寫明補件版是改版前的快照；下一批交付用新版。
- [調參沒有在補洞後重做] → 理由見決策三；README 註明。

## Migration Plan

1. 照 TDD 改程式與測試（tasks.md）。
2. 確認沒有 pairs_run／whisper_run 在跑。
3. 在 Kari-SRT 把 `news/2-asr-whisper/2-平行語料/` 改名為 `2-csv-analysis/`（一般的 mv；git 操作由使用者做）。
4. `pairs_run` 整批重產 CSV 與 SRT；`校正基準.csv` 不重算。
5. 新舊 CSV 逐欄比對：時間兩欄全變；其他欄只在補洞的組變。
6. 重跑 `tools/mtgold/sweep.py`，更新 README 的開會了數字。
7. `rebuild --verify`、`name_catalogue --check`、unittest、flake8 全過。
8. 回滾：Kari-SRT 是 git submodule，使用者還沒 commit 前，用 `git restore` 還原工作目錄、把目錄改回原名即可。
