# 族語新聞 burned-in 字幕 → SRT

把原視族語新聞（`族語新聞/` 的 mp4 與 2 月的 mxf 母帶）裡燒在畫面上的
中文字幕抽成 SRT。影像處理引擎是 `scripts/subs2srt/`（做法說明見
`.claude/skills/video-subtitle-srt/SKILL.md`）；這個目錄放這批語料專屬的
編排：檔名對應、preset、路徑設定（`paths.py`）。

三個位置各司其職：

- **這裡（`scripts/news/`）**：程式與 `presets.json`、`inventory.json`。
- **`Kari-SRT/` submodule**：資料正本——交付 SRT、`smkul.csv`、每集時間軸
  `cues/`、視覺逐字稿 `vision/`、`vision-rtf/`。僅靠主 repo + Kari-SRT
  即可離線重建全部 SRT：`python3 -m scripts.news.rebuild --verify`
  （或 `tox -e subtitle-rebuild`）。**每次程式修改完在本機跑一次**——
  Kari-SRT 是私有 repo，CI 抓不到 submodule，這條不進 CI。
- **`kithann/`**（gitignore）：來源資料與可重生快取（work dir、log）。

### `kithann/` 每次執行後會有什麼

不算舊資料（FFmpeg／kaldi／開會了／ilrdf-corpus 那些既有素材），pipeline
往後每跑一次，只會在 `kithann/out/` 底下寫東西，而且全部是快取／日誌，
沒有任何一份是正本：

| 路徑 | 何時產生 | 內容 | 性質 |
|---|---|---|---|
| `out/mxf/<slug>.work/` | `fetch_sftp.sh`／`run_cues.sh` 跑 `cues` 步驟 | `cues.json`（時間軸）、`sheets.json`、`sheets/*.png`、`strips/*.png` | 快取，遷入 Kari-SRT 後可刪 |
| `out/mxf/<slug>.work/transcripts.json` | 有跑 `ocr --engine tesseract`（現在只當 fallback，非預設）| tesseract 辨識草稿 | 快取，不供字，可刪 |
| `out/mxf/<slug>.work/verified.json` | `ingest.py` 匯入 TSV 之後 | 哪些 cue 已核實過的文字 | 快取，可從 Kari-SRT 的 vision TSV 重建 |
| `out/mxf/<slug>.B.work/` | `gap_sheets.py`（只重讀文稿沒蓋到的 cue）| 同一套（`cues.json`、`sheets.json`、`transcripts.json`、`verified.json`）＋ `from_rtf.json`；`strips` 是 symlink 回 `.work/strips` | 快取，可刪 |
| `out/mxf/<slug>.C.work/` | `rtf_sheets.py`（回頭把文稿供過字的 cue 也讀一次，做全量普查比對）| 同一套，子集反過來（只含文稿對到的 cue）| 快取，可刪 |
| `out/mxf-logs/<slug>.get.log` | `fetch_sftp.sh` 下載階段 | SFTP `get` 輸出紀錄 | 日誌，可刪 |
| `out/mxf-logs/<slug>.cues.log` | `fetch_sftp.sh` 切 cue 階段 | `cues` 指令 stdout/stderr | 日誌，可刪 |

兩點容易誤會：原始影片不會留在這裡——`fetch_sftp.sh` 下載到 `/tmp/ilrdf-stage`，
`cues.json` 一寫出來就刪片。視覺辨識的 TSV 也不會寫進這裡——`ingest.py`
預設直接讀寫 `Kari-SRT/vision*/<slug>/`，`kithann/` 這邊的 `verified.json`
只是本地追蹤「這個 work dir 核實到哪」的快取。

**現況：24 個影片檔，2 個上傳不完整跳過，其餘 22 集全部完成。
20,108 個 cue 100% 由 Claude 視覺辨識供字**，tesseract 與文稿都不供字。

## 跑法

**新的月份（從 SFTP 抓）**——一行指令，或用 `/smkul-news` 這個 slash command：

```bash
bash scripts/news/fetch_sftp.sh '族語新聞/110.1-110.10/3月'   # 先加 --limit 2 試跑
```

之後接第 3 步（視覺辨識）與第 4 步（組裝）。

**已在本機的影片**（2 月那批 mxf 就是這樣做的）：

```bash
python3 -m scripts.news.build_inventory   # 1. 影片 → 節目資料 → SRT 檔名
bash    scripts/news/run_cues.sh                 # 2. 切 cue（約 2.5 小時，I/O 綁死）
# 3. 視覺辨識：subagent 一批讀 24 張 sheet、直接把 TSV 寫進磁碟
python3 -m scripts.news.ingest <slug> <tsv 目錄>   # 驗證＋匯入
python3 -m scripts.news.make_all          # 4. 產 SRT ＋ 寫 Kari-SRT/srt/smkul.csv
```

每一步都可中斷重跑：`run_cues.sh` 跳過已有 `cues.json` 的 work dir，
`gap_sheets.py` 拒絕覆蓋已校讀的 work dir，`verified.json` 記錄哪些 sheet
讀過。這在實務上救過兩次——一次 devcontainer 重建、一次 session 中斷，
都是直接接著跑完。

## 影片來源：SFTP

完整語料在 `ilrdf-corpus@192.168.35.10:/docker/ilrdf-corpus`，本機 `kithann/`
底下那 24 支 mxf 只是其中 `族語新聞/110.1-110.10/2月原始mxf檔` 一個月。

```
族語新聞/110.1-110.10/{1月…10月, 2月原始mxf檔}
族語新聞/111.1-111.5/{1月…5月}
族語節目/開會了/
110年2月_族語新聞文稿/          # 文稿，本機已有
```

實測：一個月 71 集、mp4 共 154 GB（平均 2.17 GB）；15 個月推估
**約 1,065 支、2.3 TB**。下載實測 **75 MB/s**，比本機那顆 NTFS-FUSE
外接碟（42 MB/s）還快，所以從 SFTP 抓比從本機碟讀更划算。

檔名跟 `ilrdf-corpus.csv` 的「影片檔案位置」欄一一對應，整批可以直接由
那份目錄驅動，不必再爬遠端。

### 連線

密碼在 `.sftp-pass`（已 gitignore），用 `scripts/news/sftp.sh` 包起來：

```bash
scripts/news/sftp.sh 'ls -l /docker/ilrdf-corpus'
scripts/news/sftp.sh 'get "/docker/…/魯凱語-霧台20210101S1100.mp4" /tmp/x.mp4'
```

密碼從頭到尾只以**檔案**存在，不進指令列、不進 `ps`、不進對話紀錄
（規定見 `CLAUDE.md`）。兩個卡很久的坑：

- **`sftp -b` 會自動開 `BatchMode=yes`**，而 BatchMode 會**停用密碼提示**。
  ssh 於是連問都沒問就回 `Permission denied (publickey,password)` —— 這個
  錯誤訊息跟「密碼打錯」長得一模一樣，但根本不是。要明寫 `-o BatchMode=no`。
- **`sshpass` 餵不到 `sftp`**。sftp 另外 fork 一個 ssh 子行程，密碼提示走
  `/dev/tty`，sshpass 包在父行程外面的 pty 傳不到孫行程。同一組密碼用
  `ssh` 直接連是會過的，換成 `sftp` 就失敗。改用 OpenSSH 自己的
  `SSH_ASKPASS` ＋ `SSH_ASKPASS_REQUIRE=force`，任何深度都有效。

### 抓檔與刪檔

沿用 `run_cues.sh` 的模式，只是把「從慢碟複製」換成「從 SFTP 下載」：

```
逐集：下載 → 比對位元組數 → cues（切 cue＋出 sheet）→ 刪影片 → 下一集
```

**刪除時機**：影片只有 `cues` 這一步需要。之後視覺辨識讀 `strips/`、
`sheets/`，SRT 組裝讀 `cues.json`，都不再碰影片。所以 `cues.json` 一寫出來
就可以刪，磁碟峰值 = 1 支影片 + 累積的 work dir（實測約 0.5 GB／集）。

**下載完一定要驗位元組數**。本機那批 24 個檔就有 2 個上傳不完整，
`ffprobe` 的 duration 照樣宣稱完整（見下）。遠端 `ls -l` 的 size 對本機
size，不符就重抓、不進解碼。

### 版型由「資料夾」決定，不是檔名

`presets.json` 原本只能拿**檔名子字串**比對，但這批語料的檔名不可信：同一個
節目會叫 `魯凱語-霧台20210101S1100.mp4`、`賽德克-20210102s1100.mp4`、
`排灣-20210102s1800.mp4`，沒有共同片段；硬找一個又可能誤中「開會了」那批
版型完全不同的檔案，套錯 region 會整批切在錯的地方而且**不會報錯**。

所以 `subs2srt.py cues` 加了 `--preset NAME`，由呼叫端指定：

```bash
subs2srt.py cues VIDEO -o WORK --preset titv-news    # 族語新聞/ 底下都用這個
```

判斷依據是**檔案在哪個資料夾**（`族語新聞/` → `titv-news`；
`族語節目/開會了/` → `amis-xiuguluan-bilingual`），這比檔名可靠。
preset 名稱打錯會直接中止並列出可用的名稱。

### 開跑前用 verify_band.py 對照畫面

`subs2srt.py detect` 在這批素材上**不能單獨採信**——它會把氣象圖卡和台標
排在對白字幕前面。`verify_band.py` 改成量測 + 比對：抓幾分鐘的列剖面，
確認兩個地標，不合就中止。

```bash
python3 -m scripts.news.verify_band VIDEO --preset titv-news    # 加 --quiet 只看結論
```

- **對白平台**要落在 preset 的 region 內，否則就是讀錯地方了
- **紅帶上緣**（整張圖最亮的那一列）不可以落在 region **裡面**，否則標題與
  受訪者名條會被當成對白切進去

紅帶在 region **下方**多遠都沒關係：2 月母帶是 y=848（距 region 底 4 px），
1 月一支卑南是 y=917，兩個都安全。`fetch_sftp.sh` 每個資料夾自動跑一次。

### mp4 的字幕帶跟 mxf 一樣

mp4 是 1920×1080 h264，沒有 soft subtitle。實測 300 秒的列剖面：字幕平台
788–844，848 是紅色標題帶上緣的尖峰（值 382，是平台的兩倍），跟 mxf 完全
同一個形狀。所以 region 一樣是 `[0, 722, 1920, 122]`。

（版型怎麼選見上面「版型由資料夾決定」一節。）

## 幾個踩過的坑

**語料掛載點很慢。** `/dev/sda1` 是 NTFS-over-FUSE，實測單串流 41 MB/s、
雙串流 21+21 MB/s，也就是整顆碟就這樣。同時開三個解碼反而各自掉到
11.6 MB/s（慢 3.5 倍）。所以 `run_cues.sh` 改成：一次只循序複製一個檔到本機
磁碟（寫入 822 MB/s），解碼吃本機那份，解完就刪。380 GB 的讀取約 2.5 小時，
這是硬底線，解碼藏在它後面跑。

**檔名不可信，要用畫面驗證。** 五個 2021 年 2 月的檔名年份打成 `20`，
`21NL004_37午間` 掛的是晚間的 NL 代碼卻是午間。集數其實是「當年第幾天」
（集 32 ＝ 2 月 1 日），所以用「集數＋時段」查 `ilrdf-corpus.csv` 就夠。
時段取檔名裡的中文字，不取 NL 代碼；再把畫面左下角燒死的族語標章
（泰雅／撒奇萊雅／Seediq…）截出來跟目錄對照，24 個檔全部相符。

**上傳不完整的檔案。** 完整母帶是固定 6.30 MB/s 的 CBR。有兩個檔明顯偏低
（2.83 與 3.44 MB/s），檔頭仍宣稱完整長度，但尾端解碼毀損 —— 這兩集跳過
（041 鄒、037晚 排灣）。只看 `ffprobe` 的 duration 看不出來，要拿位元組數
除以長度才會現形。

**母帶開頭的 slate 會被當成字幕。** 播出母帶開頭是彩條與識別卡，識別卡的
白字剛好落在字幕帶範圍內，segmenter 會在第 0 幀開一個十幾秒的 cue。
22 集裡最早的真實字幕出現在 5.8 秒，所以 `make_srt.py` 直接丟掉
「start < 0.5 秒」的 cue。

## 文字全部來自 Claude 視覺辨識

成品裡沒有 tesseract 的字，也沒有文稿的字。過程中兩者都試過，結論寫在下面。

### tesseract：只堪定位，不堪供字

讀這種壓在畫面上的中文，46 個手讀 cue 的基準是**逐行 26% 正確**
（`去年底桃園復興巴陵的一場大火` → `同/和)[人圖復興叫陜病一易大六`）。
最初拿它當「夠爛但不亂」的訊號去對齊文稿，後來連這個角色也不需要了。

### 文稿：當交叉驗證有用，當文字來源沒用

`.rtf` 新聞稿的內容確實就是字幕的來源，`align.py` 也真的能把 cue 對回稿子
（3-gram 投票找位置，再解一次最長遞增子序列強迫單調）。但**逐字忠實於畫面
這件事，稿子在原理上做不到**。

4,344 個原本由文稿供字的 cue，全部重新用視覺讀一次逐字比對：

| | |
|---|---|
| 一致 | 4,008（92.3%）|
| 有差異 | 336（7.7%）|

336 筆全部是畫面對、稿子錯，而且分成兩種性質：

- **58% 是切點問題**：旁白在稿子裡是一整段，稿子沒有記錄字幕師把它斷在
  哪，所以只能照字元位置切，切出來多字或少字。
- **40% 是字幕師改過稿**：稿子 `然後千萬不要裝紙`，畫面是 **`裝死`**（稿子
  打錯字，字幕師改對了）；`看到熊3件事不要做` → **`3件事情不要做`**；
  `有時可能會胃痙攣` → **`有可能會胃痙攣`**。這類不管對齊做得多好都救不回來。

還有 1 筆是稿子把片尾 `企劃/文字 黃慧如` 當字幕給了出去，畫面其實是空的。

**所以文稿對「產生字幕」沒有淨幫助**——先用它供字、再全部重讀，等於把同一批
sheet 讀了一遍，還多花了建兩次 contact sheet 的工。真正的價值是**當獨立
對照**：4,344 行、92.3% 一致，而且不一致的部分有系統性解釋，這是目前唯一
能證明視覺辨識可信的證據。

比對報告：`Kari-SRT/report/rtf-vs-vision.md`（分析與範例）、
`rtf-vs-vision.json`（完整 336 筆）。

### 視覺辨識的三個實作重點

- **cue 編號會跳。** 分批重讀時 sheet 上只放需要的 cue，編號不連續
  （214、219、533…）。prompt 必須明講「讀 gutter 上的數字，不要自己 +1
  補號」，否則整段字幕會靜靜落在錯的位置——比讀錯字嚴重，因為不會報錯。
  `ingest.py` 再擋一層：TSV 裡出現不屬於該批 sheet 的 cue，整批拒收。
- **一批 24 張、TSV 直接寫進磁碟。** 實測每張 2,788 tokens（12 張一批時是
  3,450，prompt 分攤較差）。主對話只收行數，不然 context 會被圖吃光。
- **空白 cue 的行尾 tab 會被 Write 工具剪掉**，`ingest.py` 匯入前統一補回。
  prompt 要叫 subagent「寫一次就好、不要自己修 tab」，否則有 agent 會為了
  補 tab 反覆改檔，用掉 16 萬 tokens（正常 6.4 萬）。

## 檔案

| | |
|---|---|
| `build_inventory.py` | 影片↔節目資料對應，寫 `inventory.json` |
| `run_cues.sh` | 複製到本機 → 切 cue |
| `rtf.py` | 讀 Big5 RTF 文稿（檔頭寫 cp1252，其實是 Big5） |
| `align.py` | 把 OCR 訊號對回文稿（現已不供字，保留供比對用） |
| `gap_sheets.py` | 只把「還沒讀過」的 cue 做成 contact sheet |
| `rtf_sheets.py` | 只把「文稿供過字」的 cue 做成 contact sheet |
| `batches.py` | 列出一集還沒讀的 sheet，切成 24 張一批 |
| `ingest.py` | 驗證 TSV（格式＋cue 編號歸屬）並匯入 |
| `compare_rtf.py` | 文稿 vs 視覺逐字比對，`--apply` 改採視覺 |
| `make_srt.py` | 單集組裝 SRT |
| `make_all.py` | 全部組裝＋寫 `smkul.csv` |
| `check_align.py` | 早期用手讀 TSV 量文稿對齊正確率 |
| `sftp.sh` | SFTP 包裝：密碼只以檔案存在，處理 BatchMode／askpass 兩個坑 |
| `sftp-askpass.sh` | 給 OpenSSH 讀密碼檔的 hook（`SSH_ASKPASS`）|
| `fetch_sftp.sh` | 逐集：下載 → 驗位元組 → 驗band → 切cue → **刪影片** |
| `verify_band.py` | 量列剖面，確認字幕帶真的在 preset 說的位置 |
| `resolve_slug.py` | 用 `ilrdf-corpus.csv` 把檔名對成 work dir／SRT 名稱 |
| `paths.py` | 全部路徑的單一出處；`--var` 供 shell 取值 |
| `migrate_kari.py` | 一次性：舊命名資料 → Kari-SRT（保留當對照文件）|
| `rebuild.py` | 從 Kari-SRT 離線重建全部 SRT 並逐 byte 驗證 |
| `Kari-SRT/vision/` | 第一輪視覺逐字稿 TSV（文稿沒蓋到的 cue）|
| `Kari-SRT/vision-rtf/` | 第二輪視覺逐字稿 TSV（文稿蓋到的 cue）|

`vision/` 與 `vision-rtf/` 加起來就是 20,108 個 cue 的完整逐字稿，
是這批工作最可重複使用的成果，正本在 `Kari-SRT/`。

## 產出

正本都在 `Kari-SRT/`（submodule，進版本控制）：

- `Kari-SRT/srt/<播出日期>_<集數>_<時段>_<族語英>_<族語中>.srt` —— 22 集
- `Kari-SRT/srt/smkul.csv` —— 進度表
- `Kari-SRT/report/rtf-vs-vision.md` / `.json` —— 文稿 vs 視覺比對報告
- `Kari-SRT/cues/`、`vision/`、`vision-rtf/`、`from_rtf/`、
  `inventory.json` —— 重建 SRT 所需的全部過程資料

驗證離線閉環：`python3 -m scripts.news.rebuild --verify` 會只用
Kari-SRT 的資料重組全部 SRT 並逐 byte 比對，缺件即指名失敗。

## 換機器要帶什麼

進 git 的（跟著 repo 走，不用管）：主 repo（程式 `scripts/`、測試
`tests/`、`.claude/` 說明）＋ `Kari-SRT` submodule（上面那些資料正本）。

**不在 git、要自己搬或重建的**：

| | 怎麼辦 |
|---|---|
| `kithann/out/mxf/*.work/` | 純快取（strips/sheets 約 15 GB）。**不用搬**，`rebuild --verify` 保證正本可離線重生 |
| `kithann/tongan/ilrdf-corpus.csv` | 節目目錄，`resolve_slug.py` 和 `build_inventory.py` 都要它 |
| `.sftp-pass` | 故意不進 git。到新機器**自己在終端機重建**，不要叫 Claude 寫 |

新機器上還要做的：

1. `sudo apt install ffmpeg tesseract-ocr tesseract-ocr-chi-tra python3-venv`
   ＋ `python3 -m venv ~/.venvs/subs2srt && ~/.venvs/subs2srt/bin/pip install numpy Pillow`
   （devcontainer 重建過一次就掉光，這是實際發生過的）
2. 重新 `ssh-keyscan 192.168.35.10 >> ~/.ssh/known_hosts`
3. `.devcontainer/devcontainer.json` 裡那條 `ilrdf-corpus` 的 bind mount 是舊機器的
   路徑，新機器如果只用 SFTP 就可以整條拿掉

## 還沒做的

**`verify_band.py` 的紅帶判準還沒實測過。** 這支是加 SFTP 那次新寫的，2 月
那批當初是手動確認帶位、沒有用到它。已測：`魯凱語-霧台20210101S1100.mp4`
用 `titv-news` 通過（邊緣 y=848、平台 y=816），故意用錯 preset 會失敗。
未測：試跑 1 月時 `卑南語-20210103S1800.mp4` 的紅帶邊緣在 y=917 而非 848，
判準因此放寬成「只擋落在 region 裡面的邊緣」——推理上成立（邊緣在下方不可能
把標題文字漏進 y=844 就結束的區域），但**改完之後沒有再拿任何影片跑過**。
下次開跑含這類檔案的月份，第一支請不加 `--quiet` 跑一次、看剖面，再開
`sheets/sheet_001.png` 確認圖條上只有對白。



burned-in 字幕**只有中文**。族語只存在於聲音，以及 `.rtf` 文稿裡那些
拉丁字母的族語行——`rtf.py` 的 `is_cjk_line()` 目前把它們濾掉了，因為
對「抽中文字幕」沒用。對族語語料來說那才是主體，要用的話從那個函式著手。
