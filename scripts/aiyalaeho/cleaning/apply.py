"""清洗版 SRT 與修改前後對照表。

**直接改交付 SRT 的文字行**，編號、時間、空行、標籤一個 byte 都不動。
不在 cue 層改了再重組：重組時文字變得一樣的相鄰兩條會被 merge_repeats
併掉，編號一位移，對照表就對不上交付版。

一列文字依序做四件事，每做一件記一筆（修改前接上一筆的修改後）：

  1. a 項規則（rules.clean）：撇號、多餘空白、重複標點
  2. 撇號夾空白：看圖判定後的寫法（Merge），只在族語列
  3. 錯字：看圖確認為 OCR 讀錯或播出端錯字的（Fix），只在族語列
  4. 節目名：'a'iyalaeho: 的錯拼統一，兩列都做

判語言別差異、不同詞、斷詞不同、不確定、看不出來的，呼叫端就不會給 Fix，
這裡也就不動（d 項：語言別差異不直接修改）。
"""
import collections

from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.cleaning import rules
from scripts.aiyalaeho.cleaning import source
from scripts.errors import PipelineError

Fix = collections.namedtuple(
    "Fix", "srt_name number word replacement kind basis")
Merge = collections.namedtuple(
    "Merge", "srt_name number cleaned replacement basis")
Change = collections.namedtuple(
    "Change", "srt_name number start end row before after kind basis")

CHANGE_HEADER = ["成果檔名", "字幕編號", "開始時間", "結束時間", "列", "修改前",
                 "修改後", "類別", "依據"]

PROGRAMME_KIND = "節目名"
RULE_BASIS = {
    "撇號": "彎撇換直撇",
    "多餘空白": "連續空白縮成一個",
    "重複標點": "刪節號 4 點以上縮成 3 點；重複的驚嘆號、問號縮成一個",
}
ROWS = ((source.FORMOSAN_LABEL, "族語"), (source.HAN_LABEL, "華語"))


def _cased(original, replacement):
    """原詞第一個字母大寫，替換後也大寫（句首、專名）。"""
    first = None
    for char in original:
        if char.isalpha():
            first = char
            break
    if first is None or not first.isupper():
        return replacement
    out = list(replacement)
    for index, char in enumerate(out):
        if char.isalpha():
            out[index] = char.upper()
            break
    return "".join(out)


def replace_word(text, word, replacement):
    """以詞為單位把 word（不分大小寫）換成 replacement，回傳 (新文字, 次數)。"""
    pieces = []
    last = 0
    count = 0
    for start, end, token in candidates.spans(text):
        if token.lower() == word.lower():
            pieces.append(text[last:start])
            pieces.append(_cased(token, replacement))
            last = end
            count += 1
    pieces.append(text[last:])
    return "".join(pieces), count


def _clean_row(text, row, place, fixes, merges):
    """一列文字 → (清洗後, [(類別, 修改前, 修改後, 依據)…])。"""
    steps = []
    current, ruled = rules.clean(text)
    for step in ruled:
        basis = RULE_BASIS[step.kind]
        if step.kind == "多餘空白" and row == "華語":
            basis += "（畫面斷句保留）"
        steps.append((step.kind, step.before, step.after, basis))
    if row == "族語":
        for merge in merges.get(place, ()):
            if merge.cleaned not in current:
                raise PipelineError("%s 第 %d 條找不到要併的「%s」"
                                    % (place[0], place[1], merge.cleaned))
            after = current.replace(merge.cleaned, merge.replacement, 1)
            if after != current:
                steps.append(("撇號", current, after, merge.basis))
                current = after
        for fix in fixes.get(place, ()):
            after, count = replace_word(current, fix.word, fix.replacement)
            if not count:
                raise PipelineError("%s 第 %d 條找不到要改的「%s」"
                                    % (place[0], place[1], fix.word))
            if after != current:
                steps.append((fix.kind, current, after, fix.basis))
                current = after
    for variant in candidates.programme_variants(current):
        after, _count = replace_word(current, variant, candidates.PROGRAMME)
        if after != current:
            steps.append((PROGRAMME_KIND, current, after,
                          "節目名統一為 %s" % candidates.PROGRAMME))
            current = after
    return current, steps


def _grouped(items):
    out = collections.defaultdict(list)
    for item in items:
        out[(item.srt_name, item.number)].append(item)
    return out


def clean_episode(text, srt_name, fixes, merges):
    """交付 SRT 全文 → (清洗版全文, [Change…])。"""
    fixes = _grouped(fixes)
    merges = _grouped(merges)
    lines = text.split("\n")
    changes = []
    number = None
    start = end = ""
    for index, line in enumerate(lines):
        if line.isdigit() and index + 1 < len(lines) \
                and " --> " in lines[index + 1]:
            number = int(line)
            start, _, end = lines[index + 1].partition(" --> ")
            continue
        for label, row in ROWS:
            if not line.startswith(label):
                continue
            place = (srt_name, number)
            after, steps = _clean_row(line[len(label):], row, place, fixes,
                                      merges)
            lines[index] = label + after
            for kind, before, changed, basis in steps:
                changes.append(Change(srt_name, number, start, end, row,
                                      before, changed, kind, basis))
    return "\n".join(lines), changes


def change_rows(changes):
    """修改前後對照表的列（含表頭），照成果檔名、字幕編號、發生順序。"""
    out = [list(CHANGE_HEADER)]
    order = sorted(range(len(changes)),
                   key=lambda i: (changes[i].srt_name, changes[i].number, i))
    for index in order:
        change = changes[index]
        out.append([change.srt_name, str(change.number), change.start,
                    change.end, change.row, change.before, change.after,
                    change.kind, change.basis])
    return out
