## Why

派給 Claude Vision 的一批有多大、批裡先讀哪一張，現在是照組合圖的檔名順序每 24 張切一塊決定的——**和「這一批會讓讀者累積多少 context」沒有關係**。實測 18 輪、3,367 條 cue：成本幾乎全部是「前面看過的圖被後面每一則回覆重算幾次」（cache 讀佔 token 的 96.7%），而超過某個累積量之後快取會整段作廢重寫（尖峰 175k 以下失效 0 次，184k 那輪失效 3 次、重寫 166,380 token，等於多付 $1.04）。照檔名切出來的各批負載差 1.23–1.44 倍，是運氣好才沒踩到。

同一批實測還量到兩件會靜靜出錯的事。**一是批裡大圖先讀比小圖先讀貴約 10%**：先進 context 的圖，後面每一則都要再算一次錢。**二是《開會了》同一條 cue 的兩列圖條被拆散了**。族語列的降部（`g`／`p`／`y`）被列窗切掉之後會印到下一條圖條的頂端（111 集 88% 的 cue 如此，殘餘中位 3 px、p99 6 px），而兩列**各自裁自己的欄範圍**——左緣差中位 85 px、p90 235 px、最大 636 px，42% 的 cue 差 100 px 以上——所以那一截降部在組合圖上**橫向錯位，落到完全無關的字母底下**，再加上兩列只隔 2 px 貼著，看起來就是那個字母的下加符號。讀者因此把 `ubu` 讀成 `ybu`，也在沒有附加符號的字母底下看到附加符號。

還有一個現成的洞：`batches.py` 是對「還沒核實的組合圖」切批，`vision_tools/prompt.py` 的 `brief()` 是對「全部組合圖」切批，兩邊都從 `b01.tsv` 開始編號。全新的一集兩邊一樣所以平常沒事，**讀到一半、已經有幾批收進 Kari-SRT 之後，再派下一批就會蓋掉已經收進去的 `b01.tsv`**，而且沒有任何地方會報錯。切批改成「整組重新分配」之後這件事會更容易發生。

## What Changes

- **切批改成最長作業優先分配法（Longest Processing Time first）**：先算每張組合圖的重量（視覺 token ＋ 逐逝數 × 17），用總重量除以每批上限算出要幾批，再把組合圖由重到輕逐張丟給目前最輕的那一批；分完檢查有沒有哪一批超過上限，超過就多開一批重分。**BREAKING**：`prompt.SIZE`（一批幾張）與 `prompt.MIN_TAIL`（尾批地板）刪除，換成每批上限 `CEILING`；`batches.py` 的 `--size` 跟著刪除。

- **每一批裡小圖先讀、大圖最後**。省的就是這一件（模擬 94.0%／95.7%），最長作業優先分配法本身不省錢，它買到的是各批負載一致（1.44 倍 → 1.02 倍）。

- **切批回傳的是每批的組合圖清單，不再是連續區段**。`brief.md` 裡「第一張–最後一張」那個範圍要換成逐張列出，否則讀者會照檔名範圍去讀到別批的圖。

- **`batches.py` 與 `brief()` 對同一組組合圖、用同一支切批程式**，`bNN.tsv` 的編號接在 Kari-SRT 已經存在的檔案後面，不得覆蓋。

- **新增 `scripts/ocr/sheetsize.py`**：只用標準函式庫讀 PNG 檔頭拿寬高、算視覺 token。跑 `batches.py` 的系統 `python3` 沒有 PIL 與 numpy，而 `scripts/ocr/sheets.py` 在模組層就 import 這兩個，所以切批端不能碰它；視覺 token 的算法只能有一份，由這支供給兩邊。

- **同一條 cue 的多列圖條，用同一個欄裁切範圍貼，而且照它們在畫面上的間隔貼**（《開會了》兩列在畫面上是連著的，所以中間不留空隙）——等於把畫面上那條字幕帶原樣拼回去，被列窗切掉的降部回到它自己的字母底下。**比加寬空隙更省**：111 集實測視覺 token 從 152,228 降到 150,008（98.5%），而加寬到 6 px 反而是 102.9%；張數都是 70 張不變。新聞一條 cue 只有一列，欄裁切範圍就是它自己，區塊高度仍是 134 px、一個畫素都不動。

- **不做**：《開會了》不加切批程式（39 集三個階段已全部讀完，本來就是用 `ocr.cli pending` 人工切）；不把視覺 token 寫進 `sheets.json`（讀 PNG 檔頭就有精確值，而那個檔有五支程式在讀）。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `subtitle-text-source`：新增一條「派給 Claude Vision 的批次照累積 context 切」——批的大小由預估的累積 context 決定而非張數，各批負載要相當，批裡小圖先讀，同一組組合圖只能有一種切法，且不得覆蓋已經收進 Kari-SRT 的 TSV。並修改〈Claude Vision 輸入組合圖不得付空白的錢〉，加上「同一條 cue 的多列圖條要拼得回畫面上的樣子」——同一個欄裁切範圍、照畫面上的間隔貼。

## Impact

- **Kari-SRT（資料）**：目錄、格式、欄位都不變。唯一的差別是未來集數**哪幾條 cue 落在哪一個 `bNN.tsv`**（切法改了），以及續讀時新的批**接在既有編號後面**。每一列的 cue 編號、列名、文字逐字不變，`ingest` 的排序仍保證行序照 cue 編號遞增。已交付的集數不重跑，`rebuild --verify` 從 `1-cues/` 與 `2-vision/` 離線重建，不碰組合圖與切批。

- **scripts/**：新增 `scripts/ocr/sheetsize.py`；修改 `scripts/ocr/sheets.py`（視覺 token 改由 `sheetsize.py` 供給、同一條 cue 的多列改成逐 cue 算一次欄裁切並照畫面間隔貼）、`scripts/news/vision_tools/prompt.py`（切批整支換掉）、`scripts/news/vision_tools/brief.md`（範圍換成逐張列）、`scripts/news/batches.py`（同一支切批、編號接續）、`scripts/news/README.md`（三處寫著 `SIZE`／`MIN_TAIL` 的說明）。不動 `scripts/aiyalaeho/`；`split_cue.py`、`reread_tools/regen_strips.py` 不受影響（`sheets.json` 格式不變）。

- **tests/**：修改 `tests/news/test_vision_prompt.py`、`tests/news/test_batches.py`、`tests/news/test_sheet_packing.py`、`tests/ocr/test_sheets.py`、`tests/aiyalaeho/test_paths.py`、`tests/README.md`。

- **量出來的常數會過期**：每批上限 120,000、重量估算式 `69,184 ＋ 視覺 token ＋ 逐逝數 × 17`、快取失效那條線 175k，都是 2026-09-11 用 18 輪實讀量的。換模型、換 harness、或組合圖的打包規則再改（一張裝幾條 cue 變了），都要重量。
