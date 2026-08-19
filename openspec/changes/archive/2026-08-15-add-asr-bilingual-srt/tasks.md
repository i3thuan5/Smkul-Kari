# Tasks：add-asr-bilingual-srt

試點集：110 年 2 月新聞 `20210201_032_晚間_Amis_阿美`。5.x 是
gate——報告經使用者核可前，6.x（其餘 34 集）不准動。有平行 session
在動 repo，每組動手前先重驗現況。**全程照 CLAUDE.md TDD 規定：
每個 2.x 模組先寫 `tests/asrmt/` 對應測試檔走紅，才寫實作走綠。**

## 0. 改組：Kari-SRT 資料＋scripts 拆分（照技術分，最先做）

- [x] 0.1 Kari-SRT 內純 `mv`（內容逐 byte 不動；git 由使用者
      commit）：`cues→news/1-ocr/1-cues`、
      `from_rtf→news/1-ocr/2-from_rtf`、`vision→news/1-ocr/3-vision`、
      `vision-rtf→news/1-ocr/4-vision-rtf`、
      `report→news/1-ocr/5-report`、`srt→news/1-ocr/6-srt`、
      `inventory.json→news/`、`srt/smkul.csv→news/smkul.csv`
- [x] 0.2 主 repo 路徑常數更新：`scripts/news/paths.py` 等全部指向
      新位置；grep 掃程式、測試、文件內殘留的舊路徑
- [x] 0.3 `smkul.csv` 增列語音側進度欄（僅由 `news/2-asr/` 檔案
      存在與否推導，不手填）；`rebuild`／`make_all` 同步，重建
      含該欄逐 byte 相同——測試先行：`tests/news/test_smkul_asr.py`
- [x] 0.4 `Kari-SRT/news/1-ocr/README.md`：OCR 檔案架構與流程
      （編號＝產生順序；註明 2-from_rtf／4-vision-rtf／5-report
      是二月批次歷史產物，新批次只動 1-cues／3-vision／6-srt）；
      並改寫 `Kari-SRT/README.md` 結構圖為新分層
- [x] 0.5 scripts 拆分（照共用性歸位，模組內也拆）：
      `scripts/subs2srt` → `scripts/ocr/`——`cuelib.py`（像素
      部分）、`band.py`（字幕帶偵測，原 detect.py 正名）、
      `ocr.py`、`sheets.py`、`transcripts.py`（原 assemble 的
      TSV 匯入與 verified 半邊）、`cli.py`；＋ `scripts/srtlib/`
      ——`srt.py`（srt_timestamp／render_srt／parse_srt，
      原 cuelib 尾段）、`assemble.py`（merge_repeats／
      apply_gap_rules／pad_edges）；`scripts/news/` 六處 import
      與 e2e fixture 隨改
- [x] 0.6 tests 鏡射搬移：`tests/cuelib`＋`tests/subs2srt` →
      `tests/ocr`（test_mask／region／segmenter／sheets／
      import_tsv／ocr_prep／presets／auto_options）＋
      `tests/srtlib`（test_srt_format 隨模組鏡射改名 test_srt、
      test_merge_repeats、test_pad_edges）；
      tox.ini（discover 路徑、flake8 範圍）與
      `.claude/skills/video-subtitle-srt/SKILL.md` 路徑同步
- [x] 0.7 驗收：`rebuild --verify` 在新路徑逐 byte 全綠、全套
      單元測試綠

## 1. 環境與音檔前驗

- [x] 1.1 建 `~/.venvs/asrmt`（vosk、huggingface_hub），
      `snapshot_download('ILRDF/kaldi_formosan_250514_Amis')`，
      拿 `kithann/Formosan-AI/asr-kaldi/examples/` 的 wav 本機煙霧
      測試：words＋confidence 出得來、文字無 capitalize／u→o 處理
- [x] 1.2 用 `scripts/news/sftp.sh` 抓試點集 mp3（路徑出自
      `ilrdf-corpus.csv` 音檔欄），`ffprobe` 時長對 cue 軸預期
      2880s（容許 ±1s）；不合即改抓 mxf、`ffmpeg -vn` 抽 16k wav
      後刪影片；把採用來源與兩個時長記進工作筆記

## 2. 引擎 `scripts/asrmt/`（每條先測試紅、後實作綠）

- [x] 2.0 `tests/asrmt/fixtures.py`：合成資料產生器（詞流、條目、
      真實窗、塊），供全部測試共用
- [x] 2.1 `asr.py`：ffmpeg 轉 16kHz mono s16le、0.125s chunk 餵
      `KaldiRecognizer(SetWords)`，輸出 `1-words/<srt_name>.json`
      （逐詞 start/end/conf ＋ 語音句分界）
- [x] 2.2 抽共用組裝鏈（0.5 拆分後住 `scripts/srtlib/`）：
      `make_srt.py` 的 entries 流程改為可回傳「條目 ↔ 真實時間窗
      （合併前來源 cue 聯集）」對照表的函式，既有 SRT 輸出
      逐 byte 不變（`rebuild --verify` 必須照過）
- [x] 2.3 `project.py`：詞按與條目真實窗重疊最大歸戶；tie 歸前
      條目；straddle 計數；未落任何窗的詞保留在 words.json 標記；
      投影結果落地 `2-entries/<srt_name>.json`（真實窗、詞索引、
      族語行；華語行與語別碼由後續步驟補入同檔）
      ——測試檔 `test_project.py`
- [x] 2.4 `mtclient.py`：gradio queue client（`/queue/join`＋SSE，
      同 session 先 `/lambda` 換族別）、JSONL 內容定址快取
      （engine, direction, src_lang, text）、單併發＋固定間隔、
      失敗帶原始回應
- [x] 2.5 `bisrt.py`：從 2-entries render 兩種產物、**分檔不覆蓋**
      ——審查版六行 → `3-srt-raw/<srt_name>.srt`（族語ASR結果／
      華語OCR字幕翻譯成族語-ailabs／-claude／華語OCR字幕／
      族語ASR結果翻譯華語-ailabs／-claude）；正式版兩行 →
      `5-srt-complete/<srt_name>.srt`（族語／華語＝主引擎，gate
      後才產）；空窗條目 ASR 相關行留前綴空文字且不送翻譯、字幕
      翻譯行照出；時間戳取共用鏈的留白後值；2-entries＋mt-cache
      即可離線重組——測試檔 `test_bisrt.py`（兩種產物都釘）
- [x] 2.5b Claude 批次翻譯（第二引擎）：出批次檔（編號句子、
      兩方向）＋ ingest 驗證（編號歸屬、行數，比照視覺辨識批次
      紀律：TSV 直寫磁碟、寫一次不自行修檔）後併入 mt-cache
      （engine=claude）
- [x] 2.5c `dpalign.py`：純 DP 核心（sim 注入、時間帶限、步含
      1-1／1-2／2-1／2-2 合併與跳過、錨點軟加分、回溯出配對）；
      無 I/O 無 MT——測試檔 `test_dpalign.py`（交錯、拆併、跳過、
      帶外不配全部釘死）
- [x] 2.6 `detect.py`：語音句×條目連通塊；字元 bigram F1 內容
      分數（塊級＋條目級）；δ∈±3s 步長 0.1s 的字元 LCS 掃描
      （去斷詞記號、不以詞為單位）與 rolling median 偏移曲線；數字錨點（阿拉伯＋中文數字）；低分條目的配對恢復
      （呼叫 dpalign，字元分數雙引擎取最高，無語意向量）寫
      `matched_entries`；歸類矩陣輸出 `4-align/<srt_name>.json`
      （含 `calibrated: false` 與門檻值）＋摘要
      `4-align/<srt_name>.md`——測試檔 `test_detect_blocks.py`／
      `test_detect_scores.py`／`test_detect_classify.py`

## 3. 編排 `scripts/news/`

- [x] 3.1 `asrmt_run.py` 單集編排：srt_name → 音檔（含 1.2 的
      時長驗證，不合指名中止）→ 解碼 → 投影 → 方言碼選定
      （50 個有字條目 × 5 個 `ami_*` 跑族語→華語取內容分數中位數
      最高，記入 meta；此步只涉 ai-labs，Claude 不需語別碼）→
      全量 MT（兩方向 × 兩引擎）→ 雙語 SRT（主引擎 ai-labs）→
      偵測 → 摘要；每步落地、可中斷續跑
      ——測試檔 `tests/news/test_asrmt_run.py`（時長不符指名中止、
      續跑跳過已完成步驟；編排住 scripts/news 故測試照慣例入
      tests/news）
- [x] 3.2 阿美語錨點表 `scripts/news/anchors_ami.json`：數詞＋
      新聞常見借詞專名（地名／機構名，如 taypak 台北、
      kalingko 花蓮、kongsiya 公司）；漢字讀音資料不用中國維護
      的套件（D9），先自建小表
- [x] 3.3 `Kari-SRT/news/2-asr/README.md`：流程圖＋各階段檔案的
      輸出入對應表（哪支程式、吃什麼、產什麼）；並同步
      `Kari-SRT/README.md` 的 2-asr 一節（拿掉「開跑後出現」註記）

## 4. 測試與驗收

- [x] 4.1 測試涵蓋查核：各模組測試已依 TDD 先行（2.x 各條），
      此處對照 spec scenario 逐條查漏補齊（同軸逐 byte、語序
      倒置不誤報、系統性偏移現形、雙引擎互證、錨點對位、快取
      續跑、Claude 批次編號歸屬），全套離線跑綠
- [x] 4.1b `tests/README.md`：全部 spec（含既有 srt-data-store、
      cue-timing、subtitle-text-source）× scenario × 測試檔的
      完整對照表，按 pipeline 流程排序、按「OCR 引擎／共用組裝／
      ASR 引擎／編排／e2e」分組——測試檔名管定位（鏡射模組名），
      這張表管照流程理解
- [x] 4.2 tox 佈線：flake8 範圍含 `scripts/asrmt/`、subtitle env
      收 `tests/asrmt/`
- [x] 4.3 本機驗收三連：`subtitle-rebuild --verify`（2.2 改動後
      逐 byte 不變）、`flake8`、`subtitle` 單元測試全過

## 5. 試點執行與報告（gate）

- [x] 5.1 跑試點集全流程，產出 `Kari-SRT/news/2-asr/` 的
      `1-words/`、`2-entries/`、`3-srt-raw/`（審查版六行）、
      `4-align/` 各該集檔案與 mt-cache
- [x] 5.2 校準樣本：抽 50 個被標（mismatch／asr-doubt）＋50 個
      未標條目，Claude 初判、使用者抽驗；據以定門檻、記
      precision、更新 `.align.json` 的 calibrated 狀態
- [x] 5.3 試點報告：ASR 可用度（conf 分布、華語受訪段落表現）、
      偏移曲線（mp3 是否與 cue 軸同源的結論）、歸因分布與代表例、
      選定的方言碼、**兩引擎比較**（互相一致度、各自與字幕的
      對齊率、SRT 主引擎建議）、MT 請求數與快取命中、cue 邊界
      精度註記、**借詞專名錨點覆蓋率**（字幕專名有多少比例在
      ASR 詞流找到音近詞，決定要不要擴表）
- [x] 5.4 【使用者】審試點報告——已逐項裁定：門檻照現值、主引擎
      不適用（正式版只用原始材料）、批次隔離／塊語意句／CKIP 錨點
      全部完成；commit 依 CLAUDE.md 由使用者執行

## 6. 放量其餘集數（5.4 核可後才動）

- [x] 6.0 試點集 `6-srt-complete` 已產（原始材料＋語意整併版）；
      使用者評估後裁定效果不佳——**之後的集數不再產**
- [x] 6.1 【使用者裁定改範圍】逐集跑其餘全部已交付集數，**只到
      `3-srt-raw`**（words→entries→raw，`asrmt_batch` 驅動，逐集
      落地可續跑）；MT／偵測／審查版／正式版之後的集數都不做
- [x] 6.0b 錨點 v2：CKIP 斷詞（GPL-3.0-only 已稽核）＋就近定位
      完成（試點實測，覆蓋率 40%）；分句標記屬 align 延伸，
      預設流程不跑
- [x] 6.2 【不需要做】各族錨點表——錨點屬 align 延伸，預設流程
      止於 3-srt-raw（使用者裁定）
- [x] 6.3 【不需要做】彙整報告——偵測屬 align 延伸，預設流程不跑
      （使用者裁定）；批次結果以 smkul 語音側欄與批次 log 為準
- [x] 6.4 【使用者】放量產出的 `Kari-SRT` commit 與主 repo
      pointer bump 依 CLAUDE.md 執行（非 Claude 工作，照規定歸
      使用者；此條視同結案註記）
