#!/usr/bin/env bash
# Pull one month of video off the SFTP server, cut it into cues, and delete
# each file as soon as it is no longer needed.
#
#   scripts/news/fetch_sftp.sh '族語新聞/110.1-110.10/1月'
#   scripts/news/fetch_sftp.sh '族語新聞/111.1-111.5/2月' --preset titv-news --limit 3
#   scripts/news/fetch_sftp.sh '族語新聞/110.1-110.10/7月' --only '_(38晚間|41午間)'
#
# Disk is the reason this exists. The corpus is ~2.3 TB across ~1,065 files;
# nothing here ever holds more than one video at a time. The video is deleted
# the moment `cues.json` lands, because that is the last step that needs it --
# the vision pass reads `strips/` and `sheets/`, and the SRT is assembled from
# `cues.json`. Peak local usage is one video (~2.2 GB) plus the work dirs,
# which measured ~0.5 GB per episode.
#
# Re-runnable: an episode whose work dir already has `cues.json` is skipped,
# so an interrupted month picks up where it stopped.
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT" || exit 1
PY=$(python3 -m scripts.news.paths --var VENV_PY)
WORK=$(python3 -m scripts.news.paths --var WORK)
LOG=$(python3 -m scripts.news.paths --var LOGS)
PRESETS=$(python3 -m scripts.news.paths --var ENGINE_PRESETS)
STAGE="${STAGE:-/tmp/ilrdf-stage}"
REMOTE_ROOT=/docker/ilrdf-corpus

PRESET=titv-news
LIMIT=0
ONLY=
REMOTE_DIR="${1:-}"
shift || true
while [ $# -gt 0 ]; do
    case "$1" in
        --preset) PRESET="$2"; shift 2 ;;
        --limit)  LIMIT="$2";  shift 2 ;;
        --only)   ONLY="$2";   shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
if [ -z "$REMOTE_DIR" ]; then
    echo "usage: $0 '族語新聞/110.1-110.10/1月'" \
         "[--preset NAME] [--limit N] [--only REGEX]" >&2
    exit 2
fi

mkdir -p "$WORK" "$LOG" "$STAGE"

# --- what is in the folder ------------------------------------------------
# sftp prints non-ASCII file names as octal escapes, so decode them before
# anything tries to use them as paths.
listing=$(mktemp); trap 'rm -f "$listing"' EXIT
"$HERE/sftp.sh" "ls -l \"$REMOTE_ROOT/$REMOTE_DIR\"" 2>/dev/null \
  | "$PY" -c '
import sys
def dec(s):
    out = bytearray(); i = 0
    while i < len(s):
        if s[i] == "\\" and s[i+1:i+4].isdigit():
            out.append(int(s[i+1:i+4], 8)); i += 4
        else:
            out.extend(s[i].encode()); i += 1
    return out.decode("utf-8", "replace")
for line in sys.stdin:
    line = dec(line.rstrip())
    if not line.startswith("-"):
        continue
    parts = line.split(None, 8)
    if len(parts) < 9:
        continue
    name = parts[8].strip()
    if name.lower().endswith((".mp4", ".mxf")):
        print(parts[4] + "\t" + name)
' > "$listing"

# --only names the episodes to take out of the folder, as an extended regex
# matched against the file name. Filling gaps in the coverage means fetching
# a scattered handful out of a folder that holds hundreds of files and a
# couple of hundred GB, which is not a --limit.
if [ -n "$ONLY" ]; then
    filtered=$(mktemp)
    awk -F'\t' -v re="$ONLY" '$2 ~ re' "$listing" > "$filtered"
    mv "$filtered" "$listing"
fi

total=$(wc -l < "$listing")
echo "$(date +%H:%M:%S) $REMOTE_DIR: $total video file(s), preset=$PRESET"
[ "$total" -gt 0 ] || { echo "nothing to do"; exit 1; }

verified_band=0
done_count=0

# The listing is read on fd 3, not stdin. ssh and ffmpeg both drain stdin, and
# on stdin that is the listing itself: the folder loop swallowed every
# remaining episode and reported "finished: 1 episode(s) cut" as if the batch
# were done. Never noticed before because every earlier run used --limit.
while IFS=$'\t' read -r size name <&3; do
    [ -n "$name" ] || continue
    if [ "$LIMIT" -gt 0 ] && [ "$done_count" -ge "$LIMIT" ]; then
        echo "$(date +%H:%M:%S) stopping at --limit $LIMIT"
        break
    fi

    # Work-dir name comes from the catalogue when the file is listed there, so
    # the SRT ends up named the same way as the February batch; otherwise fall
    # back to the file's own stem.
    slug=$("$PY" -m scripts.news.resolve_slug "$REMOTE_DIR/$name")
    dst="$WORK/$slug.work"
    if [ -f "$dst/cues.json" ]; then
        echo "$(date +%H:%M:%S) skip  $slug (already cut)"
        continue
    fi

    local_file="$STAGE/$name"
    echo "$(date +%H:%M:%S) get   $slug  ($(( size / 1000000 )) MB)"
    if ! "$HERE/sftp.sh" "get \"$REMOTE_ROOT/$REMOTE_DIR/$name\" \"$local_file\"" \
         > "$LOG/$slug.get.log" 2>&1; then
        echo "$(date +%H:%M:%S) FAIL  download $slug"; rm -f "$local_file"; continue
    fi

    # Verify before decoding. Two of the 24 February masters were truncated
    # uploads whose headers still claimed the full duration -- ffprobe could
    # not tell, only the byte count could.
    got=$(stat -c %s "$local_file" 2>/dev/null || echo 0)
    if [ "$got" != "$size" ]; then
        echo "$(date +%H:%M:%S) FAIL  $slug incomplete: $got of $size bytes"
        rm -f "$local_file"; continue
    fi

    # Check the band once per folder, on the first file that gets this far.
    if [ "$verified_band" -eq 0 ]; then
        if "$PY" -m scripts.news.verify_band "$local_file" --preset "$PRESET" --quiet; then
            verified_band=1
        else
            echo "$(date +%H:%M:%S) ABORT band does not match preset '$PRESET'."
            echo "  Run verify_band.py without --quiet to see the profile, and"
            echo "  add a preset for this folder before continuing."
            rm -f "$local_file"; exit 1
        fi
    fi

    echo "$(date +%H:%M:%S) cues  $slug"
    if "$PY" -m scripts.subs2srt.cli cues "$local_file" -o "$dst" \
         --presets "$PRESETS" --preset "$PRESET" --sheets \
         > "$LOG/$slug.cues.log" 2>&1; then
        rm -f "$local_file"          # the video is not needed past this point
        done_count=$((done_count + 1))
        ncues=$("$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['cues']))" "$dst/cues.json")
        echo "$(date +%H:%M:%S) done  $slug  $ncues cues, video deleted"
    else
        echo "$(date +%H:%M:%S) FAIL  cues $slug -- see $LOG/$slug.cues.log"
        rm -f "$local_file"
    fi
done 3< "$listing"

echo "$(date +%H:%M:%S) finished: $done_count episode(s) cut"
echo "next: python3 -m scripts.news.gap_sheets   then the vision pass"
