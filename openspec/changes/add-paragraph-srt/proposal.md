## Why

族語新聞平行語料（`2-asr-whisper/2-平行語料/`）每一組的開始、結束時間，取的是「組內語音段與華語字幕的最早到最晚」。華語字幕換句的時間跟族語語音分段本來就對不齊，所以：

- 相鄰兩組的時間會重疊（2021 年 1–2 月 133 集共 5,393 處）：一條字幕整條歸給一組，它的頭或尾伸進隔壁組的語音。
- 組的時間會被字幕拉長，最多 35 秒（例：20210224_055 撒奇萊雅「對於醫療能有更多的選擇」在配樂空檔掛 27.6 秒）。

翻譯模型只用文字，不受影響；但第二期第一批補件已把這些組做成雙語字幕 SRT 交出去，SRT 的時間若要給語音模型用，聲音的範圍就必須框住族語、不能框進隔壁組的話或配樂。CLAUDE.md 的 0.5 秒留白規定，本來也是為了聲學邊界。

另外量到配對本身的一個缺口：一條很長的字幕蓋住好幾段很短的語音時，中間那幾段各不到字幕長度的 10%，被丟出組外，卻落在這一組的時間範圍裡（133 集 91 組、123 段）。組的時間改成族語語音段之後，這些組的範圍裡會有聲音、文字卻少了那幾段。

雙語字幕 SRT 目前只存在 `kithann/out/`，不在 Kari-SRT、也不受 `rebuild --verify` 把關；它已經是交付物，正本應該在 Kari-SRT。

## What Changes

- **組的時間改成族語語音段**：開始、結束時間以組內 sapolita 語音段的最早開始與最晚結束為準，不再算進華語字幕的時間。配對規則（字幕歸重疊最多的段、合併門檻 10%）不變。改後相鄰組不再重疊。
- **CSV 的時間也延伸 0.5 秒**（使用者裁定 2026-10-16）：跟 SRT 一樣前後各延伸 0.5 秒，太近就中點相接；鄰居是整集全部的語音段，不採用的組、落單段都一起延伸。CLAUDE.md〈SRT 產出規定〉的「留白只影響 SRT 輸出」改成也涵蓋這份 CSV 的時間。
- **先配對、後延伸**：配對、補洞、校正基準的前 90 秒都用真實邊界，延伸只在輸出時間上做。先延伸再配對的話，133 集組數 15,751 → 12,927、留下的族語詞少 1.9%、組長中位數 16.7 → 20.4 秒，而且 10% 的調參、開會了標準答案、校正基準都要重做（使用者裁定：段落越短越好）。
- **補洞**：一組的第一段到最後一段語音之間、沒有歸進任何組的語音段，補進這一組。組外的落單語音段不動。
- **校正基準的「前 90 秒」**改用族語語音的真實開始時間，不用 CSV 上延伸後的時間（656 集只有 2 組跨線，重算只差泰雅 0.0002）。凍結的 `校正基準.csv` 不重算。
- **BREAKING：目錄改名** `2-asr-whisper/2-平行語料/` → `2-asr-whisper/2-csv-analysis/`，跟整條線「格式-內容」的命名一致（`1-srt-sapolita`、`2-csv-analysis`、`3-srt-paragraph`）。舊目錄還在時，產出與重建 SHALL 指名中止，避免兩份並存。
- **新增資料層** `2-asr-whisper/3-srt-paragraph/<年-月>/<成果檔名>.srt`：從 CSV 挑高、中信心的組，「族語：」「華語：」兩行，時間就是 CSV 那一列的時間（已含延伸），不另外重算。跟 CSV 由同一輪產出，納入 `rebuild --verify` 與包含規則。
- **片頭辨識改語別**時，`3-srt-paragraph/` 跟 `2-csv-analysis/` 一起刪除等重跑。
- **交件與抽查**：`scripts/news/bilingual_srt.py`（第二期第一批補件時先寫的）拆掉；SRT 改由正式管線產生，交件時的複製、一集一列清單、高信心抽查搬到 `scripts/news/paragraph_export.py`。清單不進 Kari-SRT。
- 補洞後重跑《開會了》標準答案量測，更新 README 的對齊正確率；合併門檻的調參不重做，README 註明調參是補洞前量的。
- 已交出去的 `kithann/驗收/第2-1期/補件內容/新聞/` 是舊時間的快照，不動；下一批交付用新版。

## Capabilities

### New Capabilities

（無；雙語字幕併入 `whisper-parallel-corpus`，它是同一組配對的另一種輸出。）

### Modified Capabilities

- `whisper-parallel-corpus`：組的時間只看語音段、再延伸 0.5 秒（鄰居是全部語音段）；配對與補洞用真實邊界；校正基準的前 90 秒用真實語音開始時間；CSV 路徑改名；新增雙語字幕 SRT（從 CSV 挑高中信心、時間與 CSV 相同）。
- `srt-data-store`：store 結構加上 `2-csv-analysis/`、`3-srt-paragraph/`；包含規則改名並加上 `3-srt-paragraph/ ⊆ 2-csv-analysis/`；離線重建涵蓋 `3-srt-paragraph/`；舊目錄名不可存在。

## Impact

- **程式**：`scripts/mt/overlap.py`（補洞、span 只看語音段）、★`scripts/mt/paragraph_srt.py`、`scripts/news/paths.py`、`pairs_run.py`、`rebuild.py`、`relabel.py`、★`paragraph_export.py`、✖`bilingual_srt.py`；`scripts/mt/pairs.py`、`features.py`、`tuning.py` 經由 `overlap` 間接受影響；`tools/mtgold/sweep.py` 不改、重跑一次。
- **測試**：`tests/mt/` 的 overlap、pairs、run，★paragraph_srt、★paragraph_export（取代 bilingual_srt）；`tests/news/` 的 paths、rebuild_pairs、relabel。
- **資料**：Kari-SRT 656 集 CSV 重產（時間兩欄全變，且 CSV 重建多一個輸入：辨識紀錄.csv 的音長秒；91 組的族語、語音段數、可能還有信心層級會變）、656 集 SRT 新增、目錄改名，submodule 會有一大包 diff。
- **文件**：CLAUDE.md〈SRT 產出規定〉（已改）；Kari-SRT 的 `README.md`、`news/2-asr-whisper/README.md`、`2-csv-analysis/README.md`、★`3-srt-paragraph/README.md`；`scripts/README.md`、`scripts/mt/README.md`、`tests/README.md`、`tests/mt/README.md`。
- **平行 session**：每輪跑 whisper 的那條線會呼叫 `pairs_run`；改名那一刻那條線若正在跑，會寫到舊路徑，apply 時要挑它沒在跑的空檔。
