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
SECRETS="$HOME/.config/secrets/.env.secrets"
LOGDIR="$REPO/logs"
LOG="$LOGDIR/agent_time_stop.log"
ENFORCE=1
[ "${1:-}" = "--dry-run" ] && ENFORCE=0

mkdir -p "$LOGDIR"
say() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >>"$LOG"; }

[ -f "$SECRETS" ] || { say "ABORT no secrets file"; exit 1; }

# Only this one key is needed, and only in the environment. The secrets file is
# not valid shell, so it is never sourced; the value is never echoed and never
# put on a command line.
OANDA_API_KEY=$(sed -n 's/^OANDA_API_KEY=//p' "$SECRETS" | head -1 | sed 's/^"//; s/"$//')
[ -n "$OANDA_API_KEY" ] || { say "ABORT OANDA_API_KEY not found in $SECRETS"; exit 1; }
export OANDA_API_KEY

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
