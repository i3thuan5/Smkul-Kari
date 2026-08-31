#!/usr/bin/env bash
# Fetch one broadcast month off the SFTP server, cut it into cues, and delete
# each file as soon as it is no longer needed.
#
#   scripts/news/plan_month.py 2021-01        # register the month first
#   scripts/news/fetch_sftp.sh 2021-01
#   scripts/news/fetch_sftp.sh 2021-01 --limit 2            # try it out
#   scripts/news/fetch_sftp.sh 2021-02 --only '_(38晚間|41午間)'
#
# The unit is a **broadcast month**, not a source folder. They are not the
# same thing: six broadcast months are spread across two folders each, and
# `110.1-110.10/7月/` holds 140 files of which 66 are February's programmes.
# So what to fetch comes from the inventory -- `plan_month.py` put it there,
# one chosen source path per episode -- and the remote listing is used only
# to check byte counts.
#
# Disk is the reason this exists. The corpus is ~2.3 TB across ~1,065 files;
# nothing here ever holds more than one video at a time. A transcode is
# deleted the moment `cues.json` lands, because that is the last step that
# needs it -- the vision pass reads `strips/` and `sheets/`, and the SRT is
# assembled from `cues.json`. A **master** is kept instead, because
# `scripts/transcode/archive_batch.py` has to encode the archival mkv out of
# it; it deletes the master once that encode has verified. Peak local usage
# is one video (2.2 GB transcode, up to 19.7 GB master) plus the work dirs,
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
STAGE="${STAGE:-$ROOT/kithann/out/stage}"
REMOTE_ROOT=/docker/ilrdf-corpus

PRESET=titv-news
LIMIT=0
ONLY=
MONTH="${1:-}"
shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --preset) PRESET="$2"; shift 2 ;;
        --limit)  LIMIT="$2";  shift 2 ;;
        --only)   ONLY="$2";   shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
if [[ ! "$MONTH" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    echo "usage: $0 <播出月份，親像 2021-01>" \
         "[--preset NAME] [--limit N] [--only REGEX]" >&2
    exit 2
fi

mkdir -p "$WORK" "$LOG" "$STAGE"

# --- what this month still needs ------------------------------------------
todo=$(mktemp); trap 'rm -f "$todo"' EXIT
"$PY" -m scripts.news.plan_month "$MONTH" --todo > "$todo" || exit 1

# --only picks a handful out of the month, as an extended regex matched
# against the file name. Filling gaps in the coverage means fetching a
# scattered few, which is not a --limit.
if [[ -n "$ONLY" ]]; then
    filtered=$(mktemp)
    awk -F'\t' -v re="$ONLY" '$2 ~ re' "$todo" > "$filtered"
    mv "$filtered" "$todo"
fi

total=$(wc -l < "$todo")
echo "$(date +%H:%M:%S) $MONTH: $total episode(s) to fetch, preset=$PRESET"
if [[ "$total" -eq 0 ]]; then
    echo "nothing to do -- run plan_month.py $MONTH first if this is a new month"
    exit 1
fi

# --- remote byte counts, one listing per folder the month touches ----------
# sftp prints non-ASCII file names as octal escapes, so decode them before
# anything tries to use them as paths.
sizes=$(mktemp); trap 'rm -f "$todo" "$sizes"' EXIT
cut -f2 "$todo" | xargs -r -n1 dirname | sort -u | while read -r folder; do
    "$HERE/sftp.sh" ls "$REMOTE_ROOT/$folder" 2>/dev/null \
      | "$PY" -c '
import sys
folder = sys.argv[1]
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
        print(folder + "/" + name + "\t" + parts[4])
' "$folder"
done > "$sizes"

verified_bands=" "
done_count=0

# The list is read on fd 3, not stdin. ssh and ffmpeg both drain stdin, and
# on stdin that is the list itself: the loop swallowed every remaining
# episode and reported "finished: 1 episode(s) cut" as if the batch were
# done. Never noticed before because every earlier run used --limit.
while IFS=$'\t' read -r slug remote <&3; do
    [[ -n "$remote" ]] || continue
    if [[ "$LIMIT" -gt 0 ]] && [[ "$done_count" -ge "$LIMIT" ]]; then
        echo "$(date +%H:%M:%S) stopping at --limit $LIMIT"
        break
    fi

    dst="$WORK/$slug.work"
    if [[ -f "$dst/cues.json" ]]; then
        echo "$(date +%H:%M:%S) skip  $slug (already cut)"
        continue
    fi

    name=$(basename "$remote")
    folder=$(dirname "$remote")
    size=$(awk -F'\t' -v p="$remote" '$1 == p {print $2}' "$sizes")
    if [[ -z "$size" ]]; then
        echo "$(date +%H:%M:%S) FAIL  $slug: 伺服器頂懸無 $remote"
        continue
    fi

    local_file="$STAGE/$name"
    have=$(stat -c %s "$local_file" 2>/dev/null || echo 0)
    if [[ "$have" = "$size" ]]; then
        echo "$(date +%H:%M:%S) reuse $slug (already staged)"
    else
        echo "$(date +%H:%M:%S) get   $slug  ($(( size / 1000000 )) MB)"
        if ! "$HERE/sftp.sh" get "$REMOTE_ROOT/$remote" "$local_file" \
             > "$LOG/$slug.get.log" 2>&1; then
            echo "$(date +%H:%M:%S) FAIL  download $slug"; rm -f "$local_file"; continue
        fi

        # Verify before decoding. Two of the 24 February masters were
        # truncated uploads whose headers still claimed the full duration --
        # ffprobe could not tell, only the byte count could.
        got=$(stat -c %s "$local_file" 2>/dev/null || echo 0)
        if [[ "$got" != "$size" ]]; then
            echo "$(date +%H:%M:%S) FAIL  $slug incomplete: $got of $size bytes"
            rm -f "$local_file"; continue
        fi
    fi

    # Check the band once per folder, on the first file from it that gets
    # this far. A month can span folders, and layout follows the folder.
    if [[ "$verified_bands" != *" $folder "* ]]; then
        if "$PY" -m scripts.news.verify_band "$local_file" --preset "$PRESET" --quiet; then
            verified_bands="$verified_bands$folder "
        else
            echo "$(date +%H:%M:%S) ABORT band does not match preset '$PRESET'."
            echo "  Folder: $folder"
            echo "  Run verify_band.py without --quiet to see the profile, and"
            echo "  add a preset for this folder before continuing."
            rm -f "$local_file"; exit 1
        fi
    fi

    # nice/ionice 落去，佮 encode_master.sh 仝一套：一批走幾點鐘，
    # 袂使kā別人ê機器食牢去（使用者裁定 -- CPU 影響到其他工作）。
    echo "$(date +%H:%M:%S) cues  $slug"
    if nice -n 15 ionice -c 3 "$PY" -m scripts.ocr.cli cues "$local_file" -o "$dst" \
         --presets "$PRESETS" --preset "$PRESET" --sheets \
         > "$LOG/$slug.cues.log" 2>&1; then
        # Refine the boundaries while the video is still on disk. A refine
        # failure keeps the coarse 0.2s timings and does not stop the batch
        # -- the log names the episode for a later retry.
        echo "$(date +%H:%M:%S) refine $slug"
        if ! nice -n 15 ionice -c 3 "$PY" -m scripts.news.refine_cues "$local_file" \
             "$dst/cues.json" > "$LOG/$slug.refine.log" 2>&1; then
            echo "$(date +%H:%M:%S) WARN  refine $slug failed, keeping" \
                 "coarse timings -- see $LOG/$slug.refine.log"
        fi
        # A master is kept: `archive_batch` still has to encode the mkv out
        # of it, and re-fetching a 19 GB master to do that would be a second
        # download of the same file. It deletes the master once the encode
        # has verified. Transcodes are not archived -- they are already a
        # delivery copy -- so those go now, which is what keeps peak disk at
        # one video.
        kept=
        case "${name,,}" in
            *.mxf) kept=" (master kept for archiving)" ;;
            *) [[ -f "$local_file.keep" ]] || rm -f "$local_file" ;;
        esac
        done_count=$((done_count + 1))
        ncues=$("$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['cues']))" "$dst/cues.json")
        echo "$(date +%H:%M:%S) done  $slug  $ncues cues$kept"
    else
        echo "$(date +%H:%M:%S) FAIL  cues $slug -- see $LOG/$slug.cues.log"
        rm -f "$local_file"
    fi
done 3< "$todo"

echo "$(date +%H:%M:%S) finished: $done_count episode(s) cut"
echo "next: python3 -m scripts.news.gap_sheets   then the vision pass"
