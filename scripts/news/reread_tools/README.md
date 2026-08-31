# reread_tools/ ——全批重讀ê驅動程式

這四支是**驅動**，毋是引擎。判準佮純函式佇 `scripts/news/` ê
`blind_cues.py`（出題）、`reread.py`（切段）、`resplit.py`（寫入時間軸、
把關），彼幾支有測試。遮ê干焦是kā in 串起來、動檔案。

放佇遮是因為 in 走過十六集、已經穩定，毋是暫時ê 手路。原本囥佇
scratchpad，彼是 session 專屬ê，會無去。

| 檔 | 做啥 |
|---|---|
| `prompt.py` | 印一批ê讀者提示（判準ê正本囥佇 `brief.md`） |
| `allsheets.py` | 逐集切段出圖條，會跳過做過ê（可續跑） |
| `safe_resplit.py` | 逐條把關（`resplit.survives`），過ê才切，寫 cues.json ＋ TSV |
| `regen_strips.py` | 照新編號重生 strips／sheets／sheets.json（**兩个參數：NAME SLUG**，閣愛 numpy，用 `.tox/rebuild/bin/python` 走） |
| `fix_rtf.py` | kā `4-vision-rtf` 疊層重編號（**無做這步 `rebuild --verify` 會炸**） |

## 一集ê順序

```bash
set -o pipefail                       # 無這逝，`| tail` 會kā `&&` 廢掉
N=<srt_name>; SLUG=<slug>             # slug 對 Kari-SRT/news/inventory.json 提
PYTHONPATH=. python3 scripts/news/reread_tools/safe_resplit.py "$N" --write && \
PYTHONPATH=. .tox/rebuild/bin/python scripts/news/reread_tools/regen_strips.py "$N" "$SLUG" && \
PYTHONPATH=. python3 scripts/news/reread_tools/fix_rtf.py "$N" && \
PYTHONPATH=. python3 -m scripts.news.ingest "$SLUG" && \
PYTHONPATH=. python3 -m scripts.news.make_all && \
PYTHONPATH=. python3 -m scripts.news.publish && \
.tox/rebuild/bin/python -m scripts.news.rebuild --verify
```

派視覺辨識ê提示用 `prompt.py` 印：

```bash
PYTHONPATH=. python3 scripts/news/reread_tools/prompt.py <srt_name> a
PYTHONPATH=. python3 scripts/news/reread_tools/prompt.py <srt_name> b
```

一批若做一半予額度中斷（已經三擺），`read_*.tsv` 內底已經寫落ê逝
是好ê——`prompt.py` 提第三个參數指定逝ê範圍，補做ê部份寫做別个檔
（`safe_resplit` 是 glob `read*.tsv`，免合併）：

```bash
PYTHONPATH=. python3 scripts/news/reread_tools/prompt.py <srt_name> a2 101-120
```

判準ê正本是 `brief.md`；集數家己ê數字（段數、圖條範圍、work dir、有
無 `4-vision-rtf`）攏對磁碟讀，批次切佇**圖條ê邊界**。判準一改，改
`brief.md` 一擺，後壁逐批攏會著。手改提示是判準會恬恬走鐘ê所在——
漏去彼批讀出來佮厝邊無仝，煞無人會講。

`allsheets`（一擺跑規批）佮派視覺辨識佇這條ê頭前。`fix_rtf` 彼步干焦
該集有 `4-vision-rtf` 才做。

**`ingest` 是這條線ê守門ê。** 伊會kā TSV 內底ê 編號佮 `sheets.json` 對，
無合就規个擋落來、一字都無寫（`PROBLEM ... was not on any sheet given to
a reader`）。所以 `regen_strips` 若倒去，ingest 會替你掠著——毋過**愛
先確定伊真正有走**，`| tail` 彼个坑就是按呢予人食去ê。

## 改一擺 cue 編號愛同齊振動ê五樣

踏過五擺才收齊：

```
cues.json           時間軸
b*.tsv              3-vision，視覺辨識讀ê
transcripts.json    **正本**（`ingest` 是合併毋是取代——有 16 集ê TSV
                    無涵蓋規模ê cue，彼寡是 RTF 供字ê，字干焦佇遮）
sheets.json         `ingest` 提伊驗編號
4-vision-rtf/*.tsv  文稿疊層，`rebuild` ê時**贏過** 3-vision
strips/ 檔名        照編號號名
```

**2 月 054–059 這 14 集是對頭做起ê，切 cue 愛指定 `--preset titv-news`。**
`presets.json` ê `titv-news` 是比對**檔名內底ê `NL00`**（原始來源
`21NL003_54午間族語新聞.mxf`），毋過 kithann/out/mkv/ ê檔名是用
`srt_name` 號ê（`20210223_054_午間_Kavalan_噶瑪蘭.mkv`），比袂著。
無指定ê時伊會家己偵測，出來是 `0,588,1920,436`——436 列懸，紅帶
佮超文字攏含入去，全然毋著。

```bash
PYTHONPATH=. .tox/rebuild/bin/python -m scripts.ocr.cli cues \
  "kithann/out/mkv/<srt_name>.mkv" -o "kithann/out/mxf/<slug>.B.work" \
  --presets scripts/news/presets.json --preset titv-news --sheets --progress
```

**兩集ê鏈袂使做伙走。** `safe_resplit`、`regen_strips`、`fix_rtf`、
`ingest` 是**逐集**ê，`make_all`、`publish`、`rebuild --verify` 是
**規批**ê。兩條鏈平行走，尾彼三步就相踏：2026-08-30 按呢走ê時
`publish` 講「published 59 of 60」、`rebuild --verify` 報 smkul.csv
無仝。資料無損著，毋過愛閣走一擺尾段。

**做法：逐集ê頭四步會使平行，規批ê尾三步等攏做完才走一擺。**

**`ingest` 佮 `rebuild` 這馬干焦提 `b*.tsv`。** 進前兩爿攏 glob
`*.tsv`，store 內底彼一个 `sample.tsv`（20210209_040，逐 72 條抽 4
條ê抽查檔）sort 起來排佇後壁，會kā彼幾條蓋過去。舊編號ê時蓋著ê
內容拄好仝款，所以 `rebuild --verify` 四個月攏是青ê；**重新編號才予
伊現形**（彼集ê SRT 差 1,070 逝，ingest 嘛規批擋落來）。兩爿ê glob
攏收斂做 `b*.tsv` 矣，各有測試。

上危險ê是 `4-vision-rtf`：伊照舊編號索引，閣贏過 3-vision，所以編號
一改伊會kā舊字蓋去毋著ê所在。**干焦 `rebuild --verify` 掠會著**——
TSV、work transcripts、store cues.json 三爿攏一致，其他檢查全綠，
差 1760 逝。
