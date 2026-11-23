"""清洗的輸出位置。

各層目錄照產出順序編號。**Kari-SRT 只讀**：輸出目錄或任何一個
要寫的檔落在 Kari-SRT 底下，就當場中止——交付資料一個 byte 都不能
被這條線改到（使用者裁定 2026-10-15）。
"""
import os

from scripts import datadirs
from scripts.datadirs import KARI
from scripts.datadirs import KITHANN
from scripts.errors import PipelineError

OUT = os.path.join(KITHANN, "out", "aiyalaeho-清洗")


def targets(catalogue):
    """清洗範圍：節目目錄已交付的集（交付 SRT 已存在、不在版型異常表），
    照成果檔名排序。

    第2-1期寫死承辦指名的 10 集；第2-2期要全交，範圍就跟著目錄走
    （使用者裁定 2026-11-23）。catalogue 是 `episodes.load()` 的條目，
    list 或 {成果檔名: 條目} 都可以。
    """
    if isinstance(catalogue, dict):
        catalogue = catalogue.values()
    names = []
    for entry in catalogue:
        if entry["pending"] or entry["abnormal"]:
            continue
        names.append(entry["srt_name"])
    return sorted(names)


def _inside(path, folder):
    """path 是不是 folder 本身或它底下。比路徑成分，不比字串開頭。"""
    path = os.path.abspath(path)
    folder = os.path.abspath(folder)
    return path == folder or path.startswith(folder + os.sep)


def guard(path):
    """要寫的檔不在 Kari-SRT 底下才放行，原樣送回。"""
    if _inside(path, KARI):
        raise PipelineError("清洗不寫 Kari-SRT，拒絕寫入：%s" % path)
    return path


class Layout(object):
    """一個輸出根目錄底下的各層位置。建構時先擋 Kari-SRT。"""

    def __init__(self, root=OUT):
        self.root = guard(root)
        self.klokah = os.path.join(root, "1-詞庫", "E樂園")
        self.kaldi = os.path.join(root, "1-詞庫", "Kaldi詞表")
        self.candidates = os.path.join(root, "2-候選")
        self.text_verdicts = os.path.join(root, "3-判定", "文字分類")
        self.image_verdicts = os.path.join(root, "3-判定", "看圖")
        # 使用者看過結果後手寫的改判（哪些錯字改列待討論、不改）。
        self.overrides = os.path.join(root, "3-判定", "人工改判.csv")
        self.cleaned = os.path.join(root, "4-清洗版")
        self.deliver = os.path.join(root, "5-交付")


# 族語E樂園 教材匯出的位置（新聞平行語料也讀，所以定義在 datadirs）。
KLOKAH_SOURCE = datadirs.KLOKAH_SOURCE
KLOKAH_NAMES = datadirs.KLOKAH_NAMES

# 官方辭典各族只收一個語別（xlsx「語別」欄）。值是語言別名稱（E樂園
# 語別全名剝掉族語別），整欄空白的族語寫空字串。阿美、泰雅、卑南、
# 賽夏 2026-10-15 量；其餘 2026-11-23 量（魯凱、賽德克、拉阿魯哇、
# 太魯閣目前各 1 集、用不到，先記上）。
DICTIONARY_VARIETY = {"阿美": "秀姑巒", "泰雅": "賽考利克", "卑南": "南王",
                      "賽夏": "", "布農": "郡群", "排灣": "北排灣",
                      "雅美": "", "魯凱": "霧台", "賽德克": "德固達雅",
                      "拉阿魯哇": "", "太魯閣": ""}


def dictionary_variety(language):
    """該族官方辭典收的語別。沒量過就中止——當成不分語別的話，辭典
    永遠不會被當權威，錯得悄悄的。"""
    if language not in DICTIONARY_VARIETY:
        raise PipelineError("辭典語別表沒有「%s」：先量官方辭典 xlsx 的"
                            "「語別」欄再補進 DICTIONARY_VARIETY" % language)
    return DICTIONARY_VARIETY[language]
