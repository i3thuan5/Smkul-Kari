## Context

動機見 proposal.md〈Why〉。這裡只記做法要面對的現況：

`scripts/transcode/encode_master.sh` 現在是「一支包全部」——先跑一趟 ffmpeg 比對兩條音軌的 md5，再跑一趟編碼，最後再跑一趟驗證。三趟都完整讀來源。它的唯一呼叫端 `archive_batch.py` 把它當黑盒子：`subprocess.run(["bash", ENCODE_SCRIPT, src, partial], check=True)` 之後就當一切辦妥。

音軌的處理寫死在 bash 裡，而且只 map `a:0` 與 `a:1`：

```bash
maps=(-map 0:v:0 -map 0:a:0)
if [[ "$tracks" -ge 2 ]] && [[ "$keep_second" -eq 1 ]]; then
  maps+=(-map 0:a:1)
fi
```

`tracks` 有算，但只有等於 2 才進入比對分支；三軌以上時第三條之後完全不會出現在輸出裡，也不會有任何訊息。

`scripts/news/sftp.sh` 已經解掉密碼那一題：`SSH_ASKPASS` + 密碼檔，路徑逐個檢查引號與控制字元，另有 `SFTP_DRY_RUN=1` 可離線驗指令拼法。這條不重做。

實測資料（2026-09-05，對 63 支既有封存全數 ffprobe 加轉檔日誌）：全部音軌都是 mono／48 kHz／24-bit，沒有多聲道；35 支一條音軌、28 支兩條，沒有超過兩條的。兩軌不同的那 28 支，抽 `20210210_041_午間_Cou_鄒` 第 600–620 秒共 96 萬個樣本逐一比對：28.07% 完全相同，差值全是 24-bit LSB 的整數倍、最大 44 LSB（−105.6 dBFS），`corr(差值, 訊號) = 0.0002`（不是增益差），訊號大時平均差 1678、小時 669（訊號相依的捨入雜訊）。也就是同一份聲音，差在最低幾個位元。

## Goals / Non-Goals

**Goals:**

- 來源檔案在一次封存中只被完整讀取一次。
- 音軌的去留變成可單元測試的純函式，兩個呼叫端共用一份。
- 隨身硬碟批次不依賴任何登記簿，插上就能跑完拔掉。
- `tests/transcode/` 進 CI。

**Non-Goals:**

- 不換視訊編碼器。硬體加速（VAAPI）的畫質沒有經過字元錯誤率驗證，既有的 CRF 18–28 零錯誤結論只適用 libx264。
- 不放寬音訊相符的判準。
- 不在單一執行內做平行。
- 不碰 `/home/news/mkv/` 底下任何東西，也不改既有封存的命名。
- 不處理「這支影片是哪一集」。

## Decisions

### 一趟 ffmpeg，多個輸出

ffmpeg 一次輸入可以掛多個輸出，來源解碼一次、餵給多個編碼器。把來源音軌的 md5 做成額外輸出，就在編碼那一趟順便算完：

```bash
ffmpeg -v error -stats -i "$SRC" \
       -map 0:v:0 -map 0:a:0 -map 0:a:1 \
       -c:v libx264 -preset medium -pix_fmt yuv420p -crf 23 \
       -c:a flac -compression_level 8   "$WORK/x.all.mkv" \
       -map 0:a:0 -f md5 "$WORK/x.src-a0.md5" \
       -map 0:a:1 -f md5 "$WORK/x.src-a1.md5"
```

音軌的 `-map` 與 md5 輸出都依實際軌數展開，不寫死兩條。

**替代方案**：維持三趟不動——最省事，但在 USB 碟上每支多讀約 38 GB。先比對再編碼（兩趟）——省一趟，但仍要為了一個只影響「留幾條音軌」的決定，先完整讀一次來源。

**代價**：md5 輸出多佔幾乎可以忽略的 CPU（雜湊比 x264 便宜幾個數量級），但**排版**上這條指令變長，錯一個 `-map` 就會安靜地算到錯的軌。所以參數組裝要能 dry-run 並有測試（見〈bash 只兜參數〉）。

### 驗證的比對對象隨音訊編碼路徑而定

沿用既有結論，不改：來源是整數 PCM 時走 `-c:a flac`，比對**解碼後的取樣**（那正是語料實際訓練用的東西）；來源解碼出浮點時走 `-c:a copy`，比對**封裝資料**而非解碼取樣——Matroska 不帶 mp4 edit list 那種 priming delay 側資訊，解碼一個原封搬運的 AAC 會在開頭多一個編碼器 priming frame，之後每個取樣都對不上，但搬運的位元組其實完全相同。

### 拆三段：bash 兜參數、Python 決策、remux 收尾

```
              ┌─────────────────────────────────────────────┐
來源 .mxf ───▶│ encode_master.sh    一趟 ffmpeg，讀來源 1 次│
（慢速媒體）   │  視訊 libx264、音訊 N 軌全留、順便吐 N 個   │
              │  來源音軌 md5                               │
              └─────────────────────────────────────────────┘
                     │                    │
                <名>.all.mkv        <名>.src-a0.md5 … src-aN.md5
                     │                    │
                     ▼                    ▼
              ┌─────────────────────────────────────────────┐
              │ audio_tracks.py     純函式，零 I/O          │
              │  輸入：來源 md5 們、封存 md5 們             │
              │  輸出：① 逐位元相符嗎 ② 哪幾軌彼此重複     │
              │        ③ 該留哪幾軌 ④ 給人看的一句話       │
              └─────────────────────────────────────────────┘
                     │
              不相符 ─┴─▶ 這支失敗，寫進 log，跳下一支
                     │ 相符
                     ▼
              ffmpeg -c copy 只留該留的軌 ──▶ <名>.mkv
```

N 軌的判斷邏輯（哪幾條互為重複、三軌中兩條相同要留幾條）在 bash 裡是巢狀陣列迴圈，寫得出來但測不動；在 Python 裡是一個吃 md5 列表、吐索引列表的純函式，離線可測。反過來，ffmpeg 的參數組裝留在 bash——既有的編碼參數與它們的理由（每一行都有實測來歷）已經在那支腳本的註解裡，搬進 Python 只會讓那段歷史離它描述的指令更遠。

重新封裝是 `-c copy`，在 SSD 上讀寫一次 2.5 GB，秒級。

**替代方案**：全部搬進 Python（`archive_batch.py` 直接組 ffmpeg 參數）——少一層，但要把那批帶實測註解的參數搬家，而 shellcheck 對 bash 的把關也就沒了。全部留在 bash——N 軌邏輯繼續測不動，正是這次要修的問題之一。

### 判準維持逐位元，不改成門檻

那 28 支兩軌不同的差在 −105 dBFS 以下，人耳完全聽不到，看起來很像可以再省一軌（FLAC 後約 0.28 GB × 28 ≈ 7.8 GB）。不做。

理由：一旦引入「差多少算相同」就得回答門檻是多少，而那個數字沒有人量過，訂錯的後果是靜靜丟掉一條真正不同的聲音——而雙軌放不同語言（主聲道／國際聲、族語／華語）在廣播界是標準做法之一。隨身硬碟這批是新聞以外的檔案，來源更雜，風險比新聞那批高。7.8 GB 換這個保證，划算。

改為在對照表記下「兩軌相同／不同」，把判斷留給日後真的要用音訊的人。

### `tools/mxf2mkv/` import `scripts.transcode.audio_tracks`

方向是 `tools/` → `scripts/`（使用者裁定 2026-09-06）。刻意排除的依賴是**登記簿類**的（目錄、`smkul.csv`、inventory——那些會逼人先登記才能轉檔），不是同 repo 內共用一份純函式。純函式零 I/O、零設定，import 它不會把任何登記需求帶進來。

**替代方案**：把純函式放 `tools/mxf2mkv/`、讓 `scripts/transcode/` 反過來 import——一樣只寫一次，但會讓新聞封存這條穩定的線去依賴一支新工具，方向不合常理。

### 工作目錄用 `mkdtemp`，不是固定路徑加鎖

```python
tempfile.mkdtemp(prefix="mxf2mkv-", dir="/tmp")   # /tmp/mxf2mkv-a7f3k9
```

要同時對 2–3 個來源資料夾各起一個執行（來源在不同的碟上）。固定路徑就得處理互斥，而 `archive_batch.py` 已經有一份 `O_EXCL` 鎖的實作與它的血淚註解——那是為了「同一集不能被兩個行程同時編碼」而存在的，跟這裡「不同執行不要互相覆蓋」是不同的問題，用不同的解法比較誠實。`--work` 仍可指定固定路徑（要塞到別的碟時用）。

正常結束刪掉；有失敗則保留並印路徑，那是唯一還留著半成品可看的地方。

### 紀錄落點：外層只有來源名

```
kithann/mxf2mkv/2月原始mxf檔/
├── 0905-2017_2月原始mxf檔.log
├── 0905-2017_2月原始mxf檔.manifest.json
├── 0906-0930_2月原始mxf檔.log             ← 第二次跑，同一個資料夾
└── 0906-0930_2月原始mxf檔.manifest.json
```

外層若帶時間，每跑一次就是一個新資料夾，反而達不到「同一個來源的歷次執行放一起」（使用者裁定 2026-09-06 選此方案）。檔名已帶完整日期時間，外層不必重複；檔名裡再帶一次來源名看似冗餘，但檔案被拖出資料夾時仍認得出自己。

時間用 CST。建檔用 `O_EXCL`，撞名加 `-2`、`-3` 後綴。

工作目錄底下的中間產物不用「編號階段」命名，改用同一個字首加後綴（`.all.mkv`、`.src-a0.md5`、`.mkv`）。編號階段目錄是給**留著給人讀**的產出用的；這裡每一支的中間產物在上傳成功後就全部刪除，活不到有人去讀它，多一層目錄只是多一層要清的東西。

### 測試分兩層，因為 CI 沒有 ffmpeg

`tox -e unittest` 的環境只裝 numpy 與 Pillow，CI 跑得到；`tox -e e2etest` 需要系統套件（ffmpeg 等），只在本機或裝了 apt addons 的環境跑。所以純邏輯（路徑對應、掃描與跳過、N 軌決策、紀錄命名、失敗續跑）全部進 `unittest`，要真的跑 ffmpeg 的端到端進 `e2etest`。

`tests/transcode/` 這次一併加進 `unittest` 的 discover 清單——它現有的 46 個測試不在裡面，從來沒在 CI 跑過，而這次正要動它測的那支腳本。

端到端用的小 mxf 由 ffmpeg 自己的 lavfi 在跑測試時合成，跑完刪除，git 不留任何 mxf：

實際可用的指令與它的三個硬性條件（48 kHz、`yuv420p`、廣播標準影格率）見下面 Risks 那節——第一次試就是踩在取樣率上。

這樣連測試都不需要 Python 套件，`requirements.txt` 整份不必存在。

### 上傳到暫名再改名，因為「跳過」的判準沒有別的做法

實作到 `run.py` 時才發現原本規劃的判準做不出來：跳過要比對「遠端位元組數 ＝ 本機成品位元組數」，但**成品幾個位元組要轉完才知道**，而轉檔正是跳過要省下的那二十分鐘。`archive_batch.py` 沒有這個問題，因為它留著一份本機封存可以量；`tools/mxf2mkv/` 上傳完就刪，沒有東西可量。

改成：

```
put    → /home/mkv-raw/2月原始mxf檔/a.mkv.partial   斷在這裡只會留這個名字
比對位元組數                                        對不上就停在這裡，不改名
rename → /home/mkv-raw/2月原始mxf檔/a.mkv           這個名字出現＝完整
```

判準變成「最終名稱存在且非零位元組」，而它是**真的**成立——半截的上傳佔不到最終名稱。位元組數的檢查沒有拿掉，只是移到改名之前當閘門。這與 `archive_batch.py` 在本機做的事同構（`.partial.mkv` → `os.rename`）。

代價是 `scripts/news/sftp.sh` 要加一個 `rename` 動詞（原本只有 `get`／`put`／`mkdir`／`ls`／`-`）。照現有樣式寫，兩個路徑都過 `check_path`——**不可以**改走 `-` 批次模式，那正是它擋引號注入的地方。

`rename` 刻意**不加** `mkdir` 那個開頭的 `-`（sftp 的「這行失敗也繼續」）。`mkdir` 需要它是因為「資料夾已經在了」是正常狀況；`rename` 相反，它失敗代表最終名稱沒出現、這支其實沒傳成功，而呼叫端正是拿「最終名稱在不在」當完成的證據——吞掉這個錯誤會讓下一次執行跳過一支根本不在的檔案。

**替代方案**：遠端存在就跳過（不動 `sftp.sh`，但半截上傳會被當成做完，正是要避免的事）；把成品大小記進 manifest 供下次比對（不動 `sftp.sh`，但第一次跑完前無從比對，且 `kithann/` 不進 git、換機器就失效）。使用者裁定 2026-09-06 選改名這條。

### SFTP 沿用 `sftp.sh`，不引入 paramiko

密碼規定要求密碼不進指令列、不進我的 context；`sftp.sh` 已經用 `SSH_ASKPASS` 加密碼檔解掉，並逐個檢查路徑的引號與控制字元。paramiko 要把密碼交進 Python 變數，而且是新依賴——《採購安全說明書》的「裝得越少越好」與這裡的密碼要求都指向同一個答案。測試用它既有的 `SFTP_DRY_RUN=1` 驗指令拼法，不連線。

### 遠端根 `/home/mkv-raw`，不在 `/home/news/` 底下

既有封存是 `/home/news/mkv/<年-月>/<srt_name>.mkv`（按播出月分層、按集數命名）。這批是新聞以外的檔案，沒有播出月也沒有集數，放同一層會讓兩套命名混在一起（使用者裁定 2026-09-05）。等日後認完 catalogue 再 rename 或 mv。

### 不提供 `-j`

來源通常是單顆外接硬碟，同時讀兩支數十 GB 的檔案互相搶 I/O，比逐支慢。要平行時對不同來源資料夾各起一個執行即可——那是不同的碟，`mkdtemp` 已經讓它們互不干擾。

## 檔案樹

每一項標明由誰產生、吃什麼輸入。

```
scripts/transcode/
├── encode_master.sh          【改】人手維護
│     輸入：來源影片路徑、輸出目錄、CRF、像素格式
│     產出：<名>.all.mkv（含來源全部音軌）＋ <名>.src-a<i>.md5（每軌一個）
│     BREAKING：不再自己判斷音軌去留，也不再自己驗證
├── audio_tracks.py           【新】人手維護
│     輸入：來源音軌 md5 列表、封存音軌 md5 列表
│     產出：純函式回傳值——是否逐位元相符、重複分組、該留的軌索引、
│           一句給人看的說明（「兩軌相同，留一軌」）
└── archive_batch.py          【改】人手維護
      _encode() 改走三段流程；其餘（SFTP 抓檔、時長比對、O_EXCL 鎖、
      上傳與刪除）不動

tools/mxf2mkv/
├── __init__.py               【新】空
├── __main__.py               【新】CLI 進入點
│     輸入：命令列參數
│     產出：離開碼；驅動 run.py
├── walk.py                   【新】
│     輸入：來源根路徑、遠端根
│     產出：[(來源絕對路徑, 遠端絕對路徑)]，過濾非 .mxf、拒絕危險路徑
├── upload.py                 【新】
│     輸入：本機成品路徑、遠端路徑
│     產出：逐層 mkdir → put → 讀遠端位元組數比對；不符則丟錯
├── report.py                 【新】
│     輸入：來源根名稱、執行時間、每支的結果
│     產出：kithann/mxf2mkv/<來源名>/<MMDD-HHMM>_<來源名>.log
│           kithann/mxf2mkv/<來源名>/<MMDD-HHMM>_<來源名>.manifest.json
├── batch.py                  【新】
│     輸入：來源根、遠端根、工作目錄、紀錄目錄、時戳、逐支的工作函式
│     產出：掃描 → 逐支呼叫 → 失敗記錄後續跑 → 寫 manifest；
│           回傳整批結果（entries、failed、exit_code、keep_work）
│     （原本規劃無這支，實作時發現「失敗續跑」這條規矩愛佮
│       命令列剖析分開才測會著）
├── run.py                    【新】
│     輸入：一組 (來源, 遠端)、工作目錄
│     產出：把 encode_master.sh → audio_tracks → remux → upload 串起來，
│           回傳這一支的結果紀錄
└── README.md                 【新】人手維護：這是什麼、怎麼跑、產出在哪

tests/mxf2mkv/                【新】進 tox -e unittest
├── __init__.py
├── test_paths.py             walk.py 的路徑對應、副檔名過濾、危險路徑
├── test_scan.py              掃描順序、遠端位元組相符則跳過、半截檔重做
├── test_audio.py             audio_tracks.py：1 軌／2 軌相同／2 軌不同／
│                             3 軌中兩條相同／不相符
├── test_report.py            紀錄落點與命名、撞名加後綴、JSON 排版
└── test_failure.py           一支失敗記錄後續跑、離開碼

tests/transcode/
├── test_archive_batch.py     既有 46 個，這次進 CI
└── test_encode_master.py     【新】ffmpeg 參數組裝（dry-run，不跑編碼）：
                              N 軌的 -map 與 md5 輸出展開對不對

tests/e2e/
└── test_mxf2mkv_roundtrip.py 【新】跑測試時以 ffmpeg lavfi 合成 3 秒、
                              兩軌的小 mxf，跑完整條，斷言音訊逐位元相符、
                              保留軌數正確；產物跑完刪除

tox.ini                       【改】unittest 加 discover tests/transcode、
                              tests/mxf2mkv
```

工作目錄（`/tmp/mxf2mkv-<random>/`，每次執行由 `__main__.py` 建立，上傳成功即清）：

```
<名>.all.mkv        encode_master.sh 產；輸入為來源 .mxf
<名>.src-a<i>.md5   encode_master.sh 同一趟產；每條來源音軌一個
<名>.mkv            remux 產；輸入為 .all.mkv ＋ audio_tracks 決定的軌索引
```

## Risks / Trade-offs

**ffmpeg 的 MXF muxer 對輸入挑剔，合成 fixture 不一定一次成功** → 已於 2026-09-06 驗證過，**做得出來，維持用 mxf，不需要 `.mov` 退路**。失敗時的訊息是 `Could not write header (incorrect codec parameters ?): Operation not permitted`，看起來像權限問題其實不是，所以三個硬性條件記在這裡：

- **音訊取樣率必須是 48 kHz。** `sine` 預設 44100，直接讓 muxer 寫不出 header——這是最容易踩到的一個。
- **視訊要 `yuv420p` 且影格率為廣播標準值**（25 或 29.97）。
- 音軌要 mono（`-ac 1`），與母帶的實際情形一致。

可用的合成指令與實測大小（2 秒、320x240、25 fps、`-b:v 500k`）：

```bash
ffmpeg -f lavfi -i testsrc2=s=320x240:r=25:d=2 \
       -f lavfi -i "sine=f=440:d=2:r=48000" \
       -f lavfi -i "sine=f=660:d=2:r=48000" \
       -map 0:v -map 1:a -map 1:a \
       -c:v mpeg2video -pix_fmt yuv420p -b:v 500k \
       -c:a pcm_s24le -ar 48000 -ac 1 -f mxf same.mxf
```

同一個 `sine` map 兩次就得到逐位元相同的兩軌（實測兩軌 md5 皆為 `957e0a09…`），map 兩個不同的 `sine` 就得到不同的兩軌。三個 fixture 各約 0.9–1.2 MB：`same.mxf`（兩軌相同）、`diff.mxf`（兩軌不同）、`three.mxf`（三軌，前兩條相同）。

**`encode_master.sh` 的契約改變會影響已跑過 63 支的新聞封存** → 兩個呼叫端一起改、一起測；`tests/transcode/` 同時進 CI，這樣往後改壞了會當場被抓到。驗收照 CLAUDE.md：`rebuild --verify`、`flake8`、`unittest`、`name_catalogue --check`，另加 `shellcheck`（`shellcheck.sh` 會掃到新加與改動的 `.sh`）。

**多輸出的 `-map` 展開錯了會安靜地算到錯的音軌指紋** → 指紋算錯的下場是誤判「不相符」而讓好檔案失敗（吵鬧，會被發現），或誤判「重複」而丟掉一條不同的音軌（安靜，很糟）。所以 `test_encode_master.py` 專門測參數展開，端到端測試再用真的三軌來源驗一次保留軌數。

**`kithann/` 在 `.gitignore` 第 177 行，紀錄與對照表不進 git** → 換機器就沒了。用途是本機除錯與日後接目錄，符合預期；已在 proposal 記明，不另做處理。

**`/tmp` 空間** → 使用者已確認是 ext4 不是 tmpfs，所以不吃記憶體。單支峰值約一個 `.all.mkv` 加一個 `.mkv`（約 5 GB），同時跑 3 支約 15 GB。失敗時工作目錄刻意保留，長期跑下來可能累積；紀錄會印出路徑，由使用者自行清理。

**遠端 `/home/mkv-raw/` 是新目錄，權限未經驗證** → 第一次上傳就會知道。逐層 `mkdir` 失敗時該支記為失敗並繼續，不會整批停住，但若是權限問題會每一支都失敗——紀錄裡會看得很清楚。

## Migration Plan

沒有資料要搬。既有的 `/home/news/mkv/` 底下 63 支封存完全不動，也不需要重新產生：這次改的是**產生方式**（讀幾次來源、由誰決定音軌去留），不是**產出內容**（同樣的 CRF 23／`yuv420p`／FLAC、同樣的逐位元判準）。

回退方式是 `git revert` 這個 change 的 commit；`encode_master.sh` 與 `archive_batch.py` 的舊契約會一起回來，兩者本來就是一起改的。

## Open Questions

無。三層架構（資料落點、tests、程式分層）已於 2026-09-05 至 09-06 逐層經使用者確認。
