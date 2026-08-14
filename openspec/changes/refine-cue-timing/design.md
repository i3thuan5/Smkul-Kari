# refine-cue-timing 設計

## Context

- 現行切分：5fps 取樣（0.2s 格點）、`min_stable=2`；22 集邊界已實測全部
  落在 0.2s 整數倍上。e2e 斷言 worst-start ≤ 0.30s。
- 影片已不在本機：2 月 mxf 母帶（每集 ~16GB）在 SFTP
  `族語新聞/110.1-110.10/2月原始mxf檔`；下載實測 75MB/s。
- 母帶為 1080i tt 交錯掃描——切換瞬間可能出現上下場各半張字幕的過渡幀。
- `cuelib` 已有可重用的原語：`stream_region`（區域串流解碼，可指定
  start/duration/fps）、`text_mask`、`mask_distance`。
- 20,108 個已校讀 cue 的文字對映絕不可失效——重切會改變 cue 集合，
  是明確禁手。
- `verify_band.py` 的「只擋落在 region 內的紅帶邊緣」判準改完未實測。
- CLAUDE.md：git 操作由使用者執行；Python 用 for 迴圈不用 comprehension。

## Goals / Non-Goals

**Goals:**

- 邊界精度 ≤0.05s，cue 集合／編號／文字零改動。
- 精修流程可中斷續跑（逐集），結果可驗證（±0.2s 安全網＋rebuild）。
- 新月份一次到位：影片還在本機時精修完再刪。
- verify_band 紅帶判準拿實際影片驗過並 pin 成測試。

**Non-Goals:**

- 不改 cue 切分演算法與參數（fps=5、min_stable=2 維持）。
- 不追場精度（0.02s）——不拆 field、不做 yadif 雙倍場率。
- 不重讀任何文字；視覺逐字稿與 verified 狀態原封不動。
- 不處理 2 集上傳不完整的跳過集。

## Decisions

### D1：逐幀分類，不重跑 segmenter

精修窗內不做「再切一次」：兩側是誰已知，改成分類問題。對窗內每一張
高 fps 幀算 `text_mask`，與左右 cue 的參考 mask 比 `mask_distance`，
歸類為「仍是左」「已是右」「空白」「不明」。三種邊界的規則：

- 左 cue 結束（A→空白）：最後一張「仍是左」幀的時間。
- 右 cue 開始（空白→B）：第一張「已是右」幀的時間。
- 對接（A→B）：第一張「已是右」（距右 mask 較近）幀的時間，
  同時作為左 cue 的 end。

參考 mask 取各 cue 在粗切中段（避開兩端污染）的一幀。捨棄的替代方案：
高 fps 重跑 Segmenter——`min_stable` 語意隨 fps 改變、雜訊敏感度要重調，
且無法利用「兩側身分已知」這個最強的先驗。

### D2：取樣 25fps（0.04s 格），窗寬 ±0.24s

fps=25 幀距 0.04s，滿足 spec 的 ≤0.05s；窗取邊界 ±0.24s（含一幀餘裕，
覆蓋粗切 ±0.2s 誤差）。交錯過渡幀依 spec 取不明區段中點。每邊界一次
`stream_region(start-0.24, duration≈0.5, fps=25)`，只解字幕帶 region，
一集 ~2,000 個邊界窗共約 17 分鐘帶寬，解碼成本遠低於下載。
捨棄：全片 25fps 再過濾——簡單但把 50 分鐘全解，無必要。

### D3：精修是獨立指令，寫回前全集原子驗證

`python -m scripts.news.refine_cues <slug|--all>`：讀 work dir（新月份）
或臨時下載的影片（回頭精修），輸出前先做全集檢查——每個邊界 |精修−粗切|
≤ 0.2s、start < end、與鄰居不交叉——任一失敗即該集整集不寫、列名退出。
通過才改寫 `cues.json`（僅 start/end），並在 manifest 記 `"refined": true`
（spec 要求可區分精修與否）。捨棄：逐邊界即時寫回——中斷後狀態難判讀。

### D4：兩條執行路徑共用同一支程式

- **回頭精修（22 集）**：`refine_fetch.sh` 逐集「SFTP 下載 → 驗位元組 →
  refine_cues → 刪影片」，沿用 `fetch_sftp.sh` 的密碼／驗檔模式；跑完
  `make_all` 重產 SRT → `rebuild --verify` → 使用者一個 commit 同時換
  `Kari-SRT/cues/` 與 `srt/`。
- **新月份**：`fetch_sftp.sh` 在 cues 成功後、`rm 影片`之前插一步
  refine_cues（影片就在 STAGE，零額外下載）。

**STAGE 的存放與跨 session 共用**：預設 STAGE 從 `/tmp/ilrdf-stage`
移到 `kithann/out/stage/`（大碟、gitignored、container 重啟不消失）。
生命週期維持「該影片的最後一個消費步驟完成即刪」；跨 session 共用
規則：(1) 下載前先看 STAGE 有無同名檔且位元組數與遠端相符，有就
直接用、跳過下載；(2) 想保留給別的 session 用時，放同名 `.keep`
sentinel（`影片名.keep`），有 sentinel 的檔案任何流程都不刪，刪除
責任歸建立 sentinel 的人；(3) 同一時間只跑一個 fetch 迴圈（開跑前
檢查 `stage.lock`，存在且 pid 活著就拒跑）。

### D5：verify_band 實測併入下載迴圈

回頭精修反正逐集下載，第一支影片順跑 `verify_band --preset titv-news`
（不加 `--quiet`）人工看剖面一次。另抓一支紅帶低位型（1 月卑南
`卑南語-20210103S1800.mp4`）單獨驗通過案例。判準本身用合成剖面 pin 進
`tests/`：紅帶在 region 下方遠處→過、侵入 region→擋（spec 兩個
scenario 的可執行形式）。

### D6：SRT 留白在組裝層做，0.5s 對齊 Kaldi 預設

留白規則實作在 SRT 組裝（`make_srt` 的 entries 後處理，
`merge_repeats` 之後、`apply_gap_rules` 之前）。與鄰句的間隔
`g = next_start − prev_end`，兩側各延伸 `min(0.5, g/2)`——間隔不足
1 秒時在中點相接（可相接、不重疊；例 1.0–2.0 與 2.2–3.2 →
1.0–2.1 與 2.1–3.2），再以 `[0, 影片長度]` 截短。影片長度來源：
現有 `cues.json` manifest **沒有** duration 欄位——精修 pass 手上有
影片，順手 `ffprobe` 回填 `duration` 進 manifest；組裝時若仍缺
（理論上不會），以最後一個 cue 的 end 為保守上限並警告。
0.5s 的依據：Kaldi
`steps/cleanup/internal/segment_ctm_edits.py` 的
`--max-edge-silence-length` 預設 0.5s（segment 邊緣最多保留 0.5s 靜音，
再長會截掉；`clean_and_segment_data.sh` 另加 ~0.02s 特徵邊緣補償）——
字幕兩側各留 0.5s 正好餵滿它願意保留的邊界靜音。`cues.json` 不含留白
（spec 要求），所以資料層的精修精度與顯示層的留白互不污染。
捨棄：把留白寫進 cues.json——資料失真，之後任何以切換點為準的用途
（對齊、統計）都會被 0.5s 污染。

### D7：2 月補完走「目錄驅動」而非 mxf 資料夾驅動

`build_inventory.py` 現以本機 mxf 資料夾為輸入，只涵蓋 24 集。補完
改由 `ilrdf-corpus.csv` 目錄驅動：2 月共 64 集（16 族語 × 4 集，
含晨間時段——NL005 代碼，`find_transcript` 的 0800 對映已支援）。
**範圍不是全部**：先做到「每族語至少 2 集」，缺額集數以 2 月內
集數較早（播出較早）者優先——共 13 集（清單在 tasks 6.1，經使用者
確認後定案）。目錄資料已知的坑：鄒 034午 在目錄裡**沒有影片
路徑**；鄒 041午 與 排灣 037晚 本機那兩份 mxf 上傳不完整，但 SFTP
版本預期完整——排最前面先做、下載後以位元組數驗證，仍不完整則
遞補（排灣→051晚、鄒→055午）；目錄把 037晚 指到 37「午間」檔名、
賽夏 057晚 檔名也寫「午間」——一律以「集數＋時段查目錄」為準、
下載後驗位元組數。晨間集的版型
未驗過，該資料夾第一支照例跑 verify_band。`inventory.json` 擴充
收錄新集數（沿用 `srt_name`／slug 規則）。

smkul.csv 是生成物（make_all 產生、rebuild 逐 byte 比對），要補
13 列「待處理」必須走資料流而非手改：inventory 擴充後，rebuild 需要
「未交付集」語意——cues 與 srt **皆無**的集產「待處理（尚未切cue）」
列且不做比對；只缺其一仍視為交付集缺件、照舊指名失敗；兩者皆失的
退化情形照舊靠 tracker 逐 byte 比對把關（重建出的列會變待處理、與已
commit 的 smkul.csv 不符而被抓到）。此作法已在規劃期試做驗證可行
（rebuild --verify 與測試全過）後還原，apply 時照做（task 6.1）。

無文稿的集不跑對齊，
`gap_sheets` 天生把無文稿當全 gap，流程不變。視覺辨識照
`/smkul-news` 慣例：先報 sheet 數與 token 估算、取得同意再放
subagent。

### D8：交付基準的換版程序

時間戳全變 → `Kari-SRT/srt/` 逐 byte 基準改版。程序：精修完成 →
`make_all`（來源仍是 work dir transcripts；文字不變）→ 新 SRT 與舊 SRT
diff 應**只有時間行**（加一道檢查：逐 cue 文字序列相同）→
`rebuild --verify` 以新資料自洽 → 使用者 commit。change 目錄留
`timing-delta.txt`（每集邊界偏移分佈統計）供審閱。

## Risks / Trade-offs

- [SFTP 上母帶被移動／删除] → 開跑前先 `ls -l` 驗 22 支俱在且位元組數
  與 inventory 相符；缺集則該集保持粗切、列名回報，不阻塞其他集。
- [參考 mask 取到污染幀（cue 內插圖卡切換）] → 參考幀取 cue 中段
  且與該 cue 粗切 mask 距離超閾值時換樣本幀；仍不明則該邊界維持粗切
  並計數回報（安全網保證不會寫入壞值）。
- [背景高頻閃爍造成「已是右」誤判] → 分類需連續 2 幀一致才採信
  （0.08s，仍在精度預算內）。
- [mp4 月份（新流程）GOP 較長，區域解碼 seek 成本高] → stream_region
  以 -ss 前置 seek，實測後若過慢改為每集一次連續解碼、Python 端跳窗。
- [rebuild 用的 cues 來自 Kari-SRT，精修寫的是 work dir] → 回頭精修
  直接以 `Kari-SRT/cues/` 為讀寫對象（22 集的正本在那裡），work dir
  不再是來源。

## Open Questions

（無——精度目標、演算法方向、成本與換版程序已在前期討論與使用者定案。）
