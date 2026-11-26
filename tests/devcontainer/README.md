# tests/devcontainer/：開發容器的設定腳本

`.devcontainer/` 底下能離線測的部分。`post-create.sh` 一開頭就 `apt-get`，整支沒辦法離線跑，所以會出錯的邏輯拆成獨立腳本再測。測試在 PATH 最前面放假的 `stat`、`getent`、`sudo`（測試裡現寫到暫存目錄），只檢查腳本送出了哪些指令，不真的改群組。

| spec | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| dev-container：一般使用者打得開 GPU | 2026-11-26 重建成 Ubuntu 26.04：主機 GPU 群組 GID 992 在容器裡已是 `systemd-resolve`，舊寫法 `groupadd -f -g 992 render` 默默改用 1001 建 `render`，vscode 打不開裝置、`vainfo` 看似卡住——要直接加進 `systemd-resolve`，不另建群組 | `test_gpu_group.py` |
| dev-container：一般使用者打得開 GPU | 24.04 的情形：992 沒有群組，用 992 建 `render`，不可以帶 `-f`（GID 被佔時它會換一個 GID） | `test_gpu_group.py` |
| dev-container：一般使用者打得開 GPU | 前一次失敗的重建留下 GID 1001 的 `render`：再建 `render` 會撞名，要改叫 `render-992`、不動舊的 | `test_gpu_group.py` |
| dev-container：一般使用者打得開 GPU | 沒有 GPU 的機器：`post-create.sh` 是 `set -e`，`stat` 失敗會讓整個容器建不起來——要什麼都不做、離開碼 0 | `test_gpu_group.py` |

`kcmp` 放行、基底 image 版本、換環境後重做一集比對，這幾條沒有可以離線測的程式，是重建後在容器裡實機驗收的。
