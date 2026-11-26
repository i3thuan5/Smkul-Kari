# Design

## Context

動機見 proposal.md〈Why〉。現況量測（2026-11-25，重建前）：

| 項目 | 現在 | 釘 `ubuntu26.04` 後 |
|---|---|---|
| 作業系統 | Ubuntu 24.04.4 | 26.04 |
| ffmpeg | 6.1.1-3ubuntu5 | 8.0.1-3ubuntu2 |
| mesa-va-drivers | 25.2.8-0ubuntu0.24.04.4 | 26.0.8-1ubuntu0.3（updates） |
| libsoxr | 0.1.3-4build3 | 0.1.3-4.1 |
| libva | — | 2.23.0 |
| tesseract | — | 5.5.0 |
| `python3`（PATH 第一個） | 3.12.14，devcontainer python feature | 不變；系統的 3.14 排在後面 |

- `vscode` 使用者的有效能力集合是空的（`CapEff 0`），seccomp 是過濾模式（`Seccomp: 2`），有免密碼 sudo。
- 核心（7.0）支援 `F_DUPFD_QUERY`，實測複製的描述子回 1、另外開的回 0；Mesa 25.2.8 沒走這條路，只用 `kcmp`。
- 新聞 mkv2mp4wav 全跑正在背景跑（`setsid --wait`，自己一個 session），紀錄在 `kithann/mkv2mp4wav/news/`；續跑會跳過伺服器上兩樣都在的集數，第 78 集那次已驗證。
- `.tox/` 在 workspace 裡，重建後還在；它的 venv 指向 python feature 的路徑，重建後路徑相同。

## Goals / Non-Goals

**Goals:**

- 重建後 Mesa 判斷得出裝置、警告消失，且版本是明確選定的 26.04。
- 續跑新聞全跑之前，用實機比對證明新環境的產出可以接在舊產出後面。

**Non-Goals:**

- 不重做已上傳的預覽檔與音檔。
- 不改 mkv2mp4wav 或其他程式。驗收若發現 ffmpeg 8 不相容，另開 change 修，不在這個 change 裡塞程式修改。
- 不把 apt 套件鎖到小版本（`post-create.sh` 照裝當下 26.04 的版本）。釘大版本已經擋住「重建順便跳大版本」；鎖小版本得自己追安全更新，不划算。

## Decisions

### `--cap-add=SYS_PTRACE`，不是 `seccomp=unconfined`、不是換 Mesa、不是濾掉紀錄

Docker 預設 seccomp 設定對 `kcmp` 的規則是：容器有 `SYS_PTRACE` 能力才放行。加這個能力是讓驅動拿到答案的最小改動。

- `seccomp=unconfined`：整個系統呼叫過濾都關掉，範圍太大。
- 自訂 seccomp 設定檔只多放行 `kcmp`：最精準，但要維護一份 JSON，跟著 Docker 預設檔的更新走，不划算。
- 換 Mesa（PPA 或自己編）走 `F_DUPFD_QUERY`：要過採購稽核，驅動來源不明。不採用。不過 26.04 的 Mesa 可能已經走 `F_DUPFD_QUERY`，那時 `SYS_PTRACE` 對警告就是多餘的保險；照樣加，因為 `kcmp` 可用與否不該取決於 Mesa 某版的實作。
- 紀錄檔濾掉那兩行：只是看不到，驅動照樣判斷不了。使用者選了根本解決。

`kcmp` 本身還要過核心的 ptrace 存取檢查（同一個使用者、比對自己的程序），`vscode` 不需要任何能力就能通過；`SYS_PTRACE` 只是讓 seccomp 那關放行。

### 釘 `base:ubuntu26.04`，不是 `base:ubuntu24.04`

使用者裁定 2026-11-25。浮動標籤 `base:ubuntu` 已經指向 26.04，選 24.04 等於倒退回舊的；選 26.04 是把「下次重建本來就會發生的事」變成現在明確做、明確驗收。標籤用 MCR 上實際存在的寫法 `ubuntu26.04`（另有 `resolute`，用帶版本號的那個，一看就知道是哪一版）。

### GPU 群組：加入擁有裝置的那個群組，不管它叫什麼名字

使用者裁定 2026-11-26。第一次重建 26.04 時，主機 GPU 群組 GID 992 在容器裡已是 `systemd-resolve`（見 spec〈一般使用者打得開 GPU〉）。

- **採用**：查裝置 GID 在容器裡屬於哪個群組；有就把 `vscode` 加進去，沒有才以那個 GID 新建 `render`（`render` 名字被別的 GID 用掉時用 `render-<GID>`）。以後 GID 跟哪個群組撞都不會壞。代價是這台機器上 `vscode` 會在 `systemd-resolve` 群組裡，名字看起來怪；容器裡沒有跑 systemd-resolved，實際沒有影響。
- 把佔位的系統群組換號、`render` 改回 992：名字正確，但要動系統群組 GID 與屬於它的檔案，換一台機器又可能撞別的。
- `runArgs` 加 `--group-add=992`：VS Code 用 `docker exec` 進容器，對 exec 進來的程序是否有效沒把握，而且 GID 寫死在設定檔裡，每台主機不同。

這段邏輯從 `post-create.sh` 拆成 `.devcontainer/gpu-group.sh <裝置> <使用者>`，因為 `post-create.sh` 一開頭就 `apt-get`，整支沒辦法離線測。測試在 PATH 最前面放假的 `stat`、`getent`、`sudo`，假 `getent` 讀一份假的群組表，假 `sudo` 只把參數記到檔案，斷言送出的 `groupadd`／`usermod` 指令。沿用 `video` 群組（`card1` 用）一起加。

群組變更要新的登入才生效。第二次重建（2026-11-26）實測：VS Code 伺服器 01:58:49 啟動，`post-create.sh` 02:00:28 才改 `/etc/group`（前面 apt 花了一分半），所以從伺服器開出來的終端機與 Claude Code 都拿到舊群組，**重建本身不會讓工作階段拿到 GPU 群組**；`/etc/group` 是對的，`sudo su - vscode` 開的新登入就有 992。重建後要讓 VS Code 重新連線一次（關掉視窗再開，容器會停下再啟動），或長時間工作以 `sudo su - vscode -c` 新登入發動。這次的驗收與續跑用的是後者。使用者裁定（2026-11-26）：這件事只寫進文件（`devcontainer.json`、`post-create.sh` 註解與 README〈開發環境〉），不改成 `onCreateCommand`／`waitFor` 自動化。

### 重做一集只用暫存區腳本，不改工具

驗收要「重做一集、不上傳、跟伺服器比」。mkv2mp4wav 沒有「只產出不上傳」的模式，為了一次性驗收去加一個參數不值得（要 TDD、要文件、之後沒人用）。改在 scratchpad 寫一支一次性腳本，直接呼叫既有模組的 `encode.command`、`audio.command`、`verify.check_all`、`audio.verify`，產出放暫存區，比完刪掉。

選哪一集：`20210101_001_午間_Rukai_魯凱`。13 分鐘，約 2 分鐘做完；影像起點 0.033 秒，順便驗起點保留；它是重建前第一批上傳的，伺服器那份確定是舊環境做的。

### 驗收順序

先便宜後昂貴，前一步不過就不往下：

```
重建完成
  │
  ├─ 1. 版本記錄（os-release、ffmpeg、mesa、libsoxr）
  ├─ 2. kcmp 放行、seccomp 仍是 2
  ├─ 3. ffmpeg 開 VAAPI 裝置不印警告
  ├─ 4. 全套測試：flake8、unittest、e2e（含 GPU 三支）、rebuild --verify、name_catalogue --check
  ├─ 5. 重做魯凱，WAV 比 SHA-256、預覽檔比 SHA-256＋驗收
  │
  └─ 全過 → 清 /tmp 殘留 → setsid --wait 續跑新聞全跑
     任一步不過 → 停，寫回覆給使用者
```

全套測試放在重做之前：e2e 有合成影片跑全硬體與混合路徑，選項改名之類的問題在那裡就會出現，比下載 766 MB 的真實來源便宜。

## spec × scenario × 驗證方式

GPU 群組那段拆成 `gpu-group.sh` 後可以離線測，放 `tests/devcontainer/test_gpu_group.py`；其餘只改容器設定，沒有可以離線測的程式，每個 scenario 用重建後的實機指令驗收（tasks 第 2、3 節），結果寫進回覆。

| spec | scenario（會出錯的具體情形） | 驗證方式 |
|---|---|---|
| dev-container | GID 992 在 26.04 image 裡已是 `systemd-resolve`，`groupadd -f -g 992 render` 默默改用 1001，`vscode` 打不開 GPU（2026-11-26 實測） | `tests/devcontainer/test_gpu_group.py`：假群組表 992＝systemd-resolve，斷言 `usermod -aG video,systemd-resolve vscode`、沒有 `groupadd` |
| dev-container | 24.04 的情形：992 沒有群組，要新建 `render` 並用 992 | 同上：斷言 `groupadd -g 992 render`，沒有 `-f` |
| dev-container | 第一次失敗的重建留下 GID 1001 的 `render`，再建 `render` 會撞名 | 同上：斷言 `groupadd -g 992 render-992`，不動 1001 |
| dev-container | 沒有 GPU 的機器，`stat` 失敗讓 `set -e` 的 post-create 整支中止 | 同上：裝置不存在時不呼叫 `sudo`、離開碼 0 |
| dev-container | 群組修好但工作階段沒重新登入，`vscode` 仍打不開 | 再重建後以 `vscode` 執行 `vainfo --display drm`（2.3） |
| dev-container | 只開 VAAPI 裝置、不編碼，Mesa 就印 `os_same_file_description` 警告（24.04 實測每個 GPU 程序一次） | `ffmpeg -init_hw_device vaapi=va:/dev/dri/renderD128 -f lavfi -i testsrc=d=0.1 -f null -` 的錯誤輸出 grep 不到 |
| dev-container | `vscode` 呼叫 `kcmp` 回 Operation not permitted（24.04 實測） | python `ctypes` 呼叫 syscall 312 回 0 |
| dev-container | 為了放行 `kcmp` 而把 seccomp 整個關掉 | `/proc/self/status` 的 `Seccomp` 仍是 2 |
| dev-container | 浮動標籤 `base:ubuntu` 悄悄從 24.04 換到 26.04（實查兩者 digest 相同） | 讀 `devcontainer.json` 的 image；重建後 `/etc/os-release` 是 26.04 |
| dev-container | 換版本後 WAV 不再逐位元相同（重取樣是浮點運算） | 重做魯凱，WAV 與伺服器那份比 SHA-256；不同就算取樣最大差異 |
| dev-container | Mesa 換版，預覽檔位元組不同 | 預覽檔比 SHA-256；不同時看影格數 23978／23978 與驗收 |
| dev-container | ffmpeg 8 移除或改名了我們用的選項（`-fps_mode`、`-rc_mode`、`-write_tmcd`、`-f hash -hash sha256`…） | e2e 全套（mkv2mp4wav 7 支含 GPU 3 支、mxf2mkv 往返） |
| dev-container | 驗收重做時覆蓋了伺服器上的檔 | 腳本不呼叫上傳；比對後伺服器那份的位元組數與時間不變 |

## 檔案樹

```
.devcontainer/
  devcontainer.json     改：image → mcr.microsoft.com/devcontainers/base:ubuntu26.04
                            runArgs 加 "--cap-add=SYS_PTRACE"
                            兩處都加註解寫原因（照檔案現有的註解風格）
  post-create.sh        改：GPU 群組那段改成 `bash .devcontainer/gpu-group.sh /dev/dri/renderD128 vscode`
  gpu-group.sh          ★新：查裝置 GID 屬於哪個群組，決定 groupadd／usermod；由 post-create.sh 呼叫
  devcontainer-lock.json  不改（只鎖 features，不鎖 image）
Kari-SRT/               不動
tests/devcontainer/
  __init__.py           ★新
  test_gpu_group.py     ★新：執行 gpu-group.sh，PATH 前面放假 stat／getent／sudo（測試內建在暫存目錄）
  README.md             ★新：這組的 spec × scenario × 測試檔對照
tests/README.md         改：總表加一行指向 tests/devcontainer/README.md
tests-e2e/              不動
scripts/ tools/         不動
openspec/specs/dev-container/spec.md   歸檔時由本 change 的 delta 建立
kithann/tuiue/1125/…    驗收結果寫在回覆檔（gitignore，不進 repo）
<scratchpad>/redo_rukai.py   一次性驗收腳本，不進 repo
```

## Risks / Trade-offs

- [ffmpeg 8 不認得某個選項，或 ffprobe 輸出欄位變了] → e2e 全套會抓到；驗收不過就不續跑，另開 change 修程式，修好前新聞全跑暫停。最壞情況是改 image 回 `base:ubuntu24.04`（見 Migration Plan）。
- [ffmpeg 7 起改成多執行緒管線，混合路徑先前靠 `-threads 1` 解掉的檔尾少格可能有變] → e2e 的 4:2:2 混合路徑測試比對影格數；新聞全部走硬體路徑，不受混合路徑影響。
- [Mesa 26 的 h264_vaapi 編出的位元組不同] → spec 允許：影格數相等、驗收全過即可續跑；差異記在回覆。
- [WAV 不再逐位元相同] → 停下，算兩邊取樣的最大差異交給使用者決定。預期不會：FLAC 解碼與版本無關，libsoxr 同為 0.1.3。
- [tesseract 5.5 讓 e2e 的 OCR 斷言失敗] → 那是 e2e 合成字幕的辨識結果，與新聞轉檔無關；若只有這類失敗，記下來另外處理，不擋續跑（回覆裡講清楚）。
- [26.04 image 已經有 `render` 群組，或 GID 992（主機上 `/dev/dri/renderD128` 的群組）被別的系統群組佔走；`post-create.sh` 的 `groupadd -f -g` 這時會默默換一個 GID，`vscode` 打不開 GPU] → 2026-11-26 第一次重建真的發生（992＝`systemd-resolve`）。已依使用者裁定併進本 change 修，見 Decisions〈GPU 群組〉。
- [重建時別的 session 正在跑東西] → 重建前由使用者確認；目前看得到的長時間程序只有新聞全跑。
- [這個對話隨重建斷掉，接回來的 session 不知道要做什麼] → 步驟寫在 tasks.md 與 `kithann/tuiue/`；記憶裡也有「背景工作隨 session 停」那條。

## Migration Plan

1. 改 `devcontainer.json`（apply）。
2. 以 Ctrl+C 方式停新聞全跑：`pkill -INT -f 'tools\.mkv2mp4wav\.[n]ews'`，等背景任務回報結束。
3. 使用者重建容器（VS Code：Dev Containers: Rebuild Container）。
4. 重建後照「驗收順序」做；全過才續跑。

回退：`devcontainer.json` 的 image 改為 `mcr.microsoft.com/devcontainers/base:ubuntu24.04`（釘住，不回到浮動的 `ubuntu`），保留 `--cap-add=SYS_PTRACE`，再重建一次。已經在 26.04 上傳的產出都過了驗收，不用撤回。

## Open Questions

- 26.04 的 Mesa 是否已改走 `F_DUPFD_QUERY`（若是，沒有 `SYS_PTRACE` 警告也會消失）。不影響做法，重建後順便查：暫時移除能力再試一次不值得，只記錄 Mesa 版本即可。
