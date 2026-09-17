# shellcheck shell=bash
# 影片打不打得開。`source` 進來用：
#
#   source scripts/news/videocheck.sh
#   video_readable "$file" || echo "壞檔"
#
# 位元組數對得上不代表檔是好的：伺服器上的檔若上傳就不完整，遠端列出來
# 的大小就是那個殘缺的大小。mp4 的索引（moov）放在檔尾，少了尾巴整支
# 就打不開（2021-10 的 21NL003_274午間 就是這樣）。這一步要在驗字幕帶
# 之前做，否則壞檔會被報成「字幕帶和 preset 不合」，整個月停下來。

video_readable() {
    local duration
    duration=$(ffprobe -v error -select_streams v:0 \
        -show_entries format=duration -of csv=p=0 "$1" 2>/dev/null) || return 1
    [[ "$duration" =~ ^[0-9]+(\.[0-9]+)?$ ]] || return 1
    awk -v d="$duration" 'BEGIN { exit !(d > 0) }'
}
