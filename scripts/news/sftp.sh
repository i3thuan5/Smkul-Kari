#!/usr/bin/env bash
# Run sftp commands against the corpus server, reading the password from a
# file that is never named on a command line.
#
# Usage:  scripts/news/sftp.sh 'ls -l /path' 'get file local'   (one arg per line)
#         printf 'ls\n' | scripts/news/sftp.sh -
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
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export SSH_ASKPASS="$HERE/sftp-askpass.sh"
export SSH_ASKPASS_REQUIRE=force
export SFTP_PASS_FILE="${SFTP_PASS_FILE:-$HERE/../../.sftp-pass}"

SFTP_HOST="${SFTP_HOST:-ilrdf-corpus@192.168.35.10}"

batch=$(mktemp)
trap 'rm -f "$batch"' EXIT
if [ "${1:-}" = "-" ]; then
    cat > "$batch"
else
    printf '%s\n' "$@" > "$batch"
fi

exec sftp -o ConnectTimeout=20 -o BatchMode=no -o NumberOfPasswordPrompts=1 \
          -o PubkeyAuthentication=no -b "$batch" "$SFTP_HOST"
