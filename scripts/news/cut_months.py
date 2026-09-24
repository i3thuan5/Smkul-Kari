#!/usr/bin/env python3
"""一個月接一個月切 cue：`fetch_sftp.sh`，磁碟不夠就等。

    python3 -m scripts.news.cut_months                     # 2021-11～2024-11
    python3 -m scripts.news.cut_months --from 2022-03 --to 2022-06
    python3 -m scripts.news.cut_months --min-free 60       # 門檻 GB

每個月做完寫一列到 `kithann/out/news/logs/cut-progress.tsv`（月份、開始、
結束、切前待切、切後待切、結果；時間是臺灣時間）。

磁碟：一集 work dir 約 345 MB，一個月約 24 GB，剩下的月份全部切完放不
下。所以每個月開始前看剩多少，不到 `--min-free` 就每 10 分鐘看一次，
等讀字那邊入庫、清掉 work dir 再開始。月份中途不檢查，門檻要留夠一個
月（work dir 約 24 GB，加上同時在切的幾支影片）。

`fetch_sftp.sh` 本身可以重跑（切過的集數不再下載），所以倒一個月不擋
後面的月份，最後離開碼非 0；再跑一次同一個範圍就會補。
"""
import argparse
import csv
import datetime
import os
import shutil
import subprocess
import sys
import time

from scripts.news import paths

FIRST = "2021-11"
LAST = "2024-11"
MIN_FREE_GB = 50
WAIT_SECONDS = 600
COLUMNS = ["月份", "開始", "結束", "切前待切", "切後待切", "結果"]
PROGRESS = os.path.join(paths.NEWS_OUT, "logs", "cut-progress.tsv")


def month_range(first, last):
    """`first` 到 `last`（兩端都含）的 YYYY-MM。"""
    year, month = int(first[:4]), int(first[5:7])
    end = (int(last[:4]), int(last[5:7]))
    if (year, month) > end:
        raise ValueError("%s 在 %s 後面" % (first, last))
    out = []
    while (year, month) <= end:
        out.append("%04d-%02d" % (year, month))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def todo_count(month):
    """這個月還沒切的集數（`plan_month --todo` 的列數）。"""
    proc = subprocess.run([sys.executable, "-m", "scripts.news.plan_month",
                           month, "--todo"], cwd=paths.ROOT,
                          capture_output=True, text=True, check=True)
    count = 0
    for line in proc.stdout.splitlines():
        if line.strip():
            count += 1
    return count


def free_gb():
    return shutil.disk_usage(paths.NEWS_OUT).free / 1e9


def fetch(month):
    script = os.path.join(paths.ROOT, "scripts", "news", "fetch_sftp.sh")
    return subprocess.call(["bash", script, month], cwd=paths.ROOT,
                           stdin=subprocess.DEVNULL)


def now():
    taipei = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(taipei).strftime("%Y-%m-%d %H:%M")


def record(progress, row):
    fresh = not os.path.exists(progress)
    os.makedirs(os.path.dirname(progress), exist_ok=True)
    with open(progress, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, delimiter="\t",
                                lineterminator="\n")
        if fresh:
            writer.writeheader()
        writer.writerow(row)


def wait_for_disk(need_gb, free_gb, sleep, say):
    while True:
        free = free_gb()
        if free >= need_gb:
            return
        say("%s 磁碟剩 %.0f GB，未到 %d GB，%d 分鐘後再看"
            % (now(), free, need_gb, WAIT_SECONDS // 60))
        sleep(WAIT_SECONDS)


def say_now(text):
    """寫 log 愛隨出來：stdout 導去檔案時 print 會囤起來。"""
    print(text, flush=True)


def run(months, need_gb=MIN_FREE_GB, progress=PROGRESS, todo_count=todo_count,
        free_gb=free_gb, fetch=fetch, sleep=time.sleep, say=say_now, now=now):
    failed = False
    for month in months:
        before = todo_count(month)
        if before == 0:
            stamp = now()
            record(progress, {"月份": month, "開始": stamp, "結束": stamp,
                              "切前待切": 0, "切後待切": 0,
                              "結果": "無待切"})
            continue
        wait_for_disk(need_gb, free_gb, sleep, say)
        started = now()
        say("%s %s 開始，待切 %d 集" % (started, month, before))
        code = fetch(month)
        after = todo_count(month)
        if code != 0:
            result = "失敗（離開碼 %d）" % code
            failed = True
        elif after:
            result = "還剩 %d 集沒切" % after
            failed = True
        else:
            result = "切完"
        record(progress, {"月份": month, "開始": started, "結束": now(),
                          "切前待切": before, "切後待切": after,
                          "結果": result})
        say("%s %s %s" % (now(), month, result))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="first", default=FIRST)
    ap.add_argument("--to", dest="last", default=LAST)
    ap.add_argument("--min-free", type=int, default=MIN_FREE_GB,
                    help="每個月開始前磁碟至少要剩幾 GB")
    args = ap.parse_args(argv)
    return run(month_range(args.first, args.last), need_gb=args.min_free)


if __name__ == "__main__":
    sys.exit(main())
