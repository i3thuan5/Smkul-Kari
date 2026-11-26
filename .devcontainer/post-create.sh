#!/usr/bin/env bash
# devcontainer 起好之後跑一遍，裝開發工具佮VAAPI硬體加速需要的驅動。
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ffmpeg mesa-va-drivers vainfo
# 端對端測試（tests-e2e）合成影片愛用；重建 container 了後捌無去，tox -e e2etest 就倒。
sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-tra fonts-noto-cjk

# /dev/dri/renderD128 在主機上屬於哪個群組（GID）每台機器不同，容器裡那個 GID
# 可能沒有群組、也可能已經被別的群組佔走（Ubuntu 26.04 的 992 是 systemd-resolve）。
# 細節與為什麼不用 groupadd -f 寫在 gpu-group.sh。
# 這步跑完時 VS Code 伺服器早就啟動了，已開的終端機拿不到新群組：
# 重建後要關掉視窗再開一次，或用 `sudo su - vscode` 開新登入（見 devcontainer.json）。
bash "$(dirname "$0")/gpu-group.sh" /dev/dri/renderD128 vscode

