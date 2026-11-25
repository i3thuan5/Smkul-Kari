"""族語新聞: every catalogue episode to a preview mp4 and a training WAV.

    python3 -m tools.mkv2mp4wav.news --dry-run
    python3 -m tools.mkv2mp4wav.news --limit 2
    python3 -m tools.mkv2mp4wav.news

Each source is found the way every other news step finds it
(`video_names.locate`): the published root /docker/news/mkv/<年-月>/,
then the staging root /home/news/mkv/<年-月>/, then the catalogue's
`原始影片檔案位置` -- moving on only when the server says "not found".
Not `audio.locate()`: that one prefers the local archive copy left by
cue cutting, which belongs to that step. The outputs go to
/home/news/{mp4,wav}/<年-月>/<成果檔名>, the month taken from the name.
"""
import sys

from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import paths
from scripts.news import video_names
from tools.sftpbatch import batch
from tools.mkv2mp4wav import cli

NAME = "news"
SOURCE = "Kari-SRT/news/smkul.csv"
DESCRIPTION = ("族語新聞目錄逐集：從 SFTP 下載影片，做字幕編輯預覽 mp4 "
               "與訓練用 WAV，各自驗收、上傳到 /home/news/")


def jobs(limit=0, table=None):
    """Every episode, sorted by srt_name, as Jobs.

    Row by row rather than `episodes.load()`: building an entry derives
    paths from the name, so one malformed name there would stop the whole
    catalogue loading. Here it becomes that one episode's failure.
    """
    found = episodes.rows(table)
    found.sort(key=lambda row: row["成果檔名"])
    if limit:
        found = found[:limit]
    out = []
    for row in found:
        name = row["成果檔名"]
        try:
            entry = episodes.entry_of(row, set())
            preview = paths.preview_path(name)
            wav = paths.wav_path(name)
        except PipelineError as problem:
            out.append(batch.Job(name or "（空的成果檔名）", None,
                                 error=str(problem)))
            continue
        out.append(batch.Job(name, preview, preview=preview, wav=wav,
                             entry=entry))
    return out


def locate(job, sftp, log):
    """Published root, then staging root, then the catalogue's location."""
    def say(text):
        # Falling back to the original location is worth seeing live, not
        # only in the log afterwards.
        print("  " + text, flush=True)
        log(text)

    found = video_names.locate(job.entry, sftp, say=say)
    return found.path, found.source


def listing(sftp, jobs):
    """Outputs already on the server: one ls per month folder per root."""
    months = set()
    for job in jobs:
        if not job.error:
            months.add(paths.month_of(job.label))
    out = set()
    for root in (paths.PREVIEW_ROOT, paths.WAV_ROOT):
        for month in sorted(months):
            folder = "%s/%s" % (root, month)
            found = sftp.scan(folder)
            if found is None:
                continue
            files = found[0]
            for name in files:
                if files[name] > 0:
                    out.add("%s/%s" % (folder, name))
    return out


def main(argv=None):
    return cli.main(sys.modules[__name__], argv)


if __name__ == "__main__":
    sys.exit(main())
