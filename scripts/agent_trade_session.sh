#!/usr/bin/env bash
# One agent session — trading or training.
#
# The schedule lives in the tradebot_sci.trading_windows table, NOT in this file,
# so the agent can add, disable or retune its own windows in real time. This
# script reads that table every run and does every cheap deterministic check
# BEFORE spending anything on the agent: a run that matches no window, or that
# fails a gate, exits having cost nothing.
#
# Usage: agent_trade_session.sh [--force] [--kind trade|train]
#   --force  skip the schedule and market gates (still respects halt/lock)
#   --kind   force a specific brief, for manual testing

set -uo pipefail

REPO="/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
SECRETS="$HOME/.config/secrets/.env.secrets"
LOGDIR="$REPO/logs"
LOCK="/tmp/tradebot-agent-session.lock"
HALT="$LOGDIR/AGENT_TRADING_HALT"
MAX_SECONDS=3600          # hard ceiling; the briefs require finishing early
MAX_TRADE_WINDOWS=6       # sanity cap so the schedule cannot sprawl

mkdir -p "$LOGDIR"
ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
say() { printf '%s %s\n' "$(ts)" "$*" | tee -a "$LOGDIR/agent_sessions.log"; }

# ── Gate 0: leave the caller's cgroup ───────────────────────────────────
# The office work loop runs as a systemd oneshot service and starts this script
# as a plain detached child. systemd's default KillMode=control-group means that
# when the pass exits a few seconds later it kills everything still in that
# cgroup, this session included. Measured 2026-09-22: a pass lived 6 to 13
# seconds and every window from 2026-09-21 onward died inside it, so no session
# had run since the work loop took over the schedule - five windows started,
# five killed, none reaching a decision. Re-launching in a transient unit puts
# the session outside that cgroup, where it outlives the pass that asked for it.
# Same fault and same fix as the work loop's own agent wakes.
if [ -z "${TRADEBOT_SESSION_UNIT:-}" ]; then
  UNIT="tradebot-session-$(date -u +%Y%m%dT%H%M%SZ)"
  if command -v systemd-run >/dev/null 2>&1 && \
     systemd-run --user --collect --quiet --no-block \
                 --unit="$UNIT" --service-type=oneshot \
                 --working-directory="$REPO" \
                 --setenv=TRADEBOT_SESSION_UNIT=1 \
                 --setenv=PATH="$HOME/.local/bin:$PATH" \
                 /bin/bash "$0" "$@" >/dev/null 2>&1; then
    say "HANDOFF to $UNIT (escaping the work loop cgroup)"
    exit 0
  fi
  say "WARN systemd-run unavailable; running inline and at risk of a cgroup kill"
fi

# ── Gate 1: one session at a time ───────────────────────────────────────
exec 9>"$LOCK"
if ! flock -n 9; then say "SKIP already-running"; exit 0; fi

# ── Gate 2: kill switch ─────────────────────────────────────────────────
if [ -f "$HALT" ]; then say "SKIP halted (remove $HALT to resume)"; exit 0; fi

# ── Gate 3: secrets. This file is NOT valid shell (it has a bare word and an
#    unquoted <email>), so extract only the keys we need rather than sourcing it.
if [ ! -f "$SECRETS" ]; then say "ABORT no secrets file"; exit 1; fi
load_secret() {
  local key="$1" line
  line=$(grep -m1 "^${key}=" "$SECRETS" 2>/dev/null) || return 1
  line=${line#*=}; line=${line%\"}; line=${line#\"}; line=${line%\'}; line=${line#\'}
  printf '%s' "$line"
}
for k in OANDA_API_KEY TRADEBOT_DB_HOST TRADEBOT_DB_USER TRADEBOT_DB_PASSWORD TRADEBOT_DB_SCHEMA; do
  v=$(load_secret "$k") && export "$k=$v"
done
[ -z "${OANDA_API_KEY:-}" ] && { say "ABORT OANDA_API_KEY not set"; exit 1; }

dbq() { MYSQL_PWD="$TRADEBOT_DB_PASSWORD" mysql -h "$TRADEBOT_DB_HOST" -u"$TRADEBOT_DB_USER" \
        "$TRADEBOT_DB_SCHEMA" -N -B -e "$1" 2>/dev/null; }

# ── Gate 4: does the DB schedule say this hour is a window? ─────────────
FORCE_KIND=""; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --kind)  FORCE_KIND="${2:-}"; shift ;;
  esac
  shift
done

HOUR=$(date -u +%-H)
DOW=$(( $(date -u +%u) - 1 ))   # 0=Mon .. 6=Sun

if [ -n "$FORCE_KIND" ]; then
  KIND="$FORCE_KIND"
else
  KIND=$(dbq "SELECT kind FROM trading_windows
               WHERE enabled=1 AND hour_utc=$HOUR AND (weekday IS NULL OR weekday=$DOW)
               ORDER BY FIELD(kind,'trade','train') LIMIT 1;")
  if [ -z "$KIND" ]; then
    # Not a window. Fail closed if the DB itself is unreachable, rather than
    # trading on a schedule we cannot read.
    if ! dbq "SELECT 1;" >/dev/null; then say "ABORT schedule unreadable (DB down)"; exit 1; fi
    exit 0
  fi
fi

NWIN=$(dbq "SELECT COUNT(*) FROM trading_windows WHERE enabled=1 AND kind='trade';")
if [ -n "$NWIN" ] && [ "$NWIN" -gt "$MAX_TRADE_WINDOWS" ]; then
  say "ABORT $NWIN trade windows enabled, above the $MAX_TRADE_WINDOWS cap"; exit 1
fi

# ── Gate 5: market. Training sessions do not need an open market. ───────
TOOL="$REPO/tools/oanda_trade.py"
STATE=$(python3 "$TOOL" state 2>&1) || { say "ABORT state check failed: $STATE"; exit 1; }
if [ "$KIND" != "train" ]; then
  OPEN=$(python3 "$TOOL" market | python3 -c "import json,sys;print(json.load(sys.stdin).get('open'))" 2>/dev/null)
  [ "$OPEN" != "True" ] && { say "SKIP market closed"; exit 0; }
fi

read_state() { python3 -c "import json,sys;print(json.loads(sys.stdin.read()).get('$1'))" <<<"$STATE"; }
HALTED=$(read_state day_pl_halt_triggered); NAV=$(read_state NAV)
TRADES=$(read_state trades_today);          POSNS=$(read_state open_positions)
OVERDUE=$(read_state overdue_horizons)
if [ "$KIND" = "trade" ] && [ "$HALTED" = "True" ]; then
  say "SKIP daily loss halt (NAV $NAV)"; exit 0
fi

BRIEF="$REPO/Documentation/AGENT_TRADING_BRIEF.md"
[ "$KIND" = "train" ] && BRIEF="$REPO/Documentation/AGENT_TRAINING_BRIEF.md"
[ -f "$BRIEF" ] || { say "ABORT brief missing: $BRIEF"; exit 1; }

say "START kind=$KIND window=${HOUR}Z nav=$NAV trades_today=$TRADES positions=$POSNS overdue=$OVERDUE"

# ── Score the shadow book, and put the scoreboard in front of the session ─
# The desk stands aside far more often than it trades, and until 2026-10-07 what it
# passed over was prose in a note. Every stand-aside is now a row with a price and a
# deadline on it, and this prices the ones whose deadline has passed, so the entry
# filter can be judged by its own record instead of by its reputation. It reads the
# market and writes two files under logs/: it cannot place, move or close an order,
# and a failure here must not cost the window.
SHADOW=""
if [ -f "$REPO/tools/shadow_book.py" ]; then
  python3 "$REPO/tools/shadow_book.py" score >/dev/null 2>&1 || say "SHADOW score sweep failed"
  SHADOW=$(python3 "$REPO/tools/shadow_book.py" report 2>&1 | head -c 3000)
  PENDING=$(python3 "$REPO/tools/shadow_book.py" pending 2>&1 \
            | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['unscored'])" 2>/dev/null || echo "?")
  say "SHADOW scored=$(grep -c . "$REPO/logs/shadow_results.jsonl" 2>/dev/null || echo 0) waiting=$PENDING"
fi

# ── Read the agent bus and hand the messages to the agent ────────────────
# Steven had to tell an agent to do this, and it cost him work. Making it part
# of the prompt means a session cannot forget it. `peek` does not consume.
BUS=""
if command -v agentbus >/dev/null 2>&1 && [ -d /home/qchan/Scripts/agentbus ]; then
  BUS=$(cd /home/qchan/Scripts && AGENTBUS_ID=tradebot_sci timeout 20 agentbus peek 2>/dev/null | head -c 6000)
  if [ -n "$BUS" ] && ! grep -q 'nothing unread' <<<"$BUS"; then
    say "BUS unread messages present, passing to the agent"
  else
    BUS=""
  fi
fi

# ── Invoke the agent ────────────────────────────────────────────────────
export DSH_PERMISSION_MODE=danger-full-access
export PATH="$HOME/.local/bin:$PATH"
cd "$REPO" || exit 1

OUT="$LOGDIR/agent_session_$(date -u +%Y%m%dT%H%M%SZ).out"
ERR="${OUT%.out}.err"
START=$(date +%s)
if [ -n "$BUS" ]; then
  PROMPT="$(cat "$BRIEF")

===== UNREAD AGENT BUS MESSAGES (read these first, they may change your task) =====
$BUS
===== END BUS MESSAGES ====="
else
  PROMPT="$(cat "$BRIEF")"
fi

if [ -n "$SHADOW" ]; then
  PROMPT="$PROMPT

===== SHADOW BOOK: THE SETUPS THIS DESK DECLINED, SCORED =====
$SHADOW
===== END SHADOW BOOK ====="
fi
timeout "$MAX_SECONDS" dsh --profile headless "$PROMPT" >"$OUT" 2>"$ERR"
RC=$?
say "END rc=$RC elapsed=$(( $(date +%s) - START ))s out=$OUT"

# ── Record the report. The agent is told NOT to write a session row itself,
#    precisely so this is the single writer. ────────────────────────────
dbq "UPDATE trading_windows SET reviewed_at=NOW()
      WHERE enabled=1 AND kind='$KIND' AND hour_utc=$HOUR AND (weekday IS NULL OR weekday=$DOW);" >/dev/null

# A window that dies must not leave a blank row. On 2026-10-01 the 20:00Z session
# ended rc=1 after 934s and its note read only "[trade session]", which is
# indistinguishable in the record from a deliberate stand-aside. The cause was a
# one-byte output file - dsh wrote a bare newline, so the old `[ -s "$OUT" ]` test
# passed and the empty report was stored as if it were a report. Whitespace is now
# what counts as empty, and a window with no report records the failure instead,
# with the reason taken from stderr.
REPORT=$(python3 - "$OUT" "$KIND" <<'PY'
import sys, pathlib
kind, path = sys.argv[2], sys.argv[1]
p = pathlib.Path(path)
t = p.read_text(errors="replace").strip()[:6000] if p.exists() else ""
print((f"[{kind} session]\n" + t).replace("\\", " ").replace("'", "''") if t else "")
PY
)
if [ -n "$REPORT" ]; then
  NOTE_KIND="live-${KIND}-session"
  BODY="$REPORT"
else
  NOTE_KIND="live-${KIND}-session-failed"
  ERRTAIL=$(tail -c 300 "$ERR" 2>/dev/null | tr '\n\r' '  ' | tr -d '\\' | sed "s/'/''/g")
  ELAPSED=$(( $(date +%s) - START ))
  BODY="[${KIND} session FAILED] The session ended without a report: dsh exited rc=$RC after ${ELAPSED}s and wrote nothing. This row exists so the window cannot be mistaken for a deliberate stand-aside. Whether it placed an order is answerable from logs/agent_trades.jsonl and the account fills, not from this row. Last stderr: ${ERRTAIL:-<empty>}"
  say "WARN session produced no report (rc=$RC) - recording the failure"
fi
if MYSQL_PWD="$TRADEBOT_DB_PASSWORD" mysql -h "$TRADEBOT_DB_HOST" -u"$TRADEBOT_DB_USER" \
     "$TRADEBOT_DB_SCHEMA" \
     -e "INSERT INTO session_notes (at, kind, body, refs) VALUES
         (NOW(), '$NOTE_KIND', '$BODY', 'agent_trade_session.sh; $OUT');" 2>/dev/null; then
  say "recorded session_notes ($NOTE_KIND)"
else
  say "WARN could not record session_notes"
fi

exit 0
