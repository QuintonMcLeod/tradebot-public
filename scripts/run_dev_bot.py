"""Dev entrypoint for running the simulation-only Trade by SCI assistant.

This script is for research/education only. It does NOT place real orders or connect to brokers.
"""

from __future__ import annotations

import argparse
import os
import sys

# [ANTIGRAVITY FIX] Force local source usage (overrides installed package) to pick up hotfixes
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)
print(f"ANTIGRAVITY: Running with sys.path[0]={sys.path[0]}")

from tradebot_sci.runtime.loop import run_bot


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Trade by SCI dev bot (simulation or scheduled)")
    parser.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="Number of loop iterations to run (ignored in scheduled mode)",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Use scheduled sessions from config instead of fixed iterations",
    )
    parser.add_argument(
        "--bug",
        action="store_true",
        help="Bypass scheduled mode even if sessions are configured (debug outside windows)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously, respecting per-symbol market hours even when sessions would pause",
    )
    sabbath_group = parser.add_mutually_exclusive_group()
    sabbath_group.add_argument(
        "--sabbath",
        action="store_true",
        help="Block new entries between Friday and Saturday sundown (fixed 18:00 local unless configured)",
    )
    sabbath_group.add_argument(
        "--no-sabbath",
        action="store_true",
        help="Explicitly disable Sabbath blocking even if the profile enables it",
    )
    parser.add_argument(
        "--profile",
        type=str,
        help="Override the trading profile (e.g. forex_intraday)",
    )
    args = parser.parse_args()

    if args.profile:
        print(f"ANTIGRAVITY: Overriding profile to '{args.profile}'")
        os.environ["APP_PROFILE"] = args.profile

    sabbath_override: bool | None
    if args.sabbath:
        sabbath_override = True
    elif args.no_sabbath:
        sabbath_override = False
    else:
        sabbath_override = None
    if args.scheduled and not args.bug:
        from tradebot_sci.runtime.loop import run_scheduled_bot

        run_scheduled_bot(sabbath_override=sabbath_override)
    else:
        if args.bug:
            os.environ["BUG_BYPASS_SCHEDULE"] = "1"
        iterations = None if args.continuous else args.iterations
        run_bot(
            iterations=iterations,
            skip_schedule=args.continuous,
            sabbath_override=sabbath_override,
        )


if __name__ == "__main__":
    main()
