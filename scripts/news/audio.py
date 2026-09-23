#!/usr/bin/env python3
"""Where the audio to recognise comes from -- shared by kaldi and whisper.

Both speech-side engines feed on the audio track of the same episode
video, never anything a catalogue records as "the audio file" (see the
asr-bilingual-srt spec's 音檔由該集影片抽出 requirement -- 15% of
catalogue rows have no derivable audio path). The video itself sits
somewhere temporary: the archival mkv if this episode has one, otherwise
a fresh pull from SFTP, verified by byte count and deleted once its
audio track is out.

This module used to live split across `asrmt_run.audio_source` /
`extract_audio` (which checked a staged original left behind by cue-
cutting before either of the other two) and `asrmt_batch._fetch` (which
had no byte check at all and never deleted what it fetched). Both
engines want the same three things now, so they moved here, and the
staged-original shortcut is gone with them: reading a file that cue-
cutting owns raced two callers to delete it, and there is now a second
engine that also wants the audio -- mkv, then SFTP, every time, is the
one rule both sides can share (使用者裁定 2026-09-18).
"""
import os
import subprocess

from scripts.news import paths
from scripts.news import resolve_slug
from scripts.news import sources
from scripts.errors import PipelineError

SFTP_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sftp.sh")


def video_source(entry):
    """(local, remote) for this episode's video: the archived mkv, else
    a remote path chosen by `sources.pick`.

    暫存區裡切 cue 時可能留下的原檔 SHALL NOT 被當作捷徑讀——它的
    生命是切 cue 那一步自己的；兩爿引擎對仝一集才會走仝一條路。
    """
    name = entry["srt_name"]
    archived = paths.mkv_path(name)
    if os.path.exists(archived):
        return archived, ""
    chosen, problem = sources.pick(entry)
    if not chosen:
        raise PipelineError("%s：本機無封存 mkv，節目目錄嘛揀袂出來源（%s）"
                            % (name, problem))
    return "", resolve_slug.server_path(chosen)


def _remote_size(remote):
    out = subprocess.run(["bash", SFTP_SCRIPT, "ls", remote],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if line.startswith("-"):
            return int(line.split()[4])
    return None


def fetch_video(remote, local):
    """SFTP get, verified by byte count.

    一份位元組數已經對的本機檔案重用、不重抓（CLAUDE.md〈長時間的
    背景工作〉的既有做法）；抓完位元組數不符就刪掉不完整的檔並
    中止，不留半個檔給下一步誤用。
    """
    size = _remote_size(remote)
    if size is None:
        raise PipelineError("SFTP 揣無：%s" % remote)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    have = os.path.getsize(local) if os.path.exists(local) else 0
    if have != size:
        done = subprocess.run(["bash", SFTP_SCRIPT, "get", remote, local])
        got = os.path.getsize(local) if os.path.exists(local) else 0
        if done.returncode or got != size:
            if os.path.exists(local):
                os.remove(local)
            raise PipelineError("sftp 抓無完整：%s（%s/%s bytes）"
                                % (remote, got, size))


def extract_audio(local_video, out):
    """對影片抽音軌，落做辨識食ê mp3。"""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done = subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", local_video,
                           "-vn", "-ac", "1", "-ar", "16000", out],
                          capture_output=True)
    if done.returncode or not os.path.exists(out):
        raise PipelineError("對 %s 抽音軌失敗" % local_video)
    return out


def get_audio(entry, out):
    """取這集ê音檔到 out：有封存 mkv 就直接抽，SFTP 抓ê話抽煞就刪。

    封存 mkv 是逐集的正本備份，永遠不刪；自 SFTP 抓來的只是這一步
    的暫存，磁碟放袂落逐集 2.2 GB 累積，抽煞就愛清。
    """
    name = entry["srt_name"]
    local, remote = video_source(entry)
    fetched = False
    if not local:
        local = paths.staged_path(name, entry["file"])
        fetch_video(remote, local)
        fetched = True
    extract_audio(local, out)
    if fetched:
        os.remove(local)
    return out
