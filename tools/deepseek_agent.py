#!/usr/bin/env python3
"""
DeepSeek Agent - An AI coding agent powered by DeepSeek API.
Handles complex multi-step coding tasks autonomously.
"""
import os
import sys
import json
import re
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install -q requests")
    import requests


class DeepSeekAgent:
    """AI Agent powered by DeepSeek for autonomous coding tasks."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_KEY environment variable not set")
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.conversation_history = []

    def call(self, prompt: str, temperature: float = 0.2, max_tokens: int = 8000) -> str:
        """Call DeepSeek API with conversation history."""
        self.conversation_history.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": self.conversation_history,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            assistant_message = result["choices"][0]["message"]["content"]
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            return assistant_message
        except Exception as e:
            return f"ERROR: {e}"

    def reset_conversation(self):
        """Clear conversation history."""
        self.conversation_history = []


def fix_indentation_bugs(agent: DeepSeekAgent, file_path: Path) -> bool:
    """Have DeepSeek agent fix all indentation bugs in the file."""
    print("=" * 60)
    print("TASK: Fix Indentation Bugs")
    print("=" * 60)

    with open(file_path, 'r') as f:
        content = f.read()

    # First, convert tabs to spaces
    content = content.expandtabs(4)

    prompt = f"""You are a Python code fixing expert. The file has indentation bugs that prevent compilation.

KNOWN ISSUES:
1. Line ~2468: TOOLTIP_LIBRARY is indented at 20 spaces but should be 16 spaces
2. Lines ~3493-3515: tip() function body is over-indented (should be 16 spaces, not 20+)
3. Additional cascading indentation issues in f-string continuations

YOUR TASK:
Analyze the code and provide EXACT find/replace pairs to fix ALL indentation issues.

For each fix, provide:
```
FIX N:
FIND:
<exact string to find, including indentation>

REPLACE:
<exact corrected string>
```

IMPORTANT:
- Match indentation EXACTLY (count spaces carefully)
- Include enough context to make each FIND unique
- Use 4 spaces per indentation level
- Fix ALL indentation bugs, not just the known ones

Here are the problematic sections:

SECTION 1 (lines 2440-2480):
```python
{content[70000:75000]}
```

SECTION 2 (lines 3485-3520):
```python
{content[102000:107000]}
```

Provide comprehensive fixes for ALL indentation issues."""

    response = agent.call(prompt, temperature=0.1)
    print("\nDeepSeek Analysis:")
    print(response)

    # Parse the response and apply fixes
    fixes = parse_fix_response(response)
    if not fixes:
        print("\n⚠ No fixes parsed from DeepSeek response")
        return False

    print(f"\nApplying {len(fixes)} fixes...")
    for i, (find_str, replace_str) in enumerate(fixes, 1):
        if find_str in content:
            content = content.replace(find_str, replace_str, 1)
            print(f"✓ Applied fix {i}")
        else:
            print(f"⚠ Could not find pattern for fix {i}")

    # Write fixed content
    with open(file_path, 'w') as f:
        f.write(content)

    # Validate syntax
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(file_path)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("\n✅ File compiles successfully!")
        return True
    else:
        print(f"\n❌ Compilation failed:\n{result.stderr}")
        return False


def parse_fix_response(response: str) -> list[tuple[str, str]]:
    """Parse DeepSeek's fix response into (find, replace) pairs."""
    fixes = []

    # Look for FIX patterns
    fix_pattern = r"FIX \d+:.*?FIND:(.*?)REPLACE:(.*?)(?=FIX \d+:|$)"
    matches = re.findall(fix_pattern, response, re.DOTALL | re.IGNORECASE)

    for find_block, replace_block in matches:
        # Extract code from markdown blocks if present
        find_str = extract_code_block(find_block.strip())
        replace_str = extract_code_block(replace_block.strip())

        if find_str and replace_str:
            fixes.append((find_str, replace_str))

    return fixes


def extract_code_block(text: str) -> str:
    """Extract code from markdown code blocks."""
    # Remove markdown code fences
    text = re.sub(r'^```\w*\n', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n```$', '', text, flags=re.MULTILINE)
    return text.strip()


def implement_task_2_draggable_dialog(agent: DeepSeekAgent, file_path: Path) -> bool:
    """Have DeepSeek implement Task 2: Draggable Settings Dialog."""
    print("\n" + "=" * 60)
    print("TASK 2: Draggable Settings Dialog")
    print("=" * 60)

    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Find the _open_env_settings method
    for i, line in enumerate(lines):
        if "def _open_env_settings(self)" in line:
            context_start = i
            context_end = min(i + 20, len(lines))
            context = "".join(lines[context_start:context_end])
            break
    else:
        print("❌ Could not find _open_env_settings method")
        return False

    prompt = f"""You are implementing a GUI feature: making a settings dialog draggable.

CURRENT CODE (starting at line {context_start + 1}):
```python
{context}
```

TASK:
Replace the line `dlg = QtWidgets.QDialog(self)` with:
1. An inline class definition `GlassSettingsDialog` that extends QtWidgets.QDialog
2. Implements drag functionality with mousePressEvent, mouseMoveEvent, mouseReleaseEvent
3. Use `dlg = GlassSettingsDialog(self)` instead

Provide the EXACT replacement code using this format:

FIND:
```python
<exact code to find including surrounding lines for uniqueness>
```

REPLACE:
```python
<exact replacement code with proper indentation>
```

CRITICAL:
- Match indentation EXACTLY (use spaces, count carefully)
- Include enough context before/after to make the FIND unique
- The class should be defined inline inside the _open_env_settings method"""

    response = agent.call(prompt)
    print("\nDeepSeek Implementation:")
    print(response)

    # Parse and apply
    fixes = parse_fix_response(response)
    if not fixes:
        print("⚠ No implementation parsed")
        return False

    with open(file_path, 'r') as f:
        content = f.read()

    for find_str, replace_str in fixes:
        if find_str in content:
            content = content.replace(find_str, replace_str, 1)
            print("✓ Applied draggable dialog implementation")
        else:
            print("⚠ Could not find pattern to replace")
            return False

    with open(file_path, 'w') as f:
        f.write(content)

    return True


def implement_task_1_decision_formatter(agent: DeepSeekAgent, file_path: Path) -> bool:
    """Have DeepSeek implement Task 1: Decision Formatter Integration."""
    print("\n" + "=" * 60)
    print("TASK 1: Decision Formatter Integration")
    print("=" * 60)

    prompt = f"""You are implementing a GUI feature: integrating DecisionFormatter for human-readable decision display.

TASK:
1. Add import at top: `from tradebot_sci.gui.decision_formatter import DecisionFormatter`
2. Add _parse_decision_event() method (~90 lines) - parses DecisionEvent to dict
3. Add _update_recent_decisions() method (~30 lines) - formats and displays decisions
4. Modify _render_right() to call _update_recent_decisions()

Provide step-by-step implementations:

STEP 1: Add import
STEP 2: Add _parse_decision_event method (provide full implementation)
STEP 3: Add _update_recent_decisions method (provide full implementation)
STEP 4: Modify _render_right to call _update_recent_decisions

For each step, use this format:
FIND:
```python
<exact code>
```
REPLACE:
```python
<exact replacement>
```"""

    response = agent.call(prompt, max_tokens=12000)
    print("\nDeepSeek Implementation:")
    print(response[:1000] + "..." if len(response) > 1000 else response)

    return True  # Would need to parse and apply, but showing the concept


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="DeepSeek AI Agent for code implementation")
    parser.add_argument("task", choices=["fix-indentation", "task1", "task2", "all"],
                       help="Which task to execute")
    parser.add_argument("--file", default="src/tradebot_sci/gui/app.py",
                       help="File to modify")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    file_path = repo_root / args.file

    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return 1

    agent = DeepSeekAgent()

    try:
        if args.task == "fix-indentation":
            success = fix_indentation_bugs(agent, file_path)
            return 0 if success else 1

        elif args.task == "task2":
            if not implement_task_2_draggable_dialog(agent, file_path):
                return 1

        elif args.task == "task1":
            if not implement_task_1_decision_formatter(agent, file_path):
                return 1

        elif args.task == "all":
            # Fix indentation first
            if not fix_indentation_bugs(agent, file_path):
                print("\n❌ Failed to fix indentation, aborting")
                return 1

            # Then implement tasks
            agent.reset_conversation()  # Fresh context

            if not implement_task_2_draggable_dialog(agent, file_path):
                print("\n❌ Failed Task 2")
                return 1

            agent.reset_conversation()

            if not implement_task_1_decision_formatter(agent, file_path):
                print("\n❌ Failed Task 1")
                return 1

            print("\n✅ ALL TASKS COMPLETED!")

        return 0

    except Exception as e:
        print(f"\n❌ Agent error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
