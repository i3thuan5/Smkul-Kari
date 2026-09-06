#!/usr/bin/env bash
# Run sftp commands against the corpus server, reading the password from a
# file that is never named on a command line.
#
# Usage:  scripts/news/sftp.sh get REMOTE LOCAL
#         scripts/news/sftp.sh put LOCAL REMOTE
#         scripts/news/sftp.sh mkdir REMOTE         (tolerates "already there")
#         scripts/news/sftp.sh ls REMOTE            (long form, as parsed)
#         scripts/news/sftp.sh rename OLD NEW       (remote -> remote)
#         printf 'ls\n' | scripts/news/sftp.sh -    (ad-hoc batch on stdin)
#
# Paths are separate arguments, never pieces of a command string. `sftp -b`
# re-parses every line of the batch file, so a path pasted into a quoted
# argument can end that argument (a `"`) or start a whole new command (a
# newline). Callers used to build those lines themselves; now this script
# does, and refuses any path carrying a quote, a backslash or a control
# character. No broadcast master legitimately has one.
#
# Two options are load-bearing and easy to lose:
#
#   BatchMode=no        `sftp -b` turns BatchMode ON, and BatchMode suppresses
#                       the password prompt entirely -- ssh then reports
#                       "Permission denied (publickey,password)" without ever
#                       having asked. This is the failure that looks exactly
#                       like a wrong password but is not.
#   SSH_ASKPASS_REQUIRE OpenSSH's own hook, which works even though sftp asks
#                       for the password from a child ssh process. `sshpass`
#                       does not reach that child and fails the same way.
#
# SFTP_DRY_RUN=1 prints the batch that would be sent and exits, so the
# quoting is testable offline (tests/news/test_sftp_cli.py).
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export SSH_ASKPASS="$HERE/sftp-askpass.sh"
export SSH_ASKPASS_REQUIRE=force
export SFTP_PASS_FILE="${SFTP_PASS_FILE:-$HERE/../../.sftp-pass}"

SFTP_HOST="${SFTP_HOST:-ilrdf-corpus@192.168.35.10}"

# 印用法、回傳離開碼；離開由呼叫端做，函式才有明確的出口
usage() {
    echo "usage: $0 {get REMOTE LOCAL | put LOCAL REMOTE |" \
         "mkdir REMOTE | ls REMOTE | rename OLD NEW | -}" >&2
    return 2
}

check_path() {
    local path=$1
    if [[ -z "$path" ]]; then
        echo "$0: 空的路徑，拒絕" >&2
        exit 2
    fi
    case "$path" in
        *'"'* | *\\* | *$'\n'* | *$'\r'* | *$'\t'*)
            echo "$0: 路徑含引號、反斜線抑是控制字元，拒絕：$path" >&2
            exit 2
            ;;
        *)
            return 0
            ;;
    esac
}

batch=$(mktemp)
trap 'rm -f "$batch"' EXIT

verb=${1:-}
# get/ls name the remote first; put is the other direction, so the two
# operands are read per verb rather than positionally for all of them.
arg2=${2:-}
arg3=${3:-}

case "$verb" in
    -)
        cat > "$batch"
        ;;
    get)
        [[ $# -eq 3 ]] || { usage; exit $?; }
        check_path "$arg2"
        check_path "$arg3"
        printf 'get "%s" "%s"\n' "$arg2" "$arg3" > "$batch"
        ;;
    put)
        [[ $# -eq 3 ]] || { usage; exit $?; }
        check_path "$arg2"
        check_path "$arg3"
        printf 'put "%s" "%s"\n' "$arg2" "$arg3" > "$batch"
        ;;
    mkdir)
        # The leading "-" is sftp's own "carry on if this line fails". A
        # folder that is already there makes mkdir return non-zero, which
        # in a batch would abandon everything after it -- and "already
        # there" is the normal case for every episode after the first.
        [[ $# -eq 2 ]] || { usage; exit $?; }
        check_path "$arg2"
        printf -- '-mkdir "%s"\n' "$arg2" > "$batch"
        ;;
    ls)
        # every caller reads the byte count out of column 5, so the long
        # form is part of the contract, not a convenience
        [[ $# -eq 2 ]] || { usage; exit $?; }
        check_path "$arg2"
        printf 'ls -l "%s"\n' "$arg2" > "$batch"
        ;;
    rename)
        # Deliberately without mkdir's leading "-": for mkdir, "already
        # there" is the normal case and must not abandon the batch. Here
        # a failure means the final name never appeared, so the file did
        # not really arrive -- and callers use "the final name exists" as
        # their proof that an upload completed. Swallowing this would let
        # the next run skip a file that is not actually there.
        [[ $# -eq 3 ]] || { usage; exit $?; }
        check_path "$arg2"
        check_path "$arg3"
        printf 'rename "%s" "%s"\n' "$arg2" "$arg3" > "$batch"
        ;;
    *)
        usage
        exit $?
        ;;
esac

if [[ -n "${SFTP_DRY_RUN:-}" ]]; then
    cat "$batch"
    exit 0
fi

exec sftp -o ConnectTimeout=20 -o BatchMode=no -o NumberOfPasswordPrompts=1 \
          -o PubkeyAuthentication=no -b "$batch" "$SFTP_HOST"
