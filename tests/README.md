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
├── news/         族語新聞編排層測試（來源選擇、月份計畫、完整性、
│                 asrmt_run、smkul、tracker、refine、paths 保護…）
├── aiyalaeho/    《開會了》編排層測試（檔名解析、雙槽驗版型、雙列
│                 組裝、九欄進度表、0-cue 交付、離線重建）
└── e2e/          fixture.py  test_roundtrip（合成影片端對端，tox -e e2etest）
```

分組與跑法：

```bash
.tox/unittest/bin/python -m unittest discover -s tests/<組> -t .
# 組：ocr（影像側引擎）srtlib（共用組裝）asrmt（語音側引擎）
#     news／aiyalaeho（兩个語料ê編排）e2e（端對端，另走 tox -e e2etest）
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
| srt-data-store | 兩側都有交付時時間戳愛逐條仝；干焦影像側ê免比嘛免警告 | `news/test_coaxial.py` |
| srt-data-store | 只有精修過ê時間軸會使入 store；「揣無」佮「未精修」各講各ê | `news/test_publish_refined_only.py` |
| srt-data-store | 進度表十二欄佮順序；`成果檔名`＝srt_name；`cues` 對 store 推導 | `news/test_tracker_columns.py` |
| srt-data-store | 逐字稿干焦一个來源（疊層提掉了後） | `news/test_single_vision_source.py` |
| cue-timing | 時間軸寫一擺就唯讀：cues 寫 `1-cues/`、refine 寫 `2-refined/` | `news/test_workdir_writers.py` |
| cue-timing | 用 cue 號碼做鍵ê物件清單（清單改一位就好） | `news/test_cue_key_registry.py` |
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

## 《開會了》編排（tests/aiyalaeho/ ↔ scripts/aiyalaeho/）

| spec | scenario | 測試檔 |
|---|---|---|
| aiyalaeho-sourcing | 檔名解析出集數／族語別／語言別／語言代號；變體字樣照錄；德路固是賽德克ê變體毋是太魯閣；規範查無ê變體退族語級代號；括號註記佮字幕狀態毋入欄位 | `aiyalaeho/test_catalogue.py` |
| aiyalaeho-sourcing | 命名鍵是 `開會了_<集數3碼>_…`；佮新聞ê鍵袂相撞；work dir 就是彼个名 | `aiyalaeho/test_paths.py` |
| aiyalaeho-sourcing | 無法解析ê檔名略過並指名，其他照常登記；人指定族語別會當補登記；重跑不重複登記；目錄無彼逝嘛照登 | `aiyalaeho/test_catalogue.py` |
| cue-timing | 雙列帶前驗：兩列各佇家己ê槽／整帶漂十外 px 猶原過／單列只有華語過／無字幕集毋算失敗／新聞版型擋落來 | `aiyalaeho/test_verify_band.py` |
| cue-timing | 0.5 秒留白、間距不足佇中點相接、袂出負值袂超片長、留白無寫轉去時間軸 | `aiyalaeho/test_make_srt.py` |
| subtitle-text-source | 每條恆兩行帶標籤「族語：／華語：」；某列空白猶原出標籤行；兩列攏空無出；合併比兩行合成ê字串 | `aiyalaeho/test_make_srt.py` |
| subtitle-text-source | 兩逝一 cue ê TSV：列名毋著／cue 無佇 sheet 頂懸／仝一 cue 兩批攏有——規批拒收 | `aiyalaeho/test_ingest.py` |
| srt-data-store | store 版面（`aiyalaeho/1-ocr/{1-cues,2-vision,3-srt}`、不分層）；inventory 欄位宣告 | `aiyalaeho/test_paths.py` |
| —（成本防線） | preset ê列懸度愛予一張 sheet 囥會落四條 cue（1.10 MP 預算；超過就恬恬加三成閱讀量） | `aiyalaeho/test_paths.py` |
| srt-data-store | 進度表九欄佮順序；成果檔名＝srt_name；影片長度由時間軸推導；pending 不入定版表 | `aiyalaeho/test_tracker.py` |
| srt-data-store | 0-cue 集算校讀完成、以 0 行交付、袂擋整批；整批未完成一字都無寫 | `aiyalaeho/test_publish.py` |
| srt-data-store | 干焦用 store 重建雙列 SRT＋smkul.csv 逐 byte；缺件指名；pending 跳過 | `aiyalaeho/test_rebuild.py` |

## 端對端（tests/e2e/）

| spec | scenario | 測試檔 |
|---|---|---|
| 全鏈 | 合成影片燒入已知 SRT → 跑真實 pipeline 抽回 → 逐 cue 比對時間與文字（時間數學唯一的外部對照；需 ffmpeg＋tesseract，`tox -e e2etest`） | `e2e/test_roundtrip.py`＋`e2e/fixture.py` |
