#!/usr/bin/env python3
"""The second translation engine: Claude, batched over numbered TSVs.

Same discipline the vision pass runs on: a batch file carries numbered
source lines, the reading agent writes one reply file in one go, and the
ingest accepts the reply only if its id set equals the request's --
a stranger id, a missing id or a duplicate rejects the whole batch,
because a silently mis-numbered translation lands on the wrong subtitle
and nothing downstream can tell. Accepted rows go into the shared MT
cache under engine "claude"; the reply files themselves are scratch.
"""
import os
import sys


def write_batches(items, direction, folder, size=100):
    """Write numbered request files; returns their paths.

    `items` is [(key, text)] -- keys are entry indexes. Empty texts are
    not sent for translation (the spec's no-speech rule).
    """
    todo = []
    for key, text in items:
        if text.strip():
            todo.append((key, text))
    os.makedirs(folder, exist_ok=True)
    paths = []
    batch = []
    for item in todo:
        batch.append(item)
        if len(batch) == size:
            paths.append(_write_one(folder, direction, len(paths) + 1,
                                    batch))
            batch = []
    if batch:
        paths.append(_write_one(folder, direction, len(paths) + 1, batch))
    return paths


def _write_one(folder, direction, number, batch):
    path = os.path.join(folder, "b%02d.%s.tsv" % (number, direction))
    with open(path, "w", encoding="utf-8") as handle:
        for key, text in batch:
            handle.write("%d\t%s\n" % (key, text))
    return path


def _read_rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            key, _, rest = line.partition("\t")
            rows.append((key.strip(), rest))
    return rows


def ingest_reply(request_path, reply_path, cache, direction, lang):
    """Validate a reply against its request, then fill the cache.

    The cache key is the *source* text (content-addressed), which is why
    the request file is read back here rather than trusting the reply.
    """
    request = {}
    for key, text in _read_rows(request_path):
        request[key] = text

    errors = []
    seen = {}
    for key, translation in _read_rows(reply_path):
        if key in seen:
            errors.append("duplicate id %s" % key)
            continue
        if key not in request:
            errors.append("id %s is not in %s"
                          % (key, os.path.basename(request_path)))
            continue
        seen[key] = translation
    for key in sorted(request):
        if key not in seen:
            errors.append("id %s has no reply line" % key)

    if errors:
        for message in errors[:20]:
            sys.stderr.write("  %s\n" % message)
        raise SystemExit("%d problem(s) in %s; nothing ingested"
                         % (len(errors), reply_path))

    for key in seen:
        cache.put("claude", direction, lang, request[key], seen[key])
    return len(seen)
