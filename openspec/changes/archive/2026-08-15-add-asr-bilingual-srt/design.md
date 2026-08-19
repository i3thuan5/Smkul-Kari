# Design：ASR＋MT 雙語 SRT（乙′）與對不齊偵測

動機見 proposal.md；行為契約見 `specs/`。這裡記技術決定與理由。

## Context

- 35 集交付 SRT 與 `Kari-SRT/cues/`（29,220 cues）已存在。實測
  cue 間隔 97% <0.1s（背靠背）、21.9% 的 cue <1s——cue 邊界落在
  連續語流中，不是語音停頓。
- 交付 SRT 不是 cues.json 的 1:1 投影：`make_srt.py` 會
  `drop_leader`（丟 start<0.5s 的 slate cue）、丟空字幕、
  `merge_repeats`（同文相鄰合併）、`apply_gap_rules`、最後
  `pad_edges` 留白。同軸必須沿用這條鏈，不能自己另算。
- ASR 模型：HF `ILRDF/kaldi_formosan_250514_<族>`（公開、vosk 版型，
  am/graph/ivector 齊備；舊名 `ithuan/...` 是 redirect）。服務端
  [asr-kaldi/app.py](../../../kithann/Formosan-AI/asr-kaldi/app.py)
  已 `SetWords(True)` 但把詞時間丟掉，且輸出經 `capitalize()` 與
  阿美 `u→o` 取代——走本機 vosk 同一顆模型即可全部避開。
- MT 服務：`ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil`
  （gradio 5.49 queue 協定）。實測：Dropdown choices 是
  session-scoped，非阿美語別須同一 `session_hash` 先打 `/lambda`
  換族別、再打 `/translate`，否則 `event: error`；單句實測 ~1s。
- 音檔：`ilrdf-corpus.csv` 的 mp3 欄 1,010/1,029 列有值，一集十幾
  MB。**但 2 月集數的 mp3 路徑在 7 月資料夾、與 mp4 同源**，而
  cue 軸是從 mxf 母帶（開頭有彩條識別卡）切的——兩者可能不同軸。
- 本機：16 core 無 GPU，RAM 時常只剩 ~3GB（有平行 session）。
- `refine-cue-timing` 的資料面已落地（Kari-SRT `718b104`：35 集
  cue 邊界精修至 0.05s、SRT 含 0.5s 留白換版，文字不變），試點
  直接吃精修後的 cues。

## Goals / Non-Goals

**Goals:**

- 試點一集（`20210201_032_晚間_Amis_阿美`）走完全流程並產出報告，
  作為放量與否的 gate。
- 流程各步可中斷續跑、對外請求最少化（快取內容定址）。
- 偵測輸出可獨立覆核（分數與依據落地）。

**Non-Goals:**

- gate（tasks 5.4）核可前不碰其餘 34 集；核可後的放量含在本
  change（tasks 6.x），但門檻與主引擎等參數以試點報告定案為準。
- 不改 Formosan-AI 服務端（露出 word timing 的 API 改法記在
  Open Questions，非本 change）。
- 不動交付 SRT 與 `cues.json` 的**內容**；目錄照技術改組
  （見 D10），`srt-data-store` 契約僅路徑修訂。
- 不處理《開會了》。

## Decisions

### D1：整集本機 vosk 解碼，不逐 cue 打 API

理由：(a) cue 背靠背，逐 cue 切音必斬詞；(b) 短片段無聲學／語言
模型上下文，21.9% 的 cue <1s 常回空；(c) API 只回純文字，事後無法
裁掉 pad 進來的鄰句詞；(d) 29,220 次呼叫（估 12–16 小時）打公開
服務 vs 35 次本機解碼；(e) 本機拿 raw result，避開 `capitalize()`
與 `u→o`。

替代案（棄）：逐 cue 打 `sapolita-kaldi`——上述全部缺點；改服務端
露出 words——要人工部署（Formosan-AI 無 CD），列 Open Question。

解碼細節：ffmpeg 轉 16kHz mono s16le 後以小 chunk（0.125s，比照
服務端 4000 bytes）餵 `KaldiRecognizer`；`SetWords(True)`；每段
`Result()` 的 words 連同該段落界（語音句）一起存。模型以
`huggingface_hub.snapshot_download` 抓、一次只載一顆（RAM 緊）。

### D2：音檔來源 mp3 優先，開跑前驗時長，不合退回 mxf

流程第 0 步：SFTP 抓 mp3，`ffprobe` 時長對 cue 軸預期時長
（該集 manifest/cues 的影片長度，032 晚間為 2880s），容許差 ±1s。
不合即指名中止（spec 要求 fail loud），改抓 mxf（75MB/s 約 4 分鐘）
`ffmpeg -vn` 抽 wav 後刪影片。雙保險：偵測的偏移曲線整集中位數
應近 0——若整條平移固定秒數，就是音檔與 cue 軸不同源的證據，
報告必列。

### D3：同軸靠共用組裝鏈，條目附真實時間窗

雙語 SRT 的條目由 `make_srt.py` 同一條鏈（`build → drop_leader →
entries_from → merge_repeats → apply_gap_rules → pad_edges`）推導，
差別只在：鏈上保留「每個最終條目 ↔ 合併前來源 cue 的真實時間窗
聯集」的對照。詞投影、MT、偵測全用真實窗；SRT 時間戳用留白後的值
——與交付 SRT 逐 byte 同軸自動成立。實作方式是把 `write_srt` 的
entries 流程抽成可回傳對照表的函式供兩邊共用，不複製邏輯。

對照表與投影結果落地為 `2-entries/<srt_name>.json`（每條目：
真實窗、歸入的詞索引、族語行、straddle、翻譯語別碼、各引擎
華語行）——SRT 是它的純 render，除錯與重組（換時間軸、換譯文）
都不必重解碼。

### D4：MT client 與快取

- gradio queue 協定（`/queue/join` + `/queue/data` SSE）自己包，
  不引入 `gradio_client` 套件（依賴重、行為黑箱；協定已實測可行）。
  每個族別一個 session：先 `/lambda` 換族別、再逐句 `/translate`。
- 快取 append-only JSONL，鍵 =（engine, direction, src_lang,
  text）、值 = 譯文，放 `Kari-SRT/news/2-asr/mt-cache/`。內容定址，
  refine-cue-timing 改時間戳後照樣命中；重跑先查快取，miss 才出
  請求；單併發、請求間固定小間隔，禮貌對待公開服務。
- 兩個方向都走同一套：族語→zho_Hant（產 SRT 華語行）、
  zho_Hant→族語（偵測的時間量測用，`translate_1`）。
- **第二引擎 Claude**：比照視覺辨識的 subagent 批次紀律——編號
  句子成批進、TSV 直寫磁碟、寫一次不自行修檔；`ingest` 驗證編號
  歸屬與行數後併入 mt-cache（engine=claude）。Claude 天然可一批
  百句（NLLB 的 1024 token 上限與換行問題在這裡不存在）。
  華語→族語方向的譯文正寫法風險高（兩引擎皆然），不當族語正本，
  但運算已花、全部留痕：gate 前 render 審查版六行到
  `3-srt-raw/`——族語ASR結果、華語OCR字幕翻譯成族語-{ailabs,
  claude}、華語OCR字幕（交付字幕原文直接併入，不跨檔對照）、
  族語ASR結果翻譯華語-{ailabs,claude}——丟進播放器即可對照；
  gate 報告比較兩引擎（互相一致度、各自與字幕的對齊率）。
  **正式版不含 MT**（使用者定案）：兩行僅由原始材料組成——族語＝
  ASR 投影詞原順序、華語＝交付字幕原文——render 到
  `6-srt-complete/`（對照版與審查版不覆蓋不刪除）；「主引擎」
  只剩審查版與偵測敘述的內部用途。

### D5：偵測的具體計分

- **內容分數**：MT(塊內族語)→華語 vs 塊內字幕華語，字元 bigram
  F1（chrF 的簡化版，自寫，不引套件）；逐塊算，條目級取所屬塊
  分數＋條目自己的分數兩欄都記。雙引擎各算一份，歸類取最高分
  （只要有一個引擎對得上就不是 mismatch）；引擎互比一致度另記
  一欄，配對恢復的 DP 分數同樣取雙引擎最高。
- **時間偏移**：zho→族語譯文 vs ASR 詞流窗的**字元 LCS**
  （正規化：2·LCS／兩串長度和），δ 掃 ±3s、步長 0.1s；整集
  曲線 = 逐條目最佳 δ 的 rolling median（窗 21 條目）。不用
  詞袋——MT 與 ASR 斷詞規範未一致（連字號、黏著詞素分寫），
  比對前去空白與連字號、統一小寫。成本可行：窗文字每側約
  20–40 字元，LCS 表 ~1,600 格 × 61 個 δ × ~900 條目，一集
  分鐘級。cue 邊界已精修至 0.05s，δ 解析度以此為底，報告仍
  註明當時邊界精度。
- **錨點（兩類，皆免華語 ASR）**：
  - *數字*：字幕側抽阿拉伯數字與中文數字（含「三十」型轉換）；
    ASR 側找族語數詞與借音數詞。族語數詞表初版只做阿美語。
  - *借詞專名*：新聞主播唸地名／機構名常用華語或日語借音，而
    **族語 lexicon 本來就收了這些借詞**——實測阿美模型的
    `graph/words.txt`（42,503 詞）含 `taypak`（台北）、
    `kalingko`（花蓮）、`kongsiya`（公司）、`kongkoan`（公館）；
    真實語料（068 逐字稿）也見 `Angcoh`（安通）等專名。做法：
    字幕側專名 → 音節序列，與 ASR 詞做音節層級模糊比對
    （編輯距離），命中即錨點，帶精確詞時間。
    漢字讀音資料**不用中國維護的套件**（見 D9）：優先自建
    新聞常見專名小表，需要擴充時取 Unicode Unihan 的 kMandarin
    欄位（Unicode Consortium 維護）。覆蓋率在試點量測後決定
    要不要擴表。
- **塊＝字幕語意句**（使用者定案）：分句標記（每條目行尾屬句號
  或逗號）由 Claude 批次以華語語意判斷產生（隔離紀律同翻譯批次，
  工具呼叫計數稽核），存進條目檔 `sent_end`；塊為連續條目至句尾，
  絕不跨句。試點實測：80 個時間鏈塊 → 316 個語意句塊，最大塊
  48→8 條。
- **錨點 v2（放量前置）**：中文數字錨點以 CKIP 斷詞
  （ckiplab/ckiptagger）為前提抽取——「新聞一開始」的「一」非
  獨立數詞不作錨點；對位改就近判定（條目窗鄰域），不以全集任意
  位置充當命中。試點 v1（全域搜尋、無斷詞）之覆蓋率 90% 屬樂觀
  上界，已於報告註明。
- **配對恢復（單調 DP）**：對低分條目跑時間帶限（|Δt|≤10s）的
  對齊 DP，步含 1-1、1-2、2-1、2-2 合併與跳過（罰分）；分數用
  字元 bigram F1，數字錨點當硬約束。設定同 Bleualign（先機翻
  再表面相似度）；**不用語意向量**（使用者定案：風險大，改寫
  誤配與門檻不透明）。時間連通塊靠「語音沒停頓」綁整句；講者
  句中換氣使塊斷開時，2-2 合併格是第二道保險（VSO↔SVO 交錯
  的反對角高分即由此收攏）。輸出 `matched_entries`。殘餘曖昧
  配對留給校準步驟的人工／Claude 抽驗，不另引模型。
- **歸類初始門檻**（標 `calibrated: false`）：內容分數 <0.25 進
  候選；候選中平均 conf <0.7 → `asr-doubt`；最佳 δ 位移後分數
  恢復 ≥0.5 → `offset`；其餘 → `mismatch`；窗內無詞 →
  `no-speech`；非候選 → `ok`。門檻值在試點的人工校準
  （50＋50）後改定案並記 precision。

### D6：MT 語別碼（阿美方言）以樣本一致度選定

kaldi 族別 = `formosan_ami` 定案；MT 的 `src_lang` 在 5 個
`ami_*` 中未知。試點先抽 50 個有字幕的條目，5 個語別碼各跑
族語→華語，與字幕算內容分數，取中位數最高者定案並記入
`.align.json` meta 與報告。此法本身就是偵測機制的首次演練。

### D7：模組布局與環境

```
scripts/ocr/              影像側引擎（拆分自 subs2srt）
  cuelib.py               像素：mask、region、取樣、Segmenter、Cue
  band.py                 字幕帶位置偵測（原 detect.py 正名，
                          避免與 asrmt/detect.py 撞名）
  ocr.py                  tesseract 輸出清理
  sheets.py               contact sheet 產生
  transcripts.py          TSV 匯入與 verified（原 assemble 的 OCR 半邊）
  cli.py                  subs2srt CLI（cues／ocr／srt stage）
scripts/srtlib/           兩側共用（拆分自 subs2srt）
  srt.py                  srt_timestamp／render_srt／parse_srt
                          （原 cuelib 尾段）
  assemble.py             merge_repeats／apply_gap_rules／pad_edges
                          ＋「條目↔真實窗」對照鏈
scripts/asrmt/            語音側引擎 package（預設流程：到 raw）
  asr.py                  vosk 整集解碼 → 1-words/
  project.py              詞 → 條目投影 → 2-entries/
  bisrt.py                raw render → 3-srt-raw/（組裝鏈走 srtlib）
  align/                  延伸子系統（指名才跑；與 raw 線隔開）
    mtclient.py           ai-labs gradio client ＋ mt-cache 讀寫
    claude_mt.py          Claude 批次翻譯：出批次檔＋ingest → mt-cache
    dpalign.py            純 DP 核心（sim 注入；無 I/O、無 MT）
    detect.py             語意句塊、計分、δ、錨點、歸類、merge_groups
    render.py             審查版（4-srt-ai）與整併正式版（6-srt-complete）
scripts/news/             編排（族語新聞專屬）
  asrmt_run.py            單集步驟（預設 words→entries→raw）
  asrmt_batch.py          整批：逐集 抓檔→解碼→投影→raw→刪音檔
  numerals_ami.json       阿美數詞錨點表（放量後逐族加 numerals_<族>）
tests/                    全離線單元測試；照 CLAUDE.md TDD 先紅後綠
  README.md               spec×scenario×測試檔對照（4.1b 產出）
  ocr/                    ← 原 tests/cuelib＋tests/subs2srt 的 OCR 檔
    test_mask  test_region  test_segmenter  test_sheets
    test_import_tsv  test_ocr_prep  test_presets  test_auto_options
  srtlib/                 ← 兩側共用
    test_srt  test_merge_repeats  test_pad_edges
  asrmt/                  ← 語音側引擎（預設線）
    fixtures.py  test_project  test_bisrt
    align/                ← align 延伸（鏡射 scripts/asrmt/align/）
      test_mtclient  test_claude_mt  test_dpalign  test_render
      test_detect_blocks  test_detect_scores  test_detect_classify
  news/                   ← 編排（既有 15 檔＋新 2 檔）
    test_asrmt_run        單集編排 guard 與續跑（編排住 scripts/news）
    test_smkul_asr        smkul 語音側欄的 store 推導（0.3 TDD）
  e2e/                    ← 端對端：合成影片燒入已知 SRT 抽回比對
（asr.py 的 vosk 呼叫層無法離線單元測試，由 1.1 實模型煙霧測試
把關；「辨識文字忠實」由下游 project／bisrt 測試守恆——詞文字
不得被任何層改動。）
Kari-SRT/news/            資料正本（語料 → 技術 → 階段，見 D10）
  inventory.json          兩技術共用（自頂層移入）
  smkul.csv               兩技術共用進度表（語音側欄由 store 推導）
  1-ocr/                  影像側既有資料移入並照產生流程編號：
    README.md             1-cues／2-from_rtf／3-vision／
                          4-vision-rtf／5-report／6-srt（內容不動）
  2-asr/                  語音側（編號＝產出順序）
    README.md             流程圖＋各檔輸出入對應
    1-words/<srt_name>.json     2-entries/<srt_name>.json
    3-srt-raw/<srt_name>.srt    （對照版兩行，同正式版格式）
    4-srt-ai/<srt_name>.srt     （審查版六行＋偵測行，永不覆蓋）
    5-align/<srt_name>.{json,md}
    6-srt-complete/<srt_name>.srt （正式版兩行，gate 後）
    mt-cache/{ailabs,claude}.jsonl   跨集共用，非階段目錄
kithann/out/asrmt/<srt_name>/    暫存（gitignored、可重生）：
                          音檔、Claude 批次 in/out TSV
```

執行環境：`~/.venvs/asrmt`（vosk、huggingface_hub），比照
subs2srt venv 慣例；單元測試不依賴它（vosk import 只在 `asr.py`
的執行路徑）。Python 風格照 CLAUDE.md：`for` 在前，不用
comprehension。

### D10：Kari-SRT 存放改組——語料→技術→階段

使用者定案：資料全部分離、照技術分、不同狀態不同路徑不覆蓋。
分層是「語料（`news/`；《開會了》等另開頂層）→ 技術（`1-ocr/`
影像側、`2-asr/` 語音側）→ 編號階段（＝產生流程）」。既有資料純
`mv` 進 `news/1-ocr/` 並照當年產生順序編號（1-cues → 2-from_rtf
→ 3-vision → 4-vision-rtf → 5-report → 6-srt；新批次只動
1、3、6，其餘是二月批次歷史產物）；`inventory.json` 與
`smkul.csv` 升到 `news/`（語料層共用），smkul 增列語音側進度欄、
值僅由 store 檔案存在推導以保逐 byte 重建。內容逐 byte 不動、
只換路徑，主 repo 只改 `paths.py` 等路徑常數，遷移後
`rebuild --verify` 必須照樣全綠（tasks 0.x，最先做）。兩技術目錄
各有 README（0.4）。程式層同樣照使用者裁定拆分（0.5–0.6）：
`scripts/subs2srt` 拆成 `scripts/ocr`（純像素與 OCR 工作流）與
`scripts/srtlib`（兩側共用的 SRT 格式與組裝鏈）——cuelib.py 尾段
的 SRT 格式函式與 assemble.py 的組裝鏈屬共用、其餘屬 OCR，兩個
模組都要在模組內拆；tests 目錄鏡射新 package。審查版
`3-srt-raw/` 與正式版 `5-srt-complete/` 分檔——中間隔著
`4-align/`（偵測）與 gate，編號如實反映產出順序。檔案系統 `mv`
由 Claude 執行，git mv／commit 依 CLAUDE.md 由使用者執行。

### D9：外部依賴的採購合規稽核

依《採購安全說明書》v2.0（規則摘要已入 CLAUDE.md，因原文件在
gitignore 的 `kithann/`）。本 change 引進的每一項稽核結果：

| 項目 | 類型 | 結論 |
|---|---|---|
| `vosk` (alphacep/vosk-api) | 開源套件 | ✅ Apache-2.0、15k star、近期 commit 在三個月內、近期 Reviewer 非中國 |
| `huggingface_hub` | 開源套件 | ✅ Apache-2.0、活躍、HF Inc.（美國） |
| `ILRDF/kaldi_formosan_250514_*` | 模型權重 | ✅ 原語會自有，臺灣 |
| ai-labs MT 服務 | 雲端服務 | ✅ 原語會自有服務，臺灣 |
| Claude（Anthropic） | 雲端服務 | ✅ 美國；本專案視覺辨識已長期使用 |
| **vosk 中文模型** | 模型權重 | ❌ **不採用**——`multi-cn` recipe 與 SpeechIO／THCHS／aishell 等訓練語料屬中國出身，觸及採購原則 1 |
| Bleualign | 開源（GPL-2.0） | 只讀作演算法對照，**不引入**、不成為依賴（授權亦不相容） |
| `ckiptagger`（ckiplab） | 開源套件 | ✅ 中研院 CKIP Lab（臺灣）維護，v0.3.0（GPL-3.0-only，執行期依賴不散布、內部使用無虞）＋tensorflow-cpu（Apache-2.0）；模型資料自 CKIP 官方通道下載，已裝並實測 |

因此「用華語 ASR 幫忙定錨」改以 D5 的**借詞音節錨點**達成：不裝
任何中文語音模型，用既有族語 ASR 軌自己的輸出即可。若日後仍需
真正的華語辨識軌，合規替代是 Whisper（OpenAI，美國）而非 vosk-cn，
但受本機 RAM 限制，列 Open Question。

### D8：與 refine-cue-timing 的關係

其資料面已換版（見 Context），試點直接受益：偵測的 δ 解析度以
0.05s 邊界為底。若日後 cue 再換版，ASR 不必重跑——重投影＋組裝＋
偵測即可（`1-words` 不變、MT 快取內容定址大多命中）。兩個 change
都會動 `scripts/news/`，apply 時以當下 repo 狀態為準（有平行
session，動手前重驗）。

## Risks / Trade-offs

- [mp3 與 cue 軸不同源（2 月 mp3 在 7 月資料夾）] → D2 的時長
  前驗＋偏移曲線後驗；不合退 mxf 抽音。
- [ASR 對播報新聞（背景音樂、受訪者講華語段落）品質未知] → 這
  正是試點 gate 的目的；華語段落預期以低 conf 現形、落在
  `asr-doubt`，報告呈現分布而非只給平均。
- [MT 品質差會把「翻不好」誤標成「對不起來」] → 雙向比對＋conf
  歸因矩陣分開三種成因；門檻經人工 50＋50 校準才宣稱有效；報告
  誠實列 precision。
- [RAM 只剩 ~3GB] → 一次一顆模型、解碼流式不整檔載入；若 OOM，
  錯開平行 session 時段再跑（試點只有一集，時間好挪）。
- [公開 MT 服務負載] → 單併發＋固定間隔＋快取；試點量 ~1,100 條
  ×2 方向，約 1–2 小時。
- [gradio 協定變動（服務升版）] → client 集中在 `mtclient.py`
  一處；失敗訊息帶原始回應利於診斷。

## Migration Plan

新增性質，無遷移。回退 = 刪 `Kari-SRT/asr/` 未 commit 內容與新
模組；不影響既有交付物。git add/commit 依 CLAUDE.md 由使用者執行。

## Open Questions

- 放量 35 集時，偵測第二方向（zho→族語）是否只對低分塊做以省
  一半請求——試點看命中率再定。
- Formosan-AI `asr-kaldi` 是否加回傳 words 的 API（服務端小改＋
  人工部署）——若做，遠端也能走乙′，但本機路線已閉環，不急。
- 非阿美各族的數詞與借詞專名錨點表——放量前逐族補，或降級為
  只用阿拉伯數字借音。
- 借詞專名錨點的覆蓋率——試點量測「字幕專名有多少比例在 ASR
  詞流找得到音近詞」，太低就只留數字錨點。
- 若真的需要獨立華語辨識軌（借詞錨點覆蓋不足時），合規選項是
  Whisper（OpenAI，美國）而非 vosk-cn；但本機 RAM ~3GB，要先
  確認 small/base 級別夠不夠，且須另跑一次 D9 稽核。
- 放量時 MT 吞吐——把多句串進單次 `/translate` 不可行（NLLB
  位置上限 1024 token、換行被 SentencePiece 正規化吃掉致輸出拆
  不回去、`no_repeat_ngram_size=4` 會跨句誤殺重複片語）；真正的
  加速是服務端加批次 endpoint（tokenizer 批次＋一次 generate、
  1:1 回傳；需人工部署）或本機 ctranslate2 int8 推論。試點量
  （~1.1k×2 句）單句呼叫即可，放量前再定。
