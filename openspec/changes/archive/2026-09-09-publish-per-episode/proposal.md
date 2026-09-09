# 定版把關改以集為單位

## Why

`publish` 現在以**廣播月**為單位把關：該月只要有一集還沒完成，整個月都不寫。2021-01 有 59 集 pending、其中 58 集連 cue 都還沒切，所以 `20210106_006_午間_Cou_鄒` 明明已經切好、精修好、Claude Vision 讀完並驗證過（1,251 條 cue、745 行 SRT），它的時間軸卻進不了 `1-ocr/1-cues/`——那份時間軸目前**只存在於工作目錄**，而該集的母帶已經刪除、`out/mkv/` 也沒有它，工作目錄一旦清掉就再也生不回來。

整批把關原本的理由是「發布是對整批的宣稱，只發一半會讓 store 宣稱它握有其實沒有的交付物」。但那個顧慮在**逐集**的層次上並不成立：`publishable()` 本來就是逐集檢查（切過、精修過、讀完），`smkul.csv` 只列非 pending 的集，`rebuild --verify` 也只走非 pending 的集——每一集發布時都自帶它的交付物與輸入，沒有任何一集在替別集背書。

順帶修一個已存在的落差：2026-08-31 使用者裁定把把關單位從「整份 inventory」縮成「廣播月」，程式改了，spec 沒跟上。本 change 一併補正。

## What Changes

- **`publish` 的把關單位從廣播月改為單集**：每一集各自判斷能不能發布，完成的就寫，未完成的照現在的方式印出理由並跳過。同一個月裡未完成的集不再擋住已完成的集。
- **`gate()` 與 `months_of()` 的去留**：`main()` 不再需要月份層級的 hold；把它們留著（`gate()` 仍是「這些集為什麼還不能發」的查詢介面，`months_of()` 供報告分組），但不再參與是否寫入的決定。
- **「什麼都沒發」不再是失敗**：現行邏輯是「有 hold 而且沒有任何一集 ready 就回非零」。改成逐集之後，沒得發只代表還沒有集數完成，逐集的 `skip` 行已經說明原因，回 0。
- **《開會了》那支一起改**：`scripts/aiyalaeho/publish.py` 有同形狀的整批把關（`gate(entries)` → `if blocked: … return 1`），而被改的 requirement 是兩個語料共用的。只改新聞會讓 spec 說逐集、《開會了》的程式卻仍是整批。它目前 44 筆 0 pending，所以這一改在行為上是 no-op，純粹是讓 spec 與程式對齊。
- **不改的**：`publishable()` 的逐集判準、`publish_one()` 寫什麼、`clear_pending()`、`smkul.csv` 的內容規則、`rebuild --verify` 的範圍與行為，全部原樣。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `srt-data-store`：「store 只在整批完成時定版」這條要求「先檢查 inventory 內每一個 pending 集數是否已校讀完成，只要有任何一集未完成就以非零狀態結束、不寫入任何檔案」。改為逐集把關：每一集各自檢查，完成的寫入、未完成的跳過並指名，未完成的集不影響其他集。

## Impact

### Kari-SRT（資料）

跑 `publish` 之後會動三處：

- `news/1-ocr/1-cues/2021-01/20210106_006_午間_Cou_鄒.json` 新增（該集精修過的時間軸）。
- `news/inventory.json`：該集的 pending 旗標清掉。
- `news/smkul.csv`：從 74 列變 75 列。

其餘不動。`rebuild --verify` 之後要通過，且它驗的集數會從 74 變 75。

### scripts

- `scripts/news/publish.py`：`main()` 拿掉月份層級的 hold 與「有 hold 且無 ready 就回非零」那段；模組 docstring 與 `gate()` 的註解改寫（兩處目前都明文寫著整批把關的理由）。
- `scripts/aiyalaeho/publish.py`：`main()` 拿掉 `if blocked: … return 1`；模組 docstring 與 `gate()` 的註解同樣改寫。

### tests

`tests/news/test_publish_gate.py`：`TestGateByMonth` 的語意改為「月份不再是把關單位」；新增「同月有未完成的集不擋已完成的集」「未完成的集不會被發布且理由指名」「沒有任何集完成時不算失敗」。`TestClearPending`、`TestMonthsOf` 不變。`tests/aiyalaeho/test_publish.py`：新增對應的一條——未完成的集不擋已完成的集。

### 文件

`scripts/news/README.md` 與 `.claude/commands/smkul-news.md` 若有寫「整批才會定版」要跟著改。
