## Why

語音側交付 `3-srt-raw` 每條是「族語 ASR 行＋華語字幕行」，要拿去當機器翻譯的平行語料，但兩行對不對得上沒有人判過：字幕是濃縮改寫，ASR 有錯有漏，直接餵進訓練集會污染模型。上一輪的 align 延伸想用字面相似度（bigram）自動判，試點證明尺是錯的（對位正確的 50 句裡 36 句 F1＝0），已整條刪除。這一輪把目標縮小成一件事：**逐條標出族語與華語的對應品質（高／中／低），高的才進訓練集**，寧缺勿濫。順便把語音側的店面改成人打開就讀得懂的版面。

## What Changes

- **語音側店面重排**（**BREAKING**，路徑全改）：`Kari-SRT/news/2-asr/` 改為 `1-words/`、`2-srt-raw/`、`3-srt-ai/`、`4-srt-quality/`、`mt-cache/`、`quality-cache/`。刪 `2-entries/`（投影是純函式，結果不落地，改為每次由 1-words＋時間軸重算）；`3-srt-raw/` 改名 `2-srt-raw/`；刪試點的 `4-srt-ai/`、`5-align/`、`6-srt-complete/`；`mt-cache/` 留（ailabs 譯文正本）。
- **新交付 `3-srt-ai/`**：每條三行帶標籤——`族語ASR結果：`／`華語OCR字幕：`／`族語ASR結果翻譯華語-ailabs：`。只做族語→華語一個方向；譯文由 ILRDF ai-labs（NLLB 族語特化）產，內容定址存 `mt-cache/`。
- **新交付 `4-srt-quality/`**：每條三行——`族語ASR結果：`／`華語OCR字幕：`／`族華對應品質：高|中|低`。判定由兩個裁判做：Sonnet 5 判全部；Sonnet 給高的再交 Fable 5.1，Fable 也給高才是高，不同意降為中。族語行或華語行空白的條目不問模型，直接低。判定正本內容定址存 `quality-cache/`（JSONL，兩個裁判的答案都留）。不設規則層——沒有任何門檻要人校。
- **裁判怎麼跑**：沿用視覺辨識與 claude_mt 的批次紀律——程式寫編號 TSV 批次檔，Claude Code subagent（`model: sonnet`／`model: fable`）讀一批寫一個回覆檔，ingest 只在 id 集合完全相等時收下整批。不接 API、不裝 SDK。
- **同軸推廣**：`rebuild --verify` 對語音側從「只比時間戳」改為**逐 byte 重建**：2-srt-raw 由 1-words＋時間軸重投影渲染、3-srt-ai 由 2-srt-raw＋mt-cache、4-srt-quality 由 3-srt-ai＋quality-cache，全部離線、與店面檔逐 byte 比。快取缺一筆算錯；後面階段沒檔不算錯（既有規則）。
- **方言碼改靜態表**：族別(英)→ai-labs 語言碼一張表放程式裡；試點證明阿美五碼平手，不再逐集偵測。
- **人讀得懂**：`json.dump` 全部 `ensure_ascii=False, indent=2, sort_keys=True`（JSONL 不 indent）；店面既有 1-words、1-ocr/1-cues 一次性重排成同格式。理由記在 design。
- **沒人力校準的替代**：構造法（配錯字幕、改數字、砍半句必須降級）與打亂重跑的自我一致，在試點集量一次，數字寫 README，並註明「高的精度未經人工驗證」。quality-cache 留著，日後有人力抽 30 條高來核。
- 進度表這次**不**加品質欄；品質步做完後另開一小條。

## Capabilities

### New Capabilities
- `parallel-corpus-quality`: 每條族語／華語對的對應品質三級（高／中／低）操作型定義、兩裁判互證、判定快取內容定址、`3-srt-ai` 與 `4-srt-quality` 兩個交付的格式與同軸、無人力時的替代校準與 README 揭露。

### Modified Capabilities
- `asr-bilingual-srt`: 「投影結果落地為獨立條目檔」改為「投影是純函式、不落地、可重算」；「產出存放於 Kari-SRT」的階段目錄改為 1-words／2-srt-raw／3-srt-ai／4-srt-quality／mt-cache／quality-cache；「條目文字行——兩行對照格式」路徑改 `2-srt-raw`，標籤維持 `族語：`／`華語：`（正式交付用短標籤；3、4 是分析用，標籤標明來源）；「翻譯快取」條文回來（族語→華語單向）。
- `srt-data-store`: 「歷史目錄已清除」情境改為新版面（`2-entries`、`4-srt-ai`、`5-align`、`6-srt-complete` 不存在；`mt-cache`、`quality-cache` 存在）；「兩側交付都在時時間軸逐條相同」改為語音側四個 SRT 逐 byte 重建驗證；「語音辨識模型欄」改看 `2-srt-raw/`；store 內 JSON 排版要求（人讀得懂）。

## Impact

### Kari-SRT（資料）

```
Kari-SRT/news/2-asr/
├── README.md               改寫：新版面、每個檔由誰產、吃什麼
├── 1-words/<年-月>/<srt_name>.json      不變（內容重排成 indent=2 sort_keys）
├── 2-srt-raw/<年-月>/<srt_name>.srt     由 3-srt-raw 改名，內容不變（`族語：`／`華語：`）
├── 3-srt-ai/<年-月>/<srt_name>.srt      新：三行（族語／字幕／ailabs 譯文）
├── 4-srt-quality/<年-月>/<srt_name>.srt 新：三行（族語／字幕／品質）
├── mt-cache/ailabs.jsonl   留；claude.jsonl 刪（Claude 不再當翻譯）
└── quality-cache/sonnet.jsonl, fable.jsonl   新：判定正本
刪：2-entries/、4-srt-ai/、5-align/、6-srt-complete/
```

### scripts/（程式）

- `scripts/asrmt/`：`project.py`（不變）、`bisrt.py`（加三行 ai／quality 渲染；兩行 raw 不變）、`mtclient.py`（從 align/ 搬上來，砍 z2f）、`judge.py`（新：批次檔寫出、回覆 ingest、兩裁判合成、quality-cache）、`dialects.py`（新：族別→語言碼靜態表）、`probes.py`（新：構造法探針）。刪 `align/`（claude_mt、detect、dpalign、render）。
- `scripts/news/`：`asrmt_run.py`（步驟改 words／raw／mt／judge-batches／judge-ingest／quality；raw 步在記憶體投影）、`asrmt_batch.py`（跟著改）、`tracker.py`（`ASR_SRT` 指 `2-srt-raw`）、`coaxial.py`（改為語音側逐 byte 重建比對）、`rebuild.py`（呼叫）、`paths.py`（階段常數）、`redump_store.py`（新：一次性重排店面 JSON）。
- 全 repo `json.dump` 參數改齊（aiyalaeho 那套由該線自改）。

### tests/

- `tests/asrmt/`：`test_bisrt.py`（改）、`test_judge.py`（新）、`test_mtclient.py`（搬上來、砍 z2f）、`test_dialects.py`（新）、`test_probes.py`（新）。刪 `tests/asrmt/align/`。
- `tests/news/`：`test_smkul_asr.py`、`test_coaxial.py`、`test_asrmt_run.py`、`test_asrmt_batch.py`、`test_asrmt_redo.py` 改路徑與步驟；`test_asrmt_rebuild.py`（新：語音側逐 byte 重建）；`test_redump_store.py`（新）。

### 文件
`Kari-SRT/news/2-asr/README.md`、`scripts/news/README.md`、`.claude/commands/smkul-news.md`（加語音側品質步的操作段）。
