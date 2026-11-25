"""Which audio track the preview and the WAV take: the first audible one.

開會了 107's original file had digital silence on its first track
(-91 dB) and the programme on its second (-25 dB), with the player's
default flag on the silent one -- the file name even said 無聲音.
"Always take a:0" would have made a silent preview and a silent WAV.
Audible tracks measured -21 to -27 dB, silence -91, so -80 sits in a
wide gap.

Tracks are measured in order and the first audible one wins, so the
usual case costs one measurement. `measure(source, index)` is passed in;
the real one is `Meter().mean`, which also keeps the decoded
sample count the WAV acceptance needs.
"""
import re
import subprocess

SILENCE_DB = -80.0

MEAN = re.compile(r"mean_volume:\s*(-?[0-9.]+|-inf)\s*dB")
SAMPLES = re.compile(r"n_samples:\s*([0-9]+)")


class Choice:
    """The track picked, its whole-track mean level, and any problem."""

    def __init__(self, index, mean_db, problem=None):
        self.index = index
        self.mean_db = mean_db
        self.problem = problem

    def __repr__(self):
        return "Choice(%r, %r, %r)" % (self.index, self.mean_db, self.problem)


def pick(source, count, measure):
    """The first track louder than -80 dB on average.

    None of them: the preview still takes track 0 and `problem` says
    全部音軌靜音, which fails the WAV.
    """
    if count < 1:
        return Choice(0, None, "來源沒有任何音軌")
    first = None
    for index in range(count):
        level = measure(source, index)
        if index == 0:
            first = level
        if level is not None and level > SILENCE_DB:
            return Choice(index, level)
    return Choice(0, first, "全部音軌靜音")


def parse_mean_volume(stderr):
    """volumedetect's mean_volume in dB, or None when it printed none."""
    found = MEAN.search(stderr)
    if not found:
        return None
    if found.group(1) == "-inf":
        return float("-inf")
    return float(found.group(1))


def parse_samples(stderr):
    """volumedetect's n_samples for the instance that measured something.

    ffmpeg prints a second, empty instance first ("n_samples: 0"), so take
    the largest rather than the first.
    """
    best = None
    for found in SAMPLES.finditer(stderr):
        value = int(found.group(1))
        if best is None or value > best:
            best = value
    return best


class Meter:
    """`measure` for `pick`, remembering each track's decoded sample count.

    The volumedetect pass already decodes the whole track and prints
    n_samples; the WAV acceptance needs exactly that number, so keeping
    it saves decoding the track a second time.
    """

    def __init__(self, run=subprocess.run):
        self.run = run
        self.samples = {}

    def mean(self, source, index):
        stderr = _volumedetect(source, index, self.run)
        self.samples[index] = parse_samples(stderr)
        return parse_mean_volume(stderr)


def _volumedetect(source, index, run):
    done = run(["nice", "-n", "15", "ionice", "-c", "3",
                "ffmpeg", "-nostdin", "-hide_banner", "-i", source,
                "-map", "0:a:%d" % index, "-af", "volumedetect",
                "-f", "null", "-"],
               capture_output=True, text=True)
    return done.stderr


def mean_volume(source, index, run=subprocess.run):
    """Decode one whole track through volumedetect; its mean level."""
    return parse_mean_volume(_volumedetect(source, index, run))
