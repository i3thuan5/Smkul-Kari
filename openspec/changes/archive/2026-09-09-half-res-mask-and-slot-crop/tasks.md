## 1. 遮罩：解析度與比對範圍（`scripts/ocr/cuelib.py`）

- [x] 1.1 `tests/ocr/test_mask.py`（紅）：`frame_mask(rgb, spec)` 在 `scale=1` 且無 `compare_cols`／`compare_rows` 時與 `text_mask(rgb, spec)` **逐 bit 相同**（回歸錨點，本 change 最重要的一條）；`scale=2` 時合成字形仍抓得到、墨水約四分之一；`compare_cols`／`compare_rows` 給值時範圍外全 False、範圍內逐畫素同未裁
- [x] 1.2 `tests/ocr/test_mask.py`（紅）：`MaskSpec.scaled(2)` 把 `outline_size` 9→5、`thin_size`、`band_probe` 的 `x`／`w`、`band_rows`、`compare_cols`、`compare_rows` **全部同步減半**；漏縮 `band_probe` 會讓《開會了》在半解析下把帶偵測指到錯的欄、整集判成無帶；漏縮 `band_rows` 會裁到錯的列
- [x] 1.3 `tests/ocr/test_mask.py`（紅）：`MaskSpec` 的三個新欄位**不進** `to_dict()`／`from_dict()` 的鍵表（使用者裁定 manifest 不新增任何鍵）——用測試鎖住 `to_dict()` 的鍵集合，日後有人順手加進去會當場破；三個欄位改由建構參數帶入
- [x] 1.4 `scripts/ocr/cuelib.py`（綠）：`MaskSpec` 加 `scale`／`compare_cols`／`compare_rows`，新增 `scaled()` 與 `frame_mask()`；**`text_mask()` 本體與 `band_rows` 一行都不動**（見 design D1）

## 2. Segmenter：比對範圍只影響切點，不影響圖條

- [x] 2.1 `tests/ocr/test_segmenter.py`（紅）：同一串影格分別以「有比對範圍」與「無比對範圍」餵 `Segmenter`，兩者為同一條 cue 產生的 `composite()` **逐畫素相同**——比對範圍若誤套在 `Cue.samples` 上，圖條會只剩右邊那一塊，Claude Vision 讀不到左半句
- [x] 2.2 `tests/ocr/test_segmenter.py`（紅）：墨水全部落在比對範圍之外時不產生 cue（漏切的機制，明確鎖住而不是未載明的副作用）；靠一側對齊的合成字幕在另一側有雜訊變動時，同一句不再被切成多條
- [x] 2.3 `scripts/ocr/cli.py`（綠）：`_feed_frames` 改呼叫 `frame_mask`；確認 `Segmenter` 收到的是裁過的遮罩、`add_sample` 收到的仍是原始 RGB

## 3. CLI 參數（manifest 不新增任何鍵）

- [x] 3.1 `tests/ocr/test_auto_options.py`＋`tests/ocr/test_presets.py`（紅）：`cues` 新增 `--mask-scale`（**預設 None＝照 preset 宣告**，見 design D11），`auto` 也收得到並傳得下去（既有的結構把關會在此破）；preset 的 `mask.compare_cols`／`compare_rows` 與 `sheet.row_slots` 讀得進來、組成 `MaskSpec` 與 `build_sheets` 的參數；preset 沒有這些鍵時對應值為 `None`（＝現行行為）
- [x] 3.2 `tests/ocr/test_presets.py`（紅）：`--min-ink` 的值意義固定是「全帶、全解析下的墨水畫素數」（預設仍 120），程式依 `scale` 與比對範圍面積換算後才餵 `Segmenter`；`segmenter.min_ink` 這個既有的 manifest 鍵**仍記換算前的值**，語意不變
- [x] 3.3 `scripts/ocr/cli.py`（綠）：新參數、換算、把 preset 的 `row_slots` 傳給 `build_sheets`；**manifest 一個新鍵都不寫**，寫出來的 `cues.json` 與改動前的鍵集合完全相同。**動手前重讀本檔**——`parallel-corpus-quality` 改過這支的 `json.dump`，不要蓋掉

## 4. 精修沿用同一組參數

- [x] 4.1 `tests/news/test_refine.py`（紅）：`refine_cues` 新增 `--preset`／`--presets`，從 preset 取得 `scale` 與 `compare_*`，窗內遮罩用與切 cue 相同的參數；**未指定 preset 時以 `PipelineError` 中止並指名**，不靜默退回全解析全帶（靜默用不同判準會讓粗切與精修不一致而無人察覺）；preset 沒有這些鍵時（《開會了》）行為與現行逐畫素相同
- [x] 4.2 `scripts/news/refine_cues.py`（綠）：加 `--preset`／`--presets`；窗內遮罩改呼叫 `frame_mask`。**動手前重讀本檔**（同 3.3 的理由）
- [x] 4.3 兩個語料呼叫 `refine_cues` 的地方都補上 preset：`scripts/news/fetch_sftp.sh`（本來就握有 `$PRESET`／`$PRESETS`）、`scripts/aiyalaeho/README.md` 第 55 行那條指令、以及 `kithann/out/aiyalaeho/batch_cut.sh`（工作區腳本，順手告知《開會了》那條線）。**漏掉《開會了》這邊，它的精修會拒跑**

## 5. `verify_band` 的欄剖面把關

- [x] 5.1 `tests/news/test_verify_band.py`（紅）：合成剖面，墨水集中在某個右緣 → 右崖算在那裡；右緣左移 → 右崖跟著移；偏離 preset 宣告值超過容許量 → 回報問題、離開碼非零；**通過與否都要在輸出印出量到的右崖與容許量**（靜默通過的把關等於沒有把關）
- [x] 5.2 `tests/news/test_verify_band.py`（紅）：把關**不可以**用「比對範圍內墨水佔全體的比例」當判準——用合成資料鎖住這一點，正常與異常版型在那個比例上重疊（實測 53%／69%／62% 對 58%）
- [x] 5.3 `scripts/news/verify_band.py`（綠）：`profile()` 在**同一個解碼迴圈**裡多算欄剖面（不另外解碼）；新增右崖判定（24 px 平滑、峰值 25% 門檻、取最右邊仍在門檻上的欄）；`judge()` 多一條規矩；輸出加一行

## 6. 字幕上下位置判斷法（`scripts/ocr/sheets.py`）

- [x] 6.1 `tests/ocr/test_sheets.py`（紅）：`build_sheets` 收 `row_slots` 參數（由呼叫端從 preset 取得，不從 manifest 讀）；墨水只在偏上 → 裁到分界列＋pad；只在偏下 → 裁到分界列−pad 以下；兩位比值 < 2.0 → **退回全高**；範圍內墨水太少 → 退回全高；`row_slots` 為 `None`（《開會了》）→ 一律不裁，與現行逐畫素相同
- [x] 6.2 `tests/ocr/test_sheets.py`（紅）：判上下位用的墨水是在 preset 宣告的 `compare_cols` 欄範圍內量的，不是全寬——用全寬量時亮背景會把比值壓到 2.0 邊緣，該裁的沒裁（實測 032午 有 186 條這樣）
- [x] 6.3 `tests/ocr/test_sheets.py`（紅）：欄方向仍走 `ink_bbox`（任何墨水都保留＋pad），不因本條改變；裁切後字幕畫素一個都沒少
- [x] 6.4 `tests/ocr/test_sheets.py`（紅）：`build_sheets` 回報該集「判不出來（退回全高）」的圖條比率，排除純空白的圖條後計算
- [x] 6.5 `scripts/ocr/sheets.py`（綠）：`build_sheets` 收 `row_slots`，`_cue_blocks` 據此判上下位裁列、回報比率。**動手前重讀本檔**（同 3.3 的理由）
- [x] 6.6 `news/gap_sheets.py` 與 `news/rescan_band.py`（兩支都是新聞專用）直接讀 `scripts/news/presets.json` 的 `titv-news` 取得 `row_slots` 傳進 `build_sheets`，**呼叫端不必改**；留一個 `--preset` 可覆寫。測試要鎖住「重建出來的圖與 `cues --sheets` 首輪產生的逐畫素相同」，不然重建的圖和原本的不一樣而沒有人會發現

## 7. preset

- [x] 7.1 `scripts/news/presets.json`：`titv-news` 與 `amis-titv-news` 加 `mask.scale: 2`、`mask.compare_cols: [1250, 1790]`、`mask.compare_rows: [4, 114]`、`sheet.row_slots: {split: 65, pad: 6, min_ratio: 2.0}`；`note` 補一句這些值的量測來源
- [x] 7.2 `scripts/aiyalaeho/presets.json`：兩個 preset 只加 `mask.scale: 2`，**不加** `compare_*` 與 `row_slots`（見 design D5）
- [x] 7.3 `tests/ocr/test_presets.py`（綠）：兩份 preset 的新鍵讀得進來、《開會了》缺鍵時走不裁的路

## 8. Claude Vision 批次大小

- [x] 8.1 `tests/news/test_vision_prompt.py`（紅）：`plan()` 預設 `SIZE` 24、`MIN_TAIL` 8；**更正**：MIN_TAIL 是模組常數不是參數，連寫死 `size=72` 的既有測試也會跟著變，兩條要一起更新；`MIN_TAIL` 若沒跟著降，尾批會被併成 47 張——用一個具體張數的案例鎖住
- [x] 8.2 `scripts/news/vision_tools/prompt.py`（綠）：`SIZE` 72→24、`MIN_TAIL` 24→8

## 9. 離線評分工具 `tools/cuescore/`

- [x] 9.1 `tests/tools/test_cuescore.py`（紅，含 `tests/tools/__init__.py`）：用合成的 cues 與 vision TSV 測三個指標的算術——**重覆對**（相鄰相接且文字相同的 cue 對）、**吞句**（正解的換句時刻被一條新 cue 吞掉）、**漏切**（正解裡有字的 cue 沒有任何新 cue 覆蓋）；邊界情形：時間剛好相接與差 0.01 秒、空字串的 cue 不計入、雙列語料的兩列文字合併後才比
- [x] 9.2 `tools/cuescore/`（綠）：`__init__.py`、`score.py`（吃 `cues.json` 與 vision TSV 目錄，印三個指標；不讀影片）
- [x] 9.3 `tools/cuescore/README.md`：三個指標的定義、怎麼跑、數字怎麼讀；寫明它跑真資料所以不在 `tests/`
- [x] 9.4 `tests/tools/README.md`：本目錄的 spec × scenario 表；`tests/README.md` 總表加一行指過去

## 10. 驗收

- [x] 10.1 `.tox/unittest/bin/python -m unittest discover -s tests/ocr -t .`、`-s tests/news`、`-s tests/tools` 全綠
- [x] 10.2 `.tox/flake8/bin/flake8 . --count` 為 0
- [x] 10.3 `rebuild --verify` 逐 byte 通過（它不重切，所以結果應與改動前完全相同——若有差異就是改到不該改的地方）；`python3 -m scripts.news.name_catalogue --check` 通過
- [x] 10.3b 切一集確認 `cues.json` 的鍵集合與改動前相同（manifest 沒有長大）
- [x] 10.4 用 `tools/cuescore` 對 032午、041午、051晚、046晚 四集重算，數字要對得上 design〈Context〉那兩張表（重覆對 268→103、70→22、370→128、48→27；吞句 37→31、9→8、87→43、0→1）。對不上就是實作和實驗不一致，先找原因再往下
- [x] 10.5 對其中一集實跑 `verify_band`，確認欄剖面把關印出量到的右崖；對 046晚 確認它的右崖是 1640、與 preset 的差在容許量內或依設定拒切

## 11. 文件

- [x] 11.1 `scripts/news/README.md`：新增一節記量測與判準——右緣 1735–1737（27 集）、字幕垂直落點 90.6% 落在其中一位、`text_mask` 每格 17.62→1.08 ms、四集切割品質；比值 2.0 的理由要寫成「防畫面裡的字和字幕搶同一條圖條」（實例：051 cue 223 的紅布條、全螢幕法規圖卡、報紙翻拍），**不要寫成「兩位都有字」**
- [x] 11.2 `scripts/README.md`：`cues`／`refine_cues`／`gap_sheets`／`rescan_band` 的新參數；`tools/cuescore/` 一行。**動手前重讀**——另外兩條線也在加行，只加自己的
- [x] 11.3 `.claude/commands/smkul-news.md`：批次大小 72→24；`verify_band` 多一道欄方向把關
- [x] 11.4 `scripts/news/README.md` 另記「參數住哪裡」的分界原則：**量測來的（逐集不同、無處可存）記進 manifest（`band_rows` 屬於這類）；宣告來的（版型固定、preset 是正本）留在 preset**——寫清楚免得日後有人把它們「統一」搬回 manifest
- [x] 11.5 用詞照 CLAUDE.md〈用詞：影像側幾個東西的正式名稱〉：組合圖、Claude Vision、字幕上下位置判斷法、置右字幕比對遮罩、把關
