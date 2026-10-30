# Design

## Context

`節目名稱` 在新聞的節目目錄裡有兩個用途：它是給人讀的節目名，也是程式推導播出時段的唯一來源。時段進到 `成果檔名`（例如 `20241202_337_晚間_Amis_阿美` 的「晚間」）、工作區名、檔名時段碼的比對，全部都經過 `catalogue_checks.slot_of()`。

```
smkul.csv 節目名稱
   │
   ▼
catalogue_checks.slot_of()  ←  SLOTS（唯一寫死舊名稱的程式）
   ├─ srt_name_of()       → 成果檔名的時段
   ├─ episodes.py (×2)    → 工作區名、播出時段
   ├─ sources.py          → 候選檔案裡挑檔名時段與時段相符的
   └─ resolve_slug.py(×3) → 檔名還原
```

量過的現況（2026-10-30）：目錄 3,153 列；2024-08-01 起的新聞 337 列（午間 147、晚間 146、晨間 44）；07-31 以前 2,816 列。新聞資料裡只有 `smkul.csv` 有這一欄；平行語料、片頭辨識、辨識紀錄、排除影片都以成果檔名為鍵。17 支測試檔提到舊名稱，但沒有一個把 2024-08 以後的日期配舊名稱。動機見 proposal。

## Goals / Non-Goals

**Goals:**
- 2024-08-01 起的列，名稱寫成實際的節目名稱「看見族語（時段）」，時段推導與成果檔名完全不變。
- 以檢查守住「名稱與日期對得上」，讓之後匯入的批次不會悄悄分成兩種寫法。

**Non-Goals:**
- 不改成果檔名，不動 Kari-SRT 任何階段的檔案名稱或內容。
- 不新增 `播出時段` 欄（既有規格明文禁止）。
- 不處理 2025 年以後的目錄匯入；那是下一批匯入時由新檢查把關。
- 不改開會了的表。

## Decisions

**D1. 名稱格式：`看見族語（午間／晚間／晨間）`，全形括號。** 使用者偏好（2026-10-30）。時段留在名稱裡，所以 `slot_of` 不必改介面，也不必新增欄位。替代方案：只寫「看見族語」另開時段欄——要改既有規格明文禁止的欄位，影響面最大，不採用。半形括號不認，因為兩種寫法並存會讓篩選與比對失靈；對不上時由 `slot_of` 提示「括號要用全形」。

**D2. 界線 2024-08-01，不是 07-31。** 07-31 的午間、晚間雖已有「並更名為看見族語」的預告，節目名稱仍是族語新聞；主播口播「歡迎收看全新改版的看見族語」從 08-01 開始。

**D3. 舊名稱保留在對照表內。** 07-31 以前 2,816 列繼續用它，所以現有測試不用改。日期對照檢查負責避免兩組名稱用錯地方，對照表本身只管「名稱 → 時段」。

**D4. 日期對照檢查放在 `catalogue_checks.row_problems`。** 它是新聞與開會了共用的頂層檢查，`rebuild --verify` 已經對真實目錄跑它，所以不必另寫讀真實檔案的測試。放進 `scripts/news/` 的話，開會了那邊看不到這條規則，而且 `rebuild --verify` 也不會自動跑到。

**D5. 單一來源：`programme_for(時段, 播出日期)`。** 回答「這個時段、這一天，節目名稱該寫什麼」，檢查用它判斷、`redate.py` 用它重寫。不這樣做的話，兩處各自寫界線，改一處另一處就不一致。界線常數 `RENAMED_ON` 也只放一處。

**D6. `redate.py` 跨界線時同步改節目名稱。** 否則用它把一集從 07-31 改到 08-01，剛改好的列會立刻被 D4 的檢查擋下。

**D7. 遷移程式放在 change 資料夾的 `migrations/`，不放 `scripts/`。** 它只跑一次，跑完就沒有存在的理由；既有的遷移（例如 `unify-episode-tables`）也這樣放。程式有 dry-run、重跑不會出事（已改的列不再動），並先驗證三組數字（337／2,816／總列數）才寫入。

## 檔案樹

**第一層：Kari-SRT（資料）**

```
Kari-SRT/
├── README.md              ✎改  「午間族語新聞→午間，983 列零例外」改成兩組名稱與界線，不寫死列數
└── news/smkul.csv         ✎改  337 列的節目名稱（遷移程式產出）
    其餘各階段目錄與紀錄表  ＝不動：以成果檔名為鍵，成果檔名不變
```

**第二層：tests/（測試）**

```
tests/
├── catalogue/
│   ├── test_catalogue_checks.py  ✎改  時段解析（新舊）、括號寫法、日期對照
│   └── README.md                 ✎改  補下表；舊的「983 列零例外」改成不寫死列數
└── news/
    ├── test_name_catalogue.py    ✎改  新名稱的列 --check 不報不合
    ├── test_episodes.py          ✎改  工作區名與時段不隨改名變
    ├── test_sources.py           ✎改  新名稱列的挑檔規則照常
    └── test_redate.py            ✎改  跨界線時節目名稱跟著換
```

**第三層：scripts/（程式）**

```
scripts/
├── catalogue_checks.py   ✎改  SLOTS 擴成六個；RENAMED_ON；programme_for()；
│                              日期對照檢查；slot_of 錯誤訊息的括號提示；掛進 row_problems
├── news/redate.py        ✎改  redate_row 用 programme_for 重寫節目名稱
└── README.md             ✎改  catalogue_checks.py、redate.py 兩列補一句
.claude/commands/smkul-catalogue-import.md   ✎改  新批次 2024-08-01 起寫新名稱
openspec/changes/rename-news-programme-2024-08/migrations/rename_programme.py   ★新（一次性）
```

不動的模組：`news/episodes.py`、`news/sources.py`、`news/resolve_slug.py`、`news/name_catalogue.py`、`aiyalaeho/*`，它們都只呼叫 `slot_of`，介面不變。

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| episode-catalogue | 三個新名稱各解出對的時段；舊的三個仍解得出（07-31 以前 2,816 列在用） | `test_catalogue_checks.py` |
| episode-catalogue | 半形括號 `看見族語(晚間)` 不認、指名並提示全形，不推空字串（Excel 手打最常犯、看起來幾乎一模一樣） | `test_catalogue_checks.py` |
| episode-catalogue | 只寫「看見族語」不帶時段，對不到時段（三個時段共用同名，推不出是哪個） | `test_catalogue_checks.py` |
| episode-catalogue | 界線兩側各測一例：07-31 配舊名稱過、08-01 配新名稱過；08-01 配舊名稱被擋、07-31 配新名稱被擋（防 `>` 與 `>=` 寫反） | `test_catalogue_checks.py` |
| episode-catalogue | 一張表同時有新舊名稱是合法的，不可要求整表同名 | `test_catalogue_checks.py` |
| episode-catalogue | 日期對照不波及開會了：無播出日期欄、節目名稱「開會了」，不拋 KeyError、不誤報 | `test_catalogue_checks.py` |
| episode-catalogue | 播出日期空白或格式壞掉時，日期對照不拋例外、不多報，只留「成果檔名與識別欄不一致」那一條 | `test_catalogue_checks.py` |
| episode-catalogue | 改名不連動改成果檔名：`看見族語（晚間）` ＋ 2024-12-02 與舊名稱組出同一個 `20241202_337_晚間_Amis_阿美`（連動的話 3,153 支 SRT 全成孤兒檔） | `test_catalogue_checks.py`、`test_name_catalogue.py` |
| episode-catalogue | 工作區名 `2024_337_2024-12-02_晚間_…` 不隨節目名稱改變（變了切好的工作區就找不到） | `test_episodes.py` |
| episode-sourcing | 新名稱列的挑檔規則照常：「看見族語（晚間）」的候選裡，檔名寫晚間的勝過寫午間的（挑檔靠 `slot_of` 解出時段，名稱解不出來就會挑錯檔） | `test_sources.py` |
| episode-catalogue | 改日期跨過 2024-08-01 時節目名稱跟著換（兩個方向），否則剛改好的列會被日期對照擋下 | `test_redate.py` |

## Risks / Trade-offs

- **Excel 手打全形括號容易打錯** → 對不上時由 `slot_of` 指名該列、列出合法寫法並提示全形；日期對照檢查在 `rebuild --verify` 時對真實目錄再把關一次。
- **界線寫在程式裡，之後節目再改名要動程式** → 界線與名稱集中在 `catalogue_checks.py` 的一處常數與對照表，`programme_for` 是唯一出口；真的再改名時也是改這一處。
- **外部單位若直接用 `smkul.csv` 的節目名稱篩選，改名後篩選結果會變** → 無法由程式查證；成果檔名不變，用成果檔名對應的做法不受影響。完成後在交付說明提一句。
- **遷移寫錯會改到不該改的列** → dry-run 先印三組數字，數字對不上就不寫；改完以 `name_catalogue --check` 與 `rebuild --verify` 驗證成果檔名與各階段檔案沒變。

## Migration Plan

1. 先寫測試（紅）、改程式（綠），文件同步。
2. 跑遷移程式：先 dry-run 看 337／2,816／總列數，再寫入 `smkul.csv`（保留原本的 BOM 與 CRLF）。
3. 驗收：`name_catalogue --check`、`rebuild --verify`、`unittest`、`flake8`。
4. 回復：`smkul.csv` 在 git 管理，改壞了以 `git restore` 還原那一個檔案即可；其他檔案都沒動。
