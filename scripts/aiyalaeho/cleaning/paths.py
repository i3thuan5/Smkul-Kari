"""清洗的輸出位置。

各層目錄照產出順序編號。**Kari-SRT 只讀**：輸出目錄或任何一個
要寫的檔落在 Kari-SRT 底下，就當場中止——交付資料一個 byte 都不能
被這條線改到（使用者裁定 2026-10-15）。
"""
import os

from scripts.datadirs import KARI
from scripts.datadirs import KITHANN
from scripts.errors import PipelineError

OUT = os.path.join(KITHANN, "out", "aiyalaeho-清洗")

# 承辦講的「10 則影片」：第1期交付 4 集（068、079、081、082）加第2-1期
# 新增 6 集。清單正本是 kithann/驗收/第2-1期/開會了清單.csv（gitignore），
# 所以這裡跟著 repo 留一份。
TARGETS = (
    "開會了_068_Amis_阿美",
    "開會了_079_SaySiyat_賽夏",
    "開會了_081_Bunun_布農",
    "開會了_082_Amis_阿美",
    "開會了_084_Amis_阿美",
    "開會了_085_Atayal_泰雅",
    "開會了_086_Pinuyumayan_卑南",
    "開會了_087_Pinuyumayan_卑南",
    "開會了_091_Atayal_泰雅",
    "開會了_092_SaySiyat_賽夏",
)


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


# 族語E樂園 教材匯出：原檔在 kithann/E樂園/（含音檔），文字檔（csv、xml）
# 另外解到 E樂園-解壓/ 給 lexicon/klokah.py 讀。語言別編號表跟著原檔放。
KLOKAH_SOURCE = os.path.join(KITHANN, "E樂園-解壓")
KLOKAH_NAMES = os.path.join(KITHANN, "E樂園", "E樂園方言編號.txt")

# 官方辭典各族只收一個語別（xlsx「語別」欄，2026-10-15 量）。賽夏不分
# 語別，欄是空的。
DICTIONARY_VARIETY = {"阿美": "秀姑巒", "泰雅": "賽考利克", "卑南": "南王",
                      "賽夏": ""}
