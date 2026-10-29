#!/usr/bin/env python3
"""《開會了》OCR 字幕當標準答案：讀成評測 ASR／MT 用的句對。

來源是 `1-ocr/4-語言檢查/逐條語言標記.csv`——每條字幕一列，族語列、
華語列、時間，加上離線判出來的「這列的語言」（純族語／族語夾雜華語／
華語／無法確定），評測要分開算就靠這欄。

兩個服務的語別碼無仝套（sapolita `ami-x-iams`、翻譯服務 `ami_Sout`），
對照表是 2026-10-28 對兩爿下拉選單的標籤讀落來的。smkul 只寫到族語別
（`ami`）的集，照新聞線的保底送（`scripts/news/新聞語言別代號.csv`）。
"""
import csv
import os

from scripts.news import whisper_run
from scripts.errors import PipelineError
from scripts import datadirs

LABELS_CSV = os.path.join(datadirs.KARI, "aiyalaeho", "1-ocr",
                          "4-語言檢查", "逐條語言標記.csv")

# sapolita 語別碼 -> 翻譯服務語別碼（兩爿下拉選單的中文標籤對起來）
MT_OF_SAPOLITA = {
    "ami-x-iams": "ami_Sout",   # 南勢
    "ami-x-skl": "ami_Xiug",    # 秀姑巒
    "ami-x-pswl": "ami_Coas",   # 海岸
    "ami-x-frng": "ami_Mala",   # 馬蘭
    "ami-x-pld": "ami_Heng",    # 恆春
}


def seconds(stamp):
    """'00:01:02,050' -> 62.05"""
    clock, millis = stamp.split(",")
    hours, minutes, secs = clock.split(":")
    return (int(hours) * 3600 + int(minutes) * 60 + int(secs)
            + int(millis) / 1000.0)


def load(path=None, family="阿美"):
    out = []
    with open(path or LABELS_CSV, encoding="utf-8-sig", newline="") as f:
        for item in csv.DictReader(f):
            if item["族語別(中)"] != family:
                continue
            out.append({
                "srt_name": item["成果檔名"],
                "index": int(item["字幕編號"]),
                "start": seconds(item["開始時間"]),
                "end": seconds(item["結束時間"]),
                "label": item["這列的語言"],
                "formosan": item["族語列"].strip(),
                "han": item["華語列"].strip(),
                "code": item["語言別代號"],
            })
    return out


def sapolita_code(srt_name, row_code, family="阿美"):
    entry = {"srt_name": srt_name, "族語別(中)": family,
             "語言別代號": row_code}
    return whisper_run.code_for(entry)


def mt_code(sapolita_code_):
    if sapolita_code_ not in MT_OF_SAPOLITA:
        raise PipelineError(
            "語別碼 %r 無對應的翻譯服務語別碼——服務收著毋捌的碼會靜靜"
            "改用海岸，袂使送" % sapolita_code_)
    return MT_OF_SAPOLITA[sapolita_code_]


def mt_items(rows):
    """(direction, mt_code, text)，族語列華語列攏有字才送，重複的只送一擺。"""
    seen = set()
    out = []
    for item in rows:
        if not item["formosan"] or not item["han"]:
            continue
        for key in (("f2z", item["mt_code"], item["formosan"]),
                    ("z2f", item["mt_code"], item["han"])):
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out
