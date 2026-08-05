---
description: Process one month of 族語新聞 from SFTP into SRTs
argument-hint: 族語新聞/110.1-110.10/3月 [--limit N]
---

Process one month of 原視族語新聞 from the SFTP server into SRT subtitles.

Month to do: **$ARGUMENTS**

If no month was given, list what is on the server and ask which one:
`scripts/news/sftp.sh 'ls /docker/ilrdf-corpus/族語新聞/110.1-110.10'`

Read `scripts/news/README.md` first — it holds the measured numbers and the
traps. The short version of the procedure:

## 1. Fetch and cut

```bash
bash scripts/news/fetch_sftp.sh '<月份>'          # add --limit 2 for a dry run
```

This downloads one video at a time, checks its byte count against the
server's, verifies the subtitle band, cuts cues, and **deletes the video**
before moving on. Never hold more than one video locally.

Filling a gap rather than doing a month — a few named episodes scattered
through a folder — takes `--only`, an extended regex matched against the file
name, followed by `add_episodes.py` to name them in the inventory (the video
is gone by then, so `build_inventory.py` has nothing to scan):

```bash
bash scripts/news/fetch_sftp.sh '族語新聞/110.1-110.10/7月' \
     --only '^(21NL005_37晨間|21NL004_37晚間)族語新聞\.mp4$'
python3 -m scripts.news.add_episodes '族語新聞/110.1-110.10/7月/…mp4' …
```

Before committing to a whole month, run it with `--limit 2` and look at a
contact sheet (`kithann/out/mxf/<slug>.work/sheets/sheet_001.png`) to confirm
the strips show the dialogue line and nothing else.

## 2. 文稿 alignment, then gap sheets

```bash
python3 -m scripts.news.gap_sheets            # or --no-rtf for every cue
```

Only months with a matching 文稿 folder get script text; the rest is all gap.
`gap_sheets.py` refuses to touch a work dir that already holds verified
transcripts, so it is safe to re-run.

Pass `--no-rtf` to put every cue on the sheets even where a 文稿 exists.
Measured on February: 7.7% of the script's lines differ from the picture and
the picture is right every time, so those cues get re-read anyway — reading
them once here is cheaper than reading them twice.

## 3. Vision pass

```bash
python3 -m scripts.news.batches <slug> --size 24     # lists the sheet batches
```

Farm each batch to a subagent, 24 sheets each, writing a TSV straight to
`Kari-SRT/vision/<集>/bNN.tsv`. Two things the prompt must say, both learned
the hard way:

- **Cue numbers on a gap sheet JUMP.** The 文稿-covered cues are not on the
  sheets, so the reader must take the number printed in each strip's gutter
  and never assume the next strip is +1. Getting this wrong lands whole
  passages on the wrong subtitles and nothing reports an error.
- **Write the file once.** Blank cues lose their trailing tab and that is
  fine — `ingest.py` restores it. Agents that try to fix it themselves burn
  two to three times the tokens.

Then per episode:

```bash
python3 -m scripts.news.ingest <slug> Kari-SRT/vision/<集>
```

`ingest.py` refuses the whole batch if a TSV names a cue that was not on the
sheets that reader was given.

## 4. Assemble

```bash
python3 -m scripts.news.make_all       # writes SRTs + Kari-SRT/srt/smkul.csv
python3 -m scripts.news.publish        # cues/from_rtf/inventory -> Kari-SRT
python3 -m scripts.news.rebuild --verify   # prove the store rebuilds them
```

## Scale — say this out loud before starting

One month is about 71 episodes, ~154 GB of download, and roughly 3,000
contact sheets ≈ 125 subagents. That is about 3× the February batch. Tell the
user the estimate for the month they picked and get agreement before farming
out the vision pass; step 1 alone is cheap and can go ahead.
