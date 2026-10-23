#!/usr/bin/env bash
# devcontainer 起好之後跑一遍，裝開發工具佮VAAPI硬體加速需要的驅動。
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ffmpeg mesa-va-drivers vainfo
# 端對端測試（tests-e2e）合成影片愛用；重建 container 了後捌無去，tox -e e2etest 就倒。
sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-tra fonts-noto-cjk

# /dev/dri/renderD128 tī host頂懸屬佗一個group（GID）逐台機器無仝，
# 容器內底/etc/group閣無這个名，所以用實際GID建group了後才加使用者入去。
render_gid="$(stat -c '%g' /dev/dri/renderD128)"
sudo groupadd -f -g "${render_gid}" render
sudo usermod -aG video,render vscode

