#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${SESSION_NAME:-tradebot}"
LOG_FILE="${LOG_FILE:-logs/tradebot.log}"
COMMENTARY_SCRIPT="${COMMENTARY_SCRIPT:-tools/commentary_tail.py}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux not found. Install it (e.g. apt install tmux) or use a regular terminal split." >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BOT_CMD="${BOT_CMD:-PYTHONPATH=src EXECUTE_TRADES=false poetry run python scripts/run_dev_bot.py --continuous}"

# In tmux, commands are typically run via a non-interactive shell (no .bashrc),
# so env vars like ${CHATGPT_KEY} won't be available unless we explicitly load them.
ENV_BOOTSTRAP="source \"$HOME/.bashrc\" >/dev/null 2>&1 || true; set -a; [ -f \"$ROOT_DIR/.env\" ] && source \"$ROOT_DIR/.env\" >/dev/null 2>&1; set +a"

tmux has-session -t "$SESSION_NAME" 2>/dev/null && {
  echo "Attaching to existing tmux session: $SESSION_NAME"
  exec tmux attach -t "$SESSION_NAME"
}

tmux new-session -d -s "$SESSION_NAME" -n view

# Persist the bot cmd/settings into the tmux session so `./scripts/tradebot.sh --restart`
# can preserve execution mode (e.g. EXECUTE_TRADES=true) without requiring flags again.
tmux set-environment -t "$SESSION_NAME" TRADEBOT_BOT_CMD "$BOT_CMD" 2>/dev/null || true
if echo "$BOT_CMD" | grep -q "EXECUTE_TRADES=true"; then
  tmux set-environment -t "$SESSION_NAME" TRADEBOT_EXECUTE_TRADES "true" 2>/dev/null || true
elif echo "$BOT_CMD" | grep -q "EXECUTE_TRADES=false"; then
  tmux set-environment -t "$SESSION_NAME" TRADEBOT_EXECUTE_TRADES "false" 2>/dev/null || true
fi

# Split right commentary pane first (capture pane ids so we always target the correct panes).
TOP_LEFT_PANE="$(tmux display-message -p -t "$SESSION_NAME:0.0" "#{pane_id}")"
RIGHT_PANE="$(tmux split-window -t "$SESSION_NAME:0.0" -h -P -F "#{pane_id}")"

# Split bottom-left candle pane (under the log).
BOTTOM_LEFT_PANE="$(tmux split-window -t "$TOP_LEFT_PANE" -v -P -F "#{pane_id}")"

# Top-left: styled log tail
tmux send-keys -t "$TOP_LEFT_PANE" "$ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && mkdir -p logs && (PYTHONPATH=src poetry run python tools/log_tail_ui.py --log \"$LOG_FILE\" --follow --interval 0.5 || tail -F \"$LOG_FILE\")" C-m

# Bottom-left: candles (IBKR delayed)
# Bottom-left: candles (IBKR or CCXT)
CANDLES_CMD="PYTHONPATH=src poetry run python tools/candles_launcher.py --log \"$LOG_FILE\" --follow --interval 15 --rotate-seconds 30 --refresh-seconds 15 --render rich"
tmux send-keys -t "$BOTTOM_LEFT_PANE" "$ENV_BOOTSTRAP; printf '\033[2J\033[H' && $CANDLES_CMD" C-m

# Right: commentary
COMMENTARY_CMD="PYTHONPATH=src poetry run python \"$COMMENTARY_SCRIPT\" --log \"$LOG_FILE\" --follow --interval 3"
if [ "${COMMENTARY_LLM:-}" = "" ]; then
  COMMENTARY_CMD="COMMENTARY_LLM=internal $COMMENTARY_CMD"
elif [ "${COMMENTARY_LLM:-off}" != "off" ]; then
  COMMENTARY_CMD="COMMENTARY_LLM=\"${COMMENTARY_LLM}\" $COMMENTARY_CMD"
fi
tmux send-keys -t "$RIGHT_PANE" "$ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && $COMMENTARY_CMD" C-m

# Window 1: bot runner (kept separate so the dashboard stays clean).
tmux new-window -t "$SESSION_NAME:1" -n bot
tmux send-keys -t "$SESSION_NAME:1" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; $BOT_CMD" C-m

# Window 2: holdings page (structured holdings snapshots from the log).
tmux new-window -t "$SESSION_NAME:2" -n holdings
tmux send-keys -t "$SESSION_NAME:2" "$ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && PYTHONPATH=src poetry run python tools/holdings_tail.py --log \"$LOG_FILE\" --follow --interval 3" C-m

# Back to dashboard.
tmux select-window -t "$SESSION_NAME:0"
tmux set-option -t "$SESSION_NAME" remain-on-exit on >/dev/null

echo "tmux dashboard started:"
echo "- Window 0 (view): left-top=log, left-bottom=candles, right=commentary"
echo "- Window 1 (bot): running BOT_CMD"
echo "- Window 2 (holdings): open positions + guard timers"
echo "Tips: Ctrl-b then n/p to switch windows; Ctrl-b then d to detach."
exec tmux attach -t "$SESSION_NAME"
