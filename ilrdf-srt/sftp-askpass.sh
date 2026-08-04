#!/usr/bin/env bash
# Hand the SFTP password to OpenSSH without it ever entering a command line.
#
# `sshpass` does not work here: sftp/scp spawn ssh as a *child*, and that child
# reads the password from /dev/tty, not from the pty sshpass wraps around the
# parent. The result is ssh giving up before it ever asks -- "Permission denied
# (publickey,password)" -- even though the same password authenticates fine
# when ssh is invoked directly.
#
# OpenSSH's own hook works at any depth. Point SSH_ASKPASS at this script and
# force its use:
#
#   SSH_ASKPASS=ilrdf-srt/sftp-askpass.sh SSH_ASKPASS_REQUIRE=force \
#   SFTP_PASS_FILE=.sftp-pass sftp ilrdf-corpus@192.168.35.10
#
# The secret stays in the file the whole time: it is never an argument, so it
# never reaches `ps`, shell history, or a transcript. Only the *path* is ever
# written down.
set -u
exec cat "${SFTP_PASS_FILE:-/workspaces/Corpus-Cleanup/.sftp-pass}"
