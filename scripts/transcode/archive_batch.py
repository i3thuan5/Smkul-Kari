#!/usr/bin/env python3
"""Archive every delivered episode's master as an mkv (使用者裁定 spec:
.claude/skills/video-subtitle-srt/壓縮率分析.md -- CRF 23, yuv420p, flac,
MKV, verify before delete).

    python3 -m scripts.transcode.archive_batch [--limit N]

Per episode: fetch the master over SFTP into the shared stage dir (reused
if already there with the right byte count), then encode in three stages --
one ffmpeg pass writing an archive with every source audio track plus a
per-track source fingerprint, a comparison that decides which tracks are
duplicates, and a `-c copy` remux down to the ones worth keeping. The
result is renamed into place only once the audio has been shown to
reproduce the source bit for bit; then the staged master is deleted.

An episode whose archive mkv already exists is skipped, so an interrupted
batch resumes without redoing finished work; a failing episode is reported
and the batch moves on to the next one.
"""
import argparse
import contextlib
import csv
import json
import os
import subprocess
import sys

from scripts.news import paths
from scripts.news import resolve_slug
from scripts.news import sources
from scripts.transcode import audio_tracks
from scripts.errors import PipelineError

REMOTE_ROOT = "/docker"

# smkul.csv abbreviates the Feb mxf batch's location to "ilrdf-corpus/2月/
# <檔名>" -- a leftover from when those masters were mounted locally at
# that path. On the SFTP host the real directory is one level deeper (see
# the same note in scripts/news/fetch_sftp.sh); the short form 404s.
FEB_MXF_SHORTHAND = "ilrdf-corpus/2月/"
FEB_MXF_REAL_DIR = "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
HERE = os.path.dirname(os.path.abspath(__file__))
ENCODE_SCRIPT = os.path.join(HERE, "encode_master.sh")
SFTP_SCRIPT = os.path.join(paths.ROOT, "scripts", "news", "sftp.sh")


def _cell_path(cell, slot):
    """One catalogue cell -> the path naming this slot, or None.

    Defensive: the master catalogue sometimes packs several paths into
    one cell separated by ";" (see asrmt_run.mp3_remote).
    """
    candidates = []
    for part in cell.split(";"):
        if part.strip():
            candidates.append(part.strip())
    if not candidates:
        return None
    for part in candidates:
        if slot in part:
            return part
    return candidates[0]


def master_remote(srt_name, catalogue_rows, rows, inventory):
    """The best master this episode has, on the SFTP host.

    Ask the **catalogue** first, not `smkul.csv`. The two answer different
    questions and only one of them is about masters:

    - `smkul.csv` records which file this SRT was *made from* -- one path,
      fixed at delivery, and correctly never revised.
    - the catalogue's cell is a *candidate list*, and `sources.pick()`
      applies 「mxf 母帶優先」 to it.

    February's first 13 episodes were delivered before `sources.py`
    existed, from the `7月/` mp4s. Their masters are still on the server,
    but asking `smkul.csv` returns the mp4, `is_master()` says no, and all
    13 are silently skipped -- which is exactly what happened when the
    archives were backfilled.

    Falls back to `video_remote` when the catalogue does not know the
    episode, so an episode registered by hand still archives.
    """
    for row in catalogue_rows:
        if row.get("srt_name") != srt_name:
            continue
        chosen, _ = sources.pick(row)
        if chosen:
            return _expand(chosen)
    return video_remote(srt_name, rows, inventory=inventory)


def _expand(chosen):
    if chosen.startswith(FEB_MXF_SHORTHAND):
        chosen = FEB_MXF_REAL_DIR + chosen[len(FEB_MXF_SHORTHAND):]
    return REMOTE_ROOT + "/" + chosen


def video_remote(srt_name, rows, inventory=None):
    """The episode's master path on the SFTP host.

    `rows` is the delivered `smkul.csv`, which is the source of truth --
    but it deliberately omits `pending` episodes, and archiving happens
    *while* an episode is pending: `fetch_sftp.sh` keeps the master staged
    the moment the cues are cut, precisely so a 19 GB file is not fetched
    twice, and that is long before `publish` clears the flag.

    So a miss falls back to the inventory, which is the registry and lists
    every episode registered, pending or delivered. Without this the
    per-episode flow dies with "no video in smkul.csv", which reads like
    the catalogue is wrong when nothing is wrong at all.
    """
    date = "%s-%s-%s" % (srt_name[0:4], srt_name[4:6], srt_name[6:8])
    slot = srt_name.split("_")[2]
    for row in rows:
        if row["播出日期"] != date or row["播出時段"] != slot:
            continue
        chosen = _cell_path(row["影片檔案位置"].strip(), slot)
        if chosen is None:
            continue
        return _expand(chosen)
    for entry in inventory or []:
        if entry.get("srt_name") != srt_name:
            continue
        chosen = (entry.get("video") or "").strip()
        if chosen:
            return _expand(chosen)
    raise PipelineError("smkul.csv 佮 inventory 攏無 %s ê影片" % srt_name)


# Where the archival copies also live, on the server, laid out by broadcast
# month the same way the store is.
REMOTE_ARCHIVE_ROOT = "/home/news/mkv"

MASTER_EXT = ".mxf"


def is_master(remote):
    """Only masters are archived.

    An mp4 is already a compressed delivery copy; re-encoding one produces a
    second lossy generation and buys nothing. `fetch_sftp.sh` deletes those
    as soon as the cues are cut, so there would be nothing here to encode
    from either.
    """
    return os.path.splitext(remote)[1].lower() == MASTER_EXT


def stage_name(srt_name, remote):
    """The staged file's name -- the source's own, as fetch_sftp.sh writes it.

    Not `<srt_name><ext>`: the master was already downloaded once to cut the
    cues, and `fetch_sftp.sh` keeps it for this step precisely so a 19 GB
    file is not fetched twice. Naming it differently here would look in the
    wrong place and fetch it again.
    """
    return os.path.basename(remote)


def remote_archive_dir(srt_name):
    """<root>/<年-月> on the server."""
    return "%s/%s" % (REMOTE_ARCHIVE_ROOT, paths.month_of(srt_name))


def remote_archive_path(srt_name):
    """Where this episode's mkv goes on the server."""
    return "%s/%s.mkv" % (remote_archive_dir(srt_name),
                          paths.check_srt_name(srt_name))


def master_episodes(catalogue):
    """[(srt_name, remote path)] for every episode whose source is a master.

    Built from the catalogue rather than from `smkul.csv`, which lists only
    delivered episodes: archiving a master has nothing to do with how far
    the subtitle work has got. Which file is the episode's is decided by the
    same rules everything else uses (`sources.py`), so an episode archived
    here and the same episode fetched by the pipeline are the same file.
    """
    rows = []
    for row in catalogue.rows:
        if row.get("播出日期"):
            rows.append(row)
    out = []
    for row, (video, _problem) in zip(rows, sources.resolve(rows)):
        if not video or not is_master(video):
            continue
        try:
            name = resolve_slug.srt_name(row, int(row["集數"]))
        except (PipelineError, KeyError, ValueError):
            continue
        # The catalogue's paths are already relative to REMOTE_ROOT
        # ("ilrdf-corpus/…"); normalising would strip that and point one
        # level too high.
        out.append((name, REMOTE_ROOT + "/" + video.strip().lstrip("/")))
    out.sort()
    return out


# The encode may land a frame or so either side of the source; anything
# beyond this is not rounding, it is a short file.
DURATION_TOLERANCE = 2.0


def duration_matches(encoded, expected):
    """Whether the archive is as long as the store's timeline says it is.

    This is the one place a half-uploaded master shows itself. `ffprobe`
    reads the *header* of an MXF, which still claims the full running time
    on a truncated upload -- two of the 24 February masters were exactly
    that. The encode, on the other hand, has to decode every frame, so what
    comes out is as long as the file really is.

    No timeline to compare against is not a failure: an episode can be
    archived before its cues are cut, and inventing a verdict there would
    be a claim nobody measured.
    """
    if expected is None:
        return True
    return abs(encoded - expected) <= max(DURATION_TOLERANCE, expected * 0.01)


def cues_duration(srt_name):
    """How long the store's timeline says this episode is, or None."""
    path = paths.stage_path(paths.KARI_CUES, srt_name, ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle).get("duration")


def probe_duration(path):
    """Seconds of the encoded file, by decoding its container."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise PipelineError("ffprobe 讀無時長：%s" % path)


def remote_dirs_to_make(srt_name):
    """Every level of the archive folder, outermost first.

    sftp's `mkdir` makes one level at a time; handed a path whose parent is
    missing it just fails, and the first upload into a new month is exactly
    that case.
    """
    parts = remote_archive_dir(srt_name).strip("/").split("/")
    out = []
    for index in range(len(parts)):
        out.append("/" + "/".join(parts[:index + 1]))
    return out


def needs_upload(local_size, remote_size):
    """Whether this archive still has to go up.

    Compared by byte count rather than "does it exist": an upload that was
    interrupted leaves a short file behind, and a shorter file that is
    present would otherwise read as done.
    """
    return remote_size != local_size


def _upload(local, srt_name):
    """Put the verified mkv on the server, under its broadcast month."""
    for folder in remote_dirs_to_make(srt_name):
        made = subprocess.run(["bash", SFTP_SCRIPT, "mkdir", folder],
                              capture_output=True)
        if made.returncode:
            raise PipelineError("袂使建遠端資料夾：%s" % folder)
    remote = remote_archive_path(srt_name)
    sent = subprocess.run(["bash", SFTP_SCRIPT, "put", local, remote])
    if sent.returncode:
        raise PipelineError("上傳失敗：%s" % remote)
    size = _remote_size(remote)
    local_size = os.path.getsize(local)
    if size != local_size:
        raise PipelineError("上傳了後位元組數無仝：%s（%s/%s）"
                            % (remote, size, local_size))
    return remote


def output_path(srt_name, archive_dir=None):
    # 預設值查佇呼叫ê時陣，毋是 import ê時陣：寫做
    # `archive_dir=paths.MKV_ARCHIVE` ê話，模組載入了後 patch
    # paths.MKV_ARCHIVE 就無效，測試改了看起來若像有影，其實無。
    if archive_dir is None:
        archive_dir = paths.MKV_ARCHIVE
    return os.path.join(archive_dir, srt_name + ".mkv")


def already_done(srt_name, archive_dir=None):
    return os.path.exists(output_path(srt_name, archive_dir))


def _remote_size(remote):
    out = subprocess.run(
        ["bash", SFTP_SCRIPT, "ls", remote],
        capture_output=True, text=True)
    size = None
    for line in out.stdout.splitlines():
        if line.startswith("-"):
            size = int(line.split()[4])
            break
    return size


def _fetch(remote, local):
    size = _remote_size(remote)
    if size is None:
        raise PipelineError("not found on SFTP: %s" % remote)
    have = os.path.getsize(local) if os.path.exists(local) else 0
    if have == size:
        print("  已在 stage，重用（%d MB）" % (size // 1_000_000))
        return
    done = subprocess.run(["bash", SFTP_SCRIPT, "get", remote, local])
    got = os.path.getsize(local) if os.path.exists(local) else 0
    if done.returncode or got != size:
        if os.path.exists(local):
            os.remove(local)
        raise PipelineError("sftp fetch incomplete: %s (%s/%s bytes)"
                            % (remote, got, size))


class Busy(PipelineError):
    """Another process is already encoding this episode."""


def lock_path(dst):
    return dst + ".lock"


def is_locked(dst):
    return os.path.exists(lock_path(dst))


@contextlib.contextmanager
def encode_lock(dst):
    """Claim one episode's encode, atomically.

    "Is anyone encoding this?" cannot be answered by looking, because the
    looking and the starting are two separate moments: A checks and sees
    nothing, B starts, A starts too, and A's first act is to delete B's
    part-finished file. Both followed the rule and they still collided.

    O_EXCL makes the claim and the check the same operation, so exactly one
    caller gets it. The holder's pid goes in the file: if a crash leaves one
    behind, the message says whose it was and `kill -0` settles whether it
    is still alive.
    """
    path = lock_path(dst)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Busy("%s 有別的行程咧轉（鎖：%s）"
                   % (os.path.basename(dst), path))
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        yield
    finally:
        if os.path.exists(path):
            os.remove(path)


def _read_md5(path):
    """The hash out of one of ffmpeg's md5-muxer files ("MD5=<hex>")."""
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip().split("=", 1)[-1]


def _source_md5s(work, name):
    """The per-track source fingerprints encode_master.sh left behind."""
    out = []
    index = 0
    while True:
        path = os.path.join(work, "%s.src-a%d.md5" % (name, index))
        if not os.path.exists(path):
            return out
        out.append(_read_md5(path))
        index += 1


def _encoded_md5s(archive, tracks, stream_copy):
    """The same fingerprints, taken off the encoded archive.

    Read from the local SSD, so this costs nothing like the source read
    it replaces. `stream_copy` has to match the path the encode took: a
    copied AAC track must be hashed as packets, not decoded samples --
    Matroska drops mp4's priming-delay side data, so decoding one picks
    up an extra frame at the front and every sample after it reads as
    different even though the bytes are identical.
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
            raise PipelineError("讀無封存ê音軌指紋：%s a:%d"
                                % (archive, index))
        out.append(done.stdout.strip().split("=", 1)[-1])
    return out


def _is_stream_copied(archive):
    """Whether the archive's audio was copied rather than re-encoded."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", archive],
        capture_output=True, text=True)
    return done.stdout.strip() != "flac"


def _remux(archive, keep, dst):
    """Copy the archive across keeping only `keep`'s audio tracks."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", archive, "-map", "0:v:0"]
    for index in keep:
        cmd += ["-map", "0:a:%d" % index]
    cmd += ["-c", "copy", dst]
    done = subprocess.run(cmd)
    if done.returncode:
        raise PipelineError("重新封裝失敗：%s" % dst)


def _encode(src, dst):
    """Encode one master into its archive, one process at a time.

    Three stages, because `encode_master.sh` deliberately stops after the
    first one (see its header): it does a single ffmpeg pass that writes
    an archive holding *every* source audio track plus one md5 per source
    track, and leaves the judgement to us.

    1. encode + fingerprint the source, one read of the master
    2. compare against the archive's own tracks and decide what to keep
    3. remux (-c copy) down to the kept tracks

    Audio that does not reproduce the source bit for bit is a failure, not
    a warning, and nothing lands in `dst` when it happens.
    """
    work = os.path.dirname(dst)
    name = os.path.basename(dst)
    if name.endswith(".mkv"):
        name = name[:-len(".mkv")]
    everything = os.path.join(work, name + ".all.mkv")
    partial = dst + ".partial.mkv"
    with encode_lock(dst):
        # Ours now -- the lock says no one else can be writing this one, so
        # leftovers are from a run that died and are safe to clear.
        for stale in (partial, everything):
            if os.path.exists(stale):
                os.remove(stale)
        try:
            subprocess.run(["bash", ENCODE_SCRIPT, src, work, name],
                           check=True)
            sources = _source_md5s(work, name)
            encoded = _encoded_md5s(everything, len(sources),
                                    _is_stream_copied(everything))
            verdict = audio_tracks.decide(sources, encoded)
            if not verdict.bit_exact:
                raise PipelineError("%s 音訊無逐位元相符：%s"
                                    % (name, verdict.summary))
            print("  %s" % verdict.summary)
            _remux(everything, verdict.keep, partial)
            os.rename(partial, dst)
        finally:
            for leftover in (everything, partial):
                if os.path.exists(leftover):
                    os.remove(leftover)
            for index in range(16):
                path = os.path.join(work, "%s.src-a%d.md5" % (name, index))
                if os.path.exists(path):
                    os.remove(path)


def apply_limit(rows, limit):
    """The first `limit` of them, or all of them when limit is 0."""
    if not limit:
        return rows
    return rows[:limit]


def run_all_masters(args):
    """Every master in the catalogue that has no archive yet, one at a time.

    Resumable and safe to leave running: an episode whose mkv is already
    there is skipped, and so is one another process is part-way through
    (its `.partial.mkv` is on disk) -- the pipeline runs this same step
    per episode, so two runs can legitimately overlap.

    Disk stays at one master plus one archive: the master is fetched,
    encoded, checked, uploaded and only then deleted.
    """
    os.makedirs(paths.STAGE, exist_ok=True)
    os.makedirs(paths.MKV_ARCHIVE, exist_ok=True)

    episodes = master_episodes(resolve_slug.load())
    todo = []
    for name, remote in episodes:
        if already_done(name):
            continue
        todo.append((name, remote))
    print("目錄內底 %d 支母帶，猶未封存 %d 支"
          % (len(episodes), len(todo)))
    # Applied before the listing, not after: `--list` answers "is this the
    # set I meant?", and a list that does not match what dropping --list
    # would actually do is the worst kind of wrong documentation.
    todo = apply_limit(todo, args.limit)
    if args.limit:
        print("照 --limit 算 %d 支" % len(todo))
    if args.list:
        for name, remote in todo:
            print("   %-46s %s" % (name, os.path.basename(remote)))
        print("\n（干焦列，啥物攏無做。欲開始就提掉 --list）")
        return 0

    done = []
    failed = []
    for position, (name, remote) in enumerate(todo, 1):
        out = output_path(name)
        if is_locked(out):
            print("skip  %s（別人咧轉）" % name, flush=True)
            continue
        if already_done(name):
            print("skip  %s（拄仔才有人轉好）" % name, flush=True)
            continue
        print("== [%d/%d] %s" % (position, len(todo), name), flush=True)
        local = os.path.join(paths.STAGE, stage_name(name, remote))
        try:
            print("  抓取", remote, flush=True)
            _fetch(remote, local)
            print("  轉檔 ->", out, flush=True)
            _encode(local, out)

            expected = cues_duration(name)
            actual = probe_duration(out)
            if not duration_matches(actual, expected):
                os.remove(out)
                raise PipelineError(
                    "轉出來才 %.0f 秒，時間軸講 %.0f 秒——母帶可能上傳無齊，"
                    "封存已經刣掉" % (actual, expected))

            if not args.no_upload:
                print("  上傳 ->", remote_archive_path(name), flush=True)
                _upload(out, name)
            os.remove(local)
            done.append(name)
            print("  好矣（%.2f GB）" % (os.path.getsize(out) / 1e9),
                  flush=True)
        except Busy as taken:
            print("skip  %s（%s）" % (name, taken), flush=True)
        except (PipelineError, subprocess.CalledProcessError) as error:
            failed.append((name, str(error)))
            print("FAILED:", name, "--", error, flush=True)

    print("\n封存 %d 支" % len(done))
    for name, why in failed:
        print("失敗：%s（%s）" % (name, why))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N episodes (0 = all)")
    ap.add_argument("--only", default="",
                    help="just this srt_name (逐集流程用ê入口)")
    ap.add_argument("--no-upload", action="store_true",
                    help="干焦編本機ê封存，莫送去伺服器")
    ap.add_argument("--upload-only", action="store_true",
                    help="本機已經有ê封存補送去伺服器，莫重編")
    ap.add_argument("--all-masters", action="store_true",
                    help="目錄內底逐支 mxf 母帶攏轉做 mkv（會使續跑）")
    ap.add_argument("--list", action="store_true",
                    help="干焦列出欲做啥，啥物攏無做")
    args = ap.parse_args(argv)

    if args.all_masters or args.list:
        return run_all_masters(args)

    os.makedirs(paths.STAGE, exist_ok=True)
    os.makedirs(paths.MKV_ARCHIVE, exist_ok=True)

    entries = paths.load_inventory()
    catalogue = resolve_slug.load().rows
    with open(paths.TRACKER_STORE, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    done = []
    failed = []
    for entry in entries:
        name = entry["srt_name"]
        if args.only and name != args.only:
            continue
        if args.upload_only:
            if not already_done(name):
                continue
            if args.limit and len(done) + len(failed) >= args.limit:
                break
            local = output_path(name)
            local_size = os.path.getsize(local)
            remote = remote_archive_path(name)
            if not needs_upload(local_size, _remote_size(remote)):
                print("skip  %s（伺服器頂懸已經有）" % name)
                continue
            print("==", name, flush=True)
            try:
                print("  上傳 ->", remote)
                _upload(local, name)
                done.append(name)
            except (PipelineError, subprocess.CalledProcessError) as error:
                failed.append((name, str(error)))
                print("FAILED:", name, "--", error, flush=True)
            continue
        if entry.get("truncated"):
            continue
        # A pending episode is fair game here: the master is on disk right
        # now, straight out of the cue cutting, and this is the one moment
        # it does not have to be fetched again. Waiting for `publish` would
        # mean re-downloading it.
        if entry.get("pending") and not args.only:
            continue
        if already_done(name):
            continue
        if args.limit and len(done) + len(failed) >= args.limit:
            break
        remote = master_remote(name, catalogue, rows, entries)
        if not is_master(remote):
            continue
        print("==", name, flush=True)
        local = os.path.join(paths.STAGE, stage_name(name, remote))
        try:
            print("  抓取", remote)
            _fetch(remote, local)
            print("  轉檔 ->", output_path(name))
            _encode(local, output_path(name))
            if not args.no_upload:
                print("  上傳 ->", remote_archive_path(name))
                _upload(output_path(name), name)
            os.remove(local)
            done.append(name)
        except Busy as taken:
            print("skip ", name, "--", taken, flush=True)
        except (PipelineError, subprocess.CalledProcessError) as error:
            failed.append((name, str(error)))
            print("FAILED:", name, "--", error, flush=True)

    print("\n完成 %d 集" % len(done))
    for name, why in failed:
        print("失敗：%s（%s）" % (name, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
