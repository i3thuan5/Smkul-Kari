#!/usr/bin/env bash
# Fetch one broadcast month off the SFTP server, cut it into cues, and delete
# each file as soon as it is no longer needed.
#
#   scripts/news/plan_month.py 2021-01        # register the month first
#   scripts/news/fetch_sftp.sh 2021-01
#   scripts/news/fetch_sftp.sh 2021-01 --limit 2            # try it out
#   scripts/news/fetch_sftp.sh 2021-02 --only '_(38晚間|41午間)'
#   scripts/news/fetch_sftp.sh 2021-10 --jobs 4 --threads 2
#
# Concurrency: downloads run one at a time; each downloaded episode is cut
# and refined in the background, at most `--jobs` (env FETCH_JOBS, default
# 6) at once, each ffmpeg on `--threads` (env FFMPEG_THREADS, default 2)
# threads. Measured here: 2 threads use a core at 0.98 efficiency, the
# default 8-9 only 0.67 -- the same work burns 49% more CPU. 16 cores over
# (2 threads + ~0.5 core of Python) is about 6 episodes.
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
# is `--jobs` + 1 videos (2.2 GB transcode, up to 19.7 GB master) plus the
# work dirs, which measured ~0.5 GB per episode.
#
# Re-runnable: an interrupted month picks up where it stopped. An episode
# that already has a timeline -- in a work dir or in the store -- is not
# downloaded at all, because cutting is the last step that needs the video.
# Delivered episodes are never fetched here either; a reread downloads what
# it needs when it runs. 使用者裁定 2026-08-31.
# `plan_month.py --todo` decides all of that.
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT" || exit 1
# Both are checked on their own; the gate runs without -x, so following
# them from here would only report that it did not.
# shellcheck disable=SC1091
source "$HERE/jobpool.sh"
# shellcheck disable=SC1091
source "$HERE/videocheck.sh"
# 這支 interpreter 是家己揀ê，毋是寫死ê：`SUBS2SRT_PY` → `~/.venvs/
# subs2srt` → repo ê `.tox/rebuild` → 這馬走ê python，頭一支入會去
# numpy 佮 PIL ê就用伊。（本底寫死一條路，別台機器就講「沒有此一
# 檔案或目錄」，規个月ê抓檔停佇遮。）
PY=$(python3 -m scripts.news.paths --var VENV_PY) || exit 1
if [[ ! -x "$PY" ]]; then
    echo "揣無會使走ê python：$PY" >&2
    echo "  用 SUBS2SRT_PY=/path/to/python 指定，抑是 tox -e rebuild 建起來" >&2
    exit 1
fi
PRESETS=$(python3 -m scripts.news.paths --var ENGINE_PRESETS)

# 無指定就照月份：`plan_month --preset`（presets.json 逐个 preset 宣告
# ê `months`）。2021-11 起ê母帶紅條上緣 852，用下緣 848 ê版型。
PRESET=
OPENING_ONLY=
LIMIT=0
ONLY=
JOBS="${FETCH_JOBS:-6}"
THREADS="${FFMPEG_THREADS:-2}"
PRINT_CONFIG=
MONTH="${1:-}"
shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --preset)  PRESET="$2";  shift 2 ;;
        --limit)   LIMIT="$2";   shift 2 ;;
        --only)    ONLY="$2";    shift 2 ;;
        --jobs)    JOBS="$2";    shift 2 ;;
        --threads) THREADS="$2"; shift 2 ;;
        --print-config) PRINT_CONFIG=1; shift ;;
        --opening-only) OPENING_ONLY=1; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
if [[ ! "$MONTH" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    echo "usage: $0 <播出月份，親像 2021-01>" \
         "[--preset NAME] [--limit N] [--only REGEX]" \
         "[--jobs N] [--threads N] [--opening-only]" >&2
    exit 2
fi
if ! pool_positive_int "$JOBS"; then
    echo "--jobs／FETCH_JOBS 愛是正整數，收著 '$JOBS'" >&2; exit 2
fi
if ! pool_positive_int "$THREADS"; then
    echo "--threads／FFMPEG_THREADS 愛是正整數，收著 '$THREADS'" >&2; exit 2
fi
# Month folders: kithann/out/news/{logs,stage}/<年-月>/, and each work dir
# under 1-ocr/<年-月>/. The fetch unit is a broadcast month, so every
# episode here belongs to $MONTH.
LOG=$(python3 -m scripts.news.paths --log-dir "$MONTH") || exit 1
STAGE="${STAGE:-$(python3 -m scripts.news.paths --stage-dir "$MONTH")}" || exit 1

if [[ -z "$PRESET" ]]; then
    PRESET=$(python3 -m scripts.news.plan_month "$MONTH" --preset) || exit 1
fi

if [[ -n "$PRINT_CONFIG" ]]; then
    echo "jobs=$JOBS"
    echo "threads=$THREADS"
    echo "preset=$PRESET"
    if [[ -n "$OPENING_ONLY" ]]; then echo "mode=opening"; else echo "mode=cut"; fi
    exit 0
fi

mkdir -p "$LOG" "$STAGE"

# --- 已經切過ê集數補做片頭辨識（2021 年）-----------------------------
# 影片早就刣掉矣，干焦抓頭尾兩段截 20／30／40 秒三格（`opening
# grab-remote`，curl 用 ~/.netrc），毋切 cue、毋刣任何物件。
if [[ -n "$OPENING_ONLY" ]]; then
    opening=$(mktemp); trap 'rm -f "$opening"' EXIT
    "$PY" -m scripts.news.plan_month "$MONTH" --opening > "$opening" || exit 1
    echo "$(date +%H:%M:%S) $MONTH: $(wc -l < "$opening") episode(s) for the opening frames"
    got=0
    while IFS=$'\t' read -r slug remote <&3; do
        dst=$(python3 -m scripts.news.paths --work-of "$slug") || continue
        if "$PY" -m scripts.news.opening grab-remote "$remote" "$dst" \
             > "$LOG/$slug.opening.log" 2>&1; then
            got=$((got + 1))
            echo "$(date +%H:%M:%S) open  $slug"
        else
            echo "$(date +%H:%M:%S) FAIL  opening $slug -- see $LOG/$slug.opening.log"
        fi
    done 3< "$opening"
    echo "$(date +%H:%M:%S) finished: $got opening(s)"
    echo "next: python3 -m scripts.news.opening sheet $MONTH   then the reader"
    exit 0
fi

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
echo "$(date +%H:%M:%S) $MONTH: $total episode(s) to fetch, preset=$PRESET," \
     "$JOBS at once, $THREADS ffmpeg thread(s) each"
if [[ "$total" -eq 0 ]]; then
    echo "nothing to do -- run plan_month.py $MONTH first if this is a new month"
    exit 1
fi

# --- remote byte counts, one listing per folder the month touches ----------
# sftp prints non-ASCII file names as octal escapes, so decode them before
# anything tries to use them as paths.
sizes=$(mktemp); trap 'rm -f "$todo" "$sizes"' EXIT
cut -f2 "$todo" | xargs -r -n1 dirname | sort -u | while read -r folder; do
    "$HERE/sftp.sh" ls "$folder" 2>/dev/null \
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
    if name.lower().endswith((".mp4", ".mxf", ".mkv")):
        print(folder + "/" + name + "\t" + parts[4])
' "$folder"
done > "$sizes"

verified_bands=" "
started=0
finished=$(mktemp); trap 'rm -f "$todo" "$sizes" "$finished"' EXIT

# One episode after its download: cut, refine, drop the transcode. Runs in
# the background, so it reports through its own lines and `$finished`.
# 切 cue＋精修了後、刪影片進前：片頭三格、逐秒特徵、段落表、判不準ê
# 格、帶外補切。影片猶佇磁碟ê時一擺做煞，後壁確認毋免閣抓。
after_cut() {
    local slug=$1 dst=$2 local_file=$3
    local low="nice -n 15 ionice -c 3"
    local year lang band duration secs
    year=$(cut -d_ -f3 <<< "$slug" | cut -c1-4)
    lang=${slug##*_}
    band=$("$PY" -c 'import json,sys
r = json.load(open(sys.argv[1]))[sys.argv[2]]["region"]
print("%d,%d" % (r[1], r[1] + r[3]))' "$PRESETS" "$PRESET") &&
    duration=$("$PY" -c 'import json,sys
print(json.load(open(sys.argv[1]))["duration"])' \
        "$("$PY" -m scripts.news.paths --cues-of "$dst")") &&
    $low "$PY" -m scripts.news.opening grab "$local_file" "$dst" &&
    $low "$PY" -m scripts.news.shots extract "$local_file" "$dst" \
        --year "$year" --preset "$PRESET" --threads "$THREADS" &&
    "$PY" -m scripts.news.segments make "$dst" --language "$lang" \
        --duration "$duration" --band "$band" &&
    secs=$("$PY" -m scripts.news.segments pending "$dst") &&
    { [[ -z "$secs" ]] || $low "$PY" -m scripts.news.shots judge \
        "$local_file" "$dst" $secs; } &&
    # 受訪者名條（段落表「受訪者語言別代號」）：影片猶佇ê時截，
    # 2024-12 事後補，69 集攏愛重抓母帶。
    $low "$PY" -m scripts.news.namebars grab "$dst" "$local_file" \
        --preset "$PRESET" &&
    $low "$PY" -m scripts.news.segment_recut "$dst" "$local_file"
}

process_episode() {
    local slug=$1 dst=$2 local_file=$3 name=$4
    local kept ncues
    # nice/ionice 落去，佮 encode_master.sh 仝一套：一批走幾點鐘，
    # 袂使kā別人ê機器食牢去（使用者裁定 -- CPU 影響到其他工作）。
    echo "$(date +%H:%M:%S) cues  $slug"
    if nice -n 15 ionice -c 3 "$PY" -m scripts.ocr.cli cues "$local_file" -o "$dst" \
         --presets "$PRESETS" --preset "$PRESET" --sheets --threads "$THREADS" \
         > "$LOG/$slug.cues.log" 2>&1; then
        # Refine the boundaries while the video is still on disk. A refine
        # failure keeps the coarse 0.2s timings and does not stop the batch
        # -- the log names the episode for a later retry.
        echo "$(date +%H:%M:%S) refine $slug"
        if ! nice -n 15 ionice -c 3 "$PY" -m scripts.news.refine_cues "$local_file" \
             "$("$PY" -m scripts.news.paths --coarse-of "$dst")" \
             --presets "$PRESETS" --preset "$PRESET" --threads "$THREADS" \
             > "$LOG/$slug.refine.log" 2>&1; then
            echo "$(date +%H:%M:%S) WARN  refine $slug failed, keeping" \
                 "coarse timings -- see $LOG/$slug.refine.log"
        fi
        # A master is kept: `archive_batch` still has to encode the mkv out
        # of it, and re-fetching a 19 GB master to do that would be a second
        # download of the same file. It deletes the master once the encode
        # has verified. Transcodes are not archived -- they are already a
        # delivery copy -- so those go now, which is what keeps peak disk at
        # `--jobs` + 1 videos.
        echo "$(date +%H:%M:%S) segs  $slug"
        if ! after_cut "$slug" "$dst" "$local_file" \
             > "$LOG/$slug.segments.log" 2>&1; then
            echo "$(date +%H:%M:%S) WARN  片頭／段落 $slug failed, video kept" \
                 "-- see $LOG/$slug.segments.log"
            touch "$local_file.keep"
        fi
        kept=
        case "${name,,}" in
            *.mxf) kept=" (master kept for archiving)" ;;
            *) [[ -f "$local_file.keep" ]] || rm -f "$local_file" ;;
        esac
        echo "$slug" >> "$finished"
        ncues=$("$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['cues']))" \
                "$("$PY" -m scripts.news.paths --cues-of "$dst")")
        echo "$(date +%H:%M:%S) done  $slug  $ncues cues$kept"
    else
        echo "$(date +%H:%M:%S) FAIL  cues $slug -- see $LOG/$slug.cues.log"
        rm -f "$local_file"
    fi
}

# The list is read on fd 3, not stdin. ssh and ffmpeg both drain stdin, and
# on stdin that is the list itself: the loop swallowed every remaining
# episode and reported "finished: 1 episode(s) cut" as if the batch were
# done. Never noticed before because every earlier run used --limit.
while IFS=$'\t' read -r slug remote <&3; do
    [[ -n "$remote" ]] || continue
    if [[ "$LIMIT" -gt 0 ]] && [[ "$started" -ge "$LIMIT" ]]; then
        echo "$(date +%H:%M:%S) stopping at --limit $LIMIT"
        break
    fi

    # Nothing on this list has been cut -- plan_month decides that, asking
    # the work dirs *and* the store. So there is no "fetch but do not cut"
    # case to handle here, and no way for this loop to renumber the cues of
    # an episode that already has a timeline.
    dst=$(python3 -m scripts.news.paths --work-of "$slug") || continue

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
        if ! "$HERE/sftp.sh" get "$remote" "$local_file" \
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

    # A file whose byte count matches can still be broken on the server
    # (an upload cut short: no moov, nothing decodes). That is this
    # episode's problem, not the folder's -- say so and move on, rather
    # than letting the band check below call it a layout mismatch and stop
    # the whole month (2021-10's first file did exactly that).
    if ! video_readable "$local_file"; then
        echo "$(date +%H:%M:%S) FAIL  $slug：影片打不開（伺服器上的檔不完整？）$remote"
        rm -f "$local_file"; continue
    fi

    # Check the band once per folder, on the first file from it that gets
    # this far. A month can span folders, and layout follows the folder.
    # niced like the other decode steps: it is short (a few minutes of row
    # profiles, once per folder) but it is still ffmpeg, and the rule here
    # is that nothing this script starts competes with the user's machine.
    if [[ "$verified_bands" != *" $folder "* ]]; then
        if nice -n 15 ionice -c 3 \
           "$PY" -m scripts.news.verify_band "$local_file" --preset "$PRESET" --quiet; then
            verified_bands="$verified_bands$folder "
        else
            echo "$(date +%H:%M:%S) ABORT band does not match preset '$PRESET'."
            echo "  Folder: $folder"
            echo "  Run verify_band.py without --quiet to see the profile, and"
            echo "  add a preset for this folder before continuing."
            echo "  (waiting for the episodes already cutting to finish)"
            rm -f "$local_file"; wait; exit 1
        fi
    fi

    # Wait for a free slot only now: downloading while every slot is busy
    # keeps the pipe full, at the price of one extra staged video.
    pool_wait_slot "$JOBS"
    started=$((started + 1))
    process_episode "$slug" "$dst" "$local_file" "$name" 3<&- < /dev/null &
done 3< "$todo"
wait

echo "$(date +%H:%M:%S) finished: $(wc -l < "$finished") of $started episode(s) cut"
echo "next: python3 -m scripts.news.gap_sheets   then the vision pass"
