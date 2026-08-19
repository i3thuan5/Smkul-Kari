#!/usr/bin/env python3
"""Where data may live, and the guards that keep arguments inside it.

Split out of `scripts.news.paths` so both sides can use it: `scripts/ocr/`
is a reusable engine that deliberately does not depend on `scripts/news/`
(the news orchestration), and inverting that just to validate a path would
have been the wrong trade. What lives here is repo layout plus argument
validation -- facts neither side owns. Corpus-specific paths (the store's
stage folders, the inventory, the catalogue) stay in `scripts.news.paths`.
"""
import os
import re
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Everything regenerable lives under kithann/; everything canonical under
# Kari-SRT/ (the data submodule).
KITHANN = os.path.join(ROOT, "kithann")
KARI = os.path.join(ROOT, "Kari-SRT")

# The only places a path-shaped CLI argument may legitimately point.
# Deliberately NOT the whole repo -- scripts/ and openspec/ are code and
# specs, not data, and nothing should be reading or writing episodes there.
# The temp dir is in because rebuild and asrmt synthesise work dirs there;
# it is read from tempfile rather than hard-coded so TMPDIR is honoured.
ALLOWED_ROOTS = (KITHANN, KARI, tempfile.gettempdir())


_PATH_COMPONENTS = re.compile(r"[/\\]|\.\.")


def check_name(name, kind="name"):
    """Refuse a name-like CLI argument that carries path components.

    Work dirs and store files are all built as base folder + name; a name
    holding a separator or ".." escapes the base and turns a mistyped (or
    injected) argument into an arbitrary read or write. Validate at the
    entry point, before the name reaches any os.path.join.

    The stripped form is built first and then compared, rather than the
    stripped form being returned: a name that needed stripping stops the
    run. Silently rewriting one would be worse than the typo it came from
    -- the inventory is read, edited and written back by `publish`,
    `add_episodes` and `build_inventory`, so a quietly corrected name
    would be written into the store as if it had always said that.
    """
    # None is what a hand-edited `"slug": null` in the inventory hands over;
    # it is a missing name, not a name carrying path components, and the
    # message has to say which so the file gets looked at.
    if not name:
        raise SystemExit("%s 無值" % kind)
    cleaned = _PATH_COMPONENTS.sub("", name)
    if cleaned != name or name == ".":
        raise SystemExit("%s %r 帶路徑成分，拒絕" % (kind, name))
    return cleaned


def check_under(path, kind="path", roots=None):
    """Refuse a path argument that lands outside the data folders.

    Guards against a mistyped (or injected) path argument turning a tool
    that edits one episode into one that edits something else entirely --
    `refine_cues` rewrites cues.json in place, so a wrong target destroys
    a timeline. Compares the realpath, so `..` and symlinks cannot walk
    out, and the base always carries a trailing separator: without it
    "/x/kithann-secret" reads as being inside "/x/kithann".

    Returns `path` unchanged (not the resolved form) so call sites keep
    writing exactly the path the caller named.
    """
    resolved = os.path.realpath(path)
    for base in (roots or ALLOWED_ROOTS):
        base = os.path.realpath(base)
        if resolved == base or resolved.startswith(base + os.sep):
            return path
    raise SystemExit(
        "%s %r 毋佇資料資料夾內底（准的是 kithann/、Kari-SRT/、暫存目錄）"
        % (kind, path))
