## Why

族語新聞的 sapolita 族語辨識（`2-asr-whisper/1-srt-sapolita/`）與華語燒印字幕（`1-ocr/3-srt/`）要配成族華平行語料，交給原語會 ai-labs 訓練雙向機器翻譯。whisper 那層的 README 寫著「配平行語料是下一層的事，還沒有目錄」，這個 change 就是那一層。

explore 階段（kithann/mt.md）量過：

- 語音那側約一半是幻覺、華語音譯或別族講者。
- 對齊本身在辨識得出來的段落裡九成正確。
- 16 族辭典命中率是最能分出好壞的特徵（對 Claude 裁判的 AUC 0.886～0.907）。

方法已經定了，現在要把實驗程式變成可以重跑、可以驗證的正式管線。

## What Changes

- **對齊**：每條華語字幕歸給時間重疊最多的那段語音。一條字幕在兩段各佔一定比例以上時，把兩段併成一組；這個比例叫合併門檻，暫定 30%。
- **分層**：每組分成高信心、中信心、不採用三層；不採用的組寫明原因（幻覺、別族語言、詞數不足、命中率不足）。
  - 辭典命中率的門檻按族校正，基準是各族主播開場的中位數。這個基準算一次、存成凍結的表。
  - 另外用幻覺旗標、別族判定、chrF、詞數一起判斷。
- **新增資料層** `Kari-SRT/news/2-asr-whisper/2-平行語料/`：
  - `<年-月>/<成果檔名>.csv`：一集一檔、一組一列，不採用的組也收。
  - `校正基準.csv`、`README.md`。
  - 範圍先做 2021-01～10、兩側都有的集數。
  - 一集配不出任何一組時，寫一個只有表頭的檔。
- **辭典**：官方族語辭典的 xlsx 與蒸餾後的詞庫放在 `kithann/族語辭典/`。沒有就從 SFTP 抓；使用者保證 SFTP 一定有辭典。
- **離線重建**：`scripts.news.rebuild --verify` 納入這一層，逐 byte 重產比對。包含規則加上：這一層有的集數，`3-srt/` 與 `1-srt-sapolita/` 都要有。
- **調參**：用 Claude 裁判調合併門檻。
  - 要比的值：不合併、10%、20%、30%、40%、50%。
  - 依「字幕在兩段中較少那邊佔多少」分成五格，每格抽 97 處，達 95% 信心、誤差 ±10 點；分不出勝負時取較低的門檻（多合併）。
  - 每處做合併、拆開兩個版本，交 Opus subagent 判，一批 200 組。
  - 另外在《開會了》標準答案上先免費掃一輪當參考。
  - 裁判只用在調參；正式產出不叫模型。
- **搬移**：官方辭典的三支模組 `dictionary.py`、`vocab.py`、`script.py` 從 `scripts/aiyalaeho/langcheck/` 搬到頂層 `scripts/lexicon/`，內容不改。原因是新聞也要用；不搬的話，新聞會依賴到開會了。開會了的產出逐 byte 不變。
- **刪除**：`scripts/mt/glosses.py`，以及 `overlap.py` 的「有重疊就併」「用譯文重派」兩個對齊法。實驗已證明比較差或用不到，結論記在 design。
- **量測工具**：開會了送 sapolita 辨識、在開會了標準答案上掃門檻，這兩支放 `tools/mtgold/`，不在交付流程上。

## Capabilities

### New Capabilities

- `whisper-parallel-corpus`：sapolita 段落與華語字幕的段落級對齊、三層分層與不採用原因、校正基準、辭典的取得、一集一檔 CSV 的格式、範圍與跳過規則、合併門檻的調參方法。

### Modified Capabilities

- `srt-data-store`：兩處要改。
  - 離線重建要涵蓋 `2-平行語料/`，並寫明這一層缺辭典時可以從 SFTP 取得（是例外，不算違反「不存取外部」）。
  - 階段包含規則加上這一層。

## Impact

檔案與資料夾（★新增、改、✖刪、⇐搬移）：

```
Kari-SRT/news/2-asr-whisper/
├── README.md                              改
└── ★2-平行語料/{README.md, 校正基準.csv, <年-月>/<成果檔名>.csv}
kithann/族語辭典/                            ★（gitignore）
kithann/out/mt/調參/                         ★（gitignore）
scripts/
├── ★lexicon/{__init__, ⇐dictionary, ⇐vocab, ⇐script}.py
├── aiyalaeho/langcheck/{mark, report}.py  改（import）
├── aiyalaeho/langcheck/{dictionary, vocab, script}.py   ✖（搬走）
├── mt/{load, textsim, features, goldalign, evaluate}.py   留
├── mt/overlap.py、hallucination.py         改
├── mt/glosses.py                          ✖
├── mt/★{calibration, tier, pairs, tuning}.py
├── mt/README.md                           改
├── news/paths.py、rebuild.py               改
├── news/★{lexicon_fetch, pairs_run, pairs_tune}.py
└── README.md                              改
tools/★mtgold/{__init__, sapolita_aiyalaeho, sweep}.py
tests/
├── ★lexicon/{__init__, fixtures, ⇐test_dictionary, ⇐test_script, ⇐test_vocab}.py
├── aiyalaeho/langcheck/{test_mark, test_report, fixtures}.py   改
├── mt/test_overlap.py                     改；test_glosses.py ✖
├── mt/★{test_lexicon, test_calibration, test_tier, test_pairs, test_run, test_tuning}.py
├── mt/README.md、tests/README.md           改
├── news/★test_rebuild_pairs.py
└── tools/★mtgold/test_sweep.py
```

- 不新增 Python 套件，不引進新的外部服務。辭典來自原語會的 SFTP（開會了已用過）；裁判是 Claude，已通過採購稽核。
- 調參的裁判用 Opus subagent，算在 Claude Max 20x 的額度裡；估計要用掉數個五小時的額度窗。
- 開會了只動 import 路徑，`scripts.aiyalaeho.rebuild --verify` 要仍然逐 byte 通過。
