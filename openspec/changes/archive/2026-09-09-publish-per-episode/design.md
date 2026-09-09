# Design

## Context

動機見 proposal.md〈Why〉。

`scripts/news/publish.py` 目前的 `main()` 分兩段：先對每個廣播月呼叫 `gate(entries, month)` 算出 `held`，再走一次 inventory，凡是所屬月份在 `held` 裡的就 `continue`。`publishable(entry)` 本來就是逐集判準（切過沒、精修過沒、Claude Vision 讀完沒），月份那一層是疊在它上面的第二道。

`gate()` 的註解記著它為什麼是整批的：「it clears the pending flags and writes the tracker, and both are claims about the batch」。

## Goals / Non-Goals

**Goals**

- 已完成的集不被同批未完成的集擋住。
- 寫入之後 store 仍然自洽——`rebuild --verify` 通過。
- 補上 spec 與程式之間既有的落差。

**Non-Goals**

- 不動 `publishable()` 的逐集判準，一條都不放寬。
- 不動 `publish_one()`、`clear_pending()`、`smkul.csv` 的內容規則。
- 不動 `rebuild --verify`。

## Decisions

### D1 — 拿掉月份那一層，逐集判準原封不動

`main()` 不再算 `held`，也不再因為月份而 `continue`。每一集走 `publishable(entry)`：有 `reason` 就印 `skip` 並跳過，沒有就發布。程式其餘部分不動。

**為什麼這樣仍然自洽**：整批把關要防的是「store 宣稱它握有其實沒有的交付物」。但那個宣稱是逐集成立的——`publishable()` 已經要求該集切過、精修過、讀完；`smkul.csv` 由 `tracker.tracker_rows()` 產生，它只列非 pending 的集；`rebuild --verify` 也只走非 pending 的集。發布一集只是把那一集從「pending」移到「已交付」，同時把它的輸入放進 store，其他集的狀態一個字都沒變。**沒有任何一集在替別集背書**，所以拆到單集不會產生半真半假的宣稱。

*替代案*：保留月份把關，另加一個 `--only <srt_name>` 的例外口。否決——那等於把「什麼時候可以破例」變成呼叫端的判斷，而破例的條件其實就是 `publishable()` 已經在做的檢查，多開一個口只是讓同一件事有兩套判準。

### D1b — 《開會了》那支一起改，因為 requirement 是共用的

被改的 `srt-data-store`「store 只在整批完成時定版」沒有語料前綴（有前綴的都寫明「aiyalaeho ...」），而且它自己的一個 scenario 講的是《開會了》的字幕版型異常集。`scripts/aiyalaeho/publish.py` 的把關是同一個形狀（`gate(entries)` → `if blocked: … return 1`）。只改新聞會讓 spec 說逐集、那支程式仍是整批——正是本 change 要修的那種落差。

它目前 44 筆 0 pending，所以這一改在行為上是 no-op。之所以還是要改，是不要留下一個「下次有 pending 時才會發現」的不一致。

### D2 — `gate()` 與 `months_of()` 留著，但不再決定是否寫入

`gate()` 仍然是「這些集為什麼還不能發」的查詢介面，`--check` 與報告都用得上；`months_of()` 供依月份分組的報告。把它們刪掉會連帶砍掉現有測試涵蓋的行為，而它們本身沒有錯，錯的只是 `main()` 拿它們當寫入的閘門。

### D3 — 「什麼都沒發」回 0

現行是 `if held and not ready: return 1`。逐集之後沒有 `held` 這個概念了；沒有任何一集完成只代表這一批還在做，每一集的 `skip` 行已經說明卡在哪。回非零會讓批次腳本把「還沒輪到」誤判成失敗。

## 檔案樹

```
scripts/news/
  publish.py            改：main() 拿掉 held 與月份 continue、拿掉 return 1；docstring 與 gate() 註解改寫
scripts/aiyalaeho/
  publish.py            改：main() 拿掉 if blocked → return 1；docstring 與 gate() 註解改寫
tests/news/
  test_publish_gate.py  改：月份不再是把關單位；加三條逐集行為
tests/aiyalaeho/
  test_publish.py       改：加一條——未完成的集不擋已完成的集
```

## spec × scenario × 測試檔對照表

| spec | scenario | 測試檔 |
|---|---|---|
| srt-data-store | 未完成的集不擋已完成的集 | `tests/news/test_publish_gate.py` |
| srt-data-store | 一集都沒完成時不算失敗 | `tests/news/test_publish_gate.py` |
| srt-data-store | 字幕版型異常集不必等其他集 | `tests/news/test_publish_gate.py` |
| srt-data-store | 寫入後 store 自洽 | `rebuild --verify`（驗收步驟，非單元測試）|

scenario 要防的具體情形：

- 同月有 58 集沒切 cue，把 1 集已完成的擋住——這正是 006午 現在的處境，它的時間軸只存在於工作目錄，而母帶已刪、`out/mkv/` 也沒有它。
- 未完成的集被順手一起發布：`publishable()` 的 `reason` 若沒有真的擋住它，store 會多一份沒有 SRT 的時間軸，`rebuild --verify` 才會抓到。
- 一批全新、一集都還沒完成時回非零，讓批次腳本把「還沒輪到」誤判成失敗。

## Risks / Trade-offs

- **失去「整批一起定版」的節奏** → 那個節奏本來就不是資料完整性的必要條件（見 D1）；要看批次做到哪，工作區的 `smkul.csv` 快取版本本來就併列 pending 集與其進度。
- **`smkul.csv` 會更常變動**（每發一集就重寫一次）→ 內容仍然只由「非 pending 的集」決定，逐 byte 可重建，`rebuild --verify` 照樣比得出來。

## Migration Plan

1. 先寫測試（紅）：三條逐集行為。
2. 改 `main()`（綠）。
3. `tox -e unittest`（`tests/news`）、`tox -e flake8`。
4. `publish --check` 看它列出哪些集會被寫。
5. `publish`，然後 `rebuild --verify`——驗的集數應從 74 變 75。
6. `name_catalogue --check`。

回退：`git restore scripts/news/publish.py` 即回到月份把關；已寫進 store 的檔由使用者用 git 決定去留。
