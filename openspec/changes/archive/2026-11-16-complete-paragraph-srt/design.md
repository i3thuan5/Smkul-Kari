# Design

## Context

動機見 proposal.md。現況：

- `scripts/news/pairs_run.py` 用 `FIRST_MONTH`／`LAST_MONTH`（2021-01～10）限定範圍；`in_scope()` 另被 place_cue、offband_backfill、rebroadcast_port 拿來決定改了 OCR SRT 之後要不要重產平行語料。
- `scripts/mt/calibration.py` 的基準表一族一列（族語別、開場組數、辭典命中率中位數），`rate_of(table, tribe, episode)` 只看族語別；`--recalibrate` 整張重算覆寫。
- 辭典來自 `scripts/news/lexicon_fetch.py`：16 族官方 xlsx，每族只收一個語言別（魯凱＝霧台）。
- `scripts/lexicon/klokah.py` 已能從 E樂園 教材抽出 42 個語言別的詞表（`vocabularies()`、`variety_of()`），目前只有《開會了》清洗用；E樂園 路徑常數在 `scripts/aiyalaeho/cleaning/paths.py`。全部現抽約 3.7 秒。
- `scripts/news/whisper_run.code_for()` 已優先送目錄那列的非保底語言別代號（10-23 起）；前例：Muni Kadrangian 131 集改北排灣後重跑，辨識紀錄與目錄一致。
- `scripts/news/relabel.py` 只能換族語別（會改成果檔名、搬檔、填該族保底語言別）。
- `scripts/asrmt/sapolita.py` 的族別選單值是 9-18 抄的「魯凱語 (Rukai)」形式；伺服器 9-24 之後改成只有中文名，送出被拒。伺服器模型也換過：20210618_169 九月存的結果與 11-16 重送的族語詞相似度 0.515，但兩次萬山詞表命中率相同（0.226 對 0.223）；同一天霧台、萬山兩個代號互比相似度 0.925。
- 試算（2026-11-16，3153 集只算不寫）：330 秒、0 集出錯；Lavoras 42 集保留率 14.6%，改用萬山詞表與萬山基準（0.357，215 組開場）後 36.0%。

## Goals / Non-Goals

**Goals:**

- 3153 集全部有平行語料與段落字幕，`rebuild --verify` 全數通過。
- 舊範圍 657 集裡，非萬山的集逐 byte 不變（校正基準凍結、霧台的集辭典不變）。
- 萬山的集用對的辭典分層，基準只拿萬山的開場算。

**Non-Goals:**

- 不把 E樂園 補充推廣到其他官方辭典沒收的語言別（阿美、排灣其他語言別等）——使用者裁定只做萬山；機制留成一張表，日後加一個代號即可。
- 不重跑其他 3111 集的 whisper（伺服器換模型不構成重跑理由；只有語言別改了的集才重跑）。
- 不重算 16 族既有的校正基準。
- 抽查結果不回頭改分層門檻；只作為交件可信度的數字。

## Decisions

### 範圍：拿掉月份，`in_scope` 改名 `ready`

`ready(name)` ＝ OCR SRT 與 sapolita SRT 兩邊都在。三個呼叫端只換函式名。另一個做法是保留月份常數、改成 2024-12，但下一批（2025）又要改，使用者裁定拿掉。

### 校正基準：表加「語言別代號」欄，只補缺的列

- 欄位：族語別、語言別代號、開場組數、辭典命中率中位數。既有 16 列的語言別代號填族語別代號（`dru`、`ami`…），數值原樣搬過去——這是一次性的格式遷移，數值不重算。
- 分組鍵：一般集數歸（族語別, 族語別代號）；補充語言別的集歸（族語別, 該語言別代號）。所以萬山的集不再參與魯凱那列的計算（那列凍結，不受影響）。
- 查表：先找（族語別, 本集語言別代號），沒有就找（族語別, 族語別代號），再沒有就指名中止。`dru-x-ngdr` 的集落到 `dru` 那列，跟現在一樣。
- `--recalibrate` → `calibration.fill_missing(old, new)`：舊表有的列原樣、只加缺的列。全量重算＝刪表再 `--recalibrate`。替代方案 `--recalibrate-all` 未採用：多一個選項，且刪表本身更明白表示「舊集數的分層都會變」。
- 舊格式的表（沒有語言別代號欄）讀取時指名拒絕，不自動遷移——遷移在 apply 時做一次、進 Kari-SRT diff。

### 萬山辭典：官方魯凱辭典 ∪ E樂園 萬山詞表，現抽不存檔

- `lexicon_fetch.SUPPLEMENTS = {"dru-x-opnh"}`；`lexicon_fetch.supplements(codes)` 用 `klokah.vocabularies()` 抽，以 `klokah.variety_of()` 把語別全名對成代號，回傳 {代號: 詞集}。E樂園-解壓 或方言編號表不在就指名中止。
- pairs_run 對每集：語言別代號在 SUPPLEMENTS 的，傳給 features 的本族辭典與 16 族辭典 dict 裡那一族都換成聯集；其他集原樣。只有範圍內有補充語言別的集時才呼叫 `supplements()`。
- 聯集而非替換：試算整個換成萬山會讓同集講霧台的受訪者掉下去。
- 不蒸餾成快取：現抽 3.7 秒，pairs_run／rebuild 一輪只抽一次；快取會有和原檔不同步的問題。E樂園 路徑常數搬到共用的 `scripts/datadirs.py`，`aiyalaeho/cleaning/paths.py` 改為從那裡取（名字不變）。
- 使用者裁定放 kithann、找不到就中止（不放 Kari-SRT）。E樂園 沒有 SFTP 來源，換機器要先搬 `kithann/E樂園/` 壓縮檔再解開；寫進 `2-csv-analysis/README.md`。

### relabel 只換語言別

CLI：`python3 -m scripts.news.relabel <成果檔名> <族語別(中)> --variety <語言別> --reason "…"`。族語別參數等於目前的族語別且帶 `--variety` 時走這條：改目錄 `語言別`、`語言別代號`（`languages.code_for(族, 語言別)`，查不到就拒絕）、`備註` 接上依據；刪 whisper SRT、辨識紀錄那一列、2-csv-analysis、3-srt-paragraph；不搬 1-ocr、不動影片、不刪 kaldi（族語別模型）。語言別跟現在相同就拒絕。替代方案「手改 smkul.csv 再手刪檔」未採用：北排灣那次就是這樣做的，沒有測試把關。

### sapolita 選單值

照 11-16 伺服器錯誤訊息回的選單抄（只有中文族名），16 族一次改。不做「去掉括號」的自動轉換：選單值必須與伺服器一字不差，用表比推導穩。

### 抽查與交件

- `--spot-sample <月>… --batch <名> [--per-tribe N]`：寫到 `雙語字幕-抽查/<名>/`；資料夾已有 `request-01-*.tsv` 就拒絕。每族 N 組：依族排序後各自用同一種子抽，某族不足 N 組就全收並回報。`--spot-report --batch <名>`。
- 種子沿用 `SPOT_SEED`；抽樣仍只抽高信心、仍排除超過 1,800 字元的列。
- export 寫完複製後，重新掃描交件資料夾 `2-平行語料/` 全部 CSV 產清單，依成果檔名排序。

## 檔案樹（產出者與輸入）

```
Kari-SRT/news/
├── smkul.csv                       relabel --variety 改 42 列（輸入：本 change 的網頁證據）
├── 主播.csv                        人維護（已改）
└── 2-asr-whisper/
    ├── README.md                   人寫
    ├── 1-srt-sapolita/<月>/*.srt   whisper_run（輸入：影片音軌、目錄語言別代號、sapolita）
    │   └── 辨識紀錄.csv            whisper_run
    ├── 2-csv-analysis/
    │   ├── README.md               人寫
    │   ├── 校正基準.csv            pairs_run --recalibrate（輸入：範圍內開場組；只補缺列）
    │   └── <月>/<成果檔名>.csv     pairs_run（輸入：1-srt-sapolita、辨識紀錄音長、1-ocr/1-cues、
    │                                1-ocr/2-vision、smkul.csv、校正基準.csv、kithann/族語辭典、
    │                                萬山集另加 kithann/E樂園-解壓）
    └── 3-srt-paragraph/<月>/*.srt  pairs_run 同一輪（輸入：同集 CSV 的列）
kithann/
├── 族語辭典/                       lexicon_fetch（SFTP）
├── E樂園/、E樂園-解壓/             人放（解壓後由 klokah 讀）
└── out/news/
    ├── 雙語字幕/{1-雙語字幕,2-平行語料}/<月>/、3-雙語字幕清單.csv、README.md
    │                               paragraph_export --export（輸入：Kari-SRT 兩層、smkul.csv）；README 人寫
    └── 雙語字幕-抽查/<批次>/sample.csv、request-01-{a..d}.tsv
                                    paragraph_export --spot-sample；reply-01.tsv 由 Opus 讀者寫
scripts/  datadirs.py、aiyalaeho/cleaning/paths.py、asrmt/sapolita.py、mt/calibration.py、mt/tier.py、
          news/{lexicon_fetch,pairs_run,rebuild,relabel,paragraph_export,place_cue,offband_backfill,rebroadcast_port}.py
tests/    asrmt/test_sapolita.py、mt/{test_run,test_calibration,test_lexicon,test_paragraph_export}.py、
          news/{test_relabel,test_rebuild_pairs,test_place_cue,test_offband_backfill,test_rebroadcast_port}.py、
          mt/README.md、news/README.md
```

## spec × scenario × 測試檔

| spec | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| whisper-asr-srt | ★ 伺服器 9-24 後選單只剩中文名，送「魯凱語 (Rukai)」回「not in the list of choices」；16 族選單值都不帶括號英文名；賽德克、太魯閣仍是兩個族別 | `tests/asrmt/test_sapolita.py` |
| whisper-parallel-corpus | 2024-12 兩側都有要做（原本寫死 2021-10，2496 集被擋）；只有一側列出不算錯；★ place_cue／offband_backfill／rebroadcast_port 改 2023 年某集 OCR SRT 也要重產 | `tests/mt/test_run.py` |
| whisper-parallel-corpus | ★ Lavoras 講萬山、官方辭典只收霧台，開場命中率 0.048、85% 不採用：`dru-x-opnh` 的集本族辭典用聯集；★ 不可整個換成萬山（同集霧台受訪者會掉）；霧台的集逐 byte 不變 | `tests/mt/test_run.py` |
| whisper-parallel-corpus | ★ E樂園 不在又有萬山的集要指名中止，不可退回官方辭典靜靜產出另一種分層；沒有萬山的集不讀 E樂園 | `tests/mt/test_run.py`、`tests/mt/test_lexicon.py` |
| whisper-parallel-corpus | `dru-x-opnh` 有自己那列（0.357）就用；`dru-x-ngdr`、`ami-x-pswl` 照舊用族語別那列、不可因查不到語言別中止；★ 族語別那列也沒有照舊指名中止、不退回 0.5 | `tests/mt/test_calibration.py` |
| whisper-parallel-corpus | ★ --recalibrate 只補缺的列，原 16 列逐 byte 不變（全量重算魯凱 0.27→0.44，657 集分層全變）；寫回讀回逐 byte 相同；舊格式（無語言別代號欄）指名拒絕 | `tests/mt/test_calibration.py`、`tests/mt/test_run.py` |
| srt-data-store | rebuild：有萬山的集、E樂園 不在要指名中止、不宣告通過；沒有萬山的集不需要 E樂園 | `tests/news/test_rebuild_pairs.py` |
| srt-data-store | 只換語言別（霧台→萬山）：成果檔名不變、1-ocr 不搬；目錄兩欄改掉、備註附依據且保留原備註 | `tests/news/test_relabel.py` |
| srt-data-store | ★ 用霧台做出來的 whisper SRT、辨識紀錄那列、2-csv-analysis、3-srt-paragraph 要刪，不可留著冒充萬山；kaldi 不刪 | `tests/news/test_relabel.py` |
| srt-data-store | 魯凱下面沒有「北排灣」要拒絕；跟現在相同要拒絕、不白刪 whisper；舊批（語言別空白、代號 `dru`）也能改 | `tests/news/test_relabel.py` |
| （交件工具） | ★ 第二批抽查會蓋掉 2021-01～02 那批 request-01／reply-01：寫到批次資料夾、已有 request 就拒絕；每族 3 組 × 16 族＝48、同種子同一批；不足 3 組全收並回報；只抽高信心 | `tests/mt/test_paragraph_export.py` |
| （交件工具） | ★ 清單每 export 一次被覆寫成只剩這次的月份：要列交件資料夾全部的集；同月再 export 是取代不是重複；依成果檔名排序 | `tests/mt/test_paragraph_export.py` |

## Risks / Trade-offs

- [42 集重跑用的是新版模型，跟其他 3111 集不同版] → 辨識紀錄的辨識日期看得出來；whisper README 記改版時間與相似度數字。萬山詞表命中率顯示品質沒變。
- [範圍拿掉後，place_cue 等三支每次都載入 16 族辭典（萬山的集再加 3.7 秒）] → 可接受；這三支本來就是一集一集手動跑。
- [E樂園 只在 kithann，換機器沒有就重建不了萬山那幾集] → 使用者已知並裁定；README 寫明要搬 `kithann/E樂園/` 再解壓，中止訊息指名位置。
- [聯集讓萬山集的命中率上升，也可能讓「別族語言」判定變化] → 別族判定比的是 16 族，萬山集的魯凱那族換成聯集只會讓本族更像本族；抽查涵蓋萬山集時順便看。
- [sapolita 伺服器可能再改版] → 錯誤訊息會列出伺服器的選單，修法同這次；不做自動推導。
- [rebuild --verify 多 5～6 分鐘] → 可接受。

## Migration Plan

1. 程式（TDD）全部改完、單元測試綠。
2. 遷移 `校正基準.csv` 格式（加欄、數值不動），`rebuild --verify` 確認 657 集仍逐 byte 相同。
3. relabel 42 集 → whisper_run 重跑那 42 集（背景，`&&` 串）。
4. `pairs_run --recalibrate`（只補萬山一列）→ `pairs_run` 整批。
5. 驗收：rebuild --verify、unittest、flake8、name_catalogue --check。
6. 抽查 5 批、export、README。

回退：Kari-SRT 是 git submodule，未 commit 前 `git restore` 該目錄即可回到原狀（由使用者執行）。
