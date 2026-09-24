# scripts/：程式分層（照共用性）

資料夾定位見根 README；這裡列到檔案。原則：引擎 package 語料無關、
編排歸 `news/`、兩側共用的東西住 `srtlib/`。

## errors.py——唯一對人丟的例外（頂層，兩側共用）

`PipelineError`：操作者、store 抑是外部服務出錯，講予人知然後停。
以前 48 个函式庫函式直接丟 `SystemExit`——彼是 `BaseException`，
`except Exception` 掠袂著，等於恬恬繞過別人ê錯誤處理；而且
`asrmt_batch` 為著「跳過這集、繼續落一集」，愛掠 `BaseException` 來做
一般ê流程控制。

無人佇 CLI 邊界kā它換轉去 `SystemExit`（使用者裁定）：沒接的例外會
印 traceback、離開碼 1。堆疊會講是佗一个檢查掠著ê、是啥物叫伊，批次
做一半停落來ê時，彼比一逝清氣ê訊息較有路用。

## datadirs.py——repo 版面與參數保護（頂層，兩側共用）

`ROOT`／`kithann/`／`Kari-SRT/` 三個位置，加上 CLI 參數的保護：
`check_name`（名字不得帶路徑成分）、`check_under`（路徑只准落在
`kithann/`、`Kari-SRT/`、系統暫存目錄——**不是** repo 底下都可以，
`scripts/` 與 `openspec/` 是程式碼與規格，不是資料）。

放頂層是因為 `ocr/` 刻意不依賴 `news/`：這裡放的是 repo 版面與參數
驗證，兩邊都不擁有；語料專屬的路徑（stage、階段目錄）
留在 `news/paths.py`。

## lowpri.py——長時間工課ê優先權（頂層，兩側共用）

轉檔、解碼這款走幾點鐘ê步數，`be_nice()` kā伊降去 nice 15，才袂kā
互動ê工課拖牢。`os.nice()` 是**累加**ê，呼叫兩擺就變 30，所以內底
有擋牢，仝一个行程叫幾擺攏仝款。

## languages.py——族語別佮語言別ê代號對照表（頂層，兩側共用）

`LANGUAGES`（族語別中 → 英文拼法＋ISO 639 三碼）、`VARIETIES`（族語別
下底ê變體字樣 → 私有標籤）、`code_for()`、佮倒轉查ê `language_of()`／
`variety_of()`。規範正本（`kithann/規範/` 彼兩份 CSV）是 gitignore ê，
換一台機器就無去，所以表愛綴 repo 走——規範若改，兩爿做伙改、做伙走
`tests/languages/`。

本底伊蹛佇 `aiyalaeho/catalogue.py`（彼陣干焦《開會了》對檔名剖語言別
用著）。族語新聞這馬嘛愛填 `語言別代號`，若叫 news 去 import
aiyalaeho，依賴ê方向就顛倒去（這馬是 aiyalaeho → news），所以徙來頂層
——理由佮 `datadirs.py` 仝一條：兩爿攏用著，兩爿攏無擁有伊。

## catalogue_checks.py——節目目錄ê共同欄位佮不變量（頂層，兩側共用）

六張表攏用仝一組欄位起頭，所以「前七欄是啥、按怎驗」愛有一个所在講。
`smkul.csv` 這馬是**輸入**毋是產出，逐 byte 重算比對無意義矣，
`rebuild --verify` 對伊ê把關換做這幾條：成果檔名規格佮唯一性、佮識別欄
互推、`語言別代號` 值域、族語別中英一對一、素材位置非空、列序、孤兒檔。

## lexicon/——官方族語辭典（頂層，兩側共用）

原語會 16 族官方族語辭典（SFTP `/docker/族語辭典_單詞與例句/` ê xlsx）ê讀取佮比對。本底蹛佇 `aiyalaeho/langcheck/`，族語新聞ê平行語料嘛愛用，若叫 news 去 import aiyalaeho，依賴ê方向就顛倒去——理由佮 `languages.py` 仝一條：兩爿攏用著，兩爿攏無擁有伊。內容無改，干焦徙位。

| 檔 | 做什麼 |
|---|---|
| `dictionary.py` | xlsx → 詞庫：標準函式庫讀（`zipfile`＋`xml.etree`，無 openpyxl）、欄位靠表頭名、取 `單字`／`詞根`／`例句原文` 三欄、撇號正規化 |
| `script.py` | 字元分類（Unicode 類別，毋是 ASCII 範圍；注音毋算漢字）佮切詞——詞庫佮字幕用仝一支尺 |
| `vocab.py` | 逐族詞庫命中率、上倚ê族、方言別正音（南勢阿美 u→o、b→f、v→f，加法毋是取代） |

## ocr/——影像側引擎（燒印字幕抽取）

| 檔 | 做什麼 |
|---|---|
| `decode.py` | ffmpeg 讀取：裁切框（`exact=1`、偶數界）、`stream_region`（`fps` 濾鏡重取樣）、`stream_frames`（原生格率逐格，時間取 `showinfo` 的真實 pts；可只放行 select 視窗，視窗多時走 `-filter_script`）、`window_frames`（重疊視窗共用畫面、關一個交一個）；ffmpeg 執行緒數預設 2 |
| `refine.py` | 邊界精修的判斷：±0.24 秒視窗逐格歸左右兩側、取兩側中點；一集所有視窗一支 ffmpeg（`refine_all`）；沿用粗切值時分「取不到畫面」「無法分辨」 |
| `sheetsize.py` | Claude Vision 輸入組合圖的價錢：只讀 PNG 檔頭 24 bytes 拿寬高、算視覺 token（`⌈寬÷28⌉×⌈高÷28⌉`），`PATCH`／`LONG_EDGE`／`VISUAL_TOKENS` 的正本；只用標準函式庫，切批跑在沒有 numpy／PIL 的系統 python3 上 |
| `sampling.py` | 粗切取樣：每 0.2 秒目標取最接近的來源格，時間記該格真實 pts，同一格不交兩次；格率宣告為 0/0 時估算用 29.97 |
| `cuelib.py` | 像素核心：遮罩、cue 切分（Segmenter，調成每 0.2 秒餵一格）；`MaskSpec.band_rows` 會使共遮罩裁到字幕帶彼幾列，帶以外逐列算空 |
| `band.py` | 字幕帶位置偵測（preset 載入與帶位判準） |
| `ocr.py` | tesseract 輸出清理 |
| `sheets.py` | contact sheet 產生（給視覺辨識讀） |
| `transcripts.py` | 視覺逐字稿帳本：TSV 驗證匯入、transcripts.json／verified.json |
| `cli.py` | `python -m scripts.ocr.cli`：detect／cues／ocr／srt／auto 五階段；`cues` 原生格率解碼、每 `1/--fps` 秒取一格（`--threads` 調 ffmpeg 執行緒數）；`cues --band-rows LO,HI` 用**絕對列**指定字幕帶，寫入 manifest ê是 region 內ê偏移（《開會了》靠這隻共遮罩裁到帶頂，畫面別位ê字免影響切 cue）；`cues --mask-scale N` 覆寫 preset ê取樣倍率（無傳就照 preset，無 preset 就是 1＝逐畫素） |

## srtlib/——兩側共用

| 檔 | 做什麼 |
|---|---|
| `srt.py` | SRT 格式：時間戳、render、parse |
| `assemble.py` | 組裝鏈：同文合併、間距規則、0.5s 留白、`chain_with_spans`（條目↔真實窗對照——影像側交付與語音側 raw 跑同一條鏈，同軸因此逐 byte 成立） |

## asrmt/——語音側引擎

| 檔 | 做什麼 |
|---|---|
| `asr.py` | vosk 整集解碼 → 逐詞時間戳＋confidence（1-words） |
| `project.py` | 詞按真實窗 max-overlap 歸戶條目（純函式，結果無落地——愛ê時陣當場算） |
| `bisrt.py` | render：raw 兩逝「族語：／華語：」（2-srt-raw，正式交付）；分析用ê三逝版 |
| `gradio.py` | Gradio 佇列協定共用層：上傳、`queue/join`＋讀 SSE 串流到 `process_completed`、暫時性閘道錯誤重試（502/503/504/529）——ai-labs 翻譯服務佮 sapolita 公家 |
| `mtclient.py` | ai-labs 翻譯服務（族語→華語一个方向）＋內容定址ê `mt-cache/`；佇列協定包 `gradio.Client` |
| `dialects.py` | 族別 → 服務ê語言碼靜態表（對服務ê選單抄落來；賽德克ê碼是 `trv_` 起頭，袂使用前綴臆族別） |
| `sapolita.py` | sapolita（whisper 族語辨識）用戶端：16 族選單值表、語言別代號 → 族別選單值查表、`recognize()` 辨識一个音檔 |
| `judge.py` | 族華對應品質：材料（族語逝／字幕／譯文／前後字幕）、批次、收件檢查、`quality-cache/`、兩个裁判合成 |
| `judge_prompt.md` | 裁判ê prompt——三級ê定義本身；改伊愛順紲 `PROMPT_VERSION` 加一 |
| `judge_prompts/` | 歷版ê正文。快取逐筆判定攏記版本，彼个記號無正文就無意義——測試會擋「快取有、遮無」 |
| `probes.py` | 構造法探針（配毋著字幕、改數字、剁後半句）——無真值ê時，用「應該降級ê」來量裁判ê盲點 |
| `glossary.py` | 逐集掃一擺，揣出「佇幾若條攏對著仝一个華語主題」ê族語詞——逐批共用，省重推、標準一致 |
| `orthography.py` | 機器譯文ê字形改做這个語料ê字形（日文變體、簡體）；做佇 render，快取保持忠實 |

## news/——族語新聞編排

| 檔 | 做什麼 |
|---|---|
| `paths.py` | 語料路徑的單一出處（`stage_path()` 是階段目錄唯一出口，逐集檔案囥佇月份一層；`--var` 供 shell 取值；版面與保護轉出自 `scripts/datadirs.py`） |
| `audio.py` | 取這集辨識用ê音檔：封存 mkv → SFTP（位元組數比對），抽煞就刪抓來ê原檔——kaldi 佮 whisper 兩條線公家，暫存區既有ê原檔無算捷徑 |
| `asrmt_batch.py` | 語音側（kaldi）整批：逐集 抓音檔→解碼→投影＋render→刪音檔 |
| `asrmt_run.py` | 語音側（kaldi）單集步驟（預設 words→raw；翻譯佮品質判斷 `--step` 指名） |
| `whisper_run.py` | 語音側（whisper／sapolita）逐集佮整批：取音檔→查語別碼（`新聞語言別代號.csv`）→辨識→原樣存 SRT→寫辨識紀錄→刪暫存音檔；一次一集、可續跑（SRT 佮紀錄兩者都在才算做完） |
| `lexicon_fetch.py` | 官方族語辭典：`kithann/族語辭典/` 無就對 SFTP 抓（位元組數比對、族名對檔名讀、16 族欠一族指名停），蒸餾做詞庫快取 |
| `pairs_run.py` | 族華平行語料整批：2021-01～10、兩爿攏有ê集數 → `2-asr-whisper/2-平行語料/<年-月>/<成果檔名>.csv`；`--recalibrate` 才重算校正基準；無叫任何模型 |
| `pairs_tune.py` | 調合併門檻：`--sample` 對新聞抽樣寫裁判請求（一批四个 50 組ê檔）、`--ingest NN` 收回覆、`--report` 出各格比例表佮選值；攏囥 `kithann/out/mt/調參/`，毋入 Kari-SRT |
| `anchors_ami.json` | 阿美語錨點表（數詞＋借詞專名，拼法對照模型 lexicon） |
| `plan_month.py` | 一批＝一个播出月份：揀來源、出跳過報告（**唯讀**，無寫任何檔）|
| `sources.py` | 一集配一支檔的規則（母帶優先→時段相符→同名不同夾→一檔一集） |
| `episodes.py`／`resolve_slug.py` | 節目目錄讀出來ê逐集條目（`slug`／`file`／`pending` 攏是推導ê）；目錄索引與命名 |
| `fetch_sftp.sh`／`run_cues.sh`／`sftp.sh`／`sftp-askpass.sh` | 影像側抓檔與切 cue（吃播出月份，清單對節目目錄提；密碼只以檔案存在；`sftp.sh` 收動詞＋獨立參數，路徑不進指令字串） |
| `cut_months.py` | 一個月接一個月跑 `fetch_sftp.sh`（預設 2021-11～2024-11）；每月開始前看磁碟，不夠就等；每月一列寫 `logs/cut-progress.tsv` |
| `namebars.py` | 受訪者名條 → 段落表「受訪者語言別代號」：`grab` 照逐秒 `name` 特徵逐擺名條截一格、裁右爿、仝款ê歸組；`apply` 讀者答案（族名）換代號寫入 |
| `refine_cues.py`／`verify_band.py` | cue 邊界精修（一集一支 ffmpeg、原生格率；**愛 `--preset`／`--presets`**，精修愛佮切 cue 用仝一款判準，無講就拒絕走）、字幕帶前驗（順紲驗欄方向：字幕ê右緣有無猶佇比對遮罩內底） |
| `ocr/stripname.py` | Strip ê檔名：用 cue ê起始時間，因為序號會綴重新編號走 |
| `blank_runs.py` | 掠 vision TSV 內底ê長連紲空白：字幕印佇帶外ê段會規段變空白 |
| `rescan_band.py` | 用改正ê帶重切一段，接轉原本ê cue 排、規集重新編號（讀字了後ê補救；重切接回ê算術佇 `splice.py`） |
| `splice.py` | 重切一段、接轉時間軸ê純算術（照號碼、照秒數）佮重切本身；`rescan_band` 佮 `segment_recut` 公家 |
| `opening.py` | 片頭辨識：切 cue 時截 20／30／40 秒三格（已入庫ê集數用 curl 抓頭尾兩段補截）、組合圖、讀者 TSV → `1-ocr/片頭辨識.csv`，語別佮目錄無仝就擋 |
| `shots.py` | 影片 → 逐秒畫面特徵（160×90 縮圖：節目框在毋在、紅條、棚內參考格、語別牌、單元標誌），截判不準ê原圖；參考格佇 `shot_refs/<年>/` |
| `segments.py` | 逐秒特徵 → 段落表（兩層判法）、讀者確認、段落表ê把關（`publish` 佮 `rebuild --verify` 攏用） |
| `relabel.py` | 片頭辨識查出目錄語別標毋著：改目錄那一列（族語別、代號、成果檔名、備註），store 內佮語別無關ê檔改名、用毋著語言做ê（whisper、平行語料、kaldi）刪掉等重跑 |
| `offband_backfill.py` | 已經讀完字ê集數補切一段帶外字幕（2021 帶外專題）：`prepare` 重切、精修、照時間算新編號、干焦為新 cue 出組合圖；`apply` 照時間徙 store ê TSV 編號、收讀者 TSV、時間軸佮 SRT 入庫 |
| `segment_recut.py` | 段落表上帶外ê段（島語時間、部落信箱…）用家己ê preset 重切、精修，讀字進前接轉時間軸，cue 記 `area` |
| `split_cue.py` | 佇量出來ê時間點kā一條 cue 剖做兩條，後壁ê重新編號 |
| `migrate_strips.py` | Strip ê檔名對 cue 序號換做起始時間（照磁碟頂ê檔案走，毋是照 cue）|
| `redump_store.py` | 店面ê JSON 重排做人讀有ê形（縮排、鍵排序、漢字免跳脫）；JSONL 一逝一筆免縮排。干焦改排版，內容無動 |
| `gap_sheets.py`／`batches.py`／`ingest.py` | 視覺辨識批次的出題與收卷 |
| `make_srt.py`／`make_all.py`／`publish.py`／`rebuild.py` | 組裝、時間軸入庫、離線重建驗證 |
| `coaxial.py` | 比影像側佮語音側交付ê (index, 起, 迄)——兩爿攏有ê時愛逐條仝款；干焦影像側ê免比（語音側是家己ê一條線）|
| `name_catalogue.py` | kā `srt_name` 寫入目錄ê**產生欄**（`--check` 重算逐格、對袂起來就 exit 1；CRLF＋BOM 原樣保留） |
| `blind_cues.py` | 揀出 contact sheet 無真正看著ê cue（`frames × 0.2` 對 `end - start` ê差額），補查ê出題單 |
| `reread.py` | kā失敗ê cue 切做「一句一段」：時間中位數先洗掉會振動ê雜訊，才兩兩比。時間軸無振動，出來ê段是予視覺辨識重讀ê |
| `reread_tools/allsheets.py` | 逐集切段出圖條，會跳過做過ê（可續跑） |
| `reread_tools/prompt.py` | 印一批ê讀者提示；判準ê正本囥佇 `brief.md`，改一擺後壁逐批攏會著 |
| `reread_tools/safe_resplit.py` | 規集做伙把關（`resplit.admit`），過ê才切，寫 cues.json ＋ TSV；閣會報「切袂開毋過讀者讀著無仝」ê（`resplit.unsplit_but_changed`） |
| `reread_tools/regen_strips.py` | 照新編號重生 strips／sheets／sheets.json |
| `resplit.py` | kā `reread` 切出來ê段真正寫入時間軸：一條 cue 換做幾若條，TSV ê編號綴咧徙（兩爿做伙改，無就逐格ê字會歪去） |
| `presets.json` | 版型知識（哪個節目哪種帶位） |

## 新節目要走哪一套：看字幕是「族語＋華語兩列」還是「只有華語一列」

使用者裁定 2026-09-16。`news/` 與 `aiyalaeho/` 分成兩套，**分界不是節目名，是字幕版型**：

- **只有華語一列**（族語新聞這種）→ 走 `news/`。一條 cue 一列圖條，組合圖上兩條 cue 之間隔著區塊間隔，字不會互相干擾。
- **族語一列＋華語一列**（《開會了》這種）→ 走 `aiyalaeho/`。一條 cue 兩列圖條，而且兩列在畫面上是**貼著的**：列窗必然切在字身上，族語的降部（`g`、`p`、`y`）會被切到下一列圖條的頂端（111 集實測 88% 的 cue 如此，殘餘中位 3 px、p99 6 px），所以組合圖上同一條 cue 的兩列之間要留得比殘餘開，讀者才不會把它看成上一列字母的一部分。族語列還有 `^`、`'` 這些符號要逐字保留，判準（`aiyalaeho/brief.md`）和新聞那份不一樣。

新節目進來時先看這一項再決定放哪一邊；兩列的還要量一次「降部被切幾 px」，因為那要看該節目的字型與行距。

## aiyalaeho/——《開會了》編排

畫面同時燒族語佮華語兩逝，所以交付 SRT 是**兩行一條**（「族語：／
華語：」），兩逝攏對畫面來，無語音側。引擎（`ocr/`、`srtlib/`）共用，
一行無改；詳見 [scripts/aiyalaeho/README.md](aiyalaeho/README.md)。

| 檔 | 做什麼 |
|---|---|
| `paths.py` | 語料路徑單一出處（`stage_path()` 逐集檔案**無分層**；`check_srt_name` 認 `開會了_<集數3碼>_…`） |
| `catalogue.py` | 檔名就是這一集：解析集數／族語別／語言別／語言別代號＋整批寫兩張節目目錄表 |
| `verify_band.py` | 切 cue 前逐集驗版型：量帶ê色佮字幕列ê位置（門檻攏是量出來ê，見該 README） |
| `ingest.py` | 兩逝一 cue ê TSV 驗證匯入（cue↔sheet 歸屬、空白列補 tab、干焦提 `b*.tsv`） |
| `make_srt.py` | 單集組裝：每條兩行帶標籤，走共用組裝鏈（0.5 秒留白仝款） |
| `make_all.py`／`publish.py`／`rebuild.py`／`episodes.py` | 整批組裝、時間軸入庫、離線重建驗證、兩張目錄表讀取 |
| `presets.json` | `aiyalaeho-bilingual`（黃底雙列帶；本底寄佇 `news/presets.json`，這改搬轉來家己遮） |
| `blobs.py` | 連通元件（8-連通ê `label`／`boxes`，佮「族語逝ê墨底」ê `deepest_bottom`）——環境無 scipy，讀者逐擺家己重寫就逐擺無仝，收做一支才免 |
| `brief.md` | 視覺辨識讀者判準ê**正本**（逐批ê提示攏對這份提，判準才袂逐批走鐘） |
| `text/oledoc.py`／`decode.py`／`parse.py`／`lang.py`／`split.py`／`pairs.py` | 上字文稿（001–045，無影片、佮上面攏無關）轉族華平行語料：OLE2 讀取、副檔名分派解碼、排版判定、語言代號、多重分隔符 AI 判讀、組出 `1-句對.csv`；詳見 [Kari-SRT/aiyalaeho/text/README.md](../Kari-SRT/aiyalaeho/text/README.md) |
| `langcheck/mark.py`／`report.py` | 交付 SRT 逐條ê語言判定：逐條標記、兩張 CSV。辭典彼爿（讀 xlsx、切詞、命中率）用頂層 `lexicon/`。**干焦讀 `3-srt/`**，離線、無叫模型；詳見 [Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/README.md](../Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/README.md) |

news 有而遮無ê四支：`fetch_sftp.sh`（素材已經佇本機）、`plan_month.py`
（無月份批次，登記併入 `catalogue.py`）、`gap_sheets.py`（無 `.work`
彼層歷史）、`batches.py`（`ocr.cli pending` 就會列未讀ê sheet）。

## mt/——族語新聞 → 機器翻譯訓練語料（計算引擎）

sapolita 族語辨識段落配華語燒印字幕，
做段落級ê族華平行語料，《開會了》雙列字幕當標準答案。只 import
`srtlib/`、`lexicon/`；路徑、範圍、入庫攏佇 `news/`。詳見 [scripts/mt/README.md](mt/README.md)。

| 檔 | 做什麼 |
|---|---|
| `load.py` | 讀兩側：sapolita SRT → 段落（真實 VAD 邊界）；store ê `1-cues`＋`2-vision` 走仝一條組裝鏈 → 字幕條目（帶真實窗、保留併掉ê cue 編號） |
| `overlap.py` | 時間重疊分組：每條字幕歸予重疊上濟ê段，字幕真跨兩段（兩爿攏佔合併門檻以上）才合併 |
| `textsim.py` | 華語側字元 n-gram F1、chrF；族語側切詞（撇號、長音記號統一）、編輯距離詞相似度 |
| `hallucination.py` | 只靠文字ê幻覺旗標：重複 n-gram、譯文數字串、辭典命中率；16 族辭典判「這段其實是別族ê語言」 |
| `goldalign.py` | 《開會了》真值：ASR 詞對附近字幕ê族語列做局部對齊（Smith-Waterman），毋靠時間軸 |
| `evaluate.py` | 一組對真值ê精確率／召回（按 cue 詞數加權）、strict／lax、AUC、門檻掃描 |
| `features.py` | 一組ê信心特徵，攏是新聞頂懸（無標準答案）算會出ê：chrF、辭典命中率、旗標、時間覆蓋率、長度比、每秒詞數、壓縮比 |
| `calibration.py` | 校正基準：逐族主播開場（前 90 秒、≥5 詞）辭典命中率ê中位數；表凍結，干焦 `--recalibrate` 重算；查無族語別指名停，袂退預設值 |
| `tier.py` | 分層：高信心／中信心／不採用＋不採用原因（幻覺＞別族語言＞詞數不足＞命中率不足）；規條線ê門檻攏佇遮，合併門檻嘛是 |
| `pairs.py` | 一集ê組 → 交付 CSV 字串（欄位順序照使用者指定、SRT 時間戳、UTF-8 無 BOM、LF） |
| `tuning.py`／`judge_prompt_paragraph.md` | 調合併門檻ê算法：分格（字幕佇兩段中較少彼爿佔偌濟）、固定種子抽樣、合併／拆開三組、分批（兩版袂仝批）、整批收件、Wilson 95% 區間、選值（分不出取較低ê門檻）；佮裁判ê判準 |

## transcode/

`transcode/` 是母帶封存：`encode_master.sh` 是編碼本身（CRF 23、
yuv420p、flac、MKV），`archive_batch.py` 是整批流程——抓母帶落
stage、編、驗、改名就位、紲落去刣掉 stage 彼支。已經有封存ê集數直接
跳過，所以斷去閣走接會起來。

編碼彼站行**三站**，`encode_master.sh` 刁工做煞頭一站就停：一逝
ffmpeg 共來源全部聲軌攏紮入去封存，順紲算出**逐條來源聲軌ê指紋**；
紲落來 `audio_tracks.py` 決定敢忠實、佗幾條愛留；上尾 `-c copy` 重
封裝賰該留ê。按呢來源干焦讀一擺——舊版讀三擺（比聲軌、編碼、驗證），
一支 19 GB ê母帶佇 USB 碟就是 57 GB ê讀取。

`audio_tracks.py` 是這爿ê判斷：對音訊指紋看封存敢逐位元忠實、佗幾條
聲軌愛留。純函式無 I/O，予 `archive_batch.py` 佮 `tools/mxf2mkv/` 兩
爿共用。兩條聲軌內容無仝（主聲道／國際聲、族語／華語）是廣電ê常規，
所以「看起來仝款就刣一條」這款判斷伊袂家己做——伊逐位元比。

`tools/mxf2mkv/` 是仝一套編碼佮聲軌邏輯ê另外一个呼叫端：**隨身硬碟**
一个資料夾底ê mxf 逐支轉、轉一支傳一支，遠端結構照來源排，囥
`/home/mkv-raw/`。伊無查節目目錄，所以
猶未登記ê母帶嘛轉會動；佮 `/home/news/mkv/` 彼爿無相干，重複ê照轉。
按怎走看 `tools/mxf2mkv/README.md`。

## `tools/`：無佇交付流程頂懸ê量測工具

| 檔案 | 做啥 |
| --- | --- |
| `cuescore/score.py` | 一份時間軸對 store ê視覺辨識文字評分：**重覆對／吞句／漏切**三个數字，毋免影片。動任何切割參數（門檻、比對遮罩、解析度）了後就用這支量——`rebuild --verify` 掠袂著切割ê回歸，因為伊從頭到尾無碰遮罩 |
| `measure/`、`mxf2mkv/` | 影片壓縮量測、mxf→mkv 轉檔 |
| `mtgold/sapolita_aiyalaeho.py`、`mtgold/sweep.py` | 開會了送 sapolita 辨識（結果放 `kithann/out/mt/aiyalaeho-sapolita/`，毋入 Kari-SRT），佮佇開會了標準答案頂懸掃合併門檻——開會了干焦提供正確答案，毋產平行語料 |
