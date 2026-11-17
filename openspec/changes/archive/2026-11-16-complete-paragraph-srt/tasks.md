# Tasks

## 1. sapolita 族別選單值

- [x] 1.1 先改 `tests/asrmt/test_sapolita.py`：選單值改成只有中文族名、不得出現「 (」，賽德克／太魯閣仍分開（紅）；驗證：`unittest tests.asrmt.test_sapolita` 失敗
- [x] 1.2 改 `scripts/asrmt/sapolita.py` 16 族選單值（照 2026-11-16 伺服器回的選單），更新註解出處；驗證：1.1 的測試綠

## 2. E樂園 路徑與萬山詞表

- [x] 2.1 `scripts/datadirs.py` 新增 `KLOKAH_SOURCE`、`KLOKAH_NAMES`，`scripts/aiyalaeho/cleaning/paths.py` 改從 datadirs 取（名字不變）；驗證：`unittest discover -s tests/aiyalaeho` 全綠
- [x] 2.2 先在 `tests/mt/test_lexicon.py` 加：`supplements({"dru-x-opnh"})` 從 fixture 的 E樂園 抽出萬山詞集；E樂園-解壓或方言編號表不在要指名中止；空集合不讀 E樂園（紅）
- [x] 2.3 `scripts/news/lexicon_fetch.py` 加 `SUPPLEMENTS`、`supplements()`（重用 `klokah.vocabularies`／`variety_of`）；驗證：2.2 綠

## 3. 校正基準按語言別代號

- [x] 3.1 先改 `tests/mt/test_calibration.py`：表多語言別代號欄、寫回讀回逐 byte；`rate_of` 先找語言別那列、再找族語別那列、都沒有指名中止；`fill_missing` 舊列逐 byte 保留只加缺列；舊格式表指名拒絕；baseline 依（族語別, 分組代號）分組（紅）
- [x] 3.2 改 `scripts/mt/calibration.py`（`baseline`、`write`、`read`、`rate_of`、新增 `fill_missing`）；驗證：3.1 綠

## 4. pairs_run 拿掉範圍、萬山聯集、只補缺列

- [x] 4.1 先改 `tests/mt/test_run.py`：「2021-11 兩側都有也不做」改為 2024-12 要做；`in_scope`→`ready`；`dru-x-opnh` 的集本族辭典是聯集（萬山詞、霧台詞都命中）；霧台的集不讀 E樂園、輸出不變；有萬山的集而 E樂園 不在要指名中止；`--recalibrate` 只補缺列、16 列逐 byte 不變（紅）
- [x] 4.2 改 `scripts/news/pairs_run.py`：刪 `FIRST_MONTH`／`LAST_MONTH`、`in_scope` 改名 `ready`、每集挑辭典（補充語言別用聯集）、萬山集按（族語別, 語言別代號）分組算基準、`--recalibrate` 走 `fill_missing`；更新 docstring；驗證：4.1 綠
- [x] 4.3 `scripts/news/place_cue.py`、`offband_backfill.py`、`rebroadcast_port.py` 改呼叫 `ready`，對應測試的 mock 改名；`scripts/mt/tier.py` 註解拿掉「2021-01～10」；驗證：`unittest tests.news.test_place_cue tests.news.test_offband_backfill tests.news.test_rebroadcast_port tests.mt.test_tier` 綠
- [x] 4.4 `tests/mt/README.md` 的 run、calibration、lexicon 列照 design 對照表更新；驗證：人讀過、無「2021-11 也不做」舊字樣（`grep -n "2021-11 兩側" tests/mt/README.md` 無輸出）

## 5. rebuild 帶上萬山辭典

- [x] 5.1 先在 `tests/news/test_rebuild_pairs.py` 加：入庫有 `dru-x-opnh` 集而 E樂園 不在要指名中止、不宣告通過；沒有萬山集時不需要 E樂園（紅）
- [x] 5.2 改 `scripts/news/rebuild.py` 的 `pairs_problems`：透過 pairs_run 取得與產出相同的辭典（含補充）；驗證：5.1 綠，`unittest tests.news.test_rebuild_pairs` 全綠
- [x] 5.3 `tests/news/README.md` rebuild 那列補 E樂園 情形

## 6. relabel 只換語言別

- [x] 6.1 先在 `tests/news/test_relabel.py` 加：`--variety` 只換語言別時成果檔名不變、1-ocr 不搬、目錄兩欄改掉、備註附依據且保留原備註；刪 whisper SRT、辨識紀錄那列、2-csv-analysis、3-srt-paragraph，kaldi 不刪；不屬該族的語言別拒絕；相同語言別拒絕；舊批（語言別空白、`dru`）可改（紅）
- [x] 6.2 改 `scripts/news/relabel.py`（`--variety` 路徑、更新 docstring）；驗證：6.1 綠
- [x] 6.3 `tests/news/README.md` 〈語別改正〉補只換語言別的列

## 7. 抽查分批與交件清單

- [x] 7.1 先在 `tests/mt/test_paragraph_export.py` 加：`--batch` 寫到批次資料夾、已有 request 拒絕；`--per-tribe 3` 每族 3 組、同種子同一批、不足全收並回報；`--spot-report --batch`；export 清單列出交件資料夾全部的集、同月重 export 不重複、依成果檔名排序（紅）
- [x] 7.2 改 `scripts/news/paragraph_export.py`；驗證：7.1 綠
- [x] 7.3 `tests/mt/README.md` paragraph_export 列更新

## 8. 程式驗收（資料還沒動）

- [x] 8.1 `scripts/README.md` 更新 pairs_run、relabel、paragraph_export、lexicon_fetch、datadirs 那幾列；驗證：`unittest tests.news.test_readme_covers_scripts` 綠
- [x] 8.2 清 `__pycache__` 後跑 `tox -e flake8`、`tox -e unittest`；驗證：0 錯、全綠

## 9. 資料：校正基準格式遷移與萬山改正

- [x] 9.1 遷移 `Kari-SRT/news/2-asr-whisper/2-csv-analysis/校正基準.csv`：加語言別代號欄（填族語別代號），16 列數值原樣；驗證：`rebuild --verify` 通過，657 集逐 byte 相同
- [x] 9.2 用 `relabel <名> 魯凱 --variety 萬山 --reason "…"` 改 Lavoras 42 集（清單取自辨識紀錄主播名 Lavoras Tavelengae），依據寫 Medium 網址、截圖位置、E樂園 比對數字；驗證：smkul.csv 42 列為 `dru-x-opnh`、`name_catalogue --check` 通過、那 42 集的 whisper SRT 與辨識紀錄列已刪
- [x] 9.3 背景跑 `whisper_run`（無名字，自動挑出那 42 集），`&&` 串 `pairs_run --recalibrate`（只補萬山列）`&&` `pairs_run` 整批；驗證：辨識紀錄 42 列代號 `dru-x-opnh`、校正基準 17 列且原 16 列不變、2-csv-analysis／3-srt-paragraph 各 3153 集
- [x] 9.4 文件：`2-asr-whisper/README.md`（語別碼、sapolita 改版與相似度數字）、`2-csv-analysis/README.md`（範圍、萬山聯集、校正基準欄與補算語意、E樂園 換機器要搬）、`scripts/news/README.md` 若有範圍字樣一併改；驗證：`grep -rn "2021-01～10" Kari-SRT/news/2-asr-whisper/*/README.md` 只剩歷史量測的描述
- [x] 9.5 驗收：`rebuild --verify`（集數＝inventory 非 pending 筆數）、`tox -e unittest`、`tox -e flake8`、`name_catalogue --check`；驗證：全部通過

## 10. 抽查與交件

- [x] 10.1 `--spot-sample` 五批：`2021-11～2022-12`、`2023`、`2024-01～07`（各高信心隨機 48）、`看見族語-隨機`（2024-08～12 隨機 48）、`看見族語-每族3組`（`--per-tribe 3`）；驗證：五個資料夾各有 sample.csv 與 request-01-{a..d}.tsv
- [x] 10.2 每批派 Opus 讀者照 `scripts/mt/judge_prompt_paragraph.md` 判、寫 reply-01.tsv，`--spot-report --batch` 統計；驗證：五批 report 都通過編號核對，高／中／低數字寫進 2-csv-analysis/README〈可信度〉
- [x] 10.3 `paragraph_export --export 2021-03 … 2024-12`；驗證：交件資料夾 1-雙語字幕、2-平行語料 各 3153 集，清單 3153 列（實做：第一批交付後才補收的 20210116_016_晚間 排灣在 2021-01，export 照月份會蓋掉第一批，所以這一集單獨複製、再重寫清單）
- [x] 10.4 修 `kithann/out/news/雙語字幕/README.md`：集數範圍、時間含前後 0.5 秒留白、萬山分層、抽查數字；驗證：README 不再把「不含留白」寫成全部集數的性質（實做：第一批 2021-01～02 的 133 集原樣保留、CSV 時間確實不含留白，README 分兩批寫清楚）

## Workflow follow-up

- `/opsx:archive`；spec 有差異就 sync 到 `openspec/specs/`。
- 回覆檔寫到 `kithann/tuiue/<MMDD>/`。
