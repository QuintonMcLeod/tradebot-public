#!/usr/bin/env bash
# End-of-day PnL push, on a timer.
#
# Steven asked for this on 2026-10-07: "Send push notifications on PnL wins and
# losses at the end of your trading day so I can keep track. Send through Vera (she
# handles push notifications)."
#
# This wrapper exists for one reason: the OANDA key has to be in the process
# environment and must never appear on a command line. The secrets file is not valid
# shell, so it is never sourced; the single key this needs is read out of it here and
# exported. Nothing is echoed.
#
# The message itself, the numbers in it and the decision to push or stay quiet all
# live in tools/daily_pnl_push.py, so a rule cannot drift between the two files.
#
# The push goes out through the secretary's notifier, which is the only channel on
# this host that returns a receipt. A day with no trade pushes nothing and is not a
# failure: the exit code stays 0.
#
# Usage:
#   scripts/agent_daily_pnl_push.sh --dry-run   # print the message, send nothing

set -uo pipefail

REPO="/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
LOG="$REPO/logs/daily_pnl_push.log"

mkdir -p "$REPO/logs"
say() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >>"$LOG"; }

# Rule 206: no secret comes out of a file. The OANDA key and the database password come
# out of secretary.vault into the environment through the accessor, which re-runs this
# same script with both set. Steven's ~/.config/secrets/.env.secrets is never read.
VAULT="$HOME/Scripts/Secretary/vault_crypto.py"
if [ -z "${TRADEBOT_SECRETS_ENV:-}" ]; then
  export TRADEBOT_SECRETS_ENV=1
  export TRADEBOT_DB_HOST="${TRADEBOT_DB_HOST:-192.168.133.206}"
  export TRADEBOT_DB_USER="${TRADEBOT_DB_USER:-tradebot_sci}"
  export TRADEBOT_DB_SCHEMA="${TRADEBOT_DB_SCHEMA:-tradebot_sci}"
  exec python3 "$VAULT" exec tradebot-sci-db --as TRADEBOT_DB_PASSWORD -- \
       python3 "$VAULT" exec tradebot-oanda-key --as OANDA_API_KEY -- \
       /bin/bash "$0" "$@"
fi
[ -n "${OANDA_API_KEY:-}" ] || { say "ABORT OANDA_API_KEY not set by the accessor"; exit 1; }

OUT=$(cd "$REPO" && timeout 120 python3 tools/daily_pnl_push.py "$@" 2>&1)
RC=$?

# One line per run, whatever happened, so a week of silence is visible as a week of
# log lines rather than guessed at.
TITLE=$(sed -n 's/^--- \(.*\) ---$/\1/p' <<<"$OUT" | head -1)
say "rc=$RC ${TITLE:-no-title} $(tail -1 <<<"$OUT" | head -c 160)"
[ -n "$TITLE" ] && printf '%s\n' "$TITLE"

# The exit code is deliberately passed through only when the run really failed to
# build or send. A quiet day exits 0 from the tool, and a timer marked failed for
# doing nothing is how a working job gets switched off (incident 16).
exit "$RC"
