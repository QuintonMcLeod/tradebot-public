#!/bin/bash
# Description: Background monitor for Tradebot pyramiding events

LOG_FILE="$HOME/.config/tradebot-sci/logs/tradebot.log"
echo "Monitoring $LOG_FILE for pyramid entries (scale_ins)..."

tail -F "$LOG_FILE" | while read -r line; do
    if echo "$line" | grep -qE "(scale_in|add_to_position)"; then
        # Check settings for Debug Notifications
        CONFIG_FILE="$HOME/.config/tradebot-sci/config.json"
        DEBUG_NOTIFS="false"
        if command -v jq >/dev/null 2>&1 && [ -f "$CONFIG_FILE" ]; then
            DEBUG_NOTIFS=$(jq -r '.global.GUI_DEBUG_NOTIFICATIONS // false' "$CONFIG_FILE" 2>/dev/null)
        fi

        # Play a sound or send a notification if desktop environment is active AND debug mode is on
        if [ "$DEBUG_NOTIFS" = "true" ]; then
            notify-send -u critical "Tradebot SCI: PYRAMID FIRED!" "$line" 2>/dev/null || true
        fi
        # Also log to a special found file so user can check easily
        echo "$line" >> "$HOME/.config/tradebot-sci/logs/pyramids_found.txt"
        echo -e "\n[!] Pyramid Fired: $line"
    fi
done
