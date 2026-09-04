## 1. 引擎：切 cue 的遮罩裁到帶上（`scripts/ocr/`；news 逐畫素不變）

- [ ] 1.1 `tests/ocr/test_cuelib_band_rows.py`（紅）：合成一格 RGB，`band_rows=None` 時 `text_mask` 輸出與現行逐畫素相同；給 `(lo, hi)` 時範圍外每一列全 False、範圍內逐畫素同未裁；`MaskSpec.from_dict`／`to_dict` 帶著 `band_rows` 來回；舊 manifest 的 `mask`（無此鍵）載入後為 `None`
- [ ] 1.2 `scripts/ocr/cuelib.py`（綠）：`MaskSpec.band_rows`（預設 `None`）、`text_mask` 末尾裁列、`from_dict`／`to_dict` 兩個鍵表各加一項
- [ ] 1.3 `tests/ocr/`（紅）：`cues --band-rows LO,HI` 以絕對列傳入，寫進 manifest `mask.band_rows` 的是 region 內偏移（含 `normalize_region` 對齊後仍正確）；未傳時 manifest 沒有該鍵或為 `None`；格式錯誤以 `PipelineError` 拒絕
- [ ] 1.4 `scripts/ocr/cli.py`（綠）：`cues` 加 `--band-rows`，轉偏移後設進 spec，其餘不動
- [ ] 1.5 驗收：`tests/ocr` 全綠；news 的 `rebuild --verify` 照樣通過（引擎行為未變的證明）

## 2. paths：欄位與路徑

- [ ] 2.1 `tests/aiyalaeho/test_paths.py`（紅）：`INVENTORY_FIELDS` 尾端依序是「理由」「影片長度」且兩者皆在 `INVENTORY_OPTIONAL`；`load_inventory` 對帶這兩欄的條目照收、對缺這兩欄的舊條目照收；`ABNORMAL_STORE`＝`Kari-SRT/aiyalaeho/smkul-字幕版型異常.csv`、`ABNORMAL_CACHE` 在工作區；`band_json(work)` 指向 `<work>/band.json`
- [ ] 2.2 `scripts/aiyalaeho/paths.py`（綠）

## 3. catalogue：理由、影片長度、補註

- [ ] 3.1 `tests/aiyalaeho/test_catalogue.py`（紅）：`parse` 對 `-無字幕`、`-僅華語字幕` 記理由、對 `-雙語字幕（講中文居多）` 留空、括號內容不入任何欄；有理由時呼叫時長探測（mock）並記影片長度，無理由時不探測；`annotate(entries, ...)` 只填空的理由與長度、其他欄位與條目順序逐字不變、無事可做回「未改」且不寫檔；`annotate` 指名 `<srt_name>=<理由>` 會寫入並探測長度、空理由以 `PipelineError` 拒絕、既有非空理由不被覆蓋並回報；CLI `--annotate` 印出改了哪幾筆哪幾欄
- [ ] 3.2 `scripts/aiyalaeho/catalogue.py`（綠）：`_variety_after` 順手回傳字幕狀態 token；`parse` 帶兩欄；`annotate()`；時長用函式內 `from scripts.news.refine_cues import probe_duration`；`main` 加 `--annotate`（無參數＝補全部；`'<srt_name>=<理由>'`＝指名）

## 4. verify_band：守門、離開碼、帶範圍輸出

- [ ] 4.1 `tests/aiyalaeho/test_verify_band.py`（紅）：`verdict(..., band=(924, 1014))` 對標準槽 → `mismatch`，問題文字含族語槽範圍與帶範圍；`band=(876, 1014)` 或省略 → 既有 12 個 verdict 案例逐一照舊；`SLOT_ON_BAND == 0.9`；`main` 對 ok／mismatch／no-band 分別回 0／1／2（以 mock 的 `check` 驅動）；no-band 訊息含「記做無字幕」、mismatch 訊息含「換低版 preset」；`--band-json` 寫出的 JSON 含 `band`、`state`、`slots`、`score`、`problems`；`test_one_row_only_passes` 的註解改成只講 164
- [ ] 4.2 `scripts/aiyalaeho/verify_band.py`（綠）：`verdict` 加 `band=None` 與槽覆蓋率檢查；`check` 把帶範圍傳給 `verdict`；`main` 離開碼與訊息；`--band-json`
- [ ] 4.3 活體驗證並記進 README：對 083 母帶跑 `verify_band` 得 MISMATCH 且指名族語槽底下無帶；對 088 跑得離開碼 2；對 087 用標準 preset 得 1、用低版 preset 得 0（SOP 的「先換 preset」有例可循）；對任一雙語集（如 068）跑仍 OK 且 `band.json` 的帶＝整個 region

## 5. tracker：兩張表

- [ ] 5.1 `tests/aiyalaeho/test_tracker.py`（紅）：`is_abnormal` 對理由非空為真、空或缺欄為假；`ABNORMAL_FIELDS`＝`FIELDS` 加「理由」；`tracker_rows` 排除有理由者；`abnormal_rows` 只含有理由且非 pending 者、十欄、理由值照 inventory、成果檔名＝`srt_name`、影片長度由 inventory 的秒數格式化成與 `video_length` 相同的 時:分:秒；`include_pending=True` 的快取版含 pending 者；`write_tracker(rows, path, fields)` 可寫十欄
- [ ] 5.2 `scripts/aiyalaeho/tracker.py`（綠）

## 6. make_all／publish／rebuild

- [ ] 6.1 `tests/aiyalaeho/test_publish.py`（紅）：fixture `add(..., reason="")` 可帶理由與長度；`make_one` 對有理由者回「字幕版型異常（列於 smkul-字幕版型異常.csv）」且不寫 SRT；`make_all` 寫兩張快取表；`publish` 對有理由者不問 `vision_complete`、不遷時間軸、pending 被清、兩張表落 store、有理由者不出現在 `smkul.csv`；`--check` 與定版報告逐集列理由並標出非檔名來源者（理由 `無字幕` 而檔名字樣不是、或以 `版型不符：`／`人工判定：` 起頭）；既有 `test_a_no_subtitle_episode_delivers_an_empty_srt`、`test_a_no_subtitle_episode_does_not_block_the_batch` 改寫成理由版；`test_an_episode_with_no_cues_is_complete` 保留
- [ ] 6.2 `scripts/aiyalaeho/make_all.py`＋`publish.py`（綠）
- [ ] 6.3 `tests/aiyalaeho/test_rebuild.py`（紅）：有理由者在 `1-ocr/` 沒有任何檔時 `check_inputs` 不報缺件；`verify` 同時比對 `smkul.csv` 與 `smkul-字幕版型異常.csv`，第二張被改動時報 `DIFFERS: smkul-字幕版型異常.csv`；有非 pending 理由者而 store 缺第二張表時報 MISSING；沒有理由者時不要求第二張表；既有 `test_an_episode_with_no_subtitles_rebuilds_as_an_empty_srt` 改寫成理由版
- [ ] 6.4 `scripts/aiyalaeho/rebuild.py`（綠）
- [ ] 6.5 驗收：`.tox/unittest/bin/python -m unittest discover -s tests/ocr -t .` 與 `-s tests/aiyalaeho` 全綠；`.tox/flake8/bin/flake8 . --count` 為 0

## 7. 資料遷移（順序要緊：先補註、再刪檔、再驗）

- [ ] 7.1 `python3 -m scripts.aiyalaeho.catalogue --annotate`：083（`僅華語字幕`）／088／090／098（`無字幕`）四筆得理由與影片長度；`git -C Kari-SRT diff aiyalaeho/inventory.json` 只有那幾個位置有差
- [ ] 7.2 `rebuild --verify`：對 083 不再要求輸入，其餘照舊通過（此時 store 還沒有第二張表，且 083 仍 pending，所以不要求它）
- [ ] 7.3 用 `git -C Kari-SRT ls-files aiyalaeho/1-ocr | grep 083` 列出 083 的 19 個檔，逐一 `rm`；`rm -r openspec/changes/half-res-mask-and-slot-crop/`；`rebuild --verify` 全綠；`git status` 與 `git -C Kari-SRT status` 列給使用者 `git add`
- [ ] 7.4 `scripts/aiyalaeho/README.md`：判定表 098 改 MISMATCH 並寫明「檔名與量測各是什麼、為什麼兩者都指向無字幕」；素材分類把 083 移入字幕版型異常組（現為 4 集，116 下載後 5 集）

## 8. 伺服器三支（116、119、122）

- [ ] 8.1 用 `scripts/news/sftp.sh get` 下載三支到 `kithann/開會了/`，比位元組數；憑證照 CLAUDE.md 規定只走檔案路徑，不出現在指令列
- [ ] 8.2 人看過影片後以 `catalogue --language <檔名>=<族語別中>` 登記；`116ALL_無字` 登記時理由即為 `無字幕`（第五筆異常集）
- [ ] 8.3 119／122 走完整 SOP：`verify_band --band-json`；回 1 換 `--preset aiyalaeho-bilingual-low` 再量，仍 1 → `catalogue --annotate '<name>=版型不符：<band.json 第一行問題>'`；回 2 → `'<name>=無字幕'`；回 0 → `cues --band-rows` → `refine`，切完看 sheet_001，判異常 → `'<name>=人工判定：<一句所見>'`。任何一關判異常就記理由、不問使用者

## 9. 本機 16 集：守門補跑與視覺辨識（`/loop 20m` 推進）

- [ ] 9.1 對 106、107、108、109、110、111、112、113、114、115、117、118、120、121、123、164 逐集跑 `verify_band --band-json`（已切好、精修過，不重切）：回 0 照舊；回 1 換低版 preset 再量，仍 1 → 記 `版型不符：…` 分流；回 2 → 記 `無字幕` 分流；分流者不派讀者
- [ ] 9.2 以 `/loop 20m` 持續檢查：對已切完且無 TSV 的雙語集逐集派 7 批左右的讀者（model opus、判準 `scripts/aiyalaeho/brief.md`、TSV 寫進 `Kari-SRT/aiyalaeho/1-ocr/2-vision/<srt_name>/bNN.tsv`）；派工前先 `ls` 確認前一集檔案都在，重派時給不同的輸出檔名與 scratchpad；額度用完就停下來等，做到一個段落就回報
- [ ] 9.3 108／111 派工提示明寫：頂列夾漢字整行進 `formosan`，不把漢字搬去 `han`
- [ ] 9.4 每集七批 TSV 落地並覆核後：ingest 前照例做編號連續與重複稽核，`ingest` → `make_all <srt_name>`；每集交付後掃一次全語料碼位（README 的例行動作）

## 10. 整批定版與總驗收

- [ ] 10.1 `make_all`（全部）：報告段逐集列異常集理由並標出非檔名來源者
- [ ] 10.2 `publish --check` 通過後 `publish`：inventory 不再有 pending；store 有 `smkul.csv` 與 `smkul-字幕版型異常.csv`；兩表無重複 `srt_name`，列數相加＝inventory 筆數；另表每列理由非空
- [ ] 10.3 aiyalaeho `rebuild --verify`：全部交付 SRT 與兩張表逐 byte 相同
- [ ] 10.4 總驗收：`tox -e unittest`、`tox -e flake8`、news 的 `rebuild --verify` 與 `name_catalogue --check`
- [ ] 10.5 文件：`tests/README.md`（spec × scenario 表：cue-timing 加守門與遮罩裁帶、srt-data-store 加另表、aiyalaeho-sourcing 加分流與三路理由）、`Kari-SRT/README.md`（樹加 `smkul-字幕版型異常.csv`）、`Kari-SRT/aiyalaeho/1-ocr/README.md`（重建及於兩張表）、`scripts/README.md`（`cues --band-rows`）、`scripts/aiyalaeho/README.md`（SOP 一條指令串：`verify_band --band-json` → 依離開碼分支 → `cues --band-rows` → `refine` → 看 sheet_001；兩張表說明；報告怎麼看；人工判定的理由怎麼寫）
- [ ] 10.6 收尾回覆檔到 `kithann/tuiue/`：交付集數與行數、兩張表列數、異常集清單附理由與來源、待使用者 `git add` 的檔案清單
