## Context

動機見 proposal.md。這裡只寫 explore 階段量到、會影響做法的事（2026-09-18 在測試機實測）。

- sapolita 是 Gradio 5.35 應用，三個端點：`update_languages`（選族別，回傳該族的語別選單）、`generate_srt`（音檔＋語別碼 → SRT 文字）、`export_srt`（把文字包成檔案下載，用不到）。
- `generate_srt` 的「族語影片」欄直接收 mp3（16 kHz 單聲道一集約 9 MB），不用包成 mp4。
- 語別選單綁在 session：用 `/call/generate_srt` 直接送 `ssf`，回 `event: error`、`data: null`，沒有任何訊息；改用 `queue/join` 帶固定 `session_hash`，先呼叫 `update_languages("邵語 (Thau)")` 再辨識就過。這跟 `mtclient.py` 對付 ai-labs 翻譯服務踩過的坑一樣。
- 結果串流依序是 `estimation`、`process_starts`、好幾個 `heartbeat`、`process_completed`、`close_stream`。
- 邵語整集 48.5 分鐘，伺服器 116 秒辨識完（約 25 倍速）；193 段，段長中位數 11.6 秒、最長 30 秒。
- 回傳 SRT 每段兩行：`族語：`（辨識）、`華語：`（服務自己的機器翻譯，常有幻覺）。片尾配樂處會幻覺出整段「ʼa ʼa ʼa…」或別族的句子。
- 1 月各族抽一集（頭尾各 3 分鐘）都成功。主播名從 OCR 字幕開頭「我是…」取得：掃 2021-01～10 已 OCR 的集數，16 族中 15 族抓得到，雅美的字幕沒有名字（畫面字卡寫「主播 Vagyatan」）。排灣是中排灣、北排灣兩位主播各半，泰雅、魯凱也是兩人輪流或換人。
- 既有程式：`mtclient.HttpTransport` 已經實作 queue/join＋讀串流＋重試；`asrmt_run.audio_source`／`extract_audio` 與 `asrmt_batch._fetch` 已經實作「暫存原檔 → 封存 mkv → SFTP」取影片，但 `_fetch` 沒有比對位元組數，抓來的原檔也沒有刪。
- 正式機（`https://ai-labs.ilrdf.org.tw/sapolita/`）2026-09-18 上線：Gradio 版本、三個端點的編號與元件編號都跟測試機相同；同一段 90 秒邵語片段先選族別再辨識，回傳的前兩段文字與時間跟測試機逐字相同，耗時 6.8 秒（測試機 4.4 秒）。
- 大部分影片不在本機：封存 mkv 只有 63 集，其餘約 900 集要從 SFTP 抓（一支約 2.2 GB，實測 75 MB/s）。

## Goals / Non-Goals

**Goals:**

- 969 集的 sapolita SRT 原樣進 Kari-SRT，並有一張逐集紀錄表，日後可以挑出語別送錯、伺服器換版的集數重做。
- Gradio 佇列協定只寫一份，翻譯服務與 sapolita 共用。
- 取音檔只寫一份，kaldi 與 whisper 兩條線共用。

**Non-Goals:**

- 不把 sapolita 的段落對到 OCR 字幕、不做平行語料配對、不濾幻覺——那是下一層（`2-asr-whisper/2-…`），另開 change。
- 不做 `--check` 一致性檢查（使用者裁定）；`rebuild --verify` 也不涵蓋這一層（伺服器輸出無法離線重建）。
- 不逐集判斷語別，也不做主播換人的期間表（使用者裁定：同一族照其中一位主播定語別就好）。
- kaldi 那條線除了路徑改名、取音檔改成「mkv → SFTP、抓來的原檔用完就刪」之外，行為不變。

## Decisions

### 一、SRT 原樣存，不經 srtlib

回傳文字直接寫檔，不 parse 再 render。parse→render 一定會動到東西（空白、編號、行尾），這一層要能跟伺服器回應逐 byte 對得上，下一層才有可信的起點。替代方案「存成 JSON 再 render」被否決：多一層格式，人打開看不懂，也違反「原樣」。

不加 0.5 秒留白（使用者 2026-09-18 裁定）：Formosan-AI 線上版（`asr/`，commit 04569de）的段落起訖是 VAD 的語音邊界，`render_srt` 沒有延伸，檔尾也沒有換行。這一層比照 `cues.json` 保存真實邊界；留白能從原樣算出來，反過來算不回去，所以留白交給下游。

### 二、語別碼由 `scripts/news/新聞語言別代號.csv` 決定，程式直接讀

一族一列，whisper_run 直接讀這張 CSV，程式裡不另寫一份對照表（單一正本）。放在 `scripts/news/`，不放 `Kari-SRT/`：它是「這條流程要送什麼參數」的設定，跟 `presets.json` 同一類，隨 repo 走；不放 `scripts/languages.py`：保底語別是使用者對這份新聞語料的決定，不是代號規範。讀的時候逐列驗證代號在 `languages.py` 的 `VARIETIES`／族語別表查得到。

節目目錄的 `語言別代號` 只用來查族：用它的前綴查 `族語別(中)` 會遇到 `trv`（賽德克）與 `trv-x-truku`（太魯閣）同前綴，所以查表的鍵用節目目錄的 `族語別(中)` 欄，不用代號。

### 三、`scripts/asrmt/gradio.py`：從 mtclient 抽出佇列協定

`gradio.Client(base_url, session_hash)` 提供 `upload(path)`、`call(fn_index, trigger_id, data, timeout)`（queue/join＋讀串流到 `process_completed`，`success: false` 或串流中斷時丟 PipelineError 並帶原始回應）、重試暫時性閘道錯誤（502/503/504/529）。`mtclient.HttpTransport` 改成包一層 `gradio.Client`，對外介面不變，`test_mtclient.py` 不改就要過。上傳用 urllib 自己組 multipart，不加 `requests`、`gradio_client`（採購規定：能用既有工具就不加依賴）。

逾時分兩種：queue/join 60 秒；讀串流由呼叫端給——翻譯 180 秒，sapolita 900 秒（量到 116 秒，留給正式機與長集數餘裕）。

### 四、`scripts/asrmt/sapolita.py`：只管「音檔＋語別碼 → SRT 文字」

放 `asrmt/`（語音側引擎），因為它跟新聞無關，開會了以後要用可以直接拿。內含 16 族的族別選單值表（照伺服器抄，含 U+2019 彎撇）與語別碼 → 族別選單值的查表（2026-09-18 從伺服器 `update_languages` 讀下來的 42 個碼）。每次辨識用一個新的 session_hash：先 `update_languages(族別)`，再 `generate_srt`。回傳空字串或失敗就丟 PipelineError，訊息帶語別碼。

### 五、`scripts/news/audio.py`：取音檔共用

從 `asrmt_run`（`audio_source`、`extract_audio`）與 `asrmt_batch`（`_fetch`）搬出來。放 `news/`：要查新聞節目目錄與 SFTP 路徑，是新聞的事。兩條線來源順序相同：「封存 mkv → SFTP」，不看暫存區既有的原檔，whisper 也不看 kaldi 工作目錄的 `audio.mp3`（使用者 2026-09-18 裁定）。自 SFTP 抓來的原檔抽完音軌就刪。SFTP 取檔後用 `sftp.sh ls` 取遠端位元組數比對（`fetch_sftp.sh` 的既有做法，實測本機那批 24 個檔有 2 個不完整）；這個比對 kaldi 那條也一起受惠。

### 六、`scripts/news/whisper_run.py`：逐集與整批

逐集：取音檔 → 查語別碼 → sapolita 辨識 → 寫 SRT → 寫紀錄列 → 刪自 SFTP 抓來的影片與抽出的 mp3。寫入順序 SRT 先、紀錄後；續跑以「兩者都在」為做完，所以中斷在兩者之間的集會重做（spec〈可續跑〉）。

整批：照節目目錄順序一次一集，不做 `--shard`（伺服器不可平行）；下載與辨識不重疊，先求單純——下載 30 秒對辨識 2 分鐘，重疊只省兩成。一集失敗報告後繼續，最後非零結束。

主播名：讀 `Kari-SRT/news/1-ocr/2-vision/<年-月>/<成果檔名>/b*.tsv` 依編號排序的前 15 條，找第一個「我是」取後面的文字；找不到寫「不明」。

紀錄表寫法：整張讀進來、以 `成果檔名` 為鍵覆寫該列、排序後整張寫回（969 列，一集寫一次無負擔）。CSV 用 UTF-8、不帶 BOM、換行 LF（使用者 2026-09-18 裁定；`smkul.csv` 那三張節目目錄是 BOM＋CRLF，不跟它們一樣）。主播.csv、新聞語言別代號.csv 同樣。

伺服器網址用參數 `--server`，預設正式機 `https://ai-labs.ilrdf.org.tw/sapolita/`；寫入紀錄的 `伺服器` 欄就是這個網址。

### 七、`2-asr` 改名 `2-asr-kaldi`

`paths.py` 兩個常數（`ASRMT_WORK`、`ASR_DIR`）是唯一出處，改那兩處加上搬目錄就完成；Kari-SRT 與工作目錄都用一般的 `mv`（不用 `git mv`，staging 留給使用者）。`move_outdirs.py` 裡寫死的 `2-asr` 是過去搬家的路徑，整支刪掉就不用改。

### 採購稽核（sapolita）

1. 非中國製造／維護：sapolita 是原住民族語言研究發展基金會的族語 AI 成果網站服務，whisper 族語模型由我方團隊以 ILRDF 族語語料訓練；whisper 基底權重出自 OpenAI（美國）。通過。
2. 認證：正式機在 ai-labs.ilrdf.org.tw，由 ILRDF 管理；送出的是公開播出的新聞音軌，不含個資。
3. 機房：ILRDF 在臺灣。
4. 開源套件：不引進新套件（Gradio 在伺服器端，我方只用標準函式庫的 urllib）。
5. 裝得越少越好：零新依賴。

## 完整檔案樹

```
Kari-SRT/
├── README.md                                改  2-asr → 2-asr-kaldi，加 2-asr-whisper 一段
└── news/
    ├── smkul.csv                            （輸入：節目目錄）
    ├── 主播.csv                             ★新 人工整理（explore 抽聽＋OCR 字幕），whisper_run 不讀
    ├── 1-ocr/2-vision/<年-月>/<成果檔名>/     （輸入：主播名從這裡取）
    ├── 2-asr-kaldi/                         改  原 2-asr/，內容不動
    │   └── README.md                        改  路徑
    └── 2-asr-whisper/                       ★新
        ├── README.md                        ★新 手寫
        └── 1-srt-sapolita/
            ├── 辨識紀錄.csv                  ★新 whisper_run 產；吃 SRT 結果＋OCR 字幕＋新聞語言別代號.csv
            └── <年-月>/<成果檔名>.srt         ★新 whisper_run 產；吃音檔＋語別碼（sapolita 回傳原樣）

kithann/out/news/
├── 2-asr-kaldi/                             改  原 2-asr/
└── 2-asr-whisper/<年-月>/<成果檔名>.mp3      ★新 whisper_run 暫存，辨識完即刪

scripts/
├── README.md                                改  刪 move_outdirs；補 gradio、sapolita、audio、whisper_run、新聞語言別代號.csv
├── asrmt/
│   ├── gradio.py                            ★新 佇列協定、上傳、重試
│   ├── mtclient.py                          改  HttpTransport 改包 gradio.Client
│   └── sapolita.py                          ★新 族別表、語別碼→族別、辨識
└── news/
    ├── 新聞語言別代號.csv                    ★新 手寫，16 族；whisper_run 讀
    ├── paths.py                             改  改名；加 WHISPER_DIR、SAPOLITA_SRT、SAPOLITA_LOG、WHISPER_WORK、ANCHORS、NEWS_VARIETIES
    ├── audio.py                             ★新 取影片（mkv → SFTP、位元組數比對、用完刪原檔）、抽音軌
    ├── asrmt_run.py                         改  audio_source／extract_audio 改呼叫 audio.py
    ├── asrmt_batch.py                       改  _fetch 改呼叫 audio.py
    ├── whisper_run.py                       ★新 逐集／整批
    ├── move_outdirs.py                      ✖刪 一次性搬家已完成
    └── README.md                            改  補 whisper 這條線的指令與量測

tests/
├── README.md                                改  補下表各列
├── asrmt/
│   ├── test_gradio.py                       ★新
│   ├── test_mtclient.py                     不動（改完照過）
│   └── test_sapolita.py                     ★新
└── news/
    ├── test_audio.py                        ★新
    ├── test_whisper_run.py                  ★新
    ├── test_paths.py                        改  2-asr-kaldi
    └── test_move_outdirs.py                 ✖刪

.claude/commands/news-stage-count.md         改  路徑改名；加 whisper 一列
```

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| whisper-asr-srt | 結果串流先來 estimation、process_starts、好幾個 heartbeat，讀到 process_completed 才算；`success: false` 要丟錯並帶原始回應，不可回傳 None 讓上層寫出空檔 | `asrmt/test_gradio.py` |
| whisper-asr-srt | 上傳檔名是中文成果檔名（`20210227_058_晨間_Thau_邵.mp3`）時，multipart 要能送；伺服器回的暫存路徑要照回傳的用，不可自己拼 | `asrmt/test_gradio.py` |
| asr-bilingual-srt | 502／503／504／529 要重試，其他 HTTP 錯誤當場丟；抽成共用模組後翻譯服務的行為不變（`test_mtclient.py` 不改照過） | `asrmt/test_gradio.py` |
| whisper-asr-srt | 沒先在同一個 session 呼叫 `update_languages`，非阿美語別碼（實測 `ssf`）回 `event: error`、data 是 null——每次辨識要先選族別、兩次呼叫用同一個 session_hash | `asrmt/test_sapolita.py` |
| whisper-asr-srt | 族別選單值「阿美語 (’Amis)」「拉阿魯哇語 (Hla’alua)」是 U+2019 彎撇，打成直撇伺服器不認 | `asrmt/test_sapolita.py` |
| whisper-asr-srt | 語別碼 → 族別要查表：賽德克 `trv-x-tgdy` 和太魯閣 `trv-x-truku` 前綴都是 `trv`；查不到的碼（例：翻譯服務那套 `ami_Xiug`）要丟錯不可送 | `asrmt/test_sapolita.py` |
| whisper-asr-srt | 伺服器回空字串時沒有任何訊息，要丟錯並帶語別碼 | `asrmt/test_sapolita.py` |
| whisper-asr-srt／asr-bilingual-srt | 有封存 mkv 就不向 SFTP 要；暫存區裡切 cue 留下的原檔不用（kaldi 以前會先看它）；whisper 不看 kaldi 工作目錄的 `audio.mp3`；自 SFTP 抓來的原檔抽完音軌就刪（一支 2.2 GB，磁碟只剩約 90 GB） | `news/test_audio.py` |
| whisper-asr-srt | SFTP 抓完位元組數不符（本機那批 24 個檔有 2 個不完整）要指名該集中止，不可抽出半集音軌送辨識 | `news/test_audio.py` |
| whisper-asr-srt | SRT 原樣存：「族語：／華語：」兩行、片尾整段「ʼa ʼa ʼa…」都不動、不加 0.5 秒留白、檔尾沒有換行也不補（伺服器 `render_srt` 用空行接段、結尾不換行）——存下的檔和伺服器回的逐 byte 相同 | `news/test_whisper_run.py` |
| whisper-asr-srt | smkul.csv 7 族只記族語別（`ami`），要換成新聞語言別代號.csv 的語別碼；`trv`（賽德克）送 `trv-x-tgdy`、`trv-x-truku` 照送，查族用 `族語別(中)` 不用代號前綴 | `news/test_whisper_run.py` |
| whisper-asr-srt | 新聞語言別代號.csv 少了某一族、或代號不在 `scripts/languages.py` 裡，要中止並指名，不可送出 | `news/test_whisper_run.py` |
| whisper-asr-srt | 主播名取 OCR 字幕前 15 條第一個「我是」後面（「我是Sulryape Gadhu」→ `Sulryape Gadhu`）；雅美沒有「我是」、還沒 OCR 的集數沒有 2-vision，都寫「不明」不留空 | `news/test_whisper_run.py` |
| whisper-asr-srt | 續跑：SRT 和紀錄列都在才算做完；SRT 寫了、紀錄沒寫（中途被打斷）要重做；重做同一集是覆寫那一列、不多一列，紀錄表照成果檔名排序 | `news/test_whisper_run.py` |
| whisper-asr-srt | 整批一次一集：前一集回來才送下一集；一集失敗報告後做下一集，最後非零結束 | `news/test_whisper_run.py` |
| whisper-asr-srt | 伺服器失敗的那集不可留下 SRT 或紀錄列，暫存 mp3 與自 SFTP 抓來的影片要刪（磁碟只剩 90 GB，一支影片 2.2 GB） | `news/test_whisper_run.py` |
| srt-data-store | `2-asr` 改名後，Kari-SRT 與工作目錄兩處都是 `2-asr-kaldi`，whisper 的路徑在 `2-asr-whisper` | `news/test_paths.py` |

## Risks / Trade-offs

- [正式機的模型、速度、佇列設定跟測試機不同] → 正式機上線後先跑 1 集比對格式與時間；紀錄表記伺服器網址，換版可挑出來重做。
- [語別選錯（排灣有一半是北排灣主播、泰雅與魯凱主播語別不明）] → 使用者裁定照一個語別；紀錄表有主播名與送出代號，日後能挑出特定主播的集數重做。
- [約 32 小時的長時間工作沒人接] → 照 CLAUDE.md〈長時間的背景工作〉：用 `run_in_background` 發動、步驟用 `&&` 串、不用 `pgrep` 輪詢。
- [磁碟只剩約 90 GB] → 一次只留一支影片，抽完即刪。
- [Gradio 協定抽出來改壞翻譯服務] → `test_mtclient.py` 不改照過才算完成。
- [主播名從 OCR 取，只涵蓋已 OCR 的集數] → 其餘寫「不明」，照 spec 不留空；主播名不影響送出的語別碼，錯了不必重跑伺服器以外的東西。

## Migration Plan

1. `2-asr` → `2-asr-kaldi`：改 `paths.py` 後，`Kari-SRT/news/2-asr` 與 `kithann/out/news/2-asr` 都用 `mv`，submodule 內的 commit 由使用者做。跑 `rebuild --verify`，kaldi 那條要照過。
2. 正式機上線後先跑 1 集確認，再整批。
3. 回復：`2-asr-kaldi` 改回只要反向 `mv` 並還原 `paths.py`；`2-asr-whisper/` 是新增的，刪掉即回到原狀。
