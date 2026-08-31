# tests/：spec × scenario × 測試檔對照表

測試檔名鏡射模組名（`test_project.py` ↔ `project.py`）——**檔名管
定位**，改哪支程式就跑哪個檔；**這張表管照流程理解**，按 pipeline
順序排列。全部離線、fixture 合成，照 CLAUDE.md TDD 先紅後綠。

## 結構

```
tests/
├── ocr/          test_mask  test_region  test_segmenter  test_sheets
│                 test_import_tsv  test_ocr_prep  test_presets  test_auto_options
├── srtlib/       test_srt  test_merge_repeats  test_pad_edges  test_chain
├── asrmt/        fixtures.py  test_project  test_bisrt
│   └── align/    test_mtclient  test_claude_mt  test_dpalign  test_render
│                 test_detect_blocks  test_detect_scores  test_detect_classify
├── news/         編排層測試（來源選擇、月份計畫、完整性、asrmt_run、
│                 smkul、tracker、refine、paths 保護、sftp.sh 介面…）
└── e2e/          fixture.py  test_roundtrip（合成影片端對端，tox -e e2etest）
```

分組與跑法：

```bash
.tox/unittest/bin/python -m unittest discover -s tests/<組> -t .
# 組：ocr（影像側引擎）srtlib（共用組裝）asrmt（語音側引擎）
#     news（編排）e2e（端對端，另走 tox -e e2etest）
```

## 影像側引擎（tests/ocr/ ↔ scripts/ocr/）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 精修取樣密度／邊界取中點／偏移超限即擋下／缺輸入明確失敗 | `news/test_refine.py`（純邏輯）＋ `ocr/test_segmenter.py`（切分） |
| cue-timing | 批次切 cue 前驗證字幕帶（紅帶低位通過／侵入擋下） | `news/test_verify_band.py` |
| subtitle-text-source | 指定 preset 每個入口都生效／名稱錯誤中止 | `ocr/test_presets.py`、`ocr/test_auto_options.py` |
| subtitle-text-source | 只有經人校讀的視覺辨識可供字 | `ocr/test_import_tsv.py`（verified 記帳）、`news/test_vision_complete.py` |
| —（引擎行為） | 像素遮罩／區域運算 | `ocr/test_mask.py`、`ocr/test_region.py` |
| —（引擎行為） | sheet→TSV→匯入迴圈、glossary | `ocr/test_sheets.py` |
| —（引擎行為） | 辨識輸出清理 | `ocr/test_ocr_prep.py` |

## 共用組裝（tests/srtlib/ ↔ scripts/srtlib/）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | SRT 邊界留白（各延伸 0.5s／中點相接／時間軸資料不含留白／不出負值／不超片長） | `srtlib/test_pad_edges.py` |
| —（格式） | SRT 時間戳、render／parse round-trip | `srtlib/test_srt.py` |
| —（組裝） | 同文相鄰合併 | `srtlib/test_merge_repeats.py` |
| asr-bilingual-srt | 逐行同軸（同一條鏈、真實窗與顯示窗分開） | `srtlib/test_chain.py` |

## 語音側引擎（tests/asrmt/ ↔ scripts/asrmt/）

| spec | scenario | 測試檔 |
|---|---|---|
| asr-bilingual-srt | 跨界詞歸戶／中間過程可追溯／辨識文字忠實（詞文字零改動） | `asrmt/test_project.py` |
| asr-bilingual-srt | raw 兩行（僅原始材料）／無語音條目／同軸時間戳 | `asrmt/test_bisrt.py` |
| asr-bilingual-srt | 審查版六行＋偵測行／語意整併正式版／不覆蓋 | `asrmt/align/test_render.py` |
| asr-bilingual-srt | 翻譯快取續跑／同鍵不重打／單併發間隔／族別 handshake | `asrmt/align/test_mtclient.py` |
| asr-bilingual-srt | Claude 批次編號歸屬（幽靈 id／缺行／重複 id 整批拒收） | `asrmt/align/test_claude_mt.py` |
| speech-subtitle-alignment | 交錯句二對二合併恢復／拆併／帶外不配／錨點軟加分 | `asrmt/align/test_dpalign.py` |
| speech-subtitle-alignment | 連通塊（句跨條目綁塊／停頓斷塊／無語音自成塊） | `asrmt/align/test_detect_blocks.py` |
| speech-subtitle-alignment | 同義改寫高分／語序免疫／斷詞差異不影響 LCS／系統性 lead-lag 現形／平移不重譯／數字與借詞錨點 | `asrmt/align/test_detect_scores.py` |
| speech-subtitle-alignment | 歸因矩陣五類／塊級救回條目級／引擎互證／未校準自我聲明／matched_entries | `asrmt/align/test_detect_classify.py` |
| —（vosk 呼叫層） | 無法離線測——實模型煙霧測試把關；忠實性由投影與 render 測試守恆 | （無單元測試檔） |

## 編排（tests/news/ ↔ scripts/news/）

| spec | scenario | 測試檔 |
|---|---|---|
| srt-data-store | 交付物唯一正本／inventory 無第二份 | `news/test_paths.py`、`news/test_plan_month.py` |
| srt-data-store | 命名鍵 srt_name；逐集資料在播出月份一層，跨集與總表不分層 | `news/test_resolve_slug.py`、`news/test_add_episodes.py`、`news/test_paths.py` |
| srt-data-store | 進度表併記影片長度（由時間軸推導，尚無時間軸留白）| `news/test_tracker_row.py` |
| srt-data-store | 缺件時明確失敗／工作目錄全毀後重建 | `news/test_make_srt.py` |
| srt-data-store | pending 語意／整批完成才定版／進度表定版寫入 | `news/test_pending.py`、`news/test_tracker_home.py`、`news/test_tracker_row.py` |
| srt-data-store | 語音側進度欄由 store 推導 | `news/test_smkul_asr.py` |
| srt-data-store | 校讀完成比對編號集合 | `news/test_vision_complete.py` |
| subtitle-text-source | 文稿不供字／中間產物不擋交付 | `news/test_make_one.py`、`news/test_make_srt.py` |
| asr-bilingual-srt | 音檔時長不符指名中止／續跑跳過已完成步驟 | `news/test_asrmt_run.py` |
| —（工作流防線） | 不覆蓋已校讀 work dir、批次 sheet 歸屬、TSV 整批拒收 | `news/test_gap_guard.py`、`news/test_batches.py`、`news/test_ingest.py` |
| —（參數防線） | 名字不得帶路徑成分／路徑只准落在資料資料夾／sftp 路徑不得含引號換行 | `news/test_paths.py`、`news/test_sftp_cli.py` |

## 一集配一支檔（tests/news/ ↔ scripts/news/）

| spec | scenario | 測試檔 |
|---|---|---|
| episode-sourcing | 分號多來源逐條查得到／母帶優先／時段字樣決勝／無法辨識的時段不當成另一個時段／同名不同資料夾算同一份／一支檔不得歸屬兩集 | `news/test_sources.py` |
| episode-sourcing | 選不出來只略過該集不中止／略過的不進 inventory／報告帶候選路徑／目錄標示無影片者只計數 | `news/test_sources.py`、`news/test_plan_month.py` |
| episode-sourcing | 完整性不自動判定（`truncated`／`partial` 是人工註記）；影片長度只記錄 | `news/test_tracker_row.py` |
| episode-sourcing | 一個月可跨資料夾／同資料夾別的月份不選入／登記先於下載／重跑不重複登記 | `news/test_plan_month.py` |
| episode-sourcing | 抓檔清單來自 inventory 的 pending 條目，不是遠端 ls | `news/test_plan_month.py` |

## 端對端（tests/e2e/）

| spec | scenario | 測試檔 |
|---|---|---|
| 全鏈 | 合成影片燒入已知 SRT → 跑真實 pipeline 抽回 → 逐 cue 比對時間與文字（時間數學唯一的外部對照；需 ffmpeg＋tesseract，`tox -e e2etest`） | `e2e/test_roundtrip.py`＋`e2e/fixture.py` |
