# tests/news/：片頭辨識、段落表、帶外補切、字幕帶版型

這份放 `add-news-segments` 那組測試的 spec × scenario × 測試檔對照表；`tests/news/` 其他測試的對照在 `tests/README.md` 的〈編排〉〈一集配一支檔〉兩節。scenario 寫的是**真的出過錯、量到的情形**，看到就知道那條測試不能拿掉。

## 畫面分類與段落表（`scripts/news/shots.py`、`segments.py`）

| spec | scenario（會出錯的具體情形） | 測試檔 |
|---|---|---|
| news-segments | 2021 年左下角是會換城市、溫度的天氣框；拿樣板比內容會把 26 分鐘判成「其他」——第一層只問框在不在（樣板用該集自己的中位數框） | `test_shot_features.py` |
| news-segments | 紅條從 y 852 起是暗紅（R 30–100、G=B=0），用 R>150 在 4 支 2024 影片只找到 3–9 格且位置錯——要用純紅，而且判準跟 presets 的 `exclude` 是同一組數字 | `test_shot_features.py` |
| news-segments | 2024-08 起紅條落到 y 938–1010、語別牌與節目框換位置；照舊位置量，量到的是字幕，一段主播段都找不到——位置由 preset 的 `shots` 給 | `test_shot_features.py`、`ocr/test_presets.py` |
| news-segments | 縮圖第 t 格是 t+0.5 秒的畫面（25 fps 合成影片實測 t+0.48）；用 `-ss t` 截原圖會差半秒、截到隔壁鏡頭 | `test_shot_features.py` |
| news-segments | 棚內右側虛擬螢幕換內容；2021 年的螢幕佔第二層範圍一半以上，區塊差的中位數跟著螢幕走（棚內 0.07–0.15 和戶外主播 0.19 黏在一起）——取第 25 百分位 | `test_shot_features.py` |
| news-segments | 裁到 x ≥ 480 後，左邊的變化（天氣框、台標）不可以影響第二層的距離 | `test_shot_features.py` |
| news-segments | 176 嘉明湖專題同一位受訪者的鏡位出現十幾次，「反覆出現＝主播」會誤判——主播段看紅條 | `test_segments.py` |
| news-segments | 主播段中間 2 秒沒紅條不可以切成兩段；183 42:01–42:04 主播段後 2 秒接受訪者人名條，橋過去就把受訪者吞進主播段——修到鏡頭邊界 | `test_segments.py` |
| news-segments | 183 結尾主播段紅條只有 14 秒，20 秒門檻判成外景新聞——12–25 秒標判不準、列出要截的秒數 | `test_segments.py` |
| news-segments | 紅條長但不像棚內的：戶外主播、2021「VS」雙人名條受訪者（約 50 秒，2021noon 抽查 4/50 格判錯）、棚內螢幕換成文化小辭典——一律交讀者，不自動判主播外景 | `test_segments.py` |
| news-segments | 176 全螢幕灰底圖卡平坦的區塊跟佈景的四分之一一樣（0.042–0.049），沒有紅條也被判成棚內——沒有紅條只像棚內的要問 | `test_segments.py` |
| news-segments | 7/14 拉阿魯哇那集的島語時間教泰雅語；單元語別只看目錄會記錯——單元段一律問讀者語別 | `test_segments.py` |
| news-segments | `202409015S0800` 第 2300 秒後語別牌換成排灣——記他族插播與語別 | `test_segments.py` |
| news-segments | 段落有 5 秒縫或重疊、類型寫「棚內」、單元語別空白、依據還是「待確認」、沒到影片長度——逐項擋下指名檔與列，不自動補 | `test_segments.py` |

## 片頭辨識（`scripts/news/opening.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| news-segments | `24NL003_160_Paiwan` 片頭是賽德克主播 Awe Nawi——語別不符要非零結束、列出目錄與畫面語別（2026-09-23 核對的 24 列裡 6 列都是這樣抓到的） | `test_opening.py` |
| news-segments | 三格都在片頭動畫、讀不到語別牌——記判不準，不可當相符 | `test_opening.py` |
| news-segments | 賽夏 'okay a 'ataw hayawan 不在 `主播.csv`——提示補表、這集不擋 | `test_opening.py` |
| news-segments | 片頭組合圖從 y 700 起裁，2021 棚內主播名條（y≈660–720）只剩下緣一截——邵語晨間 2021-06、08、09 十集主播讀不出來；裁切起點要包住名條，但也不能提到把主播半身、棚景都裁進去 | `test_opening.py` |
| news-segments | 2021 mp4 的索引在檔尾，只抓前段解不開；稀疏檔要頭 60 MB＋尾 16 MB、大小等於伺服器、位元組數不符要擋；密碼只從 `~/.netrc`，網址與指令列沒有 | `test_opening.py` |
| news-segments | 同一集重跑 ingest 要覆寫那一列、照成果檔名排；目錄查不到的成果檔名要擋 | `test_opening.py` |

## 語別改正（`scripts/news/relabel.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| episode-catalogue | `20210116_016_晚間_Paiwan_排灣` 片頭三格都是卑南（原檔名 `卑南語-20210116s1800.mp4`）：目錄改了、成果檔名換了，store 的時間軸／逐字稿／SRT 沒跟著改名就成孤兒檔 | `test_relabel.py` |
| episode-catalogue | 用排灣語辨識卑南語的 whisper SRT、平行語料、kaldi 各階段不可以改名留著冒充正確的——刪掉、辨識紀錄那列也刪，等重跑 | `test_relabel.py` |
| episode-catalogue | 改名目標已經存在時一個都不搬（不搬一半） | `test_relabel.py` |

## 已讀字集數的帶外補切（`scripts/news/offband_backfill.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 讀完字才重切，後面每條都重新編號；照號碼對會把文字放到別條字幕——舊 cue 只認 (start, end) 完全相同的，時間差 0.2 秒就不算同一條 | `test_offband_backfill.py` |
| cue-timing | TSV 改寫時被換掉的幾條拿掉、文字原樣（空白、tab 不動）；TSV 有舊時間軸沒有的號碼要擋 | `test_offband_backfill.py` |
| cue-timing | 讀者 TSV 要剛好是新 cue 那幾號，少一條、多一條都擋 | `test_offband_backfill.py` |
| news-segments | 段落表那段人工覆寫成「帶外專題」，前後的段照切，待確認的段仍擋入庫 | `test_offband_backfill.py` |
| news-segments | 已確認入庫的段落表（`20241209_344_晚間_Amis_阿美`）補切時被 2021 判準重算的表蓋掉，讀者確認過的列被換成一堆「他族插播／待確認」——起點要依序取：前一段補切的表 → Kari-SRT 已入庫的表 → 都沒有才重算 | `test_offband_backfill.py` |

## 帶外補切（`scripts/news/segment_recut.py`、`splice.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 島語時間對白置中（x≈620–1300），字幕帶的置右比對遮罩（1250–1790）切不出來——照段落表用島語時間的 preset 重切 | `test_segment_recut.py` |
| cue-timing | 補切放在讀字之後會重新編號、TSV 對到別條 cue——已讀字的集數拒跑、指名改用 `rescan_band` | `test_segment_recut.py` |
| cue-timing | 時間軸要記哪條 cue 是哪個區域切的（`areas`、`area`），沒有帶外段落的集數時間軸逐 byte 不變 | `test_segment_recut.py` |
| cue-timing | 補切的那段沒精修就接回，store 會收到粗切的邊界——拒絕、時間軸不動 | `test_segment_recut.py` |
| cue-timing | `rescan_band` 重切後讀 `<out>/cues.json`，分階段後那個檔永遠不存在（在 `1-cues/`），2021 帶外專題重切會倒 | `test_segment_recut.py` |
| cue-timing | 帶外段落重切出零條：原本照字幕帶切的（單字卡、花字）也要拿掉 | `test_segment_recut.py` |

## 入庫、目錄與流程（`publish.py`、`rebuild.py`、`plan_month.py`、`fetch_sftp.sh`、`name_catalogue.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| srt-data-store | 段落表確認完才跟時間軸入庫到 `0-segments/<年-月>/`；內容相同不重寫；還有待確認段落的不入庫、時間軸照入 | `test_publish_gate.py` |
| srt-data-store | `0-segments/` 有目錄查不到的孤兒檔、或驗不過的段落表，`rebuild --verify` 要抓到；2021 年大部分集數沒有段落表不算缺件 | `test_publish_gate.py` |
| srt-data-store | 帶外補切直接改 Kari-SRT，work dir 還是補切前的；publish 不可拿 work dir 蓋回去（1209 晚間 729 條被 575 條蓋掉、「帶外專題」段落不見，publish 沒報錯，rebuild 才抓到）——Kari-SRT 時間軸有 work dir 沒有的區域就跳過並講原因；段落表也一樣（同一集第二次踩到：名條腳本直接呼叫 `publish_segments`，繞過 `publishable()` 的把關） | `test_publish_gate.py` |
| news-segments | 新聞包裡還有節目框的電話訪問卡、公文、統計圖，讀者分成「外景新聞」「其他」兩派；另立「全螢幕圖卡」（有旁白字幕，不算無字幕的「其他」） | `test_segments.py` |
| news-segments | 一集 work dir 約 345 MB、一個月約 24 GB，剩下的月份全切完放不下（2026-09-24 只剩 42 GB）；逐月切之前看磁碟，不夠就等；整月已切完的不下載；倒一個月不擋後面、記進 `cut-progress.tsv`；fetch 回 0 但還有集數沒切不可記成「切完」 | `test_cut_months.py` |
| news-segments | 單元語別看語別牌，受訪者可能是別族（邵語那集名條標 Cou、排灣那集標 Atayal）；「受訪者語言別代號」空＝還沒查、「無」＝查過沒名條，舊表沒這欄照樣讀；不認得的代號要指名 | `test_segments.py` |
| news-segments | 名條飛入約 1 秒，要等字到位才截；主播段標題條偏粉（0.24–0.43）不是名條；同一人講幾次名條就出現幾次（1228 晨間 47 次只有 24 人），同款的只讀一次；沒黃字的紅條不可跟別張併在一起；漢人、外國受訪者沒族名不加代號但那段仍是「查過」 | `test_namebars.py` |
| news-segments | 2021-11～2024-07 舊版型名條是白字：上排小字職稱（y 860–900）、下排人名＋族別（y 930–1000）；大字新聞標題只佔下排、職稱排是空的；亮背景沒有紅條——三個一起判（20211101_305 晚間量：名條職稱 2100–2800、人名 1–1.3 萬；標題 0／3.5 萬） | `test_namebars.py` |
| news-segments | 名條要在影片刪掉前截（2024-12 事後補，69 集都得重抓母帶）；新版型要用 `shots extract` 算的特徵，所以排在它後面 | `test_fetch_sftp_config.py` |
| episode-catalogue | 排除清單上的重複檔被加回目錄，`name_catalogue --check` 要擋；沒有排除清單（開會了）不算錯 | `test_name_catalogue.py` |
| cue-timing | 2024 年照預設 `titv-news`（844）切，羅馬字下伸筆畫被切 1–5 px；2024-08 起字幕置中、在 y 860–925——沒給 `--preset` 就照月份（`plan_month --preset`） | `test_fetch_sftp_config.py`、`test_plan_month.py` |
| cue-timing | 2021 年紅條上緣 846，用 848 的版型會把紅條切進字幕帶——帶位把關要擋 | `test_verify_band.py` |
| news-segments | 2021 年已入庫的集數補片頭：`--opening-only` 不可以呼叫切 cue；只列切過、還沒片頭辨識的集數 | `test_fetch_sftp_config.py`、`test_plan_month.py` |
| —（既有缺口） | `/home/mkv-raw` 的 `.mkv` 被列檔程式當成「伺服器頂懸無」，整批新母帶抓不到 | `test_fetch_sftp_config.py` |
| news-segments | 片頭辨識與段落確認的讀者說明：語別牌寫中文族名、判不準怎麼寫、欄位是 ingest／apply 讀的那幾欄、島語時間要看右上角標誌的族名、紅條族語不是段落語言；主讀者說明要講帶外段落與紅條族語不收 | `test_vision_prompt.py` |

## 影像側引擎（`tests/ocr/`）

| spec | scenario | 測試檔 |
|---|---|---|
| subtitle-text-source | 2022 文化小辭典 y 770–837 跨偏上／偏下分界 787，判成偏下切掉字頂 8–17 px——越過分界超過 pad 就留整條高 | `ocr/test_sheets.py` |
| subtitle-text-source | 紅條上白字的墨水被算成字幕、偏上的對白判不出來——純紅背景的列不算墨水，圖條畫素不變；紅條上白字很寬時一列紅色不到一半，要只看遮罩以外的背景 | `ocr/test_sheets.py` |
| subtitle-text-source | 2024「資料畫面」標籤在左側偏上位 y 740–792，跟偏下對白同時出現——判斷只看置右比對遮罩，照裁偏下 | `ocr/test_sheets.py` |
| subtitle-text-source | 帶外段落（`area`）的 cue 用置右錨定會把右邊雜訊留進圖條、照字幕帶的分界裁——不錨右、不裁上下 | `ocr/test_sheets.py` |
| cue-timing | 各月份恰好一個字幕帶 preset；848 版型不帶 `match`（兩個 preset 搶同一種檔名）；帶外 preset 的區域涵蓋實測範圍、置中的不錨右 | `ocr/test_presets.py` |
