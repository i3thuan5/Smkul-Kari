"""b、c 項候選：一個族語的每個詞形一列，證據並排，初篩決定哪些送 Claude。

**「該集語別」才是權威**，不是辭典：辭典一族只收一個語別，087 卑南
推測是西群，它的 harem 南王辭典沒有（只收 garem），西群 E樂園 有——
拿辭典判就把語言別差異當錯字。所以每集的權威＝該集語別（dialect.infer 給的
considered）的 E樂園 詞表，該語別剛好是辭典的語別時再加上辭典。

初篩四種：

  該集語別見過      出現的每一集，權威都收 → 不是錯字候選
  其他語別見過      辭典或該族其他語別的 E樂園 收 → 待討論，不送
  只有Kaldi詞表見過 語音模型詞表收（有、但不知道哪個語別）→ 不改，不送
  送文字分類        哪裡都沒有 → 交 Claude 判

**不套 vocab.fold 的語言別正音**：它會把 082 的 kaku 折成 kako，語言別差異
就從表上消失。比對只做大小寫與撇號（’ʼ → '）。

相近寫法＝編輯距離 1（詞長 ≥ 4）。只差一個字母不等於錯字（kamo／
kamok 是兩個詞），所以只列出、不判定。分組只在這一層做語言別差異對：兩邊
都有語別證據、語別不重疊 → 語言別差異，連成一組；有共同語別 → 不同詞，
不連。送判的詞不連（會一路串成幾十個詞的一組），等判完在報表那一層
照「錯字 → 建議寫法」分組。

節目名 'a'iyalaeho:（賽夏語「開會了」）在每一族的字幕裡都有，錯拼也
跨族語，所以另外處理（programme_variants），不進一般候選。
"""
import collections
import unicodedata

from scripts.aiyalaeho.cleaning import rules
from scripts.lexicon import script

SEEN_HERE = "該集語別見過"
SEEN_ELSEWHERE = "其他語別見過"
KALDI_ONLY = "只有Kaldi詞表見過"
SEND = "送文字分類"

DIALECT = "語言別差異"

NEIGHBOUR_MIN = 4

PROGRAMME = "'a'iyalaeho:"
PROGRAMME_KEY = "aiyalaeho"

HEADER = ["詞形", "出現集數", "各集次數", "辭典", "E樂園見過的語別",
          "Kaldi詞表", "開會了全語料次數", "上字文稿次數",
          "最接近的辭典詞條", "相近寫法", "初篩", "組別"]

EpisodeText = collections.namedtuple(
    "EpisodeText", "srt_name language considered entries")

# dictionary：辭典詞庫 set；klokah：{語別: set}；kaldi：set；
# corpus：{詞: Counter(集數)}，開會了該族全部已交付集；transcripts：
# Counter，上字文稿；dict_variety：辭典收的語別（賽夏是空字串）。
Evidence = collections.namedtuple(
    "Evidence", "dictionary klokah kaldi corpus transcripts dict_variety")


class Candidate(object):
    def __init__(self, key):
        self.key = key
        self.forms = collections.Counter()
        self.episodes = collections.Counter()
        self.occurrences = []
        self.seen = []
        self.screen = ""
        self.varieties = ()
        self.in_dict = False
        self.in_kaldi = False
        self.nearest = []
        self.neighbours = []
        self.group = ""

    @property
    def display(self):
        """出現最多次的原樣寫法；同次數照字母排，重跑一樣。"""
        return sorted(self.forms, key=lambda f: (-self.forms[f], f))[0]


def episode_number(srt_name):
    return srt_name.split("_")[1]


def _word_char(char):
    return (unicodedata.category(char) in script.LETTER_CATEGORIES
            or char in script.WORD_MARKS or char in script.APOSTROPHES)


def spans(text):
    """[(起, 迄, 詞)…]：跟 script.words 同一把尺，但保留大小寫與位置。

    位置是清洗版以詞為單位替換要用的——字串替換會把 kako 改到 kakoay
    裡面去。撇號正規化成 '，長度不變，位置照用。
    """
    out = []
    start = None
    for index in range(len(text) + 1):
        inside = index < len(text) and _word_char(text[index])
        if inside and start is None:
            start = index
        elif not inside and start is not None:
            token = text[start:index]
            for mark in script.APOSTROPHES:
                token = token.replace(mark, "'")
            if (len(token) >= script.MIN_WORD
                    and token.strip(script.WORD_MARKS)):
                out.append((start, index, token))
            start = None
    return out


def tokens(text):
    """跟 script.words 同一把尺，但保留大小寫（報表要原樣）。"""
    out = []
    for _start, _end, token in spans(text):
        out.append(token)
    return out


def tentative(text):
    """規則清洗後、再暫時把「’ 夾空白」併起來的文字。

    087「mena’   u」切開會變成 mena' 和 u（太短被丟），mena' 查不到就
    被當錯字候選——但它是要看圖的撇號問題，不是拼寫問題。併起來的
    mena'u 西群 E樂園 有，才是對的比對對象。
    """
    out = rules.clean(text)[0]
    for gap in rules.apostrophe_gaps(text):
        out = out.replace(gap.cleaned, gap.joined)
    return out


def distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _programme_key(token):
    return token.lower().replace("'", "").replace(":", "")


def is_programme_like(token):
    """全語料掃過（2026-10-15）：錯拼都在編輯距離 2 以內（'a'alaeho:、
    'a'iylahaeho:）。冒號後面還接字母的是衍生詞（'a'iyalaeho:an），不算。
    """
    _head, colon, tail = token.partition(":")
    if colon and tail.strip("'"):
        return False
    key = _programme_key(token)
    return abs(len(key) - len(PROGRAMME_KEY)) <= 2 and \
        distance(key, PROGRAMME_KEY) <= 2


def programme_variants(text):
    """這一列裡節目名的錯拼（原樣），正確的 'a'iyalaeho: 不算。"""
    out = []
    for token in tokens(text):
        if is_programme_like(token) and token.lower() != PROGRAMME:
            out.append(token)
    return out


def _deletions(word):
    out = []
    for index in range(len(word)):
        out.append((index, word[:index] + word[index + 1:]))
    return out


class _Index(object):
    """編輯距離 1 的查找：替換靠「同位置刪一字相同」，增刪靠「刪一字等於對方」。"""

    def __init__(self, words):
        self.words = set(words)
        self.substitute = collections.defaultdict(set)
        self.shorter = collections.defaultdict(set)
        for word in self.words:
            for index, rest in _deletions(word):
                self.substitute[(index, rest)].add(word)
                self.shorter[rest].add(word)

    def near(self, word):
        found = set()
        for index, rest in _deletions(word):
            found.update(self.substitute.get((index, rest), ()))
            if rest in self.words:
                found.add(rest)
        found.update(self.shorter.get(word, ()))
        found.discard(word)
        return found


class Built(object):
    def __init__(self, words, group_kind, evidence, authorities=None,
                 considered=None):
        self.words = words
        self.group_kind = group_kind
        self.evidence = evidence
        # {成果檔名: 該集權威詞集}、{成果檔名: 該集語別…}：建議寫法要問
        # 「這個寫法在該集語別裡有沒有」。
        self.authorities = authorities or {}
        self.considered = considered or {}

    def authorised(self, word, key):
        """word（小寫）在 key 出現的每一集的權威裡都有。"""
        names = set()
        for srt_name, _number in self.words[key].occurrences:
            names.add(srt_name)
        if not names:
            return False
        for srt_name in names:
            if word not in self.authorities.get(srt_name, ()):
                return False
        return True

    def to_send(self):
        out = []
        for key in sorted(self.words):
            if self.words[key].screen == SEND:
                out.append(key)
        return out

    def counts(self, key):
        corpus = self.evidence.corpus.get(key)
        if corpus:
            return corpus
        return self.words[key].episodes

    def described(self, key):
        """「Likavung（087:10;106:1）」：寫法加開會了各集次數。"""
        counts = self.counts(key)
        parts = []
        for number in sorted(counts):
            parts.append("%s:%d" % (number, counts[number]))
        form = self.words[key].display if key in self.words else key
        return "%s（%s）" % (form, ";".join(parts))

    def rows(self):
        out = [list(HEADER)]
        for key in sorted(self.words):
            word = self.words[key]
            numbers = []
            per = []
            for number in sorted(word.episodes):
                numbers.append(number)
                per.append("%s:%d" % (number, word.episodes[number]))
            near = []
            for other in word.neighbours:
                near.append(self.described(other))
            out.append([
                word.display, ";".join(numbers), ";".join(per),
                "有" if word.in_dict else "無", ";".join(word.varieties),
                "有" if word.in_kaldi else "無",
                str(sum(self.counts(key).values())),
                str(self.evidence.transcripts.get(key, 0)),
                ";".join(word.nearest[:3]), "、".join(near), word.screen,
                word.group,
            ])
        return out


def _authority(considered, evidence):
    words = set()
    for variety in considered:
        words |= evidence.klokah.get(variety, set())
        if variety == evidence.dict_variety:
            words |= evidence.dictionary
    return words


def _attested(key, evidence):
    """這個詞在哪些語別有書面證據（E樂園 各語別＋辭典的語別）。"""
    found = set()
    for variety in evidence.klokah:
        if key in evidence.klokah[variety]:
            found.add(variety)
    if key in evidence.dictionary:
        found.add(evidence.dict_variety)
    return found


def build(episodes, evidence):
    """一個族語的候選。episodes 是這族要清洗的集（EpisodeText）。"""
    words = {}
    authorities = {}
    considered = {}
    for episode in episodes:
        authority = _authority(episode.considered, evidence)
        authorities[episode.srt_name] = authority
        considered[episode.srt_name] = episode.considered
        number = episode_number(episode.srt_name)
        for entry in episode.entries:
            for token in tokens(tentative(entry.formosan)):
                if is_programme_like(token):
                    continue
                key = token.lower()
                word = words.setdefault(key, Candidate(key))
                word.forms[token] += 1
                word.episodes[number] += 1
                word.occurrences.append((episode.srt_name, entry.number))
                word.seen.append(key in authority)

    dictionary = _Index(evidence.dictionary)
    for key, word in words.items():
        varieties = _attested(key, evidence)
        word.in_dict = key in evidence.dictionary
        word.in_kaldi = key in evidence.kaldi
        klokah = set()
        for variety in evidence.klokah:
            if key in evidence.klokah[variety]:
                klokah.add(variety)
        word.varieties = tuple(sorted(klokah))
        if all(word.seen):
            word.screen = SEEN_HERE
        elif varieties:
            word.screen = SEEN_ELSEWHERE
        elif word.in_kaldi:
            word.screen = KALDI_ONLY
        else:
            word.screen = SEND
        if not word.in_dict:
            word.nearest = sorted(dictionary.near(key))

    long_words = []
    for key in words:
        if len(key) >= NEIGHBOUR_MIN:
            long_words.append(key)
    index = _Index(long_words)
    links = []
    for key in sorted(long_words):
        near = sorted(index.near(key))
        words[key].neighbours = near
        for other in near:
            if other < key:
                continue
            kind = _link(words[key], words[other], evidence)
            if kind:
                links.append((key, other, kind))
    group_kind = _groups(words, links, episodes)
    return Built(words, group_kind, evidence, authorities, considered)


def _link(a, b, evidence):
    # 送判的詞不在這一層連線：卑南真資料經「差一個字母」一路串成 68
    # 個詞的一組。它們的分組等 Claude 判完、照「錯字 → 建議寫法」在
    # 報表那一層做。
    if a.screen == SEND or b.screen == SEND:
        return ""
    va = _attested(a.key, evidence)
    vb = _attested(b.key, evidence)
    if va and vb and not (va & vb):
        return DIALECT
    return ""


def _groups(words, links, episodes):
    parent = {}

    def root(key):
        while parent.get(key, key) != key:
            key = parent[key]
        return key

    for a, b, _kind in links:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    members = collections.defaultdict(list)
    for a, b, _kind in links:
        members[root(a)].extend((a, b))
    language = episodes[0].language if episodes else ""
    group_kind = {}
    for number, head in enumerate(sorted(members), start=1):
        name = "%s-%03d" % (language, number)
        for key in set(members[head]):
            words[key].group = name
        group_kind[name] = DIALECT
    return group_kind
