# 重組字幕抽取 pipeline 的程式、資料與測試

## Why

字幕抽取工作已全部完成（22 集、20,108 個 cue 全由視覺辨識供字），但成果散落在
歷史遺留的位置：程式一半在 `ilrdf-srt/`、一半在 `.claude/skills/` 裡；14 處
絕對路徑寫死；約 20M tokens 換來的逐字稿 TSV 跟程式混在同一目錄；時間軸
`cues.json` 埋在 15G 的未 commit work dir 裡——今天 `rm -rf kithann/out`，
光靠 git 拼不回任何一個 SRT。趁工作告一段落，把程式、資料、測試各歸各位，
讓成果可以被安全保存、離線重建、之後的《開會了》等批次可以複用。

## What Changes

- **程式重組**：`.claude/skills/video-subtitle-srt/scripts/` 的通用引擎搬到
  `scripts/subs2srt/`（正式 package）；`ilrdf-srt/` 的編排程式搬到
  `scripts/news/`；預留 `scripts/aiyalaeho/` 給《開會了》。
  `.claude/.../SKILL.md` 保留為純說明書，改指向 `scripts/`。
- **命名統一**：`wenkao` 一律改名 `rtf`（`rtf.py`、`rtf_sheets.py`、
  `compare_rtf.py`、`--rtf` 旗標、`from_rtf.json`、`vision-rtf/`）。
- **路徑集中**：新增 `scripts/news/paths.py`，ROOT 由 `__file__` 推導，
  消滅全部寫死的絕對路徑。**BREAKING**：舊的 `ilrdf-srt/` 呼叫方式全部失效。
- **資料歸位**：逐字稿 TSV、時間軸 `cues.json`、來源紀錄 `from_rtf.json`、
  交付 SRT、`smkul.csv`、比對報告移入 `Kari-SRT/` submodule，命名鍵統一用
  `srt_name`。**BREAKING**：`kithann/srt/` 廢除，正本在 `Kari-SRT/srt/`。
- **corpus 知識歸位**：`presets.json` 從引擎搬到 `scripts/news/`，
  引擎改收 preset 路徑參數。
- **全面補測試**：`selftest.py` 的 51 個單元測試拆進 `tests/`（每檔約
  200 行、依模組分目錄），`scripts/news/` 各模組新增離線單元測試，
  合成影片 round-trip 保留為 e2e。tox 各 env 對應更新。

## Capabilities

### New Capabilities

- `srt-data-store`：字幕成果與過程資料的存放契約——Kari-SRT submodule 的
  目錄結構、`srt_name` 命名鍵、哪些資料必須 commit，以及核心保證：
  砍掉全部未 commit 的工作目錄後，僅靠主 repo + Kari-SRT 能離線重建出
  逐 byte 相同的 22 個 SRT。

### Modified Capabilities

（無既有 spec。）

## Impact

- **搬移**：`ilrdf-srt/*` → `scripts/news/`；`.claude/.../scripts/*.py` →
  `scripts/subs2srt/`；`ilrdf-srt/vision*` → `Kari-SRT/`；
  `kithann/out/mxf/*.work/cues.json`、`from_wenkao.json` 撈出 → `Kari-SRT/`；
  `kithann/srt/*` → `Kari-SRT/srt/`（原位置廢除）。
- **改寫**：所有 `sys.path.insert` 黑魔法換成 package import；14 處絕對
  路徑改走 `paths.py`；`run_cues.sh` 的 `$ROOT/ilrdf-srt/` 引用。
- **設定**：`tox.ini`（subtitle env 改跑 `tests/`、flake8 範圍）、
  根 `.gitignore`（kithann 維持整個 ignore）、`.travis.yml` 若引用舊路徑。
- **文件**：`ilrdf-srt/README.md` 隨程式搬家並更新路徑；SKILL.md 改寫。
- **git 操作分工**：檔案搬移與程式修改由 Claude 執行；`git add`／`commit`／
  submodule pointer bump 依 CLAUDE.md 規定由使用者執行。
