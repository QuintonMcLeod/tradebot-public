#!/usr/bin/env python3
"""Test to see what's happening with the capital check."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tradebot_sci.config.loader import load_settings

settings = load_settings()

print("Broker settings:")
print(f"  max_dollar_risk_per_symbol: ${settings.broker.max_dollar_risk_per_symbol}")
print()

capital = 1000.0
max_risk = settings.broker.max_dollar_risk_per_symbol

print(f"Test capital: ${capital:.2f}")
print(f"Max risk: ${max_risk:.2f}")
print(f"Required capital (max_risk * 2): ${max_risk * 2:.2f}")
print()

if capital < max_risk * 2:
    print(f"FAIL: ${capital:.2f} < ${max_risk * 2:.2f}")
else:
    print(f"PASS: ${capital:.2f} >= ${max_risk * 2:.2f}")
