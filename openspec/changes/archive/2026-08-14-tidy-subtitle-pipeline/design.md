## Context

見 proposal.md — Why。這裡只記形塑做法的現況與限制。

**寫這份文件時的實測狀態**：

```
rebuild --verify        OK: 35 SRTs + smkul.csv rebuilt byte-identical
Kari-SRT HEAD           8fef982，working tree 乾淨
兩份 inventory          各 35 筆，逐字相同（0 差異）
進行中的批次            無
```

**但這是快照，不是前提。** 使用者會同時開多個 session 動同一個 repo，隨時可能在
抓新的月份、切 cue、校讀、commit `Kari-SRT`。本次重構期間集數從 35 變成 48 是
完全可能的，而且不該需要重寫計畫。

因此本設計有一條貫穿的規則：**驗收標準一律用推導的，不用記錄的常數。**
「跟基準一樣是 35 集」會在別人做完一批之後變成假紅燈；「`rebuild --verify` 通過，
且集數等於 store inventory 中非 pending 的筆數」則永遠成立。這跟本次要修的三個
缺陷是同一種錯誤——把一個當時為真的假設寫死，環境一變就靜默失準。

**唯一的強安全網是 `rebuild --verify`**：它只用 Kari-SRT 的 `cues/` + vision TSV
離線重組全部交付 SRT 與 `smkul.csv`，逐 byte 比對。但它的覆蓋範圍是**組裝路徑**，
不是整條 pipeline：

| 程式 | `rebuild --verify` | 單元測試 |
|---|---|---|
| `cuelib` 的 SRT 輸出（`render_srt`／`srt_timestamp`） | ✓ 逐 byte | ✓ |
| `cli.merge_repeats`／`apply_gap_rules`／`parse_transcript_tsv` | ✓ 逐 byte | ✓ |
| `make_srt` 全部（`build`／`drop_leader`／`entries_from`／`write_srt`） | ✓ 逐 byte | ✓ 部分 |
| `make_all.tracker_row`／`write_tracker` | ✓ 逐 byte | ✓ |
| `rebuild.episode_transcripts`／`check_inputs` | ✓（它自己） | — |
| `cli.detect_band`／`region_from_profile`／`split_lines` | ✗ | 部分 |
| `cli.build_sheets`／`flush_sheet`／`ink_bbox` | ✗ | ✓ |
| `cli.ocr_*`／`prep_for_tesseract` | ✗ | ✓ 部分 |
| `cli.stage_*`（全部 9 個） | ✗ | **✗** |
| `ingest`／`publish`／`add_episodes`／`gap_sheets`／`verify_band` | ✗ | 部分 |

第二個限制：`tox` 本身不在這台機器的 PATH 上，只剩 `.tox/*/bin/` 的 venv。

## Goals / Non-Goals

**Goals:**
- 每一個階段結束時 `rebuild --verify` 都是綠的——包含階段之間，也包含未來
  批次進行到一半的時候
- 純搬移與行為修改分開 commit，紅燈時能立刻分辨是哪一種造成的
- 修掉的每個缺陷各自留下一條會紅的測試；`da2f0b3` 已修的那個補上回歸測試

**Non-Goals:**
- 不改 `cuelib.py`（分區清楚、覆蓋率高，動它沒有淨收益）
- 不改任何 SRT 的內容——本次全部改動對 `Kari-SRT/srt/` 應為零 diff
- 不改 `inventory.json` 既有欄位（`文稿位置` 留著，理由見 D4），只新增可選的 `pending`
- 不動 `paths.VENV_PY`（理由見 D6）
- 不碰 `migrate_kari.py`（一次性、已跑完）

## Decisions

### D1 — `inventory.json` 遷入 store，批次進行中的集數以 `pending` 標記

`paths.INVENTORY` 指向 `Kari-SRT/inventory.json`，主 repo 那份刪除。內容已逐字
相同，所以是純粹的路徑改動，沒有資料遷移。

**這會直接消滅一個缺陷**：`publish.py:86` 的 `copy2(本機 inventory → store)`
整行不存在了。兩份不可能不同步，因為只有一份。

**新張力**：`add_episodes` 必須在 `gap_sheets`／`batches`／`ingest` 之前跑（後三者
要靠 inventory 查每集的 `srt_name`），所以一登記，store 就宣告了還沒做完的集數。
解法是 `pending` 旗標——**`rebuild` 與 tracker 列產生器都跳過它**。

時序推演，證明全程綠：

| 時點 | store inventory | store `smkul.csv` | rebuild 重建出 | |
|---|---|---|---|---|
| 現在（上批已定版） | 35 筆，0 pending | 35 列 | 35 列 | ✓ |
| `add_episodes` 登記新 13 集 | 48 筆，**13 pending** | 35 列（未動） | 35 列（跳過 pending） | ✓ |
| 校讀中，跑 `make_all` | 48 筆，13 pending | 35 列（未動） | 35 列 | ✓ 快取進度表列 48 列 |
| `publish` 整批把關通過 | 48 筆，**0 pending** | 48 列 | 48 列 | ✓ |

三個標記語意不重疊，缺一不可：

| 標記 | 意思 | rebuild | tracker |
|---|---|---|---|
| `truncated` | 來源根本不完整，永不交付 | 跳過 | 列出，狀態「略過：…」 |
| `partial` | 已交付，但來源短缺 | **驗** | 列出，狀態後接註記 |
| `pending` | 本批還在做 | 跳過 | **不列** |

考慮過的替代方案：
- *兩份檔案：store 只含已交付，工作中的放 `kithann/`* — 讀取端要讀聯集，多一個
  檔案與一層邏輯。使用者選了單檔加旗標。
- *`rebuild` 放寬，只驗 store 裡有 SRT 的集數* — 等於拆掉它偵測「宣告了卻沒有」
  的能力，而那是它最有價值的地方。`pending` 是**顯式宣告**「這集我知道還沒好」，
  跟「靜默跳過缺件」不同。否決。
- *延後到批次結束才 `add_episodes`* — `batches`／`ingest` 需要 `srt_name` 查表，
  做不到。

**附帶必須處理的**：遷移後 `build_inventory.py` 會整份重寫 store 的正本（它掃的是
`CORPUS/2月`，而該掛載點在當前環境已不存在，且它會刪掉 `add_episodes` 登記的
一切）。改為合併式，或要求明示旗標才整份重寫。

### D2 — `smkul.csv` 的定版從 `make_all` 移到 `publish`

即使 inventory 只剩一份，這一步仍然需要——原因不是兩份不同步，而是**可重建性**：

```
mid-batch 的狀態字串（「待處理（尚未切cue）」等）由 work dir 決定
rebuild 沒有 work dir
→ 重建不出來 → 逐 byte 比對必然失敗
```

所以 mid-batch 的進度表只能是快取。分工：

```
make_all   逐集 →  Kari-SRT/srt/*.srt              多一個 SRT 不影響 rebuild
           進度表 →  kithann/out/smkul.csv          列全部含 pending，給人看
publish    整批把關通過 → 清 pending
                      → Kari-SRT/srt/smkul.csv     定版，只列非 pending
                      → cues/、from_rtf/
rebuild    從 store 重建，跳過 pending，逐 byte 比
```

配套：`FIELDS`／`tracker_row()`／`write_tracker()` 抽成 `scripts/news/tracker.py`。
現在 `publish` 與 `rebuild` 都 `import make_all` 只為了拿它們，抽出來三方對等。

### D3 — 三個缺陷的修法（第四個已修，補規格與回歸測試）

| 位置 | 修法 | 為什麼是這樣 |
|---|---|---|
| `publish` | 先跑一輪整批把關（每個 pending 集數皆須校讀完成），全數通過才寫任何檔案 | 部分寫入必然讓 store 進入自己的驗證抓得到的不一致 |
| `stage_auto` | 不再手抄 Namespace，改由 `vars(args)` 衍生後覆寫必要欄位 | 手抄清單每加一個參數就要記得同步一次，這次漏的是 `preset`；換成衍生就結構性消滅這類漏抄 |
| `vision_complete` | 改比編號集合 | 數量相等不蘊含集合相等 |

`stage_auto` 另加一條**結構性測試**：斷言 `auto` 子命令的參數集合 ⊇ `cues` 子命令的
參數集合，且每一個都真的傳到下游。這條在未來加參數時會自動生效。

`make_all.make_one` 的檢查順序已由 `da2f0b3` 修正（視覺辨識分支移到 tesseract 草稿
檢查之前）。本次只補上兩樣它缺的東西：`subtitle-text-source` 的規格，以及一條
回歸測試——「無 `.work/transcripts.json` 但 `.B.work` 校讀完成時應產 SRT」。

### D4 — 刪除文稿路徑的邊界

刪：`align.py`(438)、`rtf.py`(124)、`rtf_sheets.py`(89)、`compare_rtf.py`(150)、
`check_align.py`(93)、`tests/align/`(238)、`tests/rtf/`(137)，以及
`make_srt`／`make_all`／`gap_sheets` 內的 rtf 分支。

**留**（各有理由，不是猶豫）：

| 留什麼 | 為什麼 |
|---|---|
| `inventory.json` 的 `文稿位置` 欄 | `smkul.csv` 有這一欄，而 `smkul.csv` 逐 byte 比對。刪欄就得重簽整份交付品 |
| `Kari-SRT/from_rtf/` | 「哪些 cue 曾由文稿供字」的歷史索引，是比對報告的鑰匙。`rebuild` 不讀它，留著零成本。新集數不再產生（永遠 `[]`） |
| `Kari-SRT/report/rtf-vs-vision.*` | 目前唯一能證明視覺辨識可信的證據（4,344 行、92.3% 一致，且不一致處有系統性解釋） |
| `Kari-SRT/vision-rtf/` | `rebuild.episode_transcripts` 會讀，離線重建必需 |

**這一刀有安全網**：`rebuild` 呼叫 `make_srt` 時不帶 `--rtf`，aligner 完全不
參與離線重建。刪掉之後 `rebuild --verify` 應原地保持綠——若變紅，就是刪過頭了。

文件處理：`README.md` 與 `.claude/` 相關章節改寫為「已於 commit `<sha>` 移除，
其 parent 是最後一個含比較程式的版本」。`<sha>` 在刪除 commit 建立後回填。

### D5 — `cli.py` 的拆法

純搬移，不改一個字元的邏輯。邊界依「這段程式回答什麼問題」切：

| 新檔 | 內容 | 約行數 |
|---|---|---|
| `detect.py` | 決定要切哪塊像素：`load_presets`、`match_preset`、`detect_band`、`region_from_profile`、`merge_bands`、`split_lines`、`probe_or_die`、`grab_frame`、`grab_burst`、`stable_text_mask` | ~290 |
| `sheets.py` | `LABEL_FONT`、`ink_bbox`、`build_sheets`、`flush_sheet` | ~130 |
| `ocr.py` | `TESS_COMMON`、`prep_for_tesseract`、`run_tesseract`、`clean_text`、`ocr_tesseract`、`ocr_claude_api`、`default_prompt` | ~180 |
| `assemble.py` | `read_manifest`、`load_transcripts`、`merge_repeats`、`apply_gap_rules`、`parse_transcript_tsv`、`glossary_tokens`、`SPECIAL_MARKS`、`VERIFIED_NAME`、`load_verified`、`save_verified`、`import_tsv`（見 D6） | ~200 |
| `cli.py` | 9 個 `stage_*` ＋ `build_parser`／`add_*_options`／`main` | ~600 |

`cuelib.py` 不動。下游改 `from scripts.subs2srt import assemble`（`make_srt`）
與 `import sheets`（`gap_sheets`），不再 `import cli`。

### D6 — subprocess 自呼叫的拆法，以及 `VENV_PY` 本次不動的理由

三處 Python 對 Python 的 subprocess 呼叫全部改直接 import：

| 現在 | 改成 |
|---|---|
| `make_all.make_one` → `run([PY, "-m", "scripts.news.make_srt", ...])`，parse stdout 最後一行 JSON | `make_srt.run(work, out) -> qc dict` |
| `rebuild.rebuild_one` → 同上 | 同上 |
| `ingest.main` → `run([PY, "-m", "scripts.subs2srt.cli", "import", ...])` | `assemble.import_tsv(work, path, replace=False)` |

`make_srt.main()` 拆成 `run()`（回傳 dict）＋ `main()`（argparse、印 JSON、寫
`.qc.json`）。stdout 格式對人保持不變，但不再是程式之間的契約。

**`paths.VENV_PY` 本次一行都不改。** 拆完之後它只剩兩個使用者：

```
現在                      本階段之後
ingest.py    → VENV_PY    直接 import，不需要任何直譯器路徑
make_all.py  → VENV_PY    直接 import
rebuild.py   → VENV_PY    直接 import
fetch_sftp.sh → VENV_PY   ← 只剩這兩支
run_cues.sh   → VENV_PY   ←
```

「`tox -e subtitle-rebuild` 在 tox venv 裡跑 rebuild、卻用另一個直譯器跑
make_srt」這個問題，**光靠上表三列就解決了**，與 `VENV_PY` 怎麼寫無關：拆完
之後 `rebuild` 全程在同一個直譯器內完成。

剩下的「shell 要拿哪個直譯器」是環境／部署問題，不是本次要修的架構問題。混
進來會讓那個階段的 diff 同時含「拆架構」與「改部署」，紅燈時分不出是哪個。

**曾經考慮、已撤回的方案**：讓 `VENV_PY` 解析而非寫死，順序
`$SUBS2SRT_PYTHON` → `~/.venvs/subs2srt/bin/python` → `sys.executable`。
查證後發現這是錯的：shell 是用 `/usr/bin/python3 -m scripts.news.paths` 去問
路徑的，所以 `sys.executable` 就是 `/usr/bin/python3`，而它**沒有 numpy**
（實測）。這條 fallback 會在 venv 不見時交出一個跑不動的直譯器，然後在
`fetch_sftp.sh:145` 跑 `cli cues` 時才炸——也就是下載完 2 GB 影片之後。比現況
（bash 立刻報 no such file）更晚、更難懂，正是本次要修的那種病理。

**留給後續 change 的選項**（不在本次範圍）：

| | 做法 | 評語 |
|---|---|---|
| 驗證式 | `paths` 逐一驗候選能否 `import numpy, PIL`，全掛就 exit 非零說怎麼修 | 把失敗從「下載完才炸」提前到「腳本第 23 行」。小、安全，但只是早炸 |
| devcontainer 根治 | `postCreateCommand` 建 venv、`remoteEnv.PATH` 前置它，shell 全改用 `python3`，`VENV_PY` 刪除 | **推薦的後續**。現在 `postCreateCommand` 只裝 openspec、完全沒有 Python 設定，venv 是手建的——這正是 README 記載的「devcontainer 重建一次就掉光」。不污染系統 python |
| 打包 | `pyproject.toml` ＋ `pip install -e .`，shell 叫 `subs2srt cues` | 最正規，但 `tox.ini` 現在 `skipsdist = True`，會牽動 CI 五個 env；且沒解掉「重建就掉」 |

### D7 — 階段順序按安全網強度排，不按重要性

```
階段 0  tracker.py 抽出 + smkul.csv 搬家    ← 先讓安全網在整段重構期間都能綠
階段 1  inventory 遷入 store（純搬檔）       ← 兩份逐字相同，是純路徑改動
階段 2  pending 語意 + publish 整批把關       ← 行為改動，可測
階段 3  另兩個缺陷 + make_one 回歸測試        ← 行為改動，可測
階段 4  刪文稿路徑（894 + 375 行）           ← rebuild 保護
階段 5  拆 cli.py（純搬移）                  ← rebuild 保護 assemble，其餘靠單元測試
階段 6  拆 Python 內部的 subprocess          ← rebuild 保護 make_srt 兩處
```

每階段結束跑三件事：`tox -e subtitle`、`tox -e subtitle-rebuild`、`tox -e flake8`。

階段 1 與 2 分開的理由跟階段 4 與 5 分開一樣：搬移與行為改動混在同一次改動，
紅燈時分不出是搬錯位置還是語意寫錯。

### D8 — 與平行 session 共存

重構期間別的 session 可能隨時在做影片。階段分成兩段對待：

| | 階段 | 與新批次的關係 |
|---|---|---|
| **需要協調** | 0–2 | `pending` 機制還沒建好。這期間若有人跑 `add_episodes`，新集數會以「已交付」的身分進 inventory，`rebuild --verify` 立刻紅；階段 1 更會刪掉一個別人正在寫的檔 |
| **可並行** | 3–6 | 只動程式。新批次照 `pending` 走，兩邊互不干擾 |

所以：**階段 0、1、2 要連續做完，中間不要停**，而且開工前跟使用者確認這段期間
不開新批次。階段 2 一落地，`pending` 就接手，後面四個階段可以跟做影片並行。

每一組開工前先跑：

```bash
git log --oneline -1
git -C Kari-SRT log --oneline -1 && git -C Kari-SRT status --short
```

若與上一組結束時不同，先重讀受影響的檔案再繼續——不要沿用記憶中的內容。

階段 1 另加一道實質前置檢查（tasks 1.1）：兩份 inventory 必須逐字相同，且沒有
任何集數處於「已登記但未校讀完成」。不符就是有人正在做，停下來協調，不要硬刪。

## Risks / Trade-offs

**[平行 session 隨時可能在做影片]** 集數、`Kari-SRT` HEAD、`rebuild --verify` 的
輸出都會在重構期間變動 → 驗收一律推導不記錄（見 Context）；階段 0–2 連續做完並
事先協調，階段 3 之後靠 `pending` 共存（見 D8）。**階段 1 刪 `scripts/news/inventory.json`
是唯一會毀掉別人工作的一步**，前置檢查不可略過。

**[遷移後 `build_inventory.py` 會整份重寫 store 正本]** 它掃 `CORPUS/2月`，而該
掛載點在當前環境已不存在（實測 `No such file or directory`）；就算存在，整份重寫
也會刪掉 `add_episodes` 登記的一切 → 階段 1 必須同時加防護（合併式或明示旗標），
不能等到階段 6 的文件標註。

**[`pending` 可能被誤用來繞過缺件檢查]** → 規格明文要求「未標記 pending 的集數
缺件時仍須失敗」；`publish` 清除 pending 前必先驗校讀完成，這兩道合起來讓
`pending` 只能是「登記中」而不能是「永久豁免」。

**[階段 6 會動到 `ingest`]** `ingest` 呼叫 `cli import` 那段目前**沒有測試覆蓋**
（`tests/news/test_ingest.py` 只測 `normalise` 與編號驗證）→ 拆除前先補一條端對端
測試：造一個小 work dir，跑 `import_tsv`，斷言 `transcripts.json` 與 `verified.json`
的內容。

**[階段 5 拆的東西多數沒有逐 byte 保護]** `detect_band`／`split_lines` 只有部分
單元測試，`stage_*` 完全沒有 → 嚴格純搬移：不改名、不改預設值、不「順手改進」。
搬完用 `git diff --stat` 確認新舊檔案行數合計與原檔一致（誤差只該來自 import 行）。

**[刪除文稿路徑不可逆]** → 刪除本身是一個獨立 commit，其 parent 即完整版本；
`README.md` 記下 sha。`Kari-SRT/report/` 的比對結論已經是文字紀錄，不依賴程式。

**[`vision_complete` 改嚴可能讓目前判為完成的集數變成未完成]** → 寫這份文件時已用
唯讀檢查掃過當時全部 35 集，沒有任何一集的校讀紀錄含有多餘編號。**但期間可能有新
批次進來**，所以這條檢查要在階段 3 動手前**重跑一次**，而不是引用這裡的結論。

## Migration Plan

`scripts/news/inventory.json` 刪除前先確認與 `Kari-SRT/inventory.json` 逐字相同
（目前已實測相同），所以沒有資料遷移，只有路徑改動。

其餘無資料遷移。`Kari-SRT` 是 git submodule，本次改動對它的 `srt/`、`cues/`、
`vision*/` 應為**零 diff**；`inventory.json` 只在階段 2 之後可能出現新增的
`pending` 鍵。若 `git -C Kari-SRT status` 在階段 0–1 出現任何改動，就是有非預期的
行為變化，停下來查。

回退：每階段一個 commit，`git revert` 即可。`Kari-SRT` 若被意外寫入，
`git -C Kari-SRT checkout -- .` 復原。

## Open Questions

- `migrate_kari.py`（331 行、一次性、已跑完）搬進 `scripts/news/oneoff/` 還是
  原地在 docstring 標註即可？兩者都不影響其他任何東西，實作時順手決定。
- `CLAUDE.md` 的驗收指令要不要補一行「tox 不在 PATH 時用 `.tox/<env>/bin/python`」
  的 fallback。純文件，可最後再決定。
