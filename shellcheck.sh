#!/bin/bash
# 對這个 repo ê shell script 走靜態檢查。
#
# 排除ê目錄佮 tox.ini ê flake8 彼節仝款（.git、.tox、venv、kithann、
# scratchpad）。本底干焦排除 venv，結果 kithann/ 內底三千外支舊 session
# 產出來ê臨時指令檔（status.sh、todo.sh、midcue_cmds.sh 這款）逐支攏
# 掃：規个走煞愛兩分鐘外，而且**永遠是紅ê**。kithann/ 是 gitignore ê
# 暫存，毋是欲維護ê程式碼，按呢這个關卡就佮程式碼ê品質無關係矣。排除
# 了後賰 6 支，拄好就是 git 追蹤ê彼 6 支。
#
# 用 -prune 毋是 -not -path：-prune 根本無行入去彼幾个目錄，-not -path
# 是行入去逐支才閣篩掉。三千外支ê差別是兩分鐘對無夠一秒。
#
# LC_ALL 愛設做 UTF-8：容器ê locale 是 POSIX，這款 locale 下底，
# 若欲共有漢字ê彼逝原始碼印出來會失敗做「commitBuffer: invalid
# argument (invalid character)」——看起來若像是檔案歹去，其實是咧報
# 一个正常ê發現，煞印袂出來。這个 repo ê註解濟濟是漢字，無設ê話
# 真正ê訊息就予這句蓋去矣。
#
# （順紲一項：註解逐逝ê頭一个詞袂使是 shellcheck 彼字，伊會共當做
# 指令去解析，報 SC1072／SC1073。頂懸彼幾逝就是按呢排ê。）
export LC_ALL=C.utf8
exit_code=0
while IFS= read -r -d '' file
do
    shellcheck --severity=info "$file";
    tsitkai="$?"
    exit_code=$(( tsitkai != 0 ? tsitkai : exit_code))
done <   <(find . \
    \( -path ./.git -o -path ./.tox -o -path ./venv \
       -o -path ./kithann -o -path ./scratchpad \) -prune \
    -o -type f -name '*.sh' -print0)
exit $(( exit_code == 0 ? 0 : 1))
