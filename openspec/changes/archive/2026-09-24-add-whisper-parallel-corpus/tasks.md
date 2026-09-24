## 1. 辭典搬到頂層 scripts/lexicon/

- [x] 1.1 搬 `tests/aiyalaeho/langcheck/test_dictionary.py`、`test_script.py`、`test_vocab.py` 到 `tests/lexicon/`；fixtures 裡跟辭典有關的部分一起搬；import 改成 `scripts.lexicon`，先跑紅
- [x] 1.2 搬 `scripts/aiyalaeho/langcheck/{dictionary,vocab,script}.py` 到 `scripts/lexicon/`，內容不改；改 `mark.py`、`report.py`、`scripts/mt/hallucination.py` 的 import，跑綠
- [x] 1.3 `tests/lexicon/README.md` 放對照表那幾列、`tests/aiyalaeho/langcheck/README.md` 拿掉搬走的列、`tests/README.md` 總表加一行；`scripts/README.md` 補 `lexicon/` 一節
- [x] 1.4 驗收：`scripts.aiyalaeho.rebuild --verify` 逐 byte 通過、unittest 全綠、flake8 0

## 2. 整理既有 scripts/mt/

- [x] 2.1 刪 `test_glosses.py` 與 `test_overlap.py` 裡「有重疊就併」「用譯文重派」兩組；刪 `glosses.py`、`overlap.transitive_groups`、`overlap.rescored_groups`
- [x] 2.2 `test_overlap.py` 補「字幕剛好等於合併門檻算合併」的測試（先紅），`max_overlap_groups` 改用 ≥（綠）
- [x] 2.3 `scripts/mt/README.md`、`tests/mt/README.md` 更新；原 README 的做法比較結論移到 design 已記的那段，不留重複

## 3. 辭典取得（news/lexicon_fetch.py）

- [x] 3.1 寫 `tests/mt/test_lexicon.py`（SFTP 用假的）：缺檔去抓、位元組數比對、不完整刪檔中止、已有且相符不重抓、族名從「_10邵語」那段讀而不依賴日期、只有 15 族指名中止、原檔比詞庫新就重蒸餾（紅）
- [x] 3.2 `scripts/news/paths.py` 加 `LEXICON_KITHANN`（`kithann/族語辭典/`）等常數；實作 `scripts/news/lexicon_fetch.py`（綠）
- [x] 3.3 實機跑一次：從 SFTP 抓 16 族到 `kithann/族語辭典/`，蒸餾出詞庫

## 4. 分層與校正基準（mt/calibration.py、mt/tier.py）

- [x] 4.1 寫 `tests/mt/test_calibration.py`：前 90 秒、≥5 詞的中位數；按族分開；讀寫表；查無族語別指名中止、不退回預設值（紅）
- [x] 4.2 實作 `scripts/mt/calibration.py`（綠）
- [x] 4.3 寫 `tests/mt/test_tier.py`：碎片「harung uri」→ 詞數不足；別族差 40 點以上且 ≥5 詞 → 別族語言（本族也過門檻時照樣）；「ʼa ʼa ʼa…」與譯文數字串 → 幻覺；chrF 0.01 最多中信心；門檻用 ≥；原因優先序固定（紅）
- [x] 4.4 實作 `scripts/mt/tier.py`，門檻常數（含合併門檻 30%）只在這裡（綠）

## 5. 一集一檔 CSV（mt/pairs.py）

- [x] 5.1 寫 `tests/mt/test_pairs.py`：14 欄的先後；SRT 時間戳；含逗號的欄位讀回來不變；族語撇號 ʼ 原樣；多段、多條用一個空格接；辭典命中率與 chrF 固定三位小數；高與中的原因欄留空；UTF-8 無 BOM、LF；重跑逐 byte 相同；零組也有表頭（紅）
- [x] 5.2 實作 `scripts/mt/pairs.py`（綠）

## 6. 整批產出（news/pairs_run.py）

- [x] 6.1 寫 `tests/mt/test_run.py`：只做 2021-01～10；缺一側只列出、離開碼 0；基準表存在就不重算，加一個月份舊檔與基準表逐 byte 不變；`--recalibrate` 才重算；整批不呼叫任何模型；合併門檻只從 `tier.py` 讀（紅）
- [x] 6.2 `scripts/news/paths.py` 加 `PAIRS_DIR`、`PAIRS_CALIBRATION`；實作 `scripts/news/pairs_run.py`（綠）
- [x] 6.3 實機跑：`--recalibrate` 產出校正基準，再產出 2021-01～10 全部集數到 `Kari-SRT/news/2-asr-whisper/2-平行語料/`

## 7. 離線重建（news/rebuild.py）

- [x] 7.1 寫 `tests/news/test_rebuild_pairs.py`：手改 CSV 一格要被指名；缺辭典先抓再驗、SFTP 也失敗就指名中止不宣告通過；2-平行語料 有而 1-srt-sapolita 或 3-srt 沒有要報包含錯誤；還沒做的集數不算錯（紅）
- [x] 7.2 `scripts/news/rebuild.py` 在 `speech_stages()` 加上 2-平行語料、包含規則加兩條（綠）
- [x] 7.3 驗收：`scripts.news.rebuild --verify` 對 2021-01～10 的 2-平行語料 逐 byte 通過

## 8. 資料層文件

- [x] 8.1 寫 `Kari-SRT/news/2-asr-whisper/2-平行語料/README.md`：這層是什麼、從哪裡產、欄位說明、三層與不採用原因的定義、校正基準、辭典版本（xlsx 檔名日期）、門檻（調參結果先留「暫定 30%，調參中」）
- [x] 8.2 改 `Kari-SRT/news/2-asr-whisper/README.md` 的流程圖與「誰讀」；改 `Kari-SRT/README.md` 的結構樹

## 9. 開會了量測工具（tools/mtgold/）

- [x] 9.1 寫 `tests/tools/mtgold/test_sweep.py`：六個門檻值各出一列；沒有 sapolita 結果的集（107）列出來、不當錯誤（紅）
- [x] 9.2 實作 `tools/mtgold/sweep.py`（綠）；把實驗用的開會了 sapolita 送件程式整理成 `tools/mtgold/sapolita_aiyalaeho.py`
- [x] 9.3 實機跑 sweep，結果寫到 `kithann/out/mt/調參/開會了掃描.csv`

## 10. 調參（mt/tuning.py、news/pairs_tune.py）

- [x] 10.1 寫 `tests/mt/test_tuning.py`：邊界分格用較少那邊的最大比例、≥50% 不會出現；固定種子可重現；格內不足 97 處全收並註明；三組（合併、拆開 A、拆開 B）的組成、其他邊界不合併；合併版與拆開版在不同批次；單列超過 1,800 字元的處不抽；一批 200 組拆成 4 個 50 組的請求檔；回覆編號不全就整批退回並指名；分數＝詞數 ×（高 1、中 0.5、低 0）；「一樣」不計；Wilson 95% 區間跨過 0.5 標「分不出」；選最低的 t 使 t 以上各格合併較好或分不出（分不出取較低門檻）；40–50% 就拆開較好選不合併（紅）
- [x] 10.2 實作 `scripts/mt/tuning.py`（綠）；段落版判準入 repo 為 `scripts/mt/judge_prompt_paragraph.md`
- [x] 10.3 實作 `scripts/news/pairs_tune.py`（`--sample`、`--ingest`、`--report`），請求與回覆放 `kithann/out/mt/調參/`
- [x] 10.4 抽樣：五格各 97 處（95% 信心、±10 點），寫出約 7 批請求
- [x] 10.5 逐批交 Opus subagent 判（一批 200 組、不讀回檢查），每批回來就 `--ingest` 收件
- [x] 10.6 `--report` 產出各格比例表，依 design 的選值規則定出合併門檻
- [x] 10.7 若選定的值不是 30%：改 `tier.py` 的常數、`pairs_run --recalibrate`、重產 2021-01～10、`rebuild --verify` 通過
- [x] 10.8 把選定的值、各格比例表、開會了掃描的對照，寫進 `2-平行語料/README.md`

## 11. 收尾驗收

- [x] 11.1 `tox -e unittest`、`tox -e flake8`、`tox -e rebuild`（news）、`scripts.aiyalaeho.rebuild --verify`、`name_catalogue --check` 全過
- [x] 11.2 `tests/README.md`、`scripts/README.md` 的清單與實際檔案一致（`test_readme_covers_scripts` 通過）
- [x] 11.3 回報寫到 `kithann/tuiue/`：各層組數與詞數、各族產量、選定的門檻與理由
