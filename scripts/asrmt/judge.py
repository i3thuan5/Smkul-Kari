#!/usr/bin/env python3
"""族華對應品質：材料、批次、收件、快取、合成。

The question this answers, per entry: are the Formosan line and the
Chinese subtitle the same sentence, well enough to train a translation
model on? Three grades -- 高／中／低 -- defined in `judge_prompt.md`,
which is the prompt and the definition at once.

**Two judges.** The first grades everything; whatever it grades 高 goes
to a second, and only if that one agrees is the entry 高. There is
nobody available who reads these languages, so the precision of 高 rests
on two independent models agreeing rather than on a person checking --
which is stated in the store's README rather than glossed over. Entries
the first judge grades 中 or 低 are not asked twice: a wrong 低 costs one
row of training data, a wrong 高 poisons the corpus.

**The cache key is content, never the entry number.** Re-projecting an
episode onto a new timeline renumbers everything -- the pilot's entry 304
became 309 -- so keying by number would silently attach yesterday's
judgments to different sentences. The key is everything the judge was
shown, the neighbouring subtitles included: change the material and it
is a different question, so it gets asked again.

**A batch is accepted whole or not at all.** Same rule as the vision
pass: id set equal, labels legal, or the whole file is rejected and
nothing is written. A half-accepted batch puts grades on the wrong
entries, and nothing downstream can tell.
"""
import json
import os

from scripts.errors import PipelineError

LABELS = ("高", "中", "低")
EMPTY_LABEL = "低"

# Bump when `judge_prompt.md` changes what is being asked: the version is
# part of the cache key, so answers given under the old definition stop
# counting rather than being quietly mixed in with the new ones.
PROMPT_VERSION = "v8"

FIRST = "sonnet"
SECOND = "fable"

# Batch files are named by judge, so a folder half-way through says who
# still owes a reply just by its listing.
PREFIX = {FIRST: "s", SECOND: "f"}

# The material columns, in the order the batch file writes them.
COLUMNS = ("formosan", "subtitle", "translation", "suspect",
           "before", "after")

# What goes in the `suspect` column when the translation is one of the
# service's canned outputs. See `materials`.
CANNED = "罐頭句，莫採信"

# Dictionary glosses the service emits instead of a translation. The
# repetition test misses these when they occur once, but they are
# recognisable on sight: they are linguistics terminology, which is
# what a wordlist in the training data looks like coming back out.
GLOSSES = ("屬格", "受格", "主格", "斜格", "標記", "男子名", "女子名",
           "人名", "地名", "助詞", "連接詞", "量詞", "詞綴", "前綴",
           "後綴", "重疊", "使動", "被動")


def is_gloss(text):
    """Is this a dictionary entry rather than a translation?

    Short and made of grammar words: a real subtitle translation is a
    sentence about the news, not a part-of-speech label. The length
    guard is what keeps a sentence that happens to mention 地名 out.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 12:
        return False
    # A semicolon in a short line separates senses -- that is how a
    # dictionary writes an entry (「年;歲」), not how anyone writes a
    # subtitle.
    if ";" in stripped or "；" in stripped:
        return True
    for gloss in GLOSSES:
        if gloss in stripped:
            return True
    return False


# 逐版留一份。快取逐筆判定攏記版本，彼个記號ê意思是「這筆是照彼
# 陣ê定義判ê」——定義無留，記號就無意義，判定嘛重現袂出來。本底
# 是一支檔案改幾若擺、逐擺蓋過去，磁碟頂干焦賰上尾彼版。
PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "judge_prompts")

# 走ê彼版：予 subagent 讀ê路徑固定佇遮，免逐擺改指示。
PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "judge_prompt.md")


def prompt_path(version):
    """Where one version's text lives."""
    return os.path.join(PROMPTS, version + ".md")


def kept_versions():
    """Every version whose text is on disk, oldest first."""
    if not os.path.isdir(PROMPTS):
        return []
    found = []
    for name in sorted(os.listdir(PROMPTS)):
        if name.endswith(".md"):
            found.append(name[:-len(".md")])
    return found


def prompt_text(version=None):
    """The judging definition -- the live one, or a named version."""
    path = PROMPT if version is None else prompt_path(version)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    """A field safe to put in a tab-separated column."""
    return text.replace("\t", " ").replace("\n", " ")


def materials(entries, translate, suspect=None):
    """What the judge is shown, one item per entry worth asking about.

    An entry with no recognised words, or no subtitle, is not asked
    about: there is nothing to compare, so it is 低 by definition and a
    request would be money spent on the empty string.

    The neighbours are the real neighbours in the episode, not the
    neighbours among the asked entries -- they are there so the judge can
    recognise a Formosan line that belongs to the sentence next door, and
    a skipped entry does not move that sentence.

    `suspect(translation) -> bool` marks a translation the judge should
    not lean on. The service does not say "I don't know" when it is out
    of its depth; it emits a canned sentence, the same text word for
    word across unrelated inputs. Measured over the whole cache, 21% of
    entries carry a translation that also appears for a different source
    line, and those entries are graded 高 half as often and 低 nearly
    twice as often. Telling the judge which ones they are costs nothing
    and takes a misleading hint off the table.
    """
    out = []
    for position, row in enumerate(entries):
        if not row["formosan"].strip() or not row["subtitle"].strip():
            continue
        before = ""
        after = ""
        if position > 0:
            before = entries[position - 1]["subtitle"]
        if position + 1 < len(entries):
            after = entries[position + 1]["subtitle"]
        rendered = translate(row["formosan"])
        marked = ""
        if is_gloss(rendered):
            marked = CANNED
        elif suspect is not None and suspect(rendered):
            marked = CANNED
        out.append({"index": row["index"],
                    "formosan": row["formosan"],
                    "subtitle": row["subtitle"],
                    "translation": rendered,
                    "suspect": marked,
                    "before": before, "after": after})
    return out


def write_batches(items, folder, prefix, size=100):
    """Write numbered request files; returns their paths."""
    if not items:
        return []
    os.makedirs(folder, exist_ok=True)
    paths = []
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            paths.append(_write_one(folder, prefix, len(paths) + 1, batch))
            batch = []
    if batch:
        paths.append(_write_one(folder, prefix, len(paths) + 1, batch))
    return paths


def _write_one(folder, prefix, number, batch):
    path = os.path.join(folder, "%s%02d.tsv" % (prefix, number))
    with open(path, "w", encoding="utf-8") as handle:
        for item in batch:
            fields = [str(item["index"])]
            for column in COLUMNS:
                fields.append(_flat(item[column]))
            handle.write("\t".join(fields) + "\n")
    return path


def _read_rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            key, _tab, rest = line.partition("\t")
            rows.append((key.strip(), rest))
    return rows


def ingest_reply(request_path, reply_path, cache, name, items):
    """Check a reply against its request, then fill the cache. Or refuse.

    Whole-batch acceptance is the point: a reply whose ids do not match
    the request exactly is one where some grade would land on an entry
    it was not about, and there is no way to tell which afterwards.
    """
    wanted = []
    for key, _rest in _read_rows(request_path):
        wanted.append(key)
    by_index = {}
    for item in items:
        by_index[str(item["index"])] = item

    errors = []
    seen = {}
    for key, label in _read_rows(reply_path):
        label = label.strip()
        if key in seen:
            errors.append("id %s 重複" % key)
            continue
        if key not in wanted:
            errors.append("id %s 毋是 %s 內底ê"
                          % (key, os.path.basename(request_path)))
            continue
        if label not in LABELS:
            errors.append("id %s ê標籤 %r 毋是 高／中／低" % (key, label))
            continue
        seen[key] = label
    for key in wanted:
        if key not in seen:
            errors.append("id %s 無回覆" % key)

    if errors:
        raise PipelineError(
            "%s 有 %d 條問題，整批無收：%s"
            % (os.path.basename(reply_path), len(errors),
               "；".join(errors[:10])))

    for key in seen:
        cache.put(name, by_index[key], seen[key])
    return len(seen)


class QualityCache(object):
    """Append-only JSONL, one file per judge, keyed by the material."""

    def __init__(self, folder, prompt=PROMPT_VERSION):
        self.folder = folder
        self.prompt = prompt
        self.entries = {}
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    self.entries[self._key_of(row)] = row["label"]

    def _key_of(self, row):
        """The key of a row read back from disk.

        A column added later is missing from the rows already written,
        so it reads as empty rather than raising -- the file is
        append-only and yesterday's rows are there for good. They cannot
        collide with anything: a row written before the column existed
        carries an older `prompt` version, which is part of the key.
        """
        key = [row["judge"], row["prompt"]]
        for column in COLUMNS:
            key.append(row.get(column, ""))
        return tuple(key)

    def key(self, name, item):
        key = [name, self.prompt]
        for column in COLUMNS:
            key.append(item[column])
        return tuple(key)

    def get(self, name, item):
        return self.entries.get(self.key(name, item))

    def put(self, name, item, label):
        if label not in LABELS:
            raise PipelineError("標籤 %r 毋是 高／中／低" % label)
        self.entries[self.key(name, item)] = label
        row = {"judge": name, "prompt": self.prompt, "label": label}
        for column in COLUMNS:
            row[column] = item[column]
        path = os.path.join(self.folder, name + ".jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False,
                                    sort_keys=True) + "\n")


def final_label(first, second):
    """The grade of record. None means the second judge has not spoken.

    高 needs both; anything else stands on the first judge alone.
    """
    if first is None:
        return None
    if first != "高":
        return first
    if second is None:
        return None
    if second == "高":
        return "高"
    return "中"


def pending(items, cache, name):
    """The items this judge still has to be asked about.

    The second judge sees only what the first graded 高 -- that is the
    only place a second opinion changes anything.
    """
    left = []
    for item in items:
        if name == FIRST:
            if cache.get(FIRST, item) is None:
                left.append(item)
            continue
        if cache.get(FIRST, item) != "高":
            continue
        if cache.get(name, item) is None:
            left.append(item)
    return left


def verdicts(entries, cache, items):
    """{entry index: 高|中|低} for a whole episode, or say what is missing.

    `items` is what `materials` produced for these entries -- passed in
    rather than rebuilt, so the grade is looked up against exactly the
    material the judge was shown. Entries with nothing to compare are 低
    without anyone being asked.
    """
    out = {}
    for row in entries:
        if not row["formosan"].strip() or not row["subtitle"].strip():
            out[row["index"]] = EMPTY_LABEL
    for item in items:
        label = final_label(cache.get(FIRST, item), cache.get(SECOND, item))
        if label is None:
            raise PipelineError(
                "條目 %d 猶未判定齊全（%s=%s、%s=%s）"
                % (item["index"], FIRST, cache.get(FIRST, item),
                   SECOND, cache.get(SECOND, item)))
        out[item["index"]] = label
    return out
