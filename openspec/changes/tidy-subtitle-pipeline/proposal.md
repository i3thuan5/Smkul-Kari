## Why

三個缺陷是同一種病理：**測試保護跟它要保護的對象對不上**，而且都不報錯——安靜地少做事，
或安靜地做錯事。同一批病理的第四個（`make_all.make_one` 的檢查順序）已於
`da2f0b3` 修掉，本次只補上它缺的規格與回歸測試。

同時有兩筆懸而未決的技術債：

1. `scripts/news/inventory.json` 是**衍生資料卻放在主 repo**，與 `Kari-SRT/inventory.json`
   並存。已封存的 srt-data-store spec 寫明「主 repo SHALL 只含程式、測試與文件」，
   且樹狀圖把 `inventory.json` 列在 store 之下。兩份現在逐字相同（各 35 筆），
   是遷移的最好時機——沒有任何進行中的批次狀態要保。
2. 量測已證明文稿路徑對「產生字幕」沒有淨幫助（4,344 個文稿供字的 cue 全部重讀，
   336 筆不符，**全部是畫面對、稿子錯**），但那 894 行程式仍站在主流程的預設位置上。

而 `scripts/subs2srt/cli.py` 累積到 1,397 行，下游模組必須 `import cli` 才拿得到
`merge_repeats()` 這種純函式——正是這種「參數靠手抄、前置檢查靠 `getattr` 補洞」的
結構孵出了上述缺陷。

離線重建（`rebuild --verify`）目前是綠的（35 SRTs + smkul.csv 逐 byte 相同），
逐 byte 保護著組裝路徑。趁它綠著動手。

## What Changes

### 一、`inventory.json` 遷入 Kari-SRT，成為唯一正本

`paths.INVENTORY` 指向 `Kari-SRT/inventory.json`，刪除主 repo 那份。14 處讀取端
（含 `run_cues.sh` 透過 `paths --var`）全部指向同一個檔。

批次進行中的集數以 **`pending` 旗標**標示：`add_episodes` 寫入時標記，`publish`
整批把關通過時清除。`rebuild` 與進度表列產生器**跳過 `pending` 集數**，於是
store 在批次進行中仍然自洽，`rebuild --verify` 全程可綠。

`pending` 與現有兩個欄位語意不重疊：`truncated`（來源不完整，永不交付）、
`partial`（已交付但來源短）、`pending`（本批還在做）。

### 二、三個缺陷：測試保護跟它要保護的對象對不上（全部靜默）

| 位置 | 現象 |
|---|---|
| `publish.py` | `cues/`、`from_rtf/` 逐集把關，`inventory.json` 卻無條件整份覆蓋。遷移後該行消失，改由「整批把關通過才清 `pending`、才定版 `smkul.csv`」承接同一個保證 |
| `subs2srt auto` | `stage_auto` 手抄 `argparse.Namespace` 時漏傳 `preset`／`presets`，`stage_cues` 用 `getattr(..., None)` 拿預設值 → **靜默改用自動偵測**，而自動偵測在這批素材上會把氣象圖與台標排在對白之上 |
| `vision_complete()` | 判準是 `len(verified) >= len(cues)`，只比數量不比編號集合。目前資料沒有多餘 key，屬理論風險，但既然要修就一併改成比集合 |

**已修、本次只補規格與測試**：`make_all.make_one` 曾把「有沒有 tesseract 草稿」
的檢查排在視覺辨識檢查之前，導致 13 集全部校讀完成卻回報「尚未辨識」、一個 SRT
都不產。`da2f0b3` 已把順序調正，但這條行為沒有規格也沒有回歸測試。

### 三、`smkul.csv` 的定版改由 `publish` 負責

`make_all` 逐集產 SRT，進度表寫進 `kithann/out/`（快取，列出含 `pending` 在內的
全部集數）；`publish` 整批把關通過、`pending` 清空後，才把 `smkul.csv` 定版進 store。

這是「進度表要看得到還沒做的」與「store 必須逐 byte 可重建」唯一不打架的擺法：
mid-batch 的「卡在哪一步」只存在於 work dir，而 `rebuild` 沒有 work dir，重建不出來。

`FIELDS`／`tracker_row()`／`write_tracker()` 抽成 `scripts/news/tracker.py`
供 `make_all`／`publish`／`rebuild` 三方共用（現在 `publish` 與 `rebuild`
都 `import make_all` 只為了拿這些）。

### 四、移除文稿（`align.py`）路徑

刪除 **894 行程式 ＋ 375 行測試**：`align.py`、`rtf.py`、`rtf_sheets.py`、
`compare_rtf.py`、`check_align.py`、`tests/align/`、`tests/rtf/`，以及
`make_srt.py`／`make_all.py`／`gap_sheets.py` 內的 rtf 分支。`--no-rtf` 的
行為成為唯一行為。

保留（附理由）：`inventory.json` 的 `文稿位置` 欄（`smkul.csv` 有這一欄，
而 `smkul.csv` 是逐 byte 比對的交付品）、`Kari-SRT/from_rtf/`、
`Kari-SRT/report/rtf-vs-vision.*`、`Kari-SRT/vision-rtf/`（重建必需）。
文件將註明刪除 commit，其 parent 即最後一個含比較程式的版本。

### 五、純重構（不改行為）

- `cli.py` 1,397 行拆成 `detect.py`／`sheets.py`／`ocr.py`／`assemble.py`／`cli.py`，
  下游改 `import assemble` 而非 `import cli`
- `make_all`／`rebuild`／`ingest` 的 subprocess 自呼叫改為直接 import，解除
  「stdout 最後一行必須是 JSON」這個隱形契約。拆完之後 `paths.VENV_PY`
  只剩兩支 shell 腳本在用，**本次不動它**（理由與後續選項見 design.md D6）

## Capabilities

### New Capabilities
- `subtitle-text-source`: 交付字幕的文字從哪裡來、什麼條件下才算可供字。涵蓋
  「只有經人校讀的視覺辨識可供字」、文稿不再供字、「中間產物不得阻擋已完成的交付」
  （`da2f0b3` 已實作，本次補規格與回歸測試），以及「字幕帶區域必須由呼叫端指定、
  不得靜默退回自動偵測」——後者的失敗後果同樣是錯的文字。

### Modified Capabilities
- `srt-data-store`: store 的一致性契約收緊。明定 `inventory.json` 的正本在 store、
  主 repo 不得有副本；新增 `pending` 標記與「重建驗證跳過 pending」、「store 只在
  整批完成時定版」、「進度表由遷移流程定版」、「完成判準比對編號集合」四條要求；
  原規格寫死的「22 集」改為隨批次成長。

## Impact

**程式**：`scripts/subs2srt/`（cli.py 拆檔）、`scripts/news/`（刪 5 支、新增
`tracker.py`、改 `paths`／`add_episodes`／`build_inventory`／`publish`／`rebuild`／
`make_all`／`gap_sheets`／`make_srt`／`ingest`／`batches`）

**資料**：`scripts/news/inventory.json` 從主 repo 刪除（內容已與 store 那份逐字相同，
無資料遷移）；`Kari-SRT/inventory.json` 的條目新增可選的 `pending` 鍵

**測試**：刪 `tests/align/`、`tests/rtf/`；`tests/subs2srt/` 隨拆檔改 import；
新增 pending 語意、publish 整批把關、`make_one` 判斷順序（回歸）、`auto` 參數傳遞、
`vision_complete` 集合判準、`ingest` 直接呼叫六組測試

**文件**：`scripts/news/README.md`、`.claude/commands/smkul-news.md`、
`.claude/skills/video-subtitle-srt/`（文稿章節改為指向刪除 commit）、
`CLAUDE.md`（若補 tox fallback 指令）

**驗收**：每階段跑 `tox -e subtitle`＋`tox -e subtitle-rebuild`＋`tox -e flake8`。
`rebuild --verify` 必須全程保持綠。

**風險**：遷移後 `build_inventory.py` 會整份重寫 store 的正本（它掃的是本機資料夾，
而該掛載點已不存在），必須加防護；`ingest` 的 subprocess 拆除處目前無測試覆蓋，
拆除前須先補。
