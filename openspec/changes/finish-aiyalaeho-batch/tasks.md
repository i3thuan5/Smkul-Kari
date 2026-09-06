## 1. 引擎：切 cue 的遮罩裁到帶上（`scripts/ocr/`；news 逐畫素不變）

- [x] 1.1 `tests/ocr/test_cuelib_band_rows.py`（紅）：合成一格 RGB，`band_rows=None` 時 `text_mask` 輸出與現行逐畫素相同；給 `(lo, hi)` 時範圍外每一列全 False、範圍內逐畫素同未裁；`MaskSpec.from_dict`／`to_dict` 帶著 `band_rows` 來回；舊 manifest 的 `mask`（無此鍵）載入後為 `None`
- [x] 1.2 `scripts/ocr/cuelib.py`（綠）：`MaskSpec.band_rows`（預設 `None`）、`text_mask` 末尾裁列、`from_dict`／`to_dict` 兩個鍵表各加一項
- [x] 1.3 `tests/ocr/`（紅）：`cues --band-rows LO,HI` 以絕對列傳入，寫進 manifest `mask.band_rows` 的是 region 內偏移（含 `normalize_region` 對齊後仍正確）；未傳時 manifest 沒有該鍵或為 `None`；格式錯誤以 `PipelineError` 拒絕
- [x] 1.4 `scripts/ocr/cli.py`（綠）：`cues` 加 `--band-rows`，轉偏移後設進 spec。**動手前重讀檔案**——`parallel-corpus-quality` 已把這支的兩處 `json.dump` 改成 `indent=2, sort_keys=True`（2026-09-05 確認落地），**不重複改**；做完通知那條線與 `half-res-mask-and-slot-crop`（後者的程式改動排在本項之後）
- [x] 1.4b 確認 `scripts/ocr/transcripts.py` 的兩處 `json.dump` 已是 `indent=2, sort_keys=True`（由 `parallel-corpus-quality` 改完），本 change 不動這支
- [x] 1.5 驗收：`tests/ocr` 全綠；news 的 `rebuild --verify` 照樣通過（引擎行為未變的證明）——**另一條線在改的時候用 `/loop 20m` 等他，不硬跑**（他們 1.3 到 4.3 之間 news verify 本來就會紅，見 design D14）

## 2. paths：欄位與路徑

- [x] 2.1 `tests/aiyalaeho/test_paths.py`（紅）：`INVENTORY_FIELDS` 尾端依序是「理由」「影片長度秒」且兩者皆在 `INVENTORY_OPTIONAL`；`load_inventory` 對帶這兩欄的條目照收、對缺這兩欄的舊條目照收；`ABNORMAL_STORE`＝`Kari-SRT/aiyalaeho/smkul-字幕版型異常.csv`、`ABNORMAL_CACHE` 在工作區；`band_json(srt_name)` 指向 `<work_dir>/band.json` 且會檢查名字
- [x] 2.2 `scripts/aiyalaeho/paths.py`（綠）

## 3. catalogue：理由、影片長度、補註

- [x] 3.1 `tests/aiyalaeho/test_catalogue.py`（紅）：`parse` 對 `-無字幕`、`-僅華語字幕` 記理由、對 `-雙語字幕（講中文居多）` 留空、括號內容不入任何欄；有理由時呼叫時長探測（mock）並記影片長度，無理由時不探測；`annotate(entries, ...)` 只填空的理由與長度、其他欄位與條目順序逐字不變、無事可做回「未改」且不寫檔；`annotate` 指名 `<srt_name>=<理由>` 會寫入並探測長度、空理由以 `PipelineError` 拒絕、既有非空理由不被覆蓋並回報；CLI `--annotate` 印出改了哪幾筆哪幾欄
- [x] 3.2 `scripts/aiyalaeho/catalogue.py`（綠）：`_variety_after` 順手回傳字幕狀態 token；`parse` 帶兩欄；`annotate()`；時長用函式內 `from scripts.news.refine_cues import probe_duration`；`main` 加 `--annotate`（無參數＝補全部；`'<srt_name>=<理由>'`＝指名）

## 4. verify_band：守門、離開碼、帶範圍輸出

- [x] 4.1 `tests/aiyalaeho/test_verify_band.py`（紅）：`verdict(..., band=(924, 1014))` 對標準槽 → `mismatch`，問題文字含族語槽範圍與帶範圍；`band=(876, 1014)` 或省略 → 既有 12 個 verdict 案例逐一照舊；`SLOT_ON_BAND == 0.9`；`main` 對 ok／mismatch／no-band 分別回 0／1／2（以 mock 的 `check` 驅動）；no-band 訊息含「記做無字幕」、mismatch 訊息含「換低版 preset」；`--band-json` 寫出的 JSON 含 `band`、`state`、`slots`、`score`、`problems`；`test_one_row_only_passes` 的註解改成只講 164
- [x] 4.2 `scripts/aiyalaeho/verify_band.py`（綠）：`verdict` 加 `band=None` 與槽覆蓋率檢查；`check` 把帶範圍傳給 `verdict`；`main` 離開碼與訊息；`--band-json`
- [x] 4.3 活體驗證並記進 README：對 083 母帶跑 `verify_band` 得 MISMATCH 且指名族語槽底下無帶；對 088 跑得離開碼 2；對 087 用標準 preset 得 1、用低版 preset 得 0（SOP 的「先換 preset」有例可循）；對任一雙語集（如 068）跑仍 OK 且 `band.json` 的帶＝整個 region

## 5. tracker：兩張表

- [x] 5.1 `tests/aiyalaeho/test_tracker.py`（紅）：`is_abnormal` 對理由非空為真、空或缺欄為假；`ABNORMAL_FIELDS`＝`FIELDS` 加「理由」；`tracker_rows` 排除有理由者；`abnormal_rows` 只含有理由且非 pending 者、十欄、理由值照 inventory、成果檔名＝`srt_name`、影片長度由 inventory 的秒數格式化成與 `video_length` 相同的 時:分:秒；`include_pending=True` 的快取版含 pending 者；`write_tracker(rows, path, fields)` 可寫十欄
- [x] 5.2 `scripts/aiyalaeho/tracker.py`（綠）

## 6. make_all／publish／rebuild

- [x] 6.1 `tests/aiyalaeho/test_publish.py`（紅）：fixture `add(..., reason="")` 可帶理由與長度；`make_one` 對有理由者回「字幕版型異常（列於 smkul-字幕版型異常.csv）」且不寫 SRT；`make_all` 寫兩張快取表；`publish` 對有理由者不問 `vision_complete`、不遷時間軸、pending 被清、兩張表落 store、有理由者不出現在 `smkul.csv`；`--check` 與定版報告逐集列理由並標出非檔名來源者（理由 `無字幕` 而檔名字樣不是、或以 `版型不符：`／`人工判定：` 起頭）；既有 `test_a_no_subtitle_episode_delivers_an_empty_srt`、`test_a_no_subtitle_episode_does_not_block_the_batch` 改寫成理由版；`test_an_episode_with_no_cues_is_complete` 保留
- [x] 6.2 `scripts/aiyalaeho/make_all.py`＋`publish.py`（綠）
- [x] 6.3 `tests/aiyalaeho/test_rebuild.py`（紅）：有理由者在 `1-ocr/` 沒有任何檔時 `check_inputs` 不報缺件；`verify` 同時比對 `smkul.csv` 與 `smkul-字幕版型異常.csv`，第二張被改動時報 `DIFFERS: smkul-字幕版型異常.csv`；有非 pending 理由者而 store 缺第二張表時報 MISSING；沒有理由者時不要求第二張表；既有 `test_an_episode_with_no_subtitles_rebuilds_as_an_empty_srt` 改寫成理由版
- [x] 6.4 `scripts/aiyalaeho/rebuild.py`（綠）
- [x] 6.5a `tests/aiyalaeho/test_publish.py`＋`test_catalogue.py`（紅）：`publish_one` 寫進 store 的 `1-cues/<name>.json` 是 `indent=2, sort_keys=True, ensure_ascii=False` 的排版（不是工作目錄檔的逐 byte 複本），內容相等；`catalogue.write` 與 `publish.clear_pending` 寫出的 inventory 鍵排序、中文不轉義；對已定版的集重跑 `publish` 不改動 store 內既有 `1-cues` 檔的 byte
- [x] 6.5b `publish.py`＋`catalogue.py`＋`make_srt.py`＋`make_all.py`（綠）：`publish_one` 讀 JSON 再 dump、不 `copy2`；`scripts/aiyalaeho/` 全部 `json.dump` 一律 `ensure_ascii=False, indent=2, sort_keys=True`（使用者裁定：照另一條線的規格；也避免和 `redump_store` 來回翻，見 design D14）
- [ ] 6.6 驗收：`.tox/unittest/bin/python -m unittest discover -s tests/ocr -t .` 與 `-s tests/aiyalaeho` 全綠；`.tox/flake8/bin/flake8 . --count` 為 0

## 7. 資料遷移（順序要緊：先補註、再刪檔、再驗）

- [x] 7.1 `python3 -m scripts.aiyalaeho.catalogue --annotate`：083（`僅華語字幕`）／088／090／098（`無字幕`）四筆得理由與影片長度；`git -C Kari-SRT diff aiyalaeho/inventory.json` 只有那幾個位置有差
- [x] 7.2 `rebuild --verify`：對 083 不再要求輸入，其餘照舊通過（此時 store 還沒有第二張表，且 083 仍 pending，所以不要求它）
- [x] 7.3 用 `git -C Kari-SRT ls-files aiyalaeho/1-ocr | grep 083` 列出 083 的 19 個檔，逐一 `rm`；`rebuild --verify` 全綠；`git status` 與 `git -C Kari-SRT status` 列給使用者 `git add`。**`openspec/changes/half-res-mask-and-slot-crop/` 不刪**——那條線正在寫 artifact（2026-09-05 更正）
- [x] 7.4 `scripts/aiyalaeho/README.md`：判定表 098 改 MISMATCH 並寫明「檔名與量測各是什麼、為什麼兩者都指向無字幕」；素材分類把 083 移入字幕版型異常組（現為 4 集，116 下載後 5 集）

## 8. 伺服器三支（116、119、122）

**2026-09-06 使用者給了路徑，三支都在，不再擋。** 位置是 `scripts/news/sftp.sh` 的同一台（`ilrdf-corpus@192.168.35.10`）底下的 **`/docker/ilrdf-corpus/族語節目/開會了/`**——絕對路徑，不是 SFTP 相對根目錄；`fetch_sftp.sh` 的 `REMOTE_ROOT` 也正是 `/docker/ilrdf-corpus`。9/5 記「拿不到」是查錯層：只看了相對根目錄，那裡只有新聞的 `home/news/mkv/2021-02`。同一層另有 `族語節目/開會了_a_iyalaeho=上字文稿/`（文稿，本 change 不用）。

實地 `ls` 到的三支 mp4（同目錄還有各集的 mp3／wav，**不要下載**，本 change 只要影像）：

| 集 | 檔名 | 位元組數 |
|---|---|---|
| 116 | `116ALL_無字.mp4` | 1,628,016,459 |
| 119 | `119-混雜.mp4` | 2,086,465,217 |
| 122 | `122-混雜.mp4` | 1,696,929,267 |

**檔名的字幕狀態 token 和本機那批不一樣**：本機是 `-雙語字幕`／`-無字幕`／`-僅華語字幕`，這三支是 `_無字`（116）與 `-混雜`（119、122）。`catalogue._variety_after` 的 token 表要能認這兩個新樣態，否則 3.2 的「從檔名推導理由」對這三支會落空。`無字` 等同 `無字幕`；**`混雜` 是新類別，檔名本身不足以判定**，119／122 一律走 8.3 的量測與人工判定，不要只憑檔名記理由。

**⚠️ 這一組現在是第 10 組的前置條件。** 9/5 寫「不影響完成定義」是在三支拿不到的前提下才成立；**拿得到之後那句話變成陷阱**——116／119／122 沒進 inventory，第 8 組不做、第 10 組的「兩張表列數相加＝inventory 筆數」照樣會全綠，然後整批「定版」了卻少三集。所以第 8 組要排在第 10 組之前（8.2 一登記它們就進 inventory，10.2 的計數自然涵蓋），10.2 也加了前置條件那一句。

- [x] 8.1 用 `scripts/news/sftp.sh get /docker/ilrdf-corpus/族語節目/開會了/<檔名> kithann/開會了/<檔名>` 逐一下載上表三支，比位元組數（上表是 9/6 量的，下載前再 `ls` 一次核對）；憑證照 CLAUDE.md 規定只走檔案路徑，不出現在指令列。合計約 5.4 GB，逐支下載、下載完才做下一支
**2026-09-06 進展。** 語言別不必真的把影片看完：這個節目**每一集畫面右上角都有自己的語言卡**（台灣島形狀＋`a'iyalaeho:` 標題，底下一行族語拼寫、一行「〇〇族」）。拿兩支檔名已知語言的集數當對照組驗過——123 的卡是 `Truku 太魯閣族`、107 是 `Hla'alua 拉阿魯哇族`，都和檔名一致，所以這張卡就是在標語言。裁切位置是原始 1920×1080 的 `crop=340:260:1580:40`。

- **119、122 的卡都是 `Bunun 布農族`**，已用 `--language 119-混雜.mp4=布農 --language 122-混雜.mp4=布農` 登記，inventory 從 41 筆到 43 筆。122 那格還直接讀得到字幕帶的內容（族語列 `Uninang saikin hai Landuun isMahasan tainkasia isTanda`，華語列「大家好 我是倫敦 伊斯瑪哈善 母氏伊斯坦大」），是布農語無誤。檔名的「混雜」不是指版型，兩支的帶和上下兩列都在、都落在槽裡。
- **116 沒有語言卡，也沒有字幕。** 全片 2880 秒取樣 20 格掃過角標位置，從頭到尾都是空的；畫面是正常的棚內節目加視訊連線，只是乾淨母帶。同層的「上字文稿」目錄只到 045，是另一套編號，對不上 068–164，幫不了忙。**116 的族語別只能靠聽的，這一條卡在使用者。**

**8.2 現況：119／122 已登記（見上），只剩 116 卡在使用者。** 116 的族語別要聽過才知道——畫面上沒有語言卡（全片 2880 秒取樣 20 格，角標位置從頭到尾空的），也沒有字幕；伺服器同層的上字文稿目錄只到 045，是另一套編號，對不上。

- [ ] 8.2 人看過影片後以 `catalogue --language <檔名>=<族語別中>` 登記；`116ALL_無字` 登記時理由即為 `無字幕`（第五筆異常集）
**8.3 量測結果（2026-09-06）：兩支都在第一步就回 0**，不用換 preset、不用加長取樣。

| 集 | 帶色比 | 帶 y | 槽 | 字幕列 | 剖面對比 |
|---|---|---|---|---|---|
| 119 | 3.0 倍 | 882..1014 | 888..948、948..1012 | 918..943、967..1004 | 8.8 倍 |
| 122 | **1.2 倍** | 876..1014 | 888..948、948..1012 | 908..933、957..994 | 13.6 倍 |

**122 的帶色比 1.2 倍低於 1.5 的門檻，要留意。** 已知有帶的集數落在 2.0 到 22 倍、沒帶的落在 0.8 到 1.0 倍，1.2 掉在兩群之間。它判 OK 是因為兩列文字確實各自落在槽裡（帶色不是判準）。看畫面，122 的帶是偏亮的黃色而不是典型的黃到紅，紅≧綠≧藍那一關大概是勉強過的。切完看 sheet_001 要特別確認這一支。

**sheet_001 看過了（2026-09-06）：兩支都正常，都不是異常集。** 119 的第一張三條 cue 全是乾淨的雙列雙語，帶裁得準。122 的 cue 2、3 一樣乾淨；**cue 1 沒有字幕**（棚內鏡頭、帶上無字），那是畫面亮度觸發的空 cue，108 開頭兩條也是同一回事，讀者照規矩寫空白列即可，不算異常。

122 那個 1.2 倍的帶色比，看 sheet 就明白了：宣告的帶列 876..1014 含到帶以上的畫面列，所以「帶色」那一項被非帶的畫面稀釋。實際兩條字幕列（908..933、957..994）都在裡面，裁切完全正確。**帶色比低不等於帶不對**，這一次是量法的分母問題，不是版型問題。

**語言判定另有一個獨立佐證。** 119 的 cue 3 族語列是 `maza sia 'a'iyalaeho: an hai malis saysiat hailivhailiv tu halinga`、華語列是「`'a'iyalaeho:`是賽夏族的語言」——節目名本身是賽夏語詞，這一集是**用布農語在解釋節目名的來歷**。族語列的 `maza`／`sia`／`hai`／`tu halinga`／`uninang` 都是布農語。122 的 cue 2 是 `Uninang saikin hai Landuun isMahasan tainkasia isTanda`，`isTanda`（伊斯坦大）是布農氏族名。**語言卡和畫面上的族語內容兩邊獨立指向同一個答案。**

- [x] 8.3 119／122 走完整 SOP：`verify_band --band-json`；回 1 依序試低版 preset、`--duration 480`、兩者併用，任一回 0 就用那組參數切；四種都回 1 才 `catalogue --annotate '<name>=版型不符：<band.json 第一行問題>'`；回 2 → `'<name>=無字幕'`；回 0 → `cues --band-rows` → `refine`，切完看 sheet_001，判異常 → `'<name>=人工判定：<一句所見>'`。任何一關判異常就記理由、不問使用者

## 9. 本機 16 集：守門補跑與視覺辨識（`/loop 20m` 推進）

- [x] 9.1 對 106、107、108、109、110、111、112、113、114、115、117、118、120、121、123、164 逐集跑 `verify_band --band-json`（已切好、精修過，不重切）：回 0 照舊；回 1 依序試低版 preset、`--duration 480`、兩者併用（087 就是靠取樣加倍才分得開兩列），四種都回 1 才記 `版型不符：…` 分流；回 2 → 記 `無字幕` 分流；分流者不派讀者。**2026-09-05 結果：十六集全部回 0**（`preset=aiyalaeho-bilingual`、`duration=240`、帶＝876..1014 蓋滿 region），無一集要換 preset 抑是加長取樣，無一集分流
- [ ] 9.2 以 `/loop 20m` 持續檢查（額度共用但**不排隊、token 盡量用**，撞到上限由 `/loop` 等額度回來自動續跑——使用者裁定 2026-09-05，見 design D14）：對已切完且無 TSV 的雙語集逐集派 7 批左右的讀者（model opus、判準 `scripts/aiyalaeho/brief.md`、TSV 寫進 `Kari-SRT/aiyalaeho/1-ocr/2-vision/<srt_name>/bNN.tsv`）；派工前先 `ls` 確認前一集檔案都在，重派時給不同的輸出檔名與 scratchpad；額度用完就停下來等，做到一個段落就回報
**9.2／9.4 進度（2026-09-06 11:15 CST）：108、109 已交付，110、111 在讀。**

| 集 | cue | 批 | 派工 | 交付 | 耗時 | 交付行數 |
|---|---|---|---|---|---|---|
| 106 | 598 | 7 | 09-05 19:38 | 09-05 20:32 | 54 分 | — |
| 107 | 574 | 7 | 09-05 20:03 | 09-05 20:37 | 34 分 | — |
| 108 | 796 | 7 | 09-06 09:57 | 09-06 10:49 | **52 分** | 780 |
| 109 | 822 | 7 | 09-06 10:12 | 09-06 10:59 | **47 分** | 809 |

**111 切九批，不是七批。** 它有 977 條 cue、326 張 sheet，七批的話每人 47 張／140 條，比 108／109 的 40 張／120 條重上一截。九批之後是 37 張／111 條，和前幾集相當。**批數要照 cue 數調，不是固定七批。**

**兩集平行跑得動。** 109 讀到一半就派 110，110 讀到一半就派 111，額度沒有撞到上限。

- [x] 9.3 108／111 派工提示明寫：頂列夾漢字整行進 `formosan`，不把漢字搬去 `han`
- [ ] 9.4 每集七批 TSV 落地並覆核後：ingest 前照例做編號連續與重複稽核，`ingest` → `make_all <srt_name>`；每集交付後掃一次全語料碼位（README 的例行動作）

## 10. 整批定版與總驗收

- [ ] 10.1 `make_all`（全部）：報告段逐集列異常集理由並標出非檔名來源者
- [ ] 10.2 **前置條件：第 8 組已完成（116／119／122 已登記進 inventory），或使用者明示這三支不做。** 沒有這一條，下面的計數會在少三集的情況下全綠。`publish --check` 通過後 `publish`：inventory 不再有 pending；store 有 `smkul.csv` 與 `smkul-字幕版型異常.csv`；兩表無重複 `srt_name`，列數相加＝inventory 筆數（**做完第 8 組是 44 筆，不是 41**）；另表每列理由非空
- [ ] 10.3 aiyalaeho `rebuild --verify`：全部交付 SRT 與兩張表逐 byte 相同
- [ ] 10.4 總驗收：`tox -e unittest`、`tox -e flake8`、news 的 `rebuild --verify` 與 `name_catalogue --check`（另一條線在改就 `/loop 20m` 等他；news verify 紅的時候先看 DIFFERS 指名哪一側的檔，見 design D14）
- [ ] 10.5 文件：`tests/README.md`（spec × scenario 表：cue-timing 加守門與遮罩裁帶、srt-data-store 加另表、aiyalaeho-sourcing 加分流與三路理由）、`Kari-SRT/README.md`（樹加 `smkul-字幕版型異常.csv`）、`Kari-SRT/aiyalaeho/1-ocr/README.md`（重建及於兩張表）、`scripts/README.md`（`cues --band-rows`；另一條線也會補四支新模組，動手前重讀、只加自己的行）、`scripts/aiyalaeho/README.md`（SOP 一條指令串：`verify_band --band-json` → 依離開碼分支 → `cues --band-rows` → `refine` → 看 sheet_001；兩張表說明；報告怎麼看；人工判定的理由怎麼寫）
- [ ] 10.6 收尾回覆檔到 `kithann/tuiue/`：交付集數與行數、兩張表列數、異常集清單附理由與來源、待使用者 `git add` 的檔案清單
