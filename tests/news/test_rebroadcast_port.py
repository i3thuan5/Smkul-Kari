"""rebroadcast_port：重播集照首播搬時間軸和字，不必重讀。

同一段節目（島語時間、部落信箱、專題）在好幾集重播，首播修好的
cue 和字要搬到重播集。重播是同一段畫面，所以不必整段重新 OCR：用兩集
都只出現一次的句子當錨點算位移，照位移換掉重播那段的 cue、TSV 改號、
訂正紀錄跟著改、段落表換成首播那幾列。

每條 scenario 的數字都是 2026-10-27 用 Kari-SRT 量到的（227 午→216 晚、
244 晚→076 晚、194 晚→098 晚、309 午→299 午、182 晨部落信箱…），這裡
只用合成 fixture 重現那個情形，不讀真資料。
"""
import contextlib
import io
import json
import math
import os
import random
import re
import shutil
import signal
import tempfile
import unittest
from unittest import mock

import numpy

from scripts.errors import PipelineError
from scripts.news import offband_backfill
from scripts.news import publish
from scripts.news import rebroadcast_port as port
from scripts.news import segments

F = 1001 / 30000
SRC = "20240315_075_午間_Kavalan_噶瑪蘭"
TGT = "20240401_129_午間_Kavalan_噶瑪蘭"
SRC_SLUG = "2024_075_2024-03-15_午間_Kavalan_噶瑪蘭"
TGT_SLUG = "2024_129_2024-04-01_午間_Kavalan_噶瑪蘭"


def say(number):
    return "第%03d句測試字幕" % number


def own(number):
    return "本集%03d自己的新聞" % number


def cue(index, start, end, **extra):
    item = {"index": index, "start": start, "end": end, "sample_ts": start,
            "frames": 5, "ink": 1000,
            "images": {"han": "2-strips/t%08d_han.png" % int(start * 1000)}}
    item.update(extra)
    return item


def build(lines):
    """[(start, end, text, extra dict)] → (cues, texts)，照時間編號。"""
    lines = sorted(lines, key=lambda line: line[0])
    cues = []
    texts = {}
    for number, line in enumerate(lines, 1):
        extra = line[3] if len(line) > 3 else {}
        cues.append(cue(number, line[0], line[1], **extra))
        texts[number] = line[2]
    return cues, texts


def program(lo=1000.0, count=30, step=4.0, area="島語時間"):
    """首播範圍內的句子：(start, end, text, extra)。"""
    out = []
    for number in range(count):
        start = round(lo + number * step + 0.3, 3)
        out.append((start, round(start + 3.2, 3), say(number),
                    {"area": area}))
    return out


def shifted(lines, off):
    out = []
    for start, end, text, extra in lines:
        out.append((round(start + off, 3), round(end + off, 3), text,
                    dict(extra)))
    return out


def pair(off=-234.0, lo=1000.0, count=30, step=4.0):
    """首播和重播：範圍內相同，範圍外各自有自己的新聞。"""
    hi = lo + count * step
    body = program(lo, count, step)
    src_lines = [(lo - 30.0, lo - 26.0, own(901), {}),
                 (lo - 20.0, lo - 16.0, own(902), {})]
    src_lines += body
    src_lines += [(hi + 10.0, hi + 14.0, own(903), {})]
    tgt_lines = [(lo + off - 40.0, lo + off - 36.0, own(1), {}),
                 (lo + off - 30.0, lo + off - 26.0, own(2), {})]
    tgt_lines += shifted(body, off)
    tgt_lines += [(hi + off + 20.0, hi + off + 24.0, own(3), {})]
    src_cues, src_texts = build(src_lines)
    tgt_cues, tgt_texts = build(tgt_lines)
    src_book = {"cues": src_cues, "duration": hi + 100.0,
                "areas": {"島語時間": {"preset": "titv-news-island",
                                   "region": [0, 940, 1920, 120]}},
                "refined": True}
    tgt_book = {"cues": tgt_cues, "duration": hi + off + 100.0,
                "areas": {}, "refined": True}
    return src_book, src_texts, tgt_book, tgt_texts, lo, hi


def own_cut(lines):
    """重播自己切的第一條晚 0.133 秒起、沒讀到字（222 cue 444 那種空白
    cue 迄點 1597.433，重播自己的下一條不會跟它重疊）。"""
    _start, end, _text, extra = lines[0]
    return [(1597.433, end, "", extra)] + list(lines[1:])


def anchor_set(deltas, lo=1000.0, step=4.0):
    out = []
    for number, delta in enumerate(deltas):
        start = lo + number * step
        out.append({"src": start, "tgt": start + delta, "delta": delta,
                    "text": say(number)})
    return out


def text_of(result, number):
    return result["texts"].get(number, "")


def mentions(reasons, *words):
    """reasons 裡有一句同時包含所有 words。"""
    for why in reasons:
        hit = True
        for word in words:
            if word not in why:
                hit = False
        if hit:
            return True
    return False


def drop(book, texts, index):
    """重播漏一條 cue（島語時間漏收的典型）：拿掉，後面的號碼退一位。"""
    cues = []
    moved = {}
    for item in book["cues"]:
        if item["index"] == index:
            continue
        item = dict(item)
        old = item["index"]
        item["index"] = len(cues) + 1
        cues.append(item)
        if old in texts:
            moved[item["index"]] = texts[old]
    book["cues"] = cues
    texts.clear()
    texts.update(moved)


# ------------------------------------------------------------ 位移


class TestRuns(unittest.TestCase):

    def test_runs_merge_adjacent_same_text(self):
        """一句字幕跨好幾條 cue、每條寫同一句（全批 12,351 處）：不先併成
        一段，就算不出「只出現一次」，錨點少一大半。只併「相連而且同字」
        的。"""
        cues, texts = build([(0.0, 1.0, "一二三四五六七"),
                             (1.0, 2.0, "一二三四五六七"),
                             (2.0, 3.0, "另外一句話八九"),
                             (5.0, 6.0, "一二三四五六七")])
        got = port.runs(cues, texts)
        self.assertEqual(len(got), 3)
        self.assertEqual(got[0]["cues"], [1, 2])
        self.assertEqual((got[0]["start"], got[0]["end"]), (0.0, 2.0))
        self.assertEqual(got[2]["cues"], [4])

        src_cues, src_texts = build([(10.0, 12.0, say(1)),
                                     (12.0, 14.0, say(1))])
        tgt_cues, tgt_texts = build([(110.0, 111.0, say(1)),
                                     (111.0, 112.0, say(1)),
                                     (112.0, 114.0, say(1))])
        found = port.anchors(src_cues, src_texts, tgt_cues, tgt_texts,
                             0.0, 100.0)
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0]["delta"], 100.0)

    def test_norm_treats_curly_and_straight_apostrophe_alike(self):
        self.assertEqual(port.norm("’Acicim， 好！"), port.norm("'Acicim好"))


class TestOffset(unittest.TestCase):

    def test_offset_not_rounded_to_frames(self):
        """位移不是整數格：244 晚→076 晚 −234.000＝−7012.99 格；硬取整格
        會差 0.4 毫秒，搬過去逐條四捨五入就出錯。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair(off=-234.0)
        found = port.anchors(src_book["cues"], src_texts, tgt_book["cues"],
                             tgt_texts, lo, hi)
        evidence = port.judge_offset(found, None, lo, hi)
        self.assertEqual(evidence["status"], "ready")
        self.assertAlmostEqual(evidence["offset"], -234.0, places=6)
        whole = round(-234.0 / F) * F
        self.assertGreater(abs(evidence["offset"] - whole), 0.0003)

    def test_anchor_uses_start_only(self):
        """迄點不能當錨點：重播用別的區域切 cue 時迄點差 p90 1.8 秒
        （227→222），起點只差 0.028 秒。"""
        body = program(count=20)
        tgt = []
        for number, (start, end, text, extra) in enumerate(body):
            wobble = 1.8 if number % 2 else -1.2
            tgt.append((start + 500.0, end + 500.0 + wobble, text, extra))
        src_cues, src_texts = build(body)
        tgt_cues, tgt_texts = build(tgt)
        found = port.anchors(src_cues, src_texts, tgt_cues, tgt_texts,
                             1000.0, 1080.0)
        evidence = port.judge_offset(found, None, 1000.0, 1080.0)
        self.assertEqual(evidence["status"], "ready")
        self.assertAlmostEqual(evidence["offset"], 500.0, places=6)
        self.assertLessEqual(evidence["p90"], 0.001)

    def test_reject_cut_inside_range(self):
        """重播剪掉中間 3 秒：單一位移會讓後半段全錯——要找出「前面連續
        18 個 +100.00、後面連續 12 個 +97.00」的分界並拒絕，講出首播幾秒。"""
        found = anchor_set([100.0] * 18 + [97.0] * 12)
        cut = port.find_cut(found)
        self.assertIsNotNone(cut)
        self.assertGreater(cut["at"], found[17]["src"])
        self.assertLess(cut["at"], found[18]["src"])
        evidence = port.judge_offset(found, None, 1000.0, 1120.0)
        self.assertEqual(evidence["status"], "rejected")
        self.assertTrue(mentions(evidence["reasons"], "剪接", "1070"),
                        evidence["reasons"])

    def test_interleaved_second_cluster_is_not_a_cut(self):
        """首播改過起迄的 cue 會形成第二群（182 晨部落信箱 6 條差 −0.57
        秒，跟 41 條交錯），不可以誤判成剪接。"""
        deltas = []
        for number in range(47):
            deltas.append(-0.57 + 50.0 if number % 8 == 3 else 50.0)
        found = anchor_set(deltas)
        self.assertIsNone(port.find_cut(found))
        evidence = port.judge_offset(found, None, 1000.0, 1188.0)
        self.assertEqual(evidence["status"], "ready", evidence["reasons"])
        self.assertEqual(evidence["inliers"], 41)

    def test_reject_inconsistent_anchor_spread(self):
        """錨點各自差 0.07–0.45 秒、沒有一致的格位移（309 午→299 午）→
        拒絕，不可以拿中位數硬搬。"""
        wobble = [0.05, -0.04, 0.045, -0.05, 0.04, -0.045, 0.05, -0.04]
        deltas = []
        for number in range(24):
            deltas.append(30.0 + wobble[number % len(wobble)])
        evidence = port.judge_offset(anchor_set(deltas), None, 1000.0,
                                     1096.0)
        self.assertEqual(evidence["status"], "rejected")
        self.assertGreater(evidence["p90"], 0.034)
        self.assertTrue(mentions(evidence["reasons"], "逐格"))

    def test_reject_different_edit(self):
        """剪法不同（194 晚→098 晚：33 個錨點只有 10 個同群，三窗中位數
        −374.37／−374.91／−373.24）→ 拒絕。"""
        deltas = [-374.37] * 10 + [-374.91] * 12 + [-373.24] * 11
        found = []
        for number, delta in enumerate(deltas):
            start = 1000.0 + number * 5.4
            found.append({"src": start, "tgt": start + delta,
                          "delta": delta, "text": say(number)})
        evidence = port.judge_offset(found, None, 1000.0, 1180.0)
        self.assertEqual(evidence["status"], "rejected")
        self.assertTrue(mentions(evidence["reasons"], "剪法"),
                        evidence["reasons"])


class TestWhisper(unittest.TestCase):

    def test_whisper_short_window_inconclusive(self):
        """whisper 短窗沒有結論（109 秒、6 段，三個候選各 3 票）不等於不一致：
        要回報「沒有結論」，窗放寬到範圍中點前後各 300 秒。"""
        src = []
        for number in range(6):
            start = 1000.0 + number * 18.0
            src.append((start, start + 9.0))
        tgt = []
        for shift in (100.0, 200.0, 300.0):
            for start, _end in src[:3]:
                tgt.append((start + shift, start + shift + 2.5))
        got = port.whisper_offset(src, tgt, 1000.0, 1109.0)
        self.assertFalse(got["conclusive"])
        self.assertEqual(port.whisper_window(1000.0, 1109.0),
                         (754.5, 1354.5))
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        found = port.anchors(src_book["cues"], src_texts, tgt_book["cues"],
                             tgt_texts, lo, hi)
        evidence = port.judge_offset(found, got, lo, hi)
        self.assertEqual(evidence["status"], "ready")
        self.assertEqual(evidence["whisper_verdict"], "沒有結論")

    def test_whisper_coarse_only(self):
        """whisper 跟畫面差 53 毫秒（089 晚 2021←332 晚 2023，影音同步不同）：
        whisper 只當粗定位（容差 0.1 秒），最後的位移用畫面。"""
        found = anchor_set([83.584] * 25)
        near = {"offset": 83.531, "hits": 60, "runner_up": 4,
                "conclusive": True}
        evidence = port.judge_offset(found, near, 1000.0, 1100.0)
        self.assertEqual(evidence["status"], "ready")
        self.assertAlmostEqual(evidence["offset"], 83.584, places=6)
        self.assertEqual(evidence["whisper_verdict"], "一致")
        self.assertEqual(evidence["grade"], "A")

        far = dict(near, offset=83.8)
        evidence = port.judge_offset(found, far, 1000.0, 1100.0)
        self.assertAlmostEqual(evidence["offset"], 83.584, places=6)
        self.assertEqual(evidence["whisper_verdict"], "不一致")
        self.assertEqual(evidence["grade"], "B")

        evidence = port.judge_offset(anchor_set([83.584]), near, 1000.0,
                                     1100.0)
        self.assertEqual(evidence["status"], "pixel")
        self.assertAlmostEqual(evidence["offset"], 83.531)

    def test_whisper_only_without_ocr_anchors(self):
        """島語時間這種重播集整段沒讀過字的，OCR 一個錨點都沒有：whisper
        有效時要走像素定位，不可以因為沒有畫面位移可比而當掉。"""
        near = {"offset": -234.006, "hits": 52, "runner_up": 3,
                "conclusive": True}
        evidence = port.judge_offset([], near, 1191.0, 2126.0)
        self.assertEqual(evidence["status"], "pixel")
        self.assertAlmostEqual(evidence["offset"], -234.006)
        self.assertEqual(evidence["whisper_verdict"], "有效（沒有 OCR 可比）")

    def test_whisper_boundaries_not_text(self):
        """whisper 邊界跟族語碼無關：同一段聲音送不同語言碼，文字完全不同，
        段落邊界一樣（244 賽夏→076 排灣 52 個邊界對到）；不可以用 whisper
        的文字比對。"""
        blocks_src = []
        blocks_tgt = []
        start = 1191.0
        rand = random.Random(5)
        for number in range(30):
            end = round(start + rand.uniform(3.0, 12.0), 3)
            blocks_src.append("%d\n%s --> %s\n族語：sazasangasan %d\n華語：甲\n"
                              % (number + 1, stamp(start), stamp(end),
                                 number))
            blocks_tgt.append("%d\n%s --> %s\n族語：ailja vuvu %d\n華語：乙\n"
                              % (number + 1, stamp(start - 234.006),
                                 stamp(end - 234.006), number))
            start = round(end + rand.uniform(0.2, 3.0), 3)
        src = port.read_sapolita("\n".join(blocks_src))
        tgt = port.read_sapolita("\n".join(blocks_tgt))
        self.assertEqual(len(src), 30)
        got = port.whisper_offset(src, tgt, 1191.0, 2126.0)
        self.assertTrue(got["conclusive"])
        self.assertGreaterEqual(got["hits"], 52)
        self.assertAlmostEqual(got["offset"], -234.006, places=3)


def stamp(seconds):
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return "%02d:%02d:%02d,%03d" % (hours, minutes, secs, millis)


# ------------------------------------------------------------ 範圍邊界


class TestRange(unittest.TestCase):

    def test_range_shrinks_off_target_own_lines(self):
        """範圍迄點落在重播自己的主播開場：244→076 首播那列搬過去到
        1892，會蓋掉 076 cue 702–706「接下來要跟大家分享的是…」；要縮到
        1878.626。"""
        off = -234.0
        body = program(lo=2000.0, count=22)        # 2000.3 … 2087.5
        src_lines = list(body)
        src_lines.append((2088.3, 2092.0, "首播後段別的節目內容", {}))
        src_lines.append((2092.5, 2098.0, "首播後段第二句內容", {}))
        tgt_lines = shifted(body, off)             # 到 1853.5
        tgt_lines.append((1854.626, 1857.0, "接下來要跟大家分享的是", {}))
        tgt_lines.append((1857.2, 1860.0, "為女穿衣是排灣族的習俗", {}))
        tgt_lines.append((1860.2, 1864.0, own(5), {}))
        src_cues, src_texts = build(src_lines)
        tgt_cues, tgt_texts = build(tgt_lines)
        result = port.port({"cues": src_cues}, src_texts,
                           {"cues": tgt_cues}, tgt_texts, 2000.0, 2100.0,
                           off)
        self.assertAlmostEqual(result["range"][1], 1854.626)
        new_texts = []
        for item in result["cues"]:
            new_texts.append(result["all_texts"][item["index"]])
        self.assertIn("接下來要跟大家分享的是", new_texts)
        self.assertIn("為女穿衣是排灣族的習俗", new_texts)
        self.assertNotIn("首播後段別的節目內容", new_texts)
        self.assertTrue(mentions(result["notes"], "1854.626"))

    def test_range_start_shrinks(self):
        """範圍起點落在重播集主播開場（6 集工作檔 prepare 範圍偏早約
        10 秒）：同一條規則對起點。"""
        off = 300.0
        body = program(lo=1000.0, count=20)
        src_lines = [(990.0, 999.5, "首播頭前別的內容句", {})] + body
        tgt_lines = [(1288.0, 1295.0, "各位觀眾大家好今天", {}),
                     (1295.2, 1299.9, "我們來看島語時間吧", {})]
        tgt_lines += shifted(body, off)
        src_cues, src_texts = build(src_lines)
        tgt_cues, tgt_texts = build(tgt_lines)
        result = port.port({"cues": src_cues}, src_texts,
                           {"cues": tgt_cues}, tgt_texts, 988.0, 1080.0, off)
        self.assertAlmostEqual(result["range"][0], 1299.9)
        kept = []
        for item in result["cues"]:
            kept.append(result["all_texts"][item["index"]])
        self.assertIn("各位觀眾大家好今天", kept)
        self.assertIn("我們來看島語時間吧", kept)

    def test_edge_cue_keeps_target_end(self):
        """邊緣那條同字不同長：「謝謝大家 掰掰」首播搬過來迄 1878.811、
        重播自己 1878.009（重播在那裡剪掉），要用重播的。"""
        off = -234.0
        body = program(lo=2000.0, count=10)
        last = (2110.3, 2112.811, "謝謝大家 掰掰", {"area": "島語時間"})
        src_cues, src_texts = build(body + [last])
        tgt_cues, tgt_texts = build(
            shifted(body, off) + [(1876.3, 1878.009, "謝謝大家 掰掰", {})])
        result = port.port({"cues": src_cues}, src_texts,
                           {"cues": tgt_cues}, tgt_texts, 2000.0, 2113.0,
                           off)
        final = result["cues"][-1]
        self.assertEqual(text_of(result, final["index"]), "謝謝大家 掰掰")
        self.assertAlmostEqual(final["end"], 1878.009)
        self.assertGreaterEqual(final["sample_ts"], final["start"])
        self.assertLessEqual(final["sample_ts"], final["end"])

    def test_edge_overlap_blank_trimmed_text_refused(self):
        """跟保留的空白 cue 重疊 0.133 秒（222 cue 444）→ 修短空白那條；
        跟有字的 cue 重疊 → 擋。"""
        off = 600.0
        body = program(lo=997.0, count=10)       # 第一條 997.3 → 1597.3
        src_cues, src_texts = build(body)
        tgt_lines = [(1590.0, 1595.0, own(1), {}),
                     (1596.178, 1597.433, "", {})]
        tgt_lines += own_cut(shifted(body, off))
        tgt_cues, tgt_texts = build(tgt_lines)
        result = port.port({"cues": src_cues}, src_texts,
                           {"cues": tgt_cues}, tgt_texts, 997.0, 1037.0, off)
        blank = None
        for item in result["cues"]:
            if item["index"] == result["moves"][2]:
                blank = item
        self.assertAlmostEqual(blank["end"], 1597.3)
        self.assertEqual(len(result["trimmed"]), 1)

        tgt_texts[2] = "這條有字不可以修"
        with self.assertRaises(PipelineError) as caught:
            port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                      tgt_texts, 997.0, 1037.0, off)
        self.assertIn("2", str(caught.exception))

    def test_moves_follow_identity_not_times(self):
        """範圍外改號要照身分不照 (start, end)：邊緣被修短的空白 cue 起迄
        變了，用時間鍵會對不到，TSV 那列被當成「被換掉」刪掉，之後那條 cue
        沒有 TSV 列。"""
        off = 600.0
        body = program(lo=997.0, count=10)
        src_cues, src_texts = build(body)
        tgt_lines = [(1596.178, 1597.433, "", {})] + own_cut(
            shifted(body, off))
        tgt_cues, tgt_texts = build(tgt_lines)
        result = port.port({"cues": src_cues}, src_texts,
                           {"cues": tgt_cues}, tgt_texts, 997.0, 1037.0, off)
        self.assertIn(1, result["moves"])
        self.assertNotIn(1, offband_backfill.moves(tgt_cues,
                                                   result["cues"]))
        rewritten, _name, _rows = port.port_tsvs(
            {"b01.tsv": [(1, "")]}, result, len(tgt_cues))
        self.assertEqual(rewritten["b01.tsv"], [(result["moves"][1], "")])


class TestPortedFields(unittest.TestCase):

    def test_ported_cue_fields(self):
        """搬進來的 cue `images` 要清空（首播的 `2-strips/t01571003_han.png`
        在重播集不存在）；`sample_ts` 要加位移、落在自己的起迄內。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair(off=742.275)
        src_book["cues"][3]["placed"] = True
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           742.275)
        source = src_book["cues"][3]
        new = result["ported"][source["index"]]
        item = result["cues"][new - 1]
        self.assertEqual(item["index"], new)
        self.assertEqual(item["images"], {})
        self.assertAlmostEqual(item["sample_ts"],
                               round(source["sample_ts"] + 742.275, 3))
        self.assertAlmostEqual(item["start"],
                               round(source["start"] + 742.275, 3))
        self.assertEqual(item["area"], "島語時間")
        self.assertEqual(item["frames"], source["frames"])
        self.assertEqual(item["ink"], source["ink"])
        self.assertTrue(item["placed"])
        for item in result["cues"]:
            self.assertLessEqual(item["start"], item["sample_ts"])
            self.assertLessEqual(item["sample_ts"], item["end"])

    def test_history_not_copied(self):
        """首播頂層的 `split`／`placed` 記的是首播的號碼，抄過去會指到重播
        集別條 cue；只加一筆 `ported`。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        src_book["split"] = [{"cue": 12, "at": 1040.0}]
        src_book["placed"] = [{"cue": 13}]
        tgt_book["split"] = [{"cue": 2, "at": 700.0}]
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           -234.0)
        book = port.new_book(tgt_book, src_book, result, SRC, lo, hi,
                             -234.0)
        self.assertEqual(book["split"], [{"cue": 2, "at": 700.0}])
        self.assertNotIn("placed", book)
        self.assertEqual(len(book["ported"]), 1)
        entry = book["ported"][0]
        self.assertEqual(entry["from"], SRC)
        self.assertEqual(entry["src_range"], [lo, hi])
        self.assertEqual(entry["offset"], -234.0)
        self.assertEqual(entry["added"], 30)
        self.assertEqual(entry["removed"], 30)
        self.assertEqual(entry["cues"], [3, 32])


# ------------------------------------------------------------ TSV


class TestTsv(unittest.TestCase):

    def setUp(self):
        (self.src_book, self.src_texts, self.tgt_book, self.tgt_texts,
         self.lo, self.hi) = pair()
        self.result = port.port(self.src_book, self.src_texts,
                                self.tgt_book, self.tgt_texts, self.lo,
                                self.hi, -234.0)

    def files(self):
        first = []
        second = []
        for number in sorted(self.tgt_texts):
            row = (number, self.tgt_texts[number])
            (first if number <= 15 else second).append(row)
        return {"b01.tsv": first, "b02.tsv": second}

    def test_tsv_each_cue_once(self):
        """每條 cue 只能在一份 TSV（`ingest` 會整集擋「cue 444 appears
        in both b02.tsv and b05.tsv」）；搬進來的字寫在新檔，舊檔裡範圍內的
        列要刪。"""
        rewritten, name, rows = port.port_tsvs(self.files(), self.result,
                                               len(self.tgt_book["cues"]))
        self.assertEqual(name, "b03.tsv")
        everything = dict(rewritten)
        everything[name] = rows
        port.check_cover(everything, len(self.result["cues"]))
        broken = dict(everything)
        broken["b01.tsv"] = list(broken["b01.tsv"]) + [rows[0]]
        with self.assertRaises(PipelineError) as caught:
            port.check_cover(broken, len(self.result["cues"]))
        self.assertIn("b01.tsv", str(caught.exception))
        self.assertIn("b03.tsv", str(caught.exception))

    def test_new_tsv_number_after_max(self):
        """新 TSV 編號用「最大號＋1」不是「檔數＋1」：有 b01、b02、b04 三
        個檔時，檔數＋1＝b04 會蓋掉既有的檔。"""
        self.assertEqual(port.next_tsv_name(["b01.tsv", "b02.tsv",
                                             "b04.tsv"]), "b05.tsv")
        self.assertEqual(port.next_tsv_name([]), "b01.tsv")

    def test_blank_source_text_still_has_row(self):
        """首播那條是空字（判不收）也要在新 TSV 寫一列空的，不然那條 cue
        沒有列。"""
        self.src_texts[15] = ""
        del self.src_texts[16]
        result = port.port(self.src_book, self.src_texts, self.tgt_book,
                           self.tgt_texts, self.lo, self.hi, -234.0)
        _rewritten, _name, rows = port.port_tsvs(
            self.files(), result, len(self.tgt_book["cues"]))
        numbers = []
        for number, _text in rows:
            numbers.append(number)
        self.assertIn(result["ported"][15], numbers)
        self.assertIn(result["ported"][16], numbers)
        self.assertIn((result["ported"][15], ""), rows)
        self.assertIn((result["ported"][16], ""), rows)

    def test_text_bytes_untouched(self):
        """文字一個 byte 都不動：讀者寫的尾端空白、`．`（U+FF0E）、族語
        撇號照抄。"""
        self.tgt_texts[1] = "Xuzi．Hakaw ’Acicim "
        self.src_texts[20] = "faki’ 　尾巴有全形空白　"
        result = port.port(self.src_book, self.src_texts, self.tgt_book,
                           self.tgt_texts, self.lo, self.hi, -234.0)
        rewritten, _name, rows = port.port_tsvs(
            self.files(), result, len(self.tgt_book["cues"]))
        self.assertIn((result["moves"][1], "Xuzi．Hakaw ’Acicim "),
                      rewritten["b01.tsv"])
        self.assertIn((result["ported"][20], "faki’ 　尾巴有全形空白　"), rows)


# ------------------------------------------------------------ 訂正紀錄


class TestFixes(unittest.TestCase):

    def setUp(self):
        (self.src_book, self.src_texts, self.tgt_book, self.tgt_texts,
         self.lo, self.hi) = pair()
        drop(self.tgt_book, self.tgt_texts, 20)       # 重播漏收一句
        self.src_texts[10] = "第008句萬用鐮"           # 首播範圍內
        self.result = port.port(self.src_book, self.src_texts,
                                self.tgt_book, self.tgt_texts, self.lo,
                                self.hi, -234.0)

    def test_fixes_outside_renumbered(self):
        """範圍外的 manual-fixes 列 cue 號照對應改（216 晚 walwalo'
        tinralom 1006→1045 那種）；「137–141」範圍兩端都改。"""
        last = len(self.tgt_book["cues"])
        rows = [[TGT, str(last), "walwalo’", "walwalo'", "撇號"],
                [TGT, "1–2", "永屋", "永久屋", "漏字"],
                [TGT, "", "傳神父", "傅神父", "全集"],
                ["20990101_001_午間_Amis_阿美", "5", "a", "b", "別集"]]
        got = port.port_fixes(rows, SRC, TGT, self.tgt_book["cues"],
                              self.result)
        self.assertEqual(self.result["moves"][last], last + 1)
        self.assertEqual(got[0][1], str(self.result["moves"][last]))
        self.assertEqual(got[1][1], "%d–%d" % (self.result["moves"][1],
                                               self.result["moves"][2]))
        self.assertEqual(got[2], rows[2])
        self.assertEqual(got[3], rows[3])

    def test_fixes_carried_from_source(self):
        """首播範圍內的訂正要抄給重播集（不然就是 095 午驗收被抓的「有訂正、
        沒紀錄」）。"""
        rows = [[SRC, "10", "萬用鐮", "萬用鏟", "明顯錯字"]]
        self.src_texts[10] = "第008句萬用鏟"
        result = port.port(self.src_book, self.src_texts, self.tgt_book,
                           self.tgt_texts, self.lo, self.hi, -234.0)
        got = port.port_fixes(rows, SRC, TGT, self.tgt_book["cues"], result)
        self.assertEqual(got[0], rows[0])
        self.assertEqual(len(got), 2)
        self.assertEqual(got[1][:4], [TGT, str(result["ported"][10]),
                                      "萬用鐮", "萬用鏟"])
        self.assertIn("移植自 %s cue 10" % SRC, got[1][4])

    def test_target_own_fix_refused(self):
        """重播範圍內自己的訂正、首播同處字不一樣（075「萬用鏟」修在
        075、129 還是「萬用鐮」）→ 擋：整段搬會把重播修好的蓋回去。"""
        removed = self.result["removed"][7]           # 重播舊號
        rows = [[TGT, str(removed), "萬用鐮", "萬用鏟", "明顯錯字"]]
        with self.assertRaises(PipelineError) as caught:
            port.port_fixes(rows, SRC, TGT, self.tgt_book["cues"],
                            self.result)
        self.assertIn("蓋掉", str(caught.exception))

        self.src_texts[10] = "第008句萬用鏟"
        result = port.port(self.src_book, self.src_texts, self.tgt_book,
                           self.tgt_texts, self.lo, self.hi, -234.0)
        got = port.port_fixes(rows, SRC, TGT, self.tgt_book["cues"], result)
        self.assertEqual(got, [[TGT, str(result["ported"][10]), "萬用鐮",
                                "萬用鏟", "明顯錯字"]])
        rows.append([SRC, "10", "萬用鐮", "萬用鏟", "明顯錯字"])
        got = port.port_fixes(rows, SRC, TGT, self.tgt_book["cues"], result)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0], rows[1])
        self.assertIn("移植自", got[1][4])

    def test_pending_fixes_cue_lines(self):
        """`pending-fixes.txt` 帶 cue 號的 sed（`/^N\\t/`，100 列）範圍外
        改號、範圍內擋；首播範圍內帶 cue 號的，補一列 manual-fixes。"""
        last = len(self.tgt_book["cues"])
        new = self.result["moves"][last]
        lines = [
            "%s\ts/^%d\\than\\t$/%d\\than\\t我的名字叫gagu/\t補齊"
            % (TGT_SLUG, last, last),
            "%s\t/^%d\\t/ s/傳神父/傅神父/g\t定案" % (TGT_SLUG, last),
            "%s\ts/彷佛/彷彿/g\t全集" % TGT_SLUG,
            "%s\ts/^12\\than\\t$/12\\than\\t回到部落/\t首播補齊" % SRC_SLUG,
        ]
        got, extra = port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                                       self.result)
        self.assertEqual(got[0], "%s\ts/^%d\\than\\t$/%d\\than\\t我的名字叫"
                         "gagu/\t補齊" % (TGT_SLUG, new, new))
        self.assertEqual(got[1], "%s\t/^%d\\t/ s/傳神父/傅神父/g\t定案"
                         % (TGT_SLUG, new))
        self.assertEqual(got[2:], lines[2:])
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0][:4], [TGT, str(self.result["ported"][12]),
                                        "（空白）", "回到部落"])

        inside = self.result["removed"][0]
        lines.append("%s\ts/^%d\\than\\t$/%d\\than\\t字/\t範圍內"
                     % (TGT_SLUG, inside, inside))
        with self.assertRaises(PipelineError):
            port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                              self.result)

    def test_pending_alternation_outside_renumbered(self):
        """多選一寫法 `^\\(N\\|M\\)`（pending 裡大括號寫法 18 列：200 晚、206 晚、
        251 午、013 晚…）範圍外也要改號：舊做法只認 `^N\\t`，`\\(` 開頭的整列
        原封不動抄過去，號碼指到別條字幕，沒有任何訊息。位址、`\\(N\\)`
        單一個、`\\(N\\than\\t…\\)` 包在大括號裡的都一樣。"""
        last = len(self.tgt_book["cues"])
        new = self.result["moves"][last]
        lines = [
            "%s\ts/^\\(2\\|%d\\)\\(\\than\\t.*\\)以工代賑/\\1\\2以工帶振/\t照畫面"
            % (TGT_SLUG, last),
            "%s\t/^\\(1\\|%d\\)\\than\\t/s/圖紋/圖文/\t照畫面" % (TGT_SLUG, last),
            "%s\ts/^\\(%d\\)\\than\\t$/\\1\\than\\t接納/\t花字" % (TGT_SLUG, last),
            "%s\ts/^\\(%d\\than\\t\\)所以/\\1那以/\t照畫面" % (TGT_SLUG, last),
        ]
        got, extra = port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                                       self.result)
        self.assertEqual(extra, [])
        self.assertEqual(got[0], "%s\ts/^\\(2\\|%d\\)\\(\\than\\t.*\\)以工代賑/"
                         "\\1\\2以工帶振/\t照畫面" % (TGT_SLUG, new))
        self.assertEqual(got[1], "%s\t/^\\(1\\|%d\\)\\than\\t/s/圖紋/圖文/\t照畫面"
                         % (TGT_SLUG, new))
        self.assertEqual(got[2], "%s\ts/^\\(%d\\)\\than\\t$/\\1\\than\\t接納/"
                         "\t花字" % (TGT_SLUG, new))
        self.assertEqual(got[3], "%s\ts/^\\(%d\\than\\t\\)所以/\\1那以/\t照畫面"
                         % (TGT_SLUG, new))

    def test_pending_alternation_inside_refused(self):
        """012 晚 `s/^\\(734\\|738\\|751\\|752\\|753\\)\\than\\t.*$/
        \\1\\than\\t/`（粉紅提問字卡清空）在移植範圍內：舊做法認不得、不擋，整段搬後
        734 變成「有一次跨年晚會在尖石」，日後套用把正確的字清空。範圍內
        一個號碼就要擋；跟範圍外的混在一起也擋。"""
        inside = self.result["removed"][0]
        for expr in ("s/^\\(%d\\)\\than\\t.*$/\\1\\than\\t/" % inside,
                     "s/^\\(1\\|%d\\)\\than\\t.*$/\\1\\than\\t/" % inside,
                     "/^\\(1\\|%d\\)\\than\\t/s/圖紋/圖文/" % inside):
            lines = ["%s\t%s\t提問字卡不收" % (TGT_SLUG, expr)]
            with self.assertRaises(PipelineError) as caught:
                port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                                  self.result)
            self.assertIn("要人看", str(caught.exception))

    def test_pending_unrecognized_cue_sed_refused(self):
        """`^` 後面接的不是認得的 cue 寫法（`7.4`、`\\(734\\|7..\\)`、
        `[0-9]\\{3\\}`）：分不出指哪幾條，不可以當成不帶號放過去。"""
        for expr in ("s/^7.4\\than\\t.*$/\\1\\than\\t/",
                     "s/^\\(734\\|7..\\)\\than\\t.*$/\\1\\than\\t/",
                     "s/^[0-9]\\{3\\}\\than\\t舊/新/"):
            lines = ["%s\t%s\t看不懂" % (TGT_SLUG, expr)]
            with self.assertRaises(PipelineError) as caught:
                port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                                  self.result)
            self.assertIn("看不懂", str(caught.exception))

    def test_pending_wildcard_cue_left_alone(self):
        """`^\\([0-9]*\\)`、`^\\([0-9]\\+\\than\\t\\)` 是照字找、不指號（104 午
        金句卡、026 午花字）：不擋、不改。"""
        lines = [
            "%s\ts/^\\([0-9]*\\)\\than\\t.*niqan gnklaan.*$/\\1\\than\\t/\t金句卡"
            % TGT_SLUG,
            "%s\ts/^\\([0-9]\\+\\than\\t\\)下次選金句$/\\1/\t花字" % TGT_SLUG,
        ]
        got, extra = port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                                       self.result)
        self.assertEqual(got, lines)
        self.assertEqual(extra, [])

    def test_pending_source_alternation_carried(self):
        """首播範圍內用多選一寫的訂正，每個號碼各補一列 manual-fixes——
        舊做法 `_sed_rows` 只認 `^N\\than\\t`，整列漏掉、訂正紀錄少了。"""
        lines = ["%s\ts/^\\(12\\|13\\)\\(\\than\\t.*\\)以工代賑/\\1\\2以工帶振/\t"
                 "照畫面" % SRC_SLUG]
        got, extra = port.port_pending(lines, SRC_SLUG, TGT_SLUG, SRC, TGT,
                                       self.result)
        self.assertEqual(got, lines)
        heads = []
        for row in extra:
            heads.append(row[:4])
        self.assertEqual(heads, [
            [TGT, str(self.result["ported"][12]), "以工代賑", "以工帶振"],
            [TGT, str(self.result["ported"][13]), "以工代賑", "以工帶振"]])


class TestSedCues(unittest.TestCase):
    """pending-fixes.txt 裡實際出現過的帶號寫法（2026-10-28 全檔 683 列）。
    `[[:space:]]` 當 tab 的 4 列（`/^469[[:space:]]/`）舊做法也認不得。"""

    def test_numbers_of_every_shape(self):
        cases = [
            ("s/^\\(734\\|738\\|751\\|752\\|753\\)\\than\\t.*$/\\1\\than\\t/",
             {734, 738, 751, 752, 753}),
            ("s/^\\(1049\\|106[2-5]\\|109[015]\\|1089\\|110[45]\\)"
             "\\than\\t.*$/\\1\\than\\t/",
             {1049, 1062, 1063, 1064, 1065, 1090, 1091, 1095, 1089, 1104,
              1105}),
            ("s/^695\\than\\t$/695\\than\\t參與的時候/; s/^\\(71[34]\\)\\than\\t$/"
             "\\1\\than\\t接納 瞬間的那種/", {695, 713, 714}),
            ("s/^\\(682\\than\\t\\)所以/\\1那以/", {682}),
            ("s/^\\(22[12]\\than\\t藉由\\)手紋/\\1手文/", {221, 222}),
            ("/^\\(724\\|728\\|735\\)\\than\\t/s/圖紋/圖文/", {724, 728, 735}),
            ("/^802\\t/ s/看得到/看的到/", {802}),
            ("/^92[567][[:space:]]/s/拉阿魯哇/拉阿魯瓦/", {925, 926, 927}),
            ("/^469[[:space:]]/s/(米粒織/(粒織/", {469}),
            ("s/^802\\than\\t舊/803\\than\\t新/", {802, 803}),
            ("s/^\\([0-9]\\+\\than\\t\\)下次選金句$/\\1/", set()),
            ("s/\\([0-9]\\)．\\([0-9]\\)/\\1.\\2/g", set()),
            ("s/Kingdalruan\\([^e]\\|$\\)/Kingdalruane\\1/g", set()),
        ]
        for expr, numbers in cases:
            self.assertEqual(port._sed_cues(expr), numbers, expr)

    def test_renumber_keeps_shape(self):
        """改號照原本的寫法：多選一逐個換；`[34]` 換完還能寫成同一個字首
        就留字元類，不行而且是獨立的一個選項就拆成 `\\|`；號碼沒變的整段
        原樣。"""
        expr = ("s/^\\(1049\\|106[2-5]\\|71[34]\\)\\than\\t.*$/\\1\\than\\t/")
        moves = {1049: 1050, 1062: 1063, 1063: 1064, 1064: 1065, 1065: 1066,
                 713: 713, 714: 714}
        self.assertEqual(port._renumber_sed(expr, moves),
                         "s/^\\(1050\\|106[3456]\\|71[34]\\)\\than\\t.*$/"
                         "\\1\\than\\t/")
        moves[1065] = 1070
        self.assertEqual(port._renumber_sed(expr, moves),
                         "s/^\\(1050\\|1063\\|1064\\|1065\\|1070\\|71[34]\\)"
                         "\\than\\t.*$/\\1\\than\\t/")

    def test_renumber_embedded_class_unrepresentable_refused(self):
        """`\\(22[12]\\than\\t藉由\\)` 的字元類包在大括號中間，換完不同字首
        （229、231）寫不回字元類，也不能拆 `\\|`（會連後面的字一起分開）：擋。"""
        expr = "s/^\\(22[12]\\than\\t藉由\\)手紋/\\1手文/"
        self.assertEqual(port._renumber_sed(expr, {221: 222, 222: 223}),
                         "s/^\\(22[23]\\than\\t藉由\\)手紋/\\1手文/")
        with self.assertRaises(PipelineError):
            port._renumber_sed(expr, {221: 229, 222: 231})


# ------------------------------------------------------------ 段落表、areas


def seg(start, end, kind, top="", bottom="", language="噶瑪蘭"):
    return {"起秒": start, "迄秒": end, "類型": kind, "單元語別": language,
            "字幕上緣y": top, "字幕下緣y": bottom,
            segments.INTERVIEWEE: "無", segments.SPEECH: "無"}


class TestSegments(unittest.TestCase):

    def test_segments_replaced_by_source_rows(self):
        """222 晚被 2542–2564 切成兩列的帶外專題要併回一列，上下緣
        690–1040 換成首播的 940–1060。"""
        target = [seg("0", "1690", "攝影棚", "722", "848"),
                  seg("1690", "2542", "帶外專題", "690", "1040"),
                  seg("2542", "2564", "其他"),
                  seg("2564", "2800", "帶外專題", "690", "1040"),
                  seg("2800", "2900", "攝影棚", "722", "848")]
        source = [seg("0", "1590", "攝影棚", "722", "848"),
                  seg("1590", "2700", "帶外專題", "940", "1060"),
                  seg("2700", "2800", "攝影棚", "722", "848")]
        got = port.port_segments(target, source, 1690.0, 2800.0, 100.0)
        spans = []
        for row in got:
            spans.append((row["起秒"], row["迄秒"], row["類型"],
                          row["字幕上緣y"], row["字幕下緣y"]))
        self.assertEqual(spans, [("0", "1690", "攝影棚", "722", "848"),
                                 ("1690", "2800", "帶外專題", "940", "1060"),
                                 ("2800", "2900", "攝影棚", "722", "848")])

    def test_segments_snap_to_target_edges(self):
        """位移不是整數，新列邊會變成 1597.049 這種；跟重播原本列邊差
        ≤ 3 秒就用重播的，避免 1–2 秒碎列。"""
        off = 742.275
        target = [seg("0", "1597", "攝影棚", "722", "848"),
                  seg("1597", "2800", "其他"),
                  seg("2800", "2900", "攝影棚", "722", "848")]
        source = [seg("0", "855", "攝影棚", "722", "848"),
                  seg("855", "1300", "島語時間", "940", "1060"),
                  seg("1300", "2000", "攝影棚", "722", "848")]
        got = port.port_segments(target, source, 1597.275, 2042.275, off)
        edges = []
        for row in got:
            edges.append(row["起秒"])
        self.assertEqual(edges, ["0", "1597", "2042.275", "2800"])
        for row in got:
            self.assertGreater(float(row["迄秒"]) - float(row["起秒"]), 3.0)

    def test_segments_basis_filled(self):
        """寫進臨時 work dir 的表要有「依據」，不然 `segments.check` 擋、
        publish 印「段落表 wait」。"""
        target = [seg("0", "1690", "攝影棚", "722", "848"),
                  seg("1690", "2900", "其他")]
        source = [seg("0", "1590", "攝影棚", "722", "848"),
                  seg("1590", "2700", "島語時間", "940", "1060")]
        got = port.port_segments(target, source, 1690.0, 2800.0, 100.0)
        for row in got:
            self.assertIn(row["依據"], segments.BASES)
        self.assertEqual(segments.check(got, TGT, 2900.0), [])

    def test_areas_conflict_refused(self):
        """一個類型只記一格：重播範圍外還有 cue 用同類型的別的 preset
        （259、290 已有 island 的島語時間）→ 擋。"""
        mine = {"島語時間": {"preset": "titv-news-island-high",
                         "region": [0, 900, 1920, 120]}}
        theirs = {"島語時間": {"preset": "titv-news-island",
                           "region": [0, 940, 1920, 120]}}
        ported = [{"area": "島語時間"}]
        with self.assertRaises(PipelineError):
            port.port_areas(mine, theirs, ported, [{"area": "島語時間"}])
        got = port.port_areas(mine, theirs, ported, [{}])
        self.assertEqual(got, theirs)


# ------------------------------------------------------------ 入庫


class Store(object):

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.store = port.Store(
            cues=os.path.join(root, "1-cues"),
            vision=os.path.join(root, "2-vision"),
            srt=os.path.join(root, "3-srt"),
            segments=os.path.join(root, "0-segments"),
            sapolita=os.path.join(root, "sapolita"),
            asr_raw=os.path.join(root, "asr-raw"),
            work=os.path.join(root, "work"),
            fixlog=os.path.join(root, "訂正紀錄.csv"),
            pairs=os.path.join(root, "pairs"),
            paragraph=os.path.join(root, "paragraph"),
            root=root)
        self.root = root
        self.entries = [{"srt_name": SRC, "slug": SRC_SLUG},
                        {"srt_name": TGT, "slug": TGT_SLUG}]

    def put(self, name, book, texts, table):
        path = self.store.timeline(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(book, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
        folder = self.store.vision_dir(name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            for number in sorted(texts):
                handle.write("%d\than\t%s\n" % (number, texts[number]))
        path = self.store.segments_file(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        segments.write_store(path, table)

    def snapshot(self, snaps, name, tag, book=None, texts=None):
        """照 snap.sh 的樣子：<snaps>/<集>--<標籤>/files/ 底下照 Kari-SRT 的
        相對路徑放；book 沒給就抄現在的。"""
        folder = os.path.join(snaps, "%s--%s" % (name, tag))
        files = self.store.under(os.path.join(folder, "files"))
        if book is None:
            loaded = port.load(name, self.store)
            book, texts = loaded["book"], loaded["texts"]
        path = files.timeline(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(book, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
        vision = files.vision_dir(name)
        os.makedirs(vision, exist_ok=True)
        with open(os.path.join(vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            for number in sorted(texts):
                handle.write("%d\than\t%s\n" % (number, texts[number]))
        with open(os.path.join(folder, "manifest.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write(path + "\n")
        return folder


class ApplyCase(unittest.TestCase):
    """整段搬的入庫測試共用：重播島語時間整段沒讀到。"""

    def setUp(self):
        self.box = Store()
        self.addCleanup(self.box.tmp.cleanup)
        (src_book, src_texts, tgt_book, tgt_texts, self.lo,
         self.hi) = pair(off=-234.0)
        src_book["duration"] = 1300.0
        tgt_book["duration"] = 1100.0
        drop(tgt_book, tgt_texts, 20)
        for number in range(3, 32):              # 重播島語時間整段沒讀到
            tgt_texts[number] = ""
        tgt_book["areas"] = {"部落信箱": {"preset": "titv-news-mailbox",
                                      "region": [0, 600, 1920, 380]}}
        self.box.put(SRC, src_book, src_texts,
                     [seg("0", "1000", "攝影棚", "722", "848"),
                      seg("1000", "1120", "島語時間", "940", "1060"),
                      seg("1120", "1300", "攝影棚", "722", "848")])
        self.box.put(TGT, tgt_book, tgt_texts,
                     [seg("0", "766", "攝影棚", "722", "848"),
                      seg("766", "886", "其他"),
                      seg("886", "1100", "攝影棚", "722", "848")])
        self.out = os.path.join(self.box.root, "out")
        self.fixes = os.path.join(self.box.root, "manual-fixes.tsv")
        with open(self.fixes, "w", encoding="utf-8") as handle:
            handle.write("%s\t%d\ta\tb\t範圍外\n" % (TGT, len(tgt_texts)))
        self.pending = os.path.join(self.box.root, "pending-fixes.txt")
        with open(self.pending, "w", encoding="utf-8") as handle:
            handle.write("%s\ts/彷佛/彷彿/g\t全集\n" % TGT_SLUG)
        self.lock = os.path.join(self.box.root, "store.lock")
        self.calls = []
        self.work = os.path.join(self.box.root, "units", "expand",
                                 "%s--from-%s.json" % (TGT, SRC))
        os.makedirs(os.path.dirname(self.work))
        with open(self.work, "w", encoding="utf-8") as handle:
            json.dump({"items": [{"seconds": "766-886"}]}, handle,
                      ensure_ascii=False, indent=2, sort_keys=True)

    def hooks(self):
        return {"pairs": self.calls.append,
                "fixlog": lambda path: self.calls.append(("fixlog", path))}

    def prepare(self):
        return port.prepare(SRC, TGT, self.lo, self.hi, self.out,
                            store=self.box.store, fixes=self.fixes,
                            pending=self.pending, entries=self.box.entries,
                            work=self.work, offset=-234.0)

    def apply(self, hooks=None):
        return port.apply(os.path.join(self.out, "plan.json"), self.lock,
                          self.fixes, pending=self.pending,
                          no_frames="合成測試沒有影片", store=self.box.store,
                          entries=self.box.entries,
                          snaps=os.path.join(self.box.root, "snap"),
                          hooks=hooks or self.hooks())


class TestApply(ApplyCase):

    def test_temp_workdir_keeps_store_areas(self):
        """臨時 work dir 的時間軸要帶 Kari-SRT 全部 `areas`，否則
        `areas_only_in_store` 判成過期、整集 skip。"""
        plan = self.prepare()
        self.assertEqual(plan["status"], "ready", plan.get("reasons"))
        work = os.path.join(self.box.root, "tmpwork")
        port.temp_workdir(work, os.path.join(self.out, "preview"))
        with open(os.path.join(work, "3-refined", "cues.json"),
                  encoding="utf-8") as handle:
            book = json.load(handle)
        self.assertTrue(book["refined"])
        self.assertIn("部落信箱", book["areas"])
        self.assertIn("島語時間", book["areas"])
        timeline = os.path.join(work, "3-refined", "cues.json")
        entry = {"srt_name": TGT, "slug": TGT_SLUG}
        self.assertEqual(publish.areas_only_in_store(entry, timeline,
                                                     self.box.store.cues),
                         [])

    def test_apply_refuses_changed_inputs(self):
        """prepare 之後重播或首播被改過（sha 不同）→ apply 擋，重做
        prepare。"""
        self.prepare()
        tsv = os.path.join(self.box.store.vision_dir(TGT), "b01.tsv")
        with open(tsv, "a", encoding="utf-8") as handle:
            handle.write("")
        with open(tsv, encoding="utf-8") as handle:
            body = handle.read()
        with open(tsv, "w", encoding="utf-8") as handle:
            handle.write(body.replace("本集001", "本集一"))
        with open(self.box.store.timeline(TGT), encoding="utf-8") as handle:
            before = handle.read()
        with self.assertRaises(PipelineError) as caught:
            self.apply()
        self.assertIn("prepare", str(caught.exception))
        with open(self.box.store.timeline(TGT), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), before)

    def test_apply_refuses_without_frames_check(self):
        """像素驗收沒有判過就擋，除非帶了理由（使用者同意過才可以免做）。"""
        self.prepare()
        with self.assertRaises(PipelineError):
            port.apply(os.path.join(self.out, "plan.json"), self.lock,
                       self.fixes, pending=self.pending,
                       store=self.box.store, entries=self.box.entries,
                       hooks=self.hooks())

    def test_tsv_whose_rows_all_replaced_is_removed(self):
        """某一份 TSV 的列全在範圍內（島語時間整段一批讀的）：換掉後是空檔，
        要刪掉，不在 Kari-SRT 留一個 0 byte 的 bNN.tsv。"""
        folder = self.box.store.vision_dir(TGT)
        rows = port.read_tsv(os.path.join(folder, "b01.tsv"))
        inside = []
        outside = []
        for number, text in rows:
            (inside if 3 <= number <= 31 else outside).append((number, text))
        with open(os.path.join(folder, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write(port.tsv_text(outside))
        with open(os.path.join(folder, "b02.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write(port.tsv_text(inside))
        plan = self.prepare()
        self.assertEqual(plan["tsv"]["emptied"], ["b02.tsv"])
        self.assertEqual(plan["tsv"]["new"], "b03.tsv")
        self.apply()
        self.assertEqual(sorted(os.listdir(folder)), ["b01.tsv", "b03.tsv"])

    def test_existing_workdir_retired(self):
        """重播原本有 work dir：apply 前要改名 `.stale-MMDD`，否則之後的
        publish 會把舊時間軸蓋回來（20241209_344 踩過兩次）。"""
        from scripts.news import paths
        work = paths.work_dir(TGT_SLUG, self.box.store.work)
        os.makedirs(os.path.join(work, "3-refined"))
        self.prepare()
        self.apply()
        self.assertFalse(os.path.exists(work))
        stale = []
        for name in os.listdir(os.path.dirname(work)):
            if ".stale-" in name:
                stale.append(name)
        self.assertEqual(len(stale), 1)

        with open(self.box.store.timeline(TGT), encoding="utf-8") as handle:
            book = json.load(handle)
        self.assertEqual(book["ported"][0]["from"], SRC)
        self.assertIn("島語時間", book["areas"])
        self.assertIn("部落信箱", book["areas"])
        folder = self.box.store.vision_dir(TGT)
        self.assertEqual(sorted(os.listdir(folder)), ["b01.tsv", "b02.tsv"])
        srt = self.box.store.srt_file(TGT)
        with open(srt, encoding="utf-8") as handle:
            self.assertIn(say(5), handle.read())
        table = segments.read(self.box.store.segments_file(TGT))
        kinds = []
        for row in table:
            kinds.append(row["類型"])
        self.assertEqual(kinds, ["攝影棚", "島語時間", "攝影棚"])
        with open(self.fixes, encoding="utf-8") as handle:
            fixed = handle.read()
        self.assertIn("%s\t%d\ta\tb" % (TGT, len(book["cues"])), fixed)
        backups = []
        for name in os.listdir(self.box.root):
            if name.startswith("manual-fixes.tsv.bak-"):
                backups.append(name)
        self.assertEqual(len(backups), 1)
        self.assertIn(TGT, self.calls)
        self.assertIn(("fixlog", self.fixes), self.calls)

        # 剛搬完再 prepare：重播那段已經有字、切法一樣，改走分區搬；首播
        # 快照跟現在一樣，沒有首播改過的地方。
        snaps = os.path.join(self.box.root, "snap")
        self.box.snapshot(snaps, SRC, "main")
        again = port.prepare(SRC, TGT, self.lo, self.hi,
                             os.path.join(self.box.root, "again"),
                             store=self.box.store, fixes=self.fixes,
                             pending=self.pending, entries=self.box.entries,
                             snaps=snaps)
        self.assertEqual(again["mode"], "zone")
        self.assertEqual(again["status"], "ready", again["reasons"])
        self.assertEqual(again["summary"]["applied"], 0)
        self.assertEqual(again["summary"]["ask"], 0)


# ------------------------------------------------------------ 像素驗收


def frames_seq(count, seed):
    generator = numpy.random.default_rng(seed)
    return generator.integers(0, 256, size=(count, 27, 48)).astype(
        numpy.float64)


class TestFrames(unittest.TestCase):

    def points(self, source, target, shift):
        out = []
        for k in range(3, 12):
            out.append({"kind": "inside",
                        "same": port.mad(source[k], target[k + shift]),
                        "minus": port.mad(source[k], target[k + shift - 1]),
                        "plus": port.mad(source[k], target[k + shift + 1])})
        return out

    def test_frames_judge_thresholds(self):
        """像素：同位移 MAD 0.50–0.72、±1 格 0.84–8.58、+5 秒 7.8–64.0；
        合成兩支只差位移的小圖序列，同位移要過、差一格要判出局部最小在
        正確那格。"""
        source = frames_seq(16, 1)
        noise = numpy.random.default_rng(2).normal(0, 0.6, source.shape)
        target = numpy.clip(source + noise, 0, 255)
        verdict = port.judge_frames(self.points(source, target, 0))
        self.assertTrue(verdict["ok"], verdict["problems"])
        self.assertFalse(port.judge_frames(
            self.points(source, target, 1))["ok"])
        costs = {}
        for shift in (-2, -1, 0, 1, 2):
            row = []
            for k in range(4, 10):
                row.append(port.mad(source[k], target[k + shift]))
            costs[shift] = row
        self.assertEqual(port.pixel_locate(costs), 0)

    def test_frames_static_ties_tolerated(self):
        """靜態畫面 ±1 格打平（0.84 對 0.50）不可以每點都要求嚴格局部最小；
        332 晚→089 晚遮掉台標、天氣框後內部點也只有 3/7 是嚴格局部最小（其餘打平、
        沒有一點是鄰格更像）。打平的點不算數，嚴格局部最小的比例到
        MATCH_SHARE 就過，不到就擋。"""
        sharp = {"kind": "inside", "same": 0.5, "minus": 5.0, "plus": 6.0}
        flat = {"kind": "inside", "same": 0.5, "minus": 0.55, "plus": 0.5}
        total = 21
        need = int(math.ceil(port.MATCH_SHARE * total - 1e-9))
        self.assertTrue(port.judge_frames(
            [sharp] * need + [flat] * (total - need))["ok"])
        self.assertFalse(port.judge_frames(
            [sharp] * (need - 1) + [flat] * (total - need + 1))["ok"])
        self.assertIsNone(port.pixel_locate({-1: [0.5], 0: [0.5],
                                             1: [0.52]}))

    def test_frames_mask_station_logo_and_weather_box(self):
        """332 晚(2023)→089 晚(2021)：2021 的台標（左上，384×216 縮圖 x
        20–62、y 16–42）和天氣框（左下，x 20–80、y 170–206）跟 2023 不同，
        同位移 MAD 光這兩塊就墊高 1.0 左右，位移對的也過不了 1.5。遮掉再比：
        只有這兩塊不同的兩張圖要算成 0。"""
        generator = numpy.random.default_rng(7)
        source = generator.integers(0, 256, size=(216, 384)).astype(float)
        target = source.copy()
        for x0, y0, x1, y1 in ((20, 16, 62, 42), (20, 170, 80, 206)):
            target[y0:y1, x0:x1] = 255 - target[y0:y1, x0:x1]
        self.assertGreater(port.mad(source, target), 1.5)
        self.assertEqual(port.frame_mad(source, target), 0.0)
        # 025 午(2024)→026 午(2023)：人名字卡（x 80–384、y 180–205）只有
        # 2024 那次有，四角遮完同位移 MAD 底還有 7.06，位移對的也不過；
        # 字卡在字幕帶下面，整條底部遮掉。字幕帶（1080 高的 y 722–844，
        # 縮圖 y 144–168）不可以遮：要比的就是它。
        named = source.copy()
        named[180:205, 80:384] = 255 - named[180:205, 80:384]
        self.assertEqual(port.frame_mad(source, named), 0.0)
        subtitle = source.copy()
        subtitle[150:166, 150:300] = 255 - subtitle[150:166, 150:300]
        self.assertGreater(port.frame_mad(source, subtitle), 0.0)
        hidden = 0
        for x0, y0, x1, y1 in port.MASK:
            if y1 > 144 / 216.0 and y0 < 168 / 216.0 and x1 - x0 > 0.3:
                hidden += 1
        self.assertEqual(hidden, 0, "字幕帶被遮掉了")
        # 遮罩照比例：縮圖大小不同（測試的 48×27）照樣遮對位置。
        small = generator.integers(0, 256, size=(27, 48)).astype(float)
        other = small.copy()
        other[2:5, 3:7] = 255 - other[2:5, 3:7]
        self.assertEqual(port.frame_mad(small, other), 0.0)
        middle = small.copy()
        middle[12:15, 20:28] = 255 - middle[12:15, 20:28]
        self.assertGreater(port.frame_mad(small, middle), 0.0)

    def test_frames_cross_year_judged_by_local_minimum(self):
        """332 晚→089 晚（遮掉台標、天氣框）：同位移 MAD 底仍有 1.2 左右（2021 整體
        偏亮），舊的絕對門檻 1.5 擋掉 48 個點。泛白轉場那點同位移 66.0
        （±1 格 67.6／72.0）、範圍頭的片頭字卡那點 77.5（兩集片頭不同）是
        「畫面不同」，74 個邊界點裡只有這兩點，不到一成，不擋。位移對的
        要過；差一格時 74 個點裡 51 點是鄰格更像，要擋。"""
        def point(kind, same, minus, plus):
            return {"kind": kind, "same": same, "minus": minus, "plus": plus}
        good = []
        for _k in range(3):
            good.append(point("inside", 1.3, 1.9, 2.4))
        for _k in range(4):
            good.append(point("inside", 1.3, 1.35, 1.32))
        for _k in range(50):
            good.append(point("edge", 1.2, 1.8, 2.6))
        for _k in range(20):
            good.append(point("edge", 1.2, 1.25, 1.22))
        good.append(point("edge", 1.3, 1.15, 1.25))      # 鄰格稍好的兩點
        good.append(point("edge", 1.3, 1.25, 1.18))
        good.append(point("edge", 66.0, 67.6, 72.0))     # 泛白轉場
        good.append(point("edge", 77.5, 77.6, 77.3))     # 片頭字卡
        verdict = port.judge_frames(good)
        self.assertTrue(verdict["ok"], verdict["problems"])
        shifted_points = []
        for item in good:
            if item["same"] < 10 and len(shifted_points) < 55:
                # 差一格：原本同位移那格變成鄰格。
                shifted_points.append(point(item["kind"], item["minus"],
                                            item["same"], item["plus"] + 1))
            else:
                shifted_points.append(item)
        self.assertFalse(port.judge_frames(shifted_points)["ok"])

    def test_frames_different_footage_everywhere_refused(self):
        """範圍整段給錯（兩集根本不是同一段畫面）：每點同位移、±1 格都在
        60 上下，誰小誰大是隨機的，碰巧有三成是局部最小；底值也是 60。
        改成比鄰格之後，這種不可以因為「相對」而過。"""
        generator = numpy.random.default_rng(11)
        points = []
        for _k in range(30):
            same, minus, plus = generator.uniform(55.0, 65.0, size=3)
            points.append({"kind": "inside", "same": float(same),
                           "minus": float(minus), "plus": float(plus)})
        self.assertFalse(port.judge_frames(points)["ok"])

    def test_frames_edge_point_must_match(self):
        """邊界點放在兩集都該相同的畫面（套用區外緣、被換的 cue 外側），
        同位移 MAD 63.7（076 剪回棚內那種）就是範圍或位移錯了，要判失敗。"""
        sharp = {"kind": "inside", "same": 0.6, "minus": 5.0, "plus": 6.0}
        self.assertTrue(port.judge_frames([sharp] * 6)["ok"])
        edge = {"kind": "edge", "same": 63.7}
        self.assertFalse(port.judge_frames([sharp] * 6 + [edge])["ok"])

    def test_probe_times_at_frame_centres(self):
        """取樣時間要取格中心，貼著換格的邊會抽到前後格（runbook：概略
        -ss 在 5 fps 有 ±1 格誤差，判反過 13 條）。"""
        edge = 300 * F
        self.assertAlmostEqual(port.frame_centre(edge), 300.5 * F)
        self.assertAlmostEqual(port.frame_centre(edge - 1e-9), 299.5 * F)
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        tgt_texts[15] = "重播原本讀法不同"
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           -234.0)
        probes = port.probe_points(result, -234.0, holes=[(1040.0, 1110.0)])
        kinds = []
        for probe in probes:
            kinds.append(probe["kind"])
            for key in ("src", "tgt"):
                frame = probe[key] / F
                self.assertAlmostEqual(frame - int(frame), 0.5, places=6)
        self.assertGreaterEqual(kinds.count("inside"), 6)
        self.assertEqual(kinds.count("edge"), 2)
        self.assertEqual(kinds.count("hole"), 1)
        self.assertEqual(len(result["changed"]), 1)
        changed = result["cues"][result["changed"][0] - 1]
        want = port.frame_centre((changed["start"] + changed["end"]) / 2.0)
        hit = False
        for probe in probes:
            if probe["kind"] == "inside" and abs(probe["tgt"] - want) < 1e-6:
                hit = True
        self.assertTrue(hit, "字改掉的 cue 要有取樣點")


# ------------------------------------------------------------ 家族


class TestFamily(unittest.TestCase):

    def test_family_replays_every_source_without_canon(self):
        """251 午泰雅島語時間一家：251、254、262 各修了一部分（「歐伊歐伊
        歐....」「橙花的精油」「每日一善」是 254、262 修的，251 沒有）。挑
        251 當定本、收齊 0 步，294／295 的 from-262 工作檔移植完還是
        沒做，也沒報。改成每份工作檔各自重放、不湊定本；本身也是重播的首播
        （262）先收，沒有工作檔的組合要列出來。"""
        units = [
            {"unit": "262--from-251", "target": "262", "source": "251",
             "items": 44},
            {"unit": "254--from-251", "target": "254", "source": "251",
             "items": 41},
            {"unit": "294--from-251", "target": "294", "source": "251",
             "items": 42},
            {"unit": "294--from-262", "target": "294", "source": "262",
             "items": 3},
            {"unit": "295--from-262", "target": "295", "source": "262",
             "items": 3},
        ]
        got = port.family_order(units)
        self.assertNotIn("canon", got)
        names = []
        for step in got["steps"]:
            self.assertEqual(step["do"], "port")
            names.append(step["unit"])
        want = []
        for unit in units:
            want.append(unit["unit"])
        self.assertEqual(sorted(names), sorted(want))
        self.assertLess(names.index("262--from-251"),
                        names.index("294--from-262"))
        self.assertLess(names.index("262--from-251"),
                        names.index("295--from-262"))
        self.assertIn(["251", "295"], got["uncovered"])
        self.assertIn(["262", "254"], got["uncovered"])
        self.assertNotIn(["251", "294"], got["uncovered"])

    def test_family_topological_order_for_chains(self):
        """A→B→C→D 的鏈：只照檔名排、只排一層，C→D 可能排在 B→C 前面，B→C
        就看不到 A→B 搬進來的修改。要拓樸排序；互相補（075↔129）的列成
        循環，交給人。"""
        units = [
            {"unit": "aaa", "source": "C", "target": "D", "items": 1},
            {"unit": "mmm", "source": "B", "target": "C", "items": 1},
            {"unit": "zzz", "source": "A", "target": "B", "items": 1},
        ]
        got = port.family_order(units)
        names = []
        for step in got["steps"]:
            names.append(step["unit"])
        self.assertEqual(names, ["zzz", "mmm", "aaa"])
        self.assertEqual(got["cycles"], [])
        loop = [{"unit": "u1", "source": "075", "target": "129", "items": 1},
                {"unit": "u2", "source": "129", "target": "075", "items": 1}]
        got = port.family_order(loop)
        self.assertEqual(got["cycles"], [["u1", "u2"]])
        self.assertEqual(len(got["steps"]), 2)

    def test_family_cycle_lists_only_episodes_in_the_loop(self):
        """一家裡只要有一組互相補的（B↔C），舊做法就把剩下全部丟進「循環」、
        照檔名排：475 步裡 296 步這樣被丟進去，循環以外還有 16 處順序顛倒
        （020→358 排在 307→020 前面）。要用強連通分量把真的互相依賴的縮成
        一個點，循環只列那幾份，環外照依賴排。"""
        units = [
            {"unit": "a1", "source": "D", "target": "E", "items": 1},
            {"unit": "a2", "source": "C", "target": "D", "items": 1},
            {"unit": "m1", "source": "B", "target": "C", "items": 1},
            {"unit": "m2", "source": "C", "target": "B", "items": 1},
            {"unit": "z9", "source": "A", "target": "B", "items": 1},
        ]
        got = port.family_order(units)
        self.assertEqual(got["cycles"], [["m1", "m2"]])
        names = []
        for step in got["steps"]:
            names.append(step["unit"])
        self.assertEqual(sorted(names), ["a1", "a2", "m1", "m2", "z9"])
        for first, later in (("z9", "m1"), ("z9", "m2"), ("m1", "a2"),
                             ("m2", "a2"), ("a2", "a1")):
            self.assertLess(names.index(first), names.index(later),
                            (first, later, names))

    def test_family_second_round_after_first_round(self):
        """同一對首播→重播的第二輪工作檔 `<重播>--from-<首播>-r3.json` 照檔名
        排會排在第一輪 `<重播>--from-<首播>.json` 前面（`-` 比 `.` 小），
        216 就是這樣：第二輪先做、第一輪後做，第一輪會把第二輪補的蓋掉。
        同一對的要照輪次排：沒有 -rN 的是第一輪，接著 -r2、-r3…。"""
        first = "B--from-20230815_227_午間_Kavalan_噶瑪蘭.json"
        units = [
            {"unit": "B--from-20230815_227_午間_Kavalan_噶瑪蘭-r3.json",
             "source": "A", "target": "B"},
            {"unit": "B--from-20230815_227_午間_Kavalan_噶瑪蘭-r10.json",
             "source": "A", "target": "B"},
            {"unit": first, "source": "A", "target": "B"},
            {"unit": "C--from-B.json", "source": "B", "target": "C"},
        ]
        names = []
        for step in port.family_order(units)["steps"]:
            names.append(step["unit"])
        self.assertEqual(names, [
            first,
            "B--from-20230815_227_午間_Kavalan_噶瑪蘭-r3.json",
            "B--from-20230815_227_午間_Kavalan_噶瑪蘭-r10.json",
            "C--from-B.json"])

    def test_family_cycle_steps_marked(self):
        """環內的步驟（B↔C）只列在 cycles，steps 裡看不出哪幾步在環裡，批次
        照 steps 跑就會把環內的也自動做掉——075↔129 互相補，誰先做都會蓋
        掉另一邊。steps 上要標 `cycle: <組號>`（組號＝cycles 裡第幾組，從 1
        起算），環外的不標。"""
        units = [
            {"unit": "a1", "source": "D", "target": "E", "items": 1},
            {"unit": "m1", "source": "B", "target": "C", "items": 1},
            {"unit": "m2", "source": "C", "target": "B", "items": 1},
            {"unit": "q1", "source": "E", "target": "F", "items": 1},
            {"unit": "q2", "source": "F", "target": "E", "items": 1},
            {"unit": "z9", "source": "A", "target": "B", "items": 1},
        ]
        got = port.family_order(units)
        self.assertEqual(len(got["cycles"]), 2)
        marks = {}
        for step in got["steps"]:
            marks[step["unit"]] = step.get("cycle")
        for number, members in enumerate(got["cycles"], 1):
            for unit in members:
                self.assertEqual(marks[unit], number, unit)
        self.assertIsNone(marks["a1"])
        self.assertIsNone(marks["z9"])
        self.assertEqual(marks["m1"], marks["m2"])
        self.assertNotEqual(marks["m1"], marks["q1"])

    def test_family_irregular_unit_names_not_read_as_episodes(self):
        """`--from-r3fix1027r2x`、`--from-userrecut1023`、`--from-b1fix1027r2x`
        是那一集自己的修正單元，不是移植；`--from-<首播>-r3.json` 是同一個
        首播的第二輪。舊做法把 `--from-` 後面整串當集名去讀時間軸，
        PipelineError 一出來整個 family 當掉（對 expand 目錄跑就會）。"""
        self.assertEqual(port.unit_source("20230815_227_午間_Kavalan_噶瑪蘭-r3"),
                         "20230815_227_午間_Kavalan_噶瑪蘭")
        self.assertEqual(port.unit_source("20230815_227_午間_Kavalan_噶瑪蘭"),
                         "20230815_227_午間_Kavalan_噶瑪蘭")
        for origin in ("r3fix1027r2x", "userrecut1023", "b1fix1027r2x"):
            self.assertIsNone(port.unit_source(origin), origin)
        box = Store()
        self.addCleanup(box.tmp.cleanup)
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        table = [seg("0", "1000", "攝影棚", "722", "848"),
                 seg("1000", "1120", "島語時間", "940", "1060"),
                 seg("1120", "1300", "攝影棚", "722", "848")]
        box.put(SRC, src_book, src_texts, table)
        box.put(TGT, tgt_book, tgt_texts,
                [seg("0", "766", "攝影棚", "722", "848"),
                 seg("766", "886", "島語時間", "940", "1060"),
                 seg("886", "1100", "攝影棚", "722", "848")])
        folder = os.path.join(box.root, "expand")
        os.makedirs(folder)
        paths = []
        for base in ("%s--from-%s-r3.json" % (TGT, SRC),
                     "%s--from-r3fix1027r2x.json" % TGT,
                     "%s--from-userrecut1023.json" % SRC,
                     "%s--from-b1fix1027r2x.json" % TGT):
            path = os.path.join(folder, base)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"items": [{"seconds": "800-820"}]}, handle,
                          ensure_ascii=False, indent=2, sort_keys=True)
            paths.append(path)
        got = port.family(paths, box.store)
        self.assertEqual(len(got["families"]), 1)
        step = got["families"][0]["steps"][0]
        self.assertEqual((step["from"], step["to"]), (SRC, TGT))
        skipped = []
        for item in got["skipped"]:
            skipped.append(item["unit"])
        want = []
        for path in paths[1:]:
            want.append(os.path.basename(path))
        self.assertEqual(sorted(skipped), sorted(want))

    def test_unit_files_for_irregular_snapshot_tags(self):
        """快照標籤不一定照規則（`xr3fix1027r2x`、`xb1fix1027r2x`、
        `x216-r2-10271411`、`xuserrecut102`）：舊做法找不到工作檔，那個單元
        的差就跟別的單元標準不一致。都要找得到對應的工作檔。"""
        name = "20230815_227_午間_Kavalan_噶瑪蘭"
        with tempfile.TemporaryDirectory() as units:
            os.makedirs(os.path.join(units, "expand"))
            os.makedirs(os.path.join(units, "followup"))
            made = {}
            for key, rel in (
                    ("main", name + ".json"),
                    ("fu", os.path.join("followup", name + ".json")),
                    ("216", os.path.join("expand", name + "--from-20230804_"
                                         "216_晚間_SaySiyat_賽夏.json")),
                    ("319", os.path.join("expand", name + "--from-20231115_"
                                         "319_午間_Cou_鄒.json")),
                    ("r3", os.path.join("expand", name
                                        + "--from-r3fix1027r2x.json")),
                    ("user", os.path.join("expand", name
                                          + "--from-userrecut1023.json"))):
                path = os.path.join(units, rel)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("{}")
                made[key] = path
            for tag, key in (("main", "main"), ("fu", "fu"),
                             ("x20230804_216", "216"),
                             ("x20231115_319-r10271923", "319"),
                             ("x216-r2-10271411", "216"),
                             ("xr3fix1027r2x", "r3"),
                             ("xuserrecut102", "user")):
                self.assertEqual(port.unit_files(units, name, tag),
                                 [made[key]], tag)

    def test_families_connect_through_shared_rows(self):
        links = [(("075", 1191), ("129", 900), "a"),
                 (("279", 500), ("129", 900), "b"),
                 (("279", 500), ("075", 1191), "c"),
                 (("098", 1200), ("194", 1500), "d")]
        got = port.group_families(links)
        names = []
        for group in got:
            names.append(sorted(group))
        self.assertEqual(sorted(names), [["a", "b", "c"], ["d"]])


# ------------------------------------------------------------ 審查和驗證抓到的毛病


class TestOffsetOverride(unittest.TestCase):

    def test_phase_spread_from_other_cut_still_ready(self):
        """227 午→216 晚：移植前的 216 是用花字設定（y690–1040）切的、227
        用島語設定，199 個錨點 83% 在 1 毫秒內、其餘差 1–3 格，p90 0.050，
        舊做法的「p90 一格」把這個標準案例擋掉（盤點有 35 份同樣被擋）。
        改看 p50 一格內、八成以上錨點在兩格內。"""
        deltas = []
        for number in range(199):
            if number % 6 == 5:
                deltas.append(742.275 + (1 + (number // 6) % 3) * F)
            else:
                deltas.append(742.275 + 0.0005 * (number % 2))
        found = anchor_set(deltas, step=5.0)
        evidence = port.judge_offset(found, None, 1000.0, 2000.0)
        self.assertGreater(evidence["p90"], F)
        self.assertLessEqual(evidence["p50"], F)
        self.assertGreaterEqual(evidence["within_two"], 0.8)
        self.assertEqual(evidence["status"], "ready", evidence["reasons"])
        self.assertAlmostEqual(evidence["offset"], 742.275, places=2)

    def test_offset_cannot_override_cut_or_different_edit(self):
        """`--offset` 只能補位移（證據不足、逐格不一致），不可以蓋掉剪接、
        剪法不同的拒絕：舊做法直接把 status 設成 ready，驗證者為了讓 216
        過關就是靠它，批次裡會被常用。"""
        cut = port.judge_offset(anchor_set([100.0] * 18 + [97.0] * 12),
                                None, 1000.0, 1120.0)
        got = port.with_offset(cut, 100.0)
        self.assertEqual(got["status"], "rejected")
        self.assertTrue(mentions(got["reasons"], "--offset", "剪接"),
                        got["reasons"])
        thin = port.judge_offset(anchor_set([100.0] * 2), None, 1000.0,
                                 1120.0)
        self.assertEqual(thin["status"], "rejected")
        got = port.with_offset(thin, 100.012)
        self.assertEqual(got["status"], "ready")
        self.assertEqual(got["offset"], 100.012)

    def test_rejected_reasons_name_the_real_blocker(self):
        """328 晚→341／020／033／093：OCR 同群只有 1–3 個、whisper 有效但跟
        畫面差幾秒到十幾秒，各 60 秒窗中位數也不同（剪法不同）。舊訊息照樣
        寫「要先用像素定位」，報告又把這 5 件和 093→060（逐格不一致）、
        194→098（剪法不同）統稱「位移證據不足」，人會以為補個像素定位就
        好。被剪接、剪法不同擋下時，不可以叫人去做像素定位。"""
        deltas = []
        for number in range(15):
            deltas.append(100.0 + number * 0.3)
        for number in range(15):
            deltas.append(120.0 + number * 0.3)
        whisper = {"offset": 100.0, "conclusive": True, "hits": 20,
                   "runner_up": 3, "segments": 40}
        got = port.judge_offset(anchor_set(deltas), whisper, 1000.0, 1120.0)
        self.assertEqual(got["status"], "rejected")
        self.assertFalse(mentions(got["reasons"], "要先用像素定位"),
                         got["reasons"])
        self.assertTrue(mentions(got["reasons"], "whisper", "補不了"),
                        got["reasons"])


ISLAND = {"preset": "titv-news-island", "region": [0, 940, 1920, 120]}
FLOWER = {"preset": "titv-news-flower", "region": [0, 690, 1920, 350]}


class TestMode(unittest.TestCase):

    def test_mode_whole_when_target_range_unread(self):
        """島語時間、帶外歌詞、插播字幕在重播整段空白（或只用一般字幕帶切
        過）：才整段換成首播的切法和字。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        tgt_book["areas"] = dict(src_book["areas"])
        for number in range(3, 33):
            tgt_texts[number] = ""
        tgt_texts[10] = "只用一般字幕帶讀到一句"
        mode, stats = port.choose_mode(src_book, src_texts, tgt_book,
                                       tgt_texts, lo, hi, -234.0)
        self.assertEqual(mode, "whole")
        self.assertEqual(stats["target_text"], 1)
        self.assertEqual(stats["source_text"], 30)

    def test_mode_whole_when_cut_setting_differs(self):
        """227 午→216 晚：216 那段有字 437 條、是首播 465 條的 94%，只數字
        會判成逐處搬、接著被三道把關擋下。216 那段用花字設定
        （titv-news-flower，y690–1040）切、227 修好後用島語設定
        （titv-news-island）：切法設定不同就整段搬。兩集 areas 的鍵名都叫
        「帶外專題」，要比 preset／region，不是比鍵名。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        src_first = json.loads(json.dumps(src_book))
        src_first["areas"] = {"帶外專題": FLOWER}
        src_book["areas"] = {"帶外專題": ISLAND}
        tgt_book["areas"] = {"帶外專題": FLOWER}
        for item in src_book["cues"] + tgt_book["cues"] + src_first["cues"]:
            if item.get("area"):
                item["area"] = "帶外專題"
        mode, stats = port.choose_mode(src_book, src_texts, tgt_book,
                                       tgt_texts, lo, hi, -234.0,
                                       src_first=src_first,
                                       tgt_first=tgt_book)
        self.assertEqual(mode, "whole")
        self.assertIn("titv-news-flower", stats["why"])
        self.assertIn("titv-news-island", stats["why"])

    def recut_case(self, src_first, src_now, tgt_first, tgt_now):
        """範圍內 cue 都標「島語時間」，四份時間軸各自給 areas；"empty"
        是範圍內沒有 cue 的快照。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        for item in tgt_book["cues"]:
            if lo - 234.0 <= item["start"] < hi - 234.0:
                item["area"] = "島語時間"
        books = []
        for base, setting in ((src_book, src_first), (src_book, src_now),
                              (tgt_book, tgt_first), (tgt_book, tgt_now)):
            if setting is None:
                books.append(None)
                continue
            if setting == "empty":
                books.append({"cues": [], "areas": {}})
                continue
            copy = json.loads(json.dumps(base))
            copy["areas"] = {"島語時間": setting}
            books.append(copy)
        return port.choose_mode(books[1], src_texts, books[3], tgt_texts, lo,
                                hi, -234.0, src_first=books[0],
                                tgt_first=books[2])

    def test_mode_whole_only_when_source_is_the_recut_one(self):
        """227 午→216 晚：227 最早那份快照是花字、現在是島語（227 重切過），
        216 現在還是花字（227 重切前那種）——首播的切法比較新，整段搬。"""
        mode, stats = self.recut_case(FLOWER, ISLAND, FLOWER, FLOWER)
        self.assertEqual(mode, "whole")
        self.assertIn("首播", stats["why"])
        self.assertIn("重切", stats["why"])

    def test_mode_asks_when_target_recut_itself(self):
        """358 晨→314 晚：358 從頭到尾是島語；314 最早那份快照是島語、後來
        重切成花字。只看兩集現在不同就整段搬，會把 314 的花字重切換回 358
        的島語，而且 ready、要人判 0，批次直接入庫。254→251 也一樣（251
        從島語重切成花字，254 一直是島語），會列 106 條要人判的字。重播
        自己重切過的，整件列要人判、不搬。"""
        mode, stats = self.recut_case(ISLAND, ISLAND, ISLAND, FLOWER)
        self.assertEqual(mode, "ask")
        self.assertIn("重播", stats["why"])
        self.assertIn("重切", stats["why"])
        # 兩集都重切過（各自換了設定）：重播也重切過，照樣要人判。
        mode, _stats = self.recut_case(FLOWER, ISLAND, ISLAND, FLOWER)
        self.assertEqual(mode, "ask")

    def test_mode_zone_when_cut_differs_but_neither_recut(self):
        """兩集從來沒重切過、只是本來切法就不同：沒有哪一集比較新，整段
        搬沒有理由，走分區搬（只搬首播改過的地方）。"""
        mode, _stats = self.recut_case(ISLAND, ISLAND, FLOWER, FLOWER)
        self.assertEqual(mode, "zone")

    def test_mode_asks_when_recut_cannot_be_told(self):
        """切法設定不同、首播卻沒有快照：判不出是哪一集重切過，不可以
        猜一個方向整段搬。首播重切過、重播卻是第三種設定（不是首播重切前
        那種）也一樣要人判。"""
        mode, stats = self.recut_case(None, ISLAND, FLOWER, FLOWER)
        self.assertEqual(mode, "ask")
        self.assertIn("快照", stats["why"])
        third = {"preset": "titv-news-island-high",
                 "region": [0, 900, 1920, 120]}
        mode, _stats = self.recut_case(FLOWER, ISLAND, third, third)
        self.assertEqual(mode, "ask")

    def test_mode_asks_when_first_snapshot_has_no_cue_in_range(self):
        """最早那份快照在這段範圍內沒有 cue 時，舊做法退回「現在的設定」：
        重播最早那份空白、首播從島語重切成花字、重播現在是島語，就判成
        「重播沒重切過」整段搬（審查合成案例）；首播最早那份空白就判成
        「首播沒重切過」分區搬。最早那份看不出切法，就判不出哪一集重切
        過，要人判。"""
        mode, stats = self.recut_case(ISLAND, FLOWER, "empty", ISLAND)
        self.assertEqual(mode, "ask")
        self.assertIn("最早那份快照", stats["why"])
        self.assertIn("沒有 cue", stats["why"])
        mode, stats = self.recut_case("empty", FLOWER, ISLAND, ISLAND)
        self.assertEqual(mode, "ask")
        self.assertIn("沒有 cue", stats["why"])

    def test_mode_asks_when_first_snapshot_lacks_timeline(self):
        """快照目錄有這集的快照，裡面卻沒有時間軸（只拍到 TSV 的那種）：
        `first_book` 舊做法給 None，跟「沒有快照」一樣當成重播沒重切過。
        有快照卻讀不到時間軸，要人判，原因寫出是哪一份快照。"""
        box = Store()
        self.addCleanup(box.tmp.cleanup)
        snaps = os.path.join(box.root, "snap")
        folder = os.path.join(snaps, "%s--main" % TGT)
        os.makedirs(folder)
        with open(os.path.join(folder, "manifest.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write("Kari-SRT/news/1-ocr/2-vision/x/b01.tsv\n")
        first = port.first_book(snaps, TGT, box.store)
        self.assertIsNotNone(first)
        self.assertIsNone(port.first_book(snaps, SRC, box.store))
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        src_first = json.loads(json.dumps(src_book))
        src_first["areas"] = {"島語時間": ISLAND}
        src_book["areas"] = {"島語時間": FLOWER}
        tgt_book["areas"] = {"島語時間": ISLAND}
        for item in tgt_book["cues"]:
            if lo - 234.0 <= item["start"] < hi - 234.0:
                item["area"] = "島語時間"
        mode, stats = port.choose_mode(src_book, src_texts, tgt_book,
                                       tgt_texts, lo, hi, -234.0,
                                       src_first=src_first, tgt_first=first)
        self.assertEqual(mode, "ask")
        self.assertIn("沒有時間軸", stats["why"])
        self.assertIn(folder, stats["why"])

    def test_mode_zone_when_target_range_read(self):
        """182 晨、291 晚、331 午、306 午：重播那段本來就有字、切法設定跟首播
        一樣，整段搬會把首播的時間軸錯和錯字（魚撈式、藩草、島嶼時間）帶
        過來、拿掉 331 的「但是遇到風雨」「部落信箱」——走分區搬。範圍外
        用別的設定不算：287 的頂層 region 是 y840、331 是 y722，部落信箱
        那段兩集都用 titv-news-mailbox，只比範圍內佔最多時間的那種。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        tgt_book["areas"] = dict(src_book["areas"])
        mode, _stats = port.choose_mode(src_book, src_texts, tgt_book,
                                        tgt_texts, lo, hi, -234.0)
        self.assertEqual(mode, "zone")
        src_book["region"] = [0, 840, 1920, 90]
        tgt_book["region"] = [0, 722, 1920, 126]
        mode, _stats = port.choose_mode(src_book, src_texts, tgt_book,
                                        tgt_texts, lo, hi, -234.0)
        self.assertEqual(mode, "zone")


def lines_book(lines, areas=None):
    cues, texts = build(lines)
    return {"cues": cues, "areas": areas or {}, "duration": 4000.0,
            "refined": True}, texts


def replace_line(lines, number, *new):
    out = list(lines)
    out[number:number + 1] = list(new)
    return out


def text_cues(result, text):
    out = []
    for item in result["cues"]:
        if result["all_texts"][item["index"]] == text:
            out.append((round(item["start"], 3), round(item["end"], 3)))
    return out


class TestZone(unittest.TestCase):
    """分區搬：首播修改前快照 → 首播現在，有差的 cue 併成區、往外擴到安全
    邊；區內整批換成首播現在的（加位移），區外重播一律不動。"""

    OFF = 199.132

    def setUp(self):
        self.body = program(lo=1600.0, count=12)       # 1600.3 … 1647.5
        self.before, self.before_texts = lines_book(self.body)

    def run_zone(self, after_lines, target_lines=None, lo=1590.0,
                 hi=1660.0):
        """target_lines 用首播時間寫，這裡加位移。"""
        after, after_texts = lines_book(after_lines)
        tgt_book, tgt_texts = lines_book(
            shifted(target_lines or self.body, self.OFF))
        result = port.zone_port(self.before, self.before_texts, after,
                                after_texts, tgt_book, tgt_texts, lo, hi,
                                self.OFF)
        return result, tgt_book, tgt_texts

    def split_five(self):
        start, end, text, extra = self.body[5]
        return replace_line(self.body, 5,
                            (start, 1621.9, text, extra),
                            (1621.9, end, "是不能隨便的", extra))

    def test_zone_split_only_where_source_changed(self):
        """152 午→182 晨：首播只把一句拆成兩句。182 自己的時間軸跟 152 各有
        對錯（抽 6 處各對 3 處：1645.8「是不能隨便的」182 對、152 晚 0.22
        秒），整段搬只是把重播的錯換成首播的錯。區只有拆句那一條，重播
        其他 cue 的起迄和字一律不動；拆出來的前半條留重播的身分和圖條，
        後半條圖條清空。"""
        target = list(self.body)
        start, end, text, extra = target[8]
        target[8] = (start, round(end + 0.22, 3), text, extra)
        target[2] = target[2][:2] + ("漁撈式的捕魚方法", {})
        result, tgt_book, _texts = self.run_zone(self.split_five(), target)
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(result["ask"], [])
        self.assertEqual(len(result["cues"]), 13)
        first = result["cues"][5]
        second = result["cues"][6]
        self.assertEqual(first["start"], tgt_book["cues"][5]["start"])
        self.assertAlmostEqual(first["end"], round(1621.9 + self.OFF, 3))
        self.assertEqual(second["start"], first["end"])
        self.assertEqual(second["end"], tgt_book["cues"][5]["end"])
        self.assertEqual(first["images"], tgt_book["cues"][5]["images"])
        self.assertEqual(second["images"], {})
        self.assertEqual(result["all_texts"][7], "是不能隨便的")
        self.assertEqual(result["all_texts"][6], say(5))
        self.assertEqual(result["cues"][9]["end"], tgt_book["cues"][8]["end"])
        self.assertEqual(result["all_texts"][3], "漁撈式的捕魚方法")
        self.assertEqual(result["moves"][3], 3)
        self.assertEqual(result["moves"][6], 6)
        self.assertEqual(result["moves"][9], 10)

    def test_zone_never_lets_source_typo_overwrite_target(self):
        """首播沒改過的「藩草」不在任何區、重播的「蘊草」留著；首播把「留言
        版」改成「留言板」、重播也是「留言版」→ 套。區內重播的字跟首播修改
        前不同——331「…共勉之 部落信箱」（重播讀到首播沒有的）、182「漁撈
        式」對首播「魚撈式」——那一區列要人判、不套，其他區照套。"""
        body = list(self.body)
        body[3] = (body[3][0], body[3][1], "藩草的味道很香", {})
        body[4] = (body[4][0], body[4][1], "請到留言版留言", {})
        body[6] = (body[6][0], body[6][1], "泰雅人我們一起共勉之", {})
        body[9] = (body[9][0], body[9][1], "魚撈式的捕魚方法", {})
        self.before, self.before_texts = lines_book(body)
        target = list(body)
        target[3] = target[3][:2] + ("蘊草的味道很香", {})
        target[6] = target[6][:2] + ("泰雅人我們一起共勉之 部落信箱", {})
        target[9] = target[9][:2] + ("漁撈式的捕魚方法", {})
        after = list(body)
        after[4] = after[4][:2] + ("請到留言板留言", {})
        after[6] = after[6][:2] + ("泰雅人一起共勉之", {})
        after[9] = after[9][:2] + ("魚撈式的捕魚方法喔", {})
        result, _book, _texts = self.run_zone(after, target)
        self.assertEqual(result["all_texts"][4], "蘊草的味道很香")
        self.assertEqual(result["all_texts"][5], "請到留言板留言")
        self.assertEqual(result["all_texts"][7], "泰雅人我們一起共勉之 部落信箱")
        self.assertEqual(result["all_texts"][10], "漁撈式的捕魚方法")
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(len(result["ask"]), 2)
        asked = []
        for item in result["ask"]:
            asked += item["target_cues"]
            self.assertTrue(mentions([item["why"]], "字不同"), item["why"])
        self.assertEqual(sorted(asked), [7, 10])

    def test_zone_target_cut_differently_takes_source_bounds(self):
        """重播那條起點比首播晚 0.3 秒（用別的區域切的）：上一個做法要求修改
        前起迄一格內，列要人判——331 兩處拆 cue、291 六十幾處都卡在這裡。
        兩邊在區邊都有空檔（安全邊），區內整批換成首播現在的，字照首播
        修改前一樣就套。"""
        target = list(self.body)
        start, end, text, extra = target[5]
        target[5] = (round(start + 0.3, 3), end, text, extra)
        result, _book, _texts = self.run_zone(self.split_five(), target)
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(result["ask"], [])
        self.assertEqual(len(result["cues"]), 13)
        self.assertAlmostEqual(result["cues"][5]["start"],
                               round(1620.3 + self.OFF, 3))
        self.assertEqual(result["all_texts"][6], say(5))
        self.assertEqual(result["all_texts"][7], "是不能隨便的")

    def test_zone_expands_to_safe_edge(self):
        """重播把第 5、6 句的分界切在首播第 6 句開頭後 1 秒：區的迄點落在
        重播有字的 cue 中間，直接切會把重播那條切成兩半。區要往外擴到兩
        邊都沒有字跨過去的點（第 6 句迄點），第 6 句也整條換成首播的。"""
        target = list(self.body)
        s5, _e5, t5, x5 = target[5]
        s6, e6, t6, x6 = target[6]
        target[5] = (s5, round(s6 + 1.0, 3), t5, x5)
        target[6] = (round(s6 + 1.0, 3), e6, t6, x6)
        result, _book, _texts = self.run_zone(self.split_five(), target)
        self.assertEqual(len(result["applied"]), 1)
        zone = result["applied"][0]
        self.assertAlmostEqual(zone["src"][0], s5)
        self.assertAlmostEqual(zone["src"][1], e6)
        self.assertEqual(text_cues(result, say(6)),
                         [(round(s6 + self.OFF, 3), round(e6 + self.OFF, 3))])
        self.assertEqual(len(result["cues"]), 13)
        port.check_timeline(result["cues"])

    def test_zone_same_sentence_not_fragmented(self):
        """291「niqan gnklaan…」：首播把三條相連的空白補成同一句，重播中間
        的邊差 0.1 秒。上一個做法逐個套，只套到第一條，SRT 只剩 1.48 秒
        （首播是 2451.416–2454.302），語音跟字幕的邊界錯了會污染 ASR 訓練。
        相連的修改要併成一區、整句一起換。"""
        before, before_texts = lines_book(
            [(8.0, 10.0, "前一句的字幕"), (10.0, 11.0, ""), (11.0, 12.0, ""),
             (12.0, 13.0, ""), (13.0, 15.0, "後一句的字幕")])
        after_lines = [(8.0, 10.0, "前一句的字幕")]
        for start in (10.0, 11.0, 12.0):
            after_lines.append((start, start + 1.0, "同一句很長的話", {}))
        after_lines.append((13.0, 15.0, "後一句的字幕"))
        after, after_texts = lines_book(after_lines)
        tgt_book, tgt_texts = lines_book(
            [(8.0, 10.0, "前一句的字幕"), (10.0, 11.0, ""), (11.0, 12.1, ""),
             (12.1, 13.0, ""), (13.0, 15.0, "後一句的字幕")])
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 0.0, 100.0, 0.0)
        self.assertEqual(result["ask"], [])
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(text_cues(result, "同一句很長的話"),
                         [(10.0, 11.0), (11.0, 12.0), (12.0, 13.0)])

    def test_zone_bounds_change_across_range_edge(self):
        """首播把「前一句」的迄點和「範圍內」的起點一起從 10.4 改到 10.9，
        前一句中點在範圍外：上一個做法只套範圍內那一半，中間多出 0.5 秒
        沒有字幕的空檔。區要往外擴到安全邊，兩條一起改。"""
        lines = [(8.0, 10.4, "前一句的字幕"), (10.4, 13.0, "範圍內的字幕"),
                 (13.0, 16.0, "後一句的字幕")]
        before, before_texts = lines_book(lines)
        after, after_texts = lines_book(
            [(8.0, 10.9, "前一句的字幕"), (10.9, 13.0, "範圍內的字幕"),
             (13.0, 16.0, "後一句的字幕")])
        tgt_book, tgt_texts = lines_book(lines)
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 10.0, 100.0, 0.0)
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(text_cues(result, "前一句的字幕"), [(8.0, 10.9)])
        self.assertEqual(text_cues(result, "範圍內的字幕"), [(10.9, 13.0)])

    def test_zone_insert_already_same_and_target_own_text(self):
        """首播在空檔補一句：重播同處也空才補；已經補過的算「已經一樣」，不
        重複補；重播自己有、首播沒碰的句子（331「但是遇到風雨」）在區外，
        留著；重播同處有自己的另一句 → 那一區要人判。"""
        gap = (1647.6, 1648.9)
        after = self.body + [(gap[0], gap[1], "部落信箱下次見", {})]
        target = self.body + [(1650.0, 1652.0, "但是遇到風雨", {})]
        result, _book, _texts = self.run_zone(after, target)
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(result["all_texts"][13], "部落信箱下次見")
        self.assertEqual(result["all_texts"][14], "但是遇到風雨")
        after_book, after_texts = lines_book(after)
        again = port.zone_port(self.before, self.before_texts, after_book,
                               after_texts, {"cues": result["cues"]},
                               result["all_texts"], 1590.0, 1660.0, self.OFF)
        self.assertEqual(again["applied"], [])
        self.assertEqual(len(again["same"]), 1)

        crowded = target + [(gap[0], gap[1], "重播自己的另一句", {})]
        result, _book, _texts = self.run_zone(after, crowded)
        self.assertEqual(result["applied"], [])
        self.assertEqual(len(result["ask"]), 1)
        self.assertIn("重播自己的另一句", result["all_texts"].values())

    def test_zone_bounds_change_keeps_target_bytes(self):
        """部落信箱詩句淡入淡出，首播把起點晚 1.2 秒：重播那條字跟首播一樣
        （只差尾端空白），起點照改，字留重播的 byte、TSV 列不換。"""
        start, end, text, extra = self.body[7]
        after = replace_line(self.body, 7, (start + 1.2, end, text, extra))
        target = list(self.body)
        target[7] = target[7][:2] + (text + " ", {})
        result, _book, _texts = self.run_zone(after, target)
        self.assertEqual(len(result["applied"]), 1)
        self.assertAlmostEqual(result["cues"][7]["start"],
                               round(start + 1.2 + self.OFF, 3))
        self.assertEqual(result["all_texts"][8], text + " ")
        self.assertEqual(result["moves"][8], 8)

    def test_zone_reports_source_text_where_target_blank(self):
        """用 323 午現在的狀態模擬 269 午←323 午（那四條其實是 323 後來才補
        上的，這裡當成首播從最早就有）：首播 2176–2194 秒四條（嗆辣問答題目、
        歌詞，重播時間 1573–1591）沒改過；重播同處 1572.805–1590.589
        沒有 cue、1590.589–1591.24 只有一條空白 cue。那裡不在任何區，分區
        搬不碰，舊做法完全不報。要列成「首播有字、重播沒字」：附首播、重播
        秒數、首播 cue 和字、重播那裡的空白 cue；不自動搬。區裡的（首播在
        空檔補一句、重播同處也空，照套）不重報；範圍外的不報。"""
        target = list(self.body)
        blank = target[10]
        target[8:11] = [(blank[0], blank[1], "", {})]
        after = self.split_five()
        result, tgt_book, _texts = self.run_zone(after, target)
        self.assertEqual(len(result["applied"]), 1)
        after_book, after_texts = lines_book(after)
        numbers = {}
        for item in after_book["cues"]:
            numbers[after_texts[item["index"]]] = item["index"]
        got = []
        for entry in result["blank_in_target"]:
            got.append((entry["text"], entry["cues"]))
        self.assertEqual(got, [(say(8), [numbers[say(8)]]),
                               (say(9), [numbers[say(9)]]),
                               (say(10), [numbers[say(10)]])])
        first = result["blank_in_target"][0]
        self.assertEqual(first["src"], [self.body[8][0], self.body[8][1]])
        self.assertEqual(first["tgt"], [round(self.body[8][0] + self.OFF, 3),
                                        round(self.body[8][1] + self.OFF, 3)])
        self.assertEqual(first["target_cues"], [])
        blank_cue = None
        for item in tgt_book["cues"]:
            if abs(item["start"] - round(blank[0] + self.OFF, 3)) < 0.001:
                blank_cue = item["index"]
        self.assertEqual(result["blank_in_target"][2]["target_cues"],
                         [blank_cue])
        self.assertNotIn(say(8), result["all_texts"].values())

        result, _book, _texts = self.run_zone(after, target, hi=1630.0)
        self.assertEqual(result["blank_in_target"], [])

        gap = (1647.6, 1648.9)
        inserted = self.body + [(gap[0], gap[1], "部落信箱下次見", {})]
        result, _book, _texts = self.run_zone(inserted)
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(result["blank_in_target"], [])

    def test_items_in_blank_spot_named_not_unchanged(self):
        """工作檔項目落在「首播有字、重播沒字」那裡：舊做法報「不在首播改過
        的地方」，讀的人以為首播沒這句、不必管。要講明首播有字、重播沒字，
        附首播 cue 和字。"""
        blank = [{"tgt": [1573.889, 1576.525], "cues": [856],
                  "text": "請唱一首符合現在的心情的歌"}]
        got = port.items_status([(1574.0, 1575.0), (1700.0, 1701.0)], [],
                                [], blank)
        self.assertEqual(got[0], {"range": [1574.0, 1575.0],
                                  "status": "blank", "cues": [856],
                                  "text": "請唱一首符合現在的心情的歌"})
        self.assertEqual(got[1]["status"], "none")
        lines = port.items_lines(got)
        self.assertIn("首播有字、重播沒字", lines[0])
        self.assertIn("856", lines[0])
        self.assertIn("請唱一首", lines[0])
        self.assertIn("首播改過的地方", lines[1])

    def test_zone_without_safe_edge_asks(self):
        """重播一條有字的 cue 從範圍前 20 秒一路跨到範圍後：區兩端都找不到
        兩邊都沒有字跨過去的點，硬切會把重播那條切碎——這一區列要人判。"""
        before, before_texts = lines_book([(10.0, 20.0, "甲乙丙丁戊己")])
        after, after_texts = lines_book([(10.0, 15.0, "甲乙丙丁戊己"),
                                         (15.0, 20.0, "庚辛壬癸")])
        tgt_book, tgt_texts = lines_book([(-20.0, 140.0, "甲乙丙丁戊己")])
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 0.0, 100.0, 0.0)
        self.assertEqual(result["applied"], [])
        self.assertEqual(len(result["ask"]), 1)
        self.assertIn("安全邊", result["ask"][0]["why"])

    def test_original_overlap_outside_zone_noted_new_overlap_refused(self):
        """Kari-SRT 3152 份時間軸有 168 份本來就重疊（216 移植前 cue 1074／
        1075、254 範圍外 cue 709／710），上一個做法一開頭整件擋，盤點 183
        份擋掉 87 份。只擋這次新造成的重疊或倒置（跟重播原本的時間軸比），
        原本就有的記說明。"""
        target = list(self.body)
        start, end, text, extra = target[10]
        target[10] = (start, round(target[11][0] + 0.367, 3), text, extra)
        result, _book, _texts = self.run_zone(self.split_five(), target)
        self.assertEqual(len(result["applied"]), 1)
        self.assertTrue(mentions(result["notes"], "原本", "11"),
                        result["notes"])

        old, _texts = build([(1.0, 2.0, "a"), (2.0, 3.0, "b")])
        new, _texts = build([(1.0, 2.5, "a"), (2.0, 3.0, "b")])
        with self.assertRaises(PipelineError) as caught:
            port.check_new(old, new)
        self.assertIn("這次", str(caught.exception))
        self.assertTrue(mentions(port.check_new(new, new), "原本"))
        with self.assertRaises(PipelineError):
            port.check_new(old, [cue(1, 2.0, 1.5)])

    def test_source_own_overlap_asks_only_that_zone(self):
        """首播現在自己在某一區裡就有重疊（第 9 句迄點拉到第 10 句起點後 0.3
        秒）：舊做法搬完才整份檢查，整份 plan 擋下，連另一區的拆句也不套。
        只把那一區列要人判，其他區照套。"""
        after = self.split_five()
        start, _end, _text, extra = after[10]
        after[10] = (start, 1640.6, "第009句改過的新字", extra)
        result, _book, _texts = self.run_zone(after)
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(len(result["ask"]), 1)
        self.assertIn("重疊", result["ask"][0]["why"])
        self.assertIn("是不能隨便的", result["all_texts"].values())
        self.assertNotIn("第009句改過的新字", result["all_texts"].values())
        port.check_timeline(result["cues"])

    def zone_with_areas(self, target_areas):
        after_book, after_texts = lines_book(self.split_five(),
                                             {"島語時間": ISLAND})
        tgt_book, tgt_texts = lines_book(shifted(self.body, self.OFF),
                                         target_areas)
        result = port.zone_port(self.before, self.before_texts, after_book,
                                after_texts, tgt_book, tgt_texts, 1590.0,
                                1660.0, self.OFF)
        result["range"] = [round(1590.0 + self.OFF, 3),
                           round(1660.0 + self.OFF, 3)]
        book = port.new_book(tgt_book, after_book, result, SRC, 1590.0,
                             1660.0, self.OFF, tgt_texts, mode="zone")
        return result, book

    def test_zone_cues_keep_source_setting_under_new_area_name(self):
        """分區搬進來的 cue 是照首播的設定（島語 y940）切的，重播同名的
        「島語時間」卻是花字 y690：舊做法保留重播的設定、只記一筆說明，
        這幾條 cue 就被標成花字切的，時間軸的 metadata 對不上。首播的設定
        要用不衝突的新名字放進 areas，搬進來的 cue 標那個名字；重播自己
        的 cue 照舊。每條 cue 的 area 都要在 areas 裡（rebuild、publish
        照常）。"""
        result, book = self.zone_with_areas({"島語時間": FLOWER})
        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(book["areas"]["島語時間"], FLOWER)
        added = []
        for name in book["areas"]:
            if name != "島語時間":
                added.append(name)
        self.assertEqual(len(added), 1)
        self.assertEqual(book["areas"][added[0]], ISLAND)
        self.assertTrue(added[0].startswith("島語時間"))
        zone = result["applied"][0]["tgt"]
        for item in book["cues"]:
            self.assertIn(item["area"], book["areas"])
            inside = zone[0] - 0.001 <= item["start"] \
                and item["end"] <= zone[1] + 0.001
            self.assertEqual(item["area"], added[0] if inside else "島語時間",
                             item)
        # 新名字已經被另一種設定用掉：再換一個，不可以蓋掉。
        third = {"preset": "titv-news-island-high",
                 "region": [0, 900, 1920, 120]}
        result, again = self.zone_with_areas({"島語時間": FLOWER,
                                              added[0]: third})
        self.assertEqual(again["areas"][added[0]], third)
        others = []
        for name in again["areas"]:
            if name not in ("島語時間", added[0]):
                others.append(name)
        self.assertEqual(len(others), 1)
        self.assertEqual(again["areas"][others[0]], ISLAND)
        # 設定相同就沿用同名，不另外造。
        result, same = self.zone_with_areas({"島語時間": ISLAND})
        self.assertEqual(sorted(same["areas"]), ["島語時間"])

    def test_zone_cue_without_area_keeps_source_top_region(self):
        """首播那條 cue 沒有 area（照頂層 region y840 切），重播頂層 region
        是 y722：舊做法搬進來的 cue 也不帶 area，就落在重播的 y722 底下，
        時間軸記的切法跟實際對不上（審查合成案例；190 份工作檔全量乾跑搬
        進來的 8482 條沒遇到，換一集就可能遇到）。首播的頂層設定要另存一個 area、搬進來的
        cue 標它；重播自己的 cue 照舊不帶 area。"""
        plain = []
        for start, end, text, _extra in self.body:
            plain.append((start, end, text, {}))
        before, before_texts = lines_book(plain)
        start, end, text, _extra = plain[5]
        after, after_texts = lines_book(replace_line(
            plain, 5, (start, 1621.9, text, {}),
            (1621.9, end, "是不能隨便的", {})))
        for book in (before, after):
            book["region"] = [0, 840, 1920, 120]
        tgt_book, tgt_texts = lines_book(shifted(plain, self.OFF))
        tgt_book["region"] = [0, 722, 1920, 126]
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 1590.0, 1660.0,
                                self.OFF)
        result["range"] = [round(1590.0 + self.OFF, 3),
                           round(1660.0 + self.OFF, 3)]
        book = port.new_book(tgt_book, after, result, SRC, 1590.0, 1660.0,
                             self.OFF, tgt_texts, mode="zone")
        self.assertEqual(len(result["applied"]), 1)
        zone = result["applied"][0]["tgt"]
        source_setting = port.cut_setting(after, after["cues"][6])
        target_setting = port.cut_setting(tgt_book, tgt_book["cues"][0])
        self.assertNotEqual(source_setting, target_setting)
        moved = 0
        for item in book["cues"]:
            if item.get("area"):
                self.assertIn(item["area"], book["areas"])
            inside = zone[0] - 0.001 <= item["start"] \
                and item["end"] <= zone[1] + 0.001
            want = source_setting if inside else target_setting
            self.assertEqual(port.cut_setting(book, item), want, item)
            if inside:
                moved += 1
        self.assertEqual(moved, 2)
        self.assertEqual(book["region"], [0, 722, 1920, 126])

    def test_whole_cue_without_area_keeps_source_top_region(self):
        """整段搬也一樣：首播範圍內的 cue 沒有 area、兩集頂層 region 不同，
        搬進來的整段要標首播的頂層設定，範圍外重播自己的 cue 照舊。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        for item in src_book["cues"] + tgt_book["cues"]:
            item.pop("area", None)
        src_book["areas"] = {}
        src_book["region"] = [0, 840, 1920, 90]
        tgt_book["region"] = [0, 722, 1920, 126]
        for number in range(3, 33):
            tgt_texts[number] = ""
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           -234.0)
        book = port.new_book(tgt_book, src_book, result, SRC, lo, hi, -234.0,
                             tgt_texts, mode="whole")
        fresh = set(result["fresh"])
        self.assertTrue(fresh)
        for item in book["cues"]:
            if item.get("area"):
                self.assertIn(item["area"], book["areas"])
            want = [0, 840, 1920, 90] if item["index"] in fresh \
                else [0, 722, 1920, 126]
            self.assertEqual(json.loads(port.cut_setting(book, item))
                             ["region"], want, item)

    def test_edits_ignore_renumbering(self):
        """首播在範圍前面拆過 cue，範圍內的號碼全部 +1：起迄和字都一樣的
        不算修改。"""
        after = self.split_five()
        start, end, text, extra = after[11]
        after[11] = (start, end, text + "（訂正）", extra)
        after_book, after_texts = lines_book(after)
        edits = port.edits_between(self.before, self.before_texts,
                                   after_book, after_texts, 1590.0, 1660.0)
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0]["kind"], "split")

    def test_zone_fixes_follow_text(self):
        """訂正紀錄：重播自己區外的列照改號；首播的訂正（改前在修改前的字、
        改後在新字）照字對（號碼在快照和現在不一樣）抄給重播；重播自己訂正
        過的那條被首播改掉 → 擋，不可以默默蓋掉。"""
        after = self.split_five()
        start, end, text, extra = after[9]
        after[9] = (start, end, "第008句萬用鏟", extra)
        before_lines = list(self.body)
        before_lines[8] = before_lines[8][:2] + ("第008句萬用鐮", {})
        self.before, self.before_texts = lines_book(before_lines)
        result, _book, _texts = self.run_zone(after, before_lines)
        rows = [[TGT, "12", "a", "b", "範圍外"],
                [SRC, "10", "萬用鐮", "萬用鏟", "明顯錯字"]]
        got = port.zone_fixes(rows, SRC, TGT, result)
        self.assertEqual(got[0], [TGT, "13", "a", "b", "範圍外"])
        self.assertEqual(got[2][:4], [TGT, "10", "萬用鐮", "萬用鏟"])
        self.assertIn("移植自 %s" % SRC, got[2][4])

        rows = [[TGT, "9", "萬用鏟", "萬用鐮", "重播自己改的"]]
        with self.assertRaises(PipelineError) as caught:
            port.zone_fixes(rows, SRC, TGT, result)
        self.assertIn("9", str(caught.exception))

    def test_item_ranges_parsed(self):
        """工作檔 items 的 seconds 有十幾種寫法（1388 個「a-b」、72 個
        「a-b,c-d」、31 個「約 a-b」、全形「–」「、」、單一秒數、「見
        problems」）；看不懂的不可以當成 0 秒。"""
        items = [{"seconds": "1586-2467"},
                 {"seconds": "1767.95–1769.001、1769.001–1770.119"},
                 {"seconds": "約 1300.8-1304.0"},
                 {"seconds": "2156"},
                 {"seconds": "1140.99,1144.26"},
                 {"seconds": "見 problems"}, {"seconds": "-"}, {}]
        self.assertEqual(port.item_ranges(items),
                         [(1586.0, 2467.0), (1767.95, 1769.001),
                          (1769.001, 1770.119), (1300.8, 1304.0),
                          (2156.0, 2156.0), (1140.99, 1140.99),
                          (1144.26, 1144.26)])

    def test_item_inside_asked_zone_not_reported_done(self):
        """305→306 模擬 cue 421 改字：那一區列要人判，工作檔項目 1502.7–
        1505.0 就在那一區裡，可是離套用的上一區（1500.299–1502.018）不到
        1 秒，舊做法先用 1 秒寬限比套用區，把它報成做到了，報告沒有「列要
        人判」那句。要先看真的跟哪一區重疊。"""
        applied = [{"tgt": [10.0, 14.5]}]
        asked = [{"tgt": [14.6, 18.0], "why": "字不同：重播 cue 421"}]
        got = port.items_status([(15.0, 17.0)], applied, asked)
        self.assertEqual(got, [{"range": [15.0, 17.0], "status": "ask",
                                "why": "字不同：重播 cue 421"}])
        # 不跟任何一區重疊、離套用區 1 秒內：照舊算做到。
        self.assertEqual(port.items_status([(14.55, 14.58)], applied, []),
                         [])
        # 跨在套用區和要人判區中間：沒做完，報要人判。
        got = port.items_status([(14.0, 15.0)], applied, asked)
        self.assertEqual(got[0]["status"], "ask")

    def test_items_report_names_asked_zone(self):
        """182、331 的工作檔項目其實有對應的首播修改、只是列了要人判，上一
        個做法報「沒有對應的首播修改」，會讓人以為首播沒修。要分開講。"""
        applied = [{"tgt": [100.0, 110.0]}]
        asked = [{"tgt": [200.0, 210.0], "why": "字不同：重播 cue 599"}]
        got = port.items_status([(101.0, 102.0), (205.0, 206.0),
                                 (400.0, 401.0)], applied, asked)
        self.assertEqual(got, [
            {"range": [205.0, 206.0], "status": "ask",
             "why": "字不同：重播 cue 599"},
            {"range": [400.0, 401.0], "status": "none"}])
        lines = port.items_lines(got)
        self.assertIn("要人判", lines[0])
        self.assertIn("字不同：重播 cue 599", lines[0])
        self.assertNotIn("沒有對應", lines[0])
        self.assertIn("首播改過的地方", lines[1])


class TestWholePortEdges(unittest.TestCase):
    """整段搬（重播那段原本沒讀到）時，審查列的邊界毛病。"""

    def test_edge_same_text_longer_target_not_shrunk(self):
        """216 移植前「我傻眼」2791.405–2794.592（3.19 秒，舊花字切法拉得
        長），227 搬過來 1.10 秒：覆蓋率用重播那條算不到五成，舊做法判成
        首播沒有、迄點縮到 2791.405，範圍外留下 216 自己的 cue 跟 areas
        衝突。覆蓋率要用兩條中較短的那條算（字相同就算）。"""
        off = 742.275
        body = program(lo=2000.0, count=12)
        last = (2049.13, 2050.23, "我傻眼", {"area": "島語時間"})
        src_cues, src_texts = build(body + [last])
        tgt_cues, tgt_texts = build(shifted(body, off) + [
            (2791.405, 2794.592, "我傻眼", {})])
        result = port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                           tgt_texts, 2000.0, 2052.0, off)
        self.assertAlmostEqual(result["range"][1], 2052.0 + off)
        self.assertEqual(result["notes"], [])

    def test_ported_blank_trimmed_against_target_text(self):
        """152 午→182 晨用段落表那一列：搬進來的空白 cue 909（2638.736–
        2641.138）跟 182 範圍外有字的「休息一下 馬上回來」重疊 0.533 秒，
        舊做法只會修短保留的空白，整件擋下。搬進來的是空白就修短它。"""
        off = 199.132
        body = program(lo=1000.0, count=10)               # 到 1039.5
        blank = (1039.6, 1042.0, "", {"area": "島語時間"})
        src_cues, src_texts = build(body + [blank])
        own_start = round(1042.0 + off - 0.533, 3)
        tgt_cues, tgt_texts = build(shifted(body, off) + [
            (own_start, own_start + 5.0, "休息一下 馬上回來", {})])
        result = port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                           tgt_texts, 1000.0, 1042.5, off)
        trimmed = result["cues"][10]
        self.assertEqual(result["all_texts"][11], "")
        self.assertAlmostEqual(trimmed["end"], own_start)
        self.assertEqual(result["all_texts"][12], "休息一下 馬上回來")
        port.check_timeline(result["cues"])

    def test_trim_that_inverts_cue_refused(self):
        """保留的空白 cue 20.1–20.5，搬進來的 19.0–20.8（字跟重播不同、
        邊緣不修）：舊做法修短成 20.8–20.5、照樣 ready。修短後起點大於
        迄點要擋。"""
        src_cues, src_texts = build([(10.0, 13.0, "第一句比較長的字幕"),
                                     (13.2, 16.0, "第二句比較長的字幕"),
                                     (16.2, 18.8, "第三句比較長的字幕"),
                                     (19.0, 20.8, "第四句比較長的字幕")])
        tgt_cues, tgt_texts = build([(10.0, 13.0, "第一句比較長的字幕"),
                                     (13.2, 16.0, "第二句比較長的字幕"),
                                     (16.2, 18.8, "第三句比較長的字幕"),
                                     (19.0, 19.9, ""),
                                     (20.1, 20.5, "")])
        with self.assertRaises(PipelineError) as caught:
            port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                      tgt_texts, 10.0, 20.0, 0.0)
        self.assertIn("5", str(caught.exception))

    def test_check_timeline_refuses_overlap_and_inversion(self):
        """寫出前檢查全時間軸遞增不重疊（設計寫了、舊做法程式沒有）。"""
        good, _texts = build([(1.0, 2.0, "a"), (2.0, 3.0, "b")])
        port.check_timeline(good)
        bad, _texts = build([(1.0, 2.5, "a"), (2.0, 3.0, "b")])
        with self.assertRaises(PipelineError):
            port.check_timeline(bad)
        inverted = [cue(1, 2.0, 1.5)]
        with self.assertRaises(PipelineError):
            port.check_timeline(inverted)

    def test_range_start_continues_past_similar_sentence(self):
        """範圍起點往內縮，碰到重播自己的「體驗連結課室學習」（首播是「從
        身體力行的體驗連結課室學習」，相似度過 0.5 但時間差 2.9 秒）：舊做法
        當成同一句就停，留下 182 自己的版本被換掉。相似但時間對不上不算
        同一句，要繼續縮。"""
        off = 0.0
        body = program(lo=1000.0, count=20)
        src_lines = [(988.0, 993.5, "從身體力行的體驗連結課室學習", {})] + body
        tgt_lines = [(986.0, 988.5, "各位觀眾大家好今天", {}),
                     (990.9, 993.4, "體驗連結課室學習", {})] + body
        src_cues, src_texts = build(src_lines)
        tgt_cues, tgt_texts = build(tgt_lines)
        result = port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                           tgt_texts, 985.0, 1080.0, off)
        self.assertAlmostEqual(result["range"][0], 993.4)
        kept = []
        for item in result["cues"]:
            kept.append(result["all_texts"][item["index"]])
        self.assertIn("體驗連結課室學習", kept)
        self.assertNotIn("從身體力行的體驗連結課室學習", kept)

    def test_range_with_other_version_refused(self):
        """152 午→182 晨 --range 600 2439，182 在 946–980 是同一則新聞
        的邵語版（旁白和切法都不同）。舊做法縮了 54 次停在相似句、prepare
        判 ready，7 條差到 2.9 秒只報 1 條要人判。範圍裡有好幾句跟首播相似
        但時間錯開的，是別的版本，要擋。"""
        off = 0.0
        body = program(lo=1000.0, count=20)
        versions = [("來到了太魯閣族音樂暨獵人學校", 950.0, 952.9),
                    ("從身體力行的體驗連結課室學習", 961.077, 963.947),
                    ("孩子們學會了傳統的狩獵知識", 970.0, 972.1)]
        src_lines = list(body)
        tgt_lines = list(body)
        for text, src_at, tgt_at in versions:
            src_lines.append((src_at, src_at + 2.5, text, {}))
            tgt_lines.append((tgt_at, tgt_at + 2.5, text[1:], {}))
        src_cues, src_texts = build(src_lines)
        tgt_cues, tgt_texts = build(tgt_lines)
        with self.assertRaises(PipelineError) as caught:
            port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                      tgt_texts, 940.0, 1080.0, off)
        self.assertIn("別的版本", str(caught.exception))

    def test_target_own_drift_not_other_version_when_anchors_agree(self):
        """227 午→216 晚：「這個是日本人造的橋」216 移植前快照 1762.594、首播
        加位移 1759.308，216 現在 1759.307——是 216 舊花字切法的起迄錯，不是
        別的版本，卻有 11 句被當成「別的版本」擋下。大多數錨點在一格內時，
        少數錯開的句子算重播自己的時間軸錯，不擋、記說明；錨點大多不一致
        （或沒有錨點證據）照樣擋。"""
        off = 0.0
        body = program(lo=1000.0, count=20)
        versions = [("來到了太魯閣族音樂暨獵人學校", 950.0, 952.9),
                    ("從身體力行的體驗連結課室學習", 961.077, 963.947),
                    ("孩子們學會了傳統的狩獵知識", 970.0, 972.1)]
        src_lines = list(body)
        tgt_lines = list(body)
        for text, src_at, tgt_at in versions:
            src_lines.append((src_at, src_at + 2.5, text, {}))
            tgt_lines.append((tgt_at, tgt_at + 2.5, text[1:], {}))
        src_cues, src_texts = build(src_lines)
        tgt_cues, tgt_texts = build(tgt_lines)
        result = port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                           tgt_texts, 940.0, 1080.0, off, agree=0.9)
        self.assertTrue(mentions(result["notes"], "重播自己的時間軸"),
                        result["notes"])
        with self.assertRaises(PipelineError) as caught:
            port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                      tgt_texts, 940.0, 1080.0, off, agree=0.4)
        self.assertIn("別的版本", str(caught.exception))

    def test_whole_replaces_original_overlap_and_notes_the_rest(self):
        """216 移植前快照 cue 1074／1075 在範圍內本來就重疊，整段搬會換掉，
        結果更好，不該擋；範圍外原本就重疊的（254 cue 709／710）不動、只記
        說明。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        cues = tgt_book["cues"]
        cues[0]["end"] = round(cues[1]["start"] + 0.5, 3)
        cues[10]["end"] = round(cues[11]["start"] + 0.3, 3)
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           -234.0)
        self.assertTrue(mentions(result["notes"], "原本", "1"),
                        result["notes"])
        self.assertFalse(mentions(result["notes"], "原本", "11"))

    def test_source_text_where_target_has_no_cue_refused(self):
        """251 魯凱主播的「我們先休息一下…馬上回來」：254 用 --range 1155
        2075 時那段重播沒有 cue，舊做法照搬進泰雅 254 的 2186.97–2193.46，
        只列成「補進的字」。首播有字、重播沒有 cue、又不在工作檔 items 範圍
        內的要擋；在範圍內（題卡本來就沒 cue）才補。"""
        off = 126.66
        body = program(lo=1000.0, count=10)
        anchor = (1041.0, 1044.0, "我們先休息一下", {})
        src_cues, src_texts = build(body + [anchor])
        tgt_cues, tgt_texts = build(shifted(body, off))
        with self.assertRaises(PipelineError) as caught:
            port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                      tgt_texts, 1000.0, 1045.0, off, items=[])
        self.assertIn("沒有 cue", str(caught.exception))
        self.assertIn("我們先休息一下", str(caught.exception))
        result = port.port({"cues": src_cues}, src_texts, {"cues": tgt_cues},
                           tgt_texts, 1000.0, 1045.0, off,
                           items=[(1126.0, 1172.0)])
        self.assertEqual(len(result["cues"]), 11)

    def test_areas_conflict_message_uses_target_numbers(self):
        """areas 衝突訊息寫的是新號（254 舊 cue 710 寫成 737），人對不上；
        要寫重播現在的號。範圍外只剩空白 cue 用舊設定時不擋，記在 notes。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair()
        drop(tgt_book, tgt_texts, 20)
        tgt_book["areas"] = {"島語時間": {"preset": "titv-news-island-high",
                                      "region": [0, 900, 1920, 120]}}
        tgt_book["cues"][-1]["area"] = "島語時間"
        tgt_texts[len(tgt_book["cues"])] = "範圍外有字的島語"
        last = len(tgt_book["cues"])
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           -234.0)
        self.assertNotEqual(result["moves"][last], last)
        with self.assertRaises(PipelineError) as caught:
            port.new_book(tgt_book, src_book, result, SRC, lo, hi, -234.0,
                          tgt_texts)
        self.assertIn("cue %d" % last, str(caught.exception))
        self.assertNotIn("cue %d" % result["moves"][last],
                         str(caught.exception))
        tgt_texts[last] = ""
        book = port.new_book(tgt_book, src_book, result, SRC, lo, hi, -234.0,
                             tgt_texts)
        self.assertEqual(book["areas"]["島語時間"]["preset"],
                         "titv-news-island")
        self.assertTrue(mentions(book["ported"][-1]["notes"], "空白",
                                 str(last)))


class TestUnitRange(unittest.TestCase):

    def test_unit_range_merges_rows_of_one_program(self):
        """251 午泰雅島語時間在段落表是 1155–1266.6、1266.6–1276.9、
        1276.9–2060 三列（字幕帶不同），--unit 1300 只拿到最後一列，漏掉
        工作檔頭幾項、範圍外留下 island cue。同類型、同單元語別的相鄰列要
        併成一段；外景新聞一則一列，不可以併。"""
        table = [seg("1087", "1155", "攝影棚", "722", "848", "魯凱"),
                 seg("1155", "1266.600", "島語時間", "940", "1060", "泰雅"),
                 seg("1266.600", "1276.900", "島語時間", "690", "1040", "泰雅"),
                 seg("1276.900", "2060", "島語時間", "940", "1060", "泰雅"),
                 seg("2060", "2066", "攝影棚", "722", "848", "魯凱"),
                 seg("2087", "2124", "外景新聞", "722", "848", "魯凱"),
                 seg("2124", "2255", "外景新聞", "722", "848", "魯凱")]
        self.assertEqual(port.unit_range(table, 1300.0), (1155.0, 2060.0))
        self.assertEqual(port.unit_range(table, 1200.0), (1155.0, 2060.0))
        self.assertEqual(port.unit_range(table, 2200.0), (2124.0, 2255.0))


class TestProbes(unittest.TestCase):

    def test_probe_points_spread_over_whole_range(self):
        """262 範圍 1067–1972，舊做法 7 個內部點都在 1168–1420（先挑前 7 條
        改到的就滿了，「平均補滿」沒執行），後段 500 多秒沒有點，那裡有剪接
        也抓不到。內部點要平均分布在整個範圍。"""
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair(count=200)
        for number in range(3, 23):              # 範圍前段 20 條讀法不同
            tgt_texts[number] = say(number - 3).replace("字幕", "字母")
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           -234.0)
        probes = port.probe_points(result, -234.0)
        times = []
        for probe in probes:
            if probe["kind"] == "inside":
                times.append(probe["tgt"])
        times.sort()
        start, end = result["range"]
        width = end - start
        self.assertGreaterEqual(len(times), port.PROBE_INSIDE)
        self.assertLess(times[0] - start, width / 4.0)
        self.assertLess(end - times[-1], width / 4.0)
        for k in range(1, len(times)):
            self.assertLess(times[k] - times[k - 1], width / 3.0)


OVERLAYS = ((20, 16, 62, 42), (20, 170, 80, 206))   # 2021 台標、天氣框


def scene(side, seconds, lo, hi, off_frames, shared_margin=2.0,
          overlay=False):
    """合成影片的一格：節目範圍內兩集同一段畫面（每格一張不同的隨機圖），
    範圍頭尾 2 秒兩集不同（片頭動畫不同步、重播那格已經是自己的主播棚），
    範圍外各播各的。`overlay` 時重播那支在台標、天氣框的位置（384×216
    的座標照比例縮）蓋一塊全白，像 2021 那幾集。"""
    number = int((seconds / F) + 1e-9)
    first = int(round(lo / F))
    shift = off_frames if side == "target" else 0
    at = number - first - shift
    length = int(round((hi - lo) / F))
    margin = int(round(shared_margin / F))
    if margin <= at < length - margin:
        seed = at
    else:
        seed = 10 ** 6 + (10 ** 5 if side == "target" else 0) + number
    generator = numpy.random.default_rng(seed)
    image = generator.integers(0, 256, size=(27, 48)).astype(numpy.uint8)
    if overlay and side == "target":
        for x0, y0, x1, y1 in OVERLAYS:
            image[int(y0 * 27 / 216):int(math.ceil(y1 * 27 / 216)),
                  int(x0 * 48 / 384):int(math.ceil(x1 * 48 / 384))] = 255
    return image


def fake_ffmpeg(lo, hi, off_frames, overlay=False):
    """`grab` 的 runner：照 -ss 的秒數和 -i（source／target）畫一格。"""
    from PIL import Image

    def run(cmd, **_kwargs):
        seconds = float(cmd[cmd.index("-ss") + 1])
        side = cmd[cmd.index("-i") + 1]
        Image.fromarray(scene(side, seconds, lo, hi, off_frames,
                              overlay=overlay)).save(cmd[-1])
        return mock.Mock(returncode=0, stderr="")
    return run


class TestProbeEdges(unittest.TestCase):
    """像素驗收的邊界點：227→216（整段搬）起點內側 MAD 41.15（片頭動畫兩
    集不同步）、迄點內側 82.93（216 那格已經是自己的主播棚）；323→273
    （分區搬）26.05、66.90。內部點全部通過，check 卻一定不過，批次只能
    一律 --no-frames，等於沒有像素這道把關。"""

    OFF_FRAMES = 300

    def check(self, result, plan_off, true_off_frames, lo, hi, extra=(),
              overlay=False):
        with tempfile.TemporaryDirectory() as out:
            probes = port.probe_points(result, plan_off) + list(extra)
            plan = {"status": "ready", "offset": plan_off, "probes": probes}
            path = os.path.join(out, "plan.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(plan, handle, ensure_ascii=False, indent=2,
                          sort_keys=True)
            runner = fake_ffmpeg(lo, hi, true_off_frames, overlay)
            port.frames([path], "source", "source", runner)
            port.frames([path], "target", "target", runner)
            return probes, port.check(path)

    def whole_result(self, off):
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair(off=off)
        for number in range(14, 19):            # 範圍中段五句讀法不同
            tgt_texts[number] = "重播原本讀成別的字%d" % number
        return port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                         off), lo, hi

    def test_whole_edge_points_outside_first_and_last_replaced_cue(self):
        """整段搬只在真的有 cue 被換的地方取邊界點：第一條被換的 cue 起點
        前、最後一條迄點後各一點；範圍頭尾不取。"""
        off = self.OFF_FRAMES * F
        result, lo, hi = self.whole_result(off)
        probes = port.probe_points(result, off)
        replaced = []
        for number in result["changed"]:
            replaced.append(result["cues"][number - 1])
        first = replaced[0]["start"]
        edges = []
        for probe in probes:
            self.assertNotIn(probe["kind"], ("edge_in", "edge_out"))
            if probe["kind"] == "edge":
                edges.append(probe["tgt"])
        self.assertEqual(len(edges), 2)
        self.assertAlmostEqual(min(edges), port.frame_centre(
            first - port.PROBE_EDGE), places=6)
        self.assertAlmostEqual(max(edges), port.frame_centre(
            replaced[-1]["end"] + port.PROBE_EDGE), places=6)
        start, end = result["range"]
        for probe in probes:
            self.assertGreaterEqual(probe["tgt"], start)
            self.assertLessEqual(probe["tgt"], end)

    def test_whole_check_passes_real_shift_and_catches_one_frame(self):
        """合成兩支只差位移、範圍頭尾 2 秒不同的影片：位移對的要通過；
        plan 的位移差一格要擋（內部點不是局部最小）；舊做法把邊界點放在
        範圍起點內側 1 秒，那一點會不過。"""
        off = self.OFF_FRAMES * F
        result, lo, hi = self.whole_result(off)
        _probes, verdict = self.check(result, off, self.OFF_FRAMES, lo, hi)
        self.assertTrue(verdict["ok"], verdict["problems"])
        _probes, verdict = self.check(result, off + F, self.OFF_FRAMES, lo,
                                      hi)
        self.assertFalse(verdict["ok"])
        start = result["range"][0]
        old = port._probe(start + port.PROBE_EDGE, off, "edge", F)
        _probes, verdict = self.check(result, off, self.OFF_FRAMES, lo, hi,
                                      extra=[old])
        self.assertFalse(verdict["ok"])

    def test_check_ignores_station_logo_and_weather_box(self):
        """跨年代（332 晚 2023→089 晚 2021）兩支影片只差台標、天氣框：
        check 要把這兩塊遮掉，位移對的照樣通過；差一格照樣擋。"""
        off = self.OFF_FRAMES * F
        result, lo, hi = self.whole_result(off)
        _probes, verdict = self.check(result, off, self.OFF_FRAMES, lo, hi,
                                      overlay=True)
        self.assertTrue(verdict["ok"], verdict["problems"])
        _probes, verdict = self.check(result, off + F, self.OFF_FRAMES, lo,
                                      hi, overlay=True)
        self.assertFalse(verdict["ok"])

    def zone_result(self, off):
        body = program(lo=1000.0, count=30)
        before, before_texts = lines_book(body)
        start, end, text, extra = body[14]
        after_lines = replace_line(body, 14, (start, 1058.0, text, extra),
                                   (1058.0, end, "拆出來的後半句", extra))
        after, after_texts = lines_book(after_lines)
        tgt_book, tgt_texts = lines_book(shifted(body, off))
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 1000.0, 1120.0, off)
        result["range"] = [round(1000.0 + off, 3), round(1120.0 + off, 3)]
        return result

    def test_zone_probes_inside_applied_zones_edges_just_outside(self):
        """分區搬只改套用區：內部點都放在套用區裡，邊界點放在套用區外緣
        （區外 1 秒，兩集都該相同的畫面）；整段節目範圍的頭尾不取。位移
        對的通過，差一格要擋。"""
        off = self.OFF_FRAMES * F
        result = self.zone_result(off)
        self.assertEqual(len(result["applied"]), 1)
        zone = result["applied"][0]["tgt"]
        probes, verdict = self.check(result, off, self.OFF_FRAMES, 1000.0,
                                     1120.0)
        self.assertTrue(verdict["ok"], verdict["problems"])
        edges = []
        inside = 0
        for probe in probes:
            if probe["kind"] == "inside":
                inside += 1
                self.assertGreaterEqual(probe["tgt"], zone[0] - F)
                self.assertLessEqual(probe["tgt"], zone[1] + F)
            elif probe["kind"] == "edge":
                edges.append(probe["tgt"])
        self.assertEqual(inside, port.PROBE_INSIDE)
        self.assertEqual(len(edges), 2)
        self.assertAlmostEqual(min(edges), port.frame_centre(
            zone[0] - port.PROBE_EDGE), places=6)
        self.assertAlmostEqual(max(edges), port.frame_centre(
            zone[1] + port.PROBE_EDGE), places=6)
        _probes, verdict = self.check(result, off - F, self.OFF_FRAMES,
                                      1000.0, 1120.0)
        self.assertFalse(verdict["ok"])

    def test_edge_point_near_programme_range_end_skipped(self):
        """332 晚→151 晚（整段搬）：第一條被換的 cue 在範圍起點後 2.9 秒，
        它前 1 秒那個邊界點（範圍起點後 1.89 秒）落在 332 的片頭字卡「視・
        南島」，151 那格是自己的主播棚，同位移 MAD 19.19；全部只有這一個
        邊界點，check 一定不過。332→089 同一處 77.5，到範圍起點後 3.29 秒
        才對得上。範圍頭尾 PROBE_END 秒內的邊界點不取（這裡被換的 cue 在
        起點後 4.3 秒，它前 1 秒那點只在起點後 3.3 秒）。"""
        off = self.OFF_FRAMES * F
        src_book, src_texts, tgt_book, tgt_texts, lo, hi = pair(off=off)
        # 範圍第二條（起點後 4.3 秒）重播原本迄點早 0.3 秒：整段搬會換掉它。
        tgt_book["cues"][3]["end"] = round(tgt_book["cues"][3]["end"] - 0.3,
                                           3)
        result = port.port(src_book, src_texts, tgt_book, tgt_texts, lo, hi,
                           off)
        start, end = result["range"]
        self.assertAlmostEqual(start, lo + off)
        first = result["replaced"][0]
        self.assertLess(first - port.PROBE_EDGE - start, port.PROBE_END)
        probes = port.probe_points(result, off)
        for probe in probes:
            if probe["kind"] == "edge":
                self.assertGreaterEqual(probe["tgt"], start + port.PROBE_END)
                self.assertLessEqual(probe["tgt"], end - port.PROBE_END)

    def test_zone_every_applied_zone_has_inside_point(self):
        """分區搬內部點固定 7 點、套用區首尾相接後切 7 格：區多、區短的時候
        很多區一點都沒有（190 份工作檔全量乾跑，1188 個套用區只有 651 區有
        內部點），那些區搬錯了像素驗收也看不到。每個套用區至少一個內部點
        （區很短就取區中點），總數不設上限；位移對的照樣通過、差一格要擋。"""
        off = self.OFF_FRAMES * F
        body = program(lo=1000.0, count=60)
        before, before_texts = lines_book(body)
        after_lines = list(body)
        for number in range(55, 0, -6):          # 十處各拆一條，彼此隔 24 秒
            start, end, text, extra = after_lines[number]
            after_lines = replace_line(
                after_lines, number, (start, start + 1.5, text, extra),
                (start + 1.5, end, "拆出來的後半句%d" % number, extra))
        after, after_texts = lines_book(after_lines)
        tgt_book, tgt_texts = lines_book(shifted(body, off))
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 1000.0, 1240.0, off)
        result["range"] = [round(1000.0 + off, 3), round(1240.0 + off, 3)]
        zones = []
        for info in result["applied"]:
            zones.append(info["tgt"])
        self.assertGreater(len(zones), port.PROBE_INSIDE)
        probes, verdict = self.check(result, off, self.OFF_FRAMES, 1000.0,
                                     1240.0)
        self.assertTrue(verdict["ok"], verdict["problems"])
        inside = []
        for probe in probes:
            if probe["kind"] == "inside":
                inside.append(probe["tgt"])
        for first, last in zones:
            hit = False
            for moment in inside:
                if first - F <= moment <= last + F:
                    hit = True
            self.assertTrue(hit, "套用區 %.3f–%.3f 沒有內部點" % (first, last))
        _probes, verdict = self.check(result, off + F, self.OFF_FRAMES,
                                      1000.0, 1240.0)
        self.assertFalse(verdict["ok"])

    def test_zone_edge_point_outside_programme_range_skipped(self):
        """套用區貼著節目範圍的頭：區外 1 秒已經是片頭動畫，不取。"""
        off = self.OFF_FRAMES * F
        body = program(lo=1000.0, count=30)
        before, before_texts = lines_book(body)
        start, end, text, extra = body[0]
        after_lines = replace_line(body, 0, (start, 1001.5, text, extra),
                                   (1001.5, end, "拆出來的後半句", extra))
        after, after_texts = lines_book(after_lines)
        tgt_book, tgt_texts = lines_book(shifted(body, off))
        result = port.zone_port(before, before_texts, after, after_texts,
                                tgt_book, tgt_texts, 1000.0, 1120.0, off)
        result["range"] = [round(1000.0 + off, 3), round(1120.0 + off, 3)]
        probes = port.probe_points(result, off)
        edges = []
        for probe in probes:
            if probe["kind"] == "edge":
                edges.append(probe["tgt"])
        self.assertEqual(len(edges), 1)
        self.assertGreater(edges[0], result["applied"][0]["tgt"][1])


class TestApplyRollback(ApplyCase):

    def test_apply_failure_rolls_back_everything(self):
        """apply 的順序是覆寫 TSV → publish → 重產 SRT → pairs → 訂正紀錄；
        舊做法中間任何一步拋例外，Kari-SRT 已經改號、訂正紀錄還是舊號，重跑
        又被 sha 擋，只能人工收拾。任何一步失敗要整集回滾。"""
        from scripts.news import paths
        work = paths.work_dir(TGT_SLUG, self.box.store.work)
        os.makedirs(os.path.join(work, "3-refined"))
        self.prepare()
        before = snapshot_tree(self.box.root, skip=("out",))

        def broken(_name):
            raise PipelineError("模擬 pairs 失敗")
        hooks = self.hooks()
        hooks["pairs"] = broken
        with self.assertRaises(PipelineError) as caught:
            self.apply(hooks)
        self.assertIn("回滾", str(caught.exception))
        self.assertEqual(snapshot_tree(self.box.root, skip=("out",)), before)

    def test_rollback_removes_part_files(self):
        """新檔先抄成 `<檔>.part.<pid>` 再改名；改名那一步失敗時，舊做法的
        回滾只放回原檔，`.part` 暫存檔留在 Kari-SRT 的 1-cues 月份目錄，
        之後 rebuild 會掃到。回滾要一起清掉。"""
        self.prepare()
        before = snapshot_tree(self.box.root, skip=("out",))
        timeline = self.box.store.timeline(TGT)
        real = os.replace

        def failing(source, target):
            if target == timeline:
                raise OSError("模擬換檔失敗")
            return real(source, target)
        with mock.patch.object(port.os, "replace", failing):
            with self.assertRaises(PipelineError) as caught:
                self.apply()
        self.assertIn("回滾", str(caught.exception))
        self.assertEqual(snapshot_tree(self.box.root, skip=("out",)), before)

    def append_while(self, line, pending_line):
        """模擬別的 agent（post.py、讀字）在 apply 進行中附加一列。"""
        with open(self.fixes, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        with open(self.pending, "a", encoding="utf-8") as handle:
            handle.write(pending_line + "\n")

    def test_apply_keeps_rows_appended_while_publishing(self):
        """apply 在鎖裡先讀 manual-fixes、pending，做完暫存、publish、render
        （好幾秒）才整檔改名換進去：這段時間 post.py 或讀字的 agent 附加的列
        被蓋掉，靜靜少列。讀、改、寫要一氣呵成，中間不可以有耗時步驟。"""
        other = "20240501_999_午間_Amis_阿美\t7\t甲\t乙\t同時附加"
        other_pending = "2024_999_2024-05-01_午間_Amis_阿美\ts/甲/乙/g\t同時附加"
        self.prepare()
        real = publish.publish_one

        def busy(*args, **kwargs):
            self.append_while(other, other_pending)
            return real(*args, **kwargs)
        with mock.patch.object(publish, "publish_one", busy):
            self.apply()
        with open(self.fixes, encoding="utf-8") as handle:
            self.assertIn(other, handle.read().splitlines())
        with open(self.pending, encoding="utf-8") as handle:
            self.assertIn(other_pending, handle.read().splitlines())

    def test_rollback_keeps_rows_appended_during_apply(self):
        """入庫到一半失敗要回滾，舊做法把 manual-fixes、pending 整檔放回
        apply 開頭抄的那份：apply 期間別人附加的列（publish 時一列、訂正
        紀錄換進去之後又一列）一起不見。回滾只拿掉 apply 自己改的，別人
        附加的留著。"""
        first = "20240501_999_午間_Amis_阿美\t7\t甲\t乙\tpublish 時附加"
        second = "20240501_999_午間_Amis_阿美\t8\t丙\t丁\t換檔後附加"
        first_pending = "2024_999\ts/甲/乙/g\tpublish 時附加"
        second_pending = "2024_999\ts/丙/丁/g\t換檔後附加"
        self.prepare()
        with open(self.fixes, encoding="utf-8") as handle:
            fixes_before = handle.read()
        with open(self.pending, encoding="utf-8") as handle:
            pending_before = handle.read()
        real = publish.publish_one

        def busy(*args, **kwargs):
            self.append_while(first, first_pending)
            return real(*args, **kwargs)

        def broken(_name):
            self.append_while(second, second_pending)
            raise PipelineError("模擬 pairs 失敗")
        hooks = self.hooks()
        hooks["pairs"] = broken
        with mock.patch.object(publish, "publish_one", busy):
            with self.assertRaises(PipelineError) as caught:
                self.apply(hooks)
        self.assertIn("回滾", str(caught.exception))
        with open(self.fixes, encoding="utf-8") as handle:
            self.assertEqual(handle.read(),
                             fixes_before + first + "\n" + second + "\n")
        with open(self.pending, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), pending_before + first_pending
                             + "\n" + second_pending + "\n")

    def check_swapped(self, printed):
        """Kari-SRT 已經換成移植後的時間軸，結尾那行照樣印出快照路徑。"""
        with open(self.box.store.timeline(TGT), encoding="utf-8") as handle:
            book = json.load(handle)
        self.assertEqual(book["ported"][-1]["from"], SRC)
        self.assertIn("入庫完成", printed)
        found = re.search(r"移植前快照 (\S+?)）", printed)
        self.assertIsNotNone(found, printed)
        self.assertTrue(os.path.isdir(found.group(1)))

    def test_cleanup_error_after_swap_only_warns(self):
        """換檔、pairs、訂正紀錄都做完之後，留 .bak（`_keep_backup`）時磁碟
        滿丟 OSError：舊做法 apply 以例外結束、不印結尾那行，批次驅動程式
        看離開碼寫「apply 失敗（已整集回滾）」、項目「整件沒做」，Kari-SRT
        其實已經換掉，快照路徑也抓不到。換檔之後的收尾出錯只警告。"""
        self.prepare()

        def full(_path, _before):
            raise OSError(28, "模擬磁碟滿")
        out = io.StringIO()
        with mock.patch.object(port, "_keep_backup", full), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            self.apply()
        printed = out.getvalue()
        self.check_swapped(printed)
        self.assertIn("警告", printed)
        self.assertIn("模擬磁碟滿", printed)

    def test_cleanup_rmtree_error_after_swap_only_warns(self):
        """收尾刪回滾備份（rmtree）失敗也一樣：資料已經換好，只警告。"""
        self.prepare()
        real = shutil.rmtree

        def stuck(path, *args, **kwargs):
            if os.path.basename(path) == "backup":
                raise OSError(16, "模擬刪不掉")
            return real(path, *args, **kwargs)
        out = io.StringIO()
        with mock.patch.object(port.shutil, "rmtree", stuck), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            self.apply()
        printed = out.getvalue()
        self.check_swapped(printed)
        self.assertIn("模擬刪不掉", printed)

    def test_sigterm_during_swap_rolls_back(self):
        """換檔換到一半收到 SIGTERM（Bash 逾時、執行者被停）：舊做法照預設
        直接死掉，Kari-SRT 半套、不回滾、驅動程式也寫不出 result.json。
        換檔那段收到 SIGTERM 要整集回滾再結束；做完把原本的處理方式放回去。"""
        class Sentinel(BaseException):
            pass

        def sentinel(_signum, _frame):
            raise Sentinel()
        old = signal.signal(signal.SIGTERM, sentinel)
        self.addCleanup(signal.signal, signal.SIGTERM, old)
        self.prepare()
        before = snapshot_tree(self.box.root, skip=("out",))

        def killed(_name):
            os.kill(os.getpid(), signal.SIGTERM)
        hooks = self.hooks()
        hooks["pairs"] = killed
        with self.assertRaises(PipelineError) as caught:
            self.apply(hooks)
        self.assertIn("回滾", str(caught.exception))
        self.assertIn("SIGTERM", str(caught.exception))
        self.assertEqual(snapshot_tree(self.box.root, skip=("out",)), before)
        self.assertIs(signal.getsignal(signal.SIGTERM), sentinel)

    def test_no_frames_reason_recorded_in_timeline(self):
        """--no-frames 的理由要寫進時間軸的移植紀錄，事後才查得到哪幾集
        免做像素驗收、理由是什麼。"""
        self.prepare()
        self.apply()
        with open(self.box.store.timeline(TGT), encoding="utf-8") as handle:
            book = json.load(handle)
        self.assertEqual(book["ported"][-1]["no_frames"], "合成測試沒有影片")
        self.assertEqual(book["ported"][-1]["mode"], "whole")


def snapshot_tree(root, skip=()):
    """目錄底下每個檔的相對路徑和內容（回滾前後比對用）。"""
    out = {}
    for folder, dirs, files in os.walk(root):
        rel = os.path.relpath(folder, root)
        if rel.split(os.sep)[0] in skip:
            continue
        for name in files:
            if name == "store.lock":
                continue
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                out[os.path.join(rel, name)] = handle.read()
        for name in dirs:
            out[os.path.join(rel, name) + "/"] = b""
    return out


THIRD = "20240420_150_午間_Kavalan_噶瑪蘭"
THIRD_SLUG = "2024_150_2024-04-20_午間_Kavalan_噶瑪蘭"


class TestZoneStore(unittest.TestCase):
    """分區搬走完 prepare、apply：首播修改前快照 → 首播現在的差，套到重播。"""

    def setUp(self):
        self.box = Store()
        self.addCleanup(self.box.tmp.cleanup)
        self.box.entries.append({"srt_name": THIRD, "slug": THIRD_SLUG})
        self.off = 199.132
        body = program(lo=1000.0, count=30)
        before_lines = [(970.0, 974.0, own(901), {})] + body + [
            (1130.0, 1134.0, own(903), {})]
        before_lines[11] = before_lines[11][:2] + ("第010句萬用鐮", {})
        after_lines = list(before_lines)
        start, end, text, extra = after_lines[6]
        after_lines[6:7] = [(start, 1022.0, text, extra),
                            (1022.0, end, "口簧琴是不能隨便的", extra)]
        after_lines[12] = after_lines[12][:2] + ("第010句萬用鏟", {})
        self.tgt_lines = [(1150.0, 1154.0, own(1), {})] + shifted(
            before_lines[1:-1], self.off) + [(1340.0, 1344.0, own(3), {})]
        table = [seg("0", "1000", "攝影棚", "722", "848"),
                 seg("1000", "1120", "島語時間", "940", "1060"),
                 seg("1120", "1400", "攝影棚", "722", "848")]
        before, before_texts = lines_book(before_lines, {"島語時間": ISLAND})
        after, after_texts = lines_book(after_lines, {"島語時間": ISLAND})
        target, target_texts = lines_book(self.tgt_lines,
                                          {"島語時間": ISLAND})
        self.box.put(SRC, after, after_texts, table)
        self.box.put(TGT, target, target_texts,
                     [seg("0", "1199", "攝影棚", "722", "848"),
                      seg("1199", "1319", "島語時間", "940", "1060"),
                      seg("1319", "1400", "攝影棚", "722", "848")])
        self.snaps = os.path.join(self.box.root, "fix", "snap")
        self.box.snapshot(self.snaps, SRC, "main", before, before_texts)
        units = os.path.join(self.box.root, "fix", "units")
        os.makedirs(units)
        # 首播那個單元的工作檔只列了第二處（1043–1048）：拆句在 1022，
        # 不在 items 裡也要找得到（305→306 有 5 處就是這樣被丟掉）。
        with open(os.path.join(units, SRC + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"items": [{"seconds": "1043-1048"}]}, handle,
                      ensure_ascii=False, indent=2, sort_keys=True)
        self.fixes = os.path.join(self.box.root, "manual-fixes.tsv")
        with open(self.fixes, "w", encoding="utf-8") as handle:
            handle.write("%s\t13\t萬用鐮\t萬用鏟\t明顯錯字\n" % SRC)
        self.out = os.path.join(self.box.root, "out")
        self.lock = os.path.join(self.box.root, "store.lock")

    def prepare(self, src=SRC, tgt=TGT, lo=1000.0, hi=1120.0, out=None):
        return port.prepare(src, tgt, lo, hi, out or self.out,
                            store=self.box.store, fixes=self.fixes,
                            entries=self.box.entries, snaps=self.snaps)

    def apply(self, out=None, hooks=None):
        return port.apply(os.path.join(out or self.out, "plan.json"),
                          self.lock, self.fixes,
                          no_frames="合成測試沒有影片", store=self.box.store,
                          entries=self.box.entries, snaps=self.snaps,
                          hooks=hooks or {"pairs": lambda name: None,
                                          "fixlog": lambda path: None})

    def test_zone_mode_prepare_and_apply(self):
        """重播那段本來就有字（30 句）、切法設定一樣 → 自動走分區搬：首播拆
        了一句（在工作檔 items 以外）、改了一個字，重播只多一條、改一個字，
        其他 cue 的時間和字不動；首播那列訂正抄給重播；apply 前替重播拍快照
        （標籤 x 加首播名前 12 字），時間軸記一筆 mode zone、指到那份快照。"""
        plan = self.prepare()
        self.assertEqual(plan["mode"], "zone")
        self.assertEqual(plan["status"], "ready", plan["reasons"])
        self.assertEqual(plan["summary"]["applied"], 2)
        self.assertEqual(plan["summary"]["after"],
                         plan["summary"]["before"] + 1)
        with open(self.box.store.timeline(TGT), encoding="utf-8") as handle:
            original = handle.read()
        self.apply()
        loaded = port.load(TGT, self.box.store)
        texts = loaded["texts"]
        self.assertEqual(texts[7], say(5))
        self.assertEqual(texts[8], "口簧琴是不能隨便的")
        self.assertEqual(texts[13], "第010句萬用鏟")
        self.assertEqual(len(loaded["book"]["cues"]), 33)
        entry = loaded["book"]["ported"][-1]
        self.assertEqual(entry["mode"], "zone")
        tag = "x" + SRC[:12]
        self.assertEqual(entry["snapshot"], "%s--%s" % (TGT, tag))
        chain = port.snapshot_chain(self.snaps, TGT)
        self.assertEqual(chain[-1][0], tag)
        saved = self.box.store.under(os.path.join(chain[-1][1], "files"))
        with open(saved.timeline(TGT), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)
        self.assertTrue(os.path.exists(os.path.join(chain[-1][1],
                                                    "manifest.txt")))
        with open(self.fixes, encoding="utf-8") as handle:
            rows = handle.read().splitlines()
        self.assertIn("%s\t13\t萬用鐮\t萬用鏟\t明顯錯字" % SRC, rows)
        carried = []
        for row in rows:
            if row.startswith(TGT + "\t13\t萬用鐮\t萬用鏟\t"):
                carried.append(row)
        self.assertEqual(len(carried), 1)
        self.assertIn("移植自", carried[0])

    def test_target_recut_listed_for_review_not_ported(self):
        """重播自己重切過（最早那份快照是島語、現在是花字），首播一直是
        島語：不搬，整件列要人判（status ask），不寫預覽。"""
        loaded = port.load(TGT, self.box.store)
        self.box.snapshot(self.snaps, TGT, "main")
        book = loaded["book"]
        book["areas"] = {"島語時間": FLOWER}
        self.box.put(TGT, book, loaded["texts"],
                     [seg("0", "1199", "攝影棚", "722", "848"),
                      seg("1199", "1319", "島語時間", "940", "1060"),
                      seg("1319", "1400", "攝影棚", "722", "848")])
        plan = self.prepare()
        self.assertEqual(plan["status"], "ask", plan["reasons"])
        self.assertEqual(plan["mode"], "ask")
        self.assertTrue(mentions(plan["reasons"], "重播", "重切"),
                        plan["reasons"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "preview")))
        with open(os.path.join(self.out, "report.txt"),
                  encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("要人判", body)
        self.assertEqual(body.count("重播自己重切過"), 1, body)

    def test_zone_with_other_area_setting_survives_apply(self):
        """兩集都沒重切過、只是本來切法就不同（重播「島語時間」是花字）：
        走分區搬；搬進來的 cue 標首播設定的新名字，入庫後 areas 兩格都在、
        每條 cue 的 area 都查得到，publish 不會把它判成過期。"""
        loaded = port.load(TGT, self.box.store)
        book = loaded["book"]
        book["areas"] = {"島語時間": FLOWER}
        self.box.put(TGT, book, loaded["texts"],
                     [seg("0", "1199", "攝影棚", "722", "848"),
                      seg("1199", "1319", "島語時間", "940", "1060"),
                      seg("1319", "1400", "攝影棚", "722", "848")])
        self.box.snapshot(self.snaps, TGT, "main")
        plan = self.prepare()
        self.assertEqual(plan["mode"], "zone", plan.get("mode_stats"))
        self.assertEqual(plan["status"], "ready", plan["reasons"])
        self.apply()
        book = port.load(TGT, self.box.store)["book"]
        self.assertEqual(book["areas"]["島語時間"], FLOWER)
        self.assertEqual(len(book["areas"]), 2)
        names = set()
        for item in book["cues"]:
            if item.get("area"):
                self.assertIn(item["area"], book["areas"])
                names.add(item["area"])
        self.assertEqual(len(names), 2)
        entry = {"srt_name": TGT, "slug": TGT_SLUG}
        work = os.path.join(self.box.root, "tmpwork")
        port.temp_workdir(work, os.path.join(self.out, "preview"))
        self.assertEqual(publish.areas_only_in_store(
            entry, os.path.join(work, "3-refined", "cues.json"),
            self.box.store.cues), [])

    def test_zone_report_lists_source_text_target_lacks(self):
        """重播漏收首播第 20 句（首播沒改過那句，不在任何區）：plan、
        report.txt 都要列「首播有字、重播沒字」，summary 記幾處；不搬，
        status 照樣 ready（另外兩區照套）。"""
        loaded = port.load(TGT, self.box.store)
        book, texts = loaded["book"], loaded["texts"]
        drop(book, texts, 22)
        self.box.put(TGT, book, texts,
                     [seg("0", "1199", "攝影棚", "722", "848"),
                      seg("1199", "1319", "島語時間", "940", "1060"),
                      seg("1319", "1400", "攝影棚", "722", "848")])
        plan = self.prepare()
        self.assertEqual(plan["status"], "ready", plan["reasons"])
        self.assertEqual(plan["summary"]["applied"], 2)
        self.assertEqual(plan["summary"]["blank_in_target"], 1)
        self.assertEqual(plan["blank_in_target"][0]["text"], say(20))
        with open(os.path.join(self.out, "report.txt"),
                  encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("首播有字、重播沒字", body)
        self.assertIn(say(20), body)

    def test_zone_without_snapshot_refused(self):
        """重播那段有字、卻沒有首播快照：不知道首播改過哪裡，不可以退回整段
        搬，要擋並講原因。"""
        plan = port.prepare(SRC, TGT, 1000.0, 1120.0, self.out,
                            store=self.box.store, fixes=self.fixes,
                            entries=self.box.entries)
        self.assertEqual(plan["mode"], "zone")
        self.assertEqual(plan["status"], "rejected")
        self.assertTrue(mentions(plan["reasons"], "快照"))

    def test_snapshot_tag_never_reuses_old_one(self):
        """重播已經有 `x20240315_075` 這份快照（上一輪移植前拍的）：沿用就
        會把這次移植前的狀態當成上一輪的，鏈式移植算錯「首播改過的地方」。
        已存在就加 `-r<MMDDHHMM>` 新標籤，連那個也有就擋。"""
        snaps = os.path.join(self.box.root, "tags")
        self.assertEqual(port.snapshot_tag(snaps, TGT, SRC, "10271923"),
                         "x20240315_075")
        os.makedirs(os.path.join(snaps, "%s--x20240315_075" % TGT))
        self.assertEqual(port.snapshot_tag(snaps, TGT, SRC, "10271923"),
                         "x20240315_075-r10271923")
        os.makedirs(os.path.join(snaps,
                                 "%s--x20240315_075-r10271923" % TGT))
        with self.assertRaises(PipelineError):
            port.snapshot_tag(snaps, TGT, SRC, "10271923")

    def test_chain_carries_ported_changes_downstream(self):
        """A→B→C：B 當首播時，A→B 搬進 B 的修改要算在 B「被修過的地方」。
        上一個做法 apply 不拍快照，B→C 看不到這些修改。apply 替 B 拍的快照
        就是 B 最早的修改前狀態，B→C 照它算差。"""
        plan = self.prepare()
        self.assertEqual(plan["status"], "ready", plan["reasons"])
        self.apply()
        third_lines = shifted(self.tgt_lines, 50.0)
        third, third_texts = lines_book(third_lines, {"島語時間": ISLAND})
        self.box.put(THIRD, third, third_texts,
                     [seg("0", "1249", "攝影棚", "722", "848"),
                      seg("1249", "1369", "島語時間", "940", "1060"),
                      seg("1369", "1450", "攝影棚", "722", "848")])
        out = os.path.join(self.box.root, "out2")
        second = self.prepare(TGT, THIRD, 1199.132, 1319.132, out)
        self.assertEqual(second["mode"], "zone")
        self.assertEqual(second["status"], "ready", second["reasons"])
        self.assertEqual(second["summary"]["applied"], 2)
        self.apply(out)
        texts = port.load(THIRD, self.box.store)["texts"]
        self.assertIn("口簧琴是不能隨便的", texts.values())
        self.assertIn("第010句萬用鏟", texts.values())

    def test_zone_apply_failure_rolls_back_snapshot_and_fixes(self):
        """分區搬入庫到一半失敗（pairs 失敗；或訂正紀錄已經重寫、fixlog 才
        失敗）：整集回滾，含剛拍的快照、manual-fixes，不留 .bak。舊測試只
        測過整段搬的 pairs 失敗。"""
        self.prepare()
        before = snapshot_tree(self.box.root, skip=("out",))

        def broken(_value):
            raise PipelineError("模擬失敗")
        for hooks in ({"pairs": broken, "fixlog": lambda path: None},
                      {"pairs": lambda name: None, "fixlog": broken}):
            with self.assertRaises(PipelineError) as caught:
                self.apply(hooks=hooks)
            self.assertIn("回滾", str(caught.exception))
            self.assertEqual(snapshot_tree(self.box.root, skip=("out",)),
                             before)


if __name__ == "__main__":
    unittest.main()
