#!/usr/bin/env python3
"""
Automated Tradebot Monitor & Fix Script
Uses Qwen to monitor logs every 30 minutes and fix bugs for 6 hours
"""

import time
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
MONITORING_DURATION_HOURS = 6
CHECK_INTERVAL_MINUTES = 30
LOG_DIR = Path(__file__).parent.parent / "logs"
REPORT_FILE = Path(__file__).parent.parent / "MONITORING_REPORT.md"

def log_message(msg):
    """Print timestamped message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    sys.stdout.flush()

def run_qwen_analysis():
    """Call Qwen via API to analyze logs and suggest fixes"""
    log_message("Calling Qwen to analyze logs...")

    prompt = f"""You are monitoring a cryptocurrency trading bot that needs to execute 15 trades/day for exponential compounding.

**Your task:**
1. Analyze the most recent logs in: {LOG_DIR}/tradebot.log
2. Count trades executed in the last 30 minutes
3. Identify any NEW bugs preventing trading
4. Write code fixes for any bugs found
5. Report trading frequency status

**Focus areas:**
- Phantom positions (null avg_price, null entry_price)
- Multi-position guard rail blocks
- Stop loss tracking failures
- Symbol mapping errors
- "Stand aside" rejection rate
- Actual trades executed vs target

**Expected frequency:** 15 trades/day = ~0.625 trades/hour = ~0.31 trades per 30min

**Output format:**
1. TRADES_LAST_30MIN: [count]
2. BUGS_FOUND: [list or "none"]
3. FIXES_APPLIED: [list or "none"]
4. STATUS: [on_track / below_target / critical]

**If bugs found, provide fixes using this exact format:**

```FIX_START
FILE: relative/path/to/file.py
OLD_CODE:
[exact code to replace, must match perfectly]
NEW_CODE:
[replacement code]
FIX_END```

Example:
```FIX_START
FILE: src/tradebot_sci/runtime/loop.py
OLD_CODE:
if not multi_enabled:
    other_positions = sorted(sym for sym in open_position_symbols if sym != symbol)
NEW_CODE:
if not multi_enabled:
    other_positions = sorted(
        sym for sym in open_position_symbols
        if sym != symbol and not executor.get_open_position_snapshot(sym).get('is_dust', False)
    )
FIX_END```

**IMPORTANT:**
- OLD_CODE must match the file exactly (including whitespace)
- Can provide multiple FIX_START/FIX_END blocks
- After providing fixes, add: RESTART_REQUIRED: yes

Read the BUG_REPORT_TRADING_FREQUENCY.md for context on known issues."""

    try:
        # Use qwen2.5-coder:32b model via ollama
        result = subprocess.run(
            ["ollama", "run", "qwen2.5-coder:32b", prompt],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=LOG_DIR.parent
        )

        if result.returncode == 0:
            log_message("✓ Qwen analysis complete")
            return result.stdout
        else:
            log_message(f"✗ Qwen returned error code {result.returncode}")
            return f"ERROR: {result.stderr}"

    except subprocess.TimeoutExpired:
        log_message("✗ Qwen analysis timed out (5 min)")
        return "ERROR: Timeout"
    except FileNotFoundError:
        log_message("✗ ollama not found - is it installed?")
        return "ERROR: ollama not found"
    except Exception as e:
        log_message(f"✗ Exception calling Qwen: {e}")
        return f"ERROR: {e}"

def apply_code_fixes(qwen_output):
    """Parse and apply code fixes from Qwen's output"""
    import re

    project_root = LOG_DIR.parent
    fixes_applied = 0

    # Find all FIX_START...FIX_END blocks
    fix_pattern = r'```FIX_START\s+FILE:\s*(.+?)\s+OLD_CODE:\s*(.+?)\s+NEW_CODE:\s*(.+?)\s+FIX_END```'
    matches = re.finditer(fix_pattern, qwen_output, re.DOTALL)

    for match in matches:
        file_path = match.group(1).strip()
        old_code = match.group(2).strip()
        new_code = match.group(3).strip()

        full_path = project_root / file_path

        try:
            # Read current file content
            if not full_path.exists():
                log_message(f"✗ File not found: {file_path}")
                continue

            with open(full_path, 'r') as f:
                content = f.read()

            # Apply replacement
            if old_code in content:
                new_content = content.replace(old_code, new_code, 1)

                # Write back
                with open(full_path, 'w') as f:
                    f.write(new_content)

                log_message(f"✓ Applied fix to: {file_path}")
                fixes_applied += 1
            else:
                log_message(f"✗ OLD_CODE not found in: {file_path}")
                log_message(f"  Expected: {old_code[:100]}...")

        except Exception as e:
            log_message(f"✗ Error applying fix to {file_path}: {e}")

    return fixes_applied

def restart_bot():
    """Restart the trading bot after code fixes"""
    log_message("Executing bot restart script...")

    try:
        restart_script = Path(__file__).parent / "restart_bot.sh"
        result = subprocess.run(
            ["bash", str(restart_script)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return True
        else:
            log_message(f"Restart script error: {result.stderr}")
            return False

    except Exception as e:
        log_message(f"Failed to restart bot: {e}")
        return False

def append_to_report(cycle_num, qwen_output):
    """Append Qwen's analysis to monitoring report"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(REPORT_FILE, "a") as f:
        f.write(f"\n## Cycle {cycle_num} - {timestamp}\n\n")
        f.write("```\n")
        f.write(qwen_output)
        f.write("\n```\n")
        f.write("\n---\n")

def initialize_report():
    """Create initial monitoring report"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""# Tradebot Monitoring Report

**Start Time:** {timestamp}
**Duration:** {MONITORING_DURATION_HOURS} hours
**Check Interval:** {CHECK_INTERVAL_MINUTES} minutes
**Target:** 15 trades/day (~0.625 trades/hour)

**Monitoring Strategy:**
- Qwen analyzes logs every 30 minutes
- Identifies bugs and writes fixes automatically
- Tracks trading frequency vs target
- Reports critical issues immediately

---

"""

    with open(REPORT_FILE, "w") as f:
        f.write(content)

    log_message(f"Initialized report: {REPORT_FILE}")

def main():
    """Main monitoring loop"""
    log_message("=" * 60)
    log_message("TRADEBOT MONITORING & AUTO-FIX SYSTEM")
    log_message("=" * 60)
    log_message(f"Duration: {MONITORING_DURATION_HOURS} hours")
    log_message(f"Check interval: {CHECK_INTERVAL_MINUTES} minutes")
    log_message(f"Log directory: {LOG_DIR}")
    log_message(f"Report file: {REPORT_FILE}")
    log_message("=" * 60)

    # Initialize report
    initialize_report()

    # Calculate end time
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=MONITORING_DURATION_HOURS)

    log_message(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message(f"End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message("")

    cycle = 0

    try:
        while datetime.now() < end_time:
            cycle += 1
            remaining = end_time - datetime.now()

            log_message(f"CYCLE {cycle} - {remaining.total_seconds()/3600:.1f} hours remaining")

            # Run Qwen analysis
            qwen_output = run_qwen_analysis()

            # Save to report
            append_to_report(cycle, qwen_output)

            # Apply any code fixes
            fixes_count = apply_code_fixes(qwen_output)
            if fixes_count > 0:
                log_message(f"📝 Applied {fixes_count} code fix(es)")

            # Check if restart is required
            if "RESTART_REQUIRED: yes" in qwen_output:
                log_message("🔄 Restarting bot with new code...")
                restart_result = restart_bot()
                if restart_result:
                    log_message("✓ Bot restarted successfully")
                else:
                    log_message("✗ Bot restart failed - check logs")

            # Parse output for critical alerts
            if "STATUS: critical" in qwen_output.lower():
                log_message("⚠️  CRITICAL STATUS DETECTED")
            elif "STATUS: below_target" in qwen_output.lower():
                log_message("⚠️  Below target trading frequency")
            elif "STATUS: on_track" in qwen_output.lower():
                log_message("✓ Trading frequency on track")

            # Extract trade count if available
            for line in qwen_output.split('\n'):
                if 'TRADES_LAST_30MIN' in line:
                    log_message(f"  → {line.strip()}")
                elif 'BUGS_FOUND' in line:
                    log_message(f"  → {line.strip()}")
                elif 'FIXES_APPLIED' in line:
                    log_message(f"  → {line.strip()}")

            log_message("")

            # Sleep until next check (unless this is the last cycle)
            if datetime.now() < end_time:
                sleep_time = CHECK_INTERVAL_MINUTES * 60
                next_check = datetime.now() + timedelta(seconds=sleep_time)
                log_message(f"Next check at {next_check.strftime('%H:%M:%S')}")
                log_message(f"Sleeping for {CHECK_INTERVAL_MINUTES} minutes...")
                log_message("")
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        log_message("")
        log_message("⚠️  Monitoring interrupted by user")
        log_message(f"Completed {cycle} cycles before interruption")

    # Final summary
    log_message("")
    log_message("=" * 60)
    log_message("MONITORING SESSION COMPLETE")
    log_message("=" * 60)
    log_message(f"Total cycles: {cycle}")
    log_message(f"Duration: {(datetime.now() - start_time).total_seconds()/3600:.1f} hours")
    log_message(f"Full report: {REPORT_FILE}")
    log_message("")
    log_message("Review the report for detailed analysis and fixes applied.")
    log_message("=" * 60)

if __name__ == "__main__":
    main()
