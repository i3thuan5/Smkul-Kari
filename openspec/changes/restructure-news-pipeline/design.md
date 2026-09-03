# Design: restructure-news-pipeline

## Context

動機見 proposal.md。設計要面對的現場約束：

- **平行 session**：Kari-SRT submodule 現有約千餘個 staged 檔（月份分層遷移，另一 session 進行中）；0d 持有 `split_cue.py`、`rescan_band.py`、`migrate_strips.py`，a9 持有 `scripts/aiyalaeho/` 一套。本 change 不動這些檔；動到共用檔（`paths.py`）時要挑空檔。
- **批次時序**：refine 批次收尾後隨即發動 2021-01（58 集）抓檔切 cue。work dir 寫入端不先改好，58 個新 work dir 又是舊版面，之後要多遷移一次——所以寫入端是第一優先。刪除與 renumber 則相反，要等 submodule staged 遷移 commit 完、`rebuild --verify` 轉綠的空檔。
- **git 規定**：Claude 不執行 `git add`／`commit`／`mv`／`rm` 等，store 的資料操作由使用者做；本 change 的程式修改與驗證由 Claude 做。
- **已量測的事實**：`4-vision-rtf/` 4,151 條 cue 與 `3-vision/` 逐條同名同文字，`rebuild.episode_transcripts()` 有無 rtf 結果 16/16 集相同（2026-08-31 實測）；已交付 74 集中 47 集不同軸、15 集無 `3-srt-raw`；align 延伸只有試點集一集有產物。

## Goals / Non-Goals

**Goals:**

- store 版面收斂到「每個目錄都有現行讀者」：`1-ocr/{1-cues,2-vision,3-srt}`、`2-asr/{1-words,2-entries,3-srt-raw}`，與《開會了》語料版面一致。
- 逐 byte 重建保證在刪除與 renumber 前後不變，並延伸涵蓋語音側同軸。
- work dir 時間軸「寫一次、不原地改寫」落實到寫入端與讀取端。
- 入口收斂為三階段：cues（CPU）→ OCR（Claude）→ asr（CPU）。

**Non-Goals:**

- 門檻重校（`verify_band` SPIKE、`blank_runs`、`blind_cues`）——獨立 change `recalibrate-news-gates`。
- 0d 的三支與 a9 的 aiyalaeho 五支——各自 session 改。
- 試點集 `2-entries` 內已填 MT 欄位的清洗——保留原樣，不值得為它動資料檔。
- repo 瘦身——刪除是普通 commit，歷史保留，不改寫歷史。

## Decisions

### D1：`4-vision-rtf/` 直接刪，不搬不併

實測證明它 100% 冗餘（見 Context）。曾考慮把 rtf TSV 改名 `b9x.tsv` 併入 `3-vision/` 保住合併語意——不必要：合併結果本來就等於只讀 `3-vision/`。刪除前先落一條鎖定測試（fixture 合成：單一 vision source 重建結果與雙 source 相同），刪除後 `rebuild --verify` 逐 byte 過即為完工證明。

### D2：renumber 與程式常數同一步切換

`3-vision→2-vision`、`6-srt→3-srt` 的 `git mv`（使用者執行）與 `paths.py` 常數改名必須在同一個空檔內完成、立刻跑 `rebuild --verify`——沒有過渡期雙版面支援。理由：階段路徑全部收斂在 `paths.py`（`stage_path()` 單一入口），雙版面 fallback 是為期一小時的過渡寫兩倍的碼。`2-asr/` 不 renumber（已連號），`3-srt-raw` 名稱不動（tracker 的「語音辨識模型」欄語意綁著它，改名只有改名本身的收益）。

### D0：現行流程全圖、資源歸屬與實測耗時

一集（48 分鐘節目）跑到 `3-srt-raw` 的全部步驟。「資源」欄是這一步真正花在哪：**CPU**＝本機運算、**網路**＝SFTP、**Claude**＝模型呼叫。

```
 SFTP 母帶
   │
   │  ① 登記月份        plan_month          CPU   秒級
   │  ② 下載 19 GB mxf   sftp.sh get         網路  4.3–5.3 分
   ▼
 kithann/out/stage/
   │  ③ 驗字幕帶        verify_band         CPU   41 秒（每資料夾第一支才跑）
   │  ④ 切 cue（5 fps 全片解碼）             CPU   6.0 分  ← 解碼 3.6＋遮罩 3.5
   │     ocr.cli cues --sheets
   │     → <slug>.work/{cues.json, strips/, sheets/, sheets.json}
   │  ⑤ 邊界精修（25 fps，逐邊界 ±0.24 秒窗，約 2000 窗）
   │     refine_cues                        CPU   8.5 分  ← 遮罩 5.8＋解窗 2.7
   │  ⑥ 刪影片（mxf 留給封存）
   ▼
 work dir
   │  ⑦ 重排校讀用 sheet gap_sheets         CPU   秒～分（不碰影片，strips 用 symlink）
   │  ⑧ 出批次單        batches --size 24   CPU   瞬間
   │  ⑨ 視覺辨識 subagent → 3-vision/*.tsv
   │                                        Claude ★ 約 50 分（178 張 sheet、8.2 批）
   │  ⑩ 匯入            ingest              CPU   秒級
   │  ⑪ 組裝            make_all/make_srt   CPU   秒級
   │  ⑫ 定版            publish             CPU   秒級
   ▼
 1-ocr/{1-cues,2-vision,3-srt}
   │  ⑬ 抓 mp3          sftp.sh get         網路  十幾 MB
   │  ⑭ 時長前驗        verify_audio        CPU   瞬間
   │  ⑮ vosk 整集辨識   asrmt_run words     CPU   ┐
   │  ⑯ 投影            asrmt_run entries   CPU   ├ 合計約 15 分
   │  ⑰ render          asrmt_run raw       CPU   ┘
   ▼
 2-asr/3-srt-raw ★終點

 （平行支線，不在關鍵路徑）封存 mkv：encode_master.sh
     x264 CRF 23 編碼 CPU 約 20–30 分，整輪含抓檔驗證 50–58 分
```

**花時間的排序**：⑨ Claude 視覺辨識（50 分）≫ ⑮–⑰ 語音側（15 分）＞ ⑤ 精修（8.5 分）＞ ⑥ 切 cue（6 分）＞ ② 下載（5 分）。一個月 71 集 ≈ 58 小時視覺辨識、7.5 小時抓檔切 cue。

**文件在哪**（每一步的說明正本）：

| 主題 | 檔案 | 節 |
|---|---|---|
| 全流程操作手冊（含規模估算） | `.claude/commands/smkul-news.md` | 全文，尤其 Scale 那節 |
| 全流程兩行指令版 | `scripts/news/README.md` | 「跑法」 |
| 影像側階段目錄對照 | `Kari-SRT/news/1-ocr/README.md` | 「流程與各階段檔案」 |
| 語音側階段目錄對照 | `Kari-SRT/news/2-asr/README.md` | 「流程」「輸出入對照」 |
| SFTP 速度與兩個坑 | `scripts/news/README.md` | 「影片來源：SFTP」「連線」 |
| 字幕帶驗證與 63 支重校 | `scripts/news/README.md` | 「開跑前用 verify_band.py 對照畫面」 |
| 切 cue 機制與失效模式 | `.claude/skills/video-subtitle-srt/SKILL.md` | Cue segmentation |
| 精修設計（25 fps、±0.24） | `openspec/changes/archive/2026-08-14-refine-cue-timing/design.md` | D1–D4 |
| contact sheet 裝箱與 122 列懸崖 | `scripts/news/README.md` | 「區域ê懸度有一个無聲ê懸崖」 |
| 視覺辨識派工省法（24 vs 72 張） | `scripts/news/README.md` | 「派視覺辨識ê兩个省法」 |
| 封存編碼參數依據 | `.claude/skills/video-subtitle-srt/壓縮率分析.md` | 全文 |
| 遮罩判準與 cue 被切碎 | `kithann/mask.md` | 全文（本 change 不處理，另一條線在想） |

### D0-2：合併 ffmpeg 趟數——量過了，省 11%，不在本 change 做

母帶目前最多被解碼四趟：③ 驗帶、④ 切 cue、⑤ 精修、（封存時）⑦ 編碼。合併 ④⑤ 成一趟（一次順序解碼，5 fps 算分段遮罩，同時留 0.64 秒滾動緩衝供邊界精修）在技術上可行——精修窗是 ±0.24 秒，而斷點在 2 格（0.4 秒）後才確認，緩衝 16 格約 11 MB。

量測（本機 16 核）：

- **解碼是解碼綁的，抽格率幾乎不影響**：同一段 120 秒影片，`fps=5`＋crop 8.7 秒、`fps=25`＋crop 9.3 秒、全解碼 10.3 秒。一集全片解碼約 3.6 分。
- `text_mask` 一格 14.5 ms（1920×122）：5 fps 全片 3.5 分、25 fps 全片 17.4 分。
- x264 `-preset medium -crf 23`：120 秒影片 75 秒，是解碼的 8 倍。

所以合併 ④⑤：現行 6.0＋8.5 ＝ 14.5 分 → 合併後約 12.9 分（解碼 3.6＋5 fps 遮罩 3.5＋邊界 25 fps 遮罩 5.8），**省約 1.6 分／集（11%）**，另外省掉約 2000 次 seek。省不掉的是邊界 25 fps 遮罩那 5.8 分。

**不列入本 change**：收益 1.6 分／集，相對於同一集 50 分鐘的視覺辨識是小數；而它要動的是 `ocr/cli.py` 的 cues stage 與 `refine_cues.py`，正好是 task 1（work-dir 寫入端）要動的兩支——同時改兩件事會讓「寫入端搶時效」這個目的失焦。留作後續，數字記在此。

（真正的大頭另有其人：`kithann/mask.md` 記錄 24.9% 的 cue 是在重讀上一句，等於一集約 12 分、一個月約 14 小時的視覺辨識是重複的。那要改切 cue 判準，屬另一條線。）

### D3：同軸檢查併入 `rebuild --verify`，比序列不比 byte

檢查內容：**兩側交付都存在**的集數，(index, start/end) 序列必須與影像側交付 SRT 逐條相等；不同＝fail、指名該集與第一個岔點，並修到相同為止。**只有影像側、語音側尚未產出＝正常通過，不警告**（使用者 2026-08-31 裁定，推翻先前「缺檔要警告且 fail」的版本）。

理由：語音側是獨立的一條線，它做到哪 `smkul.csv` 的「語音辨識模型」欄已經照實反映了；把「還沒做」當成錯誤，等於讓一條線的進度擋住另一條線的驗收，而且會讓 publish 後、asr 前的 verify 長期是紅的——紅燈常態化就沒有人看它。相對地，「兩側都有但對不起來」是真正的資料矛盾：同一集有兩份互相衝突的時間軸，下游沒有辦法判斷哪一份對，所以必須擋。

不做語音側 byte 重建——族語行文字來自辨識器，byte 重建屬「可由 `2-entries` 重 render」性質，序列比對已足以守住同軸契約，成本低一個數量級。

既有欠帳（實測 47 集不同軸）照 TDD 清：檢查先落地（47 集紅）→ 47 集重投影＋重 render（離線，`asrmt_run --step entries` 起，不重跑 vosk、不重翻譯）→ 全綠。**15 集沒有 `3-srt-raw` 的不再是欠帳**，要不要補做 vosk 由語音側自己的節奏決定，不受本 change 約束。

### D4：work dir 寫入端先行，遷移工具殿後

寫入端（`ocr/cli.py` 寫 `1-cues/cues.json`、`refine_cues.py` 寫 `2-refined/cues.json`）趕在 2021-01 切 cue 前落地，新 work dir 直接是新版面。讀取端 11 支改走 `cues_to_read()` 等 helper（已存在、測試綠）。既有 work dir 的遷移工具等 a9 通知《開會了》切完才掃（邊搬邊生會漏）；掃完拿掉 `cues_to_read()` 的舊版面 fallback。「cue 號碼當鍵」的物件清單（`cues.json`、`sheets.json`、`transcripts.json`、`2-vision/b*.tsv`）從 docstring 升級成測試守——清單寫在 docstring 擋不住漏改，`split_cue` 漏 rtf 那次已經證明。

### D4-2：contact sheet 改時間命名，跟 strips 同一個道理

`sheets/sheet_NNN.png` 目前是流水號。這正是 strips 改名前的病：**看起來像編號，其實不是識別碼**——cue 一被重編（`safe_resplit`、`rescan_band`、`split_cue`），磁碟上的檔名不動而它代表的內容變了。strips 那次量到全 store 46,665/75,290（62%、48 集）的 strip 檔名不是它的 cue 號，README 曾把 strip 號當 cue 號記，照著改會改到一百列以外的 cue。

改成該 sheet **首格 cue 的起始時間**（沿用 `stripname.of()` 的形式：`t<毫秒八碼>.png`）。起始時間不會因為別條 cue 被剖開而移動，而且 `t01874700` 不像序數，沒有人會拿它當第幾張用。`sheets.json` 仍是 sheet↔cue 的唯一對照，這點兩種命名下都一樣。

strips 的遷移已於 2026-08-31 完成（136 個 work dir 全數時間命名、0 個舊流水號、0 個混用），所以本 change 只需處理 sheet，並沿用同一支遷移工具的作法。

### D4-3：`smkul.csv` 三個欄位動作

現行 12 欄：

```
節目名稱, 年度, 集數, 播出日期, 播出時段, 族語別(英), 族語別(中),
影片檔案位置, 影片長度, 文稿位置, 字幕srt狀態, 語音辨識模型
```

改成 12 欄（刪 `播出時段`、`文稿位置`，加 `成果檔名`、`cues`），順序重排成
「**這一集是誰 → 素材在哪 → 做到哪**」：

```
年度, 集數, 播出日期, 節目名稱, 族語別(英), 族語別(中),
影片檔案位置, 影片長度, 成果檔名, cues, 字幕srt狀態, 語音辨識模型
```

- 前六欄是**身份**（年度／集數／播出日期先行，才排得出時序），中間兩欄是**素材**，後四欄是**進度**：`成果檔名` → `cues` → `字幕srt狀態` → `語音辨識模型`，正好是產生順序，一列從左讀到右就是這集做到哪。
- **`文稿位置` 刪掉**：只從 `smkul.csv` 拿掉。`inventory.json` 內同名欄位由節目目錄帶進來，是來源資料不是交付物，留著不動——真要一併清是另一件事，會動到 store 的輸入檔。

**`播出時段` 刪掉與 `成果檔名` 加入必須是同一步。** 拿掉時段之後
`(年度, 集數, 播出日期)` 不再唯一：實測 74 列只有 33 組日期，其中
**31 組是一天 2–3 集**（午間／晚間／晨間）。分得開它們的就是
`成果檔名`（`20210201_032_午間_Atayal_泰雅` 本身就含時段），族語別
也跟著不同。先刪後加會留下一份三列幾乎一樣的表，所以這兩件事不
拆步驟。

三欄都必須**由 store 推導、不得手填**，否則 `rebuild --verify` 重算不出逐 byte 相同的表：

| 欄 | 推導自 |
|---|---|
| `成果檔名` | inventory 的 `srt_name`（本來就是每列的鍵）|
| `cues` | `1-cues/<年-月>/<srt_name>.json` 的精修旗標——已精修／粗切／檔不在就留白 |

`cues` 這欄現在全 74 集都會是「已精修」（實測：74 份 store 時間軸全部帶精修旗標）。**看起來全同不代表沒用**：`publish` 是把 work dir 的時間軸原樣複製進 store 的，一個沒跑過精修的 work dir 定版就會把粗切時間軸帶進來，而那件事今天沒有任何一欄看得出來。這欄就是那道記錄。

實作上 `paths.timeline_is_refined()` 已經在做這個判讀（store 的時間軸是單一檔案，旗標在檔內），照用即可。

### D5：入口三階段，斷頭路徑刪除

標準流程收斂為三個入口，各自吃的資源寫明：cues＝`fetch_sftp.sh`（CPU：下載→verify_band→切 cue→微調→sheet），OCR＝`/smkul-news` 的視覺辨識→`ingest`→`make_all`→`publish`（Claude），asr＝`asrmt_batch`（CPU：抓音檔→vosk→投影→raw render）。`refine_fetch.sh` 刪除：它指向不存在的 `Kari-SRT/cues/`、本來就跑不起來，其補救對象（14 集未微調）已由現行批次處理完。修錯鏈（reread、rescan、resplit）維持現狀，歸屬 OCR 階段文件。

### D6：`be_nice()` 改補差額

讀 `os.nice(0)` 現值、只補到目標 15，shell 已 nice 過就不再累加。`_applied` 旗標刪除——跨行程本來就看不到，補差額語意天然冪等。

### D7：align 延伸連程式帶測試刪

`asrmt_run.py` 的八個延伸步、`scripts/asrmt/align/` 五模組、`tests/asrmt/align/` 七檔全刪；`bisrt.py` 只剩 `raw_body`。歷史在 git；留死碼的維護成本（flake8、README 對照表、誤用風險）高於翻歷史的成本。

## 檔案樹（change 完成後）

### Kari-SRT（資料；「產生程式 ← 輸入」）

```
Kari-SRT/news/
├── inventory.json                     publish 維護 ← 節目目錄＋批次登記
├── smkul.csv                          publish 定版 ← store 檔案存在推導
├── 1-ocr/
│   ├── README.md
│   ├── 1-cues/<年-月>/<srt_name>.json    ocr cli cues＋refine ← 影片
│   ├── 2-vision/<年-月>/<srt_name>/b*.tsv ingest ← 視覺辨識 TSV
│   └── 3-srt/<年-月>/<srt_name>.srt      make_all＋publish ← 1-cues＋2-vision
│                └── <srt_name>.qc.json   同上
└── 2-asr/
    ├── README.md
    ├── 1-words/<年-月>/<srt_name>.json   asrmt_run words ← 音檔（vosk）
    ├── 2-entries/<年-月>/<srt_name>.json asrmt_run entries ← 1-words＋組裝鏈
    └── 3-srt-raw/<年-月>/<srt_name>.srt  asrmt_run raw ← 2-entries
```

刪除：`1-ocr/{2-from_rtf,4-vision-rtf,5-report}/`、`2-asr/{4-srt-ai,5-align,6-srt-complete,mt-cache}/`。

### work dir（kithann/out/mxf/，不進版本控制）

```
<slug>.work/
    1-cues/cues.json      ocr cli cues ← 影片（寫一次，唯讀）
    2-refined/cues.json   refine_cues ← 1-cues＋影片
    strips/ sheets/
<slug>.B.work/
    3-working/cues.json   gap_sheets 複製 ← .work；resplit／rescan／split 改
```

### scripts/（修改 M／刪除 D／新增 A）

```
M scripts/news/paths.py          刪 KARI_FROM_RTF/KARI_VISION_RTF/KARI_REPORT/MT_CACHE，
                                 KARI_VISION→"2-vision"、SRT_DIR→"3-srt"
M scripts/news/rebuild.py        單一 vision source；同軸檢查（序列比對＋缺檔警告）
M scripts/news/split_cue.py      vision_folders() 單 root
M scripts/news/publish.py        刪 from_rtf 分支
M scripts/news/asrmt_run.py      刪八個延伸步與 align import
M scripts/news/refine_cues.py    寫 2-refined/，不原地改寫
M scripts/ocr/cli.py             cues 寫 1-cues/
M scripts/lowpri.py              be_nice 補差額
M scripts/news/{make_srt,make_all,gap_sheets,blank_runs,blind_cues}.py   讀取端走 helper
M scripts/ocr/{transcripts,sheets,cuelib}.py                             讀取端走 helper
M scripts/news/reread_tools/{prompt,safe_resplit}.py                     刪 rtf 段／改 2-vision
M scripts/news/{fetch_sftp,run_cues}.sh                                  新 work dir 版面
A scripts/news/migrate_workdirs.py                                       work dir 遷移（一次性）
D scripts/news/reread_tools/fix_rtf.py
D scripts/news/refine_fetch.sh
D scripts/asrmt/align/（整包）
```

### tests/

```
M tests/news/test_paths.py            常數改名、刪三常數斷言
M tests/news/{test_rebuild_sources,test_make_srt,test_pending,test_tracker_home,
              test_split_cue,test_smkul_asr}.py    拆 rtf／align 相關段
A tests/news/test_rebuild_coaxial.py  同軸檢查：同軸過／岔開 fail／缺檔警告＋fail（fixture 合成）
A tests/news/test_single_vision_source.py  鎖定測試：單 source 重建＝雙 source
A tests/news/test_cue_key_registry.py 「cue 鍵物件」清單守門
A tests/news/test_workdir_writers.py  cues 寫 1-cues/、refine 寫 2-refined/ 不碰 1-cues/
D tests/asrmt/align/（整目錄）
```

### 文件

Kari-SRT 頂層 README、`news/1-ocr/README.md`（歷史產物節收斂為結論摘要：畫面對、稿子錯，文稿不供字）、`news/2-asr/README.md`、`scripts/README.md`、`scripts/news/README.md`、`reread_tools/README.md`、`.claude/commands/smkul-news.md`（三階段入口＋新收尾順序）。

## Risks / Trade-offs

- [renumber 空檔內平行 session 用舊路徑] → 動工前用 ListAgents／訊息對齊時段；`paths.py` 改完立刻 `rebuild --verify`，殘留舊字串由 repo 全域 grep 收尾。
- [同軸檢查上線期間 verify 長期紅] → TDD 順序把紅期壓在本 change 內：檢查、修復、補做排同一個 task 群，結束條件是全綠。
- [15 集 vosk 補做掛掉沒人知] → 依 CLAUDE.md 長時間工作規定：`run_in_background: true` 發動、步驟用 `&&` 串、不用 pgrep 輪詢。
- [遷移工具掃到一半有人生新 work dir] → 只在 a9 通知《開會了》切完後跑；遷移前後各數一次 work dir 數量核對。
- [刪 align 後 flake8／README 對照測試紅] → `test_readme_covers_scripts` 這類守門測試在同一個 task 內同步更新。

## Migration Plan

1. 寫入端（task 1）先上——與批次無衝突，愈早愈好。
2. 刪除＋renumber（task 2）等空檔：使用者 commit submodule 遷移 → verify 綠 → Claude 改程式＋使用者 `git rm`／`git mv` → verify 綠。
3. 讀取端、遷移、同軸、入口重整依 tasks 順序，各 task 自帶驗收（見 tasks.md）。
4. 回退策略：資料操作都是普通 commit，`git revert` 可逆；程式修改隨 change 分支走。

## Open Questions

（無——排程類的不確定（submodule 何時 commit 完、a9 何時通知）不影響做法，只影響開跑時點。）
