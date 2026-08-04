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
