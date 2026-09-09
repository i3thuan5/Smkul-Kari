"""一個檔的文字 → 一串列：(行號,類型,族語,華語,開始時間,結束時間)。

上字文稿混用四種互不相容的排版，一律照這裡的規則解讀，判不出來的行
標記而不是硬猜：

  同行雙語        `族語//華語` 或 `族語\\\\華語`，一行一句
  時碼＋同行雙語   前面多兩個時間碼，時間原樣不換算
  隔行雙語        族語一行、華語一行交替，行內沒有分隔符
  短片段          promo／SOT／bite 這類，多半只有單語或製作註記

`類型` 的值：`雙語`、`雙語（多重分隔符，AI切割）`、
`雙語（多重分隔符，規則切割）`、`隔行配對`、`僅族語`、`僅華語`、`混合`、
`註記`——跟 `Kari-SRT/aiyalaeho/text/1-句對.csv` 的欄位定義一致。
"""
import re

_HAN = re.compile(r"[一-鿿]")
_LAT = re.compile(r"[A-Za-z]")

TIMECODE_PAIR = re.compile(
    r"^(\d{1,2}:\d{2}:\d{2}[;:.,]\d{2})\s+"
    r"(\d{1,2}:\d{2}:\d{2}[;:.,]\d{2})\s+(.*)$"
)

# 開會031、開會032 有幾個檔整份只印一個時碼（沒有結束時間，下一條的
# 開始隱含就是這一條的結束）。抓 TIMECODE_PAIR 抓不到時才試這個——順序
# 要對，不然兩個時碼的行會被這條吃掉第一個當時碼、第二個當內容的一
# 部分。
TIMECODE_SINGLE = re.compile(
    r"^(\d{1,2}:\d{2}:\d{2}[;:.,]\d{2})\s+(.*)$"
)

# 製作註記：段落標記（OS/Bite/SOT/NS）、純數字時碼、剪接指示（含「刪」）。
# 這幾種樣子是實際盤點量到的，不是憑空編的——見 design.md 的量測結果。
_MARKER_WHOLE = re.compile(r"^(?:OS\d*|BITE|Bite|bite|SOT\d*|sot\d*|NS|ns)$")
_MARKER_DIGITS = re.compile(r"^~?\d{4,8}~?$")


def find_separator(text):
    # `\\` 先判：時碼版與開會036、038 用它；其餘多數用 `//`。一行只會
    # 出現一種分隔符（同一份文稿的排版習慣一致），不會兩種混用。
    if "\\\\" in text:
        return "\\\\"
    if "//" in text:
        return "//"
    return None


def _looks_like_marker(text):
    stripped = text.strip()
    if _MARKER_WHOLE.match(stripped):
        return True
    if _MARKER_DIGITS.match(stripped):
        return True
    if "刪" in stripped:
        return True
    return False


def _is_latin_only(text):
    return bool(_LAT.search(text)) and not _HAN.search(text)


def _is_han_only(text):
    return bool(_HAN.search(text)) and not _LAT.search(text)


def _extract_timecode(line):
    """line → (開始時間, 結束時間, 去掉時碼前綴後的內容)。

    只做這一件事，而且全部呼叫端（同行雙語、隔行配對、落單、混合）
    都要先過這一關才判斷內容——時碼一旦抽出來就不可以再弄丟。抽出來
    以後才發現「內容判不出類型」而把原始 `line`（時碼還在上面）拿去
    重判，會讓時碼字串整串掉進族語或華語欄，這是量到的真實錯誤，不是
    假設的風險。
    """
    match = TIMECODE_PAIR.match(line)
    if match:
        return match.group(1), match.group(2), match.group(3)
    match = TIMECODE_SINGLE.match(line)
    if match:
        return match.group(1), "", match.group(2)
    return "", "", line


def _classify_content(content, start, end, split_table):
    """content 已經由 `_extract_timecode` 去掉時碼前綴；start/end 原樣
    帶進每一列，跟內容判到哪一種類型無關。

    回傳 None 表示這一行要留給外層去判斷是不是隔行配對的一半、還是
    落單的族語／華語／混合。有結果時回傳一個**列表**——通常是一列，
    但一行如果其實是兩句字幕黏在一起（`split_table` 給了兩組族語華語），
    就回傳兩列，`行號` 由呼叫者統一填。
    """
    if start and not content.strip():
        # 有時碼、無內容：這個窗口沒有話要說，是製作事實不是漏譯，也
        # 不是「混合」（那是族華同一行、沒有分隔符可切的情形）。
        return [{
            "類型": "註記",
            "族語": "",
            "華語": "",
            "開始時間": start,
            "結束時間": end,
        }]

    separator = find_separator(content)
    if separator:
        count = content.count(separator)
        if count == 1:
            formosan, han = content.split(separator, 1)
            return [{
                "類型": "雙語",
                "族語": formosan.strip(),
                "華語": han.strip(),
                "開始時間": start,
                "結束時間": end,
            }]
        if content in split_table:
            return [
                {
                    "類型": "雙語（多重分隔符，AI切割）",
                    "族語": formosan.strip(),
                    "華語": han.strip(),
                    "開始時間": start,
                    "結束時間": end,
                }
                for formosan, han in split_table[content]
            ]
        formosan, han = content.rsplit(separator, 1)
        return [{
            "類型": "雙語（多重分隔符，規則切割）",
            "族語": formosan.strip(),
            "華語": han.strip(),
            "開始時間": start,
            "結束時間": end,
        }]

    if _looks_like_marker(content):
        return [{
            "類型": "註記",
            "族語": content.strip(),
            "華語": "",
            "開始時間": start,
            "結束時間": end,
        }]

    return None


def parse_lines(text, split_table=None):
    """text（decode.py 吐出來的一個檔的內容）→ 列的串列。

    `split_table`：多重分隔符行的切法對照，鍵是去掉時碼前綴後的原句，
    值是 `[(族語, 華語), ...]` 的清單——通常長度 1，一行如果其實是兩句
    字幕黏成一行就是長度 2，各自輸出一列、`行號` 相同。由 `split.py`
    驗收 Claude 的判讀後產生。查無的行退回規則切割。
    """
    split_table = split_table or {}
    raw_lines = text.split("\n")
    numbered = [(i + 1, line) for i, line in enumerate(raw_lines)
                if line.strip()]

    rows = []
    idx = 0
    total = len(numbered)
    while idx < total:
        line_no, line = numbered[idx]
        start, end, content = _extract_timecode(line)

        single = _classify_content(content, start, end, split_table)
        if single is not None:
            for row in single:
                row["行號"] = line_no
                rows.append(row)
            idx += 1
            continue

        if _is_latin_only(content) and idx + 1 < total:
            _, next_line = numbered[idx + 1]
            next_start, next_end, next_content = _extract_timecode(next_line)
            if (_classify_content(next_content, next_start, next_end,
                                  split_table) is None
                    and _is_han_only(next_content)):
                rows.append({
                    "行號": line_no,
                    "類型": "隔行配對",
                    "族語": content.strip(),
                    "華語": next_content.strip(),
                    "開始時間": start,
                    "結束時間": end,
                })
                idx += 2
                continue

        if _is_latin_only(content):
            kind, formosan, han = "僅族語", content.strip(), ""
        elif _is_han_only(content):
            kind, formosan, han = "僅華語", "", content.strip()
        else:
            kind, formosan, han = "混合", content.strip(), ""
        rows.append({
            "行號": line_no,
            "類型": kind,
            "族語": formosan,
            "華語": han,
            "開始時間": start,
            "結束時間": end,
        })
        idx += 1

    return rows
