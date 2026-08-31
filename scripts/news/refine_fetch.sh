#!/usr/bin/env bash
# Refine the boundaries of every delivered episode: download its master from
# SFTP, run refine_cues against the store's cues.json, delete the video.
#
#   scripts/news/refine_fetch.sh              # all unrefined episodes
#   scripts/news/refine_fetch.sh --limit 1    # pilot run
#
# Resumable: an episode whose store cues.json already carries "refined" is
# skipped, so an interrupted batch picks up where it stopped.
#
# STAGE sharing rules (kithann/out/stage, big disk, survives restarts):
#   * a file already in STAGE with the right byte count is reused, not
#     re-downloaded;
#   * a file with a companion `<name>.keep` sentinel is never deleted here --
#     whoever created the sentinel owns the deletion;
#   * only one fetch loop at a time: stage.lock holds the owning pid.
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT" || exit 1
PY=$(python3 -m scripts.news.paths --var VENV_PY) || exit 1
if [[ ! -x "$PY" ]]; then
    echo "揣無會使走ê python：$PY" >&2
    echo "  用 SUBS2SRT_PY=/path/to/python 指定，抑是 tox -e rebuild 建起來" >&2
    exit 1
fi
KARI=$(python3 -m scripts.news.paths --var KARI)
STAGE="${STAGE:-$ROOT/kithann/out/stage}"
LOG="$ROOT/kithann/out/mxf-logs"
REMOTE_ROOT=/docker/ilrdf-corpus
DELTA="$ROOT/openspec/changes/refine-cue-timing/timing-delta.jsonl"

LIMIT=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit) LIMIT="$2"; shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$STAGE" "$LOG"

# --- single fetch loop at a time ------------------------------------------
if [[ -f "$STAGE/stage.lock" ]]; then
    other=$(cat "$STAGE/stage.lock")
    if kill -0 "$other" 2>/dev/null; then
        echo "another fetch loop (pid $other) owns $STAGE; refusing" >&2
        exit 1
    fi
fi
echo $$ > "$STAGE/stage.lock"
trap 'rm -f "$STAGE/stage.lock"' EXIT

# --- which episodes still need refining, and where their masters live -----
# The inventory carries two vintages of video path: the February mxf batch
# recorded the old local mount ("2月/<file>", actually served from
# 2月原始mxf檔/ on the SFTP side) and later batches record corpus-relative
# paths ("ilrdf-corpus/...").
jobs=$("$PY" - <<'EOF'
import json
import os
import sys

sys.path.insert(0, ".")
from scripts.news import paths

for entry in json.load(open(paths.INVENTORY, encoding="utf-8")):
    if entry.get("pending") or entry["truncated"]:
        continue
    cues_path = paths.stage_path(paths.KARI_CUES,
                                 entry["srt_name"], ".json")
    manifest = json.load(open(cues_path, encoding="utf-8"))
    if manifest.get("refined"):
        continue
    video = entry["video"]
    name = os.path.basename(video)
    if video.startswith("ilrdf-corpus/"):
        remote = video[len("ilrdf-corpus/"):]
    else:
        remote = name
    # 2 月那批在 inventory 記做捷徑 "2月/<檔名>"（那是它們以前掛在
    # 本機的位置）；SFTP 上真正的目錄深一層，短的那個會 404。
    # scripts/transcode/archive_batch.py 有同一份對應。
    if remote.startswith("2月/") or "/" not in remote:
        remote = "族語新聞/110.1-110.10/2月原始mxf檔/" + name
    print("%s\t%s\t%s" % (entry["srt_name"], remote, name))
EOF
)

total=$(printf '%s\n' "$jobs" | grep -c . || true)
echo "$(date +%H:%M:%S) $total episode(s) still unrefined"
[[ "$total" -gt 0 ]] || { echo "nothing to do"; exit 0; }

done_count=0
failed=0
# Read the job list on fd 3: sftp (and anything else in the loop body that
# touches stdin) would otherwise eat lines of the list mid-loop.
while IFS=$'\t' read -r -u 3 srt_name remote name; do
    [[ -n "$srt_name" ]] || continue
    if [[ "$LIMIT" -gt 0 ]] && [[ "$done_count" -ge "$LIMIT" ]]; then
        echo "$(date +%H:%M:%S) stopping at --limit $LIMIT"
        break
    fi

    size=$("$HERE/sftp.sh" ls "$REMOTE_ROOT/$remote" 2>/dev/null \
        | awk '/^-/{print $5; exit}')
    if [[ -z "$size" ]]; then
        echo "$(date +%H:%M:%S) FAIL  $srt_name: not found on SFTP"
        failed=$((failed + 1)); continue
    fi

    local_file="$STAGE/$name"
    have=$(stat -c %s "$local_file" 2>/dev/null || echo 0)
    if [[ "$have" = "$size" ]]; then
        echo "$(date +%H:%M:%S) reuse $srt_name (already staged)"
    else
        echo "$(date +%H:%M:%S) get   $srt_name  ($(( size / 1000000 )) MB)"
        if ! "$HERE/sftp.sh" get "$REMOTE_ROOT/$remote" "$local_file" \
             > "$LOG/$srt_name.refine-get.log" 2>&1; then
            echo "$(date +%H:%M:%S) FAIL  download $srt_name"
            rm -f "$local_file"; failed=$((failed + 1)); continue
        fi
        got=$(stat -c %s "$local_file" 2>/dev/null || echo 0)
        if [[ "$got" != "$size" ]]; then
            echo "$(date +%H:%M:%S) FAIL  $srt_name incomplete:" \
                 "$got of $size bytes"
            rm -f "$local_file"; failed=$((failed + 1)); continue
        fi
    fi

    echo "$(date +%H:%M:%S) refine $srt_name"
    if "$PY" -m scripts.news.refine_cues "$local_file" \
         "$KARI/cues/$srt_name.json" \
         > "$LOG/$srt_name.refine.log" 2>&1; then
        tail -n 1 "$LOG/$srt_name.refine.log" >> "$DELTA"
        done_count=$((done_count + 1))
        echo "$(date +%H:%M:%S) done  $srt_name" \
             "$(tail -n 1 "$LOG/$srt_name.refine.log")"
    else
        echo "$(date +%H:%M:%S) FAIL  refine $srt_name --" \
             "see $LOG/$srt_name.refine.log"
        failed=$((failed + 1))
    fi
    if [[ ! -f "$local_file.keep" ]]; then
        rm -f "$local_file"
    fi
done 3<<< "$jobs"

echo "$(date +%H:%M:%S) finished: $done_count refined, $failed failed"
echo "next: make_all + publish, then rebuild --verify (design D8)"
[[ "$failed" -eq 0 ]]
