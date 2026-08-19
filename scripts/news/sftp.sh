#!/usr/bin/env bash
# Run sftp commands against the corpus server, reading the password from a
# file that is never named on a command line.
#
# Usage:  scripts/news/sftp.sh get REMOTE LOCAL
#         scripts/news/sftp.sh ls REMOTE            (long form, as parsed)
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

usage() {
    echo "usage: $0 {get REMOTE LOCAL | ls REMOTE | -}" >&2
    exit 2
}

check_path() {
    if [[ -z "$1" ]]; then
        echo "$0: 空的路徑，拒絕" >&2
        exit 2
    fi
    case "$1" in
        *'"'* | *\\* | *$'\n'* | *$'\r'* | *$'\t'*)
            echo "$0: 路徑含引號、反斜線抑是控制字元，拒絕：$1" >&2
            exit 2
            ;;
    esac
}

batch=$(mktemp)
trap 'rm -f "$batch"' EXIT

case "${1:-}" in
    -)
        cat > "$batch"
        ;;
    get)
        [[ $# -eq 3 ]] || usage
        check_path "$2"
        check_path "$3"
        printf 'get "%s" "%s"\n' "$2" "$3" > "$batch"
        ;;
    ls)
        # every caller reads the byte count out of column 5, so the long
        # form is part of the contract, not a convenience
        [[ $# -eq 2 ]] || usage
        check_path "$2"
        printf 'ls -l "%s"\n' "$2" > "$batch"
        ;;
    *)
        usage
        ;;
esac

if [[ -n "${SFTP_DRY_RUN:-}" ]]; then
    cat "$batch"
    exit 0
fi

exec sftp -o ConnectTimeout=20 -o BatchMode=no -o NumberOfPasswordPrompts=1 \
          -o PubkeyAuthentication=no -b "$batch" "$SFTP_HOST"
