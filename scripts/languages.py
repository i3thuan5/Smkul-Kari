#!/usr/bin/env python3
"""族語別佮語言別ê代號對照表（頂層，兩爿語料公家用）。

正本是 `kithann/規範/族語及語言別名稱 - 族語名稱.csv`（族語別 → ISO
639／英文拼法）佮同目錄ê `- 語言別名稱.csv`（族語別下底ê變體 → 代號）。
兩份攏是 gitignore ê——換一台機器就無去，所以表愛綴 repo 走
（CLAUDE.md 明文）。規範若改，兩爿愛做伙改、做伙走測試。

放頂層ê理由佮 `datadirs.py` 仝一條：兩个語料攏用著，毋過兩爿攏無
擁有伊。本底伊蹛佇 `scripts/aiyalaeho/catalogue.py`，彼陣干焦《開會了》
對檔名剖語言別會用著；族語新聞這馬嘛愛填 `語言別代號` 矣，若叫 news
去 import aiyalaeho，依賴ê方向就顛倒去（這馬是 aiyalaeho → news）。

代號查袂出來ê時 SHALL 指名是佗一个，袂使留空嘛袂使掰一个——掰出來ê
標籤khǹg佇交付表，對別人是無意義ê。
"""
import re

from scripts.errors import PipelineError

# 人聽過才命名會著ê集數，等袂得ê時先按呢登記。代號用 `und`：彼是
# ISO 639-2／639-3 家己對「未確定語言」ê答案，毋是咱掰ê。
UNKNOWN = "（未知）"

# 族語別：中文 -> (目錄用ê英文拼法, ISO 639 三碼)
#
# 英文拼法沿節目目錄ê用字（SaySiyat、Pinuyumayan、Hla'alua 這幾个佮
# 別位無仝款），按呢兩个語料ê族語別欄才對得起來。太魯閣佮賽德克 ISO
# 歸做仝一个 trv，短期照 RFC 5646 私有標籤分做 trv-x-truku 佮 trv。
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
    # 規範寫「霧臺」，檔名寫「霧台」——查表進前正規化（見 `key`）。
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


def key(token):
    """One token, normalised for lookup: no brackets, no 語, 臺 as 台."""
    token = re.sub(r"[（(][^）)]*[）)]", "", token).strip()
    if token.endswith("語"):
        token = token[:-1]
    return token.replace("臺", "台")


def variety_owner(name):
    """The language a variety 名 belongs to, when it names one on its own.

    `98-東魯凱-無字幕.mp4` writes the variety where the language goes, so a
    reverse lookup is needed. It refuses a name claimed by two languages
    rather than picking one, though the standard has no such name today.
    """
    owners = []
    for language in sorted(VARIETIES):
        if key(name) in VARIETIES[language]:
            owners.append(language)
    if len(owners) == 1:
        return owners[0]
    return None


def _known(name):
    if name in LANGUAGES:
        return name
    raise PipelineError("毋捌 %r 這个族語別（有ê是：%s）"
                        % (name, "、".join(sorted(LANGUAGES))))


def english_for(language):
    """The spelling the delivered tables use for this 族語別."""
    return LANGUAGES[_known(language)][0]


def code_for(language, variety):
    """The language tag: a private variety tag, else the ISO 639 code.

    A variety the standard does not list -- `083-魯凱語-非霧台` is the one
    in the 開會了 batch -- keeps its wording in the 語言別 column and falls
    back to the language's own code. Inventing a tag would put a code in the
    delivered table that means nothing to anybody else.
    """
    table = VARIETIES.get(_known(language)) or {}
    if variety and key(variety) in table:
        return table[key(variety)]
    return LANGUAGES[language][1]


def _by_code():
    """代號 -> (族語別, 語言別)，語言別空字串表示族語級。"""
    found = {}
    for language in LANGUAGES:
        found[LANGUAGES[language][1]] = (language, "")
    for language in VARIETIES:
        for variety in VARIETIES[language]:
            code = VARIETIES[language][variety]
            # 「德鹿谷」佮「德路固」是仝一个代號ê兩款寫法，頭一个
            # 排著ê就算——兩个攏指仝一款話，揀佗一个攏無影響代號。
            found.setdefault(code, (language, variety))
    return found


def _resolve(code):
    found = _by_code().get(code)
    if found is None:
        raise PipelineError("毋捌 %r 這个語言別代號——代號愛出自對照表，"
                            "袂使掰一个" % code)
    return found


def language_of(code):
    """代號 -> 族語別(中)。"""
    return _resolve(code)[0]


def variety_of(code):
    """代號 -> 語言別字樣；族語級ê代號回空字串。"""
    return _resolve(code)[1]
