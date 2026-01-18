#!/bin/bash
# Iteratively fix syntax errors using manual fixes

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MAX_ITERATIONS=50
iteration=0

while [ $iteration -lt $MAX_ITERATIONS ]; do
    echo "==================================="
    echo "Iteration $((iteration + 1))/$MAX_ITERATIONS"
    echo "==================================="

    # Try to compile
    if python -m py_compile src/tradebot_sci/gui/app.py 2>&1 | tee /tmp/compile_error.txt; then
        echo ""
        echo "✅ SUCCESS! File compiles!"
        exit 0
    fi

    # Extract error line
    error_line=$(grep "line [0-9]*" /tmp/compile_error.txt | head -1 | grep -oP 'line \K[0-9]+')

    if [ -z "$error_line" ]; then
        echo "❌ Could not extract error line number"
        cat /tmp/compile_error.txt
        exit 1
    fi

    echo "Error at line $error_line"

    # Show the problematic line
    sed -n "${error_line}p" src/tradebot_sci/gui/app.py | cat -A

    # Check for specific patterns and fix them
    line_content=$(sed -n "${error_line}p" src/tradebot_sci/gui/app.py)

    # Pattern 1: Lone "**"
    if [ "$line_content" == "**" ]; then
        echo "Fixing: Removing lone ** at line $error_line"
        sed -i "${error_line}d" src/tradebot_sci/gui/app.py
        iteration=$((iteration + 1))
        continue
    fi

    # Pattern 2: Lines with "**…" (ellipsis character)
    if echo "$line_content" | grep -q '**…'; then
        echo "Fixing: Removing line with **… at line $error_line"
        sed -i "${error_line}d" src/tradebot_sci/gui/app.py
        iteration=$((iteration + 1))
        continue
    fi

    # Pattern 3: Invalid ellipsis character
    if echo "$line_content" | grep -qP '\u2026'; then
        echo "Fixing: Replacing ellipsis with ..."
        sed -i "${error_line}s/…/.../g" src/tradebot_sci/gui/app.py
        iteration=$((iteration + 1))
        continue
    fi

    echo "❌ Unknown error pattern, cannot auto-fix"
    cat /tmp/compile_error.txt
    exit 1

done

echo "❌ Max iterations reached"
exit 1
