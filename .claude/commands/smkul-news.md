---
description: Process one month of 族語新聞 from SFTP into SRTs
argument-hint: 2021-03 [--limit N]
---

Process one month of 原視族語新聞 from the SFTP server into SRT subtitles.

Month to do: **$ARGUMENTS**

The month is a **broadcast month** (`2021-03`), not a source folder. They
are not the same thing: six broadcast months are spread across two folders
each, and `110.1-110.10/7月/` holds 140 files of which 66 are February's
programmes. If no month was given, ask which one.

Read `scripts/news/README.md` first — it holds the measured numbers and the
traps. The short version of the procedure:

**Three stages, and they cost different things.** Say which one you are in;
it is how anyone reading along knows what the machine is busy with and how
long it should take.

| Stage | Entry point | Resource | Per episode |
|---|---|---|---|
| **1. cues** | `fetch_sftp.sh` (download → verify band → cut → refine) | local CPU + network | ~5 min download, **~2 min cut**, 8.5 min refine |
| **2. OCR** | vision subagents → `ingest` → `make_all` → `publish` | **Claude vision** (the ingest and assembly around it are seconds of CPU) | **~50 min** |
| **3. asr** | `asrmt_batch` (audio → vosk → project → render) | local CPU | ~15 min |
| **4. quality** | `asrmt_run --step mt` then `judge` → sonnet subagents → `ingest` → `--second` → fable subagents → `ingest` → `quality` | ai-labs service (free, single concurrency) then **Claude judging** | ~15 min translation, ~8 judging batches |

Stage 2 is where the month goes: 71 episodes ≈ **58 hours of vision**,
against ~7.5 hours for all of stage 1. Stage 3 can run alongside stage 2.
Archival mkv encoding (`transcode/archive_batch.py`) is a side line and is
not on the delivery path.

## 1. Plan the month, then fetch and cut

```bash
python3 -m scripts.news.plan_month <月份> -n     # what it would do
python3 -m scripts.news.plan_month <月份>        # 唯讀，列出這個月有哪幾集
bash    scripts/news/fetch_sftp.sh <月份>        # add --limit 2 for a dry run
```

`plan_month` picks each episode's source from `news/smkul.csv` by rule
(master first, then the slot word in the file name, then
same-name-two-folders) and prints the month's episodes with the path chosen
for each. **It is read-only** — the節目目錄 covers every episode from day
one, so there is no registration step and nothing is written.

Episodes the rules cannot decide are **skipped and reported**, never guessed
— across the whole corpus that is 8 of 983, and none in 2021-01 or 2021-02.
Show the user the skip list. Episodes with no video are not in the table at
all (983 → 969), so there is nothing to decide about them.

This downloads one video at a time, checks its byte count against the
server's, verifies the subtitle band, cuts cues, refines the cue
boundaries to ≤0.05s while the video is still on disk, and **deletes the
video** before moving on. Never hold more than one video locally.

Filling a gap rather than doing a month — a few named episodes — takes
`--only`, an extended regex matched against the file name, or
`add_episodes.py` with the paths spelled out (that is also how a skipped
episode gets done once someone has judged it):

```bash
bash scripts/news/fetch_sftp.sh 2021-02 \
     --only '^(21NL005_37晨間|21NL004_37晚間)族語新聞\.mp4$'
python3 -m scripts.news.add_episodes '族語新聞/110.1-110.10/7月/…mp4' …
```

Before committing to a whole month, run the fetch with `--limit 2` and look
at a contact sheet (`kithann/out/mxf/<slug>.work/sheets/sheet_001.png`) to
confirm the strips show the dialogue line and nothing else. A month can span
folders, and layout follows the folder, so the band is verified once per
folder, not once per month.

The band check now measures both axes off the same decode. Rows as before:
the dialogue plateau must sit inside the region and the red lower-third's
edge must not. Columns are new: news subtitles are flush right (measured
over 27 episodes, the ink's right edge sits at x=1735-1737 against a
standard deviation of 460-470 for the left edge), and cutting compares only
the columns the text occupies, so the check refuses a folder whose text no
longer lands inside that window. It prints the measured right edge whether
it passes or fails -- a guard that only speaks up when it fails is one
nobody can check.

## 2. Contact sheets

```bash
python3 -m scripts.news.gap_sheets
```

Every cue goes on a sheet. There was once a filter that left off the cues an
episode's 文稿 could supply; measuring it settled the question the other way
(7.7% of the script's lines differ from the picture, and the picture is right
every time), so those cues had to be read anyway. The 文稿 path is gone —
see `scripts/news/README.md` for the comparison and which commit still has
the code.

`gap_sheets.py` refuses to touch a work dir that already holds verified
transcripts, so it is safe to re-run.

## 3. Vision pass

```bash
python3 -m scripts.news.batches <slug>               # lists the sheet batches
```

Farm each batch to a subagent, 4 sheets each, writing a TSV straight to
`Kari-SRT/news/1-ocr/2-vision/<年-月>/<srt_name>/bNN.tsv`. Two things the
prompt must say, both learned the hard way:

- **Cue numbers can JUMP.** When only part of an episode is being re-read the
  sheets carry a discontinuous set, so the reader must take the number printed
  in each strip's gutter and never assume the next strip is +1. Getting this
  wrong lands whole passages on the wrong subtitles and nothing reports an
  error.
- **Write the file once.** Blank cues lose their trailing tab and that is
  fine — `ingest.py` restores it. Agents that try to fix it themselves burn
  two to three times the tokens.

Then per episode:

```bash
python3 -m scripts.news.ingest <slug> Kari-SRT/news/1-ocr/2-vision/<年-月>/<srt_name>
```

`ingest.py` refuses the whole batch if a TSV names a cue that was not on the
sheets that reader was given.

## 4. Assemble

```bash
python3 -m scripts.news.make_all       # SRTs straight into 1-ocr/3-srt/
python3 -m scripts.news.publish        # the refined timeline into 1-ocr/1-cues/
python3 -m scripts.news.rebuild --verify   # prove the store rebuilds them
```

**每個階段做完就各自入庫。** `2-vision/` 由 Claude Vision 那端直接寫進
Kari-SRT、`3-srt/` 由 `make_all` 直接寫，只有 `1-cues/` 走 `publish`——
而且它**不再等視覺辨識讀完**。時間軸切好精修好就入庫，不必等那幾十
小時的閱讀：那幾十小時的成果放在 gitignore 的工作區，連一份備份都沒有。

`publish` 只擋兩件事：沒有時間軸、時間軸還沒精修。`1-ocr/1-cues/` 能直接
宣告「裡面每一份都是精修過的」，那只有把門看住才成立。「找不到時間軸」
和「還沒精修」是兩個不同的訊息，因為補救不同（重切，或跑 `refine_cues`）。

內容一致就不覆寫：比的是正規化之後的字串，不是工作目錄檔案的原始位元組
——工作目錄那份 JSON 的鍵是插入順序，比原始檔會每次都判成不同（曾經一次
publish 重寫了 74 個內容根本沒變的已交付檔）。

`publish` **不再寫 `smkul.csv`**：那是節目目錄，人維護的輸入。

**The speech side must rebuild byte for byte.** `rebuild --verify` does not
read the speech side's delivered files to trust them; it produces each one
again from the store — `2-srt-raw` from `1-words` plus the picture side's
timeline, `3-srt-ai` from `2-srt-raw` plus `mt-cache/`, `4-srt-quality` from
`3-srt-ai` plus `quality-cache/` — and compares the bytes. A difference is an
error to fix, not a warning. The fix costs nothing but CPU, no recognition and
no model call:

```bash
python3 -m scripts.news.asrmt_run <srt_name> --step raw
```

An episode that has **not got that far** is fine and draws no warning: the
speech side runs at its own pace, and how far it has got is answered by the
stage folders (`/news-stage-count`). A file the store cannot rebuild is a different matter — it means a
translation or a grade was written straight into the deliverable, or a cache
entry has since been removed.

## 4. Quality grading (after the speech side)

```bash
python3 -m scripts.news.asrmt_run <srt_name> --step mt        # ai-labs, ~15 min
python3 -m scripts.news.asrmt_run <srt_name> --step judge     # writes sNN.tsv
#   → one subagent per batch, model: sonnet, writes sNN.reply.tsv
python3 -m scripts.news.asrmt_run <srt_name> --step ingest
python3 -m scripts.news.asrmt_run <srt_name> --step judge --second   # fNN.tsv
#   → one subagent per batch, model: fable, writes fNN.reply.tsv
python3 -m scripts.news.asrmt_run <srt_name> --step ingest --second
python3 -m scripts.news.asrmt_run <srt_name> --step quality
```

The batch and reply files live in `kithann/out/asrmt/<srt_name>/quality/`.
Each subagent reads `scripts/asrmt/judge_prompt.md` (the grade definitions
**and** the prompt) plus its own batch file, and writes one reply file:
`id<TAB>高|中|低`, one line per request line, same ids, no extras. A reply
whose id set does not match, or that carries any other label, is rejected
whole — rerun that batch, the accepted ones are already cached.

The second pass only asks about what the first judge graded 高. High needs
both judges to agree; there is nobody who reads these languages available to
calibrate, so that agreement is what the precision of 高 rests on, and the
store's README says so out loud.

## Scale — say this out loud before starting

Measured on the February batch (35 episodes, `1-ocr/1-cues/` and
`1-ocr/2-vision/` are the record): **835 cues, 178 contact sheets and 8.2
reading batches per episode**, and the vision pass ran at about **10 batches
an hour** (13 episodes ≈ 102 batches in a 10.5 h session).

> **2026-09-09**: the sheet count above was measured when a sheet held 4 cues.
> Sheets now hold about 25, so an episode packs into roughly 33 of them rather
> than 178. **The batch and hour figures survive**: a batch was 24 sheets x 4
> cues and is now 4 sheets x ~25 cues, so it is the same ~100 cues of work,
> just delivered in 4 images instead of 24 — which is where the saving comes
> from. Cue counts per episode are unchanged. Take the live numbers from
> `sheets.json`, not from this paragraph. Fetch-and-cut costs
6.3 min per episode including the download; the speech side (`asrmt_batch`,
through `2-srt-raw`) costs 15 min per episode and can run alongside the vision
pass.

So a 71-episode month is roughly **154 GB of download, ~12,600 contact sheets
≈ 580 subagents, ~7.5 h of fetch-and-cut and ~58 h of vision**. Scale from the
per-episode figures above rather than from this paragraph — a short month or a
gap-fill batch is proportionally smaller. (An earlier version of this file said
3,000 sheets ≈ 125 subagents; that was written while cues supplied by the 文稿
were left off the sheets, and is about 4× too low now that every cue is read.)

The vision pass is the expensive part and it is farmed out to subagents. **The
user has standing authorisation for this (2026-08-30): plan it, say the numbers,
and start — do not wait for agreement.** Still say the episode count, the sheet
and subagent count and the rough hours, so the size is on the record; then go.
