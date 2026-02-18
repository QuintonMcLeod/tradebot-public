#!/bin/bash
# Run Gemini AI analysis on expected P&L for $60 crypto trading bot

cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"

echo "==================================================================="
echo "Running Gemini Profit Analysis for $60 Crypto Trading Bot"
echo "==================================================================="
echo ""
echo "This will generate a probability analysis of expected returns"
echo "based on your bot's configuration and trading parameters."
echo ""
echo "Analysis will be saved to: GEMINI_PROFIT_ANALYSIS_RESULTS.md"
echo ""
echo "==================================================================="
echo ""

# Check if gemini command exists
if command -v gemini &> /dev/null; then
    # Use gemini CLI if available
    cat GEMINI_PROFIT_ANALYSIS_PROMPT.md | gemini > GEMINI_PROFIT_ANALYSIS_RESULTS.md
    echo "✅ Analysis complete! Results saved to GEMINI_PROFIT_ANALYSIS_RESULTS.md"
else
    # Otherwise, just display the prompt for manual copy-paste
    echo "⚠️  Gemini CLI not found. Please copy the prompt below and paste it into Gemini:"
    echo ""
    echo "==================================================================="
    cat GEMINI_PROFIT_ANALYSIS_PROMPT.md
    echo ""
    echo "==================================================================="
    echo ""
    echo "Copy the above prompt and paste it into:"
    echo "  - https://gemini.google.com"
    echo "  - Or your local Gemini interface"
    echo ""
    echo "Then save the response to: GEMINI_PROFIT_ANALYSIS_RESULTS.md"
fi
