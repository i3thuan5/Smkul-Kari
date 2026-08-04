---
description: Process one month of 族語新聞 from SFTP into SRTs
argument-hint: 族語新聞/110.1-110.10/3月 [--limit N]
---

Process one month of 原視族語新聞 from the SFTP server into SRT subtitles.

Month to do: **$ARGUMENTS**

If no month was given, list what is on the server and ask which one:
`ilrdf-srt/sftp.sh 'ls /docker/ilrdf-corpus/族語新聞/110.1-110.10'`

Read `ilrdf-srt/README.md` first — it holds the measured numbers and the
traps. The short version of the procedure:

## 1. Fetch and cut

```bash
bash ilrdf-srt/fetch_sftp.sh '<月份>'          # add --limit 2 for a dry run
```

This downloads one video at a time, checks its byte count against the
server's, verifies the subtitle band, cuts cues, and **deletes the video**
before moving on. Never hold more than one video locally.

Before committing to a whole month, run it with `--limit 2` and look at a
contact sheet (`kithann/out/mxf/<slug>.work/sheets/sheet_001.png`) to confirm
the strips show the dialogue line and nothing else.

## 2. 文稿 alignment, then gap sheets

```bash
python3 ilrdf-srt/gap_sheets.py
```

Only months with a matching 文稿 folder get script text; the rest is all gap.
`gap_sheets.py` refuses to touch a work dir that already holds verified
transcripts, so it is safe to re-run.

## 3. Vision pass

```bash
python3 ilrdf-srt/batches.py <slug> --size 24     # lists the sheet batches
```

Farm each batch to a subagent, 24 sheets each, writing a TSV straight to
`ilrdf-srt/vision/<集>/bNN.tsv`. Two things the prompt must say, both learned
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
python3 ilrdf-srt/ingest.py <slug> ilrdf-srt/vision/<集>
```

`ingest.py` refuses the whole batch if a TSV names a cue that was not on the
sheets that reader was given.

## 4. Assemble

```bash
python3 ilrdf-srt/make_all.py       # writes SRTs + kithann/srt/smkul.csv
```

## Scale — say this out loud before starting

One month is about 71 episodes, ~154 GB of download, and roughly 3,000
contact sheets ≈ 125 subagents. That is about 3× the February batch. Tell the
user the estimate for the month they picked and get agreement before farming
out the vision pass; step 1 alone is cheap and can go ahead.
