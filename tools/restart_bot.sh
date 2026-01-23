#!/bin/bash
# Script to restart the tradebot after code fixes

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[RESTART] Restarting tradebot..."

# Find and kill the running bot process
BOT_PID=$(ps aux | grep "run_dev_bot.py --continuous" | grep -v grep | awk '{print $2}')

if [ -n "$BOT_PID" ]; then
    echo "[RESTART] Found bot process: $BOT_PID"
    echo "[RESTART] Sending SIGTERM..."
    kill $BOT_PID

    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! ps -p $BOT_PID > /dev/null 2>&1; then
            echo "[RESTART] Bot stopped gracefully"
            break
        fi
        sleep 1
    done

    # Force kill if still running
    if ps -p $BOT_PID > /dev/null 2>&1; then
        echo "[RESTART] Force killing bot..."
        kill -9 $BOT_PID
        sleep 1
    fi
else
    echo "[RESTART] No bot process found (may already be stopped)"
fi

# Wait a moment for cleanup
sleep 2

# Restart the bot in tmux session if it exists
if tmux has-session -t tradebot 2>/dev/null; then
    echo "[RESTART] Restarting in existing tmux session 'tradebot'..."
    tmux send-keys -t tradebot:view.0 C-c
    sleep 1
    tmux send-keys -t tradebot:view.0 "cd '$PROJECT_DIR' && '$PROJECT_DIR'/.venv/bin/python scripts/run_dev_bot.py --continuous" C-m
    echo "[RESTART] Bot restarted in tmux session"
else
    echo "[RESTART] Starting bot in new background process..."
    cd "$PROJECT_DIR"
    nohup "$PROJECT_DIR"/.venv/bin/python scripts/run_dev_bot.py --continuous > /dev/null 2>&1 &
    echo "[RESTART] Bot started (PID: $!)"
fi

sleep 3

# Verify bot is running
NEW_PID=$(ps aux | grep "run_dev_bot.py --continuous" | grep -v grep | awk '{print $2}')
if [ -n "$NEW_PID" ]; then
    echo "[RESTART] ✓ Bot successfully restarted (PID: $NEW_PID)"
    echo "[RESTART] Waiting 5 seconds for initialization..."
    sleep 5
    echo "[RESTART] Restart complete!"
    exit 0
else
    echo "[RESTART] ✗ Failed to restart bot"
    exit 1
fi
