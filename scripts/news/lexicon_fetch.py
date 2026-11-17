#!/usr/bin/env python3
"""The 16 official dictionaries, kept in kithann/, fetched when missing.

    python3 -m scripts.news.lexicon_fetch      # 確認 16 族都在、蒸餾詞庫

The xlsx files live on the SFTP (`/docker/族語辭典_單詞與例句/`) and the
SFTP is guaranteed to hold them (使用者裁定 2026-09-24), so they are not
committed: a machine without them fetches them. A complete local copy
never contacts the server -- the pipeline and the rebuild run offline
once it is there.

What this refuses, by name:

  少一族      別族判定 compares all 16 tribes; with one missing, every
              speaker of it scores 命中率不足 and nothing says why.
  一族兩版    a stale xlsx beside a new one (the date prefix changes per
              release): which one the pipeline read would depend on
              directory order.
  抓不完整    same rule as fetching a video (`news/audio.py`): the
              half file is deleted and the run stops.

The tribe comes from the file name (「…_10邵語5230筆…」), never from the
date prefix, which changes with every release.

補充詞表（`supplements`）：官方辭典一族只收一個語言別，魯凱收霧台。
萬山主播 Lavoras Tavelengae 的開場命中率只有 0.048、85% 的組被判
不採用（2026-11-16 量）。`SUPPLEMENTS` 裡的語言別從族語E樂園 教材
（`kithann/E樂園-解壓/`）現抽詞表，跟官方辭典取聯集用。E樂園 沒有
SFTP 來源，不在就指名中止；沒有要補的語言別時不讀它。
"""
import os
import re
import subprocess
import sys

from scripts import datadirs
from scripts import languages
from scripts.errors import PipelineError
from scripts.lexicon import dictionary
from scripts.lexicon import klokah
from scripts.news import paths

SFTP_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "sftp.sh")
NAME = re.compile(r"_[0-9]{2}([^_0-9]+?)語[0-9]")
OCTAL = re.compile(r"\\([0-7]{3})")
CACHE = "詞庫"

# 官方辭典沒收、要用 E樂園 詞表補的語言別代號（使用者 2026-11-16 裁定
# 只做萬山）。
SUPPLEMENTS = frozenset({"dru-x-opnh"})


def tribes():
    """The 16 族語別 a complete set must cover."""
    out = []
    for name in languages.LANGUAGES:
        if languages.LANGUAGES[name][1] != "und":
            out.append(name)
    return out


def tribe_of(filename):
    """族語別 in a dictionary file name, or None."""
    found = NAME.search(filename)
    if not found or found.group(1) not in languages.LANGUAGES:
        return None
    return found.group(1)


def _unescape(text):
    """sftp prints non-ASCII bytes as \\ooo; turn them back into UTF-8."""
    raw = bytearray()
    position = 0
    for match in OCTAL.finditer(text):
        raw.extend(text[position:match.start()].encode("utf-8"))
        raw.append(int(match.group(1), 8))
        position = match.end()
    raw.extend(text[position:].encode("utf-8"))
    return raw.decode("utf-8")


def parse_listing(text):
    """{file name: byte count} from `sftp.sh ls` output (regular files)."""
    out = {}
    for line in text.splitlines():
        if not line.startswith("-"):
            continue
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        out[_unescape(parts[8])] = int(parts[4])
    return out


def _sftp(verb, *args):
    done = subprocess.run(["bash", SFTP_SCRIPT, verb] + list(args),
                          capture_output=True, text=True)
    return done.returncode, done.stdout


def _by_tribe(names, where):
    """{tribe: name}; two names for one tribe is refused."""
    found = {}
    for name in sorted(names):
        if not name.endswith(".xlsx"):
            continue
        tribe = tribe_of(name)
        if tribe is None:
            continue
        if tribe in found:
            raise PipelineError(
                "%s有兩個%s辭典：%s、%s——留一個再跑"
                % (where, tribe, found[tribe], name))
        found[tribe] = name
    return found


def _missing(found):
    out = []
    for tribe in tribes():
        if tribe not in found:
            out.append(tribe)
    return out


def ensure(folder=None, runner=None, remote=None):
    """{族語別: local xlsx path} for all 16, fetching only what is missing."""
    folder = folder or paths.LEXICON_KITHANN
    remote = remote or paths.LEXICON_REMOTE
    runner = runner or _sftp
    os.makedirs(folder, exist_ok=True)
    local = _by_tribe(os.listdir(folder), "kithann 辭典資料夾")
    lacking = _missing(local)
    if lacking:
        code, text = runner("ls", remote)
        if code:
            raise PipelineError("列不出 SFTP 的辭典目錄 %s，缺：%s"
                                % (remote, "、".join(lacking)))
        sizes = parse_listing(text)
        offered = _by_tribe(sizes, "SFTP 上")
        absent = _missing(offered)
        if absent:
            raise PipelineError("SFTP 上缺這幾族的辭典：%s"
                                % "、".join(absent))
        for tribe in lacking:
            name = offered[tribe]
            target = os.path.join(folder, name)
            code, _ = runner("get", remote + "/" + name, target)
            got = os.path.getsize(target) if os.path.exists(target) else 0
            if code or got != sizes[name]:
                if os.path.exists(target):
                    os.remove(target)
                raise PipelineError("%s辭典沒抓完整：%s（%d/%d bytes）"
                                    % (tribe, name, got, sizes[name]))
            local[tribe] = name
    out = {}
    for tribe, name in local.items():
        out[tribe] = os.path.join(folder, name)
    return out


def lexicons(folder=None, runner=None):
    """{族語別: set of words}, distilling any xlsx newer than its cache."""
    folder = folder or paths.LEXICON_KITHANN
    books = ensure(folder, runner)
    cache = os.path.join(folder, CACHE)
    out = {}
    for tribe in sorted(books):
        target = os.path.join(cache, tribe + ".txt")
        stale = (not os.path.exists(target)
                 or os.path.getmtime(target) < os.path.getmtime(books[tribe]))
        if stale:
            dictionary.distil(books[tribe], target)
        out[tribe] = dictionary.load(target)
    return out


def supplements(codes, source=None, names=None):
    """{語言別代號: set of words} from E樂園, for the codes asked.

    No codes, no reading: a machine that has not moved E樂園 over yet can
    still do every other tribe.
    """
    if not codes:
        return {}
    source = source or datadirs.KLOKAH_SOURCE
    names = names or datadirs.KLOKAH_NAMES
    for path in (source, names):
        if not os.path.exists(path):
            raise PipelineError(
                "%s 不在：補充詞表（%s）要讀族語E樂園；E樂園 沒有 SFTP 來源，"
                "換機器要把 kithann/E樂園/ 搬過來再解壓"
                % (path, "、".join(sorted(codes))))
    out = {}
    for full_name, words in klokah.vocabularies(source, names).items():
        _language, _variety, code = klokah.variety_of(full_name)
        if code in codes:
            out[code] = words
    for code in sorted(codes):
        if code not in out:
            raise PipelineError("族語E樂園（%s）沒有 %s 的文本" % (source, code))
    return out


def main():
    books = ensure()
    found = lexicons()
    for tribe in sorted(found):
        print("%s\t%d 詞\t%s" % (tribe, len(found[tribe]),
                                os.path.basename(books[tribe])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
