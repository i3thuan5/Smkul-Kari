#!/usr/bin/env bash
# Turn a 50 Mbps MPEG-2 MXF master into an archival copy the subtitle
# pipeline can still be re-run against.
#
# This script does ONE thing: a single ffmpeg pass that writes the archive
# with **every** source audio track kept, and -- in that same pass -- an
# MD5 of each source audio track. It does not decide which tracks to keep
# and it does not verify anything. Both of those are the caller's job,
# using the .md5 files this leaves behind (scripts/transcode/audio_tracks.py
# answers them; archive_batch.py and tools/mxf2mkv/ both go through it).
#
# Why one pass. The old shape read the source three times: once to compare
# the two audio tracks, once to encode, once to verify the audio survived.
# On an SFTP mount that was merely slow; on the USB drive the mxf2mkv batch
# reads from, a 19 GB master became 57 GB of reading, and the two extra
# reads bought one bit of information ("are the tracks the same?"). ffmpeg
# takes several outputs off one input -- the source is decoded once and fed
# to the video encoder, the audio encoder and one md5 muxer per track -- so
# that bit now falls out of the encode for free. Hashing is cheaper than
# x264 by orders of magnitude; the cost is that the command line got long,
# which is what ENCODE_DRY_RUN and tests/transcode/test_encode_master.py
# are for.
#
# Why it no longer picks tracks. Deciding which of N tracks are duplicates
# is a nested loop over fingerprints. Bash can express it; bash cannot test
# it, and the failure mode is silent -- a track carrying different audio
# gets dropped and nothing says so. Measured 2026-09-06 across the 63
# archived episodes: 35 had one audio track, 28 had two that were NOT
# bit-identical. The old code also only ever mapped a:0 and a:1, so a third
# track would have vanished without a word.
#
# The encoding parameters and the reasoning behind them are unchanged; the
# numbers are in .claude/skills/video-subtitle-srt/壓縮率分析.md:
#
#   -crf 23           the whole CRF 18..28 range reproduced the delivered SRT
#                     text with zero character errors; 23 is the middle of it
#                     and lands an episode at 2.54 GB, 7.5x smaller than the
#                     19.0 GB master (measured end to end, not extrapolated).
#                     CRF 32 is where it breaks, and it breaks by *losing a
#                     subtitle*, so the headroom is the whole point.
#   -pix_fmt yuv420p  the source is 4:2:2, and keeping it was measured: at
#                     CRF 23 4:2:2 gave 11 spurious cues against 4:2:0's 17,
#                     but at CRF 28 it gave 17 against 16. The count wanders
#                     by about ±6 either way, so there is no chroma effect to
#                     buy -- and 4:2:2 costs 10-14% more every rung. Pass
#                     yuv422p as the 5th argument if the copy has to stand in
#                     for the master rather than just be re-processable.
#   1920x1080, 29.97  the band geometry in presets.json and the 9 px outline
#                     test are tuned for 1080p, and refine_cues.py re-reads
#                     at 25 fps. Scaling or dropping frames breaks one of
#                     those, and neither buys much: at a fixed CRF, 5 fps
#                     saved 21% and deinterlacing 9%.
#   -c:a flac         lossless, ~33% of PCM. The corpus exists to train
#                     acoustic models, so the audio must not be re-quantised.
#                     FLAC only holds integer PCM, though: a source that
#                     already decodes to float (AAC does, e.g. the mp4
#                     masters fetched later than the Feb mxf batch) would
#                     need a float->int rounding step to reach FLAC, and
#                     that step is a real, reproducible quantisation --
#                     caught by 2021-02-09 晚間 雅美 failing the caller's
#                     bit-exact check (fltp source, 25% of decoded PCM bytes
#                     differed). For that case the only lossless move is to
#                     not touch the audio at all: -c:a copy.
#
# The .md5 files are written through the same codec path the archive took,
# because that is what the caller has to compare against: for flac that
# means decoded PCM (what the corpus actually trains on); for copy it must
# mean the encoded packets, not decoded PCM -- Matroska doesn't carry AAC's
# skip_samples priming-delay side data the way mp4's edit list does, so
# decoding a stream-copied AAC track picks up an extra encoder-priming frame
# at the front and every sample after it reads as "different" even though
# the copied bytes are identical.
#
# Usage:
#   bash scripts/transcode/encode_master.sh SRC WORKDIR NAME [CRF] [PIX_FMT]
#
# Writes WORKDIR/NAME.all.mkv and WORKDIR/NAME.src-a<i>.md5 (one per track).
# ENCODE_DRY_RUN=1 prints the ffmpeg command that would run and exits, so
# the argument assembly is testable without ffmpeg or a real video.
set -euo pipefail

USAGE="usage: encode_master.sh SRC WORKDIR NAME [CRF] [PIX_FMT]"
SRC="${1:?$USAGE}"
WORKDIR="${2:?$USAGE}"
NAME="${3:?$USAGE}"
CRF="${4:-23}"
PIX="${5:-yuv420p}"

ARCHIVE="$WORKDIR/$NAME.all.mkv"
[[ -e "$ARCHIVE" ]] && { echo "refusing to overwrite $ARCHIVE" >&2; exit 1; }

tracks=$(ffprobe -v error -select_streams a -show_entries stream=index \
                 -of csv=p=0 "$SRC" | wc -l)
if [[ "$tracks" -lt 1 ]]; then
    echo "$SRC 無半條音軌，拒絕封存" >&2
    exit 1
fi

# FLAC is lossless only when the source is already integer PCM; see the
# -c:a note above for why anything else is stream-copied instead.
audio_codec=$(ffprobe -v error -select_streams a:0 \
                      -show_entries stream=codec_name \
                      -of csv=p=0 "$SRC")
case "$audio_codec" in
  pcm_*) audio_args=(-c:a flac -compression_level 8)
         md5_args=() ;;
  *)     audio_args=(-c:a copy)
         md5_args=(-c:a copy) ;;
esac

# Every source track is carried into the archive; nothing is dropped here.
maps=(-map 0:v:0)
for ((i = 0; i < tracks; i++)); do
    maps+=(-map "0:a:$i")
done

# One md5 output per track, each one its own ffmpeg output file. The -map
# belongs to the output that follows it, so track i's -map has to sit
# immediately before track i's md5 destination -- getting this order wrong
# fingerprints the wrong track, and a fingerprint attributed to the wrong
# track can read as "these two are duplicates" and drop one for real.
md5_outputs=()
for ((i = 0; i < tracks; i++)); do
    md5_outputs+=(-map "0:a:$i" "${md5_args[@]}" -f md5
                  "$WORKDIR/$NAME.src-a$i.md5")
done

# A batch of these runs for hours in the background; nice/ionice it down
# so it does not steal CPU/disk from whatever else is running on the box
# (使用者裁定 -- CPU 影響到其他工作).
cmd=(nice -n 15 ionice -c 3
     ffmpeg -v error -stats -i "$SRC" "${maps[@]}"
     -c:v libx264 -preset medium -pix_fmt "$PIX" -crf "$CRF"
     "${audio_args[@]}" "$ARCHIVE"
     "${md5_outputs[@]}")

if [[ -n "${ENCODE_DRY_RUN:-}" ]]; then
    printf '%s\n' "${cmd[*]}"
    exit 0
fi

"${cmd[@]}"

before=$(stat -c%s "$SRC")
after=$(stat -c%s "$ARCHIVE")
# awk, not bc: bc is not installed in the devcontainer, and a missing bc only
# showed up as a 0.0x ratio rather than as an error.
awk -v d="$ARCHIVE" -v b="$before" -v a="$after" 'BEGIN {
    printf "%s\n  %d bytes -> %d bytes  (%.1f%%, %.1fx smaller)\n",
           d, b, a, 100 * a / b, b / a
}'
echo "  音軌 $tracks 條，指紋佇 $WORKDIR/$NAME.src-a<i>.md5"
