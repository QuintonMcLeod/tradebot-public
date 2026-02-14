#!/usr/bin/env python3
"""Verify that the ledger daemon regexes correctly parse the updated EXIT/Tournament log formats."""
import re
import sys

# ── Regexes (copied from ledger_daemon.py, post-fix) ──
RE_EXIT = re.compile(
    r"\[EXIT\]\s+(?P<reason>[^:]+):\s+"
    r"(?P<symbol>[A-Z_]{3,10})\s+"
    r"(?P<pnl_sign>[+-])\$(?P<pnl_val>[\d.]+)"
    r"(?:\s+\(Pct=(?P<pct>[+-]?[\d.]+)%\))?"
    r"(?:.*?Duration=(?P<duration>[^|]+))?"
    r"(?:.*?Est\.\s*Spread\s*Cost:\s*\$(?P<spread>[\d.]+))?"
)

RE_TOURNAMENT = re.compile(
    r"Tournament Won by\s+(?P<strategy>\w+)"
)

RE_SIDE = re.compile(r"position=(?P<side>SHORT|LONG)", re.IGNORECASE)

# ── Test Cases ──
TESTS = [
    # --- Tournament ---
    {
        "name": "Tournament regex matches actual log",
        "line": "2026-02-14 16:17:44 [INFO] tradebot_sci.strategy.variants.meta_sci - [META-SCI] Tournament Won by ROBOCOP (Score: None)",
        "regex": RE_TOURNAMENT,
        "expected": {"strategy": "ROBOCOP"},
    },
    {
        "name": "Tournament regex matches another strategy",
        "line": "2026-02-14 16:15:07 [INFO] tradebot_sci.strategy.variants.meta_sci - [META-SCI] Tournament Won by RUBBERBAND_REAPER (Score: None)",
        "regex": RE_TOURNAMENT,
        "expected": {"strategy": "RUBBERBAND_REAPER"},
    },

    # --- Paper EXIT with Duration ---
    {
        "name": "Paper EXIT with duration (SL)",
        "line": "[PAPER] [EXIT] Paper SL: LINKUSD -$45.53 (Pct=-0.39%) position=SHORT | Entry=9.12588 Exit=9.13866 | Duration=0m 4s | Est. Spread Cost: $58.35",
        "regex": RE_EXIT,
        "strip_paper": True,
        "expected": {"reason": "Paper SL", "symbol": "LINKUSD", "pnl_sign": "-", "pnl_val": "45.53", "pct": "-0.39", "duration": "0m 4s ", "spread": "58.35"},
    },

    # --- OANDA EXIT with Duration (NEW FORMAT) ---
    {
        "name": "OANDA SL/TP EXIT with duration",
        "line": "[EXIT] OANDA SL/TP: EUR_USD +$1.23 (Pct=0.45%) position=LONG | Duration=5m 23s | Est. Spread Cost: $0.0180",
        "regex": RE_EXIT,
        "expected": {"reason": "OANDA SL/TP", "symbol": "EUR_USD", "pnl_sign": "+", "pnl_val": "1.23", "pct": "0.45", "duration": "5m 23s ", "spread": "0.0180"},
    },
    {
        "name": "OANDA Manual/Signal EXIT with duration and side",
        "line": "[EXIT] Manual/Signal: USDCAD -$0.50 (Pct=-0.10%) position=SHORT | Duration=1h 2m 30s | Est. Spread Cost: $0.0200 (OANDA 1.5 pips)",
        "regex": RE_EXIT,
        "expected": {"reason": "Manual/Signal", "symbol": "USDCAD", "pnl_sign": "-", "pnl_val": "0.50", "pct": "-0.10", "duration": "1h 2m 30s ", "spread": "0.0200"},
    },
    {
        "name": "OANDA EXIT with N/A duration",
        "line": "[EXIT] OANDA SL/TP: GBP_USD -$2.00 (Pct=-0.80%) position=SHORT | Duration=N/A | Est. Spread Cost: $0.0300",
        "regex": RE_EXIT,
        "expected": {"reason": "OANDA SL/TP", "symbol": "GBP_USD", "pnl_sign": "-", "pnl_val": "2.00", "pct": "-0.80", "duration": "N/A ", "spread": "0.0300"},
    },

    # --- Side detection ---
    {
        "name": "Side detection - SHORT",
        "line": "[EXIT] OANDA SL/TP: EUR_USD +$1.23 (Pct=0.45%) position=SHORT | Duration=5m 23s | Est. Spread Cost: $0.0180",
        "regex": RE_SIDE,
        "expected": {"side": "SHORT"},
    },
    {
        "name": "Side detection - LONG",
        "line": "[EXIT] Manual/Signal: USDCAD -$0.50 (Pct=-0.10%) position=LONG | Duration=1h 2m 30s | Est. Spread Cost: $0.0200",
        "regex": RE_SIDE,
        "expected": {"side": "LONG"},
    },
]


def run_tests():
    passed = 0
    failed = 0
    for t in TESTS:
        line = t["line"]
        if t.get("strip_paper"):
            line = line.replace("[PAPER] ", "").replace("[PAPER]", "")
        m = t["regex"].search(line)
        if not m:
            print(f"  ❌ FAIL: {t['name']} — no match")
            print(f"       Line: {line}")
            failed += 1
            continue

        ok = True
        for key, expected_val in t["expected"].items():
            actual = m.group(key)
            if actual != expected_val:
                # Allow stripped whitespace match for duration
                if actual and actual.strip() == expected_val.strip():
                    continue
                print(f"  ❌ FAIL: {t['name']} — {key}: expected '{expected_val}', got '{actual}'")
                ok = False
                failed += 1
                break
        if ok:
            print(f"  ✅ PASS: {t['name']}")
            passed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TESTS)} tests")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
