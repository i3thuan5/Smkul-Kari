"""多重分隔符行的切法：出工作表、收 Claude 的回覆、整批驗證後匯入。

規矩照 `scripts/asrmt/judge.py` 已經立好的，不另外發明：

- **提示詞就是定義**（`split_prompt.md`），改了提示詞就是換了問題。
- **Claude 的產出以檔案交回**，程式驗證後匯入——這個 repo 不從 Python
  打 API。
- **整批接受或整批拒收**：任何一筆的身分或切法有問題，整批不收，不
  是「這條錯了就跳過這條」——半批接受會把切法安到別的句子上，下游
  看不出來。
- **鍵是內容不是行號**：來源檔重下載後行號可能位移，但文字沒變就該
  沿用既有切法；`judge.py` 記過這個教訓（重投影一次時間軸，試作集
  第 304 條變成 309 條）。

**驗證的核心不是「逐字比對」，是「這是不是原句的合法切分」。** 把
Claude 給的每一段接起來、再把所有分隔符從兩邊都拿掉，兩邊必須完全
一樣（邊界上的空白允許被 trim 掉，那是切法本來就該做的事）。這樣寫
是因為多重分隔符裡最難的那種病——兩句字幕黏成一行——本來就沒有一個
字面上的分隔符能標出真正的邊界（那正是它會被打錯的原因），驗證不能
要求 Claude 在那個位置也生出一個分隔符，只能要求前後文字一個字都
不能多、不能少、不能調換順序。
"""
import csv
import os
import re

from scripts.aiyalaeho.text import decode
from scripts.aiyalaeho.text import parse
from scripts.errors import PipelineError


def find_problem_lines(root_dir):
    """掃過 root_dir 底下全部來源檔，回傳 [(相對路徑, 行號, 原句), ...]。

    「原句」是去掉時碼前綴後、含兩個以上分隔符的那段文字——跟
    `parse.py` 判斷「要不要查切法表」用的是同一段文字，這裡只是把它
    收集起來準備問 Claude，不逐檔照收（那是 `pairs.py` 的事）。
    """
    problems = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".txt", ".docx", ".doc"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root_dir)
            text, _fmt = decode.decode(path)
            for line_no, line in enumerate(text.split("\n"), 1):
                if not line.strip():
                    continue
                match = parse.TIMECODE_PAIR.match(line)
                content = match.group(3) if match else line
                separator = parse.find_separator(content)
                if separator and content.count(separator) >= 2:
                    problems.append((rel, line_no, content))
    return problems


def write_worksheet(problems, path):
    """去重後寫工作表：`編號<TAB>原句`。同一句原句只問一次——即使它在
    好幾個來源檔裡逐字重複（實測 158 筆裡有 135 筆是唯一內容）。
    """
    seen = {}
    for _rel, _line_no, content in problems:
        if content not in seen:
            seen[content] = len(seen) + 1
    with open(path, "w", encoding="utf-8") as handle:
        for content, number in seen.items():
            handle.write("%d\t%s\n" % (number, content))
    return seen


def _read_worksheet(path):
    by_id = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            number, _tab, content = line.rstrip("\n").partition("\t")
            by_id[number.strip()] = content
    return by_id


def _normalize(text):
    # 邊界上的空白本來就該被 trim 掉（單一分隔符那條路就是這樣做的），
    # 不能因為切完之後某個邊界少了一個空白就打回票——這裡要比的是
    # 「字有沒有被增刪調換」，不是空白排版。
    return re.sub(r"\s+", "", text)


def _reconstructs(content, pairs):
    """Claude 給的每一段接起來、雙方都拿掉分隔符字元之後，是不是同一句話。

    拿掉的是**組成分隔符的那個字元本身**（`/` 或 `\\`），不是只拿掉
    成對出現的分隔符——`////` 這種連續奇數個分隔符的殘壘（賽夏那幾個
    純分隔符占位行就有這款）用「拿掉成對的」會留一個殘餘字元下來，
    兩邊留的位置還不一定一樣，白白製造假的不符。分隔符本身沒有語意，
    整個拿掉才對。
    """
    separator = parse.find_separator(content)
    strip_char = separator[0]
    joined = "".join(formosan + han for formosan, han in pairs)
    left = _normalize(joined.replace(strip_char, ""))
    right = _normalize(content.replace(strip_char, ""))
    return left == right


def ingest_reply(worksheet_path, reply_path):
    """讀回覆、整批驗證，回傳 `{原句: [(族語,華語), ...]}`。

    回覆是 `編號<TAB>族語<TAB>華語`；同一個編號可以出現一次以上——那
    代表這句原句其實是兩句（或更多句）字幕黏成一行，每一段各自一行，
    順序就是列在回覆檔裡的順序，不另外標序號。
    """
    wanted = _read_worksheet(worksheet_path)
    answers = {}
    errors = []
    with open(reply_path, encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) != 3:
                errors.append("這一行欄位數不是 3：%r" % raw)
                continue
            number, formosan, han = fields
            number = number.strip()
            if number not in wanted:
                errors.append("編號 %s 不是工作表裡的" % number)
                continue
            answers.setdefault(number, []).append((formosan, han))

    for number in wanted:
        if number not in answers:
            errors.append("編號 %s 沒有回覆" % number)

    if not errors:
        for number, pairs in answers.items():
            content = wanted[number]
            if not _reconstructs(content, pairs):
                errors.append(
                    "編號 %s 的切法接回去不等於原句：%r -> %r"
                    % (number, content, pairs))

    if errors:
        raise PipelineError(
            "%s 有 %d 個問題，整批不收：%s"
            % (os.path.basename(reply_path), len(errors),
               "；".join(errors[:10])))

    return {wanted[number]: pairs for number, pairs in answers.items()}


def read_split_table_csv(path):
    """`多重分隔符切法.csv` → `{原句: [(族語,華語), ...]}`。

    寫出來、讀回去要一致，這樣這份 CSV 才是可信的正本，`pairs.py`
    才能只讀這個檔而不必重問一次 Claude。同一個原句在檔案裡出現不只
    一次（逐檔照收，也可能是兩句字幕黏一行的兩列）時，`族語,華語`
    對只取一次——來源檔不同但原句相同，切法必然相同。
    """
    table = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            content = row["原句"]
            pair = (row["族語"], row["華語"])
            pairs = table.setdefault(content, [])
            if pair not in pairs:
                pairs.append(pair)
    return table


def write_split_table_csv(problems, table, path):
    """把驗證過的切法表寫成人讀得懂的 CSV：`來源檔,原句,族語,華語`。

    逐檔照收，不因為 `table` 是去重過的就只寫一次——同一句原句在幾個
    來源檔出現，這裡就對應幾組列；一句原句對到兩組族語華語（兩句字幕
    黏一行）時，同一個來源檔底下就是連續兩列，不加序號欄。
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["來源檔", "原句", "族語", "華語"])
        for rel, _line_no, content in problems:
            for formosan, han in table[content]:
                writer.writerow([rel, content, formosan, han])
