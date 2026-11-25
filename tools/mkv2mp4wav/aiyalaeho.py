"""《開會了》: every catalogue episode to a preview mp4 and a training WAV.

    python3 -m tools.mkv2mp4wav.aiyalaeho --dry-run
    python3 -m tools.mkv2mp4wav.aiyalaeho --limit 2
    python3 -m tools.mkv2mp4wav.aiyalaeho

Both catalogue tables: smkul.csv and smkul-字幕版型異常.csv (使用者裁定
2026-11-23 -- the abnormal ones have no bilingual subtitles, which is
exactly what the preview is for in the subtitle editor). Each source is
the one place `原始影片檔案位置` names (mkv or mp4); the outputs go to
/home/aiyalaeho/{mp4,wav}/<成果檔名>, no sub-folders.
"""
import sys

from scripts.aiyalaeho import episodes
from scripts.aiyalaeho import paths
from scripts.errors import PipelineError
from tools.sftpbatch import batch
from tools.mkv2mp4wav import cli

NAME = "aiyalaeho"
SOURCE = "Kari-SRT/aiyalaeho/smkul.csv、smkul-字幕版型異常.csv"
DESCRIPTION = ("《開會了》目錄逐集：從 SFTP 下載影片，做字幕編輯預覽 mp4 "
               "與訓練用 WAV，各自驗收、上傳到 /home/aiyalaeho/")
WHERE = "原始影片檔案位置"


def jobs(limit=0, table=None, abnormal_table=None):
    """Every episode of both tables, sorted by srt_name, as Jobs."""
    # srt_dir=() : whether an SRT has been delivered does not matter here,
    # and passing it keeps this from reading the store's SRT folder.
    found = episodes.load(table, abnormal_table, srt_dir=())
    if limit:
        found = found[:limit]
    out = []
    for entry in found:
        name = entry["srt_name"]
        try:
            preview = paths.preview_path(name)
            wav = paths.wav_path(name)
        except PipelineError as problem:
            out.append(batch.Job(name or "（空的成果檔名）", None,
                                 error=str(problem)))
            continue
        video = "/" + entry["video"].strip().lstrip("/")
        out.append(batch.Job(name, preview, preview=preview, wav=wav,
                             video=video))
    return out


def locate(job, sftp, log):
    """The single place the catalogue names; not there is a failure."""
    if sftp.stat(job.video) is None:
        raise PipelineError("%s：伺服器上找不到來源影片 %s" % (job.label, job.video))
    return job.video, WHERE


def listing(sftp, jobs):
    """Outputs already on the server: one ls of each of the two folders."""
    out = set()
    for root in (paths.PREVIEW_ROOT, paths.WAV_ROOT):
        found = sftp.scan(root)
        if found is None:
            continue
        files = found[0]
        for name in files:
            if files[name] > 0:
                out.add("%s/%s" % (root, name))
    return out


def main(argv=None):
    return cli.main(sys.modules[__name__], argv)


if __name__ == "__main__":
    sys.exit(main())
