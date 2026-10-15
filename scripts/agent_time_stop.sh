#!/usr/bin/env bash
# The mechanical half of the time stop.
#
# WHY THIS EXISTS. A written horizon was enforced by nothing. Live trade 3 was
# opened 2026-09-23 18:01Z with "expect 1.1340 within 24h" in its reason field and
# closed 43.0 hours later, because the only things that could have closed it were
# the broker stop, the broker target - which price never reached - or a session
# choosing to act, and the sessions run at 13:00, 18:00 and 20:00 UTC. The
# deadline fell at 18:01Z on 09-24, inside a window; the position then ran another
# 19 hours because the next session did not look at it until 13:00Z on 09-25.
# A deadline that depends on a model being awake is not a deadline.
#
# So this runs on a timer. It costs one API call when there is nothing to do, it
# needs no model and no tokens, and the rules it applies live in
# tools/oanda_trade.py rather than here, so a rule cannot drift between the two.
#
# Usage:
#   scripts/agent_time_stop.sh            # enforce: close what is overdue
#   scripts/agent_time_stop.sh --dry-run  # report only, place nothing
#
# It will not close a trade that carries no horizon, and it stands down entirely
# while logs/AGENT_TRADING_HALT exists. See cmd_time_stop in tools/oanda_trade.py.

set -uo pipefail

REPO="/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
LOGDIR="$REPO/logs"
LOG="$LOGDIR/agent_time_stop.log"
ENFORCE=1
[ "${1:-}" = "--dry-run" ] && ENFORCE=0

mkdir -p "$LOGDIR"
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

ARGS=(time-stop)
[ "$ENFORCE" = "1" ] && ARGS+=(--enforce)

OUT=$(cd "$REPO" && timeout 90 python3 tools/oanda_trade.py "${ARGS[@]}" 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
  say "ERROR rc=$RC $(tr '\n' ' ' <<<"$OUT" | head -c 400)"
  exit "$RC"
fi

# Log the decision, never the payload. One line per action, plus a heartbeat on a
# quiet run: this desk has twice lost days to a job that was silently not running,
# and a line every ten minutes is the cheapest proof that it still is.
SUMMARY=$(python3 - "$OUT" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
acted = [a for a in d["actions"]
         if a["action"] in ("CLOSED", "SKIPPED_HALTED", "SKIPPED_MARKET_CLOSED", "NO_HORIZON")]
if acted:
    for a in acted:
        print(f'{a["action"]} {a["instrument"]} trade={a["trade_id"]} '
              f'age={a["age_hours"]}h overdue={a["overdue_hours"]}h pl={a["unrealizedPL"]}')
else:
    print(f'ok open={len(d["actions"])} nothing overdue')
PY
)
say "$SUMMARY"

# The excursion sampler rides the same timer. Where a trade went between its entry
# and its exit is otherwise unrecorded, so "the stop was too tight" could never be
# checked against anything. It is read-only and cannot place an order, and a failure
# here must not fail the time stop that shares the run: it is reported, then dropped.
# A quiet run logs nothing, because the heartbeat above already proves the job ran.
EXC=$(cd "$REPO" && timeout 60 python3 tools/oanda_trade.py excursions 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
  say "EXCURSIONS ERROR rc=$RC $(tr '\n' ' ' <<<"$EXC" | head -c 300)"
else
  LINE=$(python3 - "$EXC" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
if d["open_trades"]:
    print(f'sampled={d["sampled"]} scored={d["scored"]} open={d["open_trades"]}')
PY
)
  [ -n "$LINE" ] && say "EXCURSIONS $LINE"
fi

# A quiet run is a success. Without this the script's exit status would be that of
# the last test above, which is false whenever nothing is open, and the timer would
# report a healthy run as a failed service.
exit 0
