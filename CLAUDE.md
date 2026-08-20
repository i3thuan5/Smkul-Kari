# CLAUDE 規定

## SRT 產出規定

任何 SRT 語句，邊界都盡量要留白，以利語音辨識模型訓練取得正確聲學參數。每段前面、後面各延伸 **0.5 秒**，0.5 秒為參考  Kaldi cleanup `segment_ctm_edits.py` 的 [--max-edge-silence-length](https://github.com/i3thuan5/kaldi/blob/d9ab0465aa2849ff645c027110c48899d5ec6ca8/egs/wsj/s5/steps/cleanup/internal/segment_ctm_edits.py#L42-L46)
預設值。規則：

- 相鄰兩段聲音之間過於接近無法各往外延伸 0.5 秒時，延伸到兩段聲音實際聲音邊界的**中點**相接（會使拄好相接，袂使重疊）。
  例：第一段1.0–5.0秒、第二段5.2–8.3秒，延伸為第一段 1.0–5.1秒、第二段 5.1–8.3秒。
- start 不為負；且end 不能超過影片長度。
- 留白只影響** SRT 輸出**；時間軸資料（`cues.json` 等）保存真實切換點，無含留白。

## 文件排版規定

- 寫報告、SOP 這款欲交出去ê文件（特別是 `kithann/` 內底、以後欲搬去 Google Docs／Sheets 維護ê），**莫手動摺行**：一个段落、一个條目就是一逝，長就予伊長。手動換行貼去 Google 彼爿會變做斷做幾若段。
- Repo 內ê README、spec 等技術文件無受此限，照原本ê習慣。

## Git 操作規定

Claude Code **毋准**執行下底ê git 指令（會影響 staged 檔案、commit 紀錄、分支、抑是遠端）：

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

**准**執行下底ê git 指令（查看抑是暫存，毋影響紀錄）：

- `git stash`、`git stash pop`、`git stash apply`、`git stash list`
- `git log`、`git show`、`git diff`、`git status`
- `git branch`（列出，毋是建立抑是hìnn-sak）
- `git restore <file>`（working tree only，無 `--staged`）

程式碼修改（Edit、Write、等工具）會用得用。

## 密碼、憑證處理規定

指令是**佇本機**走ê，毋過下底三項會入我ê context、也就是**會送到 Anthropic 主機**：

1. 我寫ê**指令文字**
2. 我看ê**指令輸出**
3. 我 `Read` ê**檔案內容**

所以密碼只要囥佇「我永遠無讀、嘛袂出現佇指令抑是輸出」ê檔案，就袂外洩。

**毋准**：

- `Read`、`cat`、`head`、`grep` 憑證檔ê內容（讀著就等於上傳）
- kā密碼寫佇指令列，包含 `user:pass@host` 這款 URL
  （會入 `ps`、shell history、佮對話紀錄，三个所在攏走袂掉）
- kā密碼用 `echo`／`Write` 寫入檔案（彼段指令本身就是密碼）—— 這步ài**使用者家己佇終端機拍**

**准**：

- 讀憑證檔ê**路徑**、權限、位元組數（`ls -l`），毋讀內容
- 透過檔案路徑餵密碼：`SSH_ASKPASS`、`sshpass -f`、`~/.ssh` 金鑰、`~/.netrc`
- 檢查格式問題（有無 CR、空白、非 ASCII）用 `grep -c`，計數毋是內容

憑證檔ài入 `.gitignore`（`.sftp-pass` 已經佇 178 逝）。

## 外部服務佮套件ê採購規定

正本是《採購安全說明書》（辦公廳資安人員維護）。彼份文件囥佇
`kithann/`，是 gitignore ê，**換機器會無去**，所以佮開發相關ê條款
記佇遮。beh引進**任何**新ê雲端服務、模型權重、抑是 Python 套件進前，
ài先照下底稽核，結果寫入該 change ê design：

1. **毋是中國製造、毋是中國企業維護**——這條上要緊。開源看團隊
   國籍（有疑問ê時，以近期 Reviewer ê國籍為準）；模型權重看
   **訓練語料佮 recipe ê出身**，毋是干焦看發布者。
2. ISO 27701／27001 認證優先；若會接觸著個資閣無認證，揀有公告
   隱私權條款ê。
3. 雲端服務機房臺灣優先。
4. 開源套件閣ài看：GitHub 維護頻率（三個月內有 commit）、有無
   贊助商、Issue／PR 有咧處理、搜「<名稱> security issue」ê名聲。
5. **裝愈少愈好**——會使用既有ê工具解決ê，就莫加新依賴。

已經稽核過ê（`add-asr-bilingual-srt`）：`vosk`、`huggingface_hub`、
ILRDF ê族語模型、ai-labs MT 服務、Claude 攏過；**vosk ê中文模型
無過**（multi-cn recipe 佮 SpeechIO／THCHS／aishell 語料是中國出身），
所以華語辨識改用借詞音節錨點，免中文 ASR。

## Python sir-tái-luh

- `for` khǹg 頭前（`for x in ...:`），毋准用 list comprehension 抑是 generator expression kā `for` khǹg tī 後壁（`[... for x in ...]`）。若欲，ài 有特殊理由，而且經過使用者同意。

## TDD 規定

寫程式一定ài先TDD：先寫測試、走hōo伊紅（fail），才寫實作hōo伊綠
（pass），紲落去才重構。

- 新模組：先開 `tests/` 內底ê對應測試檔，才准寫模組本身。
- 修 bug：先寫一个會重現這粒 bug ê測試，才落手改。
- 測試ài會使離線走（無phah網路、無讀大檔），資料用 fixture 合成。

## 程式修改了後ê驗收

- 每擺程式修改完，ài佇本機走 `tox -e rebuild`——對 Kari-SRT
  ê資料離線重建全部交付SRT、逐byte比對。這條**無入CI**（Kari-SRT
  是私人repo，CI掠袂著submodule），所以本機這步是唯一ê把關。
- 順紲走 `tox -e flake8` 佮 `tox -e unittest`（單元測試）。
- `tox` 若無佇 PATH（devcontainer 重建了後定定按呢），直接用 `.tox/` 內底
  ê venv，效果相仝：

  ```bash
  .tox/rebuild/bin/python -m scripts.news.rebuild --verify
  .tox/unittest/bin/python -m unittest discover -s tests/<pkg> -t .
  .tox/flake8/bin/flake8 . --count
  ```

- 驗收愛用**推算**ê，莫記死數字：批次進行中ê集數會變。條件是
  「`rebuild --verify` 過，而且伊講ê集數 ＝ store inventory 內底無標
  `pending` ê筆數」，毋是「猶原是 N 集」。
- README 等文件嘛仝款：**會綴批次變ê數字（集數、cue 數）莫寫死**，
  指去正本（`smkul.csv`、`inventory.json`）就好。
- 產出ê文件（README、報告）**莫記 design／task 編號**——彼是 change
  規劃ê暫時座標，歸檔就無意義；文件ài家己讀有。
- 改著檔案了後若測試結果怪怪，先清 `__pycache__`：檔案大細相仝、mtime
  仝一秒ê時，Python 會掠著舊ê bytecode。
