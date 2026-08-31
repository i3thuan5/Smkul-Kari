# Design: recalibrate-news-gates

## Context

動機與數字見 proposal.md。約束：2021-01 批次即將切 cue，重校要趕在前面或平行；63 支存檔 mkv 在 `kithann/out/mkv/`（約 126G，離線可量）；機器 16 核，`verify_band` 單支實測 41 秒牆鐘、約 4 分鐘 CPU（ffmpeg 多執行緒）。`blank_runs.py`、`blind_cues.py` 兩檔同時在 restructure-news-pipeline 的讀取端清單內，修改要錯開時間以免互踩。

## Goals / Non-Goals

**Goals:**

- 三個門檻各自回答得出「幾集校的、用哪個量測法」，校準紀錄落在 repo 文件。
- news 側 verify_band 的失敗方向翻正：判「無紅帶」必留數值證據，不再安靜放行。
- blank_runs 能抓 006 型上方字幕（12 條短段），同時不誤報良性長空鏡。

**Non-Goals:**

- 不改 aiyalaeho 側 `verify_band`（那份判準不同，a9 的線）。
- 不引入新依賴——量測用既有 `cuelib` 串流與 numpy。
- `blind_cues` 不追求把兩類結構性漏抓變成可擋——實測證明 `spread` 判準誤報 63%，只能排序；契約止於「參數可調＋侷限記錄在案」。

## Decisions

### D1：全量重量後才定 SPIKE，不憑手感調

63 支 mkv 各跑一次現版量測（同一量測法：含 BUG_MARGIN），收集有紅帶／無紅帶兩群的比值分布，門檻取兩群間隙的中點並記錄邊界樣本。若兩群重疊（有紅帶樣本落到無紅帶群的範圍），SPIKE 單一比值判準不成立，改判準（例如紅帶色彩證據）再議——先量再說，這正是本 change 要建立的習慣。量測循序跑約 45 分鐘、nice 執行；輸出逐支一列（檔名、比值、判定），表格進 `scripts/news/README.md` 量測紀錄節。一次性掃描不新增模組，shell 迴圈呼叫既有 CLI 即可（裝得越少越好）。

### D2：blank_runs 的證據判準＝region 頂端切緣墨

上方字幕的可量特徵：字幕主體在 region 之上，region 只切到字形下緣——圖條**頂端數列**有墨、且墨在頂端邊界被截斷。從既有 strips（已在磁碟）離線量頂端 N 列的墨量與截斷形狀，超過證據門檻的 cue 列入人工複查。長度改為排序鍵。實測依據：006 病灶 12 條全部帶切緣墨、同集 13 條良性空鏡無。證據門檻本身也照 D1 的習慣：量 006（正例）與 054–059（負例）兩群再定，紀錄樣本數。

### D3：blind_cues 只參數化

`LONG` 提為 CLI 參數（預設 6.0 不變）。兩類結構性漏抓（短騎線 cue、5 秒藏 3 句）與 `spread` 誤報率 63% 的實測結論寫進模組 docstring 與 README——下一個想「加個判準」的人先讀到失敗紀錄。

## Risks / Trade-offs

- [量測期間吃 CPU 與批次搶資源] → nice 執行；挑切 cue 空檔或夜間；45 分鐘量級可接受。
- [兩群分布重疊、單比值判準不成立] → 這是量測的合法結論，不硬選新值；帶著分布數據回報使用者議改判準。
- [與 restructure-news-pipeline 撞檔] → 只有 `blank_runs.py`、`blind_cues.py` 兩檔重疊，兩邊修改錯開；本 change 不動 `paths.py`。
- [006 尚未入庫、正例樣本只有一集] → 證據門檻標記校準樣本數，之後批次遇新病灶再擴樣本重校——紀錄在案就能重校，這正是本 change 的主旨。

## Migration Plan

無資料遷移。程式改動三支各自獨立，可逐支上；門檻新值生效前先跑一次全量回測（63 支判定不變壞：原本 ok 的仍 ok、已知 news 負例仍擋下）。

## Open Questions

（無）
