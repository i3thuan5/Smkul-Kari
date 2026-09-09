#!/usr/bin/env python3
"""掃過上字文稿暫存目錄，組出 `Kari-SRT/aiyalaeho/text/1-句對.csv`。

    python3 -m scripts.aiyalaeho.text.pairs

十欄：`集,來源檔,來源檔編碼格式,行號,類型,語言別代號,族語,華語,
開始時間,結束時間`。逐檔照收，不判斷正本；解不開任何一個來源檔就整批
中止，不寫出半份 CSV——這是一次跑完 243 個檔的批次，半份結果比沒有
結果更危險。
"""
import argparse
import csv
import os

from scripts.aiyalaeho.text import decode
from scripts.aiyalaeho.text import lang
from scripts.aiyalaeho.text import parse
from scripts.aiyalaeho.text import split
from scripts.aiyalaeho import paths
from scripts.errors import PipelineError

FIELDS = ("集", "來源檔", "來源檔編碼格式", "行號", "類型", "語言別代號",
          "族語", "華語", "開始時間", "結束時間")


def _tab_to_space(text):
    return text.replace("\t", " ")


def build_rows(root_dir, split_table):
    """root_dir 底下每個一級子目錄是一集；回傳排序過的列清單。

    語言別代號一集只查一次——`lang.resolve()` 讀的是目錄名稱，跟目錄
    底下哪個檔案無關，重算只是浪費且可能因為快取／時序而兜出不一致。
    """
    episodes = sorted(
        name for name in os.listdir(root_dir)
        if os.path.isdir(os.path.join(root_dir, name))
    )

    rows = []
    for episode in episodes:
        episode_dir = os.path.join(root_dir, episode)
        language_code = lang.resolve(episode)

        source_files = []
        for dirpath, _dirnames, filenames in os.walk(episode_dir):
            for name in sorted(filenames):
                ext = os.path.splitext(name)[1].lower()
                if ext not in (".txt", ".docx", ".doc"):
                    continue
                source_files.append(os.path.join(dirpath, name))
        source_files.sort()

        for path in source_files:
            rel = os.path.relpath(path, root_dir)
            text, fmt = decode.decode(path)
            for line in parse.parse_lines(text, split_table=split_table):
                rows.append({
                    "集": episode,
                    "來源檔": rel,
                    "來源檔編碼格式": fmt,
                    "行號": line["行號"],
                    "類型": line["類型"],
                    "語言別代號": language_code,
                    "族語": _tab_to_space(line["族語"]),
                    "華語": _tab_to_space(line["華語"]),
                    "開始時間": line["開始時間"],
                    "結束時間": line["結束時間"],
                })

    rows.sort(key=lambda r: (r["集"], r["來源檔"], r["行號"]))
    return rows


def write_csv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=paths.TEXT_WORK,
                    help="上字文稿暫存目錄（預設 %(default)s）")
    ap.add_argument("--split-table",
                    default=os.path.join(paths.TEXT_STORE, "多重分隔符切法.csv"),
                    help="多重分隔符切法表（預設 %(default)s）")
    ap.add_argument("--out", default=paths.TEXT_PAIRS,
                    help="輸出的句對 CSV（預設 %(default)s）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        raise PipelineError("找不到上字文稿暫存目錄：%s——先跑 fetch.sh"
                            % args.root)

    split_table = {}
    if os.path.exists(args.split_table):
        split_table = split.read_split_table_csv(args.split_table)

    rows = build_rows(args.root, split_table)
    write_csv(rows, args.out)
    print("寫出 %d 列到 %s" % (len(rows), args.out))


if __name__ == "__main__":
    main()
