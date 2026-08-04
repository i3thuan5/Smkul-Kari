---
name: video-subtitle-srt
description: Use when asked to pull burned-in (hardcoded) subtitles out of a video file and turn them into an .srt — e.g. Formosan-language broadcast recordings where the subtitle is painted into the picture and there is no soft subtitle track. Covers finding the subtitle band, cutting the video into timed cues by pixel differencing, reading the text with Claude vision off contact sheets (the default and the only output fit to ship), resuming a part-finished vision pass, keeping spelling consistent across batches via a glossary, and exporting checked text as tesstrain ground truth. An offline tesseract path exists but is only for when the caller asks for it by name, or when the video may not leave the machine. Triggers on requests like "kā字幕提出來", "做srt", "產生兩種 srt", "方案A 方案B 比較", "extract hardcoded subtitles", "影片字幕轉逐字稿".
---

# Extracting burned-in subtitles as SRT

## First: is it actually burned in?

Always check before doing any pixel work — a soft subtitle track is a
one-liner and needs none of this.

```bash
ffprobe -v error -show_entries stream=index,codec_type,codec_name \
        -of csv=p=0 video.mp4
# a codec_type=subtitle row means you can just do:
ffmpeg -i video.mp4 -map 0:s:0 out.srt
```

Both videos in `kithann/` were checked this way: video + audio + a timecode
data stream, no subtitle stream. So the subtitles are painted into the
picture and have to be read off the pixels.

## Recipe: video → SRT (Claude vision)

**Read the text with Claude vision unless told otherwise.** On this material
tesseract reaches 20.0% whole-line accuracy on Amis and 52.9% on Chinese;
vision was correct on every line spot-checked. Measurements and the reason
tesseract cannot be tuned past this are in "Recognition" below.

Timing comes from the `cues` pass and is independent of which recogniser you
use, so a tesseract run can still serve as a rough draft or a fallback — see
"When tesseract is the right call".

```bash
S=.claude/skills/video-subtitle-srt/scripts
V=path/to/video.mp4
W=out/myvideo.work

# 0. confirm the band before spending 5 minutes on a decode
python3 $S/subs2srt.py detect $V --preview /tmp/band.png   # eyeball, then add a preset

# 1. one cues pass -> strips/ + sheets/ + sheets.json   (~5 min per 50 min)
python3 $S/subs2srt.py cues $V -o $W

# 2. read the contact sheets with vision, batch by batch
python3 $S/subs2srt.py pending $W --limit 10           # which sheets are left
#   -> Read each named sheets/sheet_NNN.png, transcribe into a TSV:
#        12<TAB>ami<TAB>Nga'ay ho^
#        12<TAB>han<TAB>大家好
#        13<TAB>ami<TAB>              <- confirmed blank: leave the text empty
python3 $S/subs2srt.py import $W --from batch01.tsv

# 3. after the first batch or two, lock in the spellings already settled and
#    paste them into every later batch's prompt
python3 $S/subs2srt.py glossary $W --min-count 3

#    repeat pending -> read -> import until pending reports 0 remaining

# 4. assemble
python3 $S/subs2srt.py srt $W -o out/myvideo.srt
```

The vision pass is **resumable on purpose**. A 50-minute video is 160+
sheets, which does not fit in one sitting; `pending` diffs `sheets.json`
against `verified.json` and names the next batch, so the work survives being
stopped and picked up later. Import each batch as you go rather than hoarding
one huge TSV.

Note `srt` only emits cues whose text arrived via `import`, so a part-finished
pass yields a short but honest SRT — never tesseract guesses padding the gaps.

### When tesseract is the right call

`ocr --engine tesseract` fills `transcripts.json` without `import`, so it is
worth reaching for when:

- **The caller asks for it by name**, or wants the two compared.
- **The video must not leave the machine.** Vision sends the cue strips to
  Anthropic; tesseract is entirely local. For sensitive material this decides
  it regardless of accuracy.
- **You want a throwaway draft of the timings**, e.g. to sanity-check the
  detected band before committing to a full vision pass.

Do not ship its text as corpus data. To run both for comparison, point a
second work dir at the same strips so the timings stay identical:

```bash
mkdir -p out/myvideo.tess.work
cp $W/cues.json $W/sheets.json out/myvideo.tess.work/
ln -s ../myvideo.work/strips out/myvideo.tess.work/strips
python3 $S/subs2srt.py ocr out/myvideo.tess.work --engine tesseract
python3 $S/subs2srt.py srt out/myvideo.tess.work -o out/myvideo.tesseract.srt
```

### Farming the vision pass out to subagents

Reading 389 sheets does not fit in one context, but each subagent gets its
own, and the main session only takes back TSV text. Measured cost is about
**3,450 tokens per sheet** including prompt, reasoning and output — roughly
2.4× a naive pixels/750 estimate, so budget from the measured figure.

Twelve sheets per agent worked well. Two things to insist on in the prompt:

- Spell out the orthography. Told explicitly to preserve `^`, `'` and `:`,
  subagents reproduced `ina^ mama^ salikaka^ nga'ay ho^`, `mido^do^` and
  `Po:long` correctly — the exact marks tesseract never emits.
- Tell them to transcribe adjacent duplicate cues verbatim rather than
  deduplicating. `merge_repeats` handles that later with the timings in hand.

**Always verify the cue↔sheet mapping before importing.** Compare the cue
numbers a subagent returned against `sheets.json` for the sheets it was
given; a mismatch means the text would land on the wrong subtitles, which is
silent and far worse than a misread character.

Measured agreement against my own hand reads: 32/32 on Chinese-only sheets,
31/32 on bilingual sheets. The single disagreement was an occluded frame —
now fixed upstream by the median composite rather than by voting.

### One agent per video does not fit

The obvious way to keep spelling consistent — hand the whole video to a
single subagent — does not work. A subagent's context is bounded like any
other, and images stay in it once read. Measured at ~2,830 tokens per sheet:

| video | sheets | needs | context ceiling |
|---|---|---|---|
| bilingual (A) | 160 | ~450k tokens | ~200k |
| news (B) | 249 | ~705k tokens | ~200k |

Batching is a hard constraint, not a preference. Twelve sheets per batch is
the compromise: large enough that a batch is internally consistent, small
enough to fit comfortably.

### Keeping spelling consistent across batches

Each subagent sees only its own dozen sheets, so it cannot know how an
earlier batch spelled a programme name or a mark-carrying word. On the last
batch of video A this bit us: the programme name `'a"iyalaeho:` came back
with a single quote, disagreeing with four earlier occurrences.

Tell later batches what has already been decided:

```bash
python3 $S/subs2srt.py glossary WORK --line ami --min-count 3
# 既定寫法（出現 >= 3 次）-- 貼進後續批次的 prompt
#   niyaro'   (66 次)
#   ho^       (43 次)
#   Angcoh    (46 次)
```

It collects exactly the words batches disagree about — those carrying
`^ ' " :` and capitalised proper nouns — ranked by frequency. Paste the list
into the prompt of subsequent batches. Run it after the first batch or two,
and refresh it as coverage grows.

**Keep the after-the-fact sweep as well.** A glossary only covers words that
have already appeared; a proper noun first seen in two different batches can
still diverge. The two are complementary: the glossary *prevents* drift on
known words at near-zero cost, the global scan *detects* drift on new ones.
After importing everything, grep the transcripts for `"`, `^` and `□` and
eyeball every hit — on these two videos that surfaced 11 double quotes, all
legitimate once checked, plus the one real inconsistency above.

When comparing a vision SRT against a tesseract one, restrict both to the
cues actually read — otherwise an unfinished vision pass merely looks worse.

## The shape of the problem

Timing and recognition are *separate* problems and should be solved
separately. Deciding when a subtitle starts and stops, and deciding which
frames show the same subtitle, are pixel problems — deterministic, testable,
and cheap. Only the last step needs a recogniser. Doing it in one pass (OCR
every frame, dedupe the strings afterwards) is far slower and produces worse
timings, because OCR noise makes two frames of the *same* subtitle look
different.

So: `scripts/subs2srt.py` cuts the video into cues by differencing the text
mask, exports one image strip per cue, and only then recognises text.

```bash
python3 scripts/subs2srt.py detect VIDEO --preview /tmp/band.png
python3 scripts/subs2srt.py cues   VIDEO -o work/
python3 scripts/subs2srt.py ocr    work/ --engine tesseract
python3 scripts/subs2srt.py srt    work/ -o out.srt
# or all at once:
python3 scripts/subs2srt.py auto   VIDEO -o out.srt
```

Decode runs at roughly 11× realtime, so a 50-minute 1080p video takes about
5 minutes per pass.

## Installing the dependencies

Verified on **Ubuntu 24.04.4 LTS / Python 3.12.3** (this devcontainer).

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg tesseract-ocr tesseract-ocr-chi-tra python3-venv

python3 -m venv ~/.venvs/subs2srt
~/.venvs/subs2srt/bin/pip install numpy Pillow
~/.venvs/subs2srt/bin/python scripts/subs2srt.py --help
```

**A venv is not optional here.** Ubuntu 24.04 ships PEP 668, so a plain
`pip install numpy` fails outright:

```
error: externally-managed-environment
× This environment is externally managed
```

`--break-system-packages` would also work but puts these into the system
Python; a venv keeps the OCR toolchain isolated from anything else on the box.

### What each piece is for

| 套件 | 版本（實測） | 用途 | 少了會怎樣 |
|---|---|---|---|
| `ffmpeg` | 7:6.1.1-3ubuntu5 | 解碼、`crop`／`fps` 濾鏡；附帶 `ffprobe` 用來檢查有無 soft subtitle | 完全不能跑 |
| `numpy` | 2.5.1 | 文字遮罩、Jaccard 距離、中位數合成 | 完全不能跑 |
| `Pillow` | 12.3.0 | 讀寫 PNG 圖條、contact sheet 排版 | 完全不能跑 |
| `tesseract-ocr` | 5.3.4-1build5 | 方案 A 的辨識器 | `ocr --engine tesseract` 失敗 |
| `tesseract-ocr-chi-tra` | 1:4.1.0-2 | 繁體中文語言包 | 中文行讀不出來 |
| `python3-venv` | 3.12.3 | 建立 venv（見上） | 無法安裝 numpy／Pillow |
| `fonts-dejavu-core` | Ubuntu 預裝 | contact sheet 左欄的編號與時間戳 | 退回 Pillow 內建點陣字，很小但仍可讀 |

`tesseract --list-langs` 應列出 `chi_tra eng osd`。方案 A 的阿美語行用 `eng`
（沒有阿美語模型，這正是它整行正確率只有 20% 的根本原因）。

### 選用

```bash
# 只有 selftest 的合成影片需要（要在畫面上燒中文字幕）
sudo apt-get install -y fonts-noto-cjk

# 只有 ocr --engine claude-api 需要
~/.venvs/subs2srt/bin/pip install anthropic   # 另需 ANTHROPIC_API_KEY

# 只有要跑 lint 時需要
~/.venvs/subs2srt/bin/pip install flake8
```

`selftest.py` 的端對端測試還依賴 ffmpeg 內建的 **libass**（`subtitles` 濾鏡）
與 **libx264** 編碼器。Ubuntu 的 `ffmpeg` 套件兩者都有，用
`ffmpeg -filters | grep subtitles` 與 `ffmpeg -encoders | grep libx264` 可確認。

### 不需要的東西

沒有用到 OpenCV、PyTorch、pytesseract 或任何 OCR 包裝套件 —— tesseract 是以
`subprocess.run()` 傳 list 直接呼叫 CLI（不經 shell，見採購合規說明關於
`CVE-2026-26832` 的說明）。第三方 import 就只有 `numpy` 與 `PIL` 兩個。

## Finding the band

`detect` proposes a band and prints ranked candidates. **It is a proposal,
not an answer** — always confirm with `--preview`, which stacks six sampled
crops with the detected line edges drawn on. Two things reliably fool it:

- A news lower-third or station graphic is also stable white-on-dark text.
  On the TITV news video, detection ranks the graphics band *above* the real
  dialogue subtitle.
- Detection picks a single band, so on a bilingual video it returns whichever
  of the two lines carries more ink, not both.

Once confirmed, record the region in `scripts/presets.json` keyed by a
substring of the file name; `cues` then picks it up automatically. That file
already holds verified entries for the two videos in `kithann/`.

## The text mask

Subtitle glyphs are near-white and carry a dark outline. Two knobs:

- `outline: false` — plain white-pixel test. Correct when the subtitle sits
  on an opaque coloured band (video A's yellow bar), because the band itself
  is saturated and never reads as white. Cheaper and cleaner.
- `outline: true` — additionally demand a dark pixel within ~9px. Required
  when glyphs sit straight on the footage (video B). This is what rejects
  sky, white shirts and pale walls; it cut the mask noise on video B by 3–4×.

Counter-intuitively, **raising `white_min` makes things worse**. Measured on
a 5-minute slice of video B: `white_min` 185 → 94 cues, 210 → 99, 225 → 144.
A tighter threshold thins the glyph mask until compression noise dominates
the frame-to-frame difference, and cues shatter. Leave it near 185.

### Titles and credit rolls

Opening titles and a closing credit roll are white text in the same part of
the frame, and they read as perfectly plausible cues — the first run on video
A produced twelve of them at the two ends of the file, full of convincing
nonsense. When the subtitles ride on a coloured band, the band's *absence* is
the honest signal that nothing is being said:

```json
"band_probe": {"x": 0, "w": 60, "min_saturation": 60}
```

That names a slice of the region which is always backdrop and never glyph
(video A's text never reaches the left edge). Measured mean channel spread
there is ~125 while the band is up and 11–26 once it goes, so one threshold
separates them cleanly; frames that fail the probe are treated as blank.
Only useful for band-style subtitles — video B has no band to test.

## The exported strip is a median composite, not one frame

Each cue keeps up to 24 of its sampled frames and exports the **per-pixel
median**. A subtitle is frozen for its whole cue; anything passing in front
of it is not. The median therefore erases occluders and leaves the glyphs.

This matters more than it sounds. Video A's cue 10 has a dark motion-blurred
shape drifting across the band:

```
single "best" frame :  ...Angcoh mam▓▓▓▓ak kami...     unreadable
median composite    :  ...Angcoh malipahak kami...     obvious
```

No choice of *single* frame reliably fixes this, because any one frame may be
the occluded one. Picking "the frame with the most ink" (the old behaviour)
does not help either — an occluder can raise the ink count.

**Do not try to solve occlusion by adding more readers.** Two agents reading
the same obscured frame produce correlated guesses, not independent evidence;
a plausible-but-wrong word can pass as consensus. Fix the input instead. The
composite costs nothing at read time and removes the ambiguity outright.

A useful side effect: where the composite differs strongly from a single
frame, something was passing in front of the text. That is a cheap,
model-free occlusion detector if a confidence signal is ever needed.

## Cue segmentation

A new cue opens when the Jaccard distance between the current frame's mask
and the open cue's mask exceeds `--change` (default 0.35), and only after the
change repeats `--min-stable` times (default 2). That hysteresis is what
stops a cross-fade or one noisy frame from spawning a phantom cue.

Prefer over-splitting to under-splitting: a split cue is repaired losslessly
later, a merged one has lost text. `srt` therefore fuses neighbouring cues
whose recognised text is *identical* (`--merge-repeats`, on by default) —
that fixes video B, where moving footage behind a motionless subtitle splits
it repeatedly.

### Known limitation

Two different subtitles showing identical text back-to-back with no blank
frame between them are indistinguishable from one long subtitle, and will be
emitted as one cue. This is inherent to pixel differencing, and is pinned by
a test so it cannot regress silently.

## Recognition: why vision is the default

Measured against a hand-read ground truth off the contact sheets (15 Amis
rows, 17 Chinese rows, sampled from the start, middle and end of video A):

| line | tesseract char | tesseract **whole-line** | Claude vision |
|---|---|---|---|
| Chinese on a clean band | 79.4% | **52.9%** | correct on every line checked |
| Chinese over footage (video B) | not scored | clearly worse | correct on every line checked |
| Amis (Latin) | 75.6% | **20.0%** | correct on every line checked |

**Score whole lines, not characters.** One wrong character makes a subtitle
line unusable, so 75–79% per character still means only a fifth to a half of
lines are shippable. Character accuracy hides the problem.

Accuracy also decides whether the *downstream* steps work at all. On video B
the vision pass let `merge_repeats` fuse 296 duplicate cues (878 → 657); the
tesseract run merged almost none, because its two readings of the same
sentence carried different errors and so never compared equal. On video A it
correctly left the Chinese-interview stretches' Amis rows empty, where
tesseract emitted noise into blank strips.

The tuning notes below are kept for the tesseract fallback. They do not
change the conclusion — the ceiling is the model, not the settings.

Do not upscale binarised strips much — see `prep_for_tesseract`, where the
measurements live. The original `scale=3` was a guess and was among the worst
options; fixing it to 2x for Latin and 1x for Chinese tripled Amis whole-line
accuracy (6.7% → 20.0%) and lifted Chinese from 41.2% to 52.9%, for free.
psm 6 is identical to psm 7, psm 13 is far worse, the dictionary flags make no
difference, and keeping anti-aliased grey instead of binarising is worse.

### The ceiling is the model, not the settings

Amis orthography uses `^` (`ina^ mama^ salikaka^`). Across four sentences
holding **12 instances of `^`, tesseract recognised zero** — even with `^`
present in `tessedit_char_whitelist`:

```
truth : caay ka tangasa^ itira i ka^ko^ matoka^ maraay tato
tess  : caay ka tangasa itira ikaSko maitokai maraay tato
```

The `eng` LSTM was never trained on `^` appearing inside a word, so it has no
model of that shape in a text stream. A whitelist can only restrict what the
model may emit; it cannot teach it a glyph it never learned. Same root cause
for `'` read as `l`/`r`/`i`, `:` read as `i`, and single-storey `g` read as
`a` — all glyph/model mismatches, none of them tunable.

So tuning tops out around 36% whole-line. Getting past that needs a different
recogniser (Claude vision) or a model trained on this material (tesstrain).

**For a language corpus, do not ship tesseract's Amis.** A corrupted corpus
is worse than a smaller one — the same rule as `book-cover-ocr`'s "never
fabricate missing fields".

### Reading the strips with Claude vision (no API key)

`cues` also writes **contact sheets** to `work/sheets/` — cue strips tiled
with their index in a gutter, packed to ~1.1 megapixels each so a vision
model reads them without downscaling. Roughly 4 bilingual cues fit per sheet.
`Read` a sheet, then type what you see into a TSV:

```
# index <TAB> line-name <TAB> text
1	ami	Ati han ako ko singsi^ niyam ci Kinci ko somowalay
1	han	我就請我們的老師來說明這部分
2	ami	Hay nga'ay ho^
```

```bash
python3 scripts/subs2srt.py import work/ --from vision.tsv
python3 scripts/subs2srt.py srt    work/ -o out.srt
```

`import` merges over whatever is already in `transcripts.json` and refuses
the whole file if any cue index or line name is unknown, so a mistyped
number fails loudly instead of silently landing on the wrong subtitle.

**The hybrid worth defaulting to:** run `ocr --engine tesseract` first, keep
its Chinese, and re-read only the Amis line from the sheets. That halves the
vision work on a bilingual video and costs nothing in Chinese accuracy.

With an `ANTHROPIC_API_KEY`, `ocr --engine claude-api` does the same
per-strip automatically (`pip install anthropic`).

## Building a training set (tesstrain)

The cue strips are already what tesstrain wants — single text lines about
60px tall — so a fine-tuning set is mostly a matter of pairing each strip
with checked text:

```bash
python3 scripts/subs2srt.py export-gt work/ -o gt/ --line ami
# gt/sub_00042_ami.png  +  gt/sub_00042_ami.gt.txt
```

**Only `import`ed rows are exported.** `import` marks what it writes in
`work/verified.json`, and `export-gt` trusts nothing else. This is not
bureaucracy: the first run of this command happily emitted

```
finawlan ina mama salikakai nga'ay ho      <- tesseract's own error
finawlan ina^ mama^ salikaka^ nga'ay ho^   <- what the frame says
```

Feeding a recogniser's output back as its training target teaches it to
repeat the mistake, and the error is self-reinforcing — a model that misses
`^` gets trained to be *more* sure there is no `^`. `--include-unverified`
exists but says so loudly.

tesstrain rejects an empty `.gt.txt`, so blank rows are skipped. Practical
floor for a fine-tune is 50–100 lines (it checkpoints every 100 iterations).

### Cue numbers are not stable identifiers

A cue index means something only for one particular `cues.json`. Re-running
`cues` with any different setting renumbers everything, and a TSV keyed on
stale numbers lands each transcription on the wrong subtitle **silently** —
worse than an OCR error, because image and label are then systematically
mispaired. This bit me during development: an 8-row TSV read against a
676-cue run was imported into a 637-cue run and every row was wrong.

Contact sheets therefore print the cue's timestamp under its number. Check
the clock, not just the index, and re-read the sheets after re-running `cues`.

## Verifying changes

`scripts/selftest.py` is the guard. It burns a known SRT into a synthetic
1080p clip over moving content — once bare, once with a coloured band — runs
the real pipeline, and diffs recovered cues against ground truth.

```bash
python3 scripts/selftest.py            # unit tests + round trip
python3 scripts/selftest.py --quick    # unit tests only, no encode
```

Current state: 51 unit tests, and both round trips recover 7/7 cues with no
spurious or missed cues and worst-case start error 0.100s at 5fps sampling.

Timing bias is systematic and small: a cue can only be detected on a sample
boundary, so starts land within one sample interval (0.2s at the default
5fps) *after* the true start. Mean observed error is +0.029s.

## The bug worth knowing about

`ffmpeg`'s `crop` filter runs in the decoder's pixel format, and for yuv420p
that **silently rounds width and height down to even**. Ask for a 107px-tall
crop and you get 106px, with no warning. A reader consuming `w*h*3` bytes per
frame then slips one row per frame, so every frame is a torn blend of two and
a motionless subtitle appears to crawl up the screen — which shows up as
plausible-looking but completely wrong cue boundaries, not as a crash.

`cuelib.normalize_region()` snaps every crop to even bounds, and
`stream_region()` raises if any bytes are left over at end of stream. Route
new crops through both; do not hand-build a crop chain.
