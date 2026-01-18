#!/usr/bin/env python3
"""
AI Helper - Use DeepSeek API to assist with code tasks.
Dramatically reduces Claude's token usage by offloading coding work.
"""
import os
import sys
import json
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install -q requests")
    import requests


def call_deepseek(prompt: str, *, model: str = "deepseek-chat") -> str:
    """Call DeepSeek API with a prompt and return the response."""
    api_key = os.getenv("DEEPSEEK_KEY")
    if not api_key:
        return "ERROR: DEEPSEEK_KEY environment variable not set"

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 8000
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def apply_task_2_draggable_settings(task_file: Path, app_file: Path) -> dict:
    """Use DeepSeek to apply Task 2: Draggable Settings Window."""

    # Read the task instructions
    with open(task_file) as f:
        task_instructions = f.read()

    # Read relevant portion of app.py (the GlassSettingsDialog class)
    with open(app_file) as f:
        lines = f.readlines()

    # Find GlassSettingsDialog class
    start_line = None
    for i, line in enumerate(lines):
        if "class GlassSettingsDialog" in line:
            start_line = i
            break

    if start_line is None:
        return {"error": "GlassSettingsDialog class not found"}

    # Extract ~100 lines around the class definition
    context_start = max(0, start_line - 10)
    context_end = min(len(lines), start_line + 100)
    context = "".join(lines[context_start:context_end])

    prompt = f"""You are a Python code assistant. Apply the following task to the code.

TASK INSTRUCTIONS:
{task_instructions}

CURRENT CODE (lines {context_start+1}-{context_end}):
```python
{context}
```

INSTRUCTIONS:
1. Provide the EXACT code changes needed
2. Use this format:
   - FIND: <exact old code>
   - REPLACE: <exact new code>
3. Provide multiple FIND/REPLACE pairs if needed
4. Match indentation exactly (use spaces, not tabs)

OUTPUT FORMAT:
```
CHANGE 1:
FIND:
<exact code to find>

REPLACE:
<exact replacement code>

CHANGE 2:
...
```
"""

    response = call_deepseek(prompt)
    return {
        "task": "Task 2: Draggable Settings",
        "response": response,
        "context_lines": f"{context_start+1}-{context_end}"
    }


def apply_task_3_ticker_dropdown(task_file: Path, app_file: Path) -> dict:
    """Use DeepSeek to apply Task 3: Ticker Selection Dropdown."""

    with open(task_file) as f:
        task_instructions = f.read()

    prompt = f"""You are a Python code assistant. Analyze this task and provide implementation guidance.

TASK INSTRUCTIONS:
{task_instructions}

This task has 4 steps:
1. Modify MainWindow.__init__ for UI elements (around line 935)
2. Add member variable _chart_locked_symbol (around line 680)
3. Add 3 helper methods after _set_candle_tf()
4. Modify _tick_candles() method

For EACH step, provide:
- Exact search string to find the location
- Exact replacement code with correct indentation

Use this format for each step:
```
STEP N: <description>

SEARCH FOR:
<exact text to search for>

REPLACE WITH:
<exact replacement including context>
```

Be precise with indentation (4 spaces per level, no tabs).
"""

    response = call_deepseek(prompt)
    return {
        "task": "Task 3: Ticker Selection Dropdown",
        "response": response
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Helper for applying GUI tasks")
    parser.add_argument("task", choices=["task2", "task3", "both"], help="Which task to apply")
    parser.add_argument("--dry-run", action="store_true", help="Just show AI output, don't apply")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    app_file = repo_root / "src/tradebot_sci/gui/app.py"

    if args.task in ["task2", "both"]:
        print("=" * 60)
        print("TASK 2: Draggable Settings Window")
        print("=" * 60)
        task_file = repo_root / "TASK_2_DRAGGABLE_SETTINGS_WINDOW.md"
        result = apply_task_2_draggable_settings(task_file, app_file)

        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            print(f"\nContext: Lines {result['context_lines']}")
            print(f"\nDeepSeek Response:\n{result['response']}")
            print("\n" + "=" * 60)

    if args.task in ["task3", "both"]:
        print("\n" + "=" * 60)
        print("TASK 3: Ticker Selection Dropdown")
        print("=" * 60)
        task_file = repo_root / "TASK_3_TICKER_SELECTION_DROPDOWN.md"
        result = apply_task_3_ticker_dropdown(task_file, app_file)

        print(f"\nDeepSeek Response:\n{result['response']}")
        print("\n" + "=" * 60)

    if not args.dry_run:
        print("\nTo apply these changes, review the output above and manually apply using Edit tool.")

    print("\n✓ AI Helper complete")
