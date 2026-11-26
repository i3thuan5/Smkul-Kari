#!/usr/bin/env bash
# 把使用者加進擁有 GPU 裝置的那個群組，不管它在容器裡叫什麼名字。
#
# 用法：gpu-group.sh <裝置> <使用者>     例：gpu-group.sh /dev/dri/renderD128 vscode
#
# 裝置的群組 GID 是主機給的，逐台機器不同；容器內底不一定有這個 GID 的群組，
# 有的話名字也不一定是 render。2026-11-26 第一次重建成 Ubuntu 26.04 時，
# 主機的 GID 992 在 26.04 image 裡已經是 systemd-resolve，舊寫法
# `groupadd -f -g 992 render` 因為 992 被佔，-f 默默改用 1001 建 render，
# 使用者在 render 裡卻打不開裝置。所以：
#
#   - 這個 GID 已經有群組 → 直接加進那個群組，不另建。
#   - 沒有 → 用這個 GID 建 render；render 這個名字被別的 GID 用掉了
#     （例如前一次用舊寫法建的 1001）就改叫 render-<GID>，不動舊的。
#   - 沒有 GPU 裝置 → 什麼都不做，容器照樣建得起來。
#
# 永遠不用 groupadd -f：它在 GID 被佔時會換一個 GID，正是上面那次出事的原因。
# 另外一起加進 video（card* 裝置是 video 群組的）。
set -euo pipefail

device="$1"
user="$2"

if [ ! -e "$device" ]; then
    echo "找不到 $device，這台沒有 GPU，不設定 GPU 群組。"
    exit 0
fi

gid="$(stat -c '%g' "$device")"
name="$(getent group "$gid" | cut -d: -f1 || true)"

if [ -z "$name" ]; then
    name=render
    if getent group "$name" > /dev/null; then
        name="render-$gid"
    fi
    sudo groupadd -g "$gid" "$name"
fi

sudo usermod -aG "video,$name" "$user"
echo "$user 加進 video 與 $name（GID $gid，擁有 $device）。"
