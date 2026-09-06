"""One master: encode, verify, drop duplicate tracks, upload, clean up.

The same three stages `archive_batch.py` uses -- they share
`scripts.transcode.audio_tracks` and `scripts/transcode/encode_master.sh`
so that an archive made here and one made by the news pipeline are made
the same way. What differs is everything around it: no catalogue lookup,
no episode identity, and the source is a local folder rather than SFTP.

Nothing is left on the local disk once a file is up: the drive this runs
against is usually nearly full, which is why the work goes to the SSD in
the first place.
"""
import os
import subprocess
import time

from scripts.transcode import audio_tracks
from tools.mxf2mkv import upload

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENCODE_SCRIPT = os.path.join(ROOT, "scripts", "transcode", "encode_master.sh")


class EncodeError(Exception):
    """This master did not become a faithful archive."""


def _read_md5(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip().split("=", 1)[-1]


def source_md5s(work, name):
    """The per-track source fingerprints encode_master.sh left behind."""
    out = []
    index = 0
    while True:
        path = os.path.join(work, "%s.src-a%d.md5" % (name, index))
        if not os.path.exists(path):
            return out
        out.append(_read_md5(path))
        index += 1


def is_stream_copied(archive):
    """Whether the archive's audio was copied rather than re-encoded."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", archive],
        capture_output=True, text=True)
    return done.stdout.strip() != "flac"


def encoded_md5s(archive, tracks, stream_copy):
    """The same fingerprints, taken off the encoded archive on the SSD.

    `stream_copy` has to match the path the encode took: a copied AAC
    track must be hashed as packets, not decoded samples -- Matroska drops
    mp4's priming-delay side data, so decoding one picks up an extra frame
    at the front and every sample after it reads as different even though
    the bytes are identical.
    """
    out = []
    for index in range(tracks):
        cmd = ["ffmpeg", "-v", "error", "-i", archive,
               "-map", "0:a:%d" % index]
        if stream_copy:
            cmd += ["-c:a", "copy"]
        cmd += ["-f", "md5", "-"]
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode:
            raise EncodeError("讀無封存ê音軌指紋：%s a:%d" % (archive, index))
        out.append(done.stdout.strip().split("=", 1)[-1])
    return out


def remux(archive, keep, dst):
    """Copy the archive across keeping only `keep`'s audio tracks."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", archive, "-map", "0:v:0"]
    for index in keep:
        cmd += ["-map", "0:a:%d" % index]
    cmd += ["-c", "copy", dst]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise EncodeError("重新封裝失敗：%s\n%s" % (dst, done.stderr))


def _name_for(relative):
    """A flat work-dir name for a possibly nested source path.

    Two files can share a basename in different subfolders, so the
    separators become "__" rather than being dropped -- otherwise
    `夜間/a.mxf` and `午間/a.mxf` would fight over the same work files.
    """
    stem = os.path.splitext(relative)[0]
    return stem.replace(os.sep, "__").replace("/", "__")


def one_file(job, work_dir, crf=23, pix_fmt="yuv420p", log=None):
    """Encode, verify, remux, upload, delete. Returns a manifest entry."""
    started = time.time()
    name = _name_for(job.relative)
    everything = os.path.join(work_dir, name + ".all.mkv")
    finished = os.path.join(work_dir, name + ".mkv")
    made = [everything, finished]
    index = 0
    try:
        done = subprocess.run(
            ["bash", ENCODE_SCRIPT, job.source, work_dir, name,
             str(crf), pix_fmt],
            capture_output=True, text=True)
        if log is not None:
            log(done.stderr)
        if done.returncode:
            raise EncodeError("編碼失敗：%s\n%s"
                              % (job.relative, done.stderr))

        sources = source_md5s(work_dir, name)
        while os.path.exists(os.path.join(
                work_dir, "%s.src-a%d.md5" % (name, index))):
            made.append(os.path.join(work_dir,
                                     "%s.src-a%d.md5" % (name, index)))
            index += 1
        if not sources:
            raise EncodeError("%s 無產出音軌指紋" % job.relative)

        encoded = encoded_md5s(everything, len(sources),
                               is_stream_copied(everything))
        verdict = audio_tracks.decide(sources, encoded)
        if not verdict.bit_exact:
            raise EncodeError("%s %s" % (job.relative, verdict.summary))

        remux(everything, verdict.keep, finished)
        local_size = os.path.getsize(finished)
        remote_size = upload.put(finished, job.remote, local_size)

        return {
            "src_bytes": os.path.getsize(job.source),
            "remote": job.remote,
            "remote_bytes": remote_size,
            "audio_tracks_src": len(sources),
            "audio_tracks_kept": len(verdict.keep),
            "音軌": verdict.summary,
            "音訊逐位元相符": True,
            "seconds": round(time.time() - started, 1),
            "結果": "成功",
        }
    finally:
        # 成功抑是失敗攏共本機ê物件清掉：隨身硬碟本身就欲滇矣,
        # 中間產物是刁工囥去 SSD ê，無應該留咧。失敗ê時陣工作
        # 目錄本身會留（batch.py 決定ê），毋過這支ê半成品無路用。
        for path in made:
            if os.path.exists(path):
                os.remove(path)


def already_done(job):
    """Whether the server already has this one, finished.

    See `upload.already_there` for why existence is enough here.
    """
    return upload.already_there(job.remote)
