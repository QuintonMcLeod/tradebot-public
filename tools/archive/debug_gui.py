#!/usr/bin/env python3
"""Quick GUI debug - check what's populated in the symbol selector."""
import sys
from pathlib import Path

# Add src to path
repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "src"))

from tradebot_sci.config.loader import load_settings

settings = load_settings()
print("Configured symbols:", settings.market.symbols)
print("Number of symbols:", len(settings.market.symbols) if settings.market.symbols else 0)
