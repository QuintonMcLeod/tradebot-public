"""Enums for trend classification and ICC phases.

This module provides type-safe enumerations for trend directions and ICC phases
to replace string literals and improve code maintainability.
"""
from enum import Enum


class TrendDirection(str, Enum):
    """Trend direction based on swing structure (HH/HL vs LH/LL)."""

    LONG = "long"  # Higher highs + higher lows (HH/HL)
    SHORT = "short"  # Lower highs + lower lows (LH/LL)
    NEUTRAL = "neutral"  # No clear trend or mixed structure

    def __str__(self) -> str:
        """Return the string value for serialization and comparison."""
        return self.value


class ICCPhase(str, Enum):
    """ICC trading phases per Trade By SCI methodology."""

    TREND = "trend"  # HTF/LTF aligned, no correction yet
    CORRECTION = "correction"  # Liquidity sweep in progress
    CONTINUATION = "continuation"  # Sweep + continuation confirmed (A+ entry)
    CHOP = "chop"  # HTF/LTF misaligned or neutral, no clear structure
