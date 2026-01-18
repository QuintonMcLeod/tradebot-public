# Logging & Environmental Issues Addendum
**Date:** January 8, 2026 (19:15 EST)
**Scope:** Log pollution and environmental configuration issues

---

## Issue #1: Coinbase API HTML Error Responses Polluting Logs

### Problem

**Coinbase API returns HTML error pages** (502 Bad Gateway) instead of JSON when experiencing server issues. The CCXT library logs the **entire HTML response**, causing massive log pollution.

### Evidence

```
2026-01-08 19:12:44 [WARNING] tradebot_sci.broker.ccxt_broker - [CCXT] fetch_open_orders DOGE/USDT failed: coinbase GET https://api.coinbase.com/api/v3/brokerage/orders/historical/batch?order_status=OPEN&product_id=DOGE-USDT&limit=100 502 Bad Gateway <html>
  <head>
    <title>Coinbase</title>
    <style type="text/css">html{line-height:1.15;-webkit-text-size-adjust:100%}...
    [62,000+ characters of HTML/CSS omitted]
```

### Root Cause

**Code Location:** `src/tradebot_sci/broker/ccxt_broker.py`

The CCXT library exception messages include the full HTTP response body, and when Coinbase returns an HTML error page instead of JSON, the entire HTML document (including embedded CSS/fonts) gets logged.

### Impact

- **Log files grow to 967KB** with mostly HTML content
- **Log analysis becomes impossible** - can't grep for trading decisions
- **Performance degradation** - large log files slow down tail/grep operations
- **Storage waste** - HTML error pages repeated hundreds of times

### Recommendation

**Immediate Fix Required:**

Modify error logging in `ccxt_broker.py` to truncate HTML responses:

```python
def _log_ccxt_error(self, operation: str, symbol: str, error: Exception):
    error_msg = str(error)

    # Truncate HTML error responses to prevent log pollution
    if '<html' in error_msg.lower() or '<body' in error_msg.lower():
        # Extract just the HTTP status and first line
        lines = error_msg.split('\n')
        error_msg = f"{lines[0]} [HTML response truncated]"
    elif len(error_msg) > 500:
        error_msg = error_msg[:500] + "... [truncated]"

    logger.warning(f"[CCXT] {operation} {symbol} failed: {error_msg}")
```

**Priority:** HIGH
- Affects log readability and analysis
- Not trading-critical but severely impacts debugging

---

## Issue #2: .bashrc Welcome Banner Pollution (Environment)

### Problem

Your `~/.bashrc` displays a welcome banner with ASCII art, calendars, and system info for **all shell sessions**, including **non-interactive shells**. This causes:

1. **Claude's bash commands** showing banner output
2. **Script execution** polluted with banner text
3. **Potential log pollution** if scripts redirect stderr

### Evidence

Every bash command executed shows:
```
[H[2J[3J
░█░█░█▀▀░█░░░█▀▀░█▀█░█▄█░█▀▀░░░░░░░▄▀▄░█▀▀░█░█░█▀█░█▀█░█
░█▄█░█▀▀░█░░░█░░░█░█░█░█░█▀▀░░░░░░░█\█░█░░░█▀█░█▀█░█░█░▀
░▀░▀░▀▀▀░▀▀▀░▀▀▀░▀▀▀░▀░▀░▀▀▀░▄▀░░░░░▀\░▀▀▀░▀░▀░▀░▀░▀░▀

Today is:              Thu Jan 8 19:15:09 EST 2026
Kernel Information:    Linux 6.17.0-8-generic x86_64
Qchan uptime is        3 days, 17:16, 1 user, load average: 3.56

[calendars and Hebrew date information]
```

### Root Cause

Your `~/.bashrc` doesn't check for interactive shell mode before displaying the banner:

```bash
# Current (WRONG):
echo "Welcome banner..."
cal
# ... etc

# Should be (CORRECT):
if [[ $- == *i* ]]; then
    echo "Welcome banner..."
    cal
    # ... etc
fi
```

The `$-` variable contains shell options, and `i` is present only for interactive shells.

### Impact

- **Not affecting tradebot** - bot doesn't source .bashrc directly
- **Affects Claude's debugging** - every bash command shows banner
- **Affects manual scripts** - any script execution polluted
- **Potential tmux issues** - if tmux panes source .bashrc

### Recommendation

**Fix your ~/.bashrc:**

Wrap all banner/greeting code in an interactive check:

```bash
# At the top of ~/.bashrc, wrap your banner section:
if [[ $- == *i* ]]; then
    # Clear screen and display banner
    clear

    # Your ASCII art banner
    echo -e "\033[0;1;34;94m░█░█░█▀▀..."
    # ... all your banner code ...

    # Calendars
    cal
    hdate

    # System info
    echo "Today is: $(date)"
    # ... etc
fi

# Rest of .bashrc (aliases, functions, etc.) stays outside the check
```

**Priority:** MEDIUM
- Doesn't affect trading
- Improves debugging experience
- Prevents script pollution

---

## Issue #3: tradebot.sh ENV_BOOTSTRAP Sources .bashrc

### Related Problem

The `tradebot.sh` script **intentionally sources .bashrc** to load environment variables in tmux panes:

**File:** `scripts/tradebot.sh:15`
```bash
ENV_BOOTSTRAP="source \"$HOME/.bashrc\" >/dev/null 2>&1 || true; set -a; [ -f \"$ROOT_DIR/.env\" ] && source \"$ROOT_DIR/.env\" >/dev/null 2>&1; set +a"
```

The `>/dev/null 2>&1` **should suppress the banner**, but:
- The banner uses ANSI escape codes that may bypass stderr
- Some terminal emulators render ANSI codes before redirect takes effect

### Impact

Currently **MINIMAL** - the redirect appears to be working for the bot itself. The banner pollution is primarily affecting Claude's debugging bash commands, not the bot's operation.

### Recommendation

**No immediate fix needed** for the bot - the redirect is sufficient.

However, **fixing your .bashrc** (Issue #2) will eliminate this concern entirely.

---

## Summary

| Issue | Severity | Impact | Fix Location | Priority |
|-------|----------|--------|--------------|----------|
| **#1: Coinbase HTML Errors** | HIGH | Log pollution, debugging difficulty | `ccxt_broker.py` | HIGH |
| **#2: .bashrc Banner** | MEDIUM | Claude debugging, script pollution | `~/.bashrc` | MEDIUM |
| **#3: ENV_BOOTSTRAP** | LOW | Already mitigated by redirect | N/A | LOW |

**Recommended Action Order:**
1. **Fix Issue #1** - Add HTML truncation to CCXT error logging
2. **Fix Issue #2** - Wrap .bashrc banner in interactive check
3. **Monitor Issue #3** - No action needed if #2 is fixed

---

**Addendum Prepared By:** Claude (AI Assistant)
**Date:** January 8, 2026 (19:15 EST)
**Status:** ⚠️ **TWO ISSUES - Recommended Fixes**
