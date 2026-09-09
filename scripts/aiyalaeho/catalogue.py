#!/usr/bin/env python3
"""Which episode is this file? The file name is the whole answer.

    python3 -m scripts.aiyalaeho.catalogue -n      # 報告，無寫入
    python3 -m scripts.aiyalaeho.catalogue         # 登記規夾
    python3 -m scripts.aiyalaeho.catalogue 068-阿美語-秀姑巒-雙語字幕.mp4
    python3 -m scripts.aiyalaeho.catalogue --language 119-混雜.mp4=布農

The news side plans a batch out of `ilrdf-corpus.csv`. That does not work
here: the catalogue's 46 rows for this programme carry no 年度, no
播出日期, no 播出時段 and no 族語別 -- 43 of them say 有無影片=否 while the
server holds the video, and two episodes the folder does have (068, 164)
have no row at all. The catalogue is not wrong so much as older than the
delivery, and it is not ours to correct.

The file names, on the other hand, say everything the pipeline needs:

    068-阿美語-秀姑巒-雙語字幕.mp4
     |      |       |      `-- subtitle state; never enters a field
     |      |       `--------- the variety, when the name gives one
     |      `----------------- the language
     `------------------------ the episode number

So the folder listing *is* the episode list, and this module turns one
name into one inventory entry. What it will not do is guess: three of the
44 files on the server are older uploads named `116ALL_無字.mp4`,
`119-混雜.mp4` and `122-混雜.mp4`, which name no language at all. Those are
reported and skipped, to be named with `--language`. Skipping rather than
aborting is deliberate: one unreadable name must not hold up the forty
that are readable.

Naming one rarely means watching it. Every episode paints its own language
card into the top-right corner -- the island of Taiwan, the `a'iyalaeho:`
title, and under them the language in its own spelling above the Chinese
`〇〇族`. One frame carries it:

    ffmpeg -ss 25 -i VIDEO -frames:v 1 -vf crop=340:260:1580:40 card.png

Two files with a language in the name confirm the card says what it looks
like it says: 123 reads `Truku 太魯閣族` and 107 reads `Hla'alua 拉阿魯哇族`.
119 and 122 both read `Bunun 布農族`, and that is how they were named --
their `混雜` is about the speech, not the subtitles, which are the ordinary
two rows on the ordinary band.

116 is the one the card does not rescue. Twenty frames spanning all 2880
seconds show that corner empty; it carries no subtitles either, and the
transcripts beside the videos on the server stop at episode 045 on a
different numbering. Its language has to be listened for.
"""
import argparse
import json
import os
import re
import sys

from scripts.aiyalaeho import paths
from scripts.errors import PipelineError

PROGRAMME = "開會了"

# Where the delivered table records a source file, and the form the server
# takes under its own root.
CORPUS_DIR = "ilrdf-corpus/族語節目/開會了/"

VIDEO_EXT = ".mp4"

# 族語別：中文 -> (目錄用ê英文拼法, ISO 639 三碼)
#
# 英文拼法沿 `ilrdf-corpus.csv` ê用字（SaySiyat、Pinuyumayan、Hla'alua
# 這幾个佮別位無仝款），按呢兩个語料ê族語別欄才對得起來。代號照
# `kithann/規範/族語及語言別名稱 - 族語名稱.csv`：太魯閣佮賽德克 ISO
# 歸做仝一个 trv，短期照 RFC 5646 私有標籤分做 trv-x-truku 佮 trv。
# 「（未知）」：人聽過才命名會著ê集數，等袂得ê時先按呢登記。
# 116 就是——伊無語言卡（規片 2880 秒抽 20 格，右頂角彼位攏空ê）、
# 嘛無燒印字幕，畫面頂懸無半个線索；伺服器仝層彼份上字文稿是
# 001–045 另外一套編號，佮 068–164 對袂起來。伊佮 088／090／098
# 仝款是「無字幕」ê異常集，袂產 SRT，所以族語別是啥其實無影響
# 交付——毋過**無登記ê話，44 支影片ê帳會少一支**。使用者裁定
# 2026-09-08。
#
# 代號用 `und`：彼是 ISO 639-2／639-3 家己對「未確定語言」ê答案，
# 毋是咱掰ê（看下跤 `code_for` ê註解）。人聽過了後改做真ê族語別，
# 跑一擺 `catalogue --language 116ALL_無字.mp4=<族語別中>` 就好。
UNKNOWN = "（未知）"

LANGUAGES = {
    UNKNOWN: ("Unknown", "und"),
    "阿美": ("Amis", "ami"),
    "泰雅": ("Atayal", "tay"),
    "排灣": ("Paiwan", "pwn"),
    "布農": ("Bunun", "bnn"),
    "卑南": ("Pinuyumayan", "pyu"),
    "魯凱": ("Rukai", "dru"),
    "鄒": ("Cou", "tsu"),
    "賽夏": ("SaySiyat", "xsy"),
    "雅美": ("Yami", "tao"),
    "邵": ("Thau", "ssf"),
    "噶瑪蘭": ("Kavalan", "ckv"),
    "撒奇萊雅": ("Sakizaya", "szy"),
    "太魯閣": ("Truku", "trv-x-truku"),
    "賽德克": ("Seediq", "trv"),
    "拉阿魯哇": ("Hla'alua", "sxr"),
    "卡那卡那富": ("Kanakanavu", "xnb"),
}

# 語言別（族語別下底ê變體）：族語別 -> {字樣: 代號}
#
# 正本是 `kithann/規範/族語及語言別名稱 - 語言別名稱.csv`，彼份是
# gitignore ê——換一台機器就無去，所以表囥佇遮，規範若改就改這搭閣走測試。
VARIETIES = {
    "阿美": {
        "南勢": "ami-x-iams", "秀姑巒": "ami-x-skl",
        "海岸": "ami-x-pswl", "馬蘭": "ami-x-frng",
        "恆春": "ami-x-pld",
    },
    "泰雅": {
        "賽考利克": "tay-x-sql", "澤敖利": "tay-x-sul",
        "四季": "tay-x-cql", "宜蘭澤敖利": "tay-x-kls",
        "汶水": "tay-x-mtuw", "萬大": "tay-x-plngw",
    },
    "排灣": {
        "東排灣": "pwn-x-kcdsn", "北排灣": "pwn-x-vnrn",
        "中排灣": "pwn-x-pnvn", "南排灣": "pwn-x-ynvl",
    },
    "布農": {
        "卓群": "bnn-x-td", "卡群": "bnn-x-bkh",
        "丹群": "bnn-x-vtn", "巒群": "bnn-x-bnz",
        "郡群": "bnn-x-isbk",
    },
    "卑南": {
        "南王": "pyu-x-pym", "知本": "pyu-x-ktrp",
        "西群": "pyu-x-mkzy", "建和": "pyu-x-ksvk",
    },
    # 規範寫「霧臺」，檔名寫「霧台」——查表進前正規化（見 _key）。
    "魯凱": {
        "東魯凱": "dru-x-trmk", "霧台": "dru-x-ngdr",
        "大武": "dru-x-lbw", "多納": "dru-x-kgdv",
        "茂林": "dru-x-tldr", "萬山": "dru-x-opnh",
    },
    # 檔名寫「德路固」，規範寫「德鹿谷賽德克語」——仝一个，賽德克底下ê
    # 變體。莫佮「太魯閣語」（trv-x-truku）濫做伙：兩爿 ISO 碼相仝，
    # 毋過是無仝ê語言。
    "賽德克": {
        "都達": "trv-x-td", "德固達雅": "trv-x-tgdy",
        "德鹿谷": "trv-x-trk", "德路固": "trv-x-trk",
    },
}


def _variety_owner(name):
    """The language a variety名 belongs to, when it names one on its own.

    `98-東魯凱-無字幕.mp4` writes the variety where the language goes, so a
    reverse lookup is needed. It refuses a name claimed by two languages
    rather than picking one, though the standard has no such name today.
    """
    owners = []
    for language in sorted(VARIETIES):
        if name in VARIETIES[language]:
            owners.append(language)
    if len(owners) == 1:
        return owners[0]
    return None


def _key(token):
    """One token, normalised for lookup: no brackets, no 語, 臺 as 台."""
    token = re.sub(r"[（(][^）)]*[）)]", "", token).strip()
    if token.endswith("語"):
        token = token[:-1]
    return token.replace("臺", "台")


def _tokens(stem):
    """(episode, [token…]) from a file stem, or (None, []) if unnumbered."""
    # 尾溜ê全形註記（「（講中文居多）」）毋是檔名ê一部份，先剁掉。
    stem = re.sub(r"（[^）]*）\s*$", "", stem).strip()
    found = re.match(r"([0-9]{1,3})[-_ ]*(.*)$", stem)
    if not found:
        return None, []
    episode = str(int(found.group(1)))
    rest = []
    for token in re.split(r"[-_]", found.group(2)):
        if token.strip():
            rest.append(token.strip())
    return episode, rest


def _language_of(tokens):
    """(語言 index, 族語別中, 語言別字樣) -- the first token that names one."""
    for index, token in enumerate(tokens):
        key = _key(token)
        if key in LANGUAGES:
            return index, key, ""
        owner = _variety_owner(key)
        if owner:
            return index, owner, key
    return -1, "", ""


def _variety_after(tokens, index, language):
    """The variety named after the language token, or "".

    Everything that carries 字幕 is the subtitle state (雙語字幕、無字幕、
    僅華語字幕) and never a variety; the first token that is not is.
    """
    for token in tokens[index + 1:]:
        if "字幕" in token:
            continue
        return _key(token)
    return ""


# The subtitle-state wording that means "this episode cannot go through
# the two-row bilingual pipeline", and what to record as the reason.
# 雙語字幕 is the normal path and yields no reason at all.
BILINGUAL = "雙語字幕"
SUBTITLE_STATE = {
    "無字幕": "無字幕",
    # `116ALL_無字.mp4`, one of the older uploads, writes the short form.
    "無字": "無字幕",
    "僅華語字幕": "僅華語字幕",
}


def subtitle_state(tokens):
    """Why this file cannot be delivered as a bilingual episode, or "".

    The broadcaster writes it into the file name, and for the four
    episodes that carry one it is the whole answer -- decisive, repeatable
    and testable, where a hand-kept note would need somebody to remember.
    Measurement cannot replace it: 083's single Chinese row measures as a
    perfectly good subtitle band, so only the name says it has no Formosan
    text.

    An unrecognised 字幕 wording is returned as-is rather than assumed to
    be normal: it is not the bilingual form, so it is not the normal path,
    and recording what the name actually says is the honest default.
    """
    for token in tokens:
        key = _key(token)
        if key in SUBTITLE_STATE:
            return SUBTITLE_STATE[key]
        if "字幕" in key:
            if key == BILINGUAL:
                return ""
            return key
    return ""


def _probe_duration(path):
    """Seconds, straight from the container.

    Imported inside the function so that registering an episode -- a
    listing and some string work -- does not drag numpy and the rest of
    the decoding stack in at import time. The news side already has this
    exact call; a third copy would be one more place to keep in step.
    """
    from scripts.news.refine_cues import probe_duration
    return probe_duration(path)


def source_path(entry_or_name):
    """The local copy of the video, for the one step that must open it."""
    name = entry_or_name
    if isinstance(entry_or_name, dict):
        name = entry_or_name.get("file") or os.path.basename(
            entry_or_name["video"])
    return os.path.join(paths.SOURCE, os.path.basename(name))


def code_for(language, variety):
    """The language tag: a private variety tag, else the ISO 639 code.

    A variety the standard does not list -- `083-魯凱語-非霧台` is the one
    in this batch -- keeps its wording in the 語言別 column and falls back
    to the language's own code. Inventing a tag would put a code in the
    delivered table that means nothing to anybody else.
    """
    table = VARIETIES.get(language) or {}
    if variety and variety in table:
        return table[variety]
    return LANGUAGES[language][1]


def parse(file_name, language="", probe=None):
    """(entry, problem) for one video file name.

    `language` is a person's answer for a file that names none -- the three
    older uploads on the server. It is checked against the language table
    rather than trusted, so a typo fails loudly instead of creating an
    episode nobody can find.

    `probe` reads a video's length; it is injected so the tests never open
    a file, and so that only the episodes that need it get opened.
    """
    if language and language not in LANGUAGES:
        raise PipelineError(
            "毋捌 %r 這个族語別（有ê是：%s）"
            % (language, "、".join(sorted(LANGUAGES))))

    stem = os.path.splitext(os.path.basename(file_name))[0]
    episode, tokens = _tokens(stem)
    if episode is None:
        return None, "檔名開頭無集數，命名袂出來：%s" % file_name

    index, found, variety = _language_of(tokens)
    if index < 0:
        if not language:
            return None, ("檔名內底揣無族語別，愛人看過影片才會當命名"
                          "（用 --language 指定）：%s" % file_name)
        found = language
    else:
        if language:
            found = language
        if not variety:
            variety = _variety_after(tokens, index, found)

    english = LANGUAGES[found][0]
    entry = {
        "file": os.path.basename(file_name),
        "video": CORPUS_DIR + os.path.basename(file_name),
        "srt_name": "%s_%03d_%s_%s" % (paths.KEY_PREFIX[:-1], int(episode),
                                       english, found),
        "節目名稱": PROGRAMME,
        "集數": episode,
        "族語別(英)": english,
        "族語別(中)": found,
        "語言別": variety,
        "語言代號": code_for(found, variety),
        # Registered, not delivered. The store's claim is that it can
        # rebuild whatever it names, and there is nothing to rebuild from
        # yet; `publish` clears the flag once the batch is finished.
        "pending": True,
    }
    reason = subtitle_state(tokens)
    if reason:
        # Only these carry the two extra fields: a bilingual episode's
        # length comes from its timeline in 1-cues/, and adding an empty
        # column to forty entries would be a column that means nothing.
        entry["理由"] = reason
        entry["影片長度秒"] = (probe or _probe_duration)(source_path(entry))
    return entry, ""


def resolve(file_names, languages=None, probe=None):
    """([entry…], [(file name, problem)…]) for a whole folder listing."""
    languages = languages or {}
    entries = []
    skipped = []
    for name in file_names:
        entry, problem = parse(name, languages.get(os.path.basename(name),
                                                   ""), probe)
        if problem:
            skipped.append((os.path.basename(name), problem))
        else:
            entries.append(entry)
    return entries, skipped


def merge(planned, existing):
    """Fold a plan into the inventory without touching what is there.

    An episode already registered is left exactly as it is: it may have
    been named by hand after somebody watched it, and a fresh listing does
    not know that.
    """
    known = set()
    for entry in existing:
        known.add(entry["srt_name"])
    merged = list(existing)
    added = []
    for entry in planned:
        if entry["srt_name"] in known:
            continue
        known.add(entry["srt_name"])
        merged.append(entry)
        added.append(entry)
    return merged, added


def annotate(entries, named=None, probe=None):
    """Fill in `理由` and `影片長度秒` where they are missing.

    `merge()` leaves a registered entry exactly as it is -- that is what
    protects a name somebody corrected by hand -- so bringing the four
    already-registered episodes up to date needs a path of its own. This
    one writes those two fields and touches nothing else, so the diff
    lands on the two lines it should.

    `named` is `(srt_name, reason)`: the batch uses it when the band check
    or a person, rather than the file name, is what decided. A reason is
    never overwritten -- changing one is a person's job, and doing it by
    hand is the point at which somebody notices.

    Returns [(srt_name, field, value)…] -- what actually changed, so the
    caller can print it and skip writing when nothing did.
    """
    probe = probe or _probe_duration
    wanted = None
    if named is not None:
        wanted, reason = named
        if not str(reason).strip():
            raise PipelineError(
                "--annotate ê理由袂使是空ê：欲寫啥理由愛講出來，"
                "親像 '%s=無字幕'" % wanted)
        if not _has(entries, wanted):
            raise PipelineError("inventory 內底無 %s 這集" % wanted)

    changed = []
    for entry in entries:
        name = entry["srt_name"]
        if wanted is not None and name != wanted:
            continue
        if not entry.get("理由"):
            found = reason if wanted is not None else _reason_of(entry)
            if found:
                entry["理由"] = found
                changed.append((name, "理由", found))
        if entry.get("理由") and not entry.get("影片長度秒"):
            seconds = probe(source_path(entry))
            entry["影片長度秒"] = seconds
            changed.append((name, "影片長度秒", seconds))
    return changed


def _has(entries, srt_name):
    for entry in entries:
        if entry["srt_name"] == srt_name:
            return True
    return False


def _reason_of(entry):
    """What this entry's own file name says, or ""."""
    stem = os.path.splitext(entry.get("file")
                            or os.path.basename(entry["video"]))[0]
    _episode, tokens = _tokens(stem)
    return subtitle_state(tokens)


def write(entries, path=None):
    """Write the inventory back, entries in registration order."""
    target = path or paths.INVENTORY
    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
    return target


def listing(folder=None, only=""):
    """The source folder's videos, sorted by episode number."""
    source = folder or paths.SOURCE
    if not os.path.isdir(source):
        raise PipelineError("揣無來源資料夾 %s" % source)
    names = []
    for name in os.listdir(source):
        if not name.lower().endswith(VIDEO_EXT):
            continue
        if only and not re.search(only, name):
            continue
        names.append(name)

    def order(name):
        episode, _tail = _tokens(os.path.splitext(name)[0])
        return (int(episode) if episode else 0, name)

    names.sort(key=order)
    return names


def _overrides(pairs):
    """--language 119-混雜.mp4=布農 -> {"119-混雜.mp4": "布農"}."""
    out = {}
    for pair in pairs or []:
        name, sep, language = pair.partition("=")
        if not sep:
            raise PipelineError(
                "--language 愛寫做 <檔名>=<族語別中>，親像"
                " 119-混雜.mp4=布農；收著ê是 %r" % pair)
        out[name.strip()] = language.strip()
    return out


def _annotate_cli(args):
    """`--annotate`: bring existing entries up to date, print what moved."""
    named = None
    if args.annotate:
        name, sep, reason = args.annotate.partition("=")
        if not sep:
            raise PipelineError(
                "--annotate 愛寫做 <srt_name>=<理由>，親像 "
                "'開會了_106_Paiwan_排灣=無字幕'；收著ê是 %r" % args.annotate)
        named = (paths.check_srt_name(name.strip()), reason.strip())

    entries = paths.load_inventory()
    changed = annotate(entries, named=named)
    for srt_name, field, value in changed:
        print("set   %-30s %s = %s" % (srt_name, field, value))
    if changed and not args.dry_run:
        write(entries)
    print("\n改著 %d 筆欄位%s"
          % (len(changed), "" if not args.dry_run else "（試跑，無寫入）"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("videos", nargs="*",
                    help="檔名（無寫就是規个來源資料夾）")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="報告欲登記啥，毋寫入 inventory")
    ap.add_argument("--only", default="",
                    help="干焦檔名合這个 regex ê")
    ap.add_argument("--language", action="append", metavar="檔名=族語別",
                    help="人判過ê族語別，予檔名講無ê彼幾支用")
    ap.add_argument("--annotate", nargs="?", const="", default=None,
                    metavar="srt_name=理由",
                    help="補既有條目ê「理由」佮「影片長度秒」；無寫參數"
                         "就是照檔名補規份，寫 srt_name=理由 就是指名"
                         "（量測抑是人判ê結果按呢寫入）")
    args = ap.parse_args(argv)

    if args.annotate is not None:
        return _annotate_cli(args)

    names = args.videos or listing(only=args.only)
    entries, skipped = resolve(names, _overrides(args.language))

    existing = []
    if os.path.exists(paths.INVENTORY):
        existing = paths.load_inventory()
    merged, added = merge(entries, existing)

    for entry in added:
        print("plan  %-30s %s" % (entry["srt_name"], entry["file"]))
    for name, problem in skipped:
        print("SKIP  %-30s %s" % (name, problem))

    if not args.dry_run and added:
        write(merged)
    print("\n登記 %d 集%s，跳過 %d 支；inventory 這馬有 %d 集"
          % (len(added), "" if not args.dry_run else "（試跑，無寫入）",
             len(skipped), len(merged)))
    if skipped:
        print("跳過ê看過影片了後，用 --language <檔名>=<族語別中> 補登記。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
