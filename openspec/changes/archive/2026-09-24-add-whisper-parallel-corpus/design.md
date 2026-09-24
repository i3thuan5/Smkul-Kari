## Context

- 動機見 proposal.md。explore 階段的量測、實驗程式與結果都在 kithann/mt.md 那條線（實驗驅動程式在 `kithann/out/mt/drivers/`）。這份只寫把它做成正式管線要怎麼做。
- 現有的 `scripts/mt/` 是實驗時照 TDD 寫的引擎：load、overlap、textsim、hallucination、features、goldalign、evaluate、glosses，共 82 個測試。這次留下、修改、刪除、新增的清單見下面的檔案樹。
- `scripts.news.rebuild` 已有一套「語音側階段」機制（`speech_stages()`，每個階段帶一個重產函式，由 coaxial 逐 byte 比對），這一層照同一個機制接上去。
- 官方辭典的讀取、切詞、命中率三支程式在 `scripts/aiyalaeho/langcheck/`，內容跟語料無關。

## Goals / Non-Goals

**Goals:**

- 交付物（一集一檔 CSV）是 store 輸入加上辭典的純函式，`rebuild --verify` 驗得到。
- 所有門檻集中在一處。調參後只改那一處、重產，就全部生效。
- 調參有明確的樣本數與收件紀律；結果寫進資料層的 README。

**Non-Goals:**

- 不切到逐詞或逐條字幕的粒度。使用者裁定，翻譯模型接受段落。
- 正式產出不叫任何模型：裁判只用在調參。
- 不做華語音譯偵測、散開重複的偵測、數字對照這些新特徵。explore 已列為之後可加的項目，不在這次範圍。
- 不處理 2021-11 以後的集數；只要改範圍常數就能擴大。
- 開會了不產語料；它只提供標準答案（`tools/mtgold/`）。

## Decisions

### 一、對齊用「字幕歸給重疊最多那段」加合併門檻

開會了 38 集的標準答案（chunk30 是把段落併成 30 秒以內，模擬新聞的切段）：

| 做法 | 正確率 | 詞召回 | 組長中位 |
|---|---|---|---|
| 字幕歸重疊最多那段，合併門檻 30% | 92.5% | 0.591 | 23.6 s |
| 字幕歸重疊最多那段，不合併 | 90.7% | 0.644 | 22.7 s |
| 有重疊就併（mt.md 的做法一） | 94.4% | 0.342 | 28.3 s |
| 用譯文 chrF 重派跨界字幕 | 88.1% | 0.630 | 22.8 s |

- 做法一的正確率最高，但召回只剩三分之一，而且新聞上會串出 495 秒的長鏈（一條字幕多溢出 0.1 秒，就把兩個段落焊在一起）。
- 用譯文重派比純看時間更差，因為 sapolita 的譯文太弱。
- 「有重疊就併」與「用譯文重派」兩個函式和它們的測試都刪掉；結論留在這一節。
- 合併門檻原本暫定 30%，調參後定為 10%（見第六點最後的結果）。

### 二、分層只用不需要模型的特徵

三個獨立驗證的排序一致：辭典 ＞ chrF ＞ 其他。三個驗證是：開會了標準答案、新聞 128 組 Claude 裁判、kaldi 線 8,619 組的既有裁判。時間覆蓋率、長度比、每秒詞數、壓縮比的 AUC 都在 0.46～0.59，不採用。logistic 組合的 AUC 0.79，只比辭典加 chrF 好一點，所以用簡單規則。規則見 spec「三層分層與不採用原因」。

辭典釋義錨點（`glosses.py`）的 AUC 只有 0.61～0.64，刪掉。

### 三、校正基準凍結成表

基準是從語料本身算出來的：各族前 90 秒、至少 5 個詞的組，其命中率中位數。每次執行都重算的話，每加一批，舊集數的分層就會變。所以用 `pairs_run --recalibrate` 明確重算，平時只讀表。

基準要用哪種合併門檻下的組來算？一律用當時生效的門檻。調參改了門檻後，要跟著跑一次 `--recalibrate`，這一步寫在 tasks 裡。

### 四、辭典搬到頂層 `scripts/lexicon/`

新聞 rebuild 要用辭典。辭典留在 `aiyalaeho/langcheck` 的話，依賴會變成 news → mt → aiyalaeho，方向顛倒。`scripts/languages.py` 就是因為同樣的理由搬到頂層的。

- 三支檔只搬位置、內容不改。
- `mark.py`、`report.py`、`hallucination.py` 改 import。
- 開會了的 `rebuild --verify` 逐 byte 不變，當作驗收。

另一個做法是 mt 直接 import aiyalaeho。沒採用，理由是依賴方向。

### 五、辭典在 kithann，缺檔去 SFTP 抓

使用者裁定：辭典不入庫；SFTP 保證有辭典。

- `news/lexicon_fetch.py` 列出遠端目錄，依檔名裡的族名對到本機 `kithann/族語辭典/`，位元組數不符就用 `sftp.sh get` 抓。
- 蒸餾結果放 `kithann/族語辭典/詞庫/<族語>.txt`，當作快取：原檔比詞庫新就重蒸餾。
- 取得失敗照 `news/audio.py` 抓影片的規矩：刪掉半個檔，並指名中止。
- 族名的解析：檔名形如 `…_10邵語5230筆(fin)(哈瑪星).xlsx`，取「_兩位數字」與「語」之間那段，再用 `scripts/languages.py` 的 `LANGUAGES` 驗證是 16 族之一。

### 六、調參的方法

- **一處的定義**：相鄰兩段語音之間的一個邊界。這個邊界上跨界的字幕中，「較少那邊佔字幕長度的比例」最大的那一條，決定這一處屬於哪一格。合併門檻 t 就是「這個比例 ≥ t 的邊界要合併」，所以門檻從一格移到下一格，只會影響落在那一格的邊界。
- **樣本數**：新聞 2021-01～10 各格的字幕數，0–10% 有 26,723、10–20% 有 20,040、20–30% 有 15,453、30–40% 有 9,904、40–50% 有 3,770，都遠多於 97。每格 97 處（95% 信心、誤差 ±10 點；使用者裁定先用這個量），固定種子。
- **三個組**：每一處拿出三個組（只看這兩段，其他邊界一律不合併，以便隔離這一個變因）：
  - 合併版 G：兩段加上歸給它們的全部字幕；
  - 拆開版 A、B：各段加上歸給它的字幕，跨界字幕歸較多那邊。
  - 判定次數是 485 處 × 3 組 ＝ 1,455 次。
- **比較**：每組的分數 ＝ 族語詞數 ×（高 1、中 0.5、低 0）。合併版的分數大於 A、B 相加，算「合併較好」；小於算「拆開較好」；相等算「一樣」。用「可用詞數」比，是因為語料的價值在留下多少可用的詞，不在組數。
- **每格的判定**：「一樣」的處不計，p ＝ 合併較好 ÷（合併較好＋拆開較好）。p 的 Wilson 95% 區間整段高於 0.5 為合併較好，整段低於 0.5 為拆開較好，跨過 0.5 為分不出。
- **選值**：取最低的候選值 t（10%、20%、30%、40%），使 t 以上每一格都是合併較好或分不出。分不出時以較低的門檻為主（使用者裁定：多合併）。40–50% 那格就拆開較好時選不合併。0–10% 那格不對應任何候選值，只用來確認「連細縫都併」是不是真的不好，結果列在表上。
- **判準**：沿用 explore 的段落版 prompt，入 repo 作為 `scripts/mt/judge_prompt_paragraph.md`。
- **批次**：一批 200 組，由 Opus subagent 判；G 與 A、B 放在不同批次。
  - 回覆不再「讀回來檢查」，由收件程式檢查編號集合。
  - 一批 200 組約 80k tokens，超過 Read 工具一次讀取的上限，所以請求拆成 4 個 50 組的檔、同一個 subagent 依序讀。
  - 單列超過 1,800 字元的處不抽，Read 會截斷過長的行。量過請求列最長 2,044 字元，新聞 p99 的族語 103 詞、華語 141 字，這樣只排除極少數。
- **收件**：照 `scripts/asrmt/judge.py` 的整批收下紀律；回覆放 `kithann/out/mt/調參/`。
- **成本**：1,455 次判定約 7 批。依 explore 實測推估，每批約等於 US$1.5～2 的牌價，合計約 US$13，算在 Max 20x 的額度裡。結果若多數格分不出，可以再加抽，擴到 95%／±5 點（每格 385 處）。
- **結果（2026-09-24）**：485 處、1,343 組全部收齊，五格都是合併較好（區間下緣 0.52～0.65），依規則取 10%。0–10% 那一格也是合併較好，但 0% 不在候選值裡，而且這個比較量不到串鏈；10% 產出後組長 p99 69 秒、最長 232 秒。完整表格在 `2-平行語料/README.md`。
- **免費的第一步**：`tools/mtgold/sweep.py` 在開會了標準答案上掃同樣六個值。結果並列在 README，但對談節目的切段跟新聞不同，不當決定依據。

### 七、放在哪一層

- `mt/`：只做計算。輸入是 dict 與字串，輸出是 dict 與字串，不碰路徑。
- `news/`：範圍、路徑、SFTP、入庫、重建。
- `tools/mtgold/`：讀開會了的 store 與 `kithann/out/mt/aiyalaeho-sapolita/`，屬於量測工具。

## 檔案樹（產出來源與輸入）

```
kithann/族語辭典/                             news/lexicon_fetch.py ← SFTP /docker/族語辭典_單詞與例句/
├── *.xlsx                                    16 族原檔
└── 詞庫/<族語>.txt                           lexicon.dictionary.distil ← xlsx（快取）
kithann/out/mt/調參/                          news/pairs_tune.py
├── sample.csv                                ← 新聞 1-cues＋2-vision＋1-srt-sapolita，固定種子
├── request-NN-{a,b,c,d}.tsv                  ← sample.csv
└── reply-NN.tsv                              ← Opus subagent；pairs_tune --ingest 收件
Kari-SRT/news/2-asr-whisper/
├── README.md                                 改（人工）：流程圖、「誰讀」
└── ★2-平行語料/
    ├── README.md                             人工：這層是什麼、分層規則、門檻與調參結果
    ├── 校正基準.csv                          news/pairs_run.py --recalibrate ← 全部組的開場命中率
    └── <年-月>/<成果檔名>.csv                news/pairs_run.py ← 1-cues＋2-vision＋1-srt-sapolita＋smkul.csv＋校正基準＋詞庫
scripts/
├── ★lexicon/__init__.py
├── ⇐lexicon/dictionary.py                   原 aiyalaeho/langcheck/dictionary.py
├── ⇐lexicon/vocab.py                        原 aiyalaeho/langcheck/vocab.py
├── ⇐lexicon/script.py                       原 aiyalaeho/langcheck/script.py
├── aiyalaeho/langcheck/mark.py、report.py    改：import scripts.lexicon
├── mt/load.py、textsim.py、features.py、goldalign.py、evaluate.py   留
├── mt/overlap.py                             改：刪 transitive_groups、rescored_groups
├── mt/hallucination.py                       改：import scripts.lexicon
├── ✖mt/glosses.py
├── ★mt/calibration.py                        開場中位數的計算、基準表的讀寫與查無中止
├── ★mt/tier.py                               門檻常數（含合併門檻）、分層、不採用原因
├── ★mt/pairs.py                              一集的組 → CSV 字串
├── ★mt/tuning.py                             分格、抽樣、三組請求、收件、比較、Wilson 區間、選值
├── ★mt/judge_prompt_paragraph.md             調參裁判的判準
├── mt/README.md                              改
├── news/paths.py                             改：PAIRS_DIR、CALIBRATION、LEXICON_KITHANN、TUNING_WORK
├── ★news/lexicon_fetch.py
├── ★news/pairs_run.py                        CLI：整批／指名集數／--recalibrate
├── ★news/pairs_tune.py                       CLI：--sample／--ingest／--report
├── news/rebuild.py                           改：speech_stages() 加上 2-平行語料；包含規則加兩條
└── README.md                                 改：lexicon/、mt/ 兩節，news/ 表補三支，tools/ 表補 mtgold
tools/★mtgold/
├── __init__.py
├── sapolita_aiyalaeho.py                     開會了送 sapolita → kithann/out/mt/aiyalaeho-sapolita/
└── sweep.py                                  開會了標準答案上掃六個門檻值
tests/
├── ★lexicon/{__init__, fixtures}.py、⇐test_dictionary.py、⇐test_script.py、⇐test_vocab.py、README.md
├── aiyalaeho/langcheck/test_mark.py、test_report.py、fixtures.py、README.md   改
├── mt/test_overlap.py                        改：刪兩組
├── ✖mt/test_glosses.py
├── mt/★test_lexicon.py                       測 news/lexicon_fetch（SFTP 用假的）
├── mt/★test_calibration.py、★test_tier.py、★test_pairs.py、★test_tuning.py
├── mt/★test_run.py                           測 news/pairs_run
├── mt/README.md、tests/README.md             改
├── news/★test_rebuild_pairs.py
└── ★tools/mtgold/{__init__, test_sweep}.py
```

`test_lexicon.py` 與 `test_run.py` 測的是 `news/` 的模組，卻放在 `tests/mt/`。這是第二層已確認的位置：這條線的測試集中一處讀。對照表會註明它們測的是哪支程式。

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| whisper-parallel-corpus | 字幕 0.1 秒溢出到下一段不可把兩段焊起來；純做法一在新聞串出 495 秒的組 | `mt/test_overlap.py` |
| whisper-parallel-corpus | 字幕在兩段各佔 40%／60%，門檻 30% 要合併；剛好等於門檻算合併 | `mt/test_overlap.py` |
| whisper-parallel-corpus | 對齊要用 1-cues 的真實窗，不是 SRT 含 0.5 秒留白的窗（留白會讓每條字幕都碰到鄰段） | `mt/test_load.py` |
| whisper-parallel-corpus | 開頭 t=0 的色條 cue 不配對 | `mt/test_load.py` |
| whisper-parallel-corpus | 「harung uri」兩個詞辭典命中 1.0，中信心抽樣的 6 個低有 3 個是這種碎片 → 詞數不足 | `mt/test_tier.py` |
| whisper-parallel-corpus | 邵語新聞的泰雅講者，本族命中率也過門檻，仍要判別族語言 | `mt/test_tier.py` |
| whisper-parallel-corpus | 片尾「ʼa ʼa ʼa…」、譯文「一、二、三…」→ 幻覺 | `mt/test_tier.py` |
| whisper-parallel-corpus | chrF 0.01 最多中信心；門檻邊界用 ≥ | `mt/test_tier.py` |
| whisper-parallel-corpus | 多個原因時照優先序只寫一個，重跑相同 | `mt/test_tier.py` |
| whisper-parallel-corpus | 卑南 0.17、魯凱 0.20 vs 卡那卡那富 0.67，固定門檻會讓四族只留 7～17%：基準要按族 | `mt/test_calibration.py` |
| whisper-parallel-corpus | 加一個月份，基準表逐 byte 不變；只有 --recalibrate 才重算 | `mt/test_run.py` |
| whisper-parallel-corpus | 查不到族語別要指名中止，不可退回 0.5（實驗程式曾這樣寫） | `mt/test_calibration.py` |
| whisper-parallel-corpus | kithann 沒有辭典 → 從 SFTP 抓，比對位元組數；不完整就刪檔中止；已有且相符不重抓 | `mt/test_lexicon.py` |
| whisper-parallel-corpus | 檔名日期「20260702_」改版會變，族名要從「_10邵語」那段讀 | `mt/test_lexicon.py` |
| whisper-parallel-corpus | 只有 15 族 → 指名缺哪族中止（少一族會讓講那族的人全被誤判） | `mt/test_lexicon.py` |
| whisper-parallel-corpus | 欄位先後照使用者指定的 13 欄，加上不採用原因 | `mt/test_pairs.py` |
| whisper-parallel-corpus | 時間戳「00:00:26,220」與族語「sbaw,」含逗號，讀回來一字不差 | `mt/test_pairs.py` |
| whisper-parallel-corpus | 族語保留 sapolita 的撇號 ʼ 不改；UTF-8 無 BOM、LF；重跑逐 byte 相同 | `mt/test_pairs.py` |
| whisper-parallel-corpus | 一組都配不出來的集數仍寫只有表頭的檔 | `mt/test_pairs.py` |
| whisper-parallel-corpus | 2021-11 的集數兩側都有也不做 | `mt/test_run.py` |
| whisper-parallel-corpus | 2021-07 sapolita 71 集、交付字幕 70 集：缺一側只列出，離開碼 0 | `mt/test_run.py` |
| whisper-parallel-corpus | 分格用較少那邊的比例；≥50% 不會出現（新聞 0 條） | `mt/test_tuning.py` |
| whisper-parallel-corpus | 同一種子抽到同一批；格內不足 97 處就全收並註明 | `mt/test_tuning.py` |
| whisper-parallel-corpus | 合併版與拆開版在不同批次；單列超過 1,800 字元的處不抽（Read 會截斷） | `mt/test_tuning.py` |
| whisper-parallel-corpus | 回覆 199／200 列 → 整批退回並指名缺的編號（kaldi 線：半收會讓判定貼到別組） | `mt/test_tuning.py` |
| whisper-parallel-corpus | 分數＝詞數 ×（高 1、中 0.5、低 0）；「一樣」不計；Wilson 區間跨過 0.5 → 分不出；分不出時取較低門檻；40–50% 就拆開較好 → 不合併 | `mt/test_tuning.py` |
| whisper-parallel-corpus | 整批產出沒有任何模型呼叫 | `mt/test_run.py` |
| whisper-parallel-corpus | 開會了掃六個門檻值，每個值出一列；107 沒有 sapolita 結果，列出來、不當錯誤 | `tools/mtgold/test_sweep.py` |
| srt-data-store | 手改入庫 CSV 一格 → --verify 指名該集 | `news/test_rebuild_pairs.py` |
| srt-data-store | kithann 沒辭典 → 先抓再驗；SFTP 也失敗 → 指名中止，不可宣告通過 | `news/test_rebuild_pairs.py` |
| srt-data-store | 2-平行語料有而 1-srt-sapolita 或 3-srt 沒有 → 包含錯誤；還沒做的不算錯 | `news/test_rebuild_pairs.py` |
| （搬移） | 辭典三支搬到 scripts/lexicon 後，開會了語言檢查兩張 CSV 逐 byte 不變 | `aiyalaeho/test_rebuild.py`（既有）＋`aiyalaeho.rebuild --verify` |

## Risks / Trade-offs

- [開會了是對談節目，切段形態跟新聞不同] → 門檻最後以新聞裁判的結果決定，開會了只並列參考。
- [裁判不懂族語，只能靠華語、借詞、數字、專名判斷] → 裁判只用在比較兩種版本誰好（相對判斷），不當絕對的真值。兩個版本受同一個裁判的偏差影響，比較時大致抵銷。
- [±10 點誤差，每格合併較好的比例要偏離 50% 約 10 點以上才分得出] → 分不出時以較低門檻為主（使用者裁定）；多數格分不出時再加抽到 385 處。
- [Max 額度] → 約 7 批，每批跑完就收件，可以續跑。
- [辭典改版] → 改版後詞庫會變，所有集數的分層也會變。這是預期行為：重跑產出與 `--recalibrate` 後 commit，README 記下辭典版本（xlsx 檔名的日期）。
- [搬辭典動到開會了] → 只改 import；開會了的 `rebuild --verify` 是驗收條件。

## Migration Plan

1. 先搬辭典，開會了 rebuild 通過。
2. 做產出管線，用暫定門檻 30% 跑 2021-01～10 並入庫。
3. 調參。若選定的值不是 30%，改常數、`--recalibrate`、重產、commit。

每一步都能獨立驗收；回退就是 revert 那個 commit。
