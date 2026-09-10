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
│   │             組裝、九欄進度表、0-cue 交付、離線重建）
│   └── langcheck/  逐條語言判定（對照表佇該目錄ê README）
└── e2e/          fixture.py  test_roundtrip（合成影片端對端，tox -e e2etest）
```

分組與跑法：

```bash
.tox/unittest/bin/python -m unittest discover -s tests/<組> -t .
# 組：ocr（影像側引擎）srtlib（共用組裝）asrmt（語音側引擎）
#     news／aiyalaeho（兩个語料ê編排）tools（量測工具）
#     e2e（端對端，另走 tox -e e2etest）
```

## 影像側引擎（tests/ocr/ ↔ scripts/ocr/）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 精修取樣密度／邊界取中點／偏移超限即擋下／缺輸入明確失敗 | `news/test_refine.py`（純邏輯）＋ `ocr/test_segmenter.py`（切分） |
| cue-timing | 批次切 cue 前驗證字幕帶（紅帶低位通過／侵入擋下） | `news/test_verify_band.py` |
| cue-timing | 切 cue ê遮罩會使裁到帶頂：無指定就佮逐畫素仝款、指定了帶外逐列攏空；`--band-rows` 用絕對列傳入，寫入 manifest ê是 region 內ê偏移 | `ocr/test_cuelib_band_rows.py`、`ocr/test_band_rows_option.py` |
| subtitle-text-source | 指定 preset 每個入口都生效／名稱錯誤中止 | `ocr/test_presets.py`、`ocr/test_auto_options.py` |
| subtitle-text-source | 只有經人校讀的視覺辨識可供字 | `ocr/test_import_tsv.py`（verified 記帳）、`news/test_vision_complete.py` |
| —（引擎行為） | 像素遮罩／區域運算 | `ocr/test_mask.py`、`ocr/test_region.py` |
| —（引擎行為） | sheet→TSV→匯入迴圈、glossary | `ocr/test_sheets.py` |
| subtitle-text-source | 圖條ê欄裁切：背景ê墨水對畫面另外彼爿用細空隙連過來／頂一逝ê字滲入圖條ê頂墘（111 cue 228「任何墨水」是 279..1725，字其實干焦佇 799..1295）／族語逝結尾ê撇號一欄才一兩个畫素，一定愛留（「逐欄墨水 ≥3」彼版kā 085 四十逝ê撇號削去） | `ocr/test_sheets.py`（`TestInkColumns`）|
| subtitle-text-source | 組合圖ê尺寸：一條滿版圖條kā規集 327 張攏撐做 2044 闊／閣加一條就超過 ⌈闊/28⌉×⌈懸/28⌉ ≤ 4784 抑是長邊 2000（超過送圖彼端會恬恬kā規張縮細）／一條圖條家己就超過上限嘛袂使hőng放揀／照闊度排了後 `sheets.json` ê cue 集合愛佮 `cues.json` 完全仝款、編號佮圖條袂使拆散／檔名取彼張上早ê彼條 cue／整條發亮ê圖條（滿版圖卡、報紙翻拍）會做出 2044 闊、超過送圖彼端ê 2000，愛佇**算 ink 進前**對倒手爿剪——算煞才夾，倒手爿彼團亮背景會贏去「墨水上濟彼團」kā裁切帶走；空白圖條無墨水通裁，嘛愛套仝一个上限 | `ocr/test_sheets.py`（`TestSheetWidth`、`TestSheetHeight`、`TestWidthSorting`）|
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
| subtitle-text-source | 交付 TSV 照 cue 編號排序：組合圖照闊度排了後，讀者是照 703、612、699 這款順序寫落來ê，落 store 愛遞增；仝一條 cue ê兩逝（族語佇頂、華語佇下）袂使對調；`12` 袂使排佇 `9`頭前 | `news/test_ingest.py` |
| —（工作流防線） | 組合圖ê懸度上限釘佇辨識端ê解析層佮送圖工具ê長邊 2000（2044 闊 → 1820 懸、一張 13 條）：版型變懸、換模型、抑是換送圖ê工具就紅——超過干焦是圖hőng縮細、字綴咧細，無一个所在會報錯（實測 818x2484 送過去，家己註「displayed at 659x2000」）| `news/test_sheet_packing.py` |
| —（工作流防線） | 批次邊界兩支工具愛講仝款ê話：`batches` 發 TSV ê名（b01、b02…）、`prompt` 照彼个號碼寫提示，51 張ê時遮切三批、彼切兩批，**仝一批 cue hőng派兩擺、掛兩个名**，`ingest` 擋規集（「cue X 佇兩个檔攏有」）；批次對 24 張改做 4 張了後，尾批短ê情形變做常態 | `news/test_batches.py`、`news/test_vision_prompt.py` |
| —（成本防線） | 批次大小綴組合圖打包走：一張對 4 條變 ~25 條，`SIZE` 若留咧 24 就是 600 條／批（量著會噴彼點 196 ê三倍），改 4 張才閣是 ~100 條；`brief.md` ê `{…}` 鍵無換掉會直接印佇讀者面頭前，袂報錯 | `news/test_vision_prompt.py` |
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
| cue-timing | 守門ê離開碼分三路——通過 0、版型不符 1、無帶 2，批次流程才分會清；`--band-json` 寫出帶範圍、槽、分數佮問題清單 | `aiyalaeho/test_verify_band.py` |
| aiyalaeho-sourcing | 版型異常集分流，理由三路來源（檔名ê字幕狀態字樣／量測／人工判定）；`--annotate` 干焦填空ê理由佮影片長度、既有理由袂予蓋掉、無事做回「未改」 | `aiyalaeho/test_catalogue.py` |
| cue-timing | 0.5 秒留白、間距不足佇中點相接、袂出負值袂超片長、留白無寫轉去時間軸 | `aiyalaeho/test_make_srt.py` |
| subtitle-text-source | 每條恆兩行帶標籤「族語：／華語：」；某列空白猶原出標籤行；兩列攏空無出；合併比兩行合成ê字串 | `aiyalaeho/test_make_srt.py` |
| aiyalaeho-language-check | 逐條語言判定ê規組（字元分類、辭典蒸餾、詞庫比對、方言別正音、兩張 CSV）——27 逝ê對照表佇 `aiyalaeho/langcheck/README.md` | `aiyalaeho/langcheck/*.py` |
| subtitle-text-source | 兩逝一 cue ê TSV：列名毋著／cue 無佇 sheet 頂懸／仝一 cue 兩批攏有——規批拒收 | `aiyalaeho/test_ingest.py` |
| srt-data-store | store 版面（`aiyalaeho/1-ocr/{1-cues,2-vision,3-srt}`、不分層）；inventory 欄位宣告 | `aiyalaeho/test_paths.py` |
| —（成本防線） | preset ê列懸度愛予一張 sheet 囥會落四條 cue（1.10 MP 預算；超過就恬恬加三成閱讀量） | `aiyalaeho/test_paths.py` |
| srt-data-store | 進度表九欄佮順序；成果檔名＝srt_name；影片長度由時間軸推導；pending 不入定版表 | `aiyalaeho/test_tracker.py` |
| srt-data-store | 0-cue 集算校讀完成、以 0 行交付、袂擋整批；整批未完成一字都無寫 | `aiyalaeho/test_publish.py` |
| srt-data-store | 兩張表：正常集入 `smkul.csv`、版型異常集入 `smkul-字幕版型異常.csv`（十欄、逐逝理由非空、影片長度對 inventory 來）；異常集免校讀免時間軸嘛袂擋整批 | `aiyalaeho/test_tracker.py`、`aiyalaeho/test_publish.py` |
| srt-data-store | 干焦用 store 重建雙列 SRT＋smkul.csv 逐 byte；缺件指名；pending 跳過 | `aiyalaeho/test_rebuild.py` |
| srt-data-store | 重建同時比兩張表；異常集佇 `1-ocr/` 無檔嘛毋算缺件；無異常集ê時免第二張表 | `aiyalaeho/test_rebuild.py` |
| —（判讀工具） | 連通元件：8-連通標號、面積算墨毋是算外框、干焦頂端落佇族語槽內ê元件算數、面積 1 ê反鋸齒濾掉（濾面積毋是濾闊——真ê `l` 柱就是一畫素闊） | `aiyalaeho/test_blobs.py` |

**上字文稿平行語料**（`aiyalaeho-text-corpus`，`tests/aiyalaeho/text/` ↔ `scripts/aiyalaeho/text/`）：表放彼个子目錄家己ê `README.md`，無囥佇遮。

## 端對端（tests/e2e/）

| spec | scenario | 測試檔 |
|---|---|---|
| 全鏈 | 合成影片燒入已知 SRT → 跑真實 pipeline 抽回 → 逐 cue 比對時間與文字（時間數學唯一的外部對照；需 ffmpeg＋tesseract，`tox -e e2etest`） | `e2e/test_roundtrip.py`＋`e2e/fixture.py` |
