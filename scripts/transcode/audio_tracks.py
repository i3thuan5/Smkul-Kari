"""Decide, from audio fingerprints alone, whether an archive is faithful
and which of its tracks are worth keeping.

Pure functions, no I/O. The fingerprints come from `encode_master.sh`,
which computes the source ones during the encode itself (one read of the
source) and the archive ones afterwards off the local SSD.

Two callers share this: `archive_batch.py` (族語新聞封存) and
`tools/mxf2mkv/` (隨身硬碟批次). The logic lives here rather than in the
shell script because deciding "which of N tracks are duplicates" is a
nested loop that bash can express but not test -- and getting it wrong
means silently dropping a track that carried different audio. Measured
2026-09-06 over the 63 archived episodes: 35 had one track, 28 had two
that were *not* bit-identical. Two tracks carrying different content
(主聲道／國際聲, 族語／華語) is a standard broadcast practice, so
"they look the same, drop one" is not a call this code may make on its
own -- it compares bit for bit.
"""


class Verdict:
    """What the fingerprints say about one episode's audio.

    bit_exact   every archive track reproduces its source track exactly
    mismatched  0-based indices of the tracks that do not (empty if ok)
    keep        0-based indices to carry into the final archive
    summary     one sentence for the report a person reads
    """

    def __init__(self, bit_exact, mismatched, keep, summary):
        self.bit_exact = bit_exact
        self.mismatched = mismatched
        self.keep = keep
        self.summary = summary

    def __repr__(self):
        return ("Verdict(bit_exact=%r, mismatched=%r, keep=%r, summary=%r)"
                % (self.bit_exact, self.mismatched, self.keep, self.summary))


def _mismatches(source, encoded):
    """0-based indices where the archive does not reproduce the source.

    A differing track count is itself a mismatch: the encode was supposed
    to carry every source track through, so a missing one is the encode
    step having gone wrong, not a judgement call to make here. The extra
    or missing positions are reported alongside any that differ.
    """
    out = []
    for index in range(max(len(source), len(encoded))):
        if index >= len(source) or index >= len(encoded):
            out.append(index)
        elif source[index] != encoded[index]:
            out.append(index)
    return out


def _keep(fingerprints):
    """Indices to keep: the first of each group of identical tracks.

    The first, not the last, so the kept tracks stay in source order.
    """
    seen = {}
    out = []
    for index, value in enumerate(fingerprints):
        if value in seen:
            continue
        seen[value] = index
        out.append(index)
    return out


def _summary(fingerprints, keep):
    total = len(fingerprints)
    if total == 1:
        return "一軌"
    if total == 2:
        if len(keep) == 1:
            return "兩軌相同，留一軌"
        return "兩軌不同，兩條都留"
    # 三軌以上寫出軌數。舊版只 map a:0 佮 a:1，第三軌恬恬無去、
    # 連一句話都無，所以遮特別共數目講出來。
    if len(keep) == total:
        return "%d 軌，攏無仝，%d 軌全留" % (total, total)
    return "%d 軌，其中 %d 軌相同，留 %d 軌" % (
        total, total - len(keep) + 1, len(keep))


def _mismatch_summary(mismatched):
    numbers = []
    for index in mismatched:
        numbers.append("第 %d 軌" % (index + 1))
    return "音訊對袂起來：%s" % "、".join(numbers)


def decide(source, encoded):
    """Compare the two fingerprint lists and say what to do.

    `source` and `encoded` are lists of fingerprint strings, one per audio
    track, in stream order.

    When verification fails there is no `keep` answer: which tracks are
    duplicates of each other is a question about audio the archive was
    supposed to contain, and it does not contain it. Answering anyway
    would be deciding what to throw away from data already known to be
    wrong.
    """
    mismatched = _mismatches(source, encoded)
    if mismatched:
        return Verdict(False, mismatched, [], _mismatch_summary(mismatched))
    keep = _keep(encoded)
    return Verdict(True, [], keep, _summary(encoded, keep))
