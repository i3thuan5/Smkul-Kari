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
| episode-catalogue／srt-data-store | 用排灣語辨識卑南語的 whisper SRT、平行語料（`2-csv-analysis`）、雙語字幕（`3-srt-paragraph`）、kaldi 各階段不可以改名留著冒充正確的——刪掉、辨識紀錄那列也刪，等重跑 | `test_relabel.py` |
| episode-catalogue | 改名目標已經存在時一個都不搬（不搬一半） | `test_relabel.py` |
| episode-catalogue | 2024-08 撒奇萊雅 → 阿美、2024-10 太魯閣 → 泰雅改了，目錄寫 `ami`、`tay`，但 mkv-raw 其他 2494 列都照 `新聞語言別代號.csv`（`ami-x-pswl`／海岸），whisper 也用那張表選模型——mkv-raw 來源照表填語言別；2021-01～10 ilrdf-corpus 舊批（289 列只記族語別）照舊 | `test_relabel.py` |

## 播出日期改正（`scripts/news/redate.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| episode-catalogue | `20240930_274_晚間_Amis_阿美` 用的 `20241001S2000.mkv`，OCR 內容（台9線崇德土石流、山陀兒颱風來襲）和檔名都是 10-01：改日期和集數後成果檔名要跟著換成 `20241001_275_…`，族語、語言別代號、來源檔都不能動 | `test_redate.py` |
| srt-data-store | 內容還是同一集、語言沒變，whisper 辨識結果、平行語料、kaldi 各階段**一個都不能刪**（relabel 才刪），逐階段改名；跨月 09 → 10 時月份資料夾也要換，否則 `rebuild --verify` 找到孤兒檔 | `test_redate.py` |
| srt-data-store | 片頭辨識、辨識紀錄兩張表原本照成果檔名排好，改名後仍要排好，否則一次改名重寫出整張表的 diff；辨識紀錄那列的音長秒、段數不可以變 | `test_redate.py` |
| episode-catalogue | 改名目標已存在（store 裡或目錄裡）時一個都不搬、不改；目錄查無這集也不搬；日期格式 `2024/10/01`、`20241001`、`2024-10-1` 要擋；跨年改日期時年度欄跟著變 | `test_redate.py` |

## 已讀字集數的帶外補切（`scripts/news/offband_backfill.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 讀完字才重切，後面每條都重新編號；照號碼對會把文字放到別條字幕——舊 cue 只認 (start, end) 完全相同的，時間差 0.2 秒就不算同一條 | `test_offband_backfill.py` |
| cue-timing | TSV 改寫時被換掉的幾條拿掉、文字原樣（空白、tab 不動）；TSV 有舊時間軸沒有的號碼要擋 | `test_offband_backfill.py` |
| cue-timing | 讀者 TSV 要剛好是新 cue 那幾號，少一條、多一條都擋 | `test_offband_backfill.py` |
| news-segments | 段落表那段人工覆寫成「帶外專題」，前後的段照切，待確認的段仍擋入庫 | `test_offband_backfill.py` |
| news-segments | 已確認入庫的段落表（`20241209_344_晚間_Amis_阿美`）補切時被 2021 判準重算的表蓋掉，讀者確認過的列被換成一堆「他族插播／待確認」——起點要依序取：前一段補切的表 → Kari-SRT 已入庫的表 → 都沒有才重算 | `test_offband_backfill.py` |
| news-segments | work dir 清掉的集（2024 試做五集）島語時間、部落信箱要用這支補切，類型寫死「帶外專題」會把段落表和 areas 標錯；plan 記類型、舊 plan 沒記的當帶外專題、打錯的類型（「島語」）要擋 | `test_offband_backfill.py` |
| news-segments | Kari-SRT 的段落表不存「依據」欄；2023-02 058 晚、059 午補切時從 store 讀進來的列依據全是空字串，apply 被 segments.check 擋下「依據 ''」，段落表沒入庫——從表讀進來時補「人工」 | `test_offband_backfill.py` |

## 帶外補切（`scripts/news/segment_recut.py`、`splice.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 島語時間對白置中（x≈620–1300），字幕帶的置右比對遮罩（1250–1790）切不出來——照段落表用島語時間的 preset 重切 | `test_segment_recut.py` |
| cue-timing | 補切放在讀字之後會重新編號、TSV 對到別條 cue——已讀字的集數拒跑、指名改用 `rescan_band` | `test_segment_recut.py` |
| cue-timing | 切 cue 程序先出組合圖、上尾才補切：補切重新編號後舊組合圖的號碼對到別條 cue（2021-12 十集，340 午間舊 827 條→新 824 條），ingest 不會發現——補切完把舊組合圖刪掉，讓 gap_sheets 照新號碼重做 | `test_segment_recut.py` |
| cue-timing | 時間軸要記哪條 cue 是哪個區域切的（`areas`、`area`），沒有帶外段落的集數時間軸逐 byte 不變 | `test_segment_recut.py` |
| cue-timing | 補切的那段沒精修就接回，store 會收到粗切的邊界——拒絕、時間軸不動 | `test_segment_recut.py` |
| cue-timing | `rescan_band` 重切後讀 `<out>/cues.json`，分階段後那個檔永遠不存在（在 `1-cues/`），2021 帶外專題重切會倒 | `test_segment_recut.py` |
| cue-timing | 帶外段落重切出零條：原本照字幕帶切的（單字卡、花字）也要拿掉 | `test_segment_recut.py` |
| cue-timing | 2021 文化小辭典字幕沉到帶下，沉多低每集不同（305 晚間 y 815–870、328 晚間 779–829）；比對列照 305 定死，328 只看到字的下緣，一條 cue 31.2 秒吞掉兩句——重切前先量字在哪幾列，照量到的列寫這段專用的 preset | `test_segment_recut.py` |
| cue-timing | 量字的列時只算白點，日頭照的樹葉（白點比例 0.04–0.06，字才 0.09–0.12）整條帶都過門檻——要算「白點旁邊有黑框」 | `test_segment_recut.py` |

## 入庫、目錄與流程（`publish.py`、`rebuild.py`、`plan_month.py`、`fetch_sftp.sh`、`name_catalogue.py`）

| spec | scenario | 測試檔 |
|---|---|---|
| srt-data-store | 段落表確認完才跟時間軸入庫到 `0-segments/<年-月>/`；內容相同不重寫；還有待確認段落的不入庫、時間軸照入 | `test_publish_gate.py` |
| srt-data-store | `0-segments/` 有目錄查不到的孤兒檔、或驗不過的段落表，`rebuild --verify` 要抓到；2021 年大部分集數沒有段落表不算缺件 | `test_publish_gate.py` |
| srt-data-store | 帶外補切直接改 Kari-SRT，work dir 還是補切前的；publish 不可拿 work dir 蓋回去（1209 晚間 729 條被 575 條蓋掉、「帶外專題」段落不見，publish 沒報錯，rebuild 才抓到）——Kari-SRT 時間軸有 work dir 沒有的區域就跳過並講原因；段落表也一樣（同一集第二次踩到：名條腳本直接呼叫 `publish_segments`，繞過 `publishable()` 的把關） | `test_publish_gate.py` |
| srt-data-store | 平行語料兩層是仝一次配對產的：`2-csv-analysis` 改一格、`3-srt-paragraph` 改一字，`rebuild --verify` 都要指名集與層；CSV 在、SRT 無，是舊程式產的，要指名；SRT 在、CSV 無要指名；辭典取不到、辨識紀錄缺音長要指名，不可略過宣告通過；舊目錄 `2-平行語料/` 佮新目錄並存要失敗（改名時平行 session 可能用舊程式寫） | `test_rebuild_pairs.py` |
| srt-data-store | `cut_months` 正在精修的集數只有粗切時間軸，`publishable()` 放行、`publish_one` 才 raise，整輪 publish 倒掉，排在後面的集數都入不了（20230703_184 晚間）——在 `publishable()` 就講「時間軸猶未精修」跳過 | `test_publish_gate.py` |
| news-segments | 新聞包裡還有節目框的電話訪問卡、公文、統計圖，讀者分成「外景新聞」「其他」兩派；另立「全螢幕圖卡」（有旁白字幕，不算無字幕的「其他」） | `test_segments.py` |
| news-segments | 一集 work dir 約 345 MB、一個月約 24 GB，剩下的月份全切完放不下（2026-09-24 只剩 42 GB）；逐月切之前看磁碟，不夠就等；整月已切完的不下載；倒一個月不擋後面、記進 `cut-progress.tsv`；fetch 回 0 但還有集數沒切不可記成「切完」 | `test_cut_months.py` |
| news-segments | 單元語別看語別牌，受訪者可能是別族（邵語那集名條標 Cou、排灣那集標 Atayal）；「受訪者語言別代號」空＝還沒查、「無」＝查過沒名條，舊表沒這欄照樣讀；不認得的代號要指名 | `test_segments.py` |
| news-segments | 名條只說受訪者是哪一族，講族語還是華語看不出來：有族別代號的段「受訪者說話語言」標「族語或華語」，之後用華語 ASR 判；只接受空、無、族語或華語、族語、華語 | `test_segments.py`、`test_namebars.py` |
| news-segments | 名條飛入約 1 秒，要等字到位才截；主播段標題條偏粉（0.24–0.43）不是名條；同一人講幾次名條就出現幾次（1228 晨間 47 次只有 24 人），同款的只讀一次；沒黃字的紅條不可跟別張併在一起；漢人、外國受訪者沒族名不加代號但那段仍是「查過」 | `test_namebars.py` |
| news-segments | 2021-11～2024-07 舊版型名條是白字：上排小字職稱（y 860–900）、下排人名＋族別（y 930–1000）；大字新聞標題只佔下排、職稱排是空的；亮背景沒有紅條——三個一起判（20211101_305 晚間量：名條職稱 2100–2800、人名 1–1.3 萬；標題 0／3.5 萬） | `test_namebars.py` |
| news-segments | 名條要在影片刪掉前截（2024-12 事後補，69 集都得重抓母帶）；新版型要用 `shots extract` 算的特徵，所以排在它後面 | `test_fetch_sftp_config.py` |
| episode-catalogue | 排除清單上的重複檔被加回目錄，`name_catalogue --check` 要擋；沒有排除清單（開會了）不算錯 | `test_name_catalogue.py` |
| cue-timing | 2024 年照預設 `titv-news`（844）切，羅馬字下伸筆畫被切 1–5 px；2024-08 起字幕置中、在 y 860–925——沒給 `--preset` 就照月份（`plan_month --preset`） | `test_fetch_sftp_config.py`、`test_plan_month.py` |
| cue-timing | 2021 年紅條上緣 846，用 848 的版型會把紅條切進字幕帶——帶位把關要擋 | `test_verify_band.py` |
| news-segments | 2021 年已入庫的集數補片頭：`--opening-only` 不可以呼叫切 cue；只列切過、還沒片頭辨識的集數 | `test_fetch_sftp_config.py`、`test_plan_month.py` |
| —（既有缺口） | `/home/mkv-raw` 的 `.mkv` 被列檔程式當成「伺服器頂懸無」，整批新母帶抓不到 | `test_fetch_sftp_config.py` |
| news-segments | 片頭辨識與段落確認的讀者說明：語別牌寫中文族名、判不準怎麼寫、欄位是 ingest／apply 讀的那幾欄、島語時間要看右上角標誌的族名、紅條族語不是段落語言；主讀者說明要講帶外段落與紅條族語不收 | `test_vision_prompt.py` |

## 重播移植（`scripts/news/rebroadcast_port.py`）

測試檔 `test_rebroadcast_port.py`（離線、fixture 合成，不讀 Kari-SRT）。量測數字與做法見 `scripts/news/README.md`〈重播移植〉。寫「舊做法」「上一個做法」的列，是 2026-10-27 驗證與審查在真實資料上抓到的毛病。

| spec | scenario（會出錯的具體情形） | 測試 |
|---|---|---|
| cue-timing | 一句字幕跨好幾條 cue、每條寫同一句（全批 12,351 處），不先併成一段就算不出「只出現一次」，錨點少一大半；只併「相連而且同字」的；彎撇直撇要視為同一個 | `test_runs_merge_adjacent_same_text`、`test_norm_treats_curly_and_straight_apostrophe_alike` |
| cue-timing | 位移不是整數格：244 晚→076 晚是 −234.000＝−7012.99 格，硬取整格差 0.4 毫秒，搬過去逐條四捨五入就出錯 | `test_offset_not_rounded_to_frames` |
| cue-timing | 迄點不能當錨點：重播用別的區域切 cue 時迄點差 p90 1.8 秒（227→222），起點只差 0.028 秒 | `test_anchor_uses_start_only` |
| cue-timing | 重播剪掉中間 3 秒，單一位移讓後半段全錯——要找出「前面連續 18 個 +100.00、後面連續 12 個 +97.00」的分界並拒絕，訊息講出首播幾秒 | `test_reject_cut_inside_range` |
| cue-timing | 首播改過起迄的 cue 會形成第二群（182 晨部落信箱 6 條差 −0.57 秒，跟 41 條交錯），不可以誤判成剪接 | `test_interleaved_second_cluster_is_not_a_cut` |
| cue-timing | 錨點各自差 0.07–0.45 秒、沒有一致的格位移（309 午→299 午，p50 超過一格）→ 拒絕，不可以拿中位數硬搬 | `test_reject_inconsistent_anchor_spread` |
| cue-timing | 227 午→216 晚移植前的快照：216 用花字設定切、227 用島語設定，199 個同群錨點 83% 在 1 毫秒內、其餘差 1–3 格，p90 0.050——舊做法「p90 一格」把這個標準案例擋掉（盤點有 35 份同樣被擋）；改看 p50 一格內、八成在兩格內 | `test_phase_spread_from_other_cut_still_ready` |
| cue-timing | `--offset` 舊做法直接把 status 設成 ready，剪接、剪法不同的拒絕也一起蓋掉（驗證者讓 216 過關就是靠它）；只准補位移 | `test_offset_cannot_override_cut_or_different_edit` |
| cue-timing | 328 晚→341／020／033／093：OCR 同群 1–3 個、whisper 有效但跟畫面差幾秒到十幾秒、又剪法不同。舊訊息照樣寫「要先用像素定位」，報告又跟 093→060（逐格不一致）一起統稱「位移證據不足」；被剪接、剪法不同擋下時要講像素定位補不了 | `test_rejected_reasons_name_the_real_blocker` |
| cue-timing | 剪法不同（194 晚→098 晚：33 個錨點只有 10 個同群，三窗中位數 −374.37／−374.91／−373.24）→ 拒絕 | `test_reject_different_edit` |
| cue-timing | whisper 短窗（109 秒、6 段，三個候選各 3 票）是「沒有結論」不是「不一致」，窗要放寬到中點前後各 300 秒 | `test_whisper_short_window_inconclusive` |
| cue-timing | whisper 跟畫面差 53 毫秒（089 晚 2021←332 晚 2023，影音同步不同）：whisper 只當粗定位（容差 0.1 秒），最後的位移用畫面；只有 whisper 時走像素定位 | `test_whisper_coarse_only` |
| cue-timing | 島語時間這種重播集整段沒讀過字、OCR 一個錨點都沒有：whisper 有效時要走像素定位，不可以因為沒有畫面位移可比而當掉 | `test_whisper_only_without_ocr_anchors` |
| cue-timing | whisper 邊界跟族語碼無關：同一段聲音送不同語言碼，字完全不同、段落邊界一樣（244 賽夏→076 排灣 52 個邊界對到）；不可以用 whisper 的字比對 | `test_whisper_boundaries_not_text` |
| cue-timing | 範圍迄點落在重播自己的主播開場：244→076 首播那列搬過去到 1892，會蓋掉 076 cue 702–706「接下來要跟大家分享的是…」，要縮到 1878.626 | `test_range_shrinks_off_target_own_lines` |
| cue-timing | 範圍起點落在重播集主播開場（6 集工作檔 prepare 範圍偏早約 10 秒）：同一條規則對起點 | `test_range_start_shrinks` |
| cue-timing | 邊緣那條同字不同長：「謝謝大家 掰掰」首播搬過來迄 1878.811、重播自己 1878.009（重播在那裡剪掉），要用重播的 | `test_edge_cue_keeps_target_end` |
| cue-timing | 跟保留的空白 cue 重疊 0.133 秒（222 cue 444）→ 修短空白那條；跟有字的 cue 重疊 → 擋 | `test_edge_overlap_blank_trimmed_text_refused` |
| cue-timing | 216 移植前「我傻眼」3.19 秒（舊花字切法拉長），227 是 1.10 秒：覆蓋率用重播那條算不到五成，舊做法判成首播沒有、迄點縮到 2791.405，範圍外留下 216 自己的 cue 跟 areas 衝突；要用兩條中較短的算，邊緣也不可以把首播那條拉長成重播的 | `test_edge_same_text_longer_target_not_shrunk` |
| cue-timing | 152 午→182 晨用段落表那一列：搬進來的空白 cue 909 跟 182 範圍外有字的「休息一下 馬上回來」重疊 0.533 秒，舊做法只會修短保留的空白，整件擋下；搬進來的是空白就修短它 | `test_ported_blank_trimmed_against_target_text` |
| cue-timing | 保留的空白 20.1–20.5、搬進來的 19.0–20.8：舊做法修短成 20.8–20.5、照樣 ready；修短後起點大於迄點要擋，寫出前檢查整條時間軸遞增不重疊 | `test_trim_that_inverts_cue_refused`、`test_check_timeline_refuses_overlap_and_inversion` |
| cue-timing | 範圍起點往內縮碰到 182 自己的「體驗連結課室學習」（152 是「從身體力行的…」，相似度過 0.5、時間差 2.9 秒）：舊做法當成同一句就停；相似但起點錯開的要繼續縮 | `test_range_start_continues_past_similar_sentence` |
| cue-timing | 152→182 --range 600 2439，182 在 946–980 是同一則新聞的邵語版，舊做法縮 54 次停在相似句、判 ready，7 條差到 2.9 秒只報 1 條；範圍裡兩句以上相似但時間錯開（而且那句首播在重播同時段對不到）、錨點又沒有過半在一格內，就擋。相鄰字幕很像（「第012句」「第013句」）不可以誤判 | `test_range_with_other_version_refused`、`test_blank_source_text_still_has_row` |
| cue-timing | 227→216：「這個是日本人造的橋」216 移植前 1762.594、首播加位移 1759.308、216 現在 1759.307，是 216 舊花字切法的錯，卻有 11 句被當成別的版本擋下；錨點過半在一格內時，少數錯開的句子算重播自己的時間軸錯，記說明不擋 | `test_target_own_drift_not_other_version_when_anchors_agree` |
| cue-timing | 216 移植前快照 cue 1074／1075 在範圍內本來就重疊，整段搬換掉更好，不該擋；範圍外原本的重疊（254 cue 709／710）不動、記說明 | `test_whole_replaces_original_overlap_and_notes_the_rest` |
| cue-timing | 254 用 --range 1155 2075：251 魯凱主播的「我們先休息一下…馬上回來」重播那段沒有 cue，舊做法照搬進泰雅 254、只列成「補進的字」；首播有字、重播沒有 cue、又不在工作檔 items 裡的要擋 | `test_source_text_where_target_has_no_cue_refused` |
| news-segments | 251 午泰雅島語時間在段落表是 1155–1266.6、1266.6–1276.9、1276.9–2060 三列（字幕帶不同），`--unit 1300` 只拿到最後一列、漏掉工作檔頭幾項；同類型、同單元語別、相接的列要併，外景新聞一則一列不併 | `test_unit_range_merges_rows_of_one_program` |
| cue-timing | 範圍外改號要照身分不照 (start, end)：邊緣被修短的空白 cue 起迄變了，`offband_backfill.moves()` 的時間鍵對不到，TSV 列被當成「被換掉」刪掉，那條 cue 就沒有 TSV 列 | `test_moves_follow_identity_not_times` |
| cue-timing | 搬進來的 cue `images` 要清空（首播的 `2-strips/t01571003_han.png` 在重播集不存在）；`sample_ts` 要加位移、落在自己的起迄內 | `test_ported_cue_fields` |
| cue-timing | 首播頂層的 `split`／`placed` 記的是首播的號碼，抄過去會指到重播集別條 cue；只加一筆 `ported` | `test_history_not_copied` |
| srt-data-store | 每條 cue 只能在一份 TSV（`ingest` 會整集擋「cue 444 appears in both b02.tsv and b05.tsv」）；搬進來的字寫在新檔，舊檔裡範圍內的列要刪 | `test_tsv_each_cue_once` |
| srt-data-store | 新 TSV 編號用「最大號＋1」不是「檔數＋1」：有 b01、b02、b04 三個檔時，檔數＋1＝b04 會蓋掉既有的檔 | `test_new_tsv_number_after_max` |
| srt-data-store | 首播那條是空字（判不收）也要在新 TSV 寫一列空的，不然那條 cue 沒有列 | `test_blank_source_text_still_has_row` |
| srt-data-store | 文字一個 byte 都不動：讀者寫的尾端空白、`．`（U+FF0E）、族語撇號照抄 | `test_text_bytes_untouched` |
| srt-data-store | 某一份 TSV 的列全在範圍內（島語時間整段一批讀的）：換掉後是空檔，要刪掉，不在 Kari-SRT 留 0 byte 的 bNN.tsv | `test_tsv_whose_rows_all_replaced_is_removed` |
| srt-data-store | 範圍外的 manual-fixes 列 cue 號照對應改（216 晚 walwalo' tinralom 1006→1045 那種）；「137–141」這種範圍兩端都改 | `test_fixes_outside_renumbered` |
| srt-data-store | 首播範圍內的訂正要抄給重播集（不然就是 095 午驗收被抓的「有訂正、沒紀錄」） | `test_fixes_carried_from_source` |
| srt-data-store | 重播範圍內自己的訂正、首播同處字不一樣（075「萬用鏟」修在 075、129 還是「萬用鐮」）→ 擋：整段搬會把重播修好的蓋回去 | `test_target_own_fix_refused` |
| srt-data-store | `pending-fixes.txt` 帶 cue 號的 sed（`/^N\t/`、`s/^N\than\t…`，100 列）範圍外改號、範圍內擋；首播範圍內帶 cue 號的補一列 manual-fixes | `test_pending_fixes_cue_lines` |
| srt-data-store | 多選一寫法 `s/^\(N\|M\)\(\than\t.*\)…`、位址 `/^\(N\|M\)\than\t/`、`\(N\)` 單一個、`\(N\than\t…\)` 包在大括號裡的（pending 裡舊做法認不得的 22 列，大括號寫法 18 列：200 晚、206 晚、251 午、013 晚…）範圍外也要改號：舊做法只認 `^N\t`，整列原封不動，號碼指到別條字幕 | `test_pending_alternation_outside_renumbered` |
| srt-data-store | 012 晚 `s/^\(734\|738\|751\|752\|753\)\than\t.*$/\1\than\t/`（粉紅提問字卡清空）在移植範圍內，舊做法認不得、不擋；整段搬後 734 變成「有一次跨年晚會在尖石」，日後套用會把正確的字清空。範圍內一個號碼就擋，跟範圍外混在一起也擋 | `test_pending_alternation_inside_refused` |
| srt-data-store | `^` 後面接的不是認得的 cue 寫法（`7.4`、`\(734\|7..\)`、`[0-9]\{3\}`）：分不出指哪幾條，報「看不懂」，不可以當成不帶號放過 | `test_pending_unrecognized_cue_sed_refused` |
| srt-data-store | `^\([0-9]*\)`、`^\([0-9]\+\than\t\)` 是照字找、不指號（104 午金句卡、026 午花字）：不擋、不改 | `test_pending_wildcard_cue_left_alone` |
| srt-data-store | 首播範圍內用多選一寫的訂正，每個號碼各補一列 manual-fixes：舊做法 `_sed_rows` 只認 `^N\than\t`，整列漏掉，訂正紀錄少了 | `test_pending_source_alternation_carried` |
| srt-data-store | pending 實際出現過的帶號寫法都認得出號碼：字元類 `106[2-5]`、`109[015]`、`71[34]`，`[[:space:]]` 當 tab 的 4 列（`/^469[[:space:]]/`，舊做法也認不得），換的那邊開頭的 `803\than\t`；照字找的、不帶 `^` 的不算 | `test_numbers_of_every_shape` |
| srt-data-store | 改號照原本的寫法寫回去：`106[2-5]` 換完還同字首就留字元類，不同字首而且是獨立的一個選項就拆成 `\|`，號碼沒變的整段原樣 | `test_renumber_keeps_shape` |
| srt-data-store | `\(22[12]\than\t藉由\)` 的字元類包在大括號中間，換成 229、231 寫不回字元類，也不能拆 `\|`（會連後面的字一起分開）：擋，要人看 | `test_renumber_embedded_class_unrepresentable_refused` |
| news-segments | 222 晚被 2542–2564 切成兩列的帶外專題要併回一列，上下緣 690–1040 換成首播的 940–1060 | `test_segments_replaced_by_source_rows` |
| news-segments | 位移不是整數，新列邊會變成 1597.049 這種；跟重播原本列邊差 ≤ 3 秒就用重播的，避免 1–2 秒碎列 | `test_segments_snap_to_target_edges` |
| news-segments | 寫進臨時 work dir 的表要有「依據」（Kari-SRT 的表沒有這欄），不然 `segments.check` 擋、publish 印「段落表 wait」 | `test_segments_basis_filled` |
| srt-data-store | 一個類型只記一格：重播範圍外還有 cue 用同類型別的 preset（259、290 已有 island 的島語時間）→ 擋 | `test_areas_conflict_refused` |
| srt-data-store | areas 衝突訊息舊做法寫新號（254 舊 cue 710 寫成 737），人對不上；要寫重播現在的號。範圍外只剩空白 cue 用舊設定的不擋、記說明 | `test_areas_conflict_message_uses_target_numbers` |
| srt-data-store | 臨時 work dir 的時間軸要帶 Kari-SRT 全部 `areas`，否則 `areas_only_in_store` 判成過期、整集 skip | `test_temp_workdir_keeps_store_areas` |
| srt-data-store | prepare 之後重播或首播被改過（sha 不同）→ apply 擋、Kari-SRT 不動，重做 prepare | `test_apply_refuses_changed_inputs` |
| srt-data-store | 像素驗收沒判過就 apply → 擋，除非帶了使用者同意過的理由 | `test_apply_refuses_without_frames_check` |
| srt-data-store | 重播原本有 work dir：apply 前要改名 `.stale-MMDD`，否則之後的 publish 會把舊時間軸蓋回來（20241209_344 踩過兩次）；剛整段搬完再 prepare，重播那段已經有字、切法一樣，要走分區搬、「套 0、要人判 0」 | `test_existing_workdir_retired` |
| srt-data-store | 舊做法 apply 依序覆寫 TSV → publish → 重產 SRT → pairs → 訂正紀錄，中間任何一步拋例外，Kari-SRT 已經改號、訂正紀錄還是舊號，重跑又被 sha 擋；要先在暫存做好、任何一步失敗整集回滾（含改名的 work dir、新建的目錄、剛拍的快照，不留 .bak） | `test_apply_failure_rolls_back_everything` |
| srt-data-store | 換檔是先抄成 `<檔>.part.<pid>` 再改名，改名失敗時回滾只放回原檔，`.part` 留在 Kari-SRT 的 1-cues 月份目錄；回滾要一起清掉 | `test_rollback_removes_part_files` |
| srt-data-store | `--no-frames` 的理由舊做法沒記，事後查不到哪幾集免做像素驗收；要寫進時間軸 `ported` 那筆 | `test_no_frames_reason_recorded_in_timeline` |
| srt-data-store | apply 在鎖裡一開頭就讀 manual-fixes、pending，做完暫存、publish、render（好幾秒）才整檔改名換進去：這段時間 post.py 或讀字的 agent 附加的列被蓋掉，靜靜少列。讀、改、寫要一氣呵成，中間不可以有耗時步驟 | `test_apply_keeps_rows_appended_while_publishing` |
| srt-data-store | 入庫到一半失敗，舊做法把 manual-fixes、pending 整檔放回 apply 開頭抄的那份：publish 時、訂正紀錄換進去之後別人附加的兩列一起不見。回滾只拿掉 apply 自己改的 | `test_rollback_keeps_rows_appended_during_apply` |
| srt-data-store | 換檔、pairs、訂正紀錄都做完之後留 .bak 時磁碟滿（`_keep_backup` 丟 OSError）：舊做法 apply 以例外結束、不印結尾那行，批次驅動程式寫「已整集回滾」、項目「整件沒做」，Kari-SRT 其實已經換掉、快照路徑也抓不到。換檔之後的收尾出錯只警告，結尾那行照印 | `test_cleanup_error_after_swap_only_warns` |
| srt-data-store | 收尾刪回滾備份（rmtree）失敗：一樣只警告，不可以讓呼叫端以為沒寫入 | `test_cleanup_rmtree_error_after_swap_only_warns` |
| srt-data-store | 換檔換到一半收到 SIGTERM（Bash 逾時、執行者被停）：舊做法照預設直接死掉，Kari-SRT 半套、不回滾。要整集回滾再結束，做完把原本的信號處理方式放回去 | `test_sigterm_during_swap_rolls_back` |
| cue-timing | 像素：同位移 MAD 0.50–0.72、±1 格 0.84–8.58、+5 秒 7.8–64.0；合成兩支只差位移的小圖序列，同位移要過、差一格要判出局部最小在正確那格 | `test_frames_judge_thresholds` |
| cue-timing | 靜態畫面 ±1 格打平（0.84 對 0.50）不可以每點都要求嚴格局部最小；332 晚→089 晚遮掉台標、天氣框後內部點也只有 3/7 是嚴格局部最小（其餘打平、沒有一點是鄰格更像），舊門檻 2/3 會擋。打平不算數，嚴格局部最小到 MATCH_SHARE（1/3）就過；像素定位最小格跟次小格打平時不採用 | `test_frames_static_ties_tolerated` |
| cue-timing | 332 晚(2023)→089 晚(2021)：2021 的台標（384×216 縮圖 x 20–62、y 16–42）、天氣框（x 20–80、y 170–206）跟 2023 不同，光這兩塊同位移 MAD 就墊高 1.0 左右，位移對的也過不了 1.5；025 午(2024)→026 午(2023) 的人名字卡（y 180–205）只有 2024 那次有，只遮四角時底值 7.06、位移對的也擋。比之前遮掉上面兩角和字幕帶下面整條，字幕帶（縮圖 y 144–168）不可以遮；遮罩照比例放（測試小圖 48×27 一樣遮得到） | `test_frames_mask_station_logo_and_weather_box`、`test_check_ignores_station_logo_and_weather_box` |
| cue-timing | 332→089 遮掉台標、天氣框後底值仍有 1.2（2021 整體偏亮），舊的絕對門檻 1.5 擋掉 48 點；泛白轉場 66.0、範圍頭片頭字卡 77.5 是畫面不同，74 個邊界點裡只有這兩點。改成以局部最小為主：位移對的要過，差一格（74 點裡 51 點鄰格更像）要擋 | `test_frames_cross_year_judged_by_local_minimum` |
| cue-timing | 範圍整段給錯、兩集根本不是同一段畫面：同位移、±1 格都在 60 上下，碰巧有三成是局部最小；改成比鄰格之後不可以因為「相對」就過——底值 60 超過上限要擋 | `test_frames_different_footage_everywhere_refused` |
| cue-timing | 邊界點放在兩集都該相同的畫面（套用區外緣、被換的 cue 外側），同位移 MAD 63.7（076 剪回棚內那種）就是範圍或位移錯了，要判失敗 | `test_frames_edge_point_must_match` |
| cue-timing | 取樣時間要取格中心，貼著換格的邊會抽到前後格（runbook：概略 -ss 在 5 fps 有 ±1 格誤差，判反過 13 條）；字改掉的 cue 要有取樣點；邊界點在被換的 cue 兩側各一點 | `test_probe_times_at_frame_centres` |
| cue-timing | 262 範圍 1067–1972，舊做法 7 個內部點都在 1168–1420（先挑前 7 條改到的就滿了），後段 500 多秒有剪接也抓不到；內部點要平均分布在整個範圍 | `test_probe_points_spread_over_whole_range` |
| cue-timing | 227→216（整段搬）起點內側 MAD 41.15（片頭動畫兩集不同步）、迄點內側 82.93（216 那格已經是自己的主播棚）：舊做法邊界點放在節目範圍內側 1 秒，內部點全過、check 一定不過，批次只能一律 `--no-frames`。整段搬只在第一條／最後一條真的被換的 cue 外側取邊界點，範圍頭尾不取 | `test_whole_edge_points_outside_first_and_last_replaced_cue` |
| cue-timing | 合成兩支只差位移、範圍頭尾 2 秒不同的影片：位移對的要通過；plan 的位移差一格要擋（內部點不是局部最小）；舊做法那個範圍起點內側 1 秒的點會不過 | `test_whole_check_passes_real_shift_and_catches_one_frame` |
| cue-timing | 323→273（分區搬）邊界內側 26.05、66.90：分區搬根本不動範圍邊緣。內部點放在套用區裡、邊界點放在套用區外 1 秒；位移差一格照樣擋 | `test_zone_probes_inside_applied_zones_edges_just_outside` |
| cue-timing | 套用區貼著節目範圍的頭，區外 1 秒已經是片頭動畫：那一點不取，另一邊照取 | `test_zone_edge_point_outside_programme_range_skipped` |
| cue-timing | 332 晚→151 晚（整段搬）唯一的邊界點在範圍起點後 1.89 秒，落在 332 的片頭字卡、151 那格是自己的主播棚（同位移 19.19），check 一定不過；332→089 同一處 77.5、到起點後 3.29 秒才對得上。範圍頭尾 4 秒內不取邊界點 | `test_edge_point_near_programme_range_end_skipped` |
| cue-timing | 分區搬內部點固定 7 點、套用區首尾相接後切 7 格：區多、區短時整區沒有點（190 份工作檔全量乾跑，1188 個套用區只有 651 區有內部點），那些區搬錯看不到。十個區各拆一句：每區至少一個內部點，位移對的過、差一格擋 | `test_zone_every_applied_zone_has_inside_point` |
| srt-data-store | 251 家族：舊做法挑 251 當定本、收齊 0 步，254、262 修的「歐伊歐伊歐....」「橙花的精油」「每日一善」漏掉也沒報；每份工作檔各自移植、不湊定本，本身也是重播的首播先收，沒有工作檔的組合列出來 | `test_family_replays_every_source_without_canon` |
| srt-data-store | A→B→C→D 的鏈只照檔名排、只排一層，C→D 可能排在 B→C 前面，B→C 就看不到 A→B 搬進來的修改；要拓樸排序，互相補的（075↔129）列成循環交給人 | `test_family_topological_order_for_chains` |
| srt-data-store | 一家裡只要有一組互相補的（B↔C），舊做法就把剩下全部丟進「循環」照檔名排：475 步裡 296 步被丟進去，循環外還有 16 處順序顛倒（020→358 排在 307→020 前面）。用強連通分量縮點，循環只列兩端都在環裡的，環外照依賴排、環的下游在環後面 | `test_family_cycle_lists_only_episodes_in_the_loop` |
| srt-data-store | 同一對首播→重播的第二輪 `<重播>--from-<首播>-r3.json` 照檔名排在第一輪前面（`-` 比 `.` 小，216 就是這樣），第一輪後做會把第二輪補的蓋掉；照輪次排，-r10 在 -r3 後面 | `test_family_second_round_after_first_round` |
| srt-data-store | 環內的步驟只列在 cycles，steps 裡看不出來，批次照 steps 跑會把環內的（075↔129，誰先做都蓋掉另一邊）也自動做掉；steps 上標 `cycle: <組號>`，環外不標 | `test_family_cycle_steps_marked` |
| srt-data-store | 展開工作檔名 `--from-r3fix1027r2x`、`--from-userrecut1023`、`--from-b1fix1027r2x` 是那一集自己的修正單元，`--from-<首播>-r3` 是同一個首播的第二輪；舊做法把整串當集名去讀時間軸，對 expand 目錄跑 family 整個當掉 | `test_family_irregular_unit_names_not_read_as_episodes` |
| srt-data-store | 快照標籤不照規則（`xr3fix1027r2x`、`x216-r2-10271411`、`xuserrecut102`、帶 `-r<MMDDHHMM>` 的）時舊做法找不到工作檔，同一個首播的不同單元標準不一致；都要找得到 | `test_unit_files_for_irregular_snapshot_tags` |
| srt-data-store | 同一段節目的工作檔要經由「同一集同一列」連成一家，剪法不同的另一段（194→098）不可以被併進來 | `test_families_connect_through_shared_rows` |
| cue-timing | 重播那段整段空白或只用一般字幕帶讀到一兩句（島語時間、帶外歌詞）才整段搬 | `test_mode_whole_when_target_range_unread` |
| cue-timing | 227→216：216 那段有字 437 條（首播 465 條的 94%），只數字會判成逐處搬、接著被三道把關擋下。227 最早那份快照是 titv-news-flower、現在是 titv-news-island（首播重切過），216 還是 flower：首播的切法比較新，整段搬。兩集 areas 的鍵名都叫「帶外專題」，要比 preset／region | `test_mode_whole_when_cut_setting_differs`、`test_mode_whole_only_when_source_is_the_recut_one` |
| cue-timing | 358 晨→314 晚：314 最早是島語、後來重切成花字，358 一直是島語。只看兩集現在不同就整段搬，會 ready、要人判 0，批次直接把 314 的花字重切換回島語；254→251 會列 106 條要人判的字、只靠 `--accept` 擋。重播自己重切過 → 整件要人判、不搬 | `test_mode_asks_when_target_recut_itself`、`test_target_recut_listed_for_review_not_ported` |
| cue-timing | 兩集都沒重切過、只是本來切法就不同：沒有哪一集比較新，走分區搬 | `test_mode_zone_when_cut_differs_but_neither_recut` |
| cue-timing | 切法不同卻沒有首播快照（判不出哪一集重切過），或首播重切過而重播是第三種設定：不可以猜方向整段搬，要人判 | `test_mode_asks_when_recut_cannot_be_told` |
| cue-timing | 最早那份快照在範圍內沒有 cue 時舊做法退回「現在的設定」：重播最早那份空白、首播從島語重切成花字、重播現在是島語，就判成重播沒重切過、整段搬；首播最早那份空白就判成分區搬。看不出當初的切法 → 要人判 | `test_mode_asks_when_first_snapshot_has_no_cue_in_range` |
| cue-timing | 快照目錄有這集的快照、裡面卻沒有時間軸：舊做法 `first_book` 給 None，跟「沒有快照」一樣當成沒重切過；要人判、寫出是哪一份快照 | `test_mode_asks_when_first_snapshot_lacks_timeline` |
| cue-timing | 182、291、331、306 重播那段本來就有字、切法一樣，整段搬會帶來首播的時間軸錯和錯字（魚撈式、藩草、島嶼時間）、拿掉 331 的「但是遇到風雨」「部落信箱」，要分區搬；287 頂層 region y840、331 是 y722，部落信箱那段兩集都用 mailbox，範圍外的設定不算 | `test_mode_zone_when_target_range_read` |
| cue-timing | 152→182 抽格看兩份時間軸各自有錯（6 處各對 3 處：1645.8「是不能隨便的」182 對、152 晚 0.22 秒）：區只有首播拆句那一條，其他 cue 起迄和字不動；拆出來的前半條留重播的身分和圖條、後半條清空 | `test_zone_split_only_where_source_changed` |
| cue-timing | 首播沒改過的「藩草」不在任何區、重播的「蘊草」留著；區內重播的字跟首播修改前、修改後都不同（331「…共勉之 部落信箱」、182「漁撈式」對「魚撈式」）→ 那一區要人判，旁邊「留言版→留言板」那區照套 | `test_zone_never_lets_source_typo_overwrite_target` |
| cue-timing | 重播那條起點比首播晚 0.3 秒（別的區域切的）：上一個做法要求起迄一格內，331 兩處拆 cue、291 六十幾處都卡在要人判；兩邊在區邊都有空檔就是安全邊，整區換成首播的 | `test_zone_target_cut_differently_takes_source_bounds` |
| cue-timing | 重播把第 5、6 句的分界切在首播第 6 句開頭後 1 秒：區的迄點落在重播有字的 cue 中間，直接切會把那條切成兩半；要擴到兩邊都沒有字跨過去的點，第 6 句一起換 | `test_zone_expands_to_safe_edge` |
| cue-timing | 291「niqan gnklaan…」首播把五條連續空白補成同一句、重播邊差 0.1 秒：上一個做法逐個套，只套到一條，SRT 只剩 1.48 秒（首播 2451.416–2454.302），語音和字幕邊界錯了會污染 ASR 訓練；相連的修改要併成一區整句換 | `test_zone_same_sentence_not_fragmented` |
| cue-timing | 首播把「前一句」迄點和「範圍內」起點一起從 10.4 改到 10.9、前一句中點在範圍外：只套範圍內那一半，中間多出 0.5 秒沒有字幕的空檔；區要擴出範圍到安全邊 | `test_zone_bounds_change_across_range_edge` |
| cue-timing | 首播在空檔補一句：重播同處也空才補；已經補過的算「已經一樣」不重複；331「但是遇到風雨」在區外留著；重播同處有自己的另一句 → 那一區要人判 | `test_zone_insert_already_same_and_target_own_text` |
| cue-timing | 部落信箱詩句淡入，首播把起點晚 1.2 秒：重播那條字一樣（只差尾端空白），起點照改，字留重播的 byte、TSV 列不換 | `test_zone_bounds_change_keeps_target_bytes` |
| cue-timing | 重播一條有字的 cue 從範圍前一路跨到範圍後：區找不到安全邊，硬切會把重播那條切碎 → 要人判 | `test_zone_without_safe_edge_asks` |
| cue-timing | 首播現在自己在某一區裡就有重疊（10–11.2「新字」、11.0–12「新字二」那種）：舊做法搬完才整份檢查，整份 plan 擋下、其他區也不套；只把那一區列要人判 | `test_source_own_overlap_asks_only_that_zone` |
| srt-data-store | 分區搬進來的 cue 是照首播設定（島語 y940）切的，重播同名「島語時間」卻是花字 y690：舊做法保留重播的設定，cue 被標成花字切的。首播的設定另存不衝突的新名字（再衝突加 -2），搬進來的 cue 標它；每條 cue 的 area 都要查得到 | `test_zone_cues_keep_source_setting_under_new_area_name`、`test_zone_with_other_area_setting_survives_apply` |
| srt-data-store | 首播那條 cue 沒有 area（照頂層 region y840 切）、重播頂層 region 是 y722：舊做法搬進來的 cue 也不帶 area，落在重播的 y722 底下，時間軸記的切法對不上（190 份工作檔全量乾跑沒遇到，換一集就會）。另存一格記首播頂層 region、搬進來的 cue 標它，整段搬也一樣；重播自己的 cue 照舊 | `test_zone_cue_without_area_keeps_source_top_region`、`test_whole_cue_without_area_keeps_source_top_region` |
| cue-timing | Kari-SRT 有 168 份時間軸本來就重疊（254 範圍外 cue 709／710），上一個做法一開頭整件擋，盤點 183 份擋掉 87 份；只擋這次新造成的重疊或倒置，原本就有的記說明 | `test_original_overlap_outside_zone_noted_new_overlap_refused` |
| cue-timing | 首播在範圍前面拆過 cue、號碼全部 +1：起迄和字一樣的不算修改 | `test_edits_ignore_renumbering` |
| srt-data-store | 分區搬後的訂正紀錄：重播自己的列照改號；首播的訂正照字對（號碼在快照和現在不一樣）抄給重播；重播自己訂正過的那條被首播改掉 → 擋 | `test_zone_fixes_follow_text` |
| srt-data-store | 工作檔 items 的 seconds 有十幾種寫法（1388 個「a-b」、72 個「a-b,c-d」、31 個「約 a-b」、全形「–」「、」、單一秒數、「見 problems」）；看不懂的不可以當成 0 秒 | `test_item_ranges_parsed` |
| srt-data-store | 305→306 模擬 cue 421 改字：那一區列要人判，工作檔項目 1502.7–1505.0 就在那一區裡，可是離套用的上一區不到 1 秒，舊做法先用 1 秒寬限比套用區，報成做到了。先看真的跟哪一區重疊，碰到要人判區就報要人判 | `test_item_inside_asked_zone_not_reported_done` |
| srt-data-store | 182、331 的工作檔項目其實有對應的首播修改、只是列了要人判，上一個做法報「沒有對應的首播修改」，會讓人以為首播沒修；要分開講，要人判的附原因 | `test_items_report_names_asked_zone` |
| cue-timing | 用 323 午現在的狀態模擬 269 午←323 午（那四條其實是 323 後來才補上的，這裡當成首播從最早就有）：首播 2176–2194 秒四條（嗆辣問答題目、歌詞）沒改過，重播同處 1572.805–1590.589 沒有 cue、1590.589–1591.24 只有空白 cue；那裡不在任何區，分區搬不碰，舊做法完全不報。要列「首播有字、重播沒字」（首播、重播秒數、首播 cue 和字、重播那裡的空白 cue），不搬；區裡的（首播在空檔補一句、重播同處也空，照套）不重報，範圍外的不報 | `test_zone_reports_source_text_where_target_blank` |
| srt-data-store | 工作檔項目落在「首播有字、重播沒字」那裡：舊做法報「不在首播改過的地方」，讀的人以為首播沒這句、不必管；要講明首播有字、重播沒字，附首播 cue 和字 | `test_items_in_blank_spot_named_not_unchanged` |
| srt-data-store | 分區搬走完 prepare、apply：首播拆了一句（不在首播工作檔 items 裡——305→306 有 5 處因此被丟掉）、改了一個字，重播只多一條、改一個字；首播那列訂正抄給重播；apply 前替重播拍快照、時間軸記 mode zone 和快照名 | `test_zone_mode_prepare_and_apply` |
| srt-data-store | 重播那段有字、卻沒給首播快照：不知道首播改過哪裡，不可以退回整段搬，要擋並講原因 | `test_zone_without_snapshot_refused` |
| srt-data-store | 重播漏收首播第 20 句（首播沒改過那句，不在任何區）：plan、report.txt 都要列「首播有字、重播沒字」、summary 記句數；不搬，status 照樣 ready，其他區照套 | `test_zone_report_lists_source_text_target_lacks` |
| srt-data-store | 重播已經有 `x20240315_075` 這份快照（上一輪拍的）：沿用就會把這次移植前的狀態當成上一輪的；加 `-r<MMDDHHMM>` 新標籤，那個也有就擋 | `test_snapshot_tag_never_reuses_old_one` |
| srt-data-store | A→B→C：上一個做法 apply 不拍快照，B→C 看不到 A→B 搬進 B 的修改；apply 替 B 拍的快照就是 B 修改前的狀態，B→C 要把兩處都搬到 C | `test_chain_carries_ported_changes_downstream` |
| srt-data-store | 分區搬入庫到一半失敗（pairs 失敗；或訂正紀錄已經重寫、fixlog 才失敗）：整集回滾，含剛拍的快照、manual-fixes；舊測試只測過整段搬的 pairs 失敗 | `test_zone_apply_failure_rolls_back_snapshot_and_fixes` |

## 影像側引擎（`tests/ocr/`）

| spec | scenario | 測試檔 |
|---|---|---|
| subtitle-text-source | 2022 文化小辭典 y 770–837 跨偏上／偏下分界 787，判成偏下切掉字頂 8–17 px——越過分界超過 pad 就留整條高 | `ocr/test_sheets.py` |
| subtitle-text-source | 紅條上白字的墨水被算成字幕、偏上的對白判不出來——純紅背景的列不算墨水，圖條畫素不變；紅條上白字很寬時一列紅色不到一半，要只看遮罩以外的背景 | `ocr/test_sheets.py` |
| subtitle-text-source | 2024「資料畫面」標籤在左側偏上位 y 740–792，跟偏下對白同時出現——判斷只看置右比對遮罩，照裁偏下 | `ocr/test_sheets.py` |
| subtitle-text-source | 帶外段落（`area`）的 cue 用置右錨定會把右邊雜訊留進圖條、照字幕帶的分界裁——不錨右、不裁上下 | `ocr/test_sheets.py` |
| cue-timing | 各月份恰好一個字幕帶 preset；848 版型不帶 `match`（兩個 preset 搶同一種檔名）；帶外 preset 的區域涵蓋實測範圍、置中的不錨右 | `ocr/test_presets.py` |
