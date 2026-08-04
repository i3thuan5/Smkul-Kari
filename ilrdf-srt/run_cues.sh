#!/usr/bin/env bash
# Stage each master to local disk, then segment it into cues.
#
# The corpus lives on /dev/sda1, an NTFS-over-FUSE volume that tops out at
# about 42 MB/s *in total*: measured 41 MB/s on one stream and 21+21 MB/s on
# two, so extra readers buy nothing and interleaving three of them cost a
# 3.5x slowdown (11.6 MB/s each). Reading all 380 GB therefore takes ~2.5 h
# whatever we do, and the only thing worth optimising is making that read
# sequential and hiding the decode behind it.
#
# Local disk writes at 822 MB/s, so each file is copied over once, decoded
# from the fast copy, then deleted. Copying is the bottleneck; up to three
# decodes run behind it, which keeps the CPU busy without touching the slow
# volume again.
#
# Work dirs are skipped if cues.json already exists, so this is safe to
# re-run after an interruption.
set -u

ROOT=/workspaces/Corpus-Cleanup
PY=$HOME/.venvs/subs2srt/bin/python
S=$ROOT/.claude/skills/video-subtitle-srt/scripts/subs2srt.py
WORK=$ROOT/kithann/out/mxf
LOG=$ROOT/kithann/out/mxf-logs
STAGE=${STAGE:-/tmp/claude-1000/-workspaces-Corpus-Cleanup/d46a0a27-17d9-4ffc-bdcb-dc0a0776dd05/scratchpad/stage}
DECODERS=${DECODERS:-3}

mkdir -p "$WORK" "$LOG" "$STAGE"

mapfile -t JOBS < <(python3 -c "
import json
for e in json.load(open('$ROOT/ilrdf-srt/inventory.json')):
    if not e['truncated']:
        print(e['slug'] + '\t' + e['video'])
")

echo "$(date +%H:%M:%S) ${#JOBS[@]} episodes to process"
for job in "${JOBS[@]}"; do
    slug=${job%%$'\t'*}
    video=${job#*$'\t'}
    if [ -f "$WORK/$slug.work/cues.json" ]; then
        echo "$(date +%H:%M:%S) skip  $slug (done)"
        continue
    fi

    # Bound both the number of decodes and the staged bytes on disk.
    while [ "$(jobs -rp | wc -l)" -ge "$DECODERS" ]; do wait -n; done

    # Keep the original basename: the preset is chosen by matching `NL00`
    # against the file name, so renaming the copy would silently drop the
    # verified band and fall back to autodetect, which on this material
    # locks onto the weather graphic instead of the dialogue.
    local_copy="$STAGE/$(basename "$video")"
    echo "$(date +%H:%M:%S) stage $slug"
    if ! cp "$video" "$local_copy"; then
        echo "$(date +%H:%M:%S) FAIL copy $slug"
        rm -f "$local_copy"
        continue
    fi

    (
        echo "$(date +%H:%M:%S) cues  $slug"
        "$PY" "$S" cues "$local_copy" -o "$WORK/$slug.work" --sheets \
            > "$LOG/$slug.cues.log" 2>&1
        rc=$?
        rm -f "$local_copy"
        if ! grep -q "using preset 'titv-news-mxf'" "$LOG/$slug.cues.log"; then
            echo "$(date +%H:%M:%S) WARN  $slug did not use the preset"
        fi
        if [ $rc -eq 0 ]; then
            "$PY" "$S" ocr "$WORK/$slug.work" --engine tesseract \
                > "$LOG/$slug.ocr.log" 2>&1
        fi
        echo "$(date +%H:%M:%S) done  $slug rc=$rc"
    ) &
done
wait
echo "$(date +%H:%M:%S) all episodes finished"
