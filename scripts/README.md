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
驗證，兩邊都不擁有；語料專屬的路徑（stage、inventory、catalogue）
留在 `news/paths.py`。

## lowpri.py——長時間工課ê優先權（頂層，兩側共用）

轉檔、解碼這款走幾點鐘ê步數，`be_nice()` kā伊降去 nice 15，才袂kā
互動ê工課拖牢。`os.nice()` 是**累加**ê，呼叫兩擺就變 30，所以內底
有擋牢，仝一个行程叫幾擺攏仝款。

## ocr/——影像側引擎（燒印字幕抽取）

| 檔 | 做什麼 |
|---|---|
| `cuelib.py` | 像素核心：遮罩、區域運算、取樣、cue 切分（Segmenter） |
| `band.py` | 字幕帶位置偵測（preset 載入與帶位判準） |
| `ocr.py` | tesseract 輸出清理 |
| `sheets.py` | contact sheet 產生（給視覺辨識讀） |
| `transcripts.py` | 視覺逐字稿帳本：TSV 驗證匯入、transcripts.json／verified.json |
| `cli.py` | `python -m scripts.ocr.cli`：detect／cues／ocr／srt／auto 五階段 |

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
| `mtclient.py` | ai-labs 翻譯服務（族語→華語一个方向）＋內容定址ê `mt-cache/` |
| `dialects.py` | 族別 → 服務ê語言碼靜態表（對服務ê選單抄落來；賽德克ê碼是 `trv_` 起頭，袂使用前綴臆族別） |
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
| `asrmt_batch.py` | 語音側整批：逐集 抓音檔→解碼→投影＋render→刪音檔 |
| `asrmt_run.py` | 語音側單集步驟（預設 words→raw；翻譯佮品質判斷 `--step` 指名） |
| `anchors_ami.json` | 阿美語錨點表（數詞＋借詞專名，拼法對照模型 lexicon） |
| `plan_month.py` | 一批＝一个播出月份：揀來源、寫 pending 條目、出跳過報告 |
| `sources.py` | 一集配一支檔的規則（母帶優先→時段相符→同名不同夾→一檔一集） |
| `add_episodes.py`／`resolve_slug.py` | 逐支指定路徑登記；目錄索引與命名 |
| `fetch_sftp.sh`／`run_cues.sh`／`sftp.sh`／`sftp-askpass.sh` | 影像側抓檔與切 cue（吃播出月份，清單對 inventory 提；密碼只以檔案存在；`sftp.sh` 收動詞＋獨立參數，路徑不進指令字串） |
| `refine_cues.py`／`verify_band.py` | cue 邊界精修、字幕帶前驗 |
| `ocr/stripname.py` | Strip ê檔名：用 cue ê起始時間，因為序號會綴重新編號走 |
| `blank_runs.py` | 掠 vision TSV 內底ê長連紲空白：字幕印佇帶外ê段會規段變空白 |
| `rescan_band.py` | 用改正ê帶重切一段，接轉原本ê cue 排、規集重新編號 |
| `split_cue.py` | 佇量出來ê時間點kā一條 cue 剖做兩條，後壁ê重新編號 |
| `migrate_strips.py` | Strip ê檔名對 cue 序號換做起始時間（照磁碟頂ê檔案走，毋是照 cue）|
| `migrate_workdirs.py` | 舊 work dir ê平 `cues.json` 徙入階段目錄（看檔案家己有無 `refined` 決定入 `1-cues/` 抑 `2-refined/`）；冪等，做過矣 |
| `redump_store.py` | 店面ê JSON 重排做人讀有ê形（縮排、鍵排序、漢字免跳脫）；JSONL 一逝一筆免縮排。干焦改排版，內容無動 |
| `gap_sheets.py`／`batches.py`／`ingest.py` | 視覺辨識批次的出題與收卷 |
| `make_srt.py`／`make_all.py`／`publish.py`／`tracker.py`／`rebuild.py` | 組裝、定版、進度表、離線重建驗證 |
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

## aiyalaeho/——《開會了》編排

畫面同時燒族語佮華語兩逝，所以交付 SRT 是**兩行一條**（「族語：／
華語：」），兩逝攏對畫面來，無語音側。引擎（`ocr/`、`srtlib/`）共用，
一行無改；詳見 [scripts/aiyalaeho/README.md](aiyalaeho/README.md)。

| 檔 | 做什麼 |
|---|---|
| `paths.py` | 語料路徑單一出處（`stage_path()` 逐集檔案**無分層**；`check_srt_name` 認 `開會了_<集數3碼>_…`） |
| `catalogue.py` | 檔名就是這一集：解析集數／族語別／語言別／語言代號＋整批登記；**無讀** `ilrdf-corpus.csv`（彼 46 逝無日期、無族語別，43 逝標無影片煞有影片） |
| `verify_band.py` | 切 cue 前逐集驗版型：量帶ê色佮字幕列ê位置（門檻攏是量出來ê，見該 README） |
| `ingest.py` | 兩逝一 cue ê TSV 驗證匯入（cue↔sheet 歸屬、空白列補 tab、干焦提 `b*.tsv`） |
| `make_srt.py` | 單集組裝：每條兩行帶標籤，走共用組裝鏈（0.5 秒留白仝款） |
| `make_all.py`／`publish.py`／`tracker.py`／`rebuild.py` | 整批組裝、定版、九欄進度表、離線重建驗證 |
| `presets.json` | `aiyalaeho-bilingual`（黃底雙列帶；本底寄佇 `news/presets.json`，這改搬轉來家己遮） |
| `blobs.py` | 連通元件（8-連通ê `label`／`boxes`，佮「族語逝ê墨底」ê `deepest_bottom`）——環境無 scipy，讀者逐擺家己重寫就逐擺無仝，收做一支才免 |
| `brief.md` | 視覺辨識讀者判準ê**正本**（逐批ê提示攏對這份提，判準才袂逐批走鐘） |

news 有而遮無ê四支：`fetch_sftp.sh`（素材已經佇本機）、`plan_month.py`
（無月份批次，登記併入 `catalogue.py`）、`gap_sheets.py`（無 `.B.work`
彼層歷史）、`batches.py`（`ocr.cli pending` 就會列未讀ê sheet）。

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
`/home/mkv-raw/`。伊無查目錄、無查 `smkul.csv`、無查 inventory，所以
猶未登記ê母帶嘛轉會動；佮 `/home/news/mkv/` 彼爿無相干，重複ê照轉。
按怎走看 `tools/mxf2mkv/README.md`。
