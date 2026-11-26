# Proposal

## Why

用 GPU 轉檔時，每個 ffmpeg 程序都會印出 `amdgpu: os_same_file_description couldn't determine if two DRM fds reference the same file description. If they do, bad things may happen!`。這是 Mesa（AMD 的 VAAPI 驅動）要判斷兩個開啟的 GPU 裝置是不是同一份時，用的 `kcmp` 系統呼叫被 Docker 預設的 seccomp 擋掉（容器沒有 `SYS_PTRACE` 權限時才擋）。目前沒有證據顯示影響產出，但驅動在「判斷不了」的狀態下運作，新聞全跑十幾天的紀錄每集也多兩行雜訊。

另外，devcontainer 的基底 image 是會移動的標籤 `base:ubuntu`，實查它已經和 `base:ubuntu26.04` 是同一個 digest；現在的容器是 24.04。也就是說，下一次重建不管為了什麼，都會悄悄把 ffmpeg（6.1 → 8.0）、Mesa（25.2 → 26.0）一起換掉。要重建，就要把版本變成明確的決定。

## What Changes

- devcontainer 的 `runArgs` 加 `--cap-add=SYS_PTRACE`，讓 Docker 預設 seccomp 放行 `kcmp`，Mesa 判斷得出來，警告消失。不關掉 seccomp（`seccomp=unconfined` 範圍太大）。
- 基底 image 從 `mcr.microsoft.com/devcontainers/base:ubuntu` 改為釘在 `base:ubuntu26.04`（使用者裁定 2026-11-25）。ffmpeg 8.0.1、Mesa 26.0.x、libsoxr 0.1.3（同版）、tesseract 5.5.0；`python3` 仍是 devcontainer python feature 的 3.12。
- `post-create.sh` 的 GPU 群組改為「把 `vscode` 加進擁有 GPU 裝置的那個群組，不管它叫什麼名字」；裝置的 GID 沒有群組時才新建。第一次重建 26.04 時實測：主機 GPU 群組 GID 992 在 26.04 image 裡已是 `systemd-resolve`，舊寫法 `groupadd -f -g 992 render` 默默把 `render` 建成 1001，`vscode` 打不開 GPU（使用者裁定 2026-11-26，併進本 change）。
- 重建後、續跑新聞全跑之前，先做四步實機驗收：`kcmp` 放行、開 GPU 不再印警告、記錄新舊版本、重做一集已上傳的新聞並與伺服器那份比對 SHA-256；再跑全套測試與 Kari-SRT 重建。通過才續跑。
- 檔案結構（Kari-SRT／tests／scripts 三層都不動，討論時已與使用者確認）：

  ```
  .devcontainer/
    devcontainer.json    改：image 釘 ubuntu26.04、runArgs 加 --cap-add=SYS_PTRACE、註解寫原因
    post-create.sh       改：GPU 群組那段改呼叫 gpu-group.sh
    gpu-group.sh         ★新：決定把 vscode 加進哪個群組（拆出來才測得到）
  Kari-SRT/              不動
  tests/devcontainer/    ★新：gpu-group.sh 的測試（假的 stat／getent／sudo）＋README 對照表
  tests/README.md        改：總表加一行指過去
  tests-e2e/             不動（環境改動，由重建後跑全套測試把關）
  scripts/ tools/        不動（驗收若發現 ffmpeg 8 不相容，另開 change 修）
  ```

## Capabilities

### New Capabilities

- `dev-container`: 開發容器的環境保證——一般使用者打得開 GPU、GPU 驅動能判斷裝置、基底 image 釘在指定版本、換環境之後續跑轉檔批次之前要先實機比對。

### Modified Capabilities

（無。`mkv2mp4wav-batch` 的「同一個來源每次產出逐位元相同的 WAV」指同一環境重跑，條文不變。）

## Impact

- **重建容器**：由使用者動手。容器內所有程序會停，新聞 mkv2mp4wav 全跑要先以 Ctrl+C 方式停下，重建驗收後再續跑；這個 Claude Code 對話也會斷，計畫寫在 tasks 與 `kithann/tuiue/`。
- **ffmpeg 8、Mesa 26**：mkv2mp4wav、mxf2mkv、`scripts/transcode/` 的指令都可能受影響（選項改名、ffprobe 輸出欄位、硬體路徑行為）。重建後的 e2e（含 GPU 路徑）與重做一集比對會當場抓出來。
- **已上傳的產出**：不重做。新聞前後兩半可能是不同版本做的；WAV 解碼是 FLAC（無損、版本無關），重取樣的 libsoxr 同版，預期逐位元相同，驗收會實測。
- **權限**：`SYS_PTRACE` 只加在容器的能力集合，`vscode` 使用者本身的權限不變；`vscode` 原本就有免密碼 sudo，風險增加很小。
- **採購**：不新增任何套件或服務。
