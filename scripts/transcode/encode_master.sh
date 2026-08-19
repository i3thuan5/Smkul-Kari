#!/usr/bin/env bash
# Turn a 50 Mbps MPEG-2 MXF master into an archival copy the subtitle
# pipeline can still be re-run against.
#
# Measured on 2021-02-01 晚間 阿美 (19.0 GB, 48 min); the numbers and the
# reasoning are in .claude/skills/video-subtitle-srt/壓縮率分析.md.
# The short version of why the defaults are what they are:
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
#                     yuv422p as the 4th argument if the copy has to stand in
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
#                     caught by 2021-02-09 晚間 雅美 failing the bit-exact
#                     check below (fltp source, 25% of decoded PCM bytes
#                     differed). For that case the only lossless move is
#                     to not touch the audio at all: -c:a copy.
#   one audio track   the two PCM tracks on these masters are bit-identical
#                     (checked per file below, not assumed).
#
# Usage:
#   bash scripts/transcode/encode_master.sh SRC.mxf DST.mkv [CRF] [PIX_FMT]
set -euo pipefail

USAGE="usage: encode_master.sh SRC.mxf DST.mkv [CRF] [PIX_FMT]"
SRC="${1:?$USAGE}"
DST="${2:?$USAGE}"
CRF="${3:-23}"
PIX="${4:-yuv420p}"

[ -e "$DST" ] && { echo "refusing to overwrite $DST" >&2; exit 1; }

tracks=$(ffprobe -v error -select_streams a -show_entries stream=index \
                 -of csv=p=0 "$SRC" | wc -l)

# Drop the second audio track only when it is provably a duplicate. An
# episode where the two carry different mixes would lose one silently.
keep_second=1
if [ "$tracks" -eq 2 ]; then
  echo "checking whether the two audio tracks are identical ..."
  sums=$(ffmpeg -v error -i "$SRC" -map 0:a:0 -f md5 - -map 0:a:1 -f md5 - \
         | sort -u | wc -l)
  if [ "$sums" -eq 1 ]; then
    echo "  identical -- keeping one"
    keep_second=0
  else
    echo "  they differ -- keeping both"
  fi
fi

maps=(-map 0:v:0 -map 0:a:0)
if [ "$tracks" -ge 2 ] && [ "$keep_second" -eq 1 ]; then
  maps+=(-map 0:a:1)
fi

# FLAC is lossless only when the source is already integer PCM. A source
# that decodes to float (AAC, the codec on the mp4-sourced episodes) would
# be silently rounded on the way into FLAC's integer samples -- not
# audible, but not bit-exact, and this pipeline's whole audio contract is
# bit-exact. Stream-copy instead: zero re-encoding, so nothing to round.
audio_codec=$(ffprobe -v error -select_streams a:0 \
                      -show_entries stream=codec_name \
                      -of csv=p=0 "$SRC")
case "$audio_codec" in
  pcm_*) audio_args=(-c:a flac -compression_level 8) ;;
  *)     audio_args=(-c:a copy) ;;
esac

# A batch of these runs for hours in the background; nice/ionice it down
# so it does not steal CPU/disk from whatever else is running on the box
# (使用者裁定 -- CPU 影響到其他工作).
nice -n 15 ionice -c 3 \
ffmpeg -v error -stats -i "$SRC" "${maps[@]}" \
       -c:v libx264 -preset medium -pix_fmt "$PIX" -crf "$CRF" \
       "${audio_args[@]}" \
       "$DST"

before=$(stat -c%s "$SRC")
after=$(stat -c%s "$DST")
# awk, not bc: bc is not installed in the devcontainer, and a missing bc only
# showed up as a 0.0x ratio rather than as an error.
awk -v d="$DST" -v b="$before" -v a="$after" 'BEGIN {
    printf "%s\n  %d bytes -> %d bytes  (%.1f%%, %.1fx smaller)\n",
           d, b, a, 100 * a / b, b / a
}'

# The audio is the part that must survive bit-exact, so prove it did rather
# than trusting that -c:a flac (or copy) means what it says. Verify through
# the same codec path the encode took: for flac that means decoded PCM
# (what the corpus actually trains on); for copy it must mean the encoded
# packets, not decoded PCM -- Matroska doesn't carry AAC's skip_samples
# priming-delay side data the way mp4's edit list does, so decoding a
# stream-copied AAC track picks up an extra encoder-priming frame at the
# front and every sample after it reads as "different" even though the
# copied bytes are identical. "-c:a copy -f md5" hashes the passthrough
# packets pre-decode, sidestepping that entirely.
case "$audio_codec" in
  pcm_*) verify_args=() ;;              # decode both sides, compare PCM
  *)     verify_args=(-c:a copy) ;;     # compare the encoded packets
esac
a=$(ffmpeg -v error -i "$SRC" -map 0:a:0 "${verify_args[@]}" -f md5 -)
b=$(ffmpeg -v error -i "$DST" -map 0:a:0 "${verify_args[@]}" -f md5 -)
if [ "$a" = "$b" ]; then
  echo "  ok: $a"
else
  echo "  MISMATCH: source $a, archive $b" >&2
  exit 1
fi
