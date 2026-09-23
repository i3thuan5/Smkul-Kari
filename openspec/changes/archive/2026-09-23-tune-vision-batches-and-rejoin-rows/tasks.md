## 0. 前置

- [x] 0.1 重讀 `scripts/news/vision_tools/prompt.py`（`plan`、`brief`、`_brief` 的 `first`／`last`）、`scripts/news/batches.py`（`pending_sheets`、`spans`、`main` 的 `made` 編號）、`scripts/ocr/sheets.py`（`_block_size`、`flush_sheet` 兩處 `+ 2`）的現況；確認平行 session 沒有正在改這幾支

## 1. 視覺 token 的正本（`scripts/ocr/sheetsize.py`）

- [x] 1.1 `tests/ocr/test_sheetsize.py`（紅）：讀 PNG 檔頭拿寬高——正常的 PNG 拿得到；**不是 PNG 或檔頭被截斷要明確報錯，不可以回傳猜的數字**；視覺 token ＝ `⌈寬÷28⌉ × ⌈高÷28⌉`，邊界（寬剛好 28 的倍數、差一個畫素）各驗一次；**整支只准用標準函式庫**（測試裡擋掉 `numpy`、`PIL` 再 import 一次仍要能跑）
- [x] 1.2 `scripts/ocr/sheetsize.py`（綠）：`PATCH`、`LONG_EDGE`、`VISUAL_TOKENS` 移進來當正本，加 `png_size(path)` 與 `tokens(path)`；註解記下「只讀前 24 bytes、不用 PIL」的理由
- [x] 1.3 `scripts/ocr/sheets.py`（綠）：改成從 `sheetsize.py` import 那三個常數與算法，刪掉自己那一份；`tests/ocr`、`tests/news`、`tests/aiyalaeho` 全綠

## 2. 同一條 cue 的多列，拼回畫面上的樣子

- [x] 2.1 `tests/ocr/test_sheets.py`（紅）：一條 cue 有多列時，各列**用同一個欄裁切範圍**（各列墨水的聯集）；上下兩列的字長度差很多時，短的那列不得自己往內縮（否則被切掉的降部會橫向錯位）；列與列之間的間隔**等於它們在畫面上的間隔**——相鄰的兩列不留空隙、中間本來有空白的版型要照留；`flush_sheet` 貼出來的位置與 `_block_size` 算的高度一致
- [x] 2.2 `tests/ocr/test_sheets.py`（紅）：一條 cue 只有一列的語料**逐畫素不變**（區塊高度仍是 `gap + 列高 + 2`，122 的語料仍是 134 px）
- [x] 2.3 `scripts/ocr/sheets.py`（綠）：`_cue_blocks()` 改成逐 cue 算一次欄裁切、`flush_sheet()` 照畫面間隔貼；註解記下為什麼不是「把空隙加寬」（兩列左緣差中位 85 px、最大 636 px，42% 差 100 px 以上，加寬只是比較看得出來，錯位還在；而且加寬是 102.9%、拼回去是 98.5%）
- [x] 2.4 `tests/news/test_sheet_packing.py`（紅→綠）：區塊高度的算法跟著改，族語新聞仍是 134 px、一張仍裝 13 條
- [x] 2.5 `tests/aiyalaeho/test_paths.py`（紅→綠）：《開會了》的區塊高度改成拼回去之後的值，一張組合圖仍不會被縮小

## 3. 切批改成最長作業優先分配法

- [x] 3.1 `tests/news/test_vision_prompt.py`（紅）：切批回傳**每批的組合圖清單**；批數由總重量除以每批上限算出；每張恰好一批、不重不漏、沒有空批；各批預估量差不得超過 1.1 倍；**批內由小到大**；重量相同時順序固定（同樣輸入切出同樣的批）；幾張特別大的圖集中時分完仍超過上限就多開一批重分
- [x] 3.2 `scripts/news/vision_tools/prompt.py`（綠）：刪 `SIZE`、`MIN_TAIL`，加 `CEILING = 120000` 與重量估算式（`69,184 ＋ 視覺 token ＋ 逐逝數 × 17`），註解記下量法、日期與「換模型或換 harness 要重量」；`plan()` 改成最長作業優先分配法並回傳清單；重量用 `sheetsize.tokens()`
- [x] 3.3 `tests/news/test_vision_prompt.py`（紅→綠）：判準逐張列出這一批要讀哪幾張，不得出現「第一張–最後一張」那種範圍
- [x] 3.4 `scripts/news/vision_tools/brief.md`＋`_brief()`（綠）：`{first}`／`{last}` 換成逐張列出的清單；`tests/news/test_vision_prompt.py` 裡「每個 `{…}` 都要被換掉」那條仍綠

## 4. 兩支程式一份清單、編號不覆蓋

- [x] 4.1 `tests/news/test_batches.py`（紅）：`batches.py` 與 `brief()` 對**同一組組合圖**、用同一支切批，批數與每批內容一致；讀到一半的集數，新批的 `bNN.tsv` 接在 Kari-SRT 既有檔名後面，**已經收進去的檔不得被覆蓋**
- [x] 4.2 `scripts/news/batches.py`（綠）：`spans()` 換成呼叫新的切批、餵同一組組合圖；編號看 Kari-SRT 既有的 `b*.tsv` 接下去；刪掉 `--size`

## 5. 文件

- [x] 5.1 `scripts/news/README.md`：三處寫著 `SIZE`／`MIN_TAIL` 的說明改成「每批上限與最長作業優先分配法」，並記下「常數是量出來的、換模型要重量」
- [x] 5.2 `tests/README.md`：加 design 對照表裡的那幾列

## 6. 驗收

- [x] 6.1 `.tox/unittest/bin/python -m unittest discover -s tests/<各組> -t .` 全綠；`.tox/flake8/bin/flake8 . --count` 為 0
- [x] 6.2 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify` 通過（集數 ＝ Kari-SRT 裡沒標 pending 的筆數）；`python3 -m scripts.news.name_catalogue --check` 通過
- [x] 6.3 拿一集實際跑 `python3 -m scripts.news.batches <slug>` 與 `python3 -m scripts.news.vision_tools.prompt <slug> 1`：確認**用系統 `python3`（沒有 PIL、numpy）跑得起來**、兩邊清單一致、各批預估量落在上限以內
- [x] 6.4 對一集重跑 `cues --sheets`，確認《開會了》的兩列拼回去（隨機抽幾條，降部接回自己的字母底下）、視覺 token 比現行少約 1.5%；族語新聞的組合圖逐畫素不變（張數、每張裝幾條、視覺 token 都一樣）
