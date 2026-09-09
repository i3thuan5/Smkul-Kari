## 1. 店面搬遷與重排

- [x] 1.1 測試 `tests/news/test_redump_store.py`（紅）：重排後 JSON 內容相等、檔案是多行縮排鍵排序、跑兩次不變、JSONL 只重寫鍵序不縮排
- [x] 1.2 實作 `scripts/news/redump_store.py`（綠）：掃 `1-words/`、`1-ocr/1-cues/`、`mt-cache/`，`--write` 才動
- [x] 1.3 `mv Kari-SRT/news/2-asr/3-srt-raw 2-srt-raw`；`rm -r 2-entries 4-srt-ai 5-align 6-srt-complete mt-cache/claude.jsonl`；`rm -r scripts/asrmt/align tests/asrmt/align`（`mtclient` 與其測試先搬走，見 5.x）
- [x] 1.4 `paths.py` 加語音側階段常數（`ASR_WORDS`、`ASR_RAW`、`ASR_AI`、`ASR_QUALITY`、`MT_CACHE`、`QUALITY_CACHE`），`test_paths.py` 先紅後綠

## 2. 進度表與重建驗證跟上路徑

- [x] 2.1 `test_smkul_asr.py` 改成 `2-srt-raw` 決定欄值、`3-srt-ai`／`4-srt-quality` 不改欄值（紅）→ `tracker.ASR_SRT` 改（綠）
- [x] 2.2 `test_asrmt_batch.py` raw_dir 改（紅）→ `asrmt_batch.py`（綠）
- [x] 2.3 `test_asrmt_redo.py` 不變，確認仍綠

## 3. 兩行帶標籤與投影不落地

- [x] 3.1 `test_bisrt.py` 既有 `raw_body` 測試（「族語：」「華語：」、無語音保留前綴）不動，確認仍綠；`raw_body` 不改
- [x] 3.2 `test_asrmt_run.py`：`rows_of(srt_name)` 由 1-words＋時間軸投影得 rows；`raw_body_of` 不讀任何 `2-entries`；`step_raw` 寫 `2-srt-raw`（紅）→ `asrmt_run`：刪 `step_entries`／`_entries_path`，步驟 `words`／`raw`（綠）
- [x] 3.3 改名後的 59 個 2-srt-raw 內容不動（git 只看到 rename）；4.3 的逐 byte 重建就是新投影路徑＝舊產物的證明
- [x] 3.4 `redump_store.py --write` 重排 1-words 與 1-cues；`rebuild --verify` 通過

## 4. 語音側逐 byte 重建

- [x] 4.1 `test_coaxial.py` 重寫（紅）：存在的每個語音側檔逐 byte 比；沒檔不警告；做到一半通過；`2-srt-raw` 不同指名集與檔；快取缺筆指名集與條
- [x] 4.2 `coaxial.py` 改為 `rebuild_problems(entries)`，重建函式與 `asrmt_run` 共用（綠）；`rebuild.py` 呼叫改名、訊息改「重投影閣 render」
- [x] 4.3 `rebuild --verify` 對現有 59 集通過（此時只有 2-srt-raw）

## 5. 翻譯：mtclient 搬家、方言表、mt 步

- [x] 5.1 `tests/asrmt/test_mtclient.py`（從 align/ 搬來、刪 z2f 測試）先紅：`from scripts.asrmt import mtclient`；→ 搬 `mtclient.py`、砍 `z2f`／`lambda_1`／`translate_1`（綠）；`fixtures.py` 跟著改
- [x] 5.2 `test_dialects.py`（紅）：已知族別查得碼、未知族別 `PipelineError` 指名 → `dialects.py`（綠）；阿美取 mt-cache 命中最多的碼，其餘族別碼由服務下拉選單一次性抄下並註明來源
- [x] 5.3 `test_bisrt.py`：`ai_body(entries, cache)` 三行、無語音譯文行只有前綴、缺快取擲 `PipelineError` 指名條目（紅）→ 實作（綠）
- [x] 5.4 `test_asrmt_run.py`：`step_mt` 對每條非空族語行 `translate_cached`、寫 `3-srt-ai`（用假 transport）（紅）→ 實作（綠）
- [x] 5.5 試點 032晚 跑 `--step mt`（背景），確認 648 條命中、其餘補問，`3-srt-ai` 產出

## 6. 裁判：批次、收件、快取、合成

- [x] 6.1 `test_judge.py` 材料（紅）：`materials(entries, cache)` 每條含族語行、華語行、譯文、前後字幕，首尾條鄰句為空；空行條目不進批次 → 實作（綠）
- [x] 6.2 `test_judge.py` 批次（紅）：`write_batches` 100 條一批、編號、TSV 欄位固定、譯文含 tab 不破壞 → 實作（綠）
- [x] 6.3 `test_judge.py` 收件（紅）：id 集合相等且標籤合法才收；陌生 id／缺 id／重複 id／非法標籤各整批拒收並指名 → `ingest_reply`（綠）
- [x] 6.4 `test_judge.py` 快取（紅）：`QualityCache` 鍵七元組、每裁判一檔 JSONL 鍵排序、命中不重問、鄰句改變視為新鍵、重開後讀回 → 實作（綠）
- [x] 6.5 `test_judge.py` 合成（紅）：`final_label`：(高,高)→高、(高,中|低)→中、(中,·)→中、(低,·)→低、空行→低；第一裁判非高時不需第二裁判 → 實作（綠）
- [x] 6.6 `test_bisrt.py`：`quality_body` 三行、不含譯文（紅）→ 實作（綠）
- [x] 6.7 `test_asrmt_run.py`：`step_judge` 寫 sNN 批次（只寫快取未命中的），`--second` 寫 fNN 批次（只寫 Sonnet 給高且 Fable 未判的）；`step_ingest` 收回覆進快取；`step_quality` 要求每條都有判定，缺就指名（紅）→ 實作（綠）
- [x] 6.9 `ingest_reply` 擋「整批攏低」：一批 10 條以上而且逐條攏低就整批退（阿美 s07、雅美 s13 兩批是按呢來ê，重判後各有 41、27 條毋是低）；規批中無擋，彼是「無把握一律給中」ê合法結果
- [x] 6.10 `step_judge` 擋「回覆猶未收就重寫批次」：`_clear_batches` 會kā請求檔刣掉重排，中間若有條目入快取，賰ê就重新分批，飛咧ê agent 回來會貼毋著位
- [x] 6.11 `rebuild.speech_stages()` 加 `4-srt-quality`：本底干焦列 raw 佮 ai 兩層，品質彼層無人顧——阿美 032晚 是舊版 prompt 判ê，材料加了「譯文可疑註記」欄了後根本重建袂出來，`--verify` 猶原講「攏仝款」
- [x] 6.8 裁判 prompt 寫成 `scripts/asrmt/judge_prompt.md`（三級定義照 spec 逐字、材料說明、回覆格式 `id\t標籤`），`PROMPT_VERSION` 常數與之對應；`test_judge.py` 驗 prompt 檔含三級定義關鍵句

## 7. 試點與替代驗證

- [x] 7.1 032晚：`--step judge` 寫批次 → subagent `model: sonnet` 逐批回覆（一批一個 agent，回報 token 用量）→ `--step ingest`
- [x] 7.2 032晚：`--step judge --second` → subagent `model: fable` → `--step ingest`；`--step quality` 產 `4-srt-quality`；`rebuild --verify` 逐 byte 通過
- [x] 7.3 `test_probes.py`（紅）：mispair／renumber／truncate 三種探針各只改一件事、id 對得回原條目、只取高的條目 → `probes.py`（綠）
- [x] 7.4 032晚探針批次跑 Sonnet，量各類降級率；同一批打亂重跑量翻牌率；把三級分布、探針結果、翻牌率、token 用量寫進 `2-asr/README.md`，並註明高未經人工驗證
- [x] 7.5 依 7.4 結果決定要不要收緊高的定義或 prompt（改了就 `PROMPT_VERSION` 加一、重判）

## 8. 人讀得懂與文件

- [x] 8.1 `scripts/news`、`scripts/ocr`、`scripts/asrmt` 全部 `json.dump` 改 `ensure_ascii=False, indent=2, sort_keys=True`（JSONL 除外）；受影響測試先紅後綠；工作區既有 `sheets.json`、`transcripts.json` 等由下次寫入自然更新
- [x] 8.2 `Kari-SRT/news/2-asr/README.md` 改寫：新版面流程圖、輸出入對照表、同軸與逐 byte 重建、品質三級定義、替代驗證數字、廢止段更新
- [x] 8.3 `scripts/news/README.md` 語音側段、`.claude/commands/smkul-news.md` 加語音側 mt／judge／ingest／quality 操作段（含 subagent model 與批次規矩）
- [x] 8.4 `tests/news/test_readme_covers_scripts.py` 對新模組仍綠

## 9. 驗收

- [x] 9.1 `tox -e unittest`、`tox -e flake8` 通過
- [x] 9.2 `tox -e rebuild`（`rebuild --verify`）通過，集數＝inventory 非 pending 筆數；語音側 59 集 2-srt-raw、試點 3-srt-ai／4-srt-quality 逐 byte 相同
- [x] 9.3 `python3 -m scripts.news.name_catalogue --check` 通過
- [x] 9.4 回覆檔寫 `kithann/tuiue/`：試點數字、成本實測、待使用者做的 `git add -A`

## 10. 全部已辨識集數試做

- [x] 10.1 `asrmt_run --step mt` 對所有已有 `2-srt-raw` 的集數逐集跑（`run_in_background`、`&&` 串、`set -o pipefail`；ai-labs 單併發，一集 12–15 分鐘，全部約半天）；每集落地可續跑
- [x] 10.2 每集 `--step judge` 寫 Sonnet 批次 → subagent `model: sonnet` 逐批回覆 → `--step ingest`；再 `--step judge --second` → subagent `model: fable` → `--step ingest` → `--step quality`。批次大小視第一集實測的 token 用量決定（100 或 200 條一批）
- [x] 10.3 全程用 `/loop 20m` 檢查進度：mt 做到第幾集、judge 收了幾批、拒收與失敗列出來；有內容的進度寫 `kithann/tuiue/`，純「還在跑」不寫
- [x] 10.4 全部做完：`rebuild --verify` 對每集的 `2-srt-raw`／`3-srt-ai`／`4-srt-quality` 逐 byte 通過；三級分布、總 token 用量與實際成本寫進 `2-asr/README.md` 與回覆檔
