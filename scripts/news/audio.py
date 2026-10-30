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
from scripts.news import video_names
from scripts.errors import PipelineError

SFTP_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sftp.sh")


def video_source(entry, sftp=None, say=print):
    """(local, remote) for this episode's video: the archived mkv, else the
    place it is on the server.

    The server place is the canonical one derived from the name
    (`paths.video_path`); only when the server says that is *not found* does
    `video_names.locate` fall back to `原始影片檔案位置` (and say so), so an
    episode not yet moved into place can still be read. A failure that is
    not "not found" (timeout, permission) is raised, not papered over.

    暫存區裡切 cue 時可能留下的原檔 SHALL NOT 被當作捷徑讀——它的
    生命是切 cue 那一步自己的；兩爿引擎對仝一集才會走仝一條路。
    """
    name = entry["srt_name"]
    archived = paths.mkv_path(name)
    if os.path.exists(archived):
        return archived, ""
    located = video_names.locate(entry, sftp or video_names.Sftp(), say=say)
    return "", located.path


def fetch_video(remote, local, sftp=None):
    """SFTP get, verified by byte count.

    一份位元組數已經對的本機檔案重用、不重抓（CLAUDE.md〈長時間的
    背景工作〉的既有做法）；抓完位元組數不符就刪掉不完整的檔並
    中止，不留半個檔給下一步誤用。伺服器問大小失敗：講「揣無」ê干焦
    伺服器明講 not found ê時，逾時、權限這款失敗直接 raise。
    """
    size = (sftp or video_names.Sftp()).stat(remote)
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


def get_audio(entry, out, sftp=None):
    """取這集ê音檔到 out：有封存 mkv 就直接抽，SFTP 抓ê話抽煞就刪。

    封存 mkv 是逐集的正本備份，永遠不刪；自 SFTP 抓來的只是這一步
    的暫存，磁碟放袂落逐集 2.2 GB 累積，抽煞就愛清。
    """
    name = entry["srt_name"]
    local, remote = video_source(entry, sftp=sftp)
    fetched = False
    if not local:
        # 暫存檔名是伺服器頂彼支ê名：正規位置就是 <成果檔名>.mkv，退回
        # 原始位置就是來源ê原名。
        local = paths.staged_path(name, remote)
        fetch_video(remote, local, sftp=sftp)
        fetched = True
    extract_audio(local, out)
    if fetched:
        os.remove(local)
    return out
