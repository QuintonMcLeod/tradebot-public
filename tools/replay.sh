#!/bin/sh
# Deterministic replay launcher: fixes PYTHONHASHSEED (set/dict iteration order)
# and runs paper_replay.py. Use for reproducible backtests/A-B.
exec env PYTHONHASHSEED="${PYTHONHASHSEED:-0}" python3 "$(dirname "$0")/paper_replay.py" "$@"
