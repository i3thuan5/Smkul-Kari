# Tasks

## 1. 改設定、準備重建

- [x] 1.1 `.devcontainer/devcontainer.json`：image 改為 `mcr.microsoft.com/devcontainers/base:ubuntu26.04`，`runArgs` 加 `"--cap-add=SYS_PTRACE"`，兩處各加一段註解寫原因（照檔案現有的註解風格：image 為什麼不用浮動的 `ubuntu`；`SYS_PTRACE` 是讓 Docker 預設 seccomp 放行 Mesa 的 `kcmp`）。驗證：`python3 -c` 去掉 `//` 註解後以 json 解析成功，image 與 runArgs 是新值
- [x] 1.2 記下重建前的版本與狀態寫進回覆檔：`/etc/os-release`、`ffmpeg -version` 首行、`mesa-va-drivers`／`libsoxr0`／`libswresample*` 的套件版本、新聞全跑最後一行進度。驗證：回覆檔裡有這幾項
- [x] 1.3 以 Ctrl+C 方式停下新聞全跑：`pkill -INT -f 'tools\.mkv2mp4wav\.[n]ews'`。驗證：背景任務回報結束（離開碼 130）、紀錄最後印「中斷」那行、`/tmp/mkv2mp4wav-*` 已不存在；寫回覆檔告訴使用者可以重建了

使用者在這裡重建容器（VS Code：Dev Containers: Rebuild Container），重建後的工作接第 2 節。

## 2. 重建後：環境本身

- [x] 2.1 版本記錄：`/etc/os-release` 是 26.04；記下 `ffmpeg -version` 首行、`mesa-va-drivers`／`libsoxr0`／`libswresample*` 版本、`python3 --version`（應仍是 3.12）。驗證：與 1.2 並列寫進回覆檔
- [x] 2.2 `kcmp` 放行、seccomp 仍開著：以 `vscode` 用 python `ctypes` 呼叫 syscall 312 比對自己程序的兩個描述子回 0；`/proc/self/status` 的 `Seccomp` 是 2。驗證：兩個輸出寫進回覆檔
- [x] 2.4 工具都在：`tox` 在 PATH（不在就照 CLAUDE.md 用 `.tox/` 底下的 venv）、`tesseract --version`、`openspec --version`。驗證：三個指令都有輸出
- [x] 2.5 先寫測試（紅）：`tests/devcontainer/__init__.py`、`tests/devcontainer/test_gpu_group.py`，執行 `.devcontainer/gpu-group.sh`，PATH 前面放假的 `stat`／`getent`／`sudo`；四個情形：992 已是 `systemd-resolve`（26.04 實測）→ 只有 `usermod -aG video,systemd-resolve vscode`；992 沒有群組 → `groupadd -g 992 render`（沒有 `-f`）；992 沒有群組但 `render` 是 1001 → `groupadd -g 992 render-992`；裝置不存在 → 不呼叫 `sudo`、離開碼 0。驗證：`tox -e unittest` 這組因為腳本不存在而失敗
- [x] 2.6 實作（綠）：新增 `.devcontainer/gpu-group.sh <裝置> <使用者>`，`post-create.sh` 的群組那段改成呼叫它，註解寫原因（992 被 `systemd-resolve` 佔走那次）。驗證：`tox -e unittest` 全過、`bash -n` 兩支腳本語法正確
- [x] 2.7 文件：`tests/devcontainer/README.md` 放這組的 spec × scenario × 測試檔對照，`tests/README.md` 總表加一行指過去。驗證：兩份都有這幾列；在容器裡用 `sudo bash .devcontainer/gpu-group.sh /dev/dri/renderD128 vscode` 實跑一次，`getent group systemd-resolve` 列出 `vscode`；寫回覆檔請使用者再重建一次

使用者在這裡再重建一次容器（群組變更要新的登入才生效），重建後接 2.3。

- [x] 2.3 以 `vscode` 自己開 VAAPI、不印警告：`id` 列出擁有 `/dev/dri/renderD128` 的群組；`ffmpeg -nostdin -hide_banner -v error -init_hw_device vaapi=va:/dev/dri/renderD128 -f lavfi -i testsrc=s=64x64:d=0.1 -f null -` 的錯誤輸出 grep 不到 `os_same_file_description`；`vainfo --display drm --device /dev/dri/renderD128` 列得出 H264 編碼。驗證：輸出寫進回覆檔

## 3. 重建後：產出不變

- [x] 3.1 全套測試：`tox -e flake8`、`tox -e unittest`、`tox -e e2etest`（含 mkv2mp4wav GPU 三支、mxf2mkv 往返）、`tox -e rebuild`、`python3 -m scripts.news.name_catalogue --check`。驗證：全部通過；若有 ffmpeg 8 造成的失敗，停在這裡、寫回覆說明，另開 change 修程式，不續跑；若只有 tesseract 5.5 讓 e2e OCR 斷言失敗，記下來、回覆講清楚，不擋 3.2
- [x] 3.2 在 scratchpad 寫一次性腳本重做 `20210101_001_午間_Rukai_魯凱`：下載來源（`/docker/news/mkv/2021-01/`），用 `tools.mkv2mp4wav.encode.command`（硬體路徑）與 `tools.mkv2mp4wav.audio.command` 產出到 scratchpad，用 `verify.check_all` 與 `audio.verify` 驗收，不呼叫任何上傳。驗證：預覽檔影格數 23978／23978、影像起點 0.033、驗收全過；音檔驗收通過
- [x] 3.3 下載伺服器上魯凱的 mp4 與 wav，各比 SHA-256。驗證：WAV 相同（不同就算兩邊取樣的最大差異，寫回覆後停下，不續跑）；預覽檔相同或不同都記下位元組數，不同時以 3.2 的驗收為準；比完刪掉 scratchpad 裡的來源與產出，伺服器上兩個檔的位元組數與時間不變

## 4. 續跑與收尾

- [x] 4.1 清 `/tmp/mkv2mp4wav-*` 殘留後，以 `run_in_background: true` 加 `setsid --wait python3 -m tools.mkv2mp4wav.news` 續跑。驗證：開場行的「已完成」等於 1.2 記下的集數（中斷那集若沒傳完則少一）、之後第一集成功且紀錄裡沒有 `os_same_file_description`
- [x] 4.2 回覆檔寫驗收總結：新舊版本對照、四步結果、魯凱比對結果、續跑後第一集的用時（與舊環境平均 6.30 分鐘比較）。驗證：回覆檔存在且有這幾項
- [x] 4.3 「重建後要關掉 VS Code 視窗再開一次，終端機才有 GPU 群組」寫進文件（使用者裁定只寫文件、不自動化）：`devcontainer.json` 的 `postCreateCommand` 前、`post-create.sh` 群組那段、README〈開發環境〉。驗證：去掉註解後 json 解析成功、`bash -n post-create.sh` 通過、`tests/devcontainer` 全過

## Workflow follow-up

- 歸檔時把 `specs/dev-container/spec.md` 同步成主 spec。
- `.devcontainer/devcontainer.json` 的改動由使用者 commit。
