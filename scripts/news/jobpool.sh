# shellcheck shell=bash
# 背景工作的並行上限。`source` 進來用：
#
#   source scripts/news/jobpool.sh
#   for x in ...; do
#       pool_wait_slot "$JOBS"      # 滿了就等其中一個做完
#       work "$x" &
#   done
#   wait
#
# `wait -n` 等「任何一個」背景工作結束，工作失敗也照樣回來——一集倒了
# 不可以卡住整批，失敗由各工作自己記進 log。

pool_wait_slot() {
    local limit=$1
    while (( $(jobs -rp | wc -l) >= limit )); do
        wait -n || true
    done
}

# 正整數才收：0 會讓 pool_wait_slot 永遠等不到空位，非數字在 bash 算術
# 裡會被當成 0。
pool_positive_int() {
    [[ "$1" =~ ^[1-9][0-9]*$ ]]
}
