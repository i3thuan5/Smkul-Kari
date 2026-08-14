# CLAUDE 規定

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

## Python sir-tái-luh

- `for` khǹg 頭前（`for x in ...:`），毋准用 list comprehension 抑是 generator expression kā `for` khǹg tī 後壁（`[... for x in ...]`）。若欲，ài 有特殊理由，而且經過使用者同意。

## 程式修改了後ê驗收

- 每擺程式修改完，ài佇本機走 `tox -e subtitle-rebuild`——對 Kari-SRT
  ê資料離線重建全部交付SRT、逐byte比對。這條**無入CI**（Kari-SRT
  是私人repo，CI掠袂著submodule），所以本機這步是唯一ê把關。
- 順紲走 `tox -e flake8` 佮 `tox -e subtitle`（單元測試）。
- `tox` 若無佇 PATH（devcontainer 重建了後定定按呢），直接用 `.tox/` 內底
  ê venv，效果相仝：

  ```bash
  .tox/subtitle-rebuild/bin/python -m scripts.news.rebuild --verify
  .tox/subtitle/bin/python -m unittest discover -s tests/<pkg> -t .
  .tox/flake8/bin/flake8 . --count
  ```

- 驗收愛用**推算**ê，莫記死數字：批次進行中ê集數會變。條件是
  「`rebuild --verify` 過，而且伊講ê集數 ＝ store inventory 內底無標
  `pending` ê筆數」，毋是「猶原是 N 集」。
- 改著檔案了後若測試結果怪怪，先清 `__pycache__`：檔案大細相仝、mtime
  仝一秒ê時，Python 會掠著舊ê bytecode。
