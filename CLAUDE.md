# CLAUDE 規定

## SRT 產出規定

任何 SRT 語句的邊界都盡量要留白，以利語音辨識模型訓練取得正確的聲學參數。每段前後各延伸 **0.5 秒**，0.5 秒是參考 Kaldi cleanup `segment_ctm_edits.py` 的 [--max-edge-silence-length](https://github.com/i3thuan5/kaldi/blob/d9ab0465aa2849ff645c027110c48899d5ec6ca8/egs/wsj/s5/steps/cleanup/internal/segment_ctm_edits.py#L42-L46)
預設值。規則：

- 相鄰兩段聲音之間太接近、無法各自往外延伸 0.5 秒時，延伸到兩段實際聲音邊界的**中點**相接（剛好相接，不可重疊）。
  例：第一段 1.0–5.0 秒、第二段 5.2–8.3 秒，延伸為第一段 1.0–5.1 秒、第二段 5.1–8.3 秒。
- start 不為負；end 不能超過影片長度。
- 留白只影響 **SRT 輸出**；時間軸資料（`cues.json` 等）保存真實切換點，不含留白。

## 文件排版規定

- 寫報告、SOP 這類要交出去的文件（特別是 `kithann/` 底下、日後要搬去 Google Docs／Sheets 維護的），**不要手動折行**：一個段落、一個條目就是一行，長就讓它長。手動換行貼到 Google 那邊會斷成好幾段。
- Repo 內的 README、spec 等技術文件不受此限，照原本的習慣。

## Git 操作規定

Claude Code **不准**執行下列 git 指令（會影響 staged 檔案、commit 紀錄、分支或遠端）：

- `git commit`
- `git add`
- `git checkout`
- `git switch`
- `git restore --staged`
- `git reset`（任何形式，含 --soft、--hard、--mixed）
- `git branch -d` / `git branch -D`
- `git push`
- `git pull`
- `git fetch`

**准許**執行下列 git 指令（查看或暫存，不影響紀錄）：

- `git stash`、`git stash pop`、`git stash apply`、`git stash list`
- `git log`、`git show`、`git diff`、`git status`
- `git branch`（列出，不是建立或刪除）
- `git restore <file>`（working tree only，不加 `--staged`）

程式碼修改（Edit、Write 等工具）可以使用。

## 密碼、憑證處理規定

指令是**在本機**執行的，不過下列三項會進入我的 context，也就是**會送到 Anthropic 主機**：

1. 我寫的**指令文字**
2. 我看的**指令輸出**
3. 我 `Read` 的**檔案內容**

所以密碼只要放在「我永遠不讀、也不會出現在指令或輸出」的檔案裡，就不會外洩。

**不准**：

- `Read`、`cat`、`head`、`grep` 憑證檔的內容（讀到就等於上傳）
- 把密碼寫在指令列，包含 `user:pass@host` 這類 URL
  （會進 `ps`、shell history 和對話紀錄，三個地方都躲不掉）
- 用 `echo`／`Write` 把密碼寫入檔案（那段指令本身就是密碼）—— 這一步要**由使用者自己在終端機輸入**

**准許**：

- 讀憑證檔的**路徑**、權限、位元組數（`ls -l`），不讀內容
- 透過檔案路徑餵密碼：`SSH_ASKPASS`、`sshpass -f`、`~/.ssh` 金鑰、`~/.netrc`
- 檢查格式問題（有無 CR、空白、非 ASCII）用 `grep -c`，計數而非內容

憑證檔要加入 `.gitignore`（`.sftp-pass` 已在第 178 行）。

## 外部服務與套件的採購規定

正本是《採購安全說明書》（辦公室資安人員維護）。那份文件放在
`kithann/`，是 gitignore 的，**換機器就會不見**，所以和開發相關的條款
記在這裡。要引進**任何**新的雲端服務、模型權重或 Python 套件之前，
要先照下列項目稽核，結果寫入該 change 的 design：

1. **不是中國製造、不是中國企業維護**——這條最重要。開源看團隊
   國籍（有疑問時，以近期 Reviewer 的國籍為準）；模型權重看
   **訓練語料與 recipe 的出身**，不是只看發布者。
2. ISO 27701／27001 認證優先；若會接觸個資又無認證，挑有公告
   隱私權條款的。
3. 雲端服務機房臺灣優先。
4. 開源套件還要看：GitHub 維護頻率（三個月內有 commit）、有無
   贊助商、Issue／PR 有無在處理、搜尋「<名稱> security issue」的名聲。
5. **裝得越少越好**——能用既有工具解決的，就不要加新依賴。

已經稽核過的（`add-asr-bilingual-srt`）：`vosk`、`huggingface_hub`、
ILRDF 的族語模型、ai-labs MT 服務、Claude 都通過；**vosk 的中文模型
不通過**（multi-cn recipe 和 SpeechIO／THCHS／aishell 語料是中國出身），
所以華語辨識改用借詞音節錨點，不用中文 ASR。

## Python 風格

- `for` 放前面（`for x in ...:`），不准用 list comprehension 或 generator expression 把 `for` 放在後面（`[... for x in ...]`）。若要用，必須有特殊理由，且經使用者同意。

## 長時間的背景工作（踩過兩次坑，每次都停一整晚）

轉檔、切 cue、vosk 解碼這類要跑好幾個小時的步驟，**怎麼發動**比程式本身更
重要：發動錯了，工作做完也沒人知道，整條流程就靜靜停在那裡，直到使用者
自己來看才發現。

- **要用 `run_in_background: true` 發動，不要用 `nohup … &`。**
  `nohup &` 是在一個前景指令裡脫身出去的，harness 沒有在追蹤它，結束時
  不會通知，所以**沒人把我叫醒**。（2026-08-21 就這樣空轉 12 個半小時。）
- **一步接一步用 `&&` 串在同一條指令，不要用 `pgrep` 輪詢等別的程序。**

  ```bash
  # 對：&& 本身就是「前面那個做完才做後面」
  python3 -m scripts.transcode.archive_batch --only "$NAME" && \
      finish-episode.sh "$SLUG" "$NAME" "$BATCHES"
  ```

  `until ! pgrep -f archive_batch; do sleep 30; done` 這種**不可以**：發出
  `pgrep` 的那個 shell，自己的指令列裡就有 `archive_batch` 這串字，
  **自己比對到自己**，迴圈永遠不會結束。更糟的是它會**傳染**——那隻殭屍
  沒清掉，後面的等待迴圈（就算改用 `[a]rchive_batch` 這種括號寫法）也
  會比對到它，一樣卡住。（2026-08-22 同一個錯犯三次，停了 10 小時。）
- **某一步若沒有照預期接下去，先找原因，不要只是補跑。** 上面那次就是
  15:00 發現沒接上時只補跑收尾、沒清殭屍，22:41 又被同一隻殭屍拖死。

## TDD 規定

寫程式一定要先 TDD：先寫測試、讓它紅（fail），再寫實作讓它綠
（pass），接著才重構。

- 新模組：先開 `tests/` 底下對應的測試檔，才准寫模組本身。
- 修 bug：先寫一個會重現這個 bug 的測試，才動手改。
- 測試要能離線執行（不連網路、不讀大檔），資料用 fixture 合成。

## 程式修改後的驗收

- 每次程式修改完，要在本機執行 `tox -e rebuild`——對 Kari-SRT
  的資料離線重建全部交付 SRT、逐 byte 比對。這條**沒有進 CI**（Kari-SRT
  是私人 repo，CI 抓不到 submodule），所以本機這一步是唯一的把關。
- 順便執行 `tox -e flake8` 和 `tox -e unittest`（單元測試）。
- 再核對目錄那欄 `srt_name`：
  `python3 -m scripts.news.name_catalogue --check`。那欄是**產生**的，
  不是手寫的——被人手改過、或命名規則動到，這一步會當場抓到（`exit 1`）。
  不符時不要去改那一格，執行 `python3 -m scripts.news.name_catalogue` 重新產生。
- `tox` 若不在 PATH（devcontainer 重建後常常這樣），直接用 `.tox/` 底下
  的 venv，效果相同：

  ```bash
  .tox/rebuild/bin/python -m scripts.news.rebuild --verify
  .tox/unittest/bin/python -m unittest discover -s tests/<pkg> -t .
  .tox/flake8/bin/flake8 . --count
  python3 -m scripts.news.name_catalogue --check
  ```

- 驗收要用**推算**的，不要記死數字：批次進行中的集數會變。條件是
  「`rebuild --verify` 通過，而且它說的集數 ＝ store inventory 裡沒標
  `pending` 的筆數」，不是「仍然是 N 集」。
- README 等文件也一樣：**會隨批次變動的數字（集數、cue 數）不要寫死**，
  指向正本（`smkul.csv`、`inventory.json`）就好。
- 產出的文件（README、報告）**不要記 design／task 編號**——那是 change
  規劃的暫時座標，歸檔後就沒意義；文件要自己讀得懂。
- 改了檔案之後若測試結果怪怪的，先清 `__pycache__`：檔案大小相同、mtime
  同一秒時，Python 會抓到舊的 bytecode。

## 先找 skill／slash command，不要自己從頭想

這個 repo 的標準做法已經寫進 skill，開工前先讀：

- **`/smkul-news`**（`.claude/commands/smkul-news.md`）——一個月的族語新聞
  從 SFTP 下載到 SRT 的全部步驟（抓檔切 cue → contact sheet → 視覺辨識
  → 組裝 publish），含規模估算和「先告知使用者才開始」的規矩。
- **`video-subtitle-srt`**（`.claude/skills/video-subtitle-srt/SKILL.md`）——
  燒印字幕抽 SRT 的引擎面做法（找字幕帶、切 cue、contact sheet 視覺辨識、
  續跑、glossary、tesstrain ground truth）。

量測過的數字和踩過的坑寫在 [scripts/news/README.md](scripts/news/README.md)。

## 對話語言

Claude 回話用**華語**（正體字）。程式註解、既有文件維持
原本的語言，不必改。用詞照〈避免中國慣用語〉那條：不要寫「兜底」
「默認」「調用」這類詞。
