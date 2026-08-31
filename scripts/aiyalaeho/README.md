# aiyalaeho/：《開會了》編排

原視《'a'iyalaeho: 開會了》的燒印字幕抽成 SRT。這個節目的畫面**同時燒著
族語與華語兩列**，所以交付 SRT 是兩行一條、兩行都來自畫面；沒有語音側
（族語文本畫面就有，不必再辨識一次）。

引擎共用（一行都沒改）：`scripts/ocr/` 切 cue 與出 contact sheet、
`scripts/srtlib/` 組裝鏈與 0.5 秒留白。這裡只放這批語料的編排。

資料正本在 `Kari-SRT/aiyalaeho/`（結構見該目錄的 README）；工作區在
`kithann/out/aiyalaeho/`，全部可重生。

## 檔案

| 檔 | 做什麼 |
|---|---|
| `paths.py` | 語料路徑的單一出處（`stage_path()` 是階段目錄唯一出口，逐集檔案不分層；`check_srt_name` 認 `開會了_<集數3碼>_…`；`--var` 供 shell 取值） |
| `catalogue.py` | 檔名就是這一集：解析集數／族語別／語言別／語言代號，登記成 pending 條目。**不讀** `ilrdf-corpus.csv` |
| `verify_band.py` | 切 cue 前逐集驗版型：量帶的顏色與字幕列的位置 |
| `ingest.py` | 視覺辨識 TSV 的驗證匯入（cue↔sheet 歸屬、空白列補尾端 tab、只吃 `b*.tsv`） |
| `make_srt.py` | 單集組裝：每條兩行「族語：／華語：」，走共用組裝鏈 |
| `make_all.py` | 整批組裝＋進度表工作版 |
| `tracker.py` | `smkul.csv` 的九欄與單列組法，三方共用 |
| `publish.py` | 整批把關→遷時間軸→清 pending→定版 `smkul.csv` |
| `rebuild.py` | 只用 store 離線重建全部交付 SRT，逐 byte 驗證 |
| `presets.json` | 版型：`aiyalaeho-bilingual`（黃底雙列帶） |

news 有而這裡**沒有**的四支，各有理由：`fetch_sftp.sh`（素材已在本機，
少數幾支手動 `scripts/news/sftp.sh get` 就好）、`plan_month.py`（沒有月份
批次，登記併進 `catalogue.py`）、`gap_sheets.py`（沒有 `.work`／`.B.work`
之分，`cues --sheets` 首輪就是完整的）、`batches.py`（`ocr.cli pending`
已列未讀的 sheet）。

## 跑法

```bash
# 1. 登記（檔名驅動；-n 先看要做什麼）
python3 -m scripts.aiyalaeho.catalogue -n
python3 -m scripts.aiyalaeho.catalogue

# 2. 逐集：驗版型 → 切 cue（出 contact sheet）→ 邊界精修
PY=$(python3 -m scripts.aiyalaeho.paths --var VENV_PY)
V='kithann/開會了/068-阿美語-秀姑巒-雙語字幕.mp4'
W="$(python3 -m scripts.aiyalaeho.paths --var WORK)/開會了_068_Amis_阿美.work"
$PY -m scripts.aiyalaeho.verify_band "$V" --quiet && \
$PY -m scripts.ocr.cli cues "$V" -o "$W" \
    --presets scripts/aiyalaeho/presets.json \
    --preset aiyalaeho-bilingual --sheets < /dev/null && \
$PY -m scripts.news.refine_cues "$V" "$W/cues.json"

# 3. 視覺辨識：subagent 一批讀 24 張 sheet，TSV 直接寫進
#    Kari-SRT/aiyalaeho/1-ocr/2-vision/<srt_name>/bNN.tsv
python3 -m scripts.ocr.cli pending "$W"        # 猶未讀ê sheet
python3 -m scripts.aiyalaeho.ingest 開會了_068_Amis_阿美

# 4. 組裝、定版、驗收
python3 -m scripts.aiyalaeho.make_all
python3 -m scripts.aiyalaeho.publish
python3 -m scripts.aiyalaeho.rebuild --verify
```

`cues` 那步的 `< /dev/null` 不可省：迴圈裡的 ffmpeg 會把 stdin 吸乾，
切 cue 就停在半路而且**不會報錯**（新聞那邊踩過，cues 少四倍）。

## TSV 格式（視覺辨識的交卷）

每個 cue 兩逝，行尾允許留空（那是「這列沒有字幕」，不是漏讀）：

```
12	formosan	Nga'ay ho^
12	han	大家好
13	formosan
13	han	這也就是今天的原因
```

族語列**照畫面抄**：夾漢字就寫漢字（`qau aicu a 民族議會 mana…`），
`^ ' " : ʉ` 這些符號原樣保留，`'`（一撇）與 `"`（兩撇）是不同的符號、
不可互換。

## 版型與判準（量過的）

38 集有字幕的版型一致：畫面底部黃紅漸層不透明帶，族語列在上、華語列
在下。preset 的槽是族語 y 888–948、華語 y 948–1014（華語槽開到區底，
是因為 094／111／117 三集的字腳落在 1008–1011）。

`verify_band.py` 量兩件事，門檻都是量出來的：

- **帶**：逐列「帶色」（飽和、R≥G≥B）像素的比例，區內下沿比區外上方。
  有帶 8–22 倍（068／083／164），無帶 0.8–0.9 倍（88 無字幕、以及故意
  拿新聞版型來試的）。門檻 2.5。
- **字幕列**：文字遮罩的逐列 ink，**只看帶罩到的列**。083 的帶比較短，
  帶上方的亮攝影棚畫面曾被誤判成 48 列的「字幕列」——畫面不是字幕。
  ink 門檻是絕對值 50（實測字幕列 83–453、無字幕集的雜訊 8–37）；用
  相對門檻會把安靜的華語列洗掉（164 就是）。

三種判定：`OK`（有帶、每列各在自己的槽內）、`NO-BAND`（沒有帶也沒有
有結構的墨水——88／90／98 這種本來就沒字幕的集，照切、交付 0 行 SRT）、
`MISMATCH`（有帶但列跑出槽外，或沒帶卻有對比 ≥2 倍的墨水——新聞版型
量到 4.04，就是這條擋下來的）。
