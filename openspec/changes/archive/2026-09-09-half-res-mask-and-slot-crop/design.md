# Design

## Context

動機見 proposal.md〈Why〉。這裡只記塑造做法的現況與限制。

`scripts/ocr/cuelib.py` 的 `text_mask()` 是整條影像側管線的中心：切 cue 逐格算它、精修逐格算它、`verify_band`／`blank_runs`／`reread` 也各自算它。`Segmenter` 拿相鄰兩張遮罩比 Jaccard 距離判斷「字有沒有換」。`finish-aiyalaeho-batch` 已在 `MaskSpec` 上加了 `band_rows`（列範圍，量測來的），`text_mask` 尾端據此把範圍外的列設為 False；`None` 時原樣返回。本 change 疊在這個基礎上。

`scripts/ocr/sheets.py` 的 `_cue_blocks()` 目前只做欄方向的 `ink_bbox` 裁切，`crop` 的上下兩個參數寫死 `0` 與 `img.height`——**垂直方向從來沒有裁過**。垂直結構只來自 preset 的 `lines`，新聞宣告一列 `{y:0, h:122}`。

`scripts/news/verify_band.py` 的 `profile()` 已在取樣解碼中算列方向的墨水剖面。它**每個資料夾跑一次**，不是每集。

`rebuild --verify` 從 store 的時間軸與 TSV 離線重建 SRT，**完全不碰 `text_mask`**——所以它抓不到切割回歸，也不會因本 change 而紅。

### explore 階段量到的數字（判準的來源）

| 量測 | 值 | 樣本 |
|---|---|---|
| 新聞字幕右緣 | 中位數 1735–1737，標準差 31–70 px；左緣標準差 460–470 px | 3 集逐 cue |
| 跨集右緣中位數 | 26 集在 1735–1737，1 集（046晚）在 1631 | 27 集各抽 60 條 |
| 欄剖面右崖 | 正常三集 1744–1745，046晚 1640 | 4 集 600+ 格 |
| 字幕垂直落點 | 偏下 79.8%、偏上 10.8%、判不出來 9.4% | 27 集 1,080 條圖條 |
| 逐集判不出來率（排除空白後）| 中位 2.9%、p90 9.1%、最高 12.5% | 同上 |
| `text_mask` 每格 | 全帶全解析 17.62 ms／全帶半解析 3.67／置右遮罩全解析 4.09／**置右遮罩半解析 1.08** | 120 格 |
| 切割品質 | 見下表 | 4 集，對 store 正解評分 |

四集切割品質（置右字幕比對遮罩 x1250–1790、列 4–114、門檻 0.35）：

| 集 | 重覆對 | 吞句 | 漏切 |
|---|---|---|---|
| 032午 | 268 → 103 | 37 → 31 | 0 → 2 |
| 041午 | 70 → 22 | 9 → 8 | 0 → 0 |
| 051晚 | 370 → 128 | 87 → 43 | 0 → 3 |
| 046晚（版型異常那集）| 48 → 27 | 0 → 1 | 0 → 0 |

半解析度與置右遮罩疊起來的品質（032／051）：103/31/2 對 105/30/2、128/43/3 對 122/45/3——差異在雜訊範圍內，兩者可疊。

## Goals / Non-Goals

**Goals**

- 兩個語料的遮罩計算降到現行的四分之一以下，切割品質不退。
- 新聞的重覆 cue 砍掉一半以上，且**不以增加吞句為代價**。
- 新聞的 Claude Vision 輸入組合圖張數再降三成以上，讀圖精確率不退。
- 版型變異有把關擋著，而不是靜靜產出錯的時間軸。
- 效益可重現：任何人日後改切割參數，都有一支工具量得出好壞。

**Non-Goals**

- **不重切已交付的集數。** 重切會作廢已交付的時間軸並要求重讀全部 vision。
- 不動 `rebuild --verify` 的範圍與行為。
- 不做間隙稽核（漏切的複查清單）——理由見〈Decisions〉D6。
- 不改《開會了》的圖條與比對範圍——理由見 D5。
- 不追求把漏切降到零；淨值已是正的（051晚 從「吞 87」變成「吞 43＋漏 3」）。

## Decisions

### D1 — 遮罩的解析度、比對範圍都放進 `MaskSpec`，由 `frame_mask()` 一次套用

`MaskSpec` 新增三個鍵：`scale`（取樣倍率，預設 1）、`compare_cols`、`compare_rows`（比對範圍，region 內座標，預設 `None`）。新增 `MaskSpec.scaled(k)` 回傳一份把所有長度量除以 `k` 的複本（`outline_size`、`thin_size`、`band_probe` 的 x／w、`band_rows`、`compare_cols`、`compare_rows`），新增 `frame_mask(rgb, spec)` 依 `spec.scale` 取樣、算遮罩、再依 `compare_*` 裁。

**`text_mask()` 本體不動。** 它是 `verify_band`／`blank_runs`／`reread` 與既有測試的共用基礎，也是 `band_rows` 的所在；動它會把風險散到四支不相干的程式上。`frame_mask()` 在 `scale=1` 且無 `compare_*` 時 SHALL 與 `text_mask()` 逐 bit 相同，這條當回歸錨點。

**這三個欄位不進 `to_dict()`／`from_dict()` 的鍵表**（見 D8：manifest 不新增任何鍵），只由建構參數帶入。這一點要用測試鎖住鍵集合——`MaskSpec` 其他每個欄位都在那兩張表裡，照著現有寫法讀很容易順手把新的也加進去，加了就等於偷偷把參數寫進 `cues.json`。

*替代案*：把 scale 塞進 `text_mask` 的參數。否決——呼叫點四處，全都要改，而且三處根本不該用半解析。

### D2 — 比對範圍寫死在 preset，不逐集量

跨 27 集量到右緣中位數只有一集偏離（1631 對 1736，差 104 px）。而**固定範圍 x 1250–1790 對那一集照樣有效**（重覆對 48→27、漏切 0），因為字幕右端 1631 仍在範圍內、範圍左緣 1250 給的餘裕（486 px）大於一句字幕的最短寬度（p10 約 420–546 px）。

*替代案*：逐集量測（比照 `band_rows`）。否決——新聞的 `verify_band` 是**每個資料夾跑一次**，改成每集要多 41 秒／集的解碼（一個月 71 集約 48 分鐘），換來的穩健度在量到的資料上並不需要。

代價是版型若變得比 046晚 更多就會失準，所以配 D3。

### D3 — 把關量「右崖」，而且比的是「比對遮罩裝不裝得下字」

在 `profile()` 現有的迴圈裡多加一行 `cols += mask.sum(axis=0)`，**不多花解碼**。欄剖面的形狀是一道右崖（字幕靠右對齊，長短句的右端疊在同一處）。判法：24 px 寬平滑後取峰值的 25% 當門檻，最右邊仍在門檻上的欄就是右崖。

**判準比的是「右崖落不落在比對遮罩裡、而且留了夠多的字」，不是「右崖等不等於某個期望值」**（實作時修正）。原本想寫「偏離 preset 宣告值 ±60 px 就拒切」，但那會誤殺 046晚：它的右崖在 1640、比常態的 1744 少 104 px，可是**固定遮罩 x 1250–1790 對它照樣有效**（實測重覆對 48→27、漏切 0），因為 1640 仍在遮罩內、左邊還留著 390 px 的字。拿「期望值 ±容許量」去量會把這種能用的集擋掉。

改成兩條：右崖 SHALL 落在比對遮罩的右界以內；而且 SHALL 距離遮罩左界至少 200 px，確保遮罩裡真的有一段字可以比。200 的來源是量到的最短字幕寬度（p10 約 420–546 px），取它的一半再往下留餘裕。這樣 046晚 通過（1640 ≥ 1250+200），而真正把字幕移出遮罩的版型會被擋下。

**「範圍內墨水佔比」實測不具鑑別力**：正常三集 53%／69%／62%，異常集 58%，夾在中間。原因是它同時受句長與背景亮度左右。這條要寫進 spec，免得日後有人以為那是更簡單的做法。

### D4 — 上下位置判斷的墨水，用置右字幕比對遮罩的欄範圍量

用全寬量時，亮背景（枯草、報紙）散在整條 1920 px 上，把兩位的墨水拉平，比值卡在 2.0 邊緣而退回全高。改用置右範圍量，背景只截到約 28%、字幾乎整段都在，比值就拉開了：三條實例從 2.0 變成 3.2／3.1／7.6。全集效果：退回全高的條數 032 186→79、051 122→29，圖條總高再降 1.7–6.5%。

**比值門檻維持 2.0**（使用者裁定）。它防的**不是「兩列都是字幕」**——掃 3,339 條圖條，新聞沒有這種情形，版型上字幕是一列落在兩個高度之一。它防的是**畫面裡本來就有的字和字幕搶同一條圖條**：051 cue 223 偏上是紅布條「屏東縣瑪家鄉舊筏灣…」、偏下才是字幕「行動電話共構基地台」，比值 1.10 退回全高，字幕保住；另有全螢幕法規圖卡、報紙翻拍兩類實例。這個理由要寫進 README，不要寫成「兩位都有字」。

### D5 — 《開會了》只吃半解析度

它的字幕壓在**不透明**的橙黃漸層帶上，影片背景根本進不了遮罩（漸層是飽和色，被 `white_min`／`max_spread` 排除）。三集實測重覆對 0／0／78——**沒有這個病**。中錨定比對遮罩在 085／068 毫無作用，在 094 把 78 砍到 36 卻憑空多出 2 條吞句。圖條裁切則實測會切薄族語列的撇號與 `i` 的點，族語列精確率 98.6%→76.8%，且 094 一張都省不到。

實作上：《開會了》的 preset 不宣告 `compare_*` 與 `sheet.row_slots`，程式要能吃「沒有這些鍵」。

### D6 — 不做漏切的間隙稽核

置右比對遮罩會讓 0.11–0.17% 的 cue 整條消失。稽核做得出來（在時間軸的間隙裡用全帶重切，成本只要全片的 6–7%，兩集實測真漏 5/5 全抓到），但不做，三個理由：

1. **精確度修不好**。誤報 032 是 2 真對 24 誤報。唯一想得到的自動判準（形狀：一行字留下多道窄痕）在 051 完美，在 032 卻**誤殺真漏**——那條「但是」只有兩個字、畫面又被圖卡佔住，段寬量到 105 會被丟掉。用降低召回率換精確度，對一個專抓稀有漏失的東西是本末倒置。
2. **比例失衡**。本 change 一集丟 2–3 條，但**現行做法本來就一集丟 43–87 條吞句**，而吞句沒有任何稽核。查新增的 3 條、無視既有的 43–87 條，力氣用錯地方。
3. **最壞情況是留白，不是寫錯**。裁錯或漏切造成的空白，`vision_tools/brief.md` 已要求 Claude Vision 對招牌、布條、圖卡留空，所以症頭是一個空白列，而 `blank_runs.py` 就在複查空白列。

日後若真要做「管線漏了什麼」的稽核，對象應該是吞句，那是另一條 change。

### D7 — `min_ink` 用全帶全解析的單位表達，程式內換算

CLI 的 `--min-ink` 預設維持 120，意思固定是「全帶、全解析下的墨水畫素數」。程式依 `scale` 與比對範圍面積換算成實際餵給 `Segmenter` 的值，manifest 記換算後的實際值。這樣文件、skill、既有筆記裡的 120 都不必改，而 manifest 仍然自我完備。實測 `min_ink` 在 12–120 之間結果幾乎一樣，本來就不敏感。

### D8 — 新參數的家是 preset，manifest 不新增任何鍵（使用者裁定）

原本的設計是把 `scale`／`compare_cols`／`compare_rows`／`row_slots` 寫進 `cues.json`，讓 `refine_cues`、`gap_sheets`、`rescan_band` 從 manifest 讀。**使用者裁定不加新鍵**，所以改成：**參數只住在 preset，每一個消費端明確指定 preset**。

分界的原則（這條要寫進 README，免得日後有人把它們搬回 manifest）：

- **量測來的**（逐集不同、除了 manifest 無處可存）→ 記進 manifest。`band_rows` 屬於這類，維持現況不動。
- **宣告來的**（同一版型固定不變、preset 就是正本）→ 留在 preset。本 change 的四個參數屬於這類。

消費端要不要收 preset，看它**是不是兩個語料共用**：

| 程式 | 誰在用 | 改成 |
|---|---|---|
| `ocr/cli.py cues` | 兩者共用 | 不變（已有 `--preset`／`--presets`）|
| `news/refine_cues.py` | **兩者共用**——《開會了》的 `batch_cut.sh` 與它的 README 都直接呼叫 `scripts.news.refine_cues` | **加 `--preset`／`--presets`**；`fetch_sftp.sh` 與 `batch_cut.sh` 兩邊都握有各自的 preset |
| `news/gap_sheets.py` | 新聞專用（`scripts/aiyalaeho/README.md` 明文把它列為「news 有而這裡沒有的四支」之一）| 不加參數；讀 `scripts/news/presets.json` 的 `titv-news`（可用 `--preset` 覆寫，但呼叫端不必改）|
| `news/rescan_band.py` | 新聞專用（已有寫死的 `REGION = "420,910,1500,122"` 前例）| 同上 |

**沒給 preset 時一律拒絕跑，不靜默退回另一組參數。** 這與既有 spec 條文〈字幕帶區域由呼叫端指定，不得靜默退回自動偵測〉同一個道理：靜默用了不同的參數，粗切與精修的判準就會不一致，而且沒有人會發現。

**「不設比對範圍」那條路不是為了相容舊資料而留的，它是《開會了》現在要走的路**：085 的族語列橫跨 x 501–1420（置中，中心標準差只有 2 px），套上新聞的 x 1250–1790 只會留下約 18%，精修會拿一小條殘影去比對而整個垮掉。所以那個分支是活的需求，不能移除；既然要在兩條路之間選，共用的那一支就必須有辦法分辨——這就是 `refine_cues` 那一個參數存在的全部理由。

*代價（明知而接受）*：work dir 不再自我完備——`refine_cues` 會變成 `region` 與 `mask`（含 `band_rows`）讀 manifest、`scale` 與 `compare_*` 讀 preset 的混合來源；preset 若在切完之後改動，重跑精修會用到與粗切不同的參數。批次流程裡兩步緊接著跑、傳同一個 `$PRESET`，所以實務上碰不到；要碰到得有人隔了一段時間、改過 preset 之後才單獨重跑精修。

*好處*：preset 改對了之後，重跑就吃得到，不會卡在一份過期的複本上；而且 store 的 `1-cues/` 保持現在的樣子，不因引擎調參而長大。

### D11 — `--mask-scale` 預設 None，由 preset 宣告（實作時的修正）

原本寫「`--mask-scale` 預設 2」。實作時發現那會**改到沒有 preset 的呼叫端**：`tests/e2e/fixture.py` 用 `autodetect=True`、不給 preset 跑合成影片端對端，預設 2 會讓它突然改用半解析度切，端對端的時間斷言跟著飄。

改成：**旗標預設 `None`，解析度由 preset 的 `mask.scale` 宣告，旗標只是覆寫**。沒有 preset 就是 1，也就是本 change 之前的行為，逐畫素相同。這也更貼合 D8 的分界原則——版型宣告的東西住 preset。

同理 `min_ink`：CLI 的 120 維持「全帶、未取樣」的語意（README、skill、筆記裡到處都是這個數字），`effective_min_ink()` 依實際比對面積換算後才餵 `Segmenter`，manifest 仍記宣告值 120。**`refine_cues` 必須跑同一套換算**，兩邊只要有一邊沒做，那一邊就會把每一格都判成空白而且不出聲。

### D9 — Claude Vision 批次 72→24，`MIN_TAIL` 一起降

`SIZE` 72→24、`MIN_TAIL` 24→8。依回覆 id 歸併重算（一則回覆帶多個 tool_use 在 log 裡佔多行、每行帶同一份 usage，逐行加總會重複計算），一批 72 張比三批 24 張貴 1.5–1.9 倍：每一輪呼叫都要重送整段變長的對話，成本隨批次長度近似平方成長。`MIN_TAIL` 不跟著降的話每個尾批都會被併成 47 張，等於白改。

### D10 — 離線評分工具放 `tools/cuescore/`，不放 `tests/`

它吃真資料（`cues.json` ＋ vision TSV），不符合「測試要能離線、用 fixture 合成」的規定，定位比照 `tools/measure/`、`tools/mxf2mkv/`。它算三個指標：**重覆對**（相鄰相接且文字相同的 cue 對）、**吞句**（store 的換句時刻被一條新 cue 吞掉）、**漏切**（store 裡有字的 cue 沒有任何新 cue 覆蓋）。`tests/tools/test_cuescore.py` 用合成的 cues 與 TSV 測它自己的算術。

## 檔案樹

```
scripts/
  ocr/
    cuelib.py          改：MaskSpec 加 scale／compare_cols／compare_rows；新增 scaled()、frame_mask()
    cli.py             改：_feed_frames 改呼叫 frame_mask；--mask-scale；把 preset 的 row_slots 傳給 build_sheets
    sheets.py          改：build_sheets 收 row_slots 參數，_cue_blocks 據此判上下位裁列；回傳逐集判不出來的比率
  news/
    refine_cues.py     改：加 --preset／--presets（沒給就拒跑）；窗內遮罩改呼叫 frame_mask
    gap_sheets.py      改：加 --preset／--presets，傳給 build_sheets
    rescan_band.py     改：加 --preset／--presets，傳給 build_sheets
    verify_band.py     改：profile() 多回欄剖面；新增右崖判定；judge() 多一條規矩；輸出印出量到的右崖
    presets.json       改：titv-news／amis-titv-news 加 mask.scale、mask.compare_cols/rows、sheet.row_slots
    vision_tools/
      prompt.py        改：SIZE 72→24、MIN_TAIL 24→8
  aiyalaeho/
    presets.json       改：兩個 preset 只加 mask.scale
tools/
  cuescore/
    __init__.py        新
    score.py           新：吃 cues.json ＋ vision TSV，印重覆對／吞句／漏切
    README.md          新：三個指標的定義、怎麼跑、數字怎麼讀
tests/
  ocr/
    test_mask.py       改：frame_mask 回歸錨點、scaled() 同步縮、compare 範圍套用
    test_segmenter.py  改：墨水全在範圍外當空白、比對範圍不影響 composite
    test_sheets.py     改：上下位置判斷四條、墨水用 compare_cols 量、逐集比率
    test_presets.py    改：新鍵讀得進來
    test_auto_options.py 改：--mask-scale 的結構把關
  news/
    test_verify_band.py 改：右崖、位移、拒切、訊息
    test_refine.py     改：沿用 manifest 參數；舊 manifest 不變
    test_vision_prompt.py 改：SIZE 24、MIN_TAIL 8
  tools/
    __init__.py        新
    README.md          新：本目錄的 spec × scenario 表
    test_cuescore.py   新：合成 cues ＋ TSV 測三個指標的算術
```

**manifest（`cues.json`）不新增任何鍵。** 參數從 preset 流到各消費端：

| 參數 | 正本 | 誰讀 |
|---|---|---|
| `mask.scale` | `presets.json` | `ocr/cli.py`、`news/refine_cues.py` |
| `mask.compare_cols`／`compare_rows` | `presets.json` | 同上 |
| `sheet.row_slots` | `presets.json` | `ocr/sheets.py`（由 `cli.py`／`gap_sheets`／`rescan_band` 傳入）|

`segmenter.min_ink` 這個既有的鍵仍照舊記換算前的值（見 D7），不改語意。

## spec × scenario × 測試檔對照表

| spec | scenario | 測試檔 |
|---|---|---|
| cue-timing | 字幕靠一側對齊時，另一側的畫面不再淹沒切點 | `tests/ocr/test_segmenter.py` |
| cue-timing | 圖條不變（有無比對範圍，圖條逐畫素相同）| `tests/ocr/test_segmenter.py` |
| cue-timing | 精修沿用同一範圍 | `tests/news/test_refine.py` |
| cue-timing | 未提供範圍時行為不變（`frame_mask` 對 `text_mask` 逐 bit）| `tests/ocr/test_mask.py` |
| cue-timing | 比對範圍完全沒有墨水的 cue 不產生 cue | `tests/ocr/test_segmenter.py` |
| cue-timing | 對齊邊緣位移擋下 | `tests/news/test_verify_band.py` |
| cue-timing | 量測值一律輸出 | `tests/news/test_verify_band.py` |
| subtitle-text-source | 字在其中一處時裁掉另一處的留白 | `tests/ocr/test_sheets.py` |
| subtitle-text-source | 兩處墨水相當時退回不裁 | `tests/ocr/test_sheets.py` |
| subtitle-text-source | 墨水太少時退回不裁 | `tests/ocr/test_sheets.py` |
| subtitle-text-source | 沒有宣告候選位置的語料不裁 | `tests/ocr/test_sheets.py` |
| subtitle-text-source | 判不出來的比率逐集可見 | `tests/ocr/test_sheets.py` |

scenario 那一欄要寫成「具體會錯的情形」，寫測試時照這些坑寫（來源是 explore 階段量到的）：

- `scaled(2)` 忘了縮 `band_probe` 的 x／w → 《開會了》的帶偵測會在半解析下指到錯的欄，整集判成「無帶」。
- `scaled(2)` 忘了縮 `band_rows` → 疊在 `finish-aiyalaeho-batch` 成果上時裁到錯的列。
- 比對範圍套在 `Cue.samples` 上 → 圖條變成只有右邊那一塊，Claude Vision 讀不到左半句。這條要用「有無比對範圍，圖條逐畫素相同」鎖住。
- 上下位置判斷用全寬量墨水 → 亮枯草把比值壓到 2.0 邊緣，該裁的沒裁（實測 032 有 186 條這樣）。
- 上下位置判斷沒有退回全高 → 051 cue 223 那種「偏上是布條、偏下才是字幕」會裁到布條，字幕消失且 Claude Vision 只會留白。
- `MIN_TAIL` 沒跟著 `SIZE` 降 → 每個尾批被併成 47 張。
- 欄剖面把關改用「範圍內墨水佔比」→ 正常 53–69%、異常 58%，分不開。

## Risks / Trade-offs

- **0.11–0.17% 的 cue 會整條消失（漏切）** → 同一改動把吞句從 37–87 降到 31–43，救回來的比丟掉的多（051晚 一集少丟 41 句）；最壞情況是留白而非寫錯字，落在 `blank_runs.py` 既有的複查路徑上。不另做稽核（D6）。
- **固定比對範圍對未來未知的版型可能失準** → D3 的欄剖面把關擋下；目前量到的最壞版型（046晚，右緣差 104 px）固定範圍照樣有效。
- **上下位置判斷可能裁錯（比值 ≥ 2.0 但畫面的字更強）** → 退回全高的門檻 2.0 是保守側；`brief.md` 已要求 Claude Vision 對招牌布條圖卡留空，所以裁錯的症頭是空白列而非假對白；逐集判不出來比率讓版型異常的集數看得出來。
- **切割回歸沒有既有把關**（`rebuild --verify` 不碰 `text_mask`）→ 只能靠新寫的單元測試；`frame_mask` 對 `text_mask` 逐 bit 那條是最重要的一道。
- **參數來源分兩處**（`region`／`band_rows` 在 manifest、本 change 的四個在 preset）→ 消費端沒給 preset 就拒跑，不靜默退回；分界原則寫進 README，避免日後被「統一」回 manifest。
- **兩條線動到同幾支檔**（`parallel-corpus-quality` 改過 `cli.py`／`sheets.py`／`refine_cues.py` 的 `json.dump`）→ 動手前重讀檔案，做前後通知對方。

## Migration Plan

1. 引擎與工具（`cuelib`／`cli`／`sheets`／`refine_cues`／`verify_band`／`tools/cuescore`），每一步先紅後綠。
2. preset 加鍵：新聞先加，《開會了》只加 `scale`；同時給 `refine_cues`／`gap_sheets`／`rescan_band` 加上 `--preset`，並更新 `fetch_sftp.sh` 的呼叫。
3. 驗收：`tox -e unittest`、`tox -e flake8`、`rebuild --verify`（應維持逐 byte 相同，因為它不重切）、`name_catalogue --check`。
4. 用 `tools/cuescore` 對 032午／041午／051晚／046晚 四集重算，數字要對得上 design〈Context〉那兩張表——這是效益的驗收，不是單元測試。
5. 新切的集自動吃到新行為；**已交付的 74 集不重切**。

回退：把 preset 的新鍵拿掉即可回到現行行為（程式對「preset 沒有這些鍵」的處理就是現行行為），不需要回退程式。既有 work dir 與 store 檔案完全不受影響，因為本 change 不寫任何新鍵。

## Open Questions

- 逐集「判不出來比率」的告警門檻：量到正常範圍是中位 2.9%、p90 9.1%、最高 12.5%（排除純空白的圖條後），建議先訂 30%，跑完一整個月再回頭校。**這一項只是報告用的數字、不擋流程**，所以晚一點定不影響 specs 與任務拆解。

  高的時候的處置：**不做任何自動處理**——逐條的退回全高已經讓它安全了，比率高只代表「這一集沒省到」。它的診斷價值在一個別處抓不到的情形：字幕帶整體在 region 內上下位移、跨過分界列 65。那種位移**通過** `verify_band`（對白平台仍在 region 內、紅帶仍在 region 外），欄方向的把關也不會叫（右緣沒變），只有這個比率會浮出來。所以處置是人看一眼該集的 `sheet_001`：若整個資料夾都這樣，是 preset 的分界列要改；若只有一兩集、而且畫面本來就多布條圖卡報紙，那是內容不是版型，不必處理。
