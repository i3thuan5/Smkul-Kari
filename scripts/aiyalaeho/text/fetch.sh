#!/usr/bin/env bash
# Fetch the whole 上字文稿 corpus off SFTP into a local staging copy.
#
#   scripts/aiyalaeho/text/fetch.sh
#
# This is deliberately the simple cousin of scripts/news/fetch_sftp.sh, not
# a smaller copy of it. That script exists because the news corpus is
# ~2.3 TB across ~1,065 files -- it downloads one episode at a time, deletes
# a transcode the moment cues.json lands, and can resume a month that was
# interrupted partway. None of that machinery earns its keep here: this
# corpus is 243 files, 9.2 MB total. It fits in memory, let alone on disk.
# So this script does the obvious thing -- wipe the staging copy and
# re-download everything, every run. "Did the fetch work" is answered by
# running it again and diffing, not by tracking partial progress.
#
# The remote layout nests one level deeper in exactly one place (a "上字"
# subfolder under 開會025), so listing is recursive rather than a single
# flat `ls`.
set -u
set -o pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
SFTP="$ROOT/scripts/news/sftp.sh"
PY="${PYTHON:-python3}"

REMOTE=$("$PY" -m scripts.aiyalaeho.paths --var TEXT_REMOTE)
LOCAL=$("$PY" -m scripts.aiyalaeho.paths --var TEXT_WORK)

rm -rf "$LOCAL"
mkdir -p "$LOCAL"

# sftp prints non-ASCII file names as octal escapes (\346\226\207...);
# decode before anything treats them as paths. Same decoder as
# fetch_sftp.sh uses for the news side, so the two do not drift apart.
decode_and_dispatch() {
    local remote_dir="$1"
    local local_dir="$2"
    "$SFTP" ls "$remote_dir" 2>/dev/null | "$PY" -c '
import sys

def dec(s):
    out = bytearray()
    i = 0
    while i < len(s):
        if s[i] == "\\" and s[i + 1:i + 4].isdigit():
            out.append(int(s[i + 1:i + 4], 8))
            i += 4
        else:
            out.extend(s[i].encode())
            i += 1
    return out.decode("utf-8", "replace")

for line in sys.stdin:
    line = dec(line.rstrip())
    parts = line.split(None, 8)
    if len(parts) < 9:
        continue
    kind = parts[0][0]
    name = parts[8].strip()
    if kind not in ("d", "-"):
        continue
    print(kind + "\t" + name)
'
}

fetch_dir() {
    local remote_dir="$1"
    local local_dir="$2"
    mkdir -p "$local_dir"
    while IFS=$'\t' read -r kind name; do
        [[ -n "$name" ]] || continue
        if [[ "$kind" == "d" ]]; then
            fetch_dir "$remote_dir/$name" "$local_dir/$name"
        else
            "$SFTP" get "$remote_dir/$name" "$local_dir/$name"
        fi
    done < <(decode_and_dispatch "$remote_dir" "$local_dir")
}

fetch_dir "$REMOTE" "$LOCAL"

count=$(find "$LOCAL" -type f | wc -l)
echo "抓到 $count 個檔，落佇 $LOCAL"
