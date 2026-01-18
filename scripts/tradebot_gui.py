#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _configure_qt_platform() -> None:
    if not os.getenv("QT_OPENGL"):
        os.environ["QT_OPENGL"] = "software"
    if not os.getenv("LIBGL_ALWAYS_SOFTWARE"):
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
    if not os.getenv("QT_CHARTS_USE_OPENGL"):
        os.environ["QT_CHARTS_USE_OPENGL"] = "0"
    if os.getenv("QT_QPA_PLATFORM"):
        return
    if os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        return
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    print(
        "WARN: No DISPLAY/WAYLAND_DISPLAY detected; running Qt in offscreen mode.",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Tradebot SCI GUI")
    parser.add_argument(
        "--settings",
        action="store_true",
        help="Open only the settings dialog for debugging",
    )
    args = parser.parse_args()

    # Ensure `src/` imports work when running directly.
    repo = _repo_root()
    os.chdir(repo)
    sys.path.insert(0, str(repo / "src"))
    _configure_qt_platform()

    try:
        if args.settings:
            from tradebot_sci.gui.settings_dialog import run_settings_only
            return int(run_settings_only(repo_root=repo))
        else:
            from tradebot_sci.gui.app import run_app
            import tradebot_sci.gui.app
            return int(run_app(repo_root=repo))
    except Exception as exc:
        print(
            "ERROR: Qt GUI is not available.\n\n"
            "Install the optional GUI deps:\n"
            "  poetry install --with gui\n\n"
            f"Import error: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
