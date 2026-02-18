#!/bin/bash
# CLI command to invoke Codex and have it work on the symbol fix task

cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"

cat <<'CODEX_TASK' | ./scripts/codex

Read the file SYMBOL_FIX_TASK.md to understand the GUI symbol selection problem.

Your task:
1. Choose and implement the best solution (Option 1, 2, or 3 from the task file)
2. Test that the fix works by checking if BTCUSD is fetched instead of SPY
3. Write your report by APPENDING to /home/qchan/Scripts/letsgo.txt

Use this exact format when appending to letsgo.txt:

[CODEX] Symbol Selection Fix Report
-----------------------------------
Approach: [which option you chose]
Files Modified: [list of files]
Changes Made: [describe what you changed]
Reasoning: [why this approach is best]
Testing: [what you verified]
Status: [COMPLETE/FAILED]
-----------------------------------

After writing your report to letsgo.txt, the file will be monitored by Claude (AI-2) who will read your findings.

CODEX_TASK
