#!/bin/bash
# Quick-start script for automated monitoring

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
MONITOR_SCRIPT="$SCRIPT_DIR/tools/monitor_and_fix.py"
LOG_FILE="$SCRIPT_DIR/monitoring_session.log"

echo "=========================================="
echo "TRADEBOT AUTO-MONITORING SYSTEM"
echo "=========================================="
echo ""
echo "This will:"
echo "  • Monitor logs every 30 minutes for 6 hours"
echo "  • Use Qwen to identify and fix bugs"
echo "  • Track trading frequency (target: 15/day)"
echo "  • Generate detailed report"
echo ""
echo "Log output: $LOG_FILE"
echo "Report: $SCRIPT_DIR/MONITORING_REPORT.md"
echo ""
echo "Press Ctrl+C to stop monitoring early"
echo ""
echo "=========================================="
echo ""

# Check if ollama is available
if ! command -v ollama &> /dev/null; then
    echo "ERROR: ollama not found!"
    echo "Please install ollama first: https://ollama.com"
    exit 1
fi

# Check if qwen model is available
if ! ollama list | grep -q "qwen2.5-coder:32b"; then
    echo "WARNING: qwen2.5-coder:32b model not found"
    echo "Pulling model... (this may take a while)"
    ollama pull qwen2.5-coder:32b
fi

# Run the monitoring script
echo "Starting monitoring session..."
echo ""

python3 "$MONITOR_SCRIPT" 2>&1 | tee "$LOG_FILE"

echo ""
echo "=========================================="
echo "Monitoring session ended."
echo "Check $SCRIPT_DIR/MONITORING_REPORT.md for results"
echo "=========================================="
