## Context

見 proposal.md「Why」。這裡只寫決定時要知道的現況與限制。

**inventory 是封閉欄位表。** `paths.INVENTORY_FIELDS` 列出全部欄位，`load_inventory()` 對未宣告的欄位直接拒收（理由：條目照這張表一欄一欄重建，未宣告的會在寫回 store 時消失）；順序也有意義——`catalogue` 與 `publish` 把條目原樣寫回，換順序等於整份 diff。新欄位只能追加在尾端。

**`merge()` 不動既有條目。** 重跑登記只補新集數、已登記的原封不動（那是為了保住人手改過的命名）。所以「給四筆既有條目加旗標與長度」不能靠重跑登記，要有一條只填新欄位、不碰其他欄位的路。

**三支程式必須對 `smkul.csv` 逐 byte 一致**：`make_all` 寫工作區快取版、`publish` 寫 store 版、`rebuild` 只憑 store 重算並比對。表的列怎麼來，只有 `tracker.py` 一處知道。第二張表要走同一條路。

**遮罩規格隨 `cues.json` 走。** `MaskSpec.from_dict`／`to_dict` 把遮罩參數寫進 manifest 的 `mask`；`refine_cues` 從那裡重建 `MaskSpec` 再算 `text_mask`。切 cue 與精修用的遮罩因此天生一致——只要新參數也走 `to_dict`。

**圖條與遮罩是兩件事。** 圖條從 `cue.best_rgb` 照 preset 的 `lines` 切，和遮罩無關；contact sheet 由圖條拼。遮罩只餵 `Segmenter`。改遮罩不會改讀者看到的任何一個畫素。

**`verify_band` 已經量得到帶的範圍。** `band_extent()` 回傳帶在 region 內蓋住的列（083：y924..1014，region 是 y876..1014）。它只是沒被切 cue 那一步用到，`rows_fit()` 也沒拿它來驗槽。

**`verify_band` 的 no-band 回傳 0，與 OK 相同。** 批次迴圈只看離開碼——這就是 088／090 被切出雜訊 cue 的機械原因。

**news 有 `truncated` 先例**：inventory 欄位、「登記了、永不交付」、`publish` 跳過附理由、`rebuild` 不要求輸入、表中仍有一列寫「略過：<理由>」。aiyalaeho 的表刻意沒有狀態欄（歸檔 design D10：無資料的欄不養）。

**083 的 19 個 store 檔已 commit 在 Kari-SRT 子模組（HEAD 694c709）。** Claude Code 只能刪工作樹的檔，不得執行 `git rm`／`git add`；刪除後由使用者 `git add` 收入。

## Goals / Non-Goals

**Goals:**

- 剩下的影片全部做完並整批定版：本機 16 集與伺服器 3 支都走完切 cue → 讀 → ingest → 組裝，`publish` 通過、`rebuild --verify` 兩張表全綠、inventory 無 pending。
- 字幕版型異常集——凡走不了雙列雙語流程的集數，理由由檔名、量測或人工判定寫入——一經判定就分流：不切、不讀、不組裝、不進 `smkul.csv`、不擋 `publish`、**不問使用者**；列於 `smkul-字幕版型異常.csv`（`smkul.csv` 的九欄加一欄理由）；兩張表都能只憑 store 離線逐 byte 重建。
- 切 cue 前先量帶，`Segmenter` 只看帶內的列；圖條、contact sheet、讀者流程一個畫素都不變；精修自動沿用。
- `verify_band` 當場擋下「宣告的槽底下沒有帶」的集數（mismatch、指名、不切）；批次流程把 mismatch（換低版 preset 仍不符者）與 no-band 都直接記進異常表附理由，不切，批次結束時報告。
- news 的引擎行為逐 byte 不變（news 不傳帶範圍）。

**Non-Goals:**

- 不救 B 類漏切（短騎線 cue、`min_stable` 抖動）——那要 `reread`／`resplit`，另案。
- 不把單列版型當第一級公民：083 離開後語料裡沒有單列集。`slots_of()` 仍只接受兩列 preset。
- 不重切、不重讀 083；不做反向判定（檔名說無字幕、其實有）。
- 不為每集生 preset（接法 1）。
- 不在 `1-ocr/` 為字幕版型異常集放任何檔。
- 不改 news 任何程式；`probe_duration` 不搬家。

## Decisions

### D1 — 類別是「字幕版型異常」；理由三路寫入，都不問使用者

類別的定義是**功能性的**：走不了這個節目雙列雙語流程的集數。不是用「為什麼」定義它，而是用「結果」——所以理由可以有很多種，都記在同一欄。inventory 的「理由」欄非空即為異常集。

理由的三條來路（使用者裁定 2026-09-03：有異常都直接記，不問）：

1. **檔名**：字幕狀態 token 是 `無字幕` 或 `僅華語字幕` 時照錄。`catalogue._variety_after()` 本來就把這個 token 認出來再跳過，改成記下來即可；解析規則不變。這是播出端打的標籤，四筆全都有，推導決定性、可重跑、可測。
2. **量測**：切 cue 前 `verify_band` 量到 no-band → 記 `無字幕`。量到 mismatch **不可以馬上記理由**，要先走完兩層補救（兩層都是機械的，不用人判）：
   - **換 `aiyalaeho-bilingual-low` 再量**：094 就是整帶低 14 px，標準 preset 的槽界 948 剛好切在它族語列中央，換低版就 OK。
   - **`--duration 480`（取樣加倍）再量，兩個 preset 都試**：087 的兩列靠得太近，240 格的平均剖面把兩列黏成一段 `918..992`，`rows_fit` 就判不出來；480 格分得開（`918..943`／`967..1004`，OK）。**這是量出來的**（2026-09-05 實測：240 格 exit 1、480 格 exit 0），不是猜的。
   - 兩層都過不了才記 `版型不符：<verify_band 指名的第一行問題>`。

   為什麼要有第二層：087 已經交付 590 行，是好的雙語集；它當初是「靠量測和影格人工確認」繞過閘門切的（README 有記）。沒有這一層，本 change 的 SOP 會把它誤記成版型不符——實作時跑活體驗證才發現，設計原本寫「087／094 都靠低版 preset 救回來」是半錯的。
3. **人工判定**：切完看 sheet_001 判版型異常（119／122 這種檔名沒說的）→ 記 `人工判定：<一句話>`，由做批次的人（Claude Code）當場決定並寫入，不問使用者。

批次結束時的報告（`make_all` 與 `publish --check`）逐集列出異常集的理由，並標出理由不是來自檔名的（理由是 `無字幕` 而檔名字樣不是、或理由以 `版型不符：`／`人工判定：` 起頭）——讓人最後看一眼。反方向（檔名說無字幕、其實有）沒有程式守——旗標集根本不進 `verify_band`；補救是 SOP：登記時抽三格看一眼（四集已看過，寫進 README）。

已標旗標的集數，`verify_band` 不跑、`cues` 不跑。這由 SOP 與 `make_all`／`publish` 的判斷共同保證：即使有人手動切了（如 088／090 已有的雜訊 cue），`make_all` 對有旗標者也不組裝。

**不用人工註記當主要來源**（news `truncated` 那款要有人記得填）；**不靠量測判「僅華語」**（083 的華語列量起來完全合格，`verify_band` 判 ok），那條只有檔名分得出。

**括號註記不是字幕狀態。** `108-排灣語-雙語字幕（講中文居多）`、`111-…（很多人講中文）` 括號裡講的是受訪者說什麼話，不是字幕怎麼排；旗標只看字幕狀態 token（`無字幕`、`僅華語字幕`），括號內容一律不看——這和既有「括號註記不入欄位」的解析規則同一條。兩集標的是 `雙語字幕`，就是雙語集，照常切、照常讀（使用者裁定 2026-09-03）。

**讀的規矩不變，也不在本 change 內，但這裡點一次**：頂列不管夾多少漢字，整行都抄進 `formosan`，不把漢字搬去 `han`。例：`Na semekez itjen aicu a 民族議會籌備處` 是一整行族語列。108／111 這種華語重的集數會大量出現這種列，讀者判準（`scripts/aiyalaeho/brief.md`）已有此條，派工時要再提。

### D2 — 兩張表；第二張是九欄加一欄「理由」

`smkul-字幕版型異常.csv` 的前九欄與 `smkul.csv` 欄位、順序完全相同，第十欄「理由」值就是 inventory 的理由：`無字幕`、`僅華語字幕`、`版型不符：…`、`人工判定：…`。編碼（utf-8-sig、CRLF）、寫法相同，都由 `tracker.write_tracker()` 寫（fieldnames 由呼叫者給）。成果檔名欄放 `srt_name`——它是鍵（inventory、工作目錄都用它），不是檔案的存在宣告。

欄名用「理由」（使用者的用詞）：表名已經說了是「字幕版型異常」，這欄回答「為什麼」。這欄在第二張表每一列都有值，不違反「無資料的欄不養」；`smkul.csv` **不加**這欄（38 列會是空的）。

**不只加旗標不列表**：明年有人拿 42 支檔對 38 列表會去找那幾集。

列的來源：`tracker.tracker_rows(entries)` 排除有旗標者；新增 `tracker.abnormal_rows(entries)` 只取有旗標且非 pending 者，多帶理由欄。兩者共用 `tracker_row()`，差別在影片長度怎麼取（見 D3）與多一欄。

### D3 — 旗標與影片長度都進 inventory；store 別處不放任何東西

inventory 追加兩欄（尾端）：**`理由`**（字串：空＝雙語、照常；非空＝分流——這個字串就是第二張表那欄的值，「有旗標」＝非空）、**`影片長度秒`**（浮點秒數，由 ffprobe 取得、工具寫入）。`tracker.video_length()` 對有旗標者改讀 inventory 這欄，其餘照舊讀 `1-cues/` 時間軸。

欄名寫 `影片長度秒` 而不是 `影片長度`：CSV 那欄是「時:分:秒」，inventory 這欄是浮點秒數，同名不同格式，人打開 inventory.json 會看不懂——`Kari-SRT/` 的內容要人讀得懂（實作時定的，2026-09-05）。

**不放空時間軸到 `1-cues/`**：使用者裁定 store 不為這些集放東西；而且一份 `cues: []` 的檔看起來像交付品的輸入，會讓「`1-cues/` 有檔＝交付過」這個直覺失效。**不在 rebuild 時跑 ffprobe**：那會讓離線重建要影片，破壞 store 的核心承諾。inventory 本來就在 store、本來就是每集事實的所在，長度由工具寫、不手填，`rebuild` 只讀它就能逐 byte 重算第二張表——這和「影片長度 SHALL NOT 手填」的用意一致。

長度只是記錄；同 news，SHALL NOT 用它判斷任何事。

### D4 — 既有條目補欄位：`catalogue --annotate`，只填新欄、不碰其他

`merge()` 不動既有條目，所以要一條專門的路：對 inventory 內每一筆，若檔名 token 推得出理由而該欄還沒有，就填；若有旗標而長度還沒有，就 ffprobe 填。**其他任何欄位一律不碰**，順序不變，寫回時只有那幾個位置出現 diff。沒有東西要填時不寫檔。

同一條路也接受指名寫入 `--annotate '<srt_name>=<理由>'`：批次迴圈在 `verify_band` 回 2 時寫 `無字幕`、回 1（換低版 preset 仍不符）時寫 `版型不符：<第一行問題>`，人工看 sheet 判異常時寫 `人工判定：<一句話>`；都順手 ffprobe 長度。理由必須非空；不覆蓋已有的非空值（要改理由是人的事，先清空再寫）。

新登記的條目（`parse()`）直接帶這兩欄，之後不需要 annotate。116 下載後走正常登記即可。

### D5 — 083 自雙語交付撤回；store 檔由 Claude Code 刪工作樹、使用者 `git add`；證據留著

083 加旗標後，`make_all`／`publish`／`rebuild` 都把它當字幕版型異常集處理，其 `1-ocr/` 下的 19 個檔（17 個 TSV、SRT、qc）就是不該在 store 裡的東西。由 Claude Code 自工作樹刪除（`rm`，不是 `git rm`），使用者最後 `git add` 收入（使用者裁定 2026-09-03）；**順序**：先 annotate 讓 inventory 帶旗標（此時 `rebuild --verify` 對 083 已不要求輸入），再刪檔，再跑 `rebuild --verify` 確認全綠。

`kithann/out/` 的 083 工作目錄、README 記載的 25 條藏句實例與 `blind_cues` 數字都留著——那是 12.4b（B 類）的證據，與 083 是否交付無關。

**不保留 083 的華語 SRT 當交付品**：一列不能同時說「交付了」與「沒有族語文字所以不交付」；本語料的交付品是族語文字。

### D6 — 帶範圍進 `MaskSpec.band_rows`，`text_mask` 只在範圍內找字

`MaskSpec` 加 `band_rows`：region 內的列範圍 `[lo, hi)`（相對 region 頂），預設 `None`。`text_mask()` 在算完既有遮罩後，把範圍外的列一律設 False——意思是**切 cue 時只比較帶內的列，帶外的畫素不參與切點判斷**；圖條與視覺辨識不受影響。`None` 時完全不動——這是 news 逐 byte 不變的保證，用測試釘：省略時輸出與現在逐畫素相同。`from_dict`／`to_dict` 帶著它，所以 `cues.json` 的 `mask` 記著切 cue 當時用的範圍，`refine_cues` 重建 `MaskSpec` 時自動沿用，`rebuild` 原樣複製。

**不裁 region**（接法 1、或依量測自動生 preset）：region 一改，圖條就變，讀者看到的畫面就變，22 集已交付的圖條與新切的不同款；而且 A 類是切 cue 的問題不是讀的問題，修的範圍應該只碰 `Segmenter` 看到的東西。**不只在 `_feed_frames` 裁**：精修從 manifest 重建遮罩，不會知道這件事，切與精修會不一致。

用 region 內偏移而非絕對列：region 會被 `normalize_region` 對齊到偶數列，絕對值可能差一列；偏移隨 region 走，寫進 manifest 後不依賴任何外部數字。

### D7 — 帶範圍由 `verify_band` 量、寫進工作目錄；`cues` 用 `--band-rows` 讀入

`verify_band` 加 `--band-json PATH`：把 `band_extent()` 的結果（絕對列）連同判定與問題寫成 `<work>/band.json`。

**SOP（寫進 README，四步，每步都看離開碼）**：

1. `verify_band VIDEO --band-json "$W/band.json"`
2. 離開碼 **0** → `cues VIDEO --band-rows LO,HI`（絕對列，從 band.json 讀；`cli` 轉成 region 內偏移寫進 spec）→ `refine`
3. 離開碼 **1**（版型不符）→ 依序試：`--preset aiyalaeho-bilingual-low` → `--duration 480` → `--preset aiyalaeho-bilingual-low --duration 480`。任何一步回 0 就用那組參數走第 2 步（`cues` 也用同一個 preset）；四種都回 1 才 `catalogue --annotate '<name>=版型不符：<band.json 的第一行問題>'`
4. 離開碼 **2**（無帶）→ `catalogue --annotate '<name>=無字幕'`

帶蓋滿 region 的集數（37 集）傳進去的就是整個 region，行為與現在相同。

**不讓 `cues` 自己呼叫 `verify_band`**：`cues` 是 news 與 aiyalaeho 共用的引擎，`verify_band` 是 aiyalaeho 專屬判準，反向依賴。**不寫進 preset**：那是逐集的量測值，preset 是版型知識。

`band.json` 是工作目錄的快取（`kithann/`），不進 store；進 store 的是 `cues.json` 的 `mask.band_rows`。

### D8 — 槽落在帶上的守門：`verdict()` 加 `band` 參數，覆蓋率門檻 0.9

帶存在時（`score ≥ BAND_SCORE`），對 preset 宣告的每一個槽算「槽與帶重疊的列數 ／ 槽的列數」，任一槽低於 `SLOT_ON_BAND = 0.9` → mismatch，問題文字指名槽與帶的範圍（這行文字就是批次寫進理由欄的東西）。帶不存在時（no-band 路徑）不做這條，因為 `check()` 那時把帶範圍設為整個 region。

量到的兩端：083 族語槽 888..948 對帶 924..1014，重疊 24/60 = **0.40**；其餘 37 集帶蓋滿 region，每個槽都是 **1.00**；087／094 那款整帶低 14 px 的用 `aiyalaeho-bilingual-low`，帶一樣蓋滿 region、槽一樣 1.00。0.4 與 1.0 之間任何值都分得開；取 0.9 是留給「帶頂沿量測差幾列」的餘裕，不是校出來的臨界值。

`verdict(score, runs, slots, region, contrast, band=None)`：`band=None` 時行為與現在完全相同，既有 12 個 verdict 測試不動；新測試傳 `band=(924, 1014)` 期望 mismatch。`test_one_row_only_passes` 的註解「083 干焦一逝華語」改成只講 164（取樣窗內只量到一列），因為 083 從此走不到那裡。

### D9 — no-band 離開碼改為 2

`verify_band` 主程式：ok → 0、mismatch → 1、no-band → **2**。批次迴圈「離開碼非零就跳過」的既有寫法從此對 no-band 也成立；2 與 1 分開，讓人一眼看出是哪一種。這是 CLI 契約的改動，用測試釘。搭配 D1，no-band 的訊息改成「畫面量無帶——記做無字幕，莫切；尾溜ê報告會點名」，mismatch 的訊息尾加「換低版 preset 閣量一擺；猶原無合就記做版型不符」。

### D10 — 三支程式都靠 `tracker.is_abnormal()` 一個判斷

`tracker.is_abnormal(entry)` 與 `is_pending()` 並列。`make_all.make_one`：有旗標 → 狀態「字幕版型異常（列於 smkul-字幕版型異常.csv）」，不組裝。`publish.publishable`／`gate`：有旗標 → 可定版、不問 `vision_complete`、不遷時間軸；定版時清 pending（它在批次裡的工作就是被列出來）。`rebuild.check_inputs`：有旗標 → 不要求任何輸入；`verify`：多比對一張表。三支只在這一個函式上分岔，和 news 對 `truncated` 的做法同構。`make_all` 與 `publish --check` 的報告另列一段：有旗標的集數逐集印理由，理由不是來自檔名的（`無字幕` 而檔名字樣不是、或以 `版型不符：`／`人工判定：` 起頭）標出來——這就是「最後再報告」。

pending 語意：有旗標的集數登記時也是 pending；`publish` 整批定版時一併清除。工作區快取版的第二張表列出全部有旗標者（含 pending），store 版只列非 pending 者——與 `smkul.csv` 的規矩一致。

### D11 — 影片長度借 `scripts.news.refine_cues.probe_duration`，函式內 import

repo 已有兩份一模一樣的 `probe_duration`（news 的 `refine_cues`、transcode 的 `archive_batch`）。不寫第三份，借 news 那份；在 `catalogue` 內用**函式內 import**，避免登記這種輕量操作在模組載入時就拖進 numpy 等重依賴。搬到共用位置是更好的長期做法，但會動 news 的 import，本 change 不做。

### D12 — 視覺辨識批次用 `/loop 20m` 推進

做影片期間以 `/loop 20m` 持續檢查狀態（使用者裁定 2026-09-03）：每 20 分鐘看一次——已切完（`cues.json` 有 `refined`）且還沒有視覺辨識 TSV 的集數，逐集派 7 批左右的讀者（model opus、判準走 `scripts/aiyalaeho/brief.md`）；七批 TSV 都落地並經覆核就 `ingest` 再 `make_all`；額度用完就停下來等，不硬撐；做到一個段落就回報。派工前先 `ls` 確認前一集的檔案都在（收到「完成」通知不等於檔案已寫完，見 brief.md 協調者那節），重派時給不同的輸出檔名與 scratchpad。

### D13 — 088／090 的雜訊工作目錄與 098 不處理

那兩份 `cues.json` 在 `kithann/out/`（快取、gitignore），從沒進 store，加旗標後沒有任何程式會讀它們。留著或刪都行，不列為任務。098 從未切，不需動。

### D14 — 與 `parallel-corpus-quality` 並行的接觸點

**同時有三條線在跑**（2026-09-05 實地確認）：本 change、`parallel-corpus-quality`（語音側：`scripts/asrmt/`、`scripts/news/asrmt_*`、`Kari-SRT/news/2-asr/`）、`half-res-mask-and-slot-crop`（半解析遮罩＋新聞圖條列位裁切，`scripts/ocr/cuelib.py`／`cli.py`／`sheets.py`、`scripts/news/refine_cues.py`／`presets.json`／`vision_tools/prompt.py`）。三條都可並行，接觸點如下。

**`half-res-mask-and-slot-crop` 不是空目錄，本 change 不刪它**（原本寫「建議刪除」是錯的，2026-09-05 更正）。它的 `frame_mask(scale)` 疊在本 change 的 `MaskSpec.band_rows` 上面，所以它的程式改動排在 1.2／1.4 之後；兩邊約定動 `scripts/ocr/` 那幾支之前互相通知、被通知的一方 `/loop 20m` 等。

**`json.dump` 的四處已由 `parallel-corpus-quality` 改完**（`cli.py` 的 manifest 與 texts、`transcripts.py` 的 existing 與 verified，全部 `indent=2, sort_keys=True`），本 change 不重複改，只在動這兩支之前重讀。與 `parallel-corpus-quality` 的接觸點如下。

1. **同一個檔兩邊都要改**：`scripts/ocr/cli.py`（他們 8.1 改全 repo `json.dump` 參數，含 `cli.py:158` 的 manifest；我 1.4 加 `--band-rows`）與 `scripts/README.md`（他們補四支新模組，`test_readme_covers_scripts` 逼的；我加一行參數說明）。協議：同一個檔一次只有一條線動、動手前重讀；我動的時候通知對方 `/loop 20m` 等我，對方動的時候我 `/loop 20m` 等他。其餘程式檔互不相碰（他們的 design 明文不碰 `scripts/aiyalaeho/`）。
2. **spec 同一份不同條**：兩邊都對 `srt-data-store` 出 delta，但 MODIFIED／ADDED／REMOVED 的九個要求標題查過各不相同、都在主 spec。誰先歸檔誰先合，後歸檔的重跑 `openspec validate --strict`。
3. **資料層的隱藏衝突——我這邊要改**：他們的 `redump_store` 會把 `1-ocr/1-cues/` 重排成 `indent=2, sort_keys=True`；`aiyalaeho/1-ocr/1-cues/` 現在只有 068 一個檔，是 `cli.py` 用 `indent=1` 寫的。而 `publish.main` 對**每一個** ready 的集（含已定版的 068）都會 `publish_one` → `shutil.copy2` 把工作目錄的 `cues.json` 再蓋一次進 store——會用 `indent=1` 蓋回去，兩邊來回翻。

   **使用者裁定 2026-09-05：`json.dump` 照他們那邊的規格改。** 也就是本 change 動到的每一支寫 JSON 的程式，一律 `ensure_ascii=False, indent=2, sort_keys=True`（JSONL 不 indent，其餘照用）：`scripts/aiyalaeho/` 的 `publish`（inventory）、`catalogue`（inventory）、`make_srt`／`make_all`（qc），以及**影像側工作目錄那三支** `scripts/ocr/cli.py`（manifest、transcripts）與 `scripts/ocr/transcripts.py`（transcripts、verified）——那三支現在是 `indent=1`、沒有 `sort_keys`，而 `1-ocr/1-cues/` 的內容就是從那裡來的。`publish_one` 不再 `copy2`，改讀 JSON 再以同一組參數寫出，讓 store 內的排版由本程式決定而非複製來源。inventory 的鍵序從此是字母序（`INVENTORY_FIELDS` 只管重建 dict 時的欄位集合，不再管檔案裡的鍵序），這是一次性的整檔 diff，之後就穩。`rebuild` 讀的是內容，不受影響。與另一條線的 8.1 有重疊，照第 1 點的協議對時。
4. **驗收互相踩**：`news` 的 `rebuild --verify` 是兩邊的驗收。他們 1.3（`mv 3-srt-raw 2-srt-raw`）到 4.3（`coaxial` 改完）之間 news verify 會紅；我的 1.5、10.4 若在那個窗口跑會誤判是我弄壞的。反過來，我若動到 `text_mask` 的預設行為，他們的 9.2 會紅。**協議（使用者裁定 2026-09-05）：對方在改的時候，我用 `/loop 20m` 等他；我在改共用檔的時候，通知他也 `/loop 20m` 等我。** 不互相打斷、不硬跑；紅的時候先看 DIFFERS 指名哪一側的檔。
5. **額度是同一個帳號的**。他們 10.2：59 集、100 條一批、Sonnet 全判再 Fable 判三成，幾百次 subagent；我 9.2：16 集 × 7 批 Opus 約 112 次，加 119／122。之前單一 session 撞過 session limit（105 b02 半路中斷）。**使用者裁定 2026-09-05：不用怕，兩邊都有 `/loop 20m`，token 盡量用。** 所以不排隊、不互讓——撞到上限就由 `/loop` 等額度回來自動續跑，做到一個段落就回報。

CPU 與磁碟不衝突：他們的 mt 步是網路單併發、judge 是 subagent；我的 `verify_band` 16 集各約 41 秒、不重切。Kari-SRT 子模組兩邊路徑分開（`news/2-asr/` 對 `aiyalaeho/`），刪檔都留給使用者 `git add`，分得開。

## 檔案樹

`P` 產生者、`I` 輸入。只列本 change 新增或改動的檔；既有檔案的既有角色見歸檔 design。

```
scripts/ocr/
├── cuelib.py                 MaskSpec.band_rows（None＝不裁）；text_mask 範圍外設 False；to_dict／from_dict 帶著
└── cli.py                    cues --band-rows LO,HI → 轉 region 內偏移 → spec.band_rows（進 cues.json 的 mask）

scripts/aiyalaeho/
├── paths.py                  INVENTORY_FIELDS 尾端追加：理由、影片長度秒；
│                             ABNORMAL_STORE／ABNORMAL_CACHE（smkul-字幕版型異常.csv 的兩個位置）；band_json(srt_name)
├── catalogue.py              parse()：字幕狀態 token → 理由欄；有旗標即 ffprobe 長度（D11）
│                             --annotate：既有條目只補這兩欄；'<srt_name>=<理由>' 收量測／人工分類（D4）
├── verify_band.py            verdict(…, band=None) 槽落帶上守門（D8）；main：no-band → 2（D9）、
│                             訊息說記做無字幕／換低版 preset；--band-json 寫 band.json 含問題行（D7）
├── tracker.py                is_abnormal()；tracker_rows() 排除旗標者；abnormal_rows() 多帶理由欄；
│                             video_length() 對旗標者讀 inventory；write_tracker 接 fieldnames
├── make_all.py               make_one() 旗標者不組裝、回狀態；寫兩張快取表；尾段報告量測分類者
├── publish.py                旗標者不問 vision_complete、不遷時間軸；定版寫兩張表、清 pending；--check 報告量測分類者
├── rebuild.py                check_inputs 旗標者免輸入；verify 比對兩張表
└── README.md                 判定表（098 MISMATCH）；素材分類（083 入字幕版型異常組）；
                              SOP：旗標 → verify_band --band-json → cues --band-rows → refine；兩張表說明

tests/ocr/
└── test_cuelib_band_rows.py  band_rows 省略時 text_mask 逐畫素同現在；給範圍時範圍外全 False；
                              from_dict／to_dict 來回；cues.json 舊檔（無此鍵）照讀

tests/aiyalaeho/
├── test_paths.py             兩個新欄位在尾端、可省略；ABNORMAL 路徑；band_json 路徑
├── test_catalogue.py         -無字幕／-僅華語字幕 → 理由；-雙語字幕 → 空；長度由 ffprobe（mock）；
│                             --annotate 只補空欄、其他欄逐字不動、無事可做不寫檔；
│                             '<srt_name>=<理由>' 指名寫入、空理由拒絕、不覆蓋非空值
├── test_verify_band.py       band=(924,1014) 對標準槽 → mismatch 指名族語槽；band 蓋滿 → 既有案例照舊；
│                             no-band 離開碼 2、訊息說記做無字幕；--band-json 含 band、state、problems
├── test_tracker.py           is_abnormal；旗標者不在 smkul 列、在異常表列、前九欄同、第十欄理由、成果檔名＝srt_name；
│                             長度取 inventory；pending 旗標者只在快取版
├── test_publish.py           旗標者不擋、不組裝、不遷時間軸、pending 被清；兩張表落 store；--check 報告點名量測分類者；
│                             既有兩個 no_subtitle 測試改寫成旗標版；test_an_episode_with_no_cues_is_complete 保留
└── test_rebuild.py           旗標者免輸入；兩張表逐 byte；第二張表被改會報 DIFFERS；既有 no_subtitles 測試改寫

Kari-SRT/aiyalaeho/                                     P                 I
├── inventory.json            四筆加理由與長度          catalogue --annotate   檔名、ffprobe、verify_band、人工判定
├── smkul.csv                 不含旗標者                publish            inventory、1-cues
├── smkul-字幕版型異常.csv          新檔                      publish            inventory（旗標、長度）
└── 1-ocr/…/開會了_083_*      自工作樹刪除              Claude Code rm；使用者 git add   —

kithann/out/aiyalaeho/<srt_name>.work/                  P                 I
├── band.json                 量到的帶範圍與判定        verify_band --band-json   母帶
└── cues.json                 mask.band_rows 多一鍵     cues --band-rows   band.json 的範圍
```

## Risks / Trade-offs

- [檔名說有字幕、其實沒有] → `verify_band` 量到 no-band 即自動記進異常表（D1、D9），不切；批次結束報告點名。
- [一集真有字幕卻被誤判 no-band 或 mismatch，靜靜被擱下] → no-band 的判準是「無帶且剖面平坦」，量到的分布有帶 2.0–22 倍、無帶 0.8–1.0，中間空；mismatch 先換低版 preset 再判（087／094 那款不會被誤歸）；加上報告點名、SOP 要求對量測分類者抽三格看——不是無人看，只是看的時間點從「擋住當下」改到「批次結束」。
- [人工判定的理由品質參差] → 理由欄是自由文字，寫的人是做批次的 Claude Code；SOP 要求一句話寫「看到什麼」（如「sheet_001 兩列皆空、帶色不對」），不寫推測。
- [檔名說無字幕、其實有] → 沒有程式守。四集已抽格看過（README 記錄）；SOP 要求登記新的旗標集時看三格。這是接受的取捨——反向自動判定需要能分「僅華語」與「雙語」的量測，目前沒有。
- [`band_rows` 讓 news 的遮罩變了] → 預設 `None` 完全不動遮罩，測試釘逐畫素相同；驗收跑 news 的 `rebuild --verify`。
- [守門對整帶漂移的集數誤擋] → 37 集帶都蓋滿 region，087／094 走低版 preset 也是；門檻 0.9 對量到的 0.40／1.00 有兩邊餘裕。若真有帶只蓋一部分又確實兩列的集數出現，那是新版型，該擋。
- [先刪 083 的檔再 annotate] → `rebuild --verify` 會對 083 報缺件。順序寫進任務：annotate 在前。
- [有人忘了傳 `--band-rows`] → 對 37 集無影響（帶蓋滿）；`cues.json` 的 `mask` 會看得出有沒有帶範圍；README SOP 寫成一條指令串。
- [`--annotate` 誤動其他欄] → 測試逐字比對其他欄與順序；無事可做時不寫檔。
- [116 尚未下載，長度取不到] → 未登記就沒有條目；下載後走正常登記，`parse()` 當場 ffprobe。
- [兩張表列數對不上 inventory] → 驗收條件：`smkul.csv` 列數 ＋ `smkul-字幕版型異常.csv` 列數 ＝ 非 pending 條目數；`rebuild --verify` 兩張都比。

## Migration Plan

1. 程式與測試（TDD，順序見 tasks）：`cuelib`／`cli` → `paths` → `catalogue` → `verify_band` → `tracker` → `make_all`／`publish`／`rebuild`。
2. `catalogue --annotate`：083／088／090／098 四筆得旗標與長度（088 2969.97、090 3000.00、098 2997.83；083 由 ffprobe 取）。`rebuild --verify` 此時對 083 不再要求輸入。
3. Claude Code 自工作樹刪除 083 的 19 個檔與 `openspec/changes/half-res-mask-and-slot-crop/` 空目錄；`rebuild --verify` 全綠；使用者最後 `git add`。
4. 其餘 16 集依新 SOP 切（`verify_band --band-json`，回 2 就 `catalogue --annotate <name>=無字幕` 跳過 → `cues --band-rows` → `refine`），並以 `/loop 20m` 推進視覺辨識（D12）；12.2 三支伺服器檔下載、比位元組數；混雜兩支切前看 sheet_001；116 登記為第五筆旗標集。
5. `make_all` → `publish`（報告點名量測分類者）→ `rebuild --verify`（兩張表）→ 總驗收；文件更新。

回退：旗標欄位可省略，`band_rows` 預設 `None`——不填就是現在的行為；`smkul-字幕版型異常.csv` 不存在時 `rebuild` 只比一張表（過渡期），定版後必須存在。

## Open Questions

- `SLOT_ON_BAND` 取 0.9 是餘裕不是校準；若之後量到帶頂沿有系統性的一兩列誤差，調到 0.8 也不影響任何既有集數（量到的兩端是 0.40 與 1.00）。不改 spec、不改任務。
- `probe_duration` 何時搬到共用位置：本 change 借用即可；等 news 那邊有理由動 import 時再一起做。
