"""Dev entrypoint for running the simulation-only Trade by SCI assistant.

This module mirrors `scripts/run_dev_bot.py` but lives under `src/` so test runs
that set `PYTHONPATH=src` can import it as `scripts.run_dev_bot`.
"""

from __future__ import annotations

import argparse

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
    args = parser.parse_args()
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
            import os

            os.environ["BUG_BYPASS_SCHEDULE"] = "1"
        iterations = None if args.continuous else args.iterations
        run_bot(
            iterations=iterations,
            skip_schedule=args.continuous,
            sabbath_override=sabbath_override,
        )


if __name__ == "__main__":
    main()

