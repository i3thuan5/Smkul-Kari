# reorg-subtitle-pipeline 設計

## Context

動機見 proposal.md。設計上重要的現況約束：

- 17 處 `/workspaces/Corpus-Cleanup/...` 絕對路徑分散在
  `ilrdf-srt/*.py`、`run_cues.sh`、`.claude` 引擎，以及 apply 前夕新增的
  SFTP 工具三支（`fetch_sftp.sh`、`resolve_slug.py`、`verify_band.py`）；
  本機 workspace 已改名 `/workspaces/Smkul-Kari`，這些路徑指向的位置
  **不存在**，該三支目前在本機跑不起來。跨檔 import 靠
  `sys.path.insert(0, SKILL)` 黑魔法。（處數以 task 1.3 的 grep 為準。）
- `selftest.py`（893 行）是自製 runner，51 個單元測試 + 合成影片 e2e
  混在一檔；tox 已有 `subtitle`／`subtitle-e2e` env 伸手進 `.claude/` 執行。
- Kari-SRT 已由使用者建立為獨立 repo（remote
  `git@github.com:i3thuan5/Kari-SRT.git`，已有一個 commit：rtf-vs-vision
  比對報告兩檔）；主 repo 已 commit gitlink，但 `.gitmodules` 尚未存在
  （task 4.6 的使用者步驟補上）。
- 早期 vision TSV 命名不一致：三種目錄名（slug／`032午_泰雅` 簡寫／
  `srt_name`）加一種攤平檔（`rukai_043_b01-03.tsv`，一檔含三批）。
- `ilrdf-srt/vision/`、`ilrdf-srt/vision-wenkao/` **untracked、無任何
  git 備份**（ilrdf-srt/README「換機器要帶什麼」聲稱已進 git，與現實
  不符）。第一個備份點是 task 4.6 的 Kari-SRT commit；在那之前的一切
  搬移只能用複製，不得移動或刪除原位置。
- 22 集的 `cues.json`、`from_wenkao.json`、`verified.json` 都在
  `kithann/out/mxf/<slug>.B.work/`，未進版本控制。
- CLAUDE.md 禁止 Claude 執行 `git add`／`commit` 等指令。
- repo 的 Python 風格規定：`for` 置前，不用 list comprehension。

## Goals / Non-Goals

**Goals:**

- 程式成為正常 package（正常 import、正常 unittest discovery、flake8 全蓋）。
- spec 中的離線重建保證有一個可執行的驗證入口（單一指令跑完 + byte 比對）。
- 搬移過程每一步可驗證：先搬、驗證通過、再刪舊位置。

**Non-Goals:**

- 不改任何演算法行為：cue 切分、對齊、SRT 組裝的輸出必須與現狀 byte 相同
  （這正是重建驗證的基準）。
- 不實作 `scripts/aiyalaeho/`（只建目錄與 README 佔位）。
- 不處理 `.rtf` 內的族語拉丁行（見 ilrdf-srt/README「還沒做的」）。
- 不新增 pytest 等相依；沿用 unittest + tox。

## Decisions

### D1：兩個 package 的邊界——引擎不認識 corpus

`scripts/subs2srt/`（引擎）只留「像素 → cue → sheet → SRT」的通用機制；
`scripts/news/`（編排）持有全部 corpus 知識。具體切法：

- `presets.json` 搬到 `scripts/news/`；引擎的 `match_preset()` 改收
  preset 檔路徑參數（CLI 加 `--presets`），不再讀自己身邊的檔案。
- `scripts/` 與各子目錄加 `__init__.py`，執行方式統一
  `python -m scripts.news.make_all`；`sys.path.insert` 全數刪除，
  news 端 `from scripts.subs2srt import cuelib` 正常 import。
- 捨棄的替代方案：引擎留在 `.claude/` 原地（維持 skill 自足）。捨棄原因：
  測試設施與 package 結構永遠要伸手進 agent 設定目錄，且 presets 滲漏
  無法解決。SKILL.md 降級為說明書即可保留 skill 的檢索價值。

### D2：路徑集中於 `scripts/news/paths.py`，ROOT 用 __file__ 推導

單一模組定義 `ROOT`（`__file__` 上推兩層）、`CORPUS`（唯一允許的外部
絕對路徑，environment variable `ILRDF_CORPUS` 可覆寫，預設
`/home/vscode/ilrdf-corpus`）、`WORK`、`KARI`、`ENGINE_PRESETS`。
`run_cues.sh` 改由 `python -m scripts.news.paths --var WORK` 之類取值，
shell 裡不再寫死路徑。捨棄的替代方案：每檔各自 `Path(__file__)` 推導——
消滅不了重複，且 shell script 無法共用。

### D3：Kari-SRT 遷移一次到位，含命名正規化

搬 TSV 進 Kari-SRT 時同步做三件事，一次遷移腳本完成，不留過渡狀態：

1. 目錄名全部改為 `srt_name`（對照表由 `inventory.json` 生成）。
2. 攤平檔（`rukai_043_b01-03.tsv` 等）拆回 `vision/<srt_name>/bNN.tsv`。
3. 從 work dir 撈出 `cues.json` → `cues/<srt_name>.json`、
   `from_wenkao.json` → `from_rtf/<srt_name>.json`。

遷移腳本本身留在 `scripts/news/`（一次性，但它就是「重建對照表」的
文件化），跑完後由重建驗證把關正確性。

### D4：重建驗證 = 一個入口指令

`python -m scripts.news.rebuild --verify`：從 Kari-SRT 的
`cues/` + `vision/` + `vision-rtf/` + `inventory.json` 在暫存目錄重組
全部 SRT，與 `Kari-SRT/srt/` 逐 byte 比對，任何差異或缺件即非零退出並
列名。這同時是 spec 兩個 scenario 的可執行形式，也是遷移腳本的驗收。
實作上是把 `make_all.py` 的組裝路徑改為可指定資料來源（Kari-SRT 或
work dir），而非另寫一套組裝邏輯——同一條程式碼路徑才能保證 byte 相同。

### D5：wenkao → rtf 改名與搬移分兩個 commit 階段

先在原位置完成改名（檔名、旗標、JSON 鍵、文件），驗證通過；再整目錄
搬移。git 視角是「rename + move」兩步，diff 可讀。所有 git 操作
（`add`／`commit`／`.gitmodules`／pointer bump）列成使用者執行的指令
清單，Claude 只做工作樹內的檔案操作（`mv`、編輯）。

### D6：測試佈局——依模組分目錄，每檔約 200 行

```
tests/
├── cuelib/     test_mask.py  test_segmenter.py  test_region.py  test_srt_format.py
├── subs2srt/   test_sheets.py  test_merge_repeats.py  test_ocr_prep.py  test_presets.py
├── align/      test_normalise.py  test_backbone.py  test_snap.py  test_no_interpolation.py
├── rtf/        test_rtf_decode.py  test_clean.py
├── news/       test_ingest.py  test_inventory.py  test_gap_guard.py
│               test_make_srt.py  test_batches.py  test_paths.py
└── e2e/        test_roundtrip.py（合成影片，tox subtitle-e2e 才跑）
```

- `selftest.py` 的 51 個測試按主題拆入 `tests/cuelib/`、`tests/subs2srt/`，
  拆完刪除 selftest.py；合成影片工具函數移到 `tests/e2e/` 共用。
- 新測試全部離線：fixture 用合成 Big5 RTF 片段、假 work dir（tmpdir）、
  真實案例節錄（`000多種的植物種類` 切壞案例、`已讀 work dir 拒絕覆蓋`
  等事故都 pin 成 regression test）。
- tox：`subtitle` env → `python -m unittest discover -s tests`（排除 e2e）；
  `subtitle-e2e` → 只跑 `tests/e2e/`；flake8 exclude 移除 `.claude` 相關
  特例，涵蓋 `scripts/` 與 `tests/`。
- 捨棄的替代方案：behave（repo 有骨架）。單元測試用 gherkin 沒有增值；
  維持 unittest。

### D7：kithann/srt 廢除的時點

在 D3 遷移完成、D4 驗證通過之後才刪 `kithann/srt/`。`make_all.py` 的
輸出目標改為 `Kari-SRT/srt/`。

## Risks / Trade-offs

- [byte 相同驗證可能因非決定性排序失敗（dict 順序、glob 順序）]
  → 組裝路徑本來就是排序過的（cue index），遷移前先跑一次現狀快照
  比對，若有非決定性來源在改動前修好（屬 bug 修正，不屬行為改變）。
- [`vision/` 早期攤平檔拆批時 cue 歸屬可能弄錯] → 拆完用「聯集 =
  work dir `verified.json` 的 cue 集合」做總量對帳，缺一多一都擋下。
- [`vision/`、`vision-rtf/` 是 untracked 的唯一正本，搬移期間任何
  誤刪都不可回復] → 全程複製不移動；原位置保留到 D4 重建驗證通過
  （task 5.2）之後才刪；task 3.8 刪 `ilrdf-srt/` 時明確排除這兩個
  目錄。
- [submodule 空 checkout：`.gitmodules` 尚未存在，remote 未知] →
  任務清單把「確認 remote／`git submodule add`」列為使用者步驟，
  Claude 只往 `Kari-SRT/` 工作樹寫檔。
- [搬移期間另一個 session 在跑舊路徑] → 使用者確認 C-pass 已完成、
  無進行中工作後才 apply；apply 過程中舊目錄保留到驗證通過才刪。
- [tox/.travis 對 `.claude` 路徑的殘留引用] → 全 repo grep
  `ilrdf-srt`、`.claude/skills/video-subtitle-srt/scripts` 作為完成
  檢查之一。

## Open Questions

（無——結構、命名、時序均已在 explore 階段與使用者定案。）
