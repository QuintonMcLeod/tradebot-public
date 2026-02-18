#!/bin/bash
# CLI command to invoke Gemini and have it verify the symbol fix

cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"

cat <<'GEMINI_TASK' | gemini

First, read /home/qchan/Scripts/letsgo.txt to see Codex's implementation report.

Your task:
1. Kill any running GUI processes: pkill -9 -f "python.*tradebot"
2. Clear Python cache: rm -rf src/**/__pycache__
3. Start the GUI: timeout 120 ./scripts/tradebot.sh --gui > /tmp/gemini_gui_test.log 2>&1 &
4. Wait 25 seconds for GUI to initialize
5. Check the logs for Coinbase fetch URLs - look for BTCUSD or BTC-USD (NOT SPY)
6. Verify the GUI process is still running (no crashes)
7. Write your verification report by APPENDING to /home/qchan/Scripts/letsgo.txt

Use this exact format when appending to letsgo.txt:

[GEMINI] Verification Report
----------------------------
GUI Process: [PID and uptime in seconds]
Symbol Fetched: [BTCUSD or SPY - check Coinbase URLs in logs]
Sample URL: [paste one Coinbase URL from logs]
Crashes: [YES or NO]
Status: [✅ WORKING - fetches BTCUSD | ❌ BROKEN - still fetches SPY]
----------------------------

After writing your report to letsgo.txt, the file will be monitored by Claude (AI-2).

GEMINI_TASK
