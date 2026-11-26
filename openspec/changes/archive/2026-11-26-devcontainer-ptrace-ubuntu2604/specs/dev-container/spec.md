## Purpose

開發容器是轉檔、OCR、語音辨識全部工作跑的地方。這份規格保證：容器裡的 GPU 驅動在完整資訊下運作、基底系統的版本是明確選定的，以及換了環境之後，長時間的轉檔批次要先證明產出沒有變才繼續。

## ADDED Requirements

### Requirement: 一般使用者打得開 GPU

容器建好後，`vscode` SHALL 屬於擁有 GPU 裝置（`/dev/dri/renderD128`）的那個群組——以主機上裝置的 GID 為準，不管那個 GID 在容器裡叫什麼名字。那個 GID 在容器裡沒有群組時才新建一個；SHALL NOT 在 GID 被佔用時改用別的 GID 建群組。沒有 GPU 裝置的機器，容器照樣建得起來。

實測（2026-11-26，第一次重建成 26.04）：主機 GPU 群組 GID 992 在 26.04 image 裡已經是 `systemd-resolve`；舊寫法 `groupadd -f -g 992 render` 因為 992 被佔，`-f` 默默改用 1001 建 `render`，`vscode` 在 `render` 裡卻打不開裝置（`Failed to open the given device`），`vainfo` 退去找圖形顯示環境而看似卡住。

#### Scenario: 裝置的 GID 已被別的系統群組佔用

- **WHEN** 裝置的 GID 是 992，容器裡 992 已經是 `systemd-resolve`
- **THEN** `vscode` 被加進 `systemd-resolve`，沒有新建任何群組

#### Scenario: 裝置的 GID 在容器裡沒有群組

- **WHEN** 裝置的 GID 是 992，容器裡沒有 GID 992 的群組，也沒有叫 `render` 的群組
- **THEN** 以 GID 992 新建 `render`，`vscode` 被加進 `render`

#### Scenario: render 這個名字已被別的 GID 用掉

- **WHEN** 裝置的 GID 992 沒有群組，但容器裡已有 GID 1001 的 `render`（前一次用舊寫法建的）
- **THEN** 以 GID 992 新建另一個名字的群組（`render-992`），`vscode` 被加進去；不動 GID 1001 的 `render`

#### Scenario: 沒有 GPU 的機器

- **WHEN** `/dev/dri/renderD128` 不存在
- **THEN** 不建群組、不改使用者，印出說明，容器照樣建好

### Requirement: GPU 驅動判斷得出兩個裝置是不是同一份

容器 SHALL 允許 GPU 驅動比對兩個開啟的 GPU 裝置是否指向同一份；開啟 VAAPI 裝置時，SHALL NOT 出現 `amdgpu: os_same_file_description couldn't determine if two DRM fds reference the same file description` 警告。容器 SHALL NOT 為此關閉整個系統呼叫過濾（seccomp），只放行驅動需要的那一類。

實測（2026-11-25，Ubuntu 24.04、Mesa 25.2.8）：只要開 VAAPI 裝置就會印這行，每個用 GPU 的 ffmpeg 程序一次；新聞紀錄 221 行剛好等於真的有做的 221 集。原因是 `kcmp` 被 Docker 預設 seccomp 擋下（Operation not permitted），而 Docker 只在容器有 `SYS_PTRACE` 能力時才放行它。

#### Scenario: 只開裝置不編碼

- **WHEN** 在容器裡以 ffmpeg 初始化 `/dev/dri/renderD128` 的 VAAPI 裝置、處理一小段合成影片
- **THEN** 錯誤輸出裡沒有 `os_same_file_description` 這串字

#### Scenario: 比對同一個程序的兩個檔案描述子

- **WHEN** 一般使用者（`vscode`）在容器裡以 `kcmp` 比對自己程序裡的兩個檔案描述子
- **THEN** 系統呼叫成功回傳，不是 Operation not permitted

#### Scenario: 系統呼叫過濾仍然開著

- **WHEN** 查看容器內任一程序的 seccomp 狀態
- **THEN** 仍是過濾模式（`/proc/self/status` 的 `Seccomp` 為 2），不是被整個關掉

### Requirement: 基底系統版本明確釘住

容器的基底 image SHALL 指名作業系統的發行版本，SHALL NOT 使用會隨上游移動的標籤。要換版本 SHALL 是改設定檔的明確決定，不是重建時順帶發生。

實查（2026-11-25）：原本用的 `base:ubuntu` 與 `base:ubuntu26.04` 是同一個 digest，而當時的容器是 24.04——不改設定、單純重建，就會把 ffmpeg 6.1 換成 8.0、Mesa 25.2 換成 26.0。

#### Scenario: 設定檔指名版本

- **WHEN** 讀 devcontainer 設定的基底 image
- **THEN** 標籤帶有發行版本號（例如 `ubuntu26.04`），不是 `ubuntu`、`latest` 這類會移動的名稱

#### Scenario: 重建後的系統版本

- **WHEN** 照設定重建容器
- **THEN** `/etc/os-release` 的版本與設定檔指名的一致

### Requirement: 換環境後先實機比對才續跑轉檔批次

容器的基底系統、ffmpeg 或 GPU 驅動換過版本後，長時間的轉檔批次（如 mkv2mp4wav 全跑）SHALL 在續跑前先完成驗收：記錄新舊版本、重做一集已上傳的產出並與伺服器那份比對、全套測試通過。驗收沒過 SHALL NOT 續跑。

批次一跑十幾天，做到一半換了驅動，前後兩半就是不同版本做的；若新版本有問題，等全跑完才發現就要重做幾千集。

#### Scenario: 音檔逐位元相同

- **WHEN** 換環境後，以同一支 FLAC 來源重做一集已上傳的 WAV
- **THEN** 與伺服器上那份的 SHA-256 相同
- **AND** 若不同，停下來比較兩邊取樣的最大差異並交給使用者決定，不續跑

#### Scenario: 預覽檔不同但驗收全過

- **WHEN** 重做的預覽檔與伺服器那份 SHA-256 不同
- **THEN** 只要影格數與來源完全相等、規格驗收全過，可以續跑
- **AND** 兩邊的差異（位元組數、編碼器版本）記在回覆裡

#### Scenario: 新版 ffmpeg 不認得某個選項

- **WHEN** 換環境後，轉檔指令因選項改名或移除而失敗
- **THEN** 驗收不過、不續跑，另外修好程式並通過全套測試後才續跑

#### Scenario: 驗收時不上傳

- **WHEN** 為了比對而重做一集
- **THEN** 產出只留在本機暫存區，比對完刪除，伺服器上的檔案不被覆蓋
