# scripts/modeleval/：用《開會了》OCR 字幕評測原語會的 AI 模型

把《開會了》燒印字幕（族語列、華語列）**當標準答案**，量三樣東西：

| 項目 | 服務 | 指標 |
|---|---|---|
| 族語語音辨識 | sapolita（whisper）`https://ai-labs.ilrdf.org.tw/sapolita/` | WER、CER |
| 族語→華語翻譯 | kari-seejiq-tnpusu-ai-hmjil `translate` | BLEU、chrF++ |
| 華語→族語翻譯 | kari-seejiq-tnpusu-ai-hmjil `translate_1` | BLEU、chrF++ |

目前只做阿美語 8 集（`pairs.load(family=...)` 換族就能做別族）。

## 流程

```
Kari-SRT/aiyalaeho/1-ocr/4-語言檢查/逐條語言標記.csv   （標準答案＋每條的語言標記）
        │
        ├─ asr_run.py ─▶ kithann/out/modeleval-阿美/asr/<成果檔名>.srt     sapolita 原樣回傳
        ├─ mt_run.py  ─▶ kithann/out/modeleval-阿美/mt-cache/ailabs.jsonl  兩個方向的翻譯快取
        ▼
     score.py ─▶ kithann/out/modeleval-阿美/report/摘要.csv、ASR逐集.csv、CER逐集.csv、MT逐集.csv、MT逐句.csv
```

```bash
python3 -m scripts.modeleval.asr_run     # 一集一集送，做過的跳過
python3 -m scripts.modeleval.mt_run      # 一句一句送，快取有的跳過
python3 -m scripts.modeleval.score       # 離線算分
```

兩支跑批都是一次一個請求（公開服務，不平行），斷掉重跑會從斷點接。

## 各檔

| 檔 | 做什麼 |
|---|---|
| `pairs.py` | 讀標準答案；sapolita 語別碼（smkul 只寫 `ami` 的照新聞線保底送海岸）；sapolita 碼 ↔ 翻譯服務碼對照（南勢 `ami-x-iams` ↔ `ami_Sout`，對兩邊下拉選單的中文標籤讀的） |
| `mtboth.py` | 翻譯服務兩個方向的用戶端。`scripts/asrmt/mtclient.py` 刻意只做族→華（交付流程用不到反方向），評測另外一支；快取共用 `MTCache` |
| `asr_run.py` | 影片 `kithann/mp4/<成果檔名>.preview.mp4` 抽 16 kHz mp3 → sapolita |
| `mt_run.py` | 逐集：族→華做完接華→族 |
| `metrics.py` | WER、CER、BLEU、chrF++ 與正規化；照 sacrebleu 的定義重寫（採購規定：不另裝套件） |
| `score.py` | 組資料、算分、bootstrap 95% 信賴區間、寫報表 |

## 計分的幾個決定

- **ASR 範圍兩種**：「全集」整集接起來比；「族語字幕時段」只留過半落在族語字幕底下的 sapolita 段——受訪者講華語時沒有族語字幕，sapolita 還是會硬聽成阿美語，算進去插入錯誤會灌爆 WER。
- **族語正規化**：小寫、撇號（`ʼ` U+02BC、`’` U+2019 …）統一成 `'`、sapolita 的 `⌃`（U+2303）統一成 `^`、夾在族語列的漢字與標點換成空白。sapolita 與翻譯服務都輸出 `ʼ`，OCR 字幕是 ASCII `'`。主要數字拿掉 `^` `:`：兩邊標得很不一致（8 集字幕 `^` 588、`:` 193 個，sapolita 只有 `⌃` 63、`:` 15 個），`scripts/mt/textsim.py` 的既有做法也是拿掉；保留、全刪撇號兩種也一起報。
- **o／u 合併只當敏感度分析**：阿美語 o、u 不分音位，南勢寫 u、其他語言別寫 o。sapolita 在海岸／秀姑巒的集也約 40% 寫成 u（字幕幾乎全寫 o），替換錯誤前四名是 no→nu、ko→ku、to→tu、o→u。主要數字照字幕的寫法比，合併後的另外報，看寫法問題佔多少。
- **信賴區間**：ASR 以塊、MT 以句重抽樣，反映的是「這 8 集」內部的不確定性，不含集與集之間的差異（ASR 各集 WER 從 4 成到 9 成都有，見 ASR逐集.csv）。
- **語別碼保底**：smkul 只寫到 `ami` 的 5 集照新聞線保底送海岸。082 的字幕 o／u 各半、還有 b，像是混了南勢的講者，用海岸送可能不合；不改代號（非保底語言別要有網頁證據），只在報告裡交代。
- **串接（sapolita 自己接的華語列）**：跟 MT 族→華在同樣的 ASR 塊上比（塊內 OCR 華語列當答案），不用整集一篇——整篇算 n-gram 不看順序，拿下一集的辨識結果去比都有 BLEU 12.23，跟逐句 MT 13.00 差不多。
- **華語正規化**：去掉空白與標點再以字為單位比。字幕用空白斷句、翻譯輸出用全形標點，跟意思無關。
- **MT 以字幕條為單位**：一條字幕常常是半句話（「所有收看節目的」），這是字幕本身的切法，分數會比整句翻譯低。
- **chrF++ 對華語**：sacrebleu 的詞 n-gram 用空白切，華語沒有空白時詞 n-gram 退化成整句一個詞，chrF++ 幾乎等於 chrF 打個折；照標準算法報，不另外發明。
