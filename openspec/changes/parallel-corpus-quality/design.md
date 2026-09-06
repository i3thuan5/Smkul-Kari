## Context

見 proposal.md「Why」。現況：語音側店面是 `1-words/ 2-entries/ 3-srt-raw/`，加上使用者 checkout 回來的試點產物 `4-srt-ai/ 5-align/ 6-srt-complete/ mt-cache/`；程式在 `scripts/asrmt/`（`asr`、`project`、`bisrt`）與 `scripts/news/asrmt_run.py`（words／entries／raw 三步），另有 checkout 回來的 `scripts/asrmt/align/`（`mtclient`、`claude_mt`、`detect`、`dpalign`、`render`）及其測試。`rebuild --verify` 只對影像側逐 byte 重建，語音側只比時間戳（`coaxial.py`）。

約束：容器內沒有 Anthropic SDK 也沒有 API key，模型工作一律走 Claude Code subagent 讀批次檔、寫回覆檔（視覺辨識與 `claude_mt` 的既有紀律）。ai-labs 翻譯服務是公共服務，單併發、每請求間隔 1 秒、一集約 12–15 分鐘。沒有懂族語的人力做校準。

## Goals / Non-Goals

**Goals:**
- 每條 2-srt-raw 條目得到一個高／中／低標籤，高的精度優先。
- 語音側每個交付檔都能離線逐 byte 重建，與影像側同軸由此自然成立。
- 店面每個檔人打開就讀得懂。

**Non-Goals:**
- 不做華語→族語方向、不做語意整併、不做分句。
- 不在 `smkul.csv` 加品質欄（做完另開一條）。
- 不做人工校準（沒人力），只做替代驗證並揭露。
- 尚未辨識（沒有 `1-words`）的集數不在本 change 內辨識；已辨識的全部做到 `4-srt-quality`。
- 不碰 `scripts/aiyalaeho/`（那條線依 CLAUDE.md 自改 json.dump）。

## Decisions

**1. 拿掉 2-entries，投影不落地。** `project.project(words, rows)` 是純函式，輸入是 1-words 與由影像側時間軸＋共用組裝鏈算出的 rows；每個消費者（render、翻譯、判定、重建）當場重算，幾毫秒。替代方案是留著當「來源追蹤」——但它是視圖不是正本，重投影就整份重產，今天試點的譯文就是這樣被洗掉的；正本應該在內容定址的快取。拿掉之後語音側才有「僅由 store 逐 byte 重建」的性質。

**2. 標籤依用途分兩組。** `2-srt-raw` 是正式交付，維持短標籤「族語：」「華語：」；`3-srt-ai`、`4-srt-quality` 是分析用，行首標籤標明來源（`族語ASR結果：`／`華語OCR字幕：`／`族語ASR結果翻譯華語-ailabs：`／`族華對應品質：`）。使用者裁定 2026-09-04：正式要用的檔不帶分析標籤。好處是 2-srt-raw 只改名不改內容，改名後 `rebuild --verify` 用新的「投影不落地」路徑重建仍須與既有 59 檔逐 byte 相同——這同時證明新路徑與舊產物等價。

**3. 裁判走 subagent 批次，不接 API。** `judge.write_batches` 寫 `kithann/out/asrmt/<srt_name>/quality/sNN.tsv`（欄：id、族語行、華語行、ailabs 譯文、前字幕、後字幕），subagent（`model: sonnet`）讀一批寫 `sNN.reply.tsv`（id、標籤）；`judge.ingest` 的 id 集合檢查沿用 `claude_mt.ingest_reply` 的寫法。第二輪只對 Sonnet 給高的寫 `fNN.tsv`，subagent `model: fable`。100 條一批。替代方案是 Messages Batch API：便宜一半，但要裝 SDK、管 key，違反「裝得越少越好」，且 repo 其他模型工作都不是這樣跑的。

**4. 判定快取的鍵。** （裁判、prompt 版本、族語行、華語行、ailabs 譯文、前字幕、後字幕）。含鄰句是因為鄰句是裁判看到的材料之一，材料變了答案就可能變；代價是 cue 分割會讓相鄰兩條失效，可接受。不含條目編號與時間戳：重投影會整批移位。每個裁判一個 JSONL 檔（`sonnet.jsonl`、`fable.jsonl`），最終標籤在 render 時由兩個答案合成，不另存——合成規則是純函式。

**5. 不設規則層。** 使用者裁定。原本想用句級 conf 與詞/秒比先擋掉低的，量過之後詞/秒比幾乎完全被 conf 涵蓋、剩下的裁判一看就會給低，而且 conf 門檻 0.7 沒有人校過。全部交裁判，成本多約一倍（一集 $0.12 → 仍不到視覺辨識的一成），換來零門檻。空行不問模型，因為沒有東西可判——這不是規則，是退化情況。

**6. 高要兩個裁判同意。** Sonnet 5 判全部，給高的再交 Fable 5.1。沒有人力做校準，高的精度只能靠獨立模型背書；Fable 只看候選（估三成），成本可控。替代方案「Sonnet 判兩次打亂順序」只量到穩定不量到對，留作一次性量測（決定 9）。

**7. 只做族語→華語。** 比對發生在華語端：字幕是參考答案，裁判在華語最強。反方向把濃縮字幕翻回族語，天生比 ASR 短、比對落在弱的一端，舊偵測也從沒用過那個方向。`mtclient` 搬到 `scripts/asrmt/mtclient.py`，砍掉 `z2f`；`mt-cache/claude.jsonl` 刪除（Claude 不再當翻譯）。

**8. 方言碼靜態表。** `scripts/asrmt/dialects.py`：族語別(英) → ai-labs 語言碼。試點證明阿美五碼平手，逐集偵測是白花 50 次請求。阿美取試點 mt-cache 命中最多的那個碼，其餘族別的碼由服務的下拉選單一次性抄下。

**9. 沒人力校準的替代。** 兩項各在試點集（032晚）量一次、數字寫 README：構造法（`scripts/asrmt/probes.py` 產探針批次：配錯字幕、改數字、砍後半句，重判必須降級）；自我一致（同批打亂重跑，記翻牌率）。這是量測不是流程步驟，不進每集的成本。README 明寫「高的精度未經人工驗證」。

**10. 語音側逐 byte 重建取代時間戳比對。** `coaxial.py` 改為：對每個存在的語音側交付檔，用 store 內容重建後 `bytes ==`。`2-srt-raw` 的重建與 `asrmt_run` 的 raw 步共用同一函式（`asrmt_run.raw_body_of(srt_name)`），確保「產」和「驗」走同一條路。快取缺件時重建函式擲 `PipelineError` 指名集與條目。時間戳比對不再需要——逐 byte 相同蘊含同軸。

**11. `json.dump` 全部 `ensure_ascii=False, indent=2, sort_keys=True`。** 理由（使用者裁定 2026-09-04）：`Kari-SRT/` 的內容要人打開就讀得懂，而且 diff 要能看出改了哪一行——緊縮一行的 JSON 兩者都做不到，中文轉義成 `\uXXXX` 更是誰都讀不了。`sort_keys` 讓同一份資料每次寫出來鍵序相同，逐 byte 重建才穩。JSONL 快取一列一筆不能縮排，其餘照用。既有 1-words（59 檔、18M，估變 3–4 倍）與 1-ocr/1-cues 用 `scripts/news/redump_store.py` 一次性重排——內容不變只是排版，`rebuild --verify` 讀的是內容，不受影響。`scripts/aiyalaeho/` 由該線自改。

**12. 步驟名。** `asrmt_run` 的步驟改為 `words`／`raw`／`mt`／`judge`（寫批次）／`ingest`（收回覆）／`quality`（render）；`--redo` 語意不變。`asrmt_batch` 只跑到 `raw`（CPU 工作），`mt` 之後由人或 `/smkul-news` 的語音側段發動——跟影像側「cues 是 CPU、OCR 是 Claude」同一種切法。

## 檔案樹

```
Kari-SRT/news/2-asr/
├── README.md                         改寫
├── 1-words/<年-月>/<srt_name>.json    scripts/asrmt/asr.py ← 音檔（重排格式）
├── 2-srt-raw/<年-月>/<srt_name>.srt   asrmt_run raw ← 1-words＋1-ocr/1-cues＋2-vision（投影在記憶體）
├── 3-srt-ai/<年-月>/<srt_name>.srt    asrmt_run mt ← 2-srt-raw＋mt-cache
├── 4-srt-quality/<年-月>/<srt_name>.srt  asrmt_run quality ← 3-srt-ai＋quality-cache
├── mt-cache/ailabs.jsonl             mtclient ← ai-labs 服務
└── quality-cache/sonnet.jsonl, fable.jsonl   judge.ingest ← subagent 回覆檔

scripts/asrmt/
├── asr.py            不變（dump 參數）
├── project.py        不變
├── bisrt.py          raw_body 不變；加 ai_body(entries, cache)、quality_body(entries, verdicts)
├── mtclient.py       從 align/ 搬上來，砍 z2f
├── dialects.py       新：ETHNICITY_LANG 表、lang_of(ethnicity)
├── judge.py          新：LABELS、PROMPT_VERSION、materials(entries)、write_batches、ingest_reply、
│                     QualityCache、final_label(sonnet, fable)、verdicts(entries, cache)
├── probes.py         新：mispair／renumber／truncate 探針批次
└── align/            刪（claude_mt、detect、dpalign、render）

scripts/news/
├── asrmt_run.py      步驟 words／raw／mt／judge／ingest／quality；rows_of()、raw_body_of()
├── asrmt_batch.py    只到 raw；raw_dir 改 2-srt-raw
├── tracker.py        ASR_SRT = ("2-srt-raw", ".srt")
├── coaxial.py        改：rebuild_problems(entries) 逐 byte
├── rebuild.py        呼叫改名
├── paths.py          ASR_STAGES 常數、MT_CACHE、QUALITY_CACHE
├── redump_store.py   新：一次性重排 store JSON
└── README.md         語音側段更新

tests/asrmt/
├── test_bisrt.py     raw 兩行測試不動；加三行 ai／quality、無語音
├── test_mtclient.py  搬上來（tests/asrmt/align/ 刪），砍 z2f
├── test_dialects.py  新
├── test_judge.py     新：材料、批次、收件紀律、快取鍵、合成規則
└── test_probes.py    新：三種探針各改動什麼、id 對得回原條目

tests/news/
├── test_smkul_asr.py     路徑改 2-srt-raw；3-srt-ai／4-srt-quality 不改欄值
├── test_coaxial.py       改：逐 byte、缺快取指名、沒檔不警告、做到一半通過
├── test_asrmt_run.py     步驟名；raw 不再讀中間檔
├── test_asrmt_batch.py   raw_dir
├── test_asrmt_redo.py    不變
└── test_redump_store.py  新：內容不變、格式變、冪等
```

## Risks / Trade-offs

- [Sonnet 對族語能力沒量過，可能把錯的當高] → Fable 第二裁判；構造法探針量盲點；README 揭露未經人工驗證。
- [鄰句進快取鍵，cue 分割讓相鄰條目失效] → 只多問幾條，接受；比起漏掉「對到隔壁句」的偏移，划算。
- [1-words 重排後 store 變大 3–4 倍] → 使用者裁定人讀得懂優先；私有 repo。
- [ai-labs 服務 502／改版] → 既有重試與 SSE 協定集中在 `HttpTransport`，中斷可續跑；一集只 12–15 分鐘。
- [subagent 回覆格式跑掉] → 整批拒收、指名問題、重跑那一批；快取已收的不重問。
- [prompt 改了舊判定失效] → prompt 版本在鍵裡，舊的不會被錯用；要重判就是重判。

## Migration Plan

1. 店面：`mv 3-srt-raw 2-srt-raw`；`rm -r 2-entries 4-srt-ai 5-align 6-srt-complete mt-cache/claude.jsonl`（我 rm／mv，使用者最後 `git add -A`）。
2. `redump_store.py` 重排 1-words 與 1-ocr/1-cues；`rebuild --verify` 必須仍通過（內容沒變）。
3. 2-srt-raw 只改名不改內容；`rebuild --verify` 以新的投影路徑重建，須與既有 59 檔逐 byte 相同。
4. 試點 032晚 跑 mt → judge → ingest → quality，量探針與自我一致，寫 README。
5. 試點數字寫好後，所有已辨識的集數逐集跑 mt → judge → ingest → quality（任務 10），進度用 `/loop 20m` 盯；做完 `rebuild --verify` 全部逐 byte 通過。

回退：所有改動可由 git 還原；store 改名與重排是純檔案操作。

## Open Questions

- 族語行的 tokenizer 切法沒實測，成本估算用「3 字元一 token」；開工第一批用 subagent 回報的用量校正。不影響 spec 與任務。
