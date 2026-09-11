#!/usr/bin/env python3
"""節目目錄ê共同欄位，佮驗伊ê不變量（頂層，兩爿語料公家用）。

六張表（兩个語料ê `smkul.csv`、《開會了》ê字幕版型異常表、句對表、兩張
語言檢查表）攏用仝一組欄位起頭，所以「前七欄是啥、按怎驗」愛有一个
所在講，袂使六位各寫一份。

`smkul.csv` 這馬是**輸入**毋是產出——內容人維護ê，逐 byte 重算比對無
意義矣。改做不變量檢查：逐 byte 會講「smkul.csv 對袂起來」，不變量會
講「第 412 逝ê `語言別代號` `amis` 無佇對照表內」。真正無去ê干焦
「有人改一格合法ê值」，彼本底就是人維護表格會當做ê代誌。
"""
import os
import re

from scripts import languages
from scripts.errors import PipelineError

# 六張表共同ê開頭欄位。集識別彼幾欄逐張無仝（新聞加年度佮播出日期），
# 插佇 `節目名稱` 後壁，賰ê逐張相仝、順序相仝。
HEAD_BEFORE = ("成果檔名", "節目名稱")
HEAD_AFTER = ("族語別(英)", "族語別(中)", "語言別", "語言別代號")

NEWS_KEYS = ("年度", "集數", "播出日期")
EPISODE_KEYS = ("集數",)

# 節目名稱 → 播出時段。量過 983 逝，一對一、零例外，而且時段本底就
# 佇 `成果檔名` 內底矣——仝一件代誌三份拷貝，留一份就好。
SLOTS = {
    "午間族語新聞": "午間",
    "晚間族語新聞": "晚間",
    "晨間族語新聞": "晨間",
}

AIYALAEHO = "開會了"


def head(keys):
    """The leading columns a table with these episode-identifying keys has."""
    return HEAD_BEFORE + tuple(keys) + HEAD_AFTER


def slot_of(programme):
    """新聞ê播出時段，對節目名稱推。

    推袂出來ê時 SHALL 指名彼一逝，袂使推一个空字串傳落去——空ê時段
    會去組出一个無人揣會著ê成果檔名。
    """
    if programme in SLOTS:
        return SLOTS[programme]
    raise PipelineError("節目名稱 %r 對袂著任何一个播出時段（有ê是：%s）"
                        % (programme, "、".join(sorted(SLOTS))))


def srt_name_of(row):
    """這一逝ê `成果檔名`，對同逝ê識別欄推。

    推導 SHALL NOT 看這集敢已經處理過——一逝一建立就有名，猶未切 cue
    ê集數嘛仝款。
    """
    number = "%03d" % int(row["集數"])
    english = row["族語別(英)"]
    chinese = row["族語別(中)"]
    if row["節目名稱"] == AIYALAEHO:
        return "%s_%s_%s_%s" % (AIYALAEHO, number, english, chinese)
    date = row["播出日期"].replace("-", "")
    return "%s_%s_%s_%s_%s" % (date, number, slot_of(row["節目名稱"]),
                               english, chinese)


_NEWS_NAME = re.compile(r"^\d{8}_\d{3}_[^_]+_[^_]+_[^_]+$")
_AIYALAEHO_NAME = re.compile(r"^開會了_\d{3}_[^_]+_[^_]+$")


def name_is_legal(name):
    """檔名合毋合規格——集數愛補三碼，日期愛八碼。"""
    return bool(_NEWS_NAME.match(name) or _AIYALAEHO_NAME.match(name))


def row_problems(rows, source_column="原始影片檔案位置"):
    """逐逝ê不變量。回一份「第幾逝、按怎毋著」ê清單。

    `source_column` 是素材位置彼欄ê名：有影片ê表是
    `原始影片檔案位置`，純文字ê句對表是 `來源文字檔檔案位置`。
    """
    problems = []
    seen = {}
    for index, row in enumerate(rows, start=2):   # 2 = 表頭了後頭一逝
        name = row.get("成果檔名", "")
        if not name_is_legal(name):
            problems.append("第 %d 逝：成果檔名 %r 無合命名規格"
                            % (index, name))
        elif name in seen:
            problems.append("第 %d 逝：成果檔名 %r 佮第 %d 逝重複"
                            % (index, name, seen[name]))
        else:
            seen[name] = index

        try:
            want = srt_name_of(row)
        except (PipelineError, KeyError, ValueError) as issue:
            problems.append("第 %d 逝：成果檔名推袂出來（%s）" % (index, issue))
        else:
            if want != name:
                problems.append("第 %d 逝：成果檔名 %r 佮識別欄推出來ê "
                                "%r 無仝" % (index, name, want))

        problems.extend(_language_problems(index, row))

        if not (row.get(source_column) or "").strip():
            problems.append("第 %d 逝：%s 空ê" % (index, source_column))

    problems.extend(_order_problems(rows))
    return problems


def _language_problems(index, row):
    """族語別中英一對一、語言別代號佇對照表內。"""
    problems = []
    chinese = row.get("族語別(中)", "")
    try:
        english = languages.english_for(chinese)
    except PipelineError as issue:
        return ["第 %d 逝：%s" % (index, issue)]
    if english != row.get("族語別(英)", ""):
        problems.append("第 %d 逝：族語別(英) %r 對袂著 %r（應該是 %r）"
                        % (index, row.get("族語別(英)"), chinese, english))
    code = row.get("語言別代號", "")
    try:
        languages.language_of(code)
    except PipelineError as issue:
        problems.append("第 %d 逝：%s" % (index, issue))
    return problems


def _order_problems(rows):
    """列序愛照 `成果檔名` 排。

    本底是登記ê順序（一月ê集數排佇二月後壁），所以加一批就kā後壁ê
    逐逝攏捒位——四擺改動全部是規檔重寫（75/75、36/36、36/36、73/34），
    對 diff 看袂出改著啥。
    """
    names = []
    for row in rows:
        names.append(row.get("成果檔名", ""))
    if names == sorted(names):
        return []
    for index in range(1, len(names)):
        if names[index] < names[index - 1]:
            return ["第 %d 逝：成果檔名 %r 排佇 %r 後壁，列序無照名排"
                    % (index + 2, names[index], names[index - 1])]
    return []


def orphan_problems(rows, stages):
    """階段目錄有、目錄表無ê檔——孤兒檔。

    倒轉來（表有、檔案系統無）毋是錯：彼是猶未做。
    """
    known = set()
    for row in rows:
        known.add(row.get("成果檔名", ""))
    problems = []
    for stage, names in stages:
        for name in sorted(names - known):
            problems.append("%s 有 %s，節目目錄查無彼逝" % (stage, name))
    return problems


def header_problems(fieldnames, keys):
    """表頭ê頭幾欄愛佮別張相仝。"""
    want = head(keys)
    got = tuple(fieldnames[:len(want)])
    if got == want:
        return []
    return ["表頭頭 %d 欄是 %s，應該是 %s"
            % (len(want), "、".join(got), "、".join(want))]


def month_of(name):
    """成果檔名 → 年-月，新聞ê階段目錄用ê彼層。"""
    return "%s-%s" % (name[:4], name[4:6])


def stage_dir(base, name):
    """新聞：階段目錄下ê月份彼層。"""
    return os.path.join(base, month_of(name))
