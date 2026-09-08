## Why

母帶陸續下載到隨身硬碟，要逐支轉成封存 mkv 再送回 SFTP，但現有的封存路徑只服務族語新聞：`archive_batch.py` 從目錄／`smkul.csv`／inventory 查「這是哪一集」才動得了，隨身硬碟上的檔案沒有那個身分，整條走不通。使用者裁定 2026-09-05：先轉完再認 catalogue，因為隨身硬碟不能一直插著除錯。

順帶要修 `encode_master.sh` 兩個實測出來的問題。**第一，它讀來源三次**（比對音軌、編碼、驗音訊），每支 19 GB 的母帶在 USB 碟上就是 57 GB 的讀取。**第二，它只 map `a:0` 和 `a:1`**，來源若有第三條音軌會被靜靜丟掉、完全不出聲——族語新聞那批剛好都是兩軌所以沒踩到，但隨身硬碟這批是新聞以外的檔案，來源不同。

## What Changes

- **新工具 `tools/mxf2mkv/`**：掃一個本機資料夾底下的 `.mxf`，逐支轉成 mkv，每支轉完就上傳 SFTP，遠端結構鏡射來源。不查目錄、不查 `smkul.csv`、不查 inventory，也不碰現有的 `/home/news/mkv/`——重複的照轉，放不同的遠端根，之後再 rename／mv。
- **`encode_master.sh` 改成一趟 ffmpeg**（**BREAKING**，呼叫契約改變）：視訊編碼與「算出來源每條音軌的 md5」在同一趟完成，來源只讀一次。它不再自己決定音軌去留，只負責產出「含來源全部音軌的 mkv」加「N 個來源音軌 md5」。
- **音軌邏輯抽成純函式 `scripts/transcode/audio_tracks.py`**：N 軌通吃，判斷逐位元是否相符、哪幾軌彼此重複、該留哪幾軌；三軌以上要明講，不得靜靜丟棄。兩個呼叫端（新聞封存、隨身硬碟批次）共用同一份，只寫一次。
- **`archive_batch.py` 跟著改**：`_encode()` 從「呼叫一支 bash 就當一切辦妥」改為走三段流程（編碼＋算 md5 → 純函式決定去留 → `-c copy` 重新封裝）。判準維持 **bit-exact 不變**。
- **測試補進 CI**：`tests/transcode/` 的 46 個測試目前不在 `tox -e unittest` 的 discover 清單裡，從來沒在 CI 跑過。這次要動 `encode_master.sh`，先把它和新的 `tests/mxf2mkv/` 一起加進去。
- **不新增任何 Python 套件**，也不留 `requirements.txt` 的佔位。外部只用 `ffmpeg`／`ffprobe`／`sftp`，測試用的小 mxf 由 ffmpeg 自己的 lavfi 在跑測試時合成，不 commit 進 git。

## Capabilities

### New Capabilities

- `master-archival`: 母帶轉封存 mkv 的編碼契約——一趟 ffmpeg 同時產出封存與來源音軌 md5、N 軌通吃、音訊逐位元相符才算數、重複音軌的判定與去除、三軌以上要出聲。兩個呼叫端共用。
- `mxf2mkv-batch`: 本機資料夾批次——掃描與跳過、來源到遠端的路徑對應、每支轉完即上傳並比對位元組數、工作目錄與清理、一支失敗跳過續跑、執行紀錄與對照表的落點與命名。

### Modified Capabilities

（無。現有六個 capability 都沒有涵蓋封存這條線，`grep` 過 `openspec/specs/` 沒有任何 `mkv`／`encode_master`／封存 的條文。）

## Impact

### 資料落點

```
隨身硬碟（唯讀，只讀這一次）
  --src /media/hong/USB/2月原始mxf檔/
   ├── a.mxf
   └── 夜間/b.mxf
        │
        ▼
本機 SSD（每次執行各自一個，2–3 支可同時跑）
  /tmp/mxf2mkv-<random>/
   ├── a.all.mkv       編碼產物，含來源全部 N 條音軌
   ├── a.src-a0.md5    編碼同一趟算出的來源音軌 md5（N 軌就 N 個）
   ├── a.src-a1.md5
   └── a.mkv           驗過、去掉重複軌的成品 → 上傳 → 三個檔全刪
        │
        ▼
SFTP
  /home/mkv-raw/2月原始mxf檔/     ← 遠端根＋--src 的最後一層資料夾名
   ├── a.mkv
   └── 夜間/b.mkv                 ← 底下相對路徑照抄，只換副檔名
```

執行紀錄（`kithann/` 在 `.gitignore` 內，不進 git）：

```
kithann/mxf2mkv/
└── 2月原始mxf檔/                              ← 外層只有來源名，歷次執行放一起
    ├── 0905-2017_2月原始mxf檔.log             每支的 ffmpeg／sftp stderr 全文
    ├── 0905-2017_2月原始mxf檔.manifest.json   對照表
    ├── 0906-0930_2月原始mxf檔.log             第二次跑，同一個資料夾
    └── 0906-0930_2月原始mxf檔.manifest.json
```

同一分鐘內跑兩次會撞名，以 `O_EXCL` 建檔、撞到就加 `-2`、`-3` 後綴，絕不覆蓋舊檔。

### 程式

```
scripts/transcode/
├── encode_master.sh      改：一趟 ffmpeg、N 軌全留、順便吐來源音軌 md5；
│                             不再自己判斷音軌去留（BREAKING）
├── audio_tracks.py       新：N 軌決策純函式，零 I/O
└── archive_batch.py      改：_encode() 改走三段流程

tools/mxf2mkv/
├── __init__.py
├── __main__.py           新：CLI、預設值、離開碼
├── walk.py               新：掃 --src、路徑對應、已存在就跳過
├── report.py             新：log／manifest 命名、O_EXCL 不覆蓋、JSON 排版
├── upload.py             新：呼叫 sftp.sh 逐層 mkdir、put、比對位元組數
├── run.py                新：一支的完整流程
└── README.md             新：這是什麼、怎麼跑、產出在哪
```

`tools/mxf2mkv/` 會 `import scripts.transcode.audio_tracks`（使用者裁定 2026-09-06）。這跟刻意排除的那種依賴（目錄／`smkul.csv`／inventory——那些會逼人先登記才能轉檔）性質不同，只是同一個 repo 內共用一份純函式。

### 測試

```
tests/mxf2mkv/            新，進 tox -e unittest（CI 跑得到，不需要 ffmpeg）
├── __init__.py
├── test_paths.py         路徑對應、副檔名過濾、危險路徑拒絕
├── test_scan.py          掃描順序、遠端已存在且位元組相符則跳過
├── test_audio.py         N 軌決策（吃 ffprobe 輸出字串，不跑 ffmpeg）
├── test_report.py        log／manifest 命名、撞名加後綴、JSON 排版
└── test_failure.py       一支失敗記錄後續跑、離開碼

tests/transcode/
├── test_archive_batch.py 既有 46 個，這次終於進 CI
└── test_encode_master.py 新：ffmpeg 參數組裝（dry-run，不跑編碼）

tests/e2e/
└── test_mxf2mkv_roundtrip.py  新：合成 3 秒兩軌小 mxf 跑完整條，
                               斷言音訊逐位元相符、軌數正確（tox -e e2etest）

tox.ini                   改：unittest 加 discover tests/transcode、tests/mxf2mkv
```

### 依賴與外部服務

不新增任何 Python 套件、雲端服務或模型權重，所以《採購安全說明書》那套稽核在這條沒有適用對象。外部只用系統既有的 `ffmpeg`／`ffprobe`／`sftp`，使用者已確認 host 上都有。

### 文件

`.claude/skills/video-subtitle-srt/壓縮率分析.md` 第 23 行寫「這批兩軌 MD5 相同」，實測是拿一支量的；63 支封存裡有 28 支（44%）兩軌不同。該行要更正，並補上這次量到的數字。
