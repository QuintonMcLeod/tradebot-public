#!/bin/bash
# Script to invoke Codex CLI and have it report to letsgo.txt

cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"

# Prepare the instruction for Codex
cat > /tmp/codex_instruction.txt <<'EOF'
Read SYMBOL_FIX_TASK.md and implement the cleanest solution to fix the GUI symbol selection issue.

After implementing the fix, write your findings to /home/qchan/Scripts/letsgo.txt in this format:

[CODEX] Symbol Selection Fix - Implementation Report
========================================
**Approach Chosen**: [Option 1/2/3]
**Files Modified**: [list files]
**Changes Made**: [describe changes]
**Reasoning**: [why this approach]
**Testing Needed**: [how to verify]
========================================

Then restart the GUI and verify BTCUSD is fetched instead of SPY.
EOF

# Launch Codex in a terminal
echo "Invoking Codex CLI..."
./scripts/codex < /tmp/codex_instruction.txt
