#!/usr/bin/env bash
# Health line for the Tradebot SCI paper runner.
#
# WHY THIS EXISTS. The forward paper test has already been truncated once by a
# silent death: incident 9, the kernel OOM kill of 2026-09-19, which ended three
# days of accumulated test after the runner reached 8.1 GB. Nobody noticed until
# it was discovered by hand the next day. A forward test that stops without
# saying so is worse than one that never ran, because the record then looks like
# a quiet market instead of a dead process.
#
# So this writes one line of arithmetic every run: is it up, how much memory,
# and at what rate is that memory growing. The rate is the number that matters.
# The old leak ran at roughly 102 MB an hour and nothing measured it.
#
# Measured on 2026-10-10: 233.9 MB RSS after 29.4 hours, against 228 MB at start,
# so the 2026-09-19 leak is NOT reproducing in this run. That is why a rate is
# recorded rather than a pass or fail.
#
# Usage:
#   scripts/paper_runner_health.sh            # record a sample, warn on change
#   scripts/paper_runner_health.sh --status   # print the current line, write nothing
#
# It always exits 0. A monitoring job that reports failure for having nothing to
# report is incident 16, and systemd flags it.
#
# It never places an order, never restarts the runner and never touches a
# credential. Restarting is a decision with evidence, not a side effect of a
# health check.

set -uo pipefail

REPO="/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
LOGDIR="$REPO/logs"
SAMPLES="$LOGDIR/paper_runner_health.jsonl"
WARNLOG="$LOGDIR/paper_runner_health.log"
# Overridable so the not-running branch can be tested without stopping the real
# runner. A warning path that has never been executed is not a warning path.
UNIT="${TB_HEALTH_UNIT:-tradebot-paper.service}"
# Warn well before the 8.1 GB that killed it, and above the ~250 MB a healthy run
# sits at, so the warning means something.
RSS_WARN_MB=1500
STATUS_ONLY=0
[ "${1:-}" = "--status" ] && STATUS_ONLY=1

mkdir -p "$LOGDIR"
say() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >>"$WARNLOG"; }

show=$(systemctl --user show "$UNIT" \
        -p ActiveState -p SubState -p MainPID -p NRestarts -p MemoryCurrent \
        -p MemoryPeak -p ActiveEnterTimestampMonotonic 2>/dev/null) || show=""

field() { printf '%s\n' "$show" | sed -n "s/^$1=//p" | head -1; }

active=$(field ActiveState); [ -n "$active" ] || active="unknown"
sub=$(field SubState)
pid=$(field MainPID);        [ -n "$pid" ] || pid=0
nrestarts=$(field NRestarts); [ -n "$nrestarts" ] || nrestarts=0
mem=$(field MemoryCurrent);  [ -n "$mem" ] || mem=0
peak=$(field MemoryPeak);    [ -n "$peak" ] || peak=0

rss_mb=$(awk -v b="$mem"   'BEGIN{ if (b+0 > 0) printf "%.1f", b/1048576; else print "0.0" }')
peak_mb=$(awk -v b="$peak" 'BEGIN{ if (b+0 > 0) printf "%.1f", b/1048576; else print "0.0" }')

# Uptime in seconds, from the monotonic start stamp against /proc/uptime.
uptime_s=0
start_mono=$(field ActiveEnterTimestampMonotonic)
if [ -n "$start_mono" ] && [ "$start_mono" != "0" ] && [ -r /proc/uptime ]; then
    uptime_s=$(awk -v s="$start_mono" '{ printf "%d", ($1*1000000 - s)/1000000 }' /proc/uptime)
    [ "$uptime_s" -lt 0 ] && uptime_s=0
fi

# Memory growth in MB per hour, against the newest earlier sample within six
# hours. This is the number that tells a leak from a steady state.
trend="null"
if [ -s "$SAMPLES" ]; then
    trend=$(python3 - "$SAMPLES" "$rss_mb" "$uptime_s" <<'PY' 2>/dev/null || printf 'null'
import json, sys, datetime
path, rss_now, up_now = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
now = datetime.datetime.now(datetime.timezone.utc)
best = None
for line in open(path, "r", errors="replace"):
    try:
        row = json.loads(line)
    except Exception:
        continue
    ts = row.get("ts")
    if not ts:
        continue
    try:
        t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        continue
    age = (now - t).total_seconds()
    if 600 <= age <= 21600 and row.get("uptime_s", 0) and row.get("uptime_s", 0) < up_now:
        best = row
if best is None:
    print("null")
else:
    hours = (up_now - float(best.get("uptime_s", 0))) / 3600.0
    if hours <= 0.05:
        print("null")
    else:
        print(f"{(rss_now - float(best.get('rss_mb', 0))) / hours:.1f}")
PY
)
fi

line=$(printf '{"ts":"%s","unit":"%s","active":"%s","sub":"%s","pid":%s,"restarts":%s,"rss_mb":%s,"peak_mb":%s,"uptime_s":%s,"rss_mb_per_hour":%s}' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$UNIT" "$active" "$sub" "$pid" "$nrestarts" "$rss_mb" "$peak_mb" "$uptime_s" "$trend")

if [ "$STATUS_ONLY" = "1" ]; then
    printf '%s\n' "$line"
    exit 0
fi

printf '%s\n' "$line" >>"$SAMPLES"

# Warn on a CHANGE of condition, never once per run. Ten identical notifications
# for one condition was a recorded failure of the secretary's, and the cause was
# keying the dedupe on the schedule instead of on the condition.
warn=""
case "$active" in
    active) ;;
    *) warn="runner NOT ACTIVE (state=$active/$sub, restarts=$nrestarts). Restart with: systemctl --user reset-failed $UNIT && systemd-run --user --unit=${UNIT%.service} --collect /home/qchan/.local/bin/${UNIT%.service}.sh" ;;
esac
if [ -z "$warn" ]; then
    over=$(awk -v r="$rss_mb" -v w="$RSS_WARN_MB" 'BEGIN{ print (r+0 > w+0) ? 1 : 0 }')
    [ "$over" = "1" ] && warn="runner memory ${rss_mb} MB is above the ${RSS_WARN_MB} MB warning line after ${uptime_s}s (peak ${peak_mb} MB). The 2026-09-19 OOM death was at 8.1 GB."
fi
if [ -z "$warn" ]; then
    [ "$nrestarts" != "0" ] && warn="runner has restarted $nrestarts time(s) since the unit was loaded."
fi

if [ -n "$warn" ]; then
    last=$(tail -n 1 "$WARNLOG" 2>/dev/null | sed 's/^[^ ]* //' | cut -c1-60)
    if [ "$last" != "$(printf '%s' "$warn" | cut -c1-60)" ]; then
        say "WARN $warn"
    else
        say "STILL $warn"
    fi
fi

exit 0
