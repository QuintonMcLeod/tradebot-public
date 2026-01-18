"""ICC strategy constants and default values.

This module centralizes magic numbers used across the strategy engine
to improve maintainability and make configuration more explicit.
"""

# Structure scoring weights
HTF_TREND_WEIGHT = 0.6
LTF_TREND_WEIGHT = 0.4
VOLATILITY_WEIGHT = 0.2

# ICC continuation constraints
MAX_BARS_AFTER_SWEEP = 15  # Maximum bars between sweep and continuation
CONTINUATION_BREAKOUT_LOOKBACK = 5  # Lookback for continuation BOS detection

# Grading thresholds
GRADE_A_PLUS_THRESHOLD = 0.95
GRADE_A_THRESHOLD = 0.9
GRADE_A_MINUS_THRESHOLD = 0.85
GRADE_B_PLUS_THRESHOLD = 0.8
GRADE_B_THRESHOLD = 0.75
GRADE_B_MINUS_THRESHOLD = 0.7
GRADE_C_PLUS_THRESHOLD = 0.65
GRADE_C_THRESHOLD = 0.6
GRADE_C_MINUS_THRESHOLD = 0.55
GRADE_D_THRESHOLD = 0.5
GRADE_F_PLUS_THRESHOLD = 0.4
GRADE_F_THRESHOLD = 0.3

# Session health defaults
DEFAULT_SESSION_RANGE_MULTIPLIER = 1.1
DEFAULT_SESSION_VOLUME_MULTIPLIER = 1.1
DEFAULT_SESSION_OVERLAP_START_HOUR = 12  # UTC
DEFAULT_SESSION_OVERLAP_END_HOUR = 16  # UTC

# ATR invalidation buffer
DEFAULT_ATR_PERIOD = 14
DEFAULT_ATR_MULTIPLIER = 0.5

# Swing detection defaults
DEFAULT_SWING_LOOKBACK = 2
DEFAULT_MIN_SWINGS = 3
DEFAULT_TREND_STRENGTH_FLOOR = 0.5
