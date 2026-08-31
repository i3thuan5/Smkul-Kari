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

## 1. Plan the month, then fetch and cut

```bash
python3 -m scripts.news.plan_month <月份> -n     # what it would do
python3 -m scripts.news.plan_month <月份>        # register, pending
bash    scripts/news/fetch_sftp.sh <月份>        # add --limit 2 for a dry run
```

`plan_month` picks each episode's source from the catalogue by rule (master
first, then the slot word in the file name, then same-name-two-folders) and
writes the month's episodes into the inventory as `pending`, each carrying
the path chosen for it. Registration has to come before the download: the
video is deleted the moment its cues are cut, so nothing downstream could
work out an episode's naming afterwards.

Episodes the rules cannot decide are **skipped and reported**, never guessed
— across the whole corpus that is 8 of 983, and none in 2021-01 or 2021-02.
Show the user the skip list; once they have decided, `add_episodes.py` takes
the chosen path. Episodes the catalogue marks as having no video are counted,
not listed — there is nothing to decide.

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
python3 -m scripts.news.batches <slug> --size 24     # lists the sheet batches
```

Farm each batch to a subagent, 24 sheets each, writing a TSV straight to
`Kari-SRT/news/1-ocr/3-vision/<年-月>/<srt_name>/bNN.tsv`. Two things the
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
python3 -m scripts.news.ingest <slug> Kari-SRT/news/1-ocr/3-vision/<年-月>/<srt_name>
```

`ingest.py` refuses the whole batch if a TSV names a cue that was not on the
sheets that reader was given.

## 4. Assemble

```bash
python3 -m scripts.news.make_all       # SRTs; progress table -> kithann/out/
python3 -m scripts.news.publish        # gate the batch, then cues + smkul.csv
python3 -m scripts.news.rebuild --verify   # prove the store rebuilds them
```

`publish` is all-or-nothing: it refuses while any episode registered by
`add_episodes` is still unread, and clears their `pending` flags only once
the whole batch is done. Until then the store keeps the previous batch's
`smkul.csv` and `rebuild --verify` stays green — which is what makes it safe
to keep running the verification while a batch is in progress.

## Scale — say this out loud before starting

Measured on the February batch (35 episodes, `1-ocr/1-cues/` and
`1-ocr/3-vision/` are the record): **835 cues, 178 contact sheets and 8.2
reading batches per episode**, and the vision pass ran at about **10 batches
an hour** (13 episodes ≈ 102 batches in a 10.5 h session). Fetch-and-cut costs
6.3 min per episode including the download; the speech side (`asrmt_batch`,
through `3-srt-raw`) costs 15 min per episode and can run alongside the vision
pass.

So a 71-episode month is roughly **154 GB of download, ~12,600 contact sheets
≈ 580 subagents, ~7.5 h of fetch-and-cut and ~58 h of vision**. Scale from the
per-episode figures above rather than from this paragraph — a short month or a
gap-fill batch is proportionally smaller. (An earlier version of this file said
3,000 sheets ≈ 125 subagents; that was written while cues supplied by the 文稿
were left off the sheets, and is about 4× too low now that every cue is read.)

The vision pass is the expensive part and it is farmed out to subagents, so it
is not something to start quietly: **tell the user the episode count, the sheet
and subagent count, and the rough hours for the month they picked, and wait for
them to agree before farming it out.** Steps 1 and 2 are cheap and can go ahead
without asking.
