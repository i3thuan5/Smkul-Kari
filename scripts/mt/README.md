# scripts/mt/：族語新聞 → 機器翻譯訓練語料（計算引擎）

材料是同一集影片的兩份東西：
`Kari-SRT/news/2-asr-whisper/`（sapolita 族語辨識，VAD 切的段落，每段
附一句服務自己的華語譯文）與 `Kari-SRT/news/1-ocr/`（華語燒印字幕）。
目標是把兩邊配成**段落級**的族語↔華語平行語料，並給每一組一個信心分數。
《開會了》畫面同時有族語與華語兩列，拿來當標準答案。

這裡只做計算：輸入是 dict 與字串，輸出是 dict 與字串，不碰路徑。用到組裝鏈
`srtlib.assemble`、SRT 讀寫 `srtlib.srt`、辭典 `lexicon`。範圍、路徑、SFTP、
入庫、重建都在 `scripts/news/`（`pairs_run.py`、`pairs_tune.py`、`rebuild.py`）。

| 檔 | 做什麼 |
|---|---|
| `load.py` | 讀兩側：sapolita SRT → 段落（真實 VAD 邊界）；store 的 `1-cues`＋`2-vision` 走同一條組裝鏈 → 字幕條目（帶**真實**窗，不是 SRT 的留白窗），保留併掉的 cue 編號 |
| `overlap.py` | 時間重疊分組：每條字幕歸給重疊最多的段，字幕真的跨兩段（兩邊都佔合併門檻以上）才合併；一組頭尾之間沒人挑的短語音段補進組（補洞）；沒對到的段落與字幕分開回報。兩種時間：`span` 是真實語音範圍（配對、校正基準、特徵用），`padded_spans` 是延伸 0.5 秒後的（只給 CSV；鄰居是整集全部語音段，太近取中點） |
| `textsim.py` | 華語側字元 n-gram F1、chrF（偏召回）；族語側切詞（撇號、長音記號統一）、編輯距離詞相似度、詞層 F1 |
| `hallucination.py` | 只靠文字的幻覺旗標：重複 n-gram、譯文數字串、辭典命中率過低（別族語言或雜訊） |
| `goldalign.py` | 《開會了》的真值：ASR 段落的詞對附近字幕的族語列做局部對齊（Smith-Waterman），得到「這段真的蓋到哪幾條 cue」與詞命中率——不靠時間軸 |
| `evaluate.py` | 一組對真值的精確率／召回（按 cue 詞數加權）、整批統計、AUC、門檻掃描 |
| `features.py` | 一組的信心特徵，全部在沒有標準答案的新聞上算得出來：chrF、bigram F1、辭典命中率、幻覺旗標、雙向時間覆蓋率、長度比 |
| `pairs.py` | 一集的組 → CSV 字串；時間由呼叫端傳入（延伸後的），自己不算 |
| `paragraph_srt.py` | 一集的 CSV 列 → `3-srt-paragraph` SRT 字串：挑高中信心、時間照抄 CSV |

各種對齊法的比較（為什麼不用「有重疊就併」、不用譯文重派）與門檻怎麼定，見 `openspec/changes/archive/2026-09-24-add-whisper-parallel-corpus/design.md`；門檻的調參結果在 `Kari-SRT/news/2-asr-whisper/2-csv-analysis/README.md`。組的時間只看語音段（字幕換句跟族語分段對不齊，算進字幕會讓相鄰組重疊），而且先配對、後延伸：先延伸的話，不到 1 秒的空隙被填滿，原本只碰到一邊的字幕兩邊都壓到而合併，組變長、留下的族語詞反而變少。
