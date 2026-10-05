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

# 16 族以外、受訪者名條會出現ê族群：中文 -> (名條頂懸ê拼法, 代號)。
# 毋囥入 `LANGUAGES`——彼是「16 族」，機器翻譯逐族抓一本辭典，加一族
# 就去抓無存在ê辭典。規範 CSV 猶未收這幾族，規範若收，兩爿愛做伙改。
OTHER_GROUPS = {
    # 使用者裁定 2026-09-24：先用巴宰 ISO `pzh` 加私有標籤，照
    # trv-x-truku ê前例，佮巴宰分會開。
    # 出現過ê新聞（受訪者名條標 Kaxabu 抑是「噶哈巫族」）：
    #   20241222_357_晚間_Pinuyumayan_卑南  886 秒 黃美玉（南投縣噶哈巫
    #     文教協會理事長）、974 秒 周珈萱、1685 秒 潘雅綺（名條寫中文）
    #   20241228_363_晨間_Thau_邵  592 秒 黃美玉、662 秒 周珈萱
    "噶哈巫": ("Kaxabu", "pzh-x-kaxabu"),
    # 使用者裁定 2026-09-25：ISO 639-3 查 SIL 代碼表（含別名索引）。
    # 畢甘布：澳洲原住民，Bigambal／Bigambul／Pikambul，名條寫「Pikangcu」
    #   「畢甘布族」（20241207_342 午間、20241213_348 午間，莉亞·金-史密斯）。
    "畢甘布": ("Bigambul", "xbe"),
    # 西拉雅：名條寫「Silaya(西拉雅族)」「西拉雅族」（20241215_350 晚間、
    #   晨間，李淑媛）。
    "西拉雅": ("Siraya", "fos"),
    # 馬卡道：ISO 639-3 查無（Makatao／Makattao／Makatau／Makataw 攏無），
    #   代號就寫漢字（使用者裁定）。名條寫「Makataw(馬卡道族)」「Makatao」
    #   「Makatau」（20241222_357 晚間、20241224_359 晚間、20241229_364
    #   午間，林勝賢）。
    "馬卡道": ("Makatao", "馬卡道"),
    # 使用者裁定 2026-09-25：16 族以外ê族名毋免先問，查 SIL 代碼表寫入，
    # 收尾報告才列。
    # 道卡斯：SIL 代碼表查無 Taokas，比照馬卡道寫漢字。名條寫「Tawkase」
    #   （20211124_328 晚間 2439 秒）、「Taukat」（20211127_331 晨間 2734
    #   秒），攏是劉新苗。
    "道卡斯": ("Taokas", "道卡斯"),
    # 外國族群。毛利：20211113_317 晚間 2004、2039 秒名條「Māori」。
    "毛利": ("Māori", "mri"),
    # 彝：20211112_316 晚間 2637 秒名條「彝族」。ISO 無「彝語」總稱，
    #   `iii` 是 Nuosu（四川彝語），彝族上濟人講ê彼種。
    "彝": ("Yi", "iii"),
    # 多爾干：俄國泰梅爾，20220103 午間 2702、2779 秒名條「Dolgan」。
    "多爾干": ("Dolgan", "dlg"),
    # 祖魯：南非，20230622 2472 秒名條「祖魯族」。
    "祖魯": ("Zulu", "zul"),
    # 巴宰：20230701 前後名條「潘英傑 Pacay」。噶哈巫用 pzh 加私有標籤，
    #   巴宰本身就是 pzh。
    "巴宰": ("Pazeh", "pzh"),
    # 桑人（南非 San）：名條「Katrina Esau San」（2023-07 2240 秒）。桑人
    #   是好幾種語言ê族群，ISO 無單一代號，比照馬卡道寫漢字。Katrina
    #   Esau 本人講 Nǁng（ngh）。
    "桑": ("San", "桑"),
    # 大武壠：名條「潘鄔奈 大武壠族」（2022-01）。SIL 有 Taivoan。
    "大武壠": ("Taivoan", "tvx"),
    # 加拿大 Nlaka'pamux：名條「Dion Kaszas Nlaka'pamux」（2022-01）。
    #   SIL 是 Thompson River Salish。無通行漢譯，鍵照原文，莫家己翻。
    "Nlaka'pamux": ("Nlaka'pamux", "thp"),
    # 2023-07／08 名條ê外國族群，SIL 代碼表查；無通行漢譯ê鍵照原文。
    #   加拿大 Cree（Scott Wabano）、智利 Mapuche（Carmen・Montupil・
    #   Curin）、復活節島 Rapa Nui（Pepe・Pakarati；名條欄用空白分族名，
    #   鍵寫 SIL 名 Rapanui）、巴西 Tembé（Sergio Muti）、澳洲 Garingbal
    #   （Melissa Mills）。
    "Cree": ("Cree", "cre"),
    "Mapuche": ("Mapuche", "arn"),
    "Rapanui": ("Rapanui", "rap"),
    "Tembé": ("Tembé", "tqb"),
    "Garingbal": ("Garingbal", "xgi"),
    # 拍瀑拉：平埔族群，名條「張麗盆 拍瀑拉族」（2023-07-02 晚間 442 秒）。
    "拍瀑拉": ("Papora", "ppu"),
    # 蓋亞那 Carib：名條「Orin Fernandes Carib」等三人（2023-07）。SIL
    #   Galibi Carib `car` 是一般講 Carib 語彼種。
    "Carib": ("Carib", "car"),
    # 2023-08 名條ê外國族群，SIL 代碼表查。美國納瓦霍：「Jayne Sandoval
    #   納瓦霍族」（2023-08-27 晚間 2113 秒）。澳洲 Ngardi、Wiradjuri：
    #   「Dale Huddleston, Ngardi/Wiradjuri」（2023-08-28 晚間 2762 秒），
    #   一人兩族，名條欄干焦會當記一个，記頭一个。
    "納瓦霍": ("Navajo", "nav"),
    "Ngardi": ("Ngardi", "rxd"),
    "Wiradjuri": ("Wiradjuri", "wrh"),
    # 2023-09 名條。美國 Shoshone：「Gary McKinney Shoshone-Paiute」
    #   （20230916_259 午間 288 秒），一人兩族記頭一个，SIL 是 Shoshoni。
    #   印度／緬甸 Kuki：「Nengjahat Kuki」「Ngaineikim Kuki」（20230917_260
    #   晨間 2621、2792 秒），Kuki-Chin 一群語言，SIL 無單一代號，比照桑
    #   代號寫族名；無通行漢譯，鍵照原文。
    "Shoshone": ("Shoshone", "shh"),
    "Kuki": ("Kuki", "Kuki"),
    # 肯亞 Maasai：「Ole Iguanani Maasai」（20230920 前後 837 秒），SIL Masai。
    #   澳洲 Wakka Wakka：「Corey Appo Wakka Wakka」（20230922_265 晚間
    #   1151 秒），SIL Wakawaka；族名本身有空白。
    "Maasai": ("Maasai", "mas"),
    "Wakka Wakka": ("Wakka Wakka", "wkw"),
    # 加拿大 Nisga'a：「Sim'oogit Ni'isjoohl Nisga'a」（2023-09 名條第 65 批
    #   b65-s004 第 5 列，1070 秒），SIL Nisga'a；族名有撇號。
    "Nisga'a": ("Nisga'a", "ncg"),
    # 巴西 Tembé：「Sergio Muti Tembé  Tembé /Tenetehara」（2023-10 名條第
    #   66 批 b66-s006 第 18 列，2655 秒），SIL Tembé；Tenetehara 是別稱，
    #   別名寫佇 namebars.ALIASES。
    "Tembé": ("Tembé", "tqb"),
    # 玻利維亞 Aymara：「Marcelina Choque Aymara」「Maria Choque Aymara」
    #   （2024-02 名條第 70 批 b70-s070、s071），SIL 總稱 `aym`；仝兩人
    #   另一則印「Aymara cuku」，別名寫佇 namebars.ALIASES。
    "艾馬拉": ("Aymara", "aym"),
    # 2024-03 名條第 71 批ê外國族群。日本愛努：「富菜栄子 愛努族」「熊谷
    #   カネ 愛努族」（b71-s032、s040），SIL Ainu (Japan) `ain`。挪威薩米：
    #   「Mariela Idivuoma 薩米族」（b71-s079 1300 秒，NRK Sápmi 總編輯），
    #   ISO 639-3 無薩米總稱，比照彝用上濟人講ê北薩米 `sme`。
    "愛努": ("Ainu", "ain"),
    "薩米": ("Sami", "sme"),
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
