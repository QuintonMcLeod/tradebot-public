"""Memory watchdog: make a slow leak name its own cause.

Why this exists
---------------
On 2026-09-19 the paper runner was OOM-killed after reaching an 8.1 GB memory
peak over three days, having started at about 228 MB. Nothing in the logs said
what grew, so the cause could not be attributed after the fact and the run was
lost. Guessing at a leak that only shows up during market hours is not
practical; measuring it is.

This thread samples the process cheaply and often, and when memory has actually
grown it takes an object histogram by type. That histogram is the useful part:
it names the class that is accumulating, which is what turns "it uses 8 GB" into
"it is retaining N of object X".

Cost is deliberately near zero until something grows: RSS every interval, and
the expensive gc walk only on growth.
"""
from __future__ import annotations

import gc
import logging
import os
import threading
import time
from collections import Counter

logger = logging.getLogger(__name__)

# Report every this many seconds.
_INTERVAL = int(os.getenv("TRADEBOT_MEMWATCH_INTERVAL", "600"))
# Take an object histogram when RSS has grown by at least this much since the
# last histogram, in MB.
_GROWTH_MB = float(os.getenv("TRADEBOT_MEMWATCH_GROWTH_MB", "64"))
# Rows to keep in the histogram comparison.
_TOP_N = 20


def _read_status() -> dict:
    out = {"rss_mb": 0.0, "threads": 0, "fds": 0}
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    out["rss_mb"] = int(line.split()[1]) / 1024.0
                elif line.startswith("Threads:"):
                    out["threads"] = int(line.split()[1])
    except Exception:
        pass
    try:
        out["fds"] = len(os.listdir("/proc/self/fd"))
    except Exception:
        pass
    return out


def _histogram() -> Counter:
    """Object counts by type name. Expensive; only called on growth."""
    counts: Counter = Counter()
    for obj in gc.get_objects():
        try:
            counts[type(obj).__name__] += 1
        except Exception:
            continue
    return counts


def _fmt(c: Counter, prev: Counter | None = None) -> str:
    if prev is None:
        top = c.most_common(_TOP_N)
    else:
        # Rank by growth, so a new accumulator stands out from steady state.
        deltas = [(name, n - prev.get(name, 0), n) for name, n in c.items()]
        top = [(name, f"+{d} (now {n})") for name, d, n in
               sorted(deltas, key=lambda t: -t[1])[:_TOP_N] if d > 0]
    return ", ".join(f"{k}={v}" for k, v in top) or "no growth"


def start(queue_stats=None) -> threading.Thread:
    """Start the watchdog. `queue_stats` optionally returns ws queue depth."""

    def run() -> None:
        prev_hist: Counter | None = None
        baseline_rss: float | None = None
        while True:
            try:
                time.sleep(_INTERVAL)
                st = _read_status()
                if baseline_rss is None:
                    baseline_rss = st["rss_mb"]
                qs = ""
                if queue_stats is not None:
                    try:
                        s = queue_stats()
                        qs = f" ws_queue={s.get('depth')}/{s.get('maxsize')} dropped={s.get('dropped')}"
                    except Exception:
                        pass
                # Compare against the RSS at the last histogram (or the start).
                # Previously this required prev_hist to be set, but the histogram
                # is only taken when growth is detected, so it could never fire.
                last_rss = getattr(run, "_last_hist_rss", 0.0) or baseline_rss
                grown = st["rss_mb"] - last_rss >= _GROWTH_MB
                if not grown:
                    logger.info(
                        f"[MEMWATCH] rss={st['rss_mb']:.0f}MB base={baseline_rss:.0f}MB "
                        f"threads={st['threads']} fds={st['fds']}{qs}"
                    )
                    continue

                hist = _histogram()
                logger.warning(
                    f"[MEMWATCH] RSS grew to {st['rss_mb']:.0f}MB from "
                    f"{baseline_rss:.0f}MB at start. Largest growing object types: "
                    f"{_fmt(hist, prev_hist)}{qs}"
                )
                prev_hist = hist
                run._last_hist_rss = st["rss_mb"]
            except Exception as e:  # never let the watchdog kill the bot
                logger.error(f"[MEMWATCH] sampling failed: {e}")

    run._last_hist_rss = 0.0
    t = threading.Thread(target=run, name="MemoryWatch", daemon=True)
    t.start()
    logger.info(f"[MEMWATCH] started: sampling every {_INTERVAL}s, histogram on "
                f"{_GROWTH_MB:.0f}MB growth")
    return t
