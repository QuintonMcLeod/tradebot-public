from __future__ import annotations

import copy
import os
import re
from datetime import datetime
from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
from pathlib import Path
from typing import Any
import yaml
from tradebot_sci.gui.shared import THEMES
from tradebot_sci.runtime.capital_tuner import (
    AUTO_TUNE_ENABLED_ENV,
    AUTO_TUNE_LAST_BROKER_ENV,
    AUTO_TUNE_LAST_EQUITY_ENV,
    AUTO_TUNE_LAST_TS_ENV,
    apply_tune_to_env,
    fetch_account_equity,
    load_log_excerpt,
    request_capital_tune,
    sanitize_context,
)


def _merge_dotenv(path: Path, updates: dict[str, str]) -> None:
    """Merge updates into a .env file, preserving existing content."""
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    present: set[str] = set()
    out_lines: list[str] = []
    for raw in existing:
        line = raw
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            eq_pos = stripped.find("=")
            if eq_pos > 0:
                k = stripped[:eq_pos].strip()
                if k in updates:
                    line = f"{k}={updates[k]}"
                    present.add(k)
        out_lines.append(line)
    for k, v in sorted(updates.items()):
        if k not in present:
            out_lines.append(f"{k}={v}")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def open_settings_dialog(self: QtWidgets.QWidget, settings: Any, repo_root: Path, discovered_env_keys: list[str], dotenv_values: dict[str, str], theme_key: str = "dark") -> None:

    # Define dotenv path early so it's available in nested functions
    dotenv_path = repo_root / ".env"

    # Define the draggable dialog class inline
    class GlassSettingsDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._dragging = False
            self._drag_start_position = QtCore.QPoint()

        def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
            if event.button() == QtCore.Qt.LeftButton:
                self._dragging = True
                self._drag_start_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
            else:
                super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
            if self._dragging and event.buttons() & QtCore.Qt.LeftButton:
                self.move(event.globalPos() - self._drag_start_position)
                event.accept()
            else:
                super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
            if event.button() == QtCore.Qt.LeftButton:
                self._dragging = False
                event.accept()
            else:
                super().mouseReleaseEvent(event)

    dlg = GlassSettingsDialog(self)
    dlg.setObjectName("settingsDialog")
    dlg.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog)
    dlg.setWindowOpacity(0.96)
    dlg.setWindowTitle("Settings")
    dlg.resize(1180, 820)

    # Get the current theme using the provided theme_key parameter
    theme = THEMES.get(theme_key, THEMES["dark"])

    # Helper to create rgba colors with alpha transparency
    def rgba(hex_color: str, alpha: float) -> str:
        s = (hex_color or "").strip()
        if s.startswith("rgba(") or s.startswith("rgb("):
            return s
        if s.startswith("#") and len(s) == 7:
            r = int(s[1:3], 16)
            g = int(s[3:5], 16)
            b = int(s[5:7], 16)
            a = max(0.0, min(1.0, float(alpha)))
            return f"rgba({r},{g},{b},{a:.2f})"
        return s

    # Semi-transparent themed backgrounds for sleek, borderless dialog
    card_bg = rgba(theme.card, 0.92)  # Main dialog background (semi-transparent)
    header_bg = rgba(theme.header, 0.85)  # Selected tab background
    tab_bg = rgba(theme.card, 0.28)  # Unselected tab background
    border_soft = rgba(theme.border, 0.12)  # Subtle borders

    dlg.setStyleSheet(
        theme.qss()
        + "QDialog#settingsDialog { "
        + "  background: " + card_bg + "; "
        + "  border-radius: 16px; "
        + "  border: 1px solid " + border_soft + "; "
        + "}"
        + "QDialog#settingsDialog QWidget { background: transparent; }"
        + "QDialog#settingsDialog QTabWidget::pane { background: transparent; }"
        + "QDialog#settingsDialog QTabBar::tab { "
        + "  background: " + tab_bg + "; "
        + "  border-radius: 8px; "
        + "  padding: 8px 16px; "
        + "  margin: 2px; "
        + "}"
        + "QDialog#settingsDialog QTabBar::tab:selected { "
        + "  background: " + header_bg + "; "
        + "  font-weight: bold; "
        + "}"
        + "QDialog#settingsDialog QTabBar::tab:hover { "
        + "  background: " + rgba(theme.header, 0.38) + "; "
        + "}"
        + "QDialog#settingsDialog QGroupBox { background: transparent; }"
        + "QDialog#settingsDialog QScrollArea { background: transparent; }"
        + "QDialog#settingsDialog QScrollArea > QWidget > QWidget { background: transparent; }"
        + "QDialog#settingsDialog QPushButton { "
        + "  border-radius: 8px; "
        + "  padding: 6px 12px; "
        + "  background: " + rgba(theme.accent, 0.20) + "; "
        + "  border: 1px solid " + border_soft + "; "
        + "}"
        + "QDialog#settingsDialog QPushButton:hover { "
        + "  background: " + rgba(theme.accent, 0.35) + "; "
        + "}"
        + "QDialog#settingsDialog QCheckBox { "
        + "  spacing: 8px; "
        + "  color: " + theme.text + "; "
        + "}"
        + "QDialog#settingsDialog QCheckBox::indicator { "
        + "  width: 18px; "
        + "  height: 18px; "
        + "  border: 2px solid " + theme.accent + "; "
        + "  border-radius: 4px; "
        + "  background: " + rgba(theme.base, 0.6) + "; "
        + "}"
        + "QDialog#settingsDialog QCheckBox::indicator:hover { "
        + "  border-color: " + theme.good + "; "
        + "  background: " + rgba(theme.accent, 0.15) + "; "
        + "}"
        + "QDialog#settingsDialog QCheckBox::indicator:checked { "
        + "  background: " + theme.accent + "; "
        + "  border-color: " + theme.accent + "; "
        + "}"
        + "QDialog, QDialog * { font-size: 12pt; }"
        + "QDialog QPlainTextEdit, QDialog QTextEdit, QDialog QTableWidget { font-size: 10.5pt; }"
    )

    initial_effective: dict[str, str] = {}
    for k in discovered_env_keys:
        initial_effective[k] = self._effective_env_value(k)[0]

    info = QtWidgets.QLabel(
        "Most options are env vars. Use the tabs for common settings, or Advanced (env) for raw key/value overrides.\n"
        "Apply affects this GUI immediately. Save to .env affects future tmux runs. Restart tmux applies to the running bot."
    )
    info.setWordWrap(True)
    info.setStyleSheet(f"color: {theme.muted};")

    def read_profiles() -> list[str]:
        path = repo_root / "config" / "settings_profiles.yaml"
        if not path.exists():
            return []
        profiles: list[str] = []
        in_section = False
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.rstrip("\n")
            if line.strip() == "profiles:":
                in_section = True
                continue
            if in_section and line and not line.startswith(" "):
                break
            if in_section and line.startswith("  ") and line.strip().endswith(":") and not line.startswith("    "):
                key = line.strip()[:-1].strip()
                if key:
                    profiles.append(key)
        return profiles

    def classify(key: str) -> str:
        if key.startswith("IBKR_") or key.startswith("CCXT_") or key in {"EXCHANGE_PROVIDER", "ALTERNATIVE_BROKER"}:
            return "Broker/Market"
        if key.startswith("TRADE_SCI_") or key in {"CHATGPT_KEY"}:
            return "AI/Commentary"
        if "SABBATH" in key or "SCHEDULE" in key:
            return "Schedule/Sabbath"
        if "LOG" in key:
            return "Logging"
        return "Runtime"

    def set_override(key: str, value: str) -> None:
        v = value.strip()
        if v == "":
            self._env_overrides.pop(key, None)
            self._qsettings.remove(f"env/{key}")
            if key in dotenv_values:
                os.environ[key] = dotenv_values[key]
            else:
                os.environ.pop(key, None)
            return
        self._env_overrides[key] = v
        self._qsettings.setValue(f"env/{key}", v)
        os.environ[key] = v

    def bool_chk(key: str, label: str) -> QtWidgets.QCheckBox:
        chk = QtWidgets.QCheckBox(label)
        chk.setChecked(self._effective_env_value(key)[0].strip().lower() in {"1", "true", "yes", "on"})
        return chk

    def scroll(widget: QtWidgets.QWidget, parent: QtWidgets.QWidget = None) -> QtWidgets.QScrollArea:
        area = QtWidgets.QScrollArea(parent)
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.NoFrame)
        area.setWidget(widget)
        return area

    def tip(widget: QtWidgets.QWidget, text: str) -> None:
        raw = (text or "").strip()
        if not raw:
            return
        lines = raw.splitlines()
        key = (lines[0] or "").strip()
        summary = "\n".join(lines[1:]).strip()

        def _env_template(env_key: str, short: str) -> str:
                short = (short or "").strip()
                return (
                    f"{env_key}\n"
                    f"{'Summary: ' + short if short else 'Summary: (no short description provided)'}\n\n"
                    "What this is\n"
                    "- This is an environment variable (env var).\n"
                    "- The bot reads env vars at startup; some settings are only applied after a restart.\n\n"
                    "When it takes effect\n"
                    "- Apply (GUI): affects what THIS running GUI session shows/does.\n"
                    "- Save to .env: affects the next time you start the bot/GUI/tmux launcher.\n"
                    "- Restart tmux: restarts the terminal panes so the running bot/dashboard pick up changes.\n\n"
                    "How to use it in this GUI\n"
                    "- Change the control (toggle/dropdown/field).\n"
                    "- Click “Apply (GUI)” to apply to this running GUI session.\n"
                    "- Click “Save to .env” to persist it for future runs.\n"
                    "- Click “Restart tmux” if you want the terminal dashboard panes to pick up changes.\n\n"
                    "Tips\n"
                    "- Clearing a value (empty) usually means “fall back to defaults / profile / config file”.\n"
                    "- Most booleans accept true/false; the GUI writes consistent values for you.\n\n"
                    "Safety notes\n"
                    "- If you enable live trading, the GUI will show a confirmation prompt.\n"
                    "- Some broker settings can prevent orders even in live mode (e.g., read-only).\n"
                    "- If you are unsure, keep `EXECUTE_TRADES=false` and validate in simulation first.\n\n"
                    "Troubleshooting\n"
                    "- If a change “did nothing”, it likely requires a restart (tmux restart or relaunch).\n"
                    "- If live trading is blocked, check for a confirmation requirement or broker read-only mode.\n"
                )

        TOOLTIP_LIBRARY: dict[str, str] = {
                "GUI_AUTOSTART_BOT": (
                    "GUI_AUTOSTART_BOT\n"
                    "Automatically start the core bot process when the GUI opens.\n\n"
                    "What this does\n"
                    "- On GUI launch, the app checks whether the bot is already running.\n"
                    "- If it is NOT running, the GUI starts it using your current settings.\n"
                    "- If it IS already running, the GUI attaches to the existing logs/state (no duplicate bot).\n\n"
                    "How to use\n"
                    "- Enable this if you want the GUI to be your “one-click launcher”.\n"
                    "- Disable this if you prefer starting the bot from tmux/terminal first.\n\n"
                    "Important safety note\n"
                    "- If `EXECUTE_TRADES=true`, you will still be asked to confirm live trading in the GUI.\n"
                    "- The confirmation is there to prevent accidental live orders.\n"
                ),
                "GUI_KEEP_BOT_RUNNING": (
                    "GUI_KEEP_BOT_RUNNING\n"
                    "Keep the bot running even after you close the GUI window.\n\n"
                    "Why you’d use this\n"
                    "- You want a desktop view temporarily, but you want the bot to keep running in the background.\n"
                    "- You want tmux/terminal users to continue seeing the dashboard after the GUI closes.\n\n"
                    "How it behaves\n"
                    "- Closing the GUI will not stop the bot.\n"
                    "- The bot will keep writing to the log file and managing positions (if enabled).\n\n"
                    "How to stop the bot\n"
                    "- Use the tmux launcher to restart/stop, or stop the process from your OS tools.\n"
                    "- If live trading is enabled, always make sure you intentionally stop it.\n"
                ),
                "GUI_LOG_BROWSE": (
                    "GUI_LOG_BROWSE\n"
                    "Pick which log file the GUI (and tmux log tail) reads.\n\n"
                    "What this is\n"
                    "- The bot writes structured events (decisions, broker actions, errors) to a log file.\n"
                    "- The GUI uses that same file to populate Current Ticker, Recent Decisions, Orders, and more.\n\n"
                    "How to use\n"
                    "- Choose the active log (usually `logs/tradebot.log`).\n"
                    "- If you want historical context, you can point it to a rotated file (`logs/tradebot.log.1`, etc.).\n\n"
                    "Tip\n"
                    "- If something “looks empty”, make sure you are looking at the active log, not an older rotated log.\n"
                ),
                "TMUX_RESTART_PREVIEW": (
                    "TMUX_RESTART_PREVIEW\n"
                    "Shows the exact tmux restart command that will be executed.\n\n"
                    "Why this exists\n"
                    "- The tmux launcher (`./scripts/tradebot.sh`) is the source of truth for how the terminal dashboard is launched.\n"
                    "- When you restart panes, this preview lets you verify the command is what you expect.\n\n"
                    "How to use\n"
                    "- Review it before clicking “Restart tmux”.\n"
                    "- If you see unexpected flags (profile/mode/execute-trades), adjust settings first.\n\n"
                    "Safety note\n"
                    "- Restarting tmux panes should keep the session open and respawn bot + commentary panes inside tmux.\n"
                ),
                "GUI_BROWSE_SYNTH_STOP_STORE": (
                    "GUI_BROWSE_SYNTH_STOP_STORE\n"
                    "Choose where to store synthetic stop state on disk.\n\n"
                    "What this is\n"
                    "- The bot can persist synthetic stop details so it can manage a position safely after restarts.\n"
                    "- This button fills `SYNTH_STOP_STORE_PATH` for you.\n\n"
                    "How to use\n"
                    "- Choose a writable path (JSON file).\n"
                    "- Keep it stable (don’t change it mid-trade) unless you understand the implications.\n\n"
                    "Why it matters\n"
                    "- If this file is missing/unwritable, some safety routines may treat the position as “unprotected”.\n"
                ),
                "GUI_BROWSE_POSITION_HOLD_STORE": (
                    "GUI_BROWSE_POSITION_HOLD_STORE\n"
                    "Choose where to store position-hold/age state on disk.\n\n"
                    "What this is\n"
                    "- The bot can persist “hold rules” (e.g., minimum hold time) across restarts.\n"
                    "- This button fills `POSITION_HOLD_STORE_PATH` for you.\n\n"
                    "How to use\n"
                    "- Choose a writable path (JSON file).\n"
                    "- Keep it stable so the bot can correctly remember how old positions are.\n\n"
                    "Why it matters\n"
                    "- Without persistence, the bot may be forced into conservative safety actions after a restart.\n"
                ),
                "ENV_FILTER": (
                    "ENV_FILTER\n"
                    "Filter the Advanced env table by key.\n\n"
                    "How to use\n"
                    "- Type part of a key (case-insensitive).\n"
                    "- Examples: `IBKR_`, `CCXT_`, `TRADE_SCI_`, `COMMENTARY_`, `EXECUTE_TRADES`.\n\n"
                    "Why this exists\n"
                    "- The bot has many configuration switches; this helps you find the one you need quickly.\n"
                ),
                "ENV_TABLE_EDIT": (
                    "ENV_TABLE_EDIT\n"
                    "Advanced mode: edit raw environment variables directly.\n\n"
                    "What this is\n"
                    "- A full list of discovered env keys used by the bot and dashboard.\n"
                    "- Useful for advanced tuning or for settings that don’t have a dedicated toggle yet.\n\n"
                    "How to use\n"
                    "- Double-click a Value cell to edit it.\n"
                    "- Click “Apply (GUI)” to apply changes to the running GUI session.\n"
                    "- Click “Save to .env” to persist for future runs.\n\n"
                    "Important rules\n"
                    "- Typed controls in the other tabs take precedence when they exist.\n"
                    "- Secret keys are masked in this table; set them in the typed tabs instead.\n\n"
                    "Safety note\n"
                    "- Be careful changing broker/live-trading keys here; prefer the dedicated controls.\n"
                ),
                "BTN_APPLY": (
                    "BTN_APPLY\n"
                    "Apply changes immediately to THIS running GUI session.\n\n"
                    "What it affects\n"
                    "- Updates the GUI’s in-process overrides.\n"
                    "- Can change what the GUI displays and how it launches/restarts other components.\n\n"
                    "What it does NOT do\n"
                    "- It does not automatically rewrite your `.env` file.\n"
                    "- It does not automatically restart tmux/bot processes.\n\n"
                    "When to use\n"
                    "- When you want to test changes safely before committing them.\n"
                ),
                "BTN_SAVE_DOTENV": (
                    "BTN_SAVE_DOTENV\n"
                    "Persist your current settings to the `.env` file.\n\n"
                    "What this does\n"
                    "- Writes your selected values so future runs start the same way.\n"
                    "- Helps keep tmux/GUI behavior consistent across restarts.\n\n"
                    "When to use\n"
                    "- After you’ve confirmed the settings are correct.\n\n"
                    "Safety note\n"
                    "- Saving `EXECUTE_TRADES=true` means future runs will be configured for live trading.\n"
                    "- The GUI still asks you to confirm live trading before starting.\n"
                ),
                "BTN_RESTART_TMUX": (
                    "BTN_RESTART_TMUX\n"
                    "Restart the terminal dashboard panes (bot + commentary) inside the tmux session.\n\n"
                    "What this does\n"
                    "- Applies and saves settings, then runs the tmux restart routine.\n"
                    "- Keeps the tmux session open and respawns the panes.\n\n"
                    "When to use\n"
                    "- When you changed bot settings that only take effect on process start.\n"
                    "- When you want the terminal dashboard to match the GUI configuration.\n\n"
                    "Safety note\n"
                    "- If live trading is enabled, confirm you intended that before restarting.\n"
                ),
                "BTN_CLEAR_OVERRIDES": (
                    "BTN_CLEAR_OVERRIDES\n"
                    "Remove all GUI overrides and fall back to your baseline config.\n\n"
                    "What this does\n"
                    "- Clears settings you changed in the GUI that were not saved to `.env`.\n"
                    "- Reverts to values from `.env` and/or your shell environment.\n\n"
                    "When to use\n"
                    "- Something looks wrong and you want to return to a known-good baseline quickly.\n"
                ),
                "BTN_CLOSE": (
                    "BTN_CLOSE\n"
                    "Close this settings dialog.\n\n"
                    "Note\n"
                    "- Closing the dialog does not automatically apply changes.\n"
                    "- Use Apply / Save / Restart as needed before closing.\n"
                ),
            "PROFILE_NAME": (
                "PROFILE_NAME\n"
                "Pick a profile that defines how the bot behaves.\n\n"
                "What it controls\n"
                "- Which symbols/universe the bot scans and trades.\n"
                "- Default timeframe (e.g., 5m) and scan/decision cadence.\n"
                "- Auto-schedule behavior (equities during US hours, crypto off-hours).\n"
                "- Sabbath behavior defaults (whether new entries are blocked in the Sabbath window).\n"
                "- Risk/stop behaviors that are profile-dependent (where configured).\n\n"
                "How to use\n"
                "- Start with `auto_schedule` for “equities in-hours, crypto off-hours”.\n"
                "- Use an intraday profile for tighter cadence; use swing for slower cadence.\n\n"
                "Where it comes from\n"
                "- Profiles are defined in `config/settings_profiles.yaml` and loaded by the bot.\n"
            ),
            "PROFILE_HTF_TIMEFRAME": (
                "PROFILE_HTF_TIMEFRAME\n"
                "Override the Higher Timeframe (HTF) used for ICC structure trend.\n\n"
                "ICC guidance\n"
                "- HTF defines the macro structure (HH/HL vs LH/LL).\n"
                "- Default is 4h unless your profile specifies otherwise.\n\n"
                "How to use\n"
                "- Use 4h for standard ICC structure.\n"
                "- Use 1h only if your ICC plan is intentionally faster and validated.\n"
                "- Leave Auto to keep the profile default.\n"
            ),
            "PROFILE_LTF_TIMEFRAME": (
                "PROFILE_LTF_TIMEFRAME\n"
                "Override the Lower Timeframe (LTF) used for ICC execution structure.\n\n"
                "ICC guidance\n"
                "- LTF is where sweeps + BOS + continuation triggers are validated.\n"
                "- If unset, the bot uses the profile candle timeframe.\n\n"
                "How to use\n"
                "- Use 15m or 5m for most ICC execution work.\n"
                "- Leave Auto to keep the profile default.\n"
            ),
            "PROFILE_TREND_WINDOW": (
                "PROFILE_TREND_WINDOW\n"
                "Number of candles used to classify HTF structure trend.\n\n"
                "ICC guidance\n"
                "- Larger windows reduce noise but respond slower.\n"
                "- Smaller windows respond faster but can misclassify chop.\n\n"
                "How to use\n"
                "- Keep the profile default unless you know the asset’s structure cadence.\n"
            ),
            "PROFILE_TREND_SWING_LOOKBACK": (
                "PROFILE_TREND_SWING_LOOKBACK\n"
                "Fractal lookback for defining swing highs/lows on HTF.\n\n"
                "ICC guidance\n"
                "- A higher lookback requires more separation between swings (cleaner structure).\n"
                "- A lower lookback is more sensitive and can classify chop as trend.\n"
            ),
            "PROFILE_TREND_MIN_SWINGS": (
                "PROFILE_TREND_MIN_SWINGS\n"
                "Minimum confirmed swings needed to call a trend (HH/HL or LH/LL).\n\n"
                "ICC guidance\n"
                "- Higher values mean stronger confirmation, fewer trades.\n"
                "- Lower values mean faster classification, higher noise risk.\n"
            ),
            "PROFILE_TREND_STRENGTH_FLOOR": (
                "PROFILE_TREND_STRENGTH_FLOOR\n"
                "Minimum structure strength to treat a trend as non‑neutral.\n\n"
                "ICC guidance\n"
                "- Strength is based on the consistency of HH/HL or LH/LL sequences.\n"
                "- If below the floor, the trend is treated as neutral (no ICC trade).\n"
            ),
            "PROFILE_STRUCTURE_SCORE_THRESHOLD": (
                "PROFILE_STRUCTURE_SCORE_THRESHOLD\n"
                "Score threshold for structure cleanliness (ICC gating).\n\n"
                "ICC guidance\n"
                "- The bot still requires HTF/LTF alignment + sweep + continuation.\n"
                "- This threshold influences selection/readiness scoring, not the hard gates.\n"
            ),
            "PROFILE_PDT_GUARD_ENABLED": (
                "PROFILE_PDT_GUARD_ENABLED\n"
                "Enable the PDT guard for equities.\n\n"
                "Important\n"
                "- This does NOT make the bot long‑only.\n"
                "- It only limits same‑day roundtrips for equities.\n"
            ),
            "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY": (
                "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY\n"
                "Maximum equity roundtrips allowed per day under PDT guard.\n\n"
                "ICC guidance\n"
                "- A flip counts as an exit + new entry (conservative).\n"
                "- Keep low unless you are exempt from PDT rules.\n"
            ),
            "PROFILE_FLIP_ACTIONS_ENABLED": (
                "PROFILE_FLIP_ACTIONS_ENABLED\n"
                "Allow flip_to_long / flip_to_short actions.\n\n"
                "ICC guidance\n"
                "- Flips are reserved for confirmed HTF structure flips.\n"
                "- Disabled by default for safety.\n"
            ),
            "PROFILE_FLIP_COOLDOWN_SECONDS": (
                "PROFILE_FLIP_COOLDOWN_SECONDS\n"
                "Minimum seconds between flips when PDT guard is active.\n\n"
                "ICC guidance\n"
                "- Prevents flip‑churn in ranges or chop.\n"
            ),
            "PROFILE_COOLDOWN_ENABLED": (
                "PROFILE_COOLDOWN_ENABLED\n"
                "Enable ICC cooldowns after blocks or successes.\n\n"
                "ICC guidance\n"
                "- Helps avoid re‑entering during chop or failed attempts.\n"
            ),
            "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK": (
                "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK\n"
                "Number of cycles to skip after a blocked attempt.\n\n"
                "ICC guidance\n"
                "- Higher values reduce churn during noisy phases.\n"
            ),
            "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS": (
                "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS\n"
                "Number of cycles to skip after a successful entry.\n\n"
                "ICC guidance\n"
                "- Use small values for faster re‑evaluation; higher values reduce over‑trading.\n"
            ),
            "PROFILE_COOLDOWN_SCOPE": (
                "PROFILE_COOLDOWN_SCOPE\n"
                "Cooldown scope for ICC gating.\n\n"
                "Options\n"
                "- symbol: only skip the symbol that just failed/succeeded.\n"
                "- global: pause all symbols for the cooldown period.\n\n"
                "ICC guidance\n"
                "- Use symbol scope for broad scanning.\n"
                "- Use global only when you want hard pauses across the entire bot.\n"
            ),
            "PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL": (
                "PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL\n"
                "How long to stick to the active symbol before rotating.\n\n"
                "Options\n"
                "- cycle_end: reevaluate on the next cycle.\n"
                "- decision_end: hold until a decision completes.\n\n"
                "ICC guidance\n"
                "- Sticking reduces churn when a structure is close to forming.\n"
            ),
            "PROFILE_AUTO_SCHEDULE_ENABLED": (
                "PROFILE_AUTO_SCHEDULE_ENABLED\n"
                "Enable auto‑schedule (equities in US hours, crypto off‑hours).\n\n"
                "ICC guidance\n"
                "- Keeps the bot aligned with market hours without manual toggles.\n"
            ),
            "PROFILE_AUTO_FLATTEN_ON_CLOSE": (
                "PROFILE_AUTO_FLATTEN_ON_CLOSE\n"
                "Auto‑flatten at end of scheduled windows.\n\n"
                "ICC note\n"
                "- Avoid this if you intend to hold ICC continuations overnight.\n\n"
                "FUTURES WARNING\n"
                "- NEVER enable for Coinbase Nano futures (perpetual-style)!\n"
                "- Perps have NO daily settlement - forced flattening causes unnecessary losses.\n"
            ),
            "PROFILE_CONTINUOUS_MODE": (
                "PROFILE_CONTINUOUS_MODE\n"
                "Keep the runtime loop alive regardless of iteration limits.\n\n"
                "Use cases\n"
                "- Always‑on monitoring with ICC gating.\n"
            ),
            "PROFILE_CRYPTO_ONLY": (
                "PROFILE_CRYPTO_ONLY\n"
                "Treat the profile as crypto‑only.\n\n"
                "ICC note\n"
                "- Useful for off‑hours ICC execution when equities are closed.\n"
            ),
            "PROFILE_ICC_AGGRESSIVE_MODE": (
                "PROFILE_ICC_AGGRESSIVE_MODE\n"
                "Enable aggressive ICC sizing + guardrails (Phase 2, opt‑in only).\n\n"
                "Default (Trade by SCI)\n"
                "- Enabled by default to reflect Trade by SCI’s preferred posture.\n"
                "- Guardrails still apply (max daily loss, exposure caps, circuit breaker).\n"
            ),
            "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT": (
                "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT\n"
                "Risk per trade as % of equity when aggressive mode is enabled.\n\n"
                "Default (Trade by SCI)\n"
                "- 3% per trade when aggressive mode is enabled.\n"
                "- Applies only with PROFILE_ICC_AGGRESSIVE_MODE=true.\n"
            ),
            "PROFILE_MAX_DAILY_LOSS_PCT": (
                "PROFILE_MAX_DAILY_LOSS_PCT\n"
                "Max daily loss % before blocking new entries (aggressive mode).\n\n"
                "Default (Trade by SCI)\n"
                "- 6% daily loss cap before blocking new entries.\n"
            ),
            "PROFILE_MAX_EXPOSURE_PCT": (
                "PROFILE_MAX_EXPOSURE_PCT\n"
                "Max total open exposure % of equity (aggressive mode).\n\n"
                "Default (Trade by SCI)\n"
                "- 40% max total exposure in aggressive mode.\n"
            ),
            "PROFILE_MAX_CONSECUTIVE_LOSSES": (
                "PROFILE_MAX_CONSECUTIVE_LOSSES\n"
                "Consecutive loss limit before blocking entries (aggressive mode).\n\n"
                "Default (Trade by SCI)\n"
                "- 2 consecutive losses before blocking entries.\n"
            ),
            "BOT_MODE": (
                "BOT_MODE\n"
                "Choose how long the bot runs and when it is allowed to run.\n\n"
                "Modes\n"
                "- continuous: runs forever (best for always-on monitoring).\n"
                "- scheduled: runs only inside configured schedule windows, then exits.\n"
                "- iterations: runs N loops then exits (best for testing).\n\n"
                "How to use\n"
                "- If you want the GUI/tmux dashboard always available, use continuous.\n"
                "- If you want strict “run only during sessions”, use scheduled and configure schedule windows.\n"
                "- If you’re validating changes safely, use iterations.\n"
            ),
            "BOT_ITERATIONS": (
                "BOT_ITERATIONS\n"
                "Number of scan/decision/execution cycles when `BOT_MODE=iterations`.\n\n"
                "How to use\n"
                "- Use a small number (e.g., 20–200) to test changes quickly.\n"
                "- If you want a longer test run without leaving it forever, increase it.\n"
            ),
            "EXECUTE_TRADES": (
                "EXECUTE_TRADES\n"
                "Master switch for live order placement.\n\n"
                "What it means\n"
                "- false: the bot runs in simulation mode (no live orders).\n"
                "- true: the bot is allowed to place live orders (subject to broker permissions and confirmation).\n\n"
                "How to use safely\n"
                "- Enable it only when you intend to trade live.\n"
                "- The GUI will show a confirmation dialog before starting live trading.\n"
                "- If `IBKR_READ_ONLY=true`, orders will still be blocked even with live enabled.\n\n"
                "Common gotcha\n"
                "- If you restart from tmux, the launcher preserves `EXECUTE_TRADES=true|false` via the stored BOT_CMD.\n"
            ),
            "BOT_SABBATH": (
                "BOT_SABBATH\n"
                "Controls Sabbath entry blocking.\n\n"
                "What it does\n"
                "- When Sabbath is active, the bot blocks NEW entries.\n"
                "- Risk management/monitoring can still run (exits/protection may still be evaluated).\n\n"
                "Options\n"
                "- Auto: use the profile’s default behavior.\n"
                "- Force ON: always block new entries during the Sabbath window.\n"
                "- Force OFF: disable Sabbath blocking entirely.\n\n"
                "When to change this\n"
                "- Leave Auto unless you’re doing a special test or you intentionally want to override profile behavior.\n"
            ),
            "SABBATH_ENABLED": (
                "SABBATH_ENABLED\n"
                "Override the profile's sabbath_enabled flag.\n\n"
                "What this controls\n"
                "- When true, the profile treats the sabbath window as active (new entries blocked).\n"
                "- When false, the profile disables sabbath blocking entirely.\n\n"
                "How to use\n"
                "- Leave empty to keep the profile default.\n"
                "- Use with BOT_SABBATH=Auto so the profile logic applies.\n"
            ),
            "SABBATH_ASTRONOMICAL": (
                "SABBATH_ASTRONOMICAL\n"
                "Use actual sunset times instead of fixed HH:MM values.\n\n"
                "Requirements\n"
                "- `astral` must be installed.\n"
                "- You must provide latitude/longitude (SABBATH_LAT/SABBATH_LON).\n\n"
                "How to use\n"
                "- Enable this for accurate sabbath windows that track seasonal sunset shifts.\n"
                "- Leave off for fixed windows (SABBATH_START_LOCAL/SABBATH_END_LOCAL).\n"
            ),
            "SABBATH_TIMEZONE": (
                "SABBATH_TIMEZONE\n"
                "Timezone used when computing sabbath start/end.\n\n"
                "Format\n"
                "- Use an IANA timezone like `America/New_York`.\n\n"
                "How to use\n"
                "- Set this to match the city you want sabbath times computed for.\n"
            ),
            "SABBATH_START_LOCAL": (
                "SABBATH_START_LOCAL\n"
                "Fixed local start time (Friday) for sabbath blocking.\n\n"
                "Format\n"
                "- HH:MM in 24-hour time (e.g., 18:00).\n\n"
                "When it applies\n"
                "- Used only when SABBATH_ASTRONOMICAL is false.\n"
            ),
            "SABBATH_END_LOCAL": (
                "SABBATH_END_LOCAL\n"
                "Fixed local end time (Saturday) for sabbath blocking.\n\n"
                "Format\n"
                "- HH:MM in 24-hour time (e.g., 18:00).\n\n"
                "When it applies\n"
                "- Used only when SABBATH_ASTRONOMICAL is false.\n"
            ),
            "SABBATH_LAT": (
                "SABBATH_LAT\n"
                "Latitude for astronomical sabbath calculations.\n\n"
                "Format\n"
                "- Decimal degrees (e.g., 40.7128).\n\n"
                "When it applies\n"
                "- Required if SABBATH_ASTRONOMICAL=true.\n"
            ),
            "SABBATH_LON": (
                "SABBATH_LON\n"
                "Longitude for astronomical sabbath calculations.\n\n"
                "Format\n"
                "- Decimal degrees (e.g., -74.0060).\n\n"
                "When it applies\n"
                "- Required if SABBATH_ASTRONOMICAL=true.\n"
            ),
            "SABBATH_CITY": (
                "SABBATH_CITY\n"
                "Optional city name used by the GUI resolver to fill latitude/longitude/timezone.\n\n"
                "How to use\n"
                "- Enter a US city (e.g., New York) and use Resolve to auto-fill lat/lon + timezone.\n"
                "- If the resolver fails, enter lat/lon/timezone manually.\n"
            ),
            "EXCHANGE_PROVIDER": (
                "EXCHANGE_PROVIDER\n"
                "Chooses the primary market connectivity stack.\n\n"
                "Options\n"
                "- IBKR: use Interactive Brokers for market data and/or execution.\n"
                "- CCXT: use CCXT-compatible crypto exchange connectivity (when configured).\n\n"
                "Important\n"
                "- “Market Data” and “Broker” dropdowns below only matter when using the alternative provider.\n"
                "- If you select IBKR here, the bot uses IBKR as the primary feed/broker.\n"
            ),
            "Market Data": (
                "Market Data\n"
                "Selects the market data source when using an alternative provider.\n\n"
                "How to use\n"
                "- If `EXCHANGE_PROVIDER=IBKR`, this setting is ignored.\n"
                "- If using CCXT/alternative mode, choose the market data backend you want.\n\n"
                "Tip\n"
                "- Delayed data is fine for monitoring; just expect candles/quotes to lag.\n"
            ),
                "Broker": (
                    "Broker\n"
                    "Selects where orders are sent when using an alternative provider.\n\n"
                "How to use\n"
                "- If `EXCHANGE_PROVIDER=IBKR`, this setting is ignored.\n"
                "- If using CCXT/alternative mode, choose the execution backend.\n\n"
                    "Safety\n"
                    "- Always verify you are on the intended account/venue before enabling live trading.\n"
                ),
                "Candles (chart)": (
                    "Candles (chart)\n"
                    "Controls the bar size used for the GUI candle chart.\n\n"
                    "What this is\n"
                    "- This changes the timeframe of the historical bars shown in the candles pane.\n"
                    "- It does not change the bot’s decision timeframe by itself (that is profile/timeframe driven).\n\n"
                    "How to use\n"
                    "- Use smaller values (1m/5m) for more detail and short-term structure.\n"
                    "- Use larger values (15m/30m/1h/daily) for broader context and swing structure.\n\n"
                    "Data note\n"
                    "- If you are using delayed market data, the chart will lag behind live prices.\n"
                    "- Missing bars usually means the provider returned no bars for that request (symbol/venue mismatch or data limitations).\n"
                ),
                "APP_ENVIRONMENT": (
                    "APP_ENVIRONMENT\n"
                    "Optional environment tag used by configuration loaders.\n\n"
                    "What this is\n"
                    "- A simple label like `development`, `staging`, or `production`.\n"
                    "- Some configs/logging may change based on this value.\n\n"
                    "How to use\n"
                    "- Leave blank if you are not using environment-specific config.\n"
                    "- Use `development` when you want safer defaults and more diagnostics.\n"
                    "- Use `production` only when you intend to run live/long-running.\n"
                ),
            "CHATGPT_KEY": (
                "CHATGPT_KEY\n"
                "API key for a ChatGPT-compatible provider (if configured).\n\n"
                "What it is for\n"
                "- Enables AI commentary and/or AI-assisted reasoning in the bot, depending on your setup.\n\n"
                "How to use safely\n"
                "- Treat this like a password.\n"
                "- Set it in the typed field (not in the Advanced env table), then Save to `.env`.\n\n"
                "Troubleshooting\n"
                "- If commentary shows “waiting” forever, verify the key is set and the provider/model are valid.\n"
            ),
            "TRADE_SCI_PROVIDER": (
                "TRADE_SCI_PROVIDER\n"
                "Select which AI provider the bot/commentary should use.\n\n"
                "Options\n"
                "- openai, gemini, claude, deepseek, openrouter, custom.\n"
                "- Use custom when you have an OpenAI-compatible endpoint.\n"
                "- Leave blank for Auto (OpenAI defaults).\n"
            ),
                "TRADE_SCI_API_BASE_URL": (
                    "TRADE_SCI_API_BASE_URL\n"
                    "Base URL for the Trade by SCI AI gateway/provider.\n\n"
                    "When you would change this\n"
                    "- You are using a self-hosted gateway, a proxy, or a non-default endpoint.\n\n"
                    "How to use\n"
                    "- Leave default unless you were explicitly given a different URL.\n"
                    "- If you change it, restart the commentary pane so it picks up the new endpoint.\n"
                ),
            "TRADE_SCI_MODEL_NAME": (
                "TRADE_SCI_MODEL_NAME\n"
                "Which LLM model to use for bot decisions and AI commentary.\n\n"
                    "How to choose\n"
                    "- Larger models: better explanations, higher cost.\n"
                    "- Smaller models: cheaper/faster, may be less insightful.\n\n"
                    "Tip\n"
                    "- If you want more “human play-by-play”, pick a stronger model and increase max tokens.\n"
                ),
                "TRADE_SCI_MAX_TOKENS": (
                    "TRADE_SCI_MAX_TOKENS\n"
                    "Maximum tokens allowed per AI response.\n\n"
                    "What this changes\n"
                    "- Higher values allow longer, more detailed commentary.\n"
                    "- Lower values reduce cost but can truncate explanations.\n\n"
                    "Recommendation\n"
                    "- For “twice as long” commentary, increase this (within your provider limits).\n"
                ),
                "TRADE_SCI_TEMPERATURE": (
                    "TRADE_SCI_TEMPERATURE\n"
                    "Controls how creative vs. deterministic the AI output is.\n\n"
                    "How to use\n"
                    "- 0.0–0.3: more consistent/grounded, best for monitoring decisions.\n"
                    "- 0.4–0.8: more expressive, can be more speculative.\n\n"
                    "Safety note\n"
                    "- Commentary is informational; trading logic should not depend on creative phrasing.\n"
                ),
                "MARKET_DEFAULT_SYMBOL": (
                    "MARKET_DEFAULT_SYMBOL\n"
                    "Default symbol shown in the GUI candle pane when there is no active symbol.\n\n"
                    "How to use\n"
                    "- Set a common benchmark symbol (e.g., SPY, QQQ, BTCUSD) to keep the chart useful.\n"
                    "- If the bot becomes active on a symbol, the GUI can switch to the active symbol.\n"
                ),
                "MARKET_DEFAULT_TIMEFRAME": (
                    "MARKET_DEFAULT_TIMEFRAME\n"
                    "Default candle timeframe used by the GUI chart.\n\n"
                    "What this affects\n"
                    "- Only the GUI chart timeframe (not the bot’s scan timeframe).\n\n"
                    "How to use\n"
                    "- Pick the timeframe you most often want as context (5m/15m/1h/daily).\n"
                ),
                "MARKET_MAX_CANDLES": (
                    "MARKET_MAX_CANDLES\n"
                    "Maximum number of candles to request/render in the GUI.\n\n"
                    "Tradeoffs\n"
                    "- More candles = more history/context, more API load.\n"
                    "- Fewer candles = faster refresh, less clutter.\n\n"
                    "Tip\n"
                    "- If you see missing bars/timeouts, reduce this value.\n"
                ),
                "MARKET_SYMBOLS": (
                    "MARKET_SYMBOLS\n"
                    "Comma-separated symbol list for GUI rotation when the bot is not actively trading a single symbol.\n\n"
                    "How to use\n"
                    "- Provide your preferred watchlist (e.g., `SPY,QQQ,DIA,BTCUSD,ETHUSD`).\n"
                    "- The GUI/candles pane can rotate through the top symbols when idle.\n\n"
                    "Tip\n"
                    "- Keep the list short to avoid unnecessary market data requests.\n"
                ),
                "FRICTION_FAIL_SAFE": (
                    "FRICTION_FAIL_SAFE\n"
                    "Blocks new entries when spread/slippage (“friction”) appears too high.\n\n"
                    "What this means\n"
                    "- If the market is illiquid or spreads are wide, fills can be worse than expected.\n"
                    "- This fail-safe helps avoid taking trades in poor execution conditions.\n\n"
                    "How to use\n"
                    "- Enable it for safer live trading.\n"
                    "- If you see trades blocked too often, adjust `FRICTION_RISK_CAP` rather than disabling.\n\n"
                    "Common symptoms when it triggers\n"
                    "- Frequent stand-aside decisions during volatile/low-liquidity periods.\n"
                ),
                "FRICTION_RISK_CAP": (
                    "FRICTION_RISK_CAP\n"
                    "Threshold for what the bot considers “too much friction”.\n\n"
                    "How to tune\n"
                    "- Lower value = stricter (blocks more trades, safer fills).\n"
                    "- Higher value = more permissive (takes more trades, riskier fills).\n\n"
                    "Recommendation\n"
                    "- Start conservative; only raise if you understand your venue’s typical spreads.\n"
                ),
                "VIX_FAIL_SAFE": (
                    "VIX_FAIL_SAFE\n"
                    "Blocks new equity entries when volatility regime looks too risky.\n\n"
                    "What this means\n"
                    "- High volatility can break continuation behavior and increase stop-outs.\n"
                    "- This is a regime filter, not an ICC gate.\n\n"
                    "How to use\n"
                    "- Enable it if you want the bot to avoid extreme volatility days.\n"
                    "- If it blocks too aggressively, adjust `VIX_RISK_CAP`.\n"
                ),
                "VIX_RISK_CAP": (
                    "VIX_RISK_CAP\n"
                    "Threshold for volatility risk tolerance.\n\n"
                    "How to tune\n"
                    "- Lower = stricter volatility avoidance.\n"
                    "- Higher = allows trading in higher-volatility regimes.\n"
                ),
                "CONFLUENCE_EXTERNAL": (
                    "CONFLUENCE_EXTERNAL\n"
                    "Include optional external confluence signals (if available).\n\n"
                    "What this is\n"
                    "- Adds additional context beyond the core ICC gates.\n"
                    "- The bot should still require HTF/LTF alignment + sweep + continuation.\n\n"
                    "How to use\n"
                    "- Keep off unless you know what signals are configured in your setup.\n"
                ),
                "COMMITMENT_MODE": (
                    "COMMITMENT_MODE\n"
                    "Reduces churn after entry by preferring hold/manage decisions over frequent re-evaluation.\n\n"
                    "Why this matters\n"
                    "- Prevents “enter then immediately flatten” behavior unless there is a real invalidation/emergency.\n"
                    "- Helps positions follow the continuation instead of getting micro-managed every cycle.\n\n"
                    "How to use\n"
                    "- Enable for live trading.\n"
                    "- Disable only for debugging strategy logic.\n"
                ),
                "BUG_BYPASS_SCHEDULE": (
                    "BUG_BYPASS_SCHEDULE\n"
                    "Debug override to bypass schedule windows.\n\n"
                    "What this does\n"
                    "- Forces the bot to run outside normal session windows.\n\n"
                    "Safety note\n"
                    "- Do not use for live trading unless you intentionally want to trade off-hours.\n"
                    "- Prefer profile-based scheduling for normal operation.\n"
                ),
                "EMERGENCY_STOP_PCT": (
                    "EMERGENCY_STOP_PCT\n"
                    "Emergency protective stop percentage used by runtime safeguards.\n\n"
                    "What it is for\n"
                    "- A last-resort protection if a position is unprotected/missing a normal stop.\n\n"
                    "How to use\n"
                    "- Keep small (tight) if you want immediate damage control.\n"
                    "- Keep larger if you want to avoid forced sells on normal noise.\n\n"
                    "Important\n"
                    "- This is not an ICC invalidation stop; it is a safety net.\n"
                ),
                "SCALE_OUT_FRACTION": (
                    "SCALE_OUT_FRACTION\n"
                    "How much of a position to take off when scaling out.\n\n"
                    "How to use\n"
                    "- 0.5 means sell/cover half when a scale-out condition triggers.\n"
                    "- Use smaller fractions for smoother exits; larger for faster de-risking.\n\n"
                    "Tip\n"
                    "- Scaling out should respect ICC continuation rules; avoid exiting too early unless invalidated.\n"
                ),
                "MAX_SCALE_INS_PER_LEG": (
                    "MAX_SCALE_INS_PER_LEG\n"
                    "Maximum number of adds (scale-ins) allowed for a single position leg.\n\n"
                    "Why it matters\n"
                    "- Prevents the bot from pyramiding too aggressively.\n"
                    "- Keeps risk bounded when continuation takes multiple pushes.\n\n"
                    "How to use\n"
                    "- Start low (0–2). Increase only if you have strict risk caps.\n"
                ),
                "MIN_POSITION_SIZE_TO_SCALE": (
                    "MIN_POSITION_SIZE_TO_SCALE\n"
                    "Minimum position size required before the bot is allowed to scale in/out.\n\n"
                    "Why this exists\n"
                    "- Prevents noisy tiny positions from triggering complex management logic.\n\n"
                    "How to use\n"
                    "- Leave default unless you frequently trade very small size.\n"
                ),
                "STARTUP_CRYPTO_UNPROTECTED_POLICY": (
                    "STARTUP_CRYPTO_UNPROTECTED_POLICY\n"
                    "What to do on startup if a ZEROHASH crypto position exists but has no persisted synthetic stop.\n\n"
                    "Options\n"
                    "- REARM: recreate the synthetic stop (preferred to avoid forced sell).\n"
                    "- PAUSE: keep the position but pause actions on that symbol.\n"
                    "- FLATTEN: immediately exit (safest operationally, but can realize losses).\n\n"
                    "Recommendation\n"
                    "- Use REARM for ICC-style continuation holding.\n"
                    "- Use FLATTEN only if you prioritize safety over holding.\n"
                ),
                "SYNTH_STOP_STORE_PATH": (
                    "SYNTH_STOP_STORE_PATH\n"
                    "Where synthetic stops are persisted (JSON file).\n\n"
                    "Why this matters\n"
                    "- Lets the bot recover/manage stops across restarts.\n"
                    "- Prevents “unprotected position” policies from triggering unnecessarily.\n\n"
                    "How to use\n"
                    "- Choose a stable, writable path.\n"
                    "- Do not delete it while positions are open.\n"
                ),
                "POSITION_HOLD_STORE_PATH": (
                    "POSITION_HOLD_STORE_PATH\n"
                    "Where position hold/age state is persisted (JSON file).\n\n"
                    "Why this matters\n"
                    "- Allows the bot to track how long a position has been held across restarts.\n"
                    "- Enables “do not sell within X hours” style protection.\n\n"
                    "How to use\n"
                    "- Choose a stable, writable path.\n"
                    "- Keep it consistent across runs so the bot retains history.\n"
                ),
                "ALLOW_INHERITED_POSITION": (
                    "ALLOW_INHERITED_POSITION\n"
                    "Allow the bot to inherit/manage positions that already exist in the broker account.\n\n"
                    "What this means\n"
                    "- When enabled, the bot will treat existing holdings as positions it must manage.\n"
                    "- This is required if you want multi-position monitoring after restarts or manual trades.\n\n"
                    "How to use safely\n"
                    "- Enable only if you want the bot to take responsibility for pre-existing positions.\n"
                    "- Make sure your hold/stop persistence paths are configured.\n"
                ),
                "CANCEL_ORDERS_ON_START": (
                    "CANCEL_ORDERS_ON_START\n"
                    "Cancel any open/pending orders on bot startup.\n\n"
                    "Why this exists\n"
                    "- Prevents stale orders from a previous run from filling unexpectedly.\n\n"
                    "Important note\n"
                    "- Canceling an order is not the same as closing a filled trade.\n"
                    "- This setting is about cleanup of pending orders, not day-trading.\n"
                ),
                "FLATTEN_ON_EXIT": (
                    "FLATTEN_ON_EXIT\n"
                    "When the bot exits/shuts down, flatten positions as part of shutdown.\n\n"
                    "Use cases\n"
                    "- Paper/sim runs where you always want to end flat.\n"
                    "- Emergency shutdown behavior.\n\n"
                    "Caution\n"
                    "- For ICC continuation holding, you usually do NOT want forced flattening.\n"
                ),
                "INTRADAY_FLATTEN": (
                    "INTRADAY_FLATTEN\n"
                    "Flatten positions near the end of the session (intraday mode).\n\n"
                    "Why this exists\n"
                    "- Avoid holding equities overnight when running an intraday-only strategy.\n\n"
                    "ICC note\n"
                    "- Only enable if your ICC plan is explicitly intraday (no overnight hold).\n"
                ),
                "IBKR_CRYPTO_EXCHANGE": (
                    "IBKR_CRYPTO_EXCHANGE\n"
                    "Exchange route for IBKR crypto (e.g., ZEROHASH).\n\n"
                    "Important\n"
                    "- ZEROHASH spot crypto is long-only in this project’s rules.\n"
                    "- If you change this, verify execution capabilities and supported order types.\n"
                ),
                "IBKR_ZEROHASH_CRYPTO_TIF": (
                    "IBKR_ZEROHASH_CRYPTO_TIF\n"
                    "Time-in-force for IBKR ZEROHASH crypto orders.\n\n"
                    "How to use\n"
                    "- Choose a TIF supported by your venue/order type (e.g., DAY/IOC).\n"
                    "- If you see broker warnings about unsupported TIF, change this.\n"
                ),
                "IBKR_MAX_SHARES_PER_SYMBOL": (
                    "IBKR_MAX_SHARES_PER_SYMBOL\n"
                    "Hard cap on position size (shares) per symbol.\n\n"
                    "Why this matters\n"
                    "- Prevents runaway sizing due to bad data or config.\n\n"
                    "How to use\n"
                    "- Set a conservative max based on your account size.\n"
                    "- Use alongside dollar-risk caps.\n"
                ),
                "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL": (
                    "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL\n"
                    "Maximum dollar risk allowed per symbol.\n\n"
                    "What this means\n"
                    "- Caps how much you can lose on a single position based on stop distance.\n\n"
                    "How to use\n"
                    "- Set this first before enabling live trading.\n"
                    "- If orders are rejected due to sizing, this cap may be too low.\n"
                ),
                "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT": (
                    "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT\n"
                    "Maximum total dollar risk allowed across all open positions.\n\n"
                    "Why this matters\n"
                    "- Required if you enable multi-position mode.\n"
                    "- Prevents cumulative exposure from becoming too large.\n\n"
                    "How to use\n"
                    "- Keep this aligned with your risk tolerance for worst-case stop-outs.\n"
                ),
                "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER": (
                    "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER\n"
                    "Automatic risk sizing as a fraction of buying power.\n\n"
                    "What this does\n"
                    "- Helps the bot scale position size with account size.\n"
                    "- Still bounded by max shares and max dollar risk caps.\n\n"
                    "How to use\n"
                    "- Start small (very conservative).\n"
                    "- Increase only after validating sizing and broker fills.\n"
                ),
                "CCXT_EXCHANGE": (
                    "CCXT_EXCHANGE\n"
                    "Which CCXT exchange to use when routing via CCXT.\n\n"
                    "How to use\n"
                    "- Set this only if you are using CCXT for market data and/or execution.\n"
                    "- Example values match CCXT exchange ids (e.g., `binance`, `coinbase`).\n"
                ),
                "CCXT_DEFAULT_TYPE": (
                    "CCXT_DEFAULT_TYPE\n"
                    "CCXT market type (spot, swap, future) depending on the exchange.\n\n"
                    "How to use\n"
                    "- Choose the type that matches the instruments you trade.\n"
                    "- Wrong type often causes “symbol not found” or missing candles.\n"
                ),
                "CCXT_ENABLE_RATE_LIMIT": (
                    "CCXT_ENABLE_RATE_LIMIT\n"
                    "Enable CCXT built-in rate limiting.\n\n"
                    "Why this matters\n"
                    "- Helps avoid exchange bans and 429 rate-limit errors.\n\n"
                    "Recommendation\n"
                    "- Keep enabled for live connectivity.\n"
                ),
                "CCXT_SANDBOX": (
                    "CCXT_SANDBOX\n"
                    "Use CCXT sandbox/testnet mode (if the exchange supports it).\n\n"
                    "How to use\n"
                    "- Enable for testing without real funds.\n"
                    "- Disable for live trading.\n"
                ),
                "CCXT_SYMBOL_MAP": (
                    "CCXT_SYMBOL_MAP\n"
                    "Optional mapping to translate internal symbols to CCXT exchange-specific symbols.\n\n"
                    "When you need this\n"
                    "- The exchange uses symbols like `BTC/USDT` but your bot uses `BTCUSD`.\n\n"
                    "How to use\n"
                    "- Provide a JSON or delimited mapping per your project’s configuration format.\n"
                ),
                "CCXT_API_KEY": (
                    "CCXT_API_KEY\n"
                    "API key for CCXT exchange authentication.\n\n"
                    "How to use safely\n"
                    "- Treat as a password.\n"
                    "- Use exchange keys with least privileges needed.\n"
                ),
                "CCXT_SECRET": (
                    "CCXT_SECRET\n"
                    "API secret for CCXT exchange authentication.\n\n"
                    "Safety\n"
                    "- Never share this.\n"
                    "- If you suspect leakage, revoke/regenerate it at the exchange.\n"
                ),
                "CCXT_PASSWORD": (
                    "CCXT_PASSWORD\n"
                    "Optional passphrase/password for CCXT (some exchanges require it).\n\n"
                    "How to use\n"
                    "- Leave blank unless your exchange specifically requires a passphrase.\n"
                ),
                "LOG_LEVEL": (
                    "LOG_LEVEL\n"
                    "Controls how chatty the bot logs are.\n\n"
                "How to use\n"
                "- INFO: normal operations.\n"
                "- DEBUG: more details (useful when diagnosing issues).\n"
                "- WARNING/ERROR: quieter logs, only problems.\n"
            ),
            "TRADEBOT_LOG": (
                "TRADEBOT_LOG\n"
                "Path to the main bot log file that the GUI/tmux dashboard tails.\n\n"
                "How to use\n"
                "- Keep this set to `logs/tradebot.log` unless you have a special setup.\n"
                "- Rotated logs `tradebot.log.1`, `tradebot.log.2`, … are used for history/context.\n"
            ),
            "SESSION_NAME": (
                "SESSION_NAME\n"
                "tmux session name used by the terminal dashboard.\n\n"
                "How to use\n"
                "- Default is `tradebot`.\n"
                "- If you run multiple dashboards, give each a different session name.\n"
            ),
            "COMMENTARY_LLM": (
                "COMMENTARY_LLM\n"
                "Controls whether the right-pane commentary uses the internal AI commentator.\n\n"
                "Options\n"
                "- Auto: use internal commentary.\n"
                "- Off: no AI calls; deterministic dashboard only.\n"
                "- Internal: call the built-in AI commentator.\n\n"
                "Cost control\n"
                "- Use the refresh/budget settings to prevent excessive API usage.\n"
            ),
            "COMMENTARY_LLM_POLICY": (
                "COMMENTARY_LLM_POLICY\n"
                "Controls WHEN the GUI/tmux is allowed to call the commentator.\n\n"
                "Options\n"
                "- a_plus_or_4x (recommended): Call on A+ continuation (readiness=1.00). If no A+ is happening, call up to 4× per day using `COMMENTARY_LLM_DAILY_SLOTS`.\n"
                "- a_plus_only: Only call when an A+ continuation appears.\n"
                "- interval: Legacy behavior (call whenever `COMMENTARY_LLM_MIN_SECONDS` allows it).\n\n"
                "Why this exists\n"
                "- Keeps API usage under control while still giving you timely insight when the bot reaches a true ICC entry (A+).\n"
            ),
            "COMMENTARY_LLM_DAILY_SLOTS": (
                "COMMENTARY_LLM_DAILY_SLOTS\n"
                "Comma-separated times (HH:MM) used by `COMMENTARY_LLM_POLICY=a_plus_or_4x`.\n\n"
                "Example\n"
                "- 09:00,12:00,18:00,22:00\n\n"
                "Notes\n"
                "- Times are interpreted in `COMMENTARY_LLM_TZ`.\n"
                "- The bot will call at most once per slot.\n"
            ),
            "COMMENTARY_LLM_TZ": (
                "COMMENTARY_LLM_TZ\n"
                "Shared timezone (IANA name) used to interpret `COMMENTARY_LLM_DAILY_SLOTS`.\n"
                "The Time tab keeps this aligned with Sabbath/session timezones.\n\n"
                "Example\n"
                "- America/New_York\n"
            ),
            "COMMENTARY_LLM_MIN_SECONDS": (
                "COMMENTARY_LLM_MIN_SECONDS\n"
                "Minimum seconds between commentary refreshes.\n\n"
                "Why this matters\n"
                "- Prevents spamming your provider/API.\n"
                "- Lower values increase cost and rate-limit risk.\n\n"
                "Recommendation\n"
                "- 300s (5 minutes) is a good default.\n"
            ),
            "COMMENTARY_LLM_MAX_CALLS_PER_DAY": (
                "COMMENTARY_LLM_MAX_CALLS_PER_DAY\n"
                "Hard daily cap for commentary calls (shared across panes).\n\n"
                "Why this exists\n"
                "- Prevents runaway cost and rate-limit lockouts.\n\n"
                "How it behaves\n"
                "- When the cap is reached, the commentary pane keeps the last good answer.\n"
            ),
            "COMMENTARY_LLM_BUDGET_PATH": (
                "COMMENTARY_LLM_BUDGET_PATH\n"
                "Shared JSON file used to coordinate commentary call budgeting across processes.\n\n"
                "How to use\n"
                "- Leave default unless you want a different shared location.\n"
                "- Must be writable.\n"
            ),
            "TRADE_SCI_API_KEY": (
                "TRADE_SCI_API_KEY\n"
                "API key for the AI provider used by the bot/commentary.\n\n"
                "How to use\n"
                "- This is sensitive. The GUI masks it and stores it as an env var.\n"
                "- Set it once, then use budgets/refresh intervals to control spend.\n"
            ),
            "IBKR_HOST": (
                "IBKR_HOST\n"
                "Host/IP where TWS or IB Gateway is running.\n\n"
                "Typical\n"
                "- `127.0.0.1` when TWS/Gateway is on the same machine.\n"
            ),
            "IBKR_PORT": (
                "IBKR_PORT\n"
                "Port for the IBKR API connection.\n\n"
                "Typical defaults\n"
                "- 7497: paper\n"
                "- 7496: live\n\n"
                "Tip\n"
                "- Match this to your TWS/Gateway API settings.\n"
            ),
            "IBKR_CLIENT_ID": (
                "IBKR_CLIENT_ID\n"
                "Client ID for the IBKR API connection.\n\n"
                "Why it matters\n"
                "- Lets multiple apps connect without stepping on each other.\n"
            ),
            "IBKR_ACCOUNT_ID": (
                "IBKR_ACCOUNT_ID\n"
                "Account identifier (useful if your login has multiple accounts).\n"
            ),
            "IBKR_DEFAULT_CCY": (
                "IBKR_DEFAULT_CCY\n"
                "Default currency used when building certain contracts (usually `USD`).\n"
            ),
            "IBKR_PAPER": (
                "IBKR_PAPER\n"
                "Paper/live preference for the IBKR connection.\n\n"
                "Important\n"
                "- This does not override `EXECUTE_TRADES`; it only selects which endpoint you connect to.\n"
            ),
            "IBKR_READ_ONLY": (
                "IBKR_READ_ONLY\n"
                "Safety switch: when true, the IBKR executor refuses to place orders.\n\n"
                "Use cases\n"
                "- Monitoring mode with live market data but no trading.\n"
                "- Safety while you validate settings.\n"
            ),
            "MULTI_POSITION_ENABLED": (
                "MULTI_POSITION_ENABLED\n"
                "Opt-in multi-position trading.\n\n"
                "Default behavior\n"
                "- Off: the bot only allows one open symbol at a time.\n\n"
                "When enabled\n"
                "- The bot may hold multiple symbols concurrently (up to `MAX_CONCURRENT_POSITIONS`).\n"
                "- Use risk caps to prevent over-exposure.\n"
            ),
            "MAX_CONCURRENT_POSITIONS": (
                "MAX_CONCURRENT_POSITIONS\n"
                "Maximum number of symbols that may be open at the same time when multi-position is enabled.\n\n"
                "How to choose a value\n"
                "- Start with 2–3.\n"
                "- Increase only if you are comfortable managing multiple positions and your risk caps are set.\n"
            ),
        }

        if key in TOOLTIP_LIBRARY:
            widget.setToolTip(TOOLTIP_LIBRARY[key])
            return

        # Env-var pattern: provide a thorough generic tooltip even if we don't have a custom entry.
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key or ""):
            widget.setToolTip(_env_template(key, summary))
            return

        # BrokerSetting: ... entries
        if key.startswith("BrokerSetting: "):
            widget.setToolTip(
                f"{key}\n"
                f"{'Summary: ' + summary if summary else 'Summary: broker sizing/risk guard.'}\n\n"
                "What this is\n"
                "- A broker-level guard used by the executor when sizing/placing orders.\n\n"
                "How to use\n"
                "- Enable \"Override\" (when present), set a value, then Apply/Save.\n"
                "- Lower values are safer; higher values allow larger positions.\n"
            )
            return

        widget.setToolTip(raw)

    # --- Typed controls (grouped in tabs) ---
    app_env = QtWidgets.QLineEdit(self._effective_env_value("APP_ENVIRONMENT")[0])
    app_env.setPlaceholderText("e.g. development / production (optional)")
    tip(app_env, "APP_ENVIRONMENT\nOptional app environment tag used by config loader.")

    profiles = read_profiles()
    profile_combo = QtWidgets.QComboBox()
    if profiles:
        profile_combo.addItems(profiles)
    else:
        profile_combo.addItems(["auto_schedule", "intraday", "crypto_247"])
    current_profile = self._effective_env_value("PROFILE_NAME")[0] or "auto_schedule"
    if current_profile in [profile_combo.itemText(i) for i in range(profile_combo.count())]:
        profile_combo.setCurrentText(current_profile)
    tip(profile_combo, "PROFILE_NAME\nControls symbol universe + cadence + schedule + sabbath rules via profiles.")

    mode_combo = QtWidgets.QComboBox()
    mode_combo.addItems(["continuous", "scheduled", "iterations"])
    mode_combo.setCurrentText(self._effective_env_value("BOT_MODE")[0] or "continuous")
    tip(
        mode_combo,
        "BOT_MODE\ncontinuous: run forever\nscheduled: run only inside configured windows (exits)\niterations: run N loops then exit",
    )

    iterations_spin = QtWidgets.QSpinBox()
    iterations_spin.setRange(1, 1_000_000)
    try:
        iterations_spin.setValue(int(self._effective_env_value("BOT_ITERATIONS")[0] or "120"))
    except Exception:
        iterations_spin.setValue(120)
    tip(iterations_spin, "BOT_ITERATIONS\nUsed only when BOT_MODE=iterations.")

    execute_chk = QtWidgets.QCheckBox("Enable LIVE trading (EXECUTE_TRADES=true)")
    execute_chk.setChecked(self._effective_env_value("EXECUTE_TRADES")[0].lower() == "true")
    tip(execute_chk, "EXECUTE_TRADES\nMaster switch for live order placement.")

    autostart_bot_chk = QtWidgets.QCheckBox("Auto-start bot when GUI opens")
    autostart_bot_chk.setChecked(self._bot_autostart)
    keep_bot_chk = QtWidgets.QCheckBox("Keep bot running after GUI closes")
    keep_bot_chk.setChecked(self._bot_keep_running_on_close)
    tip(
        autostart_bot_chk,
        "GUI_AUTOSTART_BOT\nWhen enabled, the GUI starts the core bot process automatically on launch.",
    )
    tip(
        keep_bot_chk,
        "GUI_KEEP_BOT_RUNNING\nWhen enabled, closing the GUI will NOT stop the bot process.",
    )

    sabbath_combo = QtWidgets.QComboBox()
    sabbath_combo.addItems(["Auto (profile/default)", "Force ON", "Force OFF"])
    bot_sabb = self._effective_env_value("BOT_SABBATH")[0].strip().lower()
    if bot_sabb in {"on", "true", "1", "yes"}:
        sabbath_combo.setCurrentIndex(1)
    elif bot_sabb in {"off", "false", "0", "no"}:
        sabbath_combo.setCurrentIndex(2)
    else:
        sabbath_combo.setCurrentIndex(0)
    tip(
        sabbath_combo,
        "BOT_SABBATH\nAuto: use profile/default rules\nForce ON: block NEW entries during sabbath window\nForce OFF: disable sabbath blocking",
    )

    profiles_map = getattr(settings, "profiles", {}) or {}
    profile_settings = profiles_map.get(current_profile)
    profiles_yaml_path = repo_root / "config" / "settings_profiles.yaml"

    def _load_profiles_yaml() -> dict[str, Any]:
        if not profiles_yaml_path.exists():
            return {"profiles": {}}
        try:
            with profiles_yaml_path.open("r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {"profiles": {}}
        except Exception:
            return {"profiles": {}}

    def _save_profiles_yaml(data: dict[str, Any]) -> bool:
        try:
            with profiles_yaml_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(data, handle, sort_keys=False)
            return True
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                dlg,
                "Profile Save Failed",
                f"Could not save {profiles_yaml_path}:\n{exc}",
            )
            return False

    def _base_market_symbols() -> list[str]:
        base_path = repo_root / "config" / "settings_base.yaml"
        if not base_path.exists():
            return []
        try:
            with base_path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            symbols = (raw.get("market", {}) or {}).get("symbols", []) or []
            return [str(s).upper() for s in symbols if str(s).strip()]
        except Exception:
            return []

    def _normalize_symbols(values: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            sym = str(value).upper().strip()
            if sym and sym not in seen:
                out.append(sym)
                seen.add(sym)
        return out

    def _profile_text(attr: str, default: str = "") -> str:
        if not profile_settings:
            return default
        value = getattr(profile_settings, attr, None)
        if value is None:
            return default
        if isinstance(value, float):
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return str(value)

    def _env_or_profile(key: str, profile_value: str) -> str:
        raw = self._effective_env_value(key)[0].strip()
        return raw if raw else profile_value

    sabbath_enabled_combo = QtWidgets.QComboBox()
    profile_enabled = bool(getattr(profile_settings, "sabbath_enabled", False))
    sabbath_enabled_combo.addItems(
        [
            f"Auto (profile default: {'Enabled' if profile_enabled else 'Disabled'})",
            "Enabled",
            "Disabled",
        ]
    )
    env_enabled = self._effective_env_value("SABBATH_ENABLED")[0].strip().lower()
    if env_enabled in {"1", "true", "yes", "on"}:
        sabbath_enabled_combo.setCurrentIndex(1)
    elif env_enabled in {"0", "false", "no", "off"}:
        sabbath_enabled_combo.setCurrentIndex(2)
    else:
        sabbath_enabled_combo.setCurrentIndex(0)
    tip(sabbath_enabled_combo, "SABBATH_ENABLED\nOverride the profile sabbath_enabled flag.")

    sabbath_astro_chk = QtWidgets.QCheckBox("Use astronomical sunset (Astral)")
    profile_astro = bool(getattr(profile_settings, "sabbath_astronomical", False))
    env_astro = self._effective_env_value("SABBATH_ASTRONOMICAL")[0].strip().lower()
    if env_astro in {"1", "true", "yes", "on"}:
        sabbath_astro_chk.setChecked(True)
    elif env_astro in {"0", "false", "no", "off"}:
        sabbath_astro_chk.setChecked(False)
    else:
        sabbath_astro_chk.setChecked(profile_astro)
    tip(sabbath_astro_chk, "SABBATH_ASTRONOMICAL\nUse actual sunset times instead of fixed HH:MM values.")

    sabbath_city = QtWidgets.QLineEdit(_env_or_profile("SABBATH_CITY", ""))
    sabbath_city.setPlaceholderText("City (e.g., New York)")
    tip(sabbath_city, "SABBATH_CITY\nOptional city name for resolving lat/lon/timezone.")
    resolve_city_btn = QtWidgets.QPushButton("Resolve")
    tip(resolve_city_btn, "SABBATH_CITY\nResolve city to lat/lon/timezone using timeanddate.com.")

    city_row = QtWidgets.QHBoxLayout()
    city_row.addWidget(sabbath_city, 1)
    city_row.addWidget(resolve_city_btn)
    city_row_w = QtWidgets.QWidget(dlg)
    city_row_w.setLayout(city_row)

    sabbath_tz = QtWidgets.QLineEdit(_env_or_profile("SABBATH_TIMEZONE", _profile_text("sabbath_timezone")))
    sabbath_tz.setPlaceholderText(_profile_text("sabbath_timezone", "America/New_York"))
    tip(
        sabbath_tz,
        "SABBATH_TIMEZONE\nPrimary timezone shared by Sabbath scheduling, commentary slots, and session bias.",
    )
    tz_btn = QtWidgets.QPushButton("Use system TZ")
    tip(tz_btn, "SABBATH_TIMEZONE\nSet timezone from your system clock.")
    tz_row = QtWidgets.QHBoxLayout()
    tz_row.addWidget(sabbath_tz, 1)
    tz_row.addWidget(tz_btn)
    tz_row_w = QtWidgets.QWidget(dlg)
    tz_row_w.setLayout(tz_row)

    sabbath_start = QtWidgets.QLineEdit(
        _env_or_profile("SABBATH_START_LOCAL", _profile_text("sabbath_start_local", "18:00"))
    )
    sabbath_start.setPlaceholderText("HH:MM (e.g., 18:00)")
    tip(sabbath_start, "SABBATH_START_LOCAL\nFixed local start time (Friday) when not using astronomical mode.")

    sabbath_end = QtWidgets.QLineEdit(
        _env_or_profile("SABBATH_END_LOCAL", _profile_text("sabbath_end_local", "18:00"))
    )
    sabbath_end.setPlaceholderText("HH:MM (e.g., 18:00)")
    tip(sabbath_end, "SABBATH_END_LOCAL\nFixed local end time (Saturday) when not using astronomical mode.")

    sabbath_lat = QtWidgets.QLineEdit(_env_or_profile("SABBATH_LAT", _profile_text("sabbath_lat")))
    sabbath_lat.setPlaceholderText("Latitude (e.g., 40.7128)")
    tip(sabbath_lat, "SABBATH_LAT\nLatitude for astronomical sabbath calculations.")

    sabbath_lon = QtWidgets.QLineEdit(_env_or_profile("SABBATH_LON", _profile_text("sabbath_lon")))
    sabbath_lon.setPlaceholderText("Longitude (e.g., -74.0060)")
    tip(sabbath_lon, "SABBATH_LON\nLongitude for astronomical sabbath calculations.")

    def _set_system_timezone() -> None:
        tzinfo = datetime.now().astimezone().tzinfo
        tz_key = getattr(tzinfo, "key", "") if tzinfo else ""
        sabbath_tz.setText(tz_key or str(tzinfo) or "America/New_York")

    def _resolve_sabbath_city() -> None:
        raw_city = sabbath_city.text().strip()
        if not raw_city:
            QtWidgets.QMessageBox.information(dlg, "Resolve city", "Enter a city name first.")
            return
        slug = re.sub(r"[^a-z0-9]+", "-", raw_city.strip().lower()).strip("-")
        if not slug:
            QtWidgets.QMessageBox.warning(dlg, "Resolve city", "City name is not valid.")
            return
        url = f"https://www.timeanddate.com/sun/usa/{urllib.parse.quote(slug)}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                html = resp.read().decode("utf-8", "ignore")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(dlg, "Resolve city", f"Failed to fetch city data: {exc}")
            return
        m_lat = re.search(r"lat=([-0-9.]+)", html)
        m_lon = re.search(r"lon=([-0-9.]+)", html)
        if not m_lat or not m_lon:
            QtWidgets.QMessageBox.warning(
                dlg,
                "Resolve city",
                "Could not find coordinates. Check spelling or enter lat/lon manually.",
            )
            return
        try:
            lat = float(m_lat.group(1))
            lon = float(m_lon.group(1))
        except Exception:
            QtWidgets.QMessageBox.warning(dlg, "Resolve city", "Invalid coordinates returned.")
            return
        sabbath_lat.setText(f"{lat:.6f}".rstrip("0").rstrip("."))
        sabbath_lon.setText(f"{lon:.6f}".rstrip("0").rstrip("."))
        tz_name = None
        try:
            from timezonefinder import TimezoneFinder

            tz_name = TimezoneFinder().timezone_at(lng=lon, lat=lat)
        except Exception:
            tz_name = None
        if tz_name:
            sabbath_tz.setText(tz_name)
        else:
            QtWidgets.QMessageBox.information(
                dlg,
                "Resolve city",
                "Timezone could not be resolved. Set it manually (e.g., America/New_York).",
            )
        sabbath_astro_chk.setChecked(True)

    tz_btn.clicked.connect(_set_system_timezone)
    resolve_city_btn.clicked.connect(_resolve_sabbath_city)

    log_level_combo = QtWidgets.QComboBox()
    log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
    log_level_combo.setCurrentText((self._effective_env_value("LOG_LEVEL")[0] or "INFO").upper())
    tip(log_level_combo, "LOG_LEVEL\nLogging verbosity for the core bot.")

    session_edit = QtWidgets.QLineEdit(self._effective_env_value("SESSION_NAME")[0] or "tradebot")
    tip(session_edit, "SESSION_NAME\ntmux session name used by the launcher (terminal dashboard).")

    log_row = QtWidgets.QHBoxLayout()
    log_edit = QtWidgets.QLineEdit(self._effective_env_value("TRADEBOT_LOG")[0] or str(settings.log_file))
    log_browse = QtWidgets.QPushButton("Browse…")
    tip(log_edit, "TRADEBOT_LOG\nPath to the log file tailed by the dashboard/GUI.")
    tip(
        log_browse,
        "GUI_LOG_BROWSE\nChoose which log file the GUI/tmux dashboard should tail.",
    )
    log_row.addWidget(log_edit, 1)
    log_row.addWidget(log_browse)
    log_row_w = QtWidgets.QWidget(dlg)
    log_row_w.setLayout(log_row)

    cmd_preview = QtWidgets.QLineEdit()
    cmd_preview.setReadOnly(True)
    tip(
        cmd_preview,
        "TMUX_RESTART_PREVIEW\nShows the exact `./scripts/tradebot.sh --restart ...` command this settings dialog would run.",
    )

    # Market Data Mode
    market_data_mode = QtWidgets.QComboBox()
    market_data_mode.addItem("IBKR (Primary)", "primary")
    market_data_mode.addItem("Hybrid (Auto-Route)", "hybrid")
    market_data_mode.addItem("Crypto Only (Alt)", "alternative")
    market_data_mode.addItem("Coinbase Futures", "coinbase_futures")
    
    _mdm = (self._effective_env_value("MARKET_DATA_MODE")[0] or "primary").strip()
    # Fallback to legacy Exchange Provider logic if explicit mode not set but EX_PROV is
    if not os.getenv("MARKET_DATA_MODE") and os.getenv("EXCHANGE_PROVIDER"):
        _mdm = os.getenv("EXCHANGE_PROVIDER").strip()

    for i in range(market_data_mode.count()):
        if str(market_data_mode.itemData(i) or "") == _mdm:
            market_data_mode.setCurrentIndex(i)
            break
    tip(market_data_mode, "MARKET_DATA_MODE\nPrimary: IBKR only\nAlternative: Crypto plugin (Spot)\nCoinbase Futures: Coinbase V3 Futures\nHybrid: Smart routing")

    # Broker Execution Mode
    broker_mode = QtWidgets.QComboBox()
    broker_mode.addItem("IBKR (Primary)", "primary")
    broker_mode.addItem("Hybrid (Auto-Route)", "hybrid")
    broker_mode.addItem("Crypto Only (Alt)", "alternative")
    broker_mode.addItem("Coinbase Futures", "coinbase_futures")

    _bm = (self._effective_env_value("BROKER_MODE")[0] or "primary").strip()
    if not os.getenv("BROKER_MODE") and os.getenv("EXCHANGE_PROVIDER"):
        _bm = os.getenv("EXCHANGE_PROVIDER").strip()
        
    for i in range(broker_mode.count()):
        if str(broker_mode.itemData(i) or "") == _bm:
            broker_mode.setCurrentIndex(i)
            break
    tip(broker_mode, "BROKER_MODE\nPrimary: IBKR only\nAlternative: CCXT/Alt (Spot)\nCoinbase Futures: Coinbase V3 Futures\nHybrid: Smart routing")


    alt_md = QtWidgets.QComboBox()
    alt_md.addItem("IBKR", "mock")
    alt_md.addItem("Crypto Public (REST)", "coinbase")
    alt_md.addItem("Coinbase Futures (V3)", "coinbase_futures")
    _amd = (self._effective_env_value("ALTERNATIVE_MARKET_DATA")[0] or "mock").strip()
    for i in range(alt_md.count()):
        if str(alt_md.itemData(i) or "") == _amd:
            alt_md.setCurrentIndex(i)
            break
    tip(alt_md, "Crypto Backend (Data)\nSelects the provider for Crypto data (Coinbase vs Paper).\nOnly uses this if Data Mode is Hybrid or Alt.")

    alt_broker = QtWidgets.QComboBox()
    alt_broker.addItem("IBKR", "mock")
    alt_broker.addItem("CCXT (Spot)", "ccxt")
    alt_broker.addItem("Coinbase V3 (Futures)", "coinbase_futures")
    _ab = (self._effective_env_value("ALTERNATIVE_BROKER")[0] or "mock").strip()
    for i in range(alt_broker.count()):
        if str(alt_broker.itemData(i) or "") == _ab:
            alt_broker.setCurrentIndex(i)
            break
    tip(alt_broker, "Crypto Backend (Execution)\nSelects the broker for Crypto trades (CCXT vs Paper).\nOnly uses this if Broker Mode is Hybrid or Alt.")

    default_symbol = QtWidgets.QLineEdit(self._effective_env_value("MARKET_DEFAULT_SYMBOL")[0] or "")
    tip(default_symbol, "MARKET_DEFAULT_SYMBOL\nOptional symbol override (used when no active symbol is detected).")
    default_tf = QtWidgets.QComboBox()
    default_tf.addItems(["1m", "2m", "5m", "15m", "30m", "1h", "4h", "1d"])
    default_tf.setCurrentText((self._effective_env_value("MARKET_DEFAULT_TIMEFRAME")[0] or "5m").strip())
    tip(default_tf, "MARKET_DEFAULT_TIMEFRAME\nDefault timeframe for snapshots/candles (when applicable).")

    candle_size = QtWidgets.QComboBox()
    candle_sizes = [
        ("1 min", "1 min"),
        ("5 min", "5 mins"),
        ("15 min", "15 mins"),
        ("30 min", "30 mins"),
        ("Hourly", "1 hour"),
        ("Daily", "1 day"),
        ("Weekly", "1 week"),
        ("Monthly", "1 month"),
    ]
    for label, val in candle_sizes:
        candle_size.addItem(label, val)
    for i in range(candle_size.count()):
        if str(candle_size.itemData(i) or "") == str(getattr(settings, 'candle_tf', '5 mins') or ""):
            candle_size.setCurrentIndex(i)
            break
    tip(candle_size, "Candles (chart)\nIBKR bar size for the candle pane (GUI only).")

    max_candles = QtWidgets.QSpinBox()
    max_candles.setRange(50, 5000)
    try:
        max_candles.setValue(int(self._effective_env_value("MARKET_MAX_CANDLES")[0] or "200"))
    except Exception:
        max_candles.setValue(200)
    tip(max_candles, "MARKET_MAX_CANDLES\nHow many candles to request/store per symbol (where supported).")

    symbols_edit = QtWidgets.QPlainTextEdit()
    symbols_edit.setPlaceholderText("Comma-separated symbols (e.g. SPY,QQQ,BTCUSD,ETHUSD)")
    symbols_edit.setMaximumHeight(90)
    symbols_edit.setPlainText(self._effective_env_value("MARKET_SYMBOLS")[0].strip())
    tip(symbols_edit, "MARKET_SYMBOLS\nOptional comma-separated symbol universe override.")

    cancel_orders = bool_chk("CANCEL_ORDERS_ON_START", "Cancel working orders on start")
    flatten_exit = bool_chk("FLATTEN_ON_EXIT", "Flatten on exit")
    intraday_flatten = bool_chk("INTRADAY_FLATTEN", "Intraday flatten")
    allow_inherit = bool_chk("ALLOW_INHERITED_POSITION", "Allow inherited positions")
    multi_positions = bool_chk("MULTI_POSITION_ENABLED", "Allow multiple positions (opt-in)")
    tip(cancel_orders, "CANCEL_ORDERS_ON_START\nCancel any working orders when the bot starts.")
    tip(flatten_exit, "FLATTEN_ON_EXIT\nAttempt to close open positions when the bot exits.")
    tip(intraday_flatten, "INTRADAY_FLATTEN\nFlatten positions near end of US session (if enabled in runtime).")

    # [ANTIGRAVITY] RED ALERT: Warn against flatten options on perpetual futures
    def _warn_flatten_on_futures(checkbox: QtWidgets.QCheckBox, setting_name: str):
        """Show red-alert warning if user enables flatten on futures mode."""
        def _on_toggled(checked: bool):
            if checked and broker_mode.currentData() == "coinbase_futures":
                QtWidgets.QMessageBox.critical(
                    dlg,
                    "DANGER: Flatten on Perpetual Futures",
                    f"<b style='color:red;'>RED ALERT!</b><br><br>"
                    f"You are enabling <b>{setting_name}</b> while using <b>Coinbase Futures</b>.<br><br>"
                    f"Coinbase Nano futures are <b>perpetual-style contracts</b> with 5-year expiry. "
                    f"There is <b>NO daily settlement</b> that forces position closure.<br><br>"
                    f"Enabling auto-flatten will cause <b>unnecessary forced exits</b> that can "
                    f"lock in losses at arbitrary times instead of letting your stop-loss or "
                    f"take-profit work properly.<br><br>"
                    f"<b>Recommendation:</b> Keep flatten OFF for futures trading.",
                    QtWidgets.QMessageBox.Ok,
                )
        checkbox.toggled.connect(_on_toggled)

    _warn_flatten_on_futures(flatten_exit, "FLATTEN_ON_EXIT")
    _warn_flatten_on_futures(intraday_flatten, "INTRADAY_FLATTEN")
    tip(allow_inherit, "ALLOW_INHERITED_POSITION\nAllow managing positions opened outside the bot (use carefully).")
    tip(
        multi_positions,
        "MULTI_POSITION_ENABLED\nWhen true, the bot may open multiple concurrent positions (subject to risk caps).\n"
        "When false, the bot blocks new entries while any other position is open (default).",
    )

    max_concurrent = QtWidgets.QSpinBox()
    max_concurrent.setRange(1, 25)
    try:
        max_concurrent.setValue(int(self._effective_env_value("MAX_CONCURRENT_POSITIONS")[0] or "1"))
    except Exception:
        max_concurrent.setValue(1)
    max_concurrent.setEnabled(multi_positions.isChecked())
    multi_positions.toggled.connect(max_concurrent.setEnabled)
    tip(
        max_concurrent,
        "MAX_CONCURRENT_POSITIONS\nMaximum number of concurrent open positions when MULTI_POSITION_ENABLED=true.\n"
        "Use IBKR_MAX_DOLLAR_RISK_PER_SYMBOL and IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT to divvy risk across positions.",
    )

    startup_crypto_policy = QtWidgets.QComboBox()
    startup_crypto_policy.addItem("Profile default", "")
    startup_crypto_policy.addItem("FLATTEN (sell/cover immediately)", "FLATTEN")
    startup_crypto_policy.addItem("REARM (keep position; re-arm synthetic stop)", "REARM")
    startup_crypto_policy.addItem("PAUSE (keep position; pause symbol)", "PAUSE")
    _scp = (self._effective_env_value("STARTUP_CRYPTO_UNPROTECTED_POLICY")[0] or "").strip().upper()
    if not _scp:
        startup_crypto_policy.setCurrentIndex(0)
    else:
        for i in range(startup_crypto_policy.count()):
            if str(startup_crypto_policy.itemData(i) or "").strip().upper() == _scp:
                startup_crypto_policy.setCurrentIndex(i)
                break
    tip(
        startup_crypto_policy,
        "STARTUP_CRYPTO_UNPROTECTED_POLICY\nPolicy for ZEROHASH crypto positions missing a persisted synthetic stop.\n"
        "Profile default is usually REARM. FLATTEN immediately sells/covers; REARM avoids immediate sells by recreating the stop.\n"
        "PAUSE keeps the position but blocks new actions on that symbol until a stop is rearmed.",
    )

    scale_out = QtWidgets.QDoubleSpinBox()
    scale_out.setRange(0.0, 1.0)
    scale_out.setSingleStep(0.05)
    try:
        scale_out.setValue(float(self._effective_env_value("SCALE_OUT_FRACTION")[0] or "0.5"))
    except Exception:
        scale_out.setValue(0.5)
    tip(scale_out, "SCALE_OUT_FRACTION\nFraction of position to scale out at targets (0–1).")

    min_pos_scale = QtWidgets.QDoubleSpinBox()
    min_pos_scale.setDecimals(6)
    min_pos_scale.setRange(0.0, 1_000_000.0)
    min_pos_scale.setSingleStep(0.01)
    try:
        min_pos_scale.setValue(float(self._effective_env_value("MIN_POSITION_SIZE_TO_SCALE")[0] or "0.0"))
    except Exception:
        min_pos_scale.setValue(0.0)
    tip(min_pos_scale, "MIN_POSITION_SIZE_TO_SCALE\nMinimum position size before scaling logic applies.")

    emergency_stop = QtWidgets.QDoubleSpinBox()
    emergency_stop.setDecimals(4)
    emergency_stop.setRange(0.0, 0.2)
    emergency_stop.setSingleStep(0.001)
    try:
        emergency_stop.setValue(float(self._effective_env_value("EMERGENCY_STOP_PCT")[0] or "0.005"))
    except Exception:
        emergency_stop.setValue(0.005)
    tip(emergency_stop, "EMERGENCY_STOP_PCT\nEmergency stop percentage used by runtime safeguards.")

    max_adds = QtWidgets.QSpinBox()
    max_adds.setRange(0, 10)
    try:
        max_adds.setValue(int(self._effective_env_value("MAX_SCALE_INS_PER_LEG")[0] or "2"))
    except Exception:
        max_adds.setValue(2)
    tip(max_adds, "MAX_SCALE_INS_PER_LEG\nMaximum number of adds (scale-ins) per leg.")

    # Day Trade Guards
    allow_day_trades = bool_chk("ALLOW_DAY_TRADES", "Allow day trades (exit before min hold)")
    tip(
        allow_day_trades,
        "ALLOW_DAY_TRADES\n"
        "When enabled, allows exits before the minimum hold duration.\n"
        "When disabled, positions must be held for MIN_HOLD_SECONDS before exiting.\n\n"
        "Use case:\n"
        "- Disable to enforce swing trading (hold overnight)\n"
        "- Enable for intraday strategies that may exit same-day"
    )

    min_hold_seconds = QtWidgets.QSpinBox()
    min_hold_seconds.setRange(0, 86400)  # 0 to 24 hours
    min_hold_seconds.setSuffix(" seconds")
    try:
        min_hold_seconds.setValue(int(self._effective_env_value("MIN_HOLD_SECONDS")[0] or "0"))
    except Exception:
        min_hold_seconds.setValue(0)
    tip(
        min_hold_seconds,
        "MIN_HOLD_SECONDS\n"
        "Minimum seconds to hold a position before allowing exit.\n\n"
        "Use cases:\n"
        "- Set to 0 to allow immediate exits (day trading)\n"
        "- Set to 3600 (1 hour) to prevent rapid churn\n"
        "- Set to 86400 (24 hours) to enforce overnight holds (swing trading)\n\n"
        "This works in conjunction with ALLOW_DAY_TRADES."
    )

    synth_stop_store = QtWidgets.QLineEdit(self._effective_env_value("SYNTH_STOP_STORE_PATH")[0])
    pos_hold_store = QtWidgets.QLineEdit(self._effective_env_value("POSITION_HOLD_STORE_PATH")[0])
    tip(synth_stop_store, "SYNTH_STOP_STORE_PATH\nPath to synthetic stops persistence store (JSON).")
    tip(pos_hold_store, "POSITION_HOLD_STORE_PATH\nPath to position-hold persistence store (JSON).")

    def browse_path(target: QtWidgets.QLineEdit, title: str) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            dlg, title, target.text().strip() or str(repo_root), "All files (*)"
        )
        if path:
            target.setText(path)

    synth_browse = QtWidgets.QPushButton("Browse…")
    synth_browse.clicked.connect(lambda: browse_path(synth_stop_store, "Select synthetic stop store path"))
    synth_row = QtWidgets.QHBoxLayout()
    synth_row.addWidget(synth_stop_store, 1)
    synth_row.addWidget(synth_browse)
    synth_row_w = QtWidgets.QWidget(dlg)
    synth_row_w.setLayout(synth_row)

    pos_browse = QtWidgets.QPushButton("Browse…")
    tip(
        synth_browse,
        "GUI_BROWSE_SYNTH_STOP_STORE\nBrowse for a JSON file path and fill SYNTH_STOP_STORE_PATH.",
    )
    tip(
        pos_browse,
        "GUI_BROWSE_POSITION_HOLD_STORE\nBrowse for a JSON file path and fill POSITION_HOLD_STORE_PATH.",
    )
    pos_browse.clicked.connect(lambda: browse_path(pos_hold_store, "Select position hold store path"))
    pos_row = QtWidgets.QHBoxLayout()
    pos_row.addWidget(pos_hold_store, 1)
    pos_row.addWidget(pos_browse)
    pos_row_w = QtWidgets.QWidget(dlg)
    pos_row_w.setLayout(pos_row)

    friction_fs = bool_chk("FRICTION_FAIL_SAFE", "Friction fail-safe")
    friction_cap = QtWidgets.QDoubleSpinBox()
    friction_cap.setRange(0.0, 1.0)
    friction_cap.setSingleStep(0.005)
    try:
        friction_cap.setValue(float(self._effective_env_value("FRICTION_RISK_CAP")[0] or "0.02"))
    except Exception:
        friction_cap.setValue(0.02)
    tip(friction_fs, "FRICTION_FAIL_SAFE\nIf enabled, blocks trades when friction/spread looks too high.")
    tip(friction_cap, "FRICTION_RISK_CAP\nMax tolerated friction/spread metric (higher = more permissive).")

    vix_fs = bool_chk("VIX_FAIL_SAFE", "VIX fail-safe")
    vix_cap = QtWidgets.QDoubleSpinBox()
    vix_cap.setRange(0.0, 1.0)
    vix_cap.setSingleStep(0.005)
    try:
        vix_cap.setValue(float(self._effective_env_value("VIX_RISK_CAP")[0] or "0.03"))
    except Exception:
        vix_cap.setValue(0.03)
    tip(vix_fs, "VIX_FAIL_SAFE\nIf enabled, blocks trades when volatility regime looks too risky.")
    tip(vix_cap, "VIX_RISK_CAP\nMax tolerated volatility risk metric (higher = more permissive).")

    confluence_external = bool_chk("CONFLUENCE_EXTERNAL", "Include external confluence")
    commitment_mode = bool_chk("COMMITMENT_MODE", "Commitment mode (hold position bias)")
    bypass_schedule = bool_chk("BUG_BYPASS_SCHEDULE", "Bypass schedule windows (debug)")
    tip(confluence_external, "CONFLUENCE_EXTERNAL\nInclude external confluence signals (if available).")
    tip(commitment_mode, "COMMITMENT_MODE\nWhen in a position, prefer HOLD decisions vs churn every cycle.")
    tip(bypass_schedule, "BUG_BYPASS_SCHEDULE\nDebug override: bypass schedule windows. Use carefully.")

    # Auto-restart settings
    auto_restart_chk = bool_chk("AUTO_RESTART_ON_ERROR", "Auto-restart bot on IBKR connection errors")
    auto_restart_stale_spin = QtWidgets.QSpinBox()
    auto_restart_stale_spin.setRange(60, 3600)
    auto_restart_stale_spin.setSuffix(" seconds")
    try:
        auto_restart_stale_spin.setValue(int(self._effective_env_value("AUTO_RESTART_STALE_SECONDS")[0]))
    except Exception:
        auto_restart_stale_spin.setValue(300)

    auto_restart_min_uptime_spin = QtWidgets.QSpinBox()
    auto_restart_min_uptime_spin.setRange(30, 600)
    auto_restart_min_uptime_spin.setSuffix(" seconds")
    try:
        auto_restart_min_uptime_spin.setValue(int(self._effective_env_value("AUTO_RESTART_MIN_UPTIME_SECONDS")[0]))
    except Exception:
        auto_restart_min_uptime_spin.setValue(120)

    auto_restart_cooldown_spin = QtWidgets.QSpinBox()
    auto_restart_cooldown_spin.setRange(60, 1800)
    auto_restart_cooldown_spin.setSuffix(" seconds")
    try:
        auto_restart_cooldown_spin.setValue(int(self._effective_env_value("AUTO_RESTART_COOLDOWN_SECONDS")[0]))
    except Exception:
        auto_restart_cooldown_spin.setValue(600)

    tip(auto_restart_chk, "AUTO_RESTART_ON_ERROR\nAuto-restart the bot if IBKR health looks stuck.\n\nWhat it does:\n- Watches IBKR connection + account summary freshness\n- If data stays stale too long, bot restarts itself\n- Uses cooldown and minimum-uptime guard to avoid restart loops")
    tip(auto_restart_stale_spin, "AUTO_RESTART_STALE_SECONDS\nHow long IBKR data can be stale before restart triggers.\n\nDefault: 300s (5 minutes)\nLower values = restart sooner\nHigher values = more tolerant of transient issues")
    tip(auto_restart_min_uptime_spin, "AUTO_RESTART_MIN_UPTIME_SECONDS\nMinimum uptime before auto-restart is allowed.\n\nDefault: 120s (2 minutes)\nPrevents restart loops during slow boot/connect phases")
    tip(auto_restart_cooldown_spin, "AUTO_RESTART_COOLDOWN_SECONDS\nMinimum seconds between auto-restarts.\n\nDefault: 600s (10 minutes)\nPrevents rapid restart loops if IBKR remains unstable")

    def _auto_bool_combo(profile_value: bool, env_key: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.addItem(
            f"Auto (profile: {'Enabled' if profile_value else 'Disabled'})",
            "",
        )
        combo.addItem("Enabled", "true")
        combo.addItem("Disabled", "false")
        raw = self._effective_env_value(env_key)[0].strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            combo.setCurrentIndex(1)
        elif raw in {"0", "false", "no", "off"}:
            combo.setCurrentIndex(2)
        else:
            combo.setCurrentIndex(0)
        return combo

    def _auto_int_spin(profile_value: str, env_key: str, min_val: int, max_val: int) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(-1, max_val)
        spin.setSpecialValueText(f"Auto (profile: {profile_value})")
        spin.setSingleStep(1)
        raw = self._effective_env_value(env_key)[0].strip()
        try:
            spin.setValue(int(raw))
        except Exception:
            spin.setValue(-1)
        return spin

    def _auto_float_spin(
        profile_value: str,
        env_key: str,
        min_val: float,
        max_val: float,
        step: float,
        decimals: int,
    ) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(-1.0, max_val)
        spin.setSpecialValueText(f"Auto (profile: {profile_value})")
        spin.setSingleStep(step)
        raw = self._effective_env_value(env_key)[0].strip()
        try:
            spin.setValue(float(raw))
        except Exception:
            spin.setValue(-1.0)
        return spin

    htf_combo = QtWidgets.QComboBox()
    htf_profile = _profile_text("htf_timeframe", "4h")
    htf_combo.addItem(f"Auto (profile: {htf_profile})", "")
    for tf in ("1h", "2h", "4h", "6h", "1d"):
        htf_combo.addItem(tf, tf)
    htf_env = self._effective_env_value("PROFILE_HTF_TIMEFRAME")[0].strip()
    if htf_env:
        htf_combo.setCurrentText(htf_env)
    else:
        htf_combo.setCurrentIndex(0)
    tip(htf_combo, "PROFILE_HTF_TIMEFRAME\nHigher timeframe for ICC structure trend.")

    ltf_combo = QtWidgets.QComboBox()
    ltf_profile = _profile_text("ltf_timeframe", "")
    ltf_label = ltf_profile or "candle_timeframe"
    ltf_combo.addItem(f"Auto (profile: {ltf_label})", "")
    for tf in ("1m", "2m", "5m", "15m", "30m", "1h"):
        ltf_combo.addItem(tf, tf)
    ltf_env = self._effective_env_value("PROFILE_LTF_TIMEFRAME")[0].strip()
    if ltf_env:
        ltf_combo.setCurrentText(ltf_env)
    else:
        ltf_combo.setCurrentIndex(0)
    tip(ltf_combo, "PROFILE_LTF_TIMEFRAME\nLower timeframe for ICC execution structure.")

    trend_window_spin = _auto_int_spin(
        _profile_text("trend_window", "120"),
        "PROFILE_TREND_WINDOW",
        20,
        1000,
    )
    tip(trend_window_spin, "PROFILE_TREND_WINDOW\nCandles used to infer HTF swing structure.")

    trend_swing_spin = _auto_int_spin(
        _profile_text("trend_swing_lookback", "2"),
        "PROFILE_TREND_SWING_LOOKBACK",
        1,
        10,
    )
    tip(trend_swing_spin, "PROFILE_TREND_SWING_LOOKBACK\nFractal lookback for swing highs/lows.")

    trend_min_swings_spin = _auto_int_spin(
        _profile_text("trend_min_swings", "3"),
        "PROFILE_TREND_MIN_SWINGS",
        2,
        10,
    )
    tip(trend_min_swings_spin, "PROFILE_TREND_MIN_SWINGS\nMinimum swings for HH/HL or LH/LL trend.")

    trend_strength_spin = _auto_float_spin(
        _profile_text("trend_strength_floor", "0.5"),
        "PROFILE_TREND_STRENGTH_FLOOR",
        0.0,
        1.0,
        0.05,
        2,
    )
    tip(trend_strength_spin, "PROFILE_TREND_STRENGTH_FLOOR\nMin strength to avoid chop.")

    structure_score_spin = _auto_float_spin(
        _profile_text("structure_score_threshold", "0.3"),
        "PROFILE_STRUCTURE_SCORE_THRESHOLD",
        0.0,
        1.0,
        0.01,
        3,
    )
    tip(structure_score_spin, "PROFILE_STRUCTURE_SCORE_THRESHOLD\nStructure cleanliness threshold.")

    session_gate_combo = _auto_bool_combo(
        bool(getattr(profile_settings, "session_gate_enabled", True)),
        "PROFILE_SESSION_GATE_ENABLED",
    )
    tip(
        session_gate_combo,
        "PROFILE_SESSION_GATE_ENABLED\n"
        "A+ session health gate. When enabled, entries flagged as A+ must see "
        "range + volume expansion to avoid chopping in dead sessions.\n"
        "Trade by SCI default: Enabled.",
    )

    session_min_candles_spin = _auto_int_spin(
        _profile_text("session_gate_min_candles", "30"),
        "PROFILE_SESSION_GATE_MIN_CANDLES",
        10,
        500,
    )
    tip(
        session_min_candles_spin,
        "PROFILE_SESSION_GATE_MIN_CANDLES\n"
        "Minimum number of candles required before session health is enforced.\n"
        "Lower values make the gate apply sooner; higher values need more history.",
    )

    session_range_mult_spin = _auto_float_spin(
        _profile_text("session_range_multiplier", "1.1"),
        "PROFILE_SESSION_RANGE_MULTIPLIER",
        0.0,
        3.0,
        0.05,
        2,
    )
    tip(
        session_range_mult_spin,
        "PROFILE_SESSION_RANGE_MULTIPLIER\n"
        "Range expansion multiple required for an A+ continuation.\n"
        "Example: 1.1 means the last 5 bars must average 10% more range "
        "than the prior 20 bars.",
    )

    session_volume_mult_spin = _auto_float_spin(
        _profile_text("session_volume_multiplier", "1.1"),
        "PROFILE_SESSION_VOLUME_MULTIPLIER",
        0.0,
        5.0,
        0.05,
        2,
    )
    tip(
        session_volume_mult_spin,
        "PROFILE_SESSION_VOLUME_MULTIPLIER\n"
        "Volume expansion multiple required for an A+ continuation.\n"
        "Example: 1.1 means recent volume must be 10% above prior volume.",
    )

    session_overlap_start_spin = _auto_int_spin(
        _profile_text("session_overlap_start_hour", "12"),
        "PROFILE_SESSION_OVERLAP_START_HOUR",
        0,
        23,
    )
    session_overlap_end_spin = _auto_int_spin(
        _profile_text("session_overlap_end_hour", "16"),
        "PROFILE_SESSION_OVERLAP_END_HOUR",
        0,
        23,
    )
    tip(
        session_overlap_start_spin,
        "PROFILE_SESSION_OVERLAP_START_HOUR\n"
        "Local hour (0-23) when FX/crypto session bias begins.\n"
        "Default 12 (UTC) approximates London/NY overlap.",
    )
    tip(
        session_overlap_end_spin,
        "PROFILE_SESSION_OVERLAP_END_HOUR\n"
        "Local hour (0-23) when FX/crypto session bias ends (exclusive).\n"
        "Default 16 (UTC) approximates London/NY overlap.",
    )

    pdt_guard_combo = _auto_bool_combo(bool(getattr(profile_settings, "pdt_guard_enabled", False)), "PROFILE_PDT_GUARD_ENABLED")
    tip(pdt_guard_combo, "PROFILE_PDT_GUARD_ENABLED\nEnable PDT guard for equities.")

    max_roundtrips_spin = _auto_int_spin(
        _profile_text("max_equity_roundtrips_per_day", "2"),
        "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY",
        1,
        20,
    )
    tip(max_roundtrips_spin, "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY\nMax equity roundtrips per day.")

    flip_enabled_combo = _auto_bool_combo(bool(getattr(profile_settings, "flip_actions_enabled", False)), "PROFILE_FLIP_ACTIONS_ENABLED")
    tip(flip_enabled_combo, "PROFILE_FLIP_ACTIONS_ENABLED\nAllow flip_to_long/flip_to_short actions.")

    flip_cooldown_spin = _auto_int_spin(
        _profile_text("flip_cooldown_seconds", "600"),
        "PROFILE_FLIP_COOLDOWN_SECONDS",
        0,
        86400,
    )
    tip(flip_cooldown_spin, "PROFILE_FLIP_COOLDOWN_SECONDS\nCooldown between flips when PDT guard is active.")

    cooldown_enabled_combo = _auto_bool_combo(bool(getattr(profile_settings, "cooldown_enabled", True)), "PROFILE_COOLDOWN_ENABLED")
    tip(cooldown_enabled_combo, "PROFILE_COOLDOWN_ENABLED\nEnable ICC cooldowns after blocks/successes.")

    cooldown_block_spin = _auto_int_spin(
        _profile_text("cooldown_cycles_after_block", "3"),
        "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK",
        0,
        50,
    )
    tip(cooldown_block_spin, "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK\nCycles to skip after a block.")

    cooldown_success_spin = _auto_int_spin(
        _profile_text("cooldown_cycles_after_success", "0"),
        "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS",
        0,
        50,
    )
    tip(cooldown_success_spin, "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS\nCycles to skip after success.")

    cooldown_scope_combo = QtWidgets.QComboBox()
    cooldown_scope_combo.addItem(
        f"Auto (profile: {_profile_text('cooldown_scope', 'symbol')})",
        "",
    )
    cooldown_scope_combo.addItem("symbol", "symbol")
    cooldown_scope_combo.addItem("global", "global")
    scope_env = self._effective_env_value("PROFILE_COOLDOWN_SCOPE")[0].strip().lower()
    if scope_env in {"symbol", "global"}:
        cooldown_scope_combo.setCurrentText(scope_env)
    else:
        cooldown_scope_combo.setCurrentIndex(0)
    tip(cooldown_scope_combo, "PROFILE_COOLDOWN_SCOPE\nApply cooldown per symbol or globally.")

    stick_to_active_combo = QtWidgets.QComboBox()
    stick_profile = _profile_text("stick_to_active_symbol_until", "cycle_end")
    stick_to_active_combo.addItem(f"Auto (profile: {stick_profile})", "")
    stick_to_active_combo.addItem("cycle_end", "cycle_end")
    stick_to_active_combo.addItem("decision_end", "decision_end")
    stick_env = self._effective_env_value("PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL")[0].strip()
    if stick_env:
        stick_to_active_combo.setCurrentText(stick_env)
    else:
        stick_to_active_combo.setCurrentIndex(0)
    tip(stick_to_active_combo, "PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL\nStick to active symbol policy.")

    # ICC Scoring Parameters
    icc_entry_score_threshold_spin = _auto_float_spin(
        _profile_text("icc_entry_score_threshold", "55.0"),
        "PROFILE_ICC_ENTRY_SCORE_THRESHOLD",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        icc_entry_score_threshold_spin,
        "PROFILE_ICC_ENTRY_SCORE_THRESHOLD\n"
        "Minimum total score required for automatic entry.\n"
        "ICC point-based scoring: HTF/LTF align (30) + sweep (25) + continuation (25) + strong HTF (15) + phase (5) = 100 max.\n"
        "Default 55 allows entry with core gates (HTF/LTF + sweep + continuation).\n"
        "AI can override scores below threshold if enabled.",
    )

    icc_score_htf_ltf_align_points_spin = _auto_float_spin(
        _profile_text("icc_score_htf_ltf_align_points", "30.0"),
        "PROFILE_ICC_SCORE_HTF_LTF_ALIGN_POINTS",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        icc_score_htf_ltf_align_points_spin,
        "PROFILE_ICC_SCORE_HTF_LTF_ALIGN_POINTS\n"
        "Points awarded when HTF and LTF trends are aligned.\n"
        "Default 30 points (largest component) - core ICC requirement.",
    )

    icc_score_sweep_points_spin = _auto_float_spin(
        _profile_text("icc_score_sweep_points", "25.0"),
        "PROFILE_ICC_SCORE_SWEEP_POINTS",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        icc_score_sweep_points_spin,
        "PROFILE_ICC_SCORE_SWEEP_POINTS\n"
        "Points awarded for confirmed liquidity sweep.\n"
        "Default 25 points - validates correction absorbed orders.",
    )

    icc_score_continuation_points_spin = _auto_float_spin(
        _profile_text("icc_score_continuation_points", "25.0"),
        "PROFILE_ICC_SCORE_CONTINUATION_POINTS",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        icc_score_continuation_points_spin,
        "PROFILE_ICC_SCORE_CONTINUATION_POINTS\n"
        "Points awarded for BOS + continuation close beyond correction.\n"
        "Default 25 points - confirms momentum resuming.",
    )

    icc_score_strong_htf_points_spin = _auto_float_spin(
        _profile_text("icc_score_strong_htf_points", "15.0"),
        "PROFILE_ICC_SCORE_STRONG_HTF_POINTS",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        icc_score_strong_htf_points_spin,
        "PROFILE_ICC_SCORE_STRONG_HTF_POINTS\n"
        "Bonus points for strong HTF trend (above strength threshold).\n"
        "Default 15 points - rewards clean macro structure.",
    )

    icc_score_phase_points_spin = _auto_float_spin(
        _profile_text("icc_score_phase_points", "5.0"),
        "PROFILE_ICC_SCORE_PHASE_POINTS",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        icc_score_phase_points_spin,
        "PROFILE_ICC_SCORE_PHASE_POINTS\n"
        "Bonus points for favorable market phase alignment.\n"
        "Default 5 points - minor boost for ideal timing.",
    )

    icc_score_htf_strength_threshold_spin = _auto_float_spin(
        _profile_text("icc_score_htf_strength_threshold", "0.7"),
        "PROFILE_ICC_SCORE_HTF_STRENGTH_THRESHOLD",
        0.0,
        1.0,
        0.05,
        2,
    )
    tip(
        icc_score_htf_strength_threshold_spin,
        "PROFILE_ICC_SCORE_HTF_STRENGTH_THRESHOLD\n"
        "HTF strength threshold for awarding strong HTF bonus points.\n"
        "Default 0.7 (70%) - requires consistent HH/HL or LH/LL structure.",
    )

    # ICC Pyramiding and Exit Parameters
    max_pyramid_entries_spin = _auto_int_spin(
        _profile_text("max_pyramid_entries", "3"),
        "PROFILE_MAX_PYRAMID_ENTRIES",
        1,
        10,
    )
    tip(
        max_pyramid_entries_spin,
        "PROFILE_MAX_PYRAMID_ENTRIES\n"
        "Maximum number of pyramid entries allowed per position.\n"
        "ICC methodology: allows up to 3 entries (initial + 2 adds) into winning positions.\n"
        "Each add uses same 10% risk, so 3 entries = 30% total risk with pyramiding.",
    )

    pyramid_score_threshold_spin = _auto_float_spin(
        _profile_text("pyramid_score_threshold", "70.0"),
        "PROFILE_PYRAMID_SCORE_THRESHOLD",
        0.0,
        100.0,
        1.0,
        1,
    )
    tip(
        pyramid_score_threshold_spin,
        "PROFILE_PYRAMID_SCORE_THRESHOLD\n"
        "Score threshold required to add to an existing position (pyramid).\n"
        "Higher threshold (70+) ensures only high-conviction continuations get pyramided.\n"
        "Default 70.0 requires stronger confirmation than initial entry (55.0).",
    )

    htf_neutral_exit_bars_spin = _auto_int_spin(
        _profile_text("htf_neutral_exit_bars", "48"),
        "PROFILE_HTF_NEUTRAL_EXIT_BARS",
        0,
        500,
    )
    tip(
        htf_neutral_exit_bars_spin,
        "PROFILE_HTF_NEUTRAL_EXIT_BARS\n"
        "Number of bars with HTF neutral before exiting position.\n"
        "ICC methodology: when HTF trend goes neutral (no clear HH/HL or LH/LL), "
        "wait this many bars before exiting to avoid premature exits during consolidation.\n"
        "Default 48 bars (4 hours on 5m chart) allows time for structure to re-establish.",
    )

    # ICC Auto-Entry Settings
    icc_auto_entry_enabled_combo = _auto_bool_combo(
        bool(getattr(profile_settings, "icc_auto_entry_enabled", False)),
        "PROFILE_ICC_AUTO_ENTRY_ENABLED"
    )
    tip(
        icc_auto_entry_enabled_combo,
        "PROFILE_ICC_AUTO_ENTRY_ENABLED\n"
        "Enable automatic entry on ICC sweep + continuation signals without requiring AI confirmation.\n"
        "When enabled, the bot will enter trades automatically when ICC entry criteria are met "
        "(sweep + HL/LH + BOS + continuation) and the entry score meets the threshold.",
    )

    icc_auto_entry_cooldown_spin = _auto_int_spin(
        _profile_text("icc_auto_entry_cooldown_minutes", "15"),
        "PROFILE_ICC_AUTO_ENTRY_COOLDOWN_MINUTES",
        0,
        1440,
    )
    tip(
        icc_auto_entry_cooldown_spin,
        "PROFILE_ICC_AUTO_ENTRY_COOLDOWN_MINUTES\n"
        "Cooldown period in minutes between auto-entry attempts for the same symbol.\n"
        "Prevents over-trading by enforcing a minimum wait time after an auto-entry.\n"
        "Default 15 minutes gives time to see if the entry develops properly.",
    )

    icc_auto_entry_min_htf_strength_spin = _auto_float_spin(
        _profile_text("icc_auto_entry_min_htf_strength", "0.6"),
        "PROFILE_ICC_AUTO_ENTRY_MIN_HTF_STRENGTH",
        0.0,
        1.0,
        0.05,
        2,
    )
    tip(
        icc_auto_entry_min_htf_strength_spin,
        "PROFILE_ICC_AUTO_ENTRY_MIN_HTF_STRENGTH\n"
        "Minimum HTF trend strength required for auto-entry (0.0 to 1.0).\n"
        "Higher values require clearer HTF structure before allowing automated entries.\n"
        "Default 0.6 (60%) ensures reasonably strong HTF trend confirmation.",
    )

    icc_auto_entry_require_sweep_combo = _auto_bool_combo(
        bool(getattr(profile_settings, "icc_auto_entry_require_sweep", False)),
        "PROFILE_ICC_AUTO_ENTRY_REQUIRE_SWEEP"
    )
    tip(
        icc_auto_entry_require_sweep_combo,
        "PROFILE_ICC_AUTO_ENTRY_REQUIRE_SWEEP\n"
        "Require liquidity sweep before auto-entry.\n"
        "When enabled, auto-entries must include a sweep of previous liquidity (sweep points).\n"
        "Default FALSE because backtesting (including record-breaking November 2024) showed requiring sweeps prevented ALL entries.\n"
        "While sweep+continuation is core ICC theory, real market conditions rarely trigger perfect sweeps.\n"
        "Enable only if you want ultra-strict ICC entries (warning: may result in zero trades).",
    )

    aggressive_mode_combo = _auto_bool_combo(bool(getattr(profile_settings, "icc_aggressive_mode", False)), "PROFILE_ICC_AGGRESSIVE_MODE")
    tip(
        aggressive_mode_combo,
        "PROFILE_ICC_AGGRESSIVE_MODE\n"
        "Enable aggressive ICC sizing (Phase 2). Trade by SCI defaults to enabled\n"
        "with strict guardrails (daily loss cap, exposure cap, consecutive loss cap).",
    )

    aggressive_risk_spin = _auto_float_spin(
        _profile_text("aggressive_risk_per_trade_pct", "0.03"),
        "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT",
        0.0,
        1.0,
        0.005,
        3,
    )
    tip(aggressive_risk_spin, "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT\nRisk per trade % in aggressive mode.")

    max_daily_loss_spin = _auto_float_spin(
        _profile_text("max_daily_loss_pct", "0.06"),
        "PROFILE_MAX_DAILY_LOSS_PCT",
        0.0,
        1.0,
        0.005,
        3,
    )
    tip(max_daily_loss_spin, "PROFILE_MAX_DAILY_LOSS_PCT\nDaily loss limit % (aggressive mode).")

    max_exposure_spin = _auto_float_spin(
        _profile_text("max_exposure_pct", "0.4"),
        "PROFILE_MAX_EXPOSURE_PCT",
        0.0,
        1.0,
        0.01,
        3,
    )
    tip(max_exposure_spin, "PROFILE_MAX_EXPOSURE_PCT\nTotal exposure limit % (aggressive mode).")
 
    balance_cap_spin = _auto_float_spin(
        _profile_text("balance_cap_pct", "0.95"),
        "PROFILE_BALANCE_CAP_PCT",
        0.0,
        1.0,
        0.05,
        2,
    )
    tip(
        balance_cap_spin,
        "PROFILE_BALANCE_CAP_PCT\n"
        "Safety cap on total account usage (Margin + Spot).\n"
        "Example: 0.90 means the bot will never use more than 90% of your liquid balance,\n"
        "leaving a 10% buffer for fees and margin fluctuations.\n"
        "Lower this (e.g., 0.70) if you are getting 'Insufficient Funds' errors.",
    )

    max_losses_spin = _auto_int_spin(
        _profile_text("max_consecutive_losses", "2"),
        "PROFILE_MAX_CONSECUTIVE_LOSSES",
        1,
        20,
    )
    tip(max_losses_spin, "PROFILE_MAX_CONSECUTIVE_LOSSES\nConsecutive loss cap (aggressive mode).")

    def _capital_status_text() -> str:
        last_ts_raw = os.getenv(AUTO_TUNE_LAST_TS_ENV, "").strip()
        last_eq = os.getenv(AUTO_TUNE_LAST_EQUITY_ENV, "").strip()
        last_broker = os.getenv(AUTO_TUNE_LAST_BROKER_ENV, "").strip()
        try:
            last_ts = float(last_ts_raw)
        except Exception:
            last_ts = 0.0
        if last_ts <= 0:
            return "Last run: never"
        try:
            stamp = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            stamp = last_ts_raw
        parts = [f"Last run: {stamp}"]
        if last_eq:
            parts.append(f"equity={last_eq}")
        if last_broker:
            parts.append(f"broker={last_broker}")
        return " · ".join(parts)

    commentary_combo = QtWidgets.QComboBox()
    commentary_combo.addItems(["Auto", "Off", "Internal"])
    comm = (self._effective_env_value("COMMENTARY_LLM")[0] or "").strip().lower()
    if comm == "":
        commentary_combo.setCurrentIndex(0)
    elif comm == "off":
        commentary_combo.setCurrentIndex(1)
    else:
        commentary_combo.setCurrentIndex(2)
    tip(commentary_combo, "COMMENTARY_LLM\nAuto: internal commentary\nOff: deterministic dashboard\nInternal: fetch AI commentary.")

    commentary_policy_combo = QtWidgets.QComboBox()
    commentary_policy_combo.addItems(["A+ or 4/day", "A+ only", "Interval"])
    pol = (self._effective_env_value("COMMENTARY_LLM_POLICY")[0] or "").strip().lower()
    if pol == "a_plus_only":
        commentary_policy_combo.setCurrentIndex(1)
    elif pol == "interval":
        commentary_policy_combo.setCurrentIndex(2)
    else:
        commentary_policy_combo.setCurrentIndex(0)
    tip(
        commentary_policy_combo,
        "COMMENTARY_LLM_POLICY\nControls when commentary is called.\n"
        "A+ or 4/day (recommended): call on A+ continuation (readiness=1.00), otherwise call at 4 daily slots.\n"
        "A+ only: only call when an A+ continuation appears.\n"
        "Interval: legacy behavior (calls based on COMMENTARY_LLM_MIN_SECONDS).",
    )

    commentary_slots = QtWidgets.QLineEdit(
        self._effective_env_value("COMMENTARY_LLM_DAILY_SLOTS")[0] or "09:00,12:00,18:00,22:00"
    )
    commentary_slots.setPlaceholderText("09:00,12:00,18:00,22:00")
    tip(commentary_slots, "COMMENTARY_LLM_DAILY_SLOTS\nComma-separated daily slot times (HH:MM).")

    commentary_min_spin = QtWidgets.QSpinBox()
    commentary_min_spin.setRange(5, 3600)
    try:
        commentary_min_spin.setValue(
            int(float(self._effective_env_value("COMMENTARY_LLM_MIN_SECONDS")[0] or "300"))
        )
    except Exception:
        commentary_min_spin.setValue(300)
    tip(commentary_min_spin, "COMMENTARY_LLM_MIN_SECONDS\nMinimum seconds between commentary refreshes (default: 300).")

    commentary_max_calls = QtWidgets.QSpinBox()
    commentary_max_calls.setRange(0, 10000)
    try:
        commentary_max_calls.setValue(
            int(float(self._effective_env_value("COMMENTARY_LLM_MAX_CALLS_PER_DAY")[0] or "250"))
        )
    except Exception:
        commentary_max_calls.setValue(250)
    tip(
        commentary_max_calls,
        "COMMENTARY_LLM_MAX_CALLS_PER_DAY\nHard cap across all panes per day (shared budget file).\n0 disables the cap.",
    )

    commentary_budget_path = QtWidgets.QLineEdit(self._effective_env_value("COMMENTARY_LLM_BUDGET_PATH")[0])
    commentary_budget_path.setPlaceholderText("/tmp/tradebot_sci_commentary_budget.json")
    tip(
        commentary_budget_path,
        "COMMENTARY_LLM_BUDGET_PATH\nShared JSON budget file path for commentary call limiting.\nUse a shared path if you run multiple dashboards.",
    )

    provider_combo = QtWidgets.QComboBox()
    provider_combo.setIconSize(QtCore.QSize(18, 18))
    provider_icons_root = repo_root / "src" / "tradebot_sci" / "gui" / "assets" / "providers"

    def _provider_icon(name: str) -> QtGui.QIcon:
        icon_path = provider_icons_root / f"{name}.svg"
        if icon_path.exists():
            return QtGui.QIcon(str(icon_path))
        return QtGui.QIcon()

    provider_combo.addItem(_provider_icon("openai"), "Auto (OpenAI)", "")
    provider_combo.addItem(_provider_icon("openai"), "OpenAI", "openai")
    provider_combo.addItem(_provider_icon("gemini"), "Gemini", "gemini")
    provider_combo.addItem(_provider_icon("claude"), "Claude", "claude")
    provider_combo.addItem(_provider_icon("deepseek"), "DeepSeek", "deepseek")
    provider_combo.addItem(_provider_icon("openrouter"), "OpenRouter", "openrouter")
    provider_combo.addItem(_provider_icon("custom"), "Custom (OpenAI-compatible)", "custom")
    provider_env = (self._effective_env_value("TRADE_SCI_PROVIDER")[0] or "").strip().lower()
    if provider_env:
        for idx in range(provider_combo.count()):
            if str(provider_combo.itemData(idx) or "").strip().lower() == provider_env:
                provider_combo.setCurrentIndex(idx)
                break
    else:
        provider_combo.setCurrentIndex(0)
    tip(
        provider_combo,
        "TRADE_SCI_PROVIDER\nSelect which AI provider the bot/commentary should use.\n"
        "Auto uses OpenAI defaults unless overridden.",
    )

    ai_base = QtWidgets.QLineEdit(self._effective_env_value("TRADE_SCI_API_BASE_URL")[0])
    ai_key = QtWidgets.QLineEdit(self._effective_env_value("TRADE_SCI_API_KEY")[0])
    ai_key.setEchoMode(QtWidgets.QLineEdit.Password)
    chatgpt_key = QtWidgets.QLineEdit(self._effective_env_value("CHATGPT_KEY")[0])
    chatgpt_key.setEchoMode(QtWidgets.QLineEdit.Password)
    ai_model = QtWidgets.QLineEdit(self._effective_env_value("TRADE_SCI_MODEL_NAME")[0])
    tip(ai_base, "TRADE_SCI_API_BASE_URL\nBase URL for the AI provider API (optional).")
    tip(ai_key, "TRADE_SCI_API_KEY\nAPI key for the AI provider. Stored as env var; masked here.")
    tip(chatgpt_key, "CHATGPT_KEY\nLegacy API key fallback (optional). Stored as env var; masked here.")
    tip(ai_model, "TRADE_SCI_MODEL_NAME\nModel name/id for the AI provider (optional).")
    ai_temp = QtWidgets.QDoubleSpinBox()
    ai_temp.setRange(0.0, 2.0)
    ai_temp.setSingleStep(0.05)
    try:
        ai_temp.setValue(float(self._effective_env_value("TRADE_SCI_TEMPERATURE")[0] or "0.2"))
    except Exception:
        ai_temp.setValue(0.2)
    tip(ai_temp, "TRADE_SCI_TEMPERATURE\nControls randomness/creativity for AI outputs.")
    ai_tokens = QtWidgets.QSpinBox()
    ai_tokens.setRange(128, 16384)
    try:
        ai_tokens.setValue(int(float(self._effective_env_value("TRADE_SCI_MAX_TOKENS")[0] or "2048")))
    except Exception:
        ai_tokens.setValue(2048)
    tip(ai_tokens, "TRADE_SCI_MAX_TOKENS\nMax tokens for AI responses.")

    ibkr_host = QtWidgets.QLineEdit(self._effective_env_value("IBKR_HOST")[0] or "127.0.0.1")
    ibkr_port = QtWidgets.QSpinBox()
    ibkr_port.setRange(1, 65535)
    try:
        ibkr_port.setValue(int(self._effective_env_value("IBKR_PORT")[0] or "7497"))
    except Exception:
        ibkr_port.setValue(7497)
    ibkr_crypto = QtWidgets.QLineEdit(self._effective_env_value("IBKR_CRYPTO_EXCHANGE")[0] or "ZEROHASH")
    ibkr_zerohash_tif = QtWidgets.QComboBox()
    ibkr_zerohash_tif.addItem("Auto (IOC)", "")
    ibkr_zerohash_tif.addItem("IOC", "IOC")
    ibkr_zerohash_tif.addItem("Minutes", "Minutes")
    _ztif = (self._effective_env_value("IBKR_ZEROHASH_CRYPTO_TIF")[0] or "").strip()
    if not _ztif:
        ibkr_zerohash_tif.setCurrentIndex(0)
    else:
        _ztif_n = _ztif.strip().lower()
        for i in range(ibkr_zerohash_tif.count()):
            item_val = str(ibkr_zerohash_tif.itemData(i) or "").strip().lower()
            if item_val == _ztif_n:
                ibkr_zerohash_tif.setCurrentIndex(i)
                break
    ibkr_client_id = QtWidgets.QLineEdit(self._effective_env_value("IBKR_CLIENT_ID")[0])
    ibkr_account_id = QtWidgets.QLineEdit(self._effective_env_value("IBKR_ACCOUNT_ID")[0])
    ibkr_default_ccy = QtWidgets.QLineEdit(self._effective_env_value("IBKR_DEFAULT_CCY")[0] or "USD")
    ibkr_paper = bool_chk("IBKR_PAPER", "Paper trading")
    ibkr_read_only = bool_chk("IBKR_READ_ONLY", "Read-only")
    tip(ibkr_host, "IBKR_HOST\nTWS/IB Gateway host (usually 127.0.0.1).")
    tip(ibkr_port, "IBKR_PORT\nTWS/IB Gateway port (7497 paper, 7496 live by default).")
    tip(ibkr_crypto, "IBKR_CRYPTO_EXCHANGE\nCrypto venue routing (e.g. ZEROHASH).")
    tip(
        ibkr_zerohash_tif,
        "IBKR_ZEROHASH_CRYPTO_TIF\nTIF for IBKR spot crypto on ZEROHASH.\nIBKR requires Minutes or IOC; Auto defaults to IOC.",
    )
    tip(ibkr_client_id, "IBKR_CLIENT_ID\nOptional client id for the API connection.")
    tip(ibkr_account_id, "IBKR_ACCOUNT_ID\nOptional account id to target (if multiple accounts).")
    tip(ibkr_default_ccy, "IBKR_DEFAULT_CCY\nDefault currency (e.g. USD).")
    tip(ibkr_paper, "IBKR_PAPER\ntrue: paper trading connection preference.")
    tip(ibkr_read_only, "IBKR_READ_ONLY\ntrue: do not place orders even if EXECUTE_TRADES=true.")

    # Broker risk caps live in config/broker_ibkr.yaml, but we allow optional env overrides for GUI users.
    broker_defaults: dict[str, Any] = {}
    try:
        import yaml  # type: ignore

        broker_path = repo_root / "config" / "broker_ibkr.yaml"
        if broker_path.exists():
            broker_defaults = yaml.safe_load(broker_path.read_text(encoding="utf-8")) or {}
    except Exception:
        broker_defaults = {}

    def _broker_default(key: str, fallback: Any) -> Any:
        v = broker_defaults.get(key)
        return fallback if v is None else v

    def _override_flag(env_key: str) -> bool:
        return bool((self._effective_env_value(env_key)[0] or "").strip())

    def _override_row(override_chk: QtWidgets.QCheckBox, editor: QtWidgets.QWidget) -> QtWidgets.QWidget:
        row = QtWidgets.QHBoxLayout()
        row.addWidget(override_chk, 0)
        row.addWidget(editor, 1)
        row_w = QtWidgets.QWidget()
        row_w.setLayout(row)
        return row_w

    # Max shares / symbol
    ibkr_max_shares_override = QtWidgets.QCheckBox("Override")
    ibkr_max_shares_override.setChecked(_override_flag("IBKR_MAX_SHARES_PER_SYMBOL"))
    ibkr_max_shares = QtWidgets.QSpinBox()
    ibkr_max_shares.setRange(1, 10_000)
    ibkr_max_shares.setValue(int(_broker_default("max_shares_per_symbol", 5) or 5))
    try:
        v = int((self._effective_env_value("IBKR_MAX_SHARES_PER_SYMBOL")[0] or "").strip() or "0")
        if v > 0:
            ibkr_max_shares.setValue(v)
    except Exception:
        pass
    ibkr_max_shares.setEnabled(ibkr_max_shares_override.isChecked())
    ibkr_max_shares_override.toggled.connect(ibkr_max_shares.setEnabled)
    ibkr_max_shares_row = _override_row(ibkr_max_shares_override, ibkr_max_shares)
    tip(
        ibkr_max_shares_override,
        "IBKR_MAX_SHARES_PER_SYMBOL\nOptional env override for broker_ibkr.yaml:max_shares_per_symbol.\n"
        "Enable to override from the GUI without editing YAML.",
    )
    tip(ibkr_max_shares, "BrokerSetting: max_shares_per_symbol\nPer-symbol share cap (sizing guard).")

    # Max dollar risk / symbol
    ibkr_max_sym_risk_override = QtWidgets.QCheckBox("Override")
    ibkr_max_sym_risk_override.setChecked(_override_flag("IBKR_MAX_DOLLAR_RISK_PER_SYMBOL"))
    ibkr_max_sym_risk = QtWidgets.QDoubleSpinBox()
    ibkr_max_sym_risk.setDecimals(2)
    ibkr_max_sym_risk.setRange(0.0, 1_000_000.0)
    ibkr_max_sym_risk.setSingleStep(5.0)
    ibkr_max_sym_risk.setValue(float(_broker_default("max_dollar_risk_per_symbol", 3.0) or 0.0))
    try:
        v = float((self._effective_env_value("IBKR_MAX_DOLLAR_RISK_PER_SYMBOL")[0] or "").strip() or "nan")
        if v == v:
            ibkr_max_sym_risk.setValue(max(0.0, v))
    except Exception:
        pass
    ibkr_max_sym_risk.setEnabled(ibkr_max_sym_risk_override.isChecked())
    ibkr_max_sym_risk_override.toggled.connect(ibkr_max_sym_risk.setEnabled)
    ibkr_max_sym_risk_row = _override_row(ibkr_max_sym_risk_override, ibkr_max_sym_risk)
    tip(
        ibkr_max_sym_risk_override,
        "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL\nOptional env override for broker_ibkr.yaml:max_dollar_risk_per_symbol.\n"
        "Total open bracket risk allowed per symbol (USD).",
    )
    tip(ibkr_max_sym_risk, "BrokerSetting: max_dollar_risk_per_symbol\nPer-symbol open bracket risk cap (USD).")

    # Max dollar risk / account
    ibkr_max_acct_risk_override = QtWidgets.QCheckBox("Override")
    ibkr_max_acct_risk_override.setChecked(_override_flag("IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT"))
    ibkr_max_acct_risk = QtWidgets.QDoubleSpinBox()
    ibkr_max_acct_risk.setDecimals(2)
    ibkr_max_acct_risk.setRange(0.0, 1_000_000.0)
    ibkr_max_acct_risk.setSingleStep(10.0)
    ibkr_max_acct_risk.setValue(float(_broker_default("max_dollar_risk_per_account", 0.0) or 0.0))
    try:
        v = float((self._effective_env_value("IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT")[0] or "").strip() or "nan")
        if v == v:
            ibkr_max_acct_risk.setValue(max(0.0, v))
    except Exception:
        pass
    ibkr_max_acct_risk.setEnabled(ibkr_max_acct_risk_override.isChecked())
    ibkr_max_acct_risk_override.toggled.connect(ibkr_max_acct_risk.setEnabled)
    ibkr_max_acct_risk_row = _override_row(ibkr_max_acct_risk_override, ibkr_max_acct_risk)
    tip(
        ibkr_max_acct_risk_override,
        "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT\nOptional env override for broker_ibkr.yaml:max_dollar_risk_per_account.\n"
        "Aggregate cap across all symbols (USD). Useful when MULTI_POSITION_ENABLED=true.",
    )
    tip(ibkr_max_acct_risk, "BrokerSetting: max_dollar_risk_per_account\nAggregate open bracket risk cap (USD).")

    # Auto risk fraction of buying power
    ibkr_auto_risk_override = QtWidgets.QCheckBox("Override")
    ibkr_auto_risk_override.setChecked(_override_flag("IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER"))
    ibkr_auto_risk = QtWidgets.QDoubleSpinBox()
    ibkr_auto_risk.setDecimals(4)
    ibkr_auto_risk.setRange(0.0, 1.0)
    ibkr_auto_risk.setSingleStep(0.01)
    ibkr_auto_risk.setValue(float(_broker_default("auto_risk_fraction_of_buying_power", 0.001) or 0.0))
    try:
        v = float(
            (self._effective_env_value("IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER")[0] or "").strip() or "nan"
        )
        if v == v:
            ibkr_auto_risk.setValue(max(0.0, min(1.0, v)))
    except Exception:
        pass
    ibkr_auto_risk.setEnabled(ibkr_auto_risk_override.isChecked())
    ibkr_auto_risk_override.toggled.connect(ibkr_auto_risk.setEnabled)
    ibkr_auto_risk_row = _override_row(ibkr_auto_risk_override, ibkr_auto_risk)
    tip(
        ibkr_auto_risk_override,
        "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER\nOptional env override for broker_ibkr.yaml:auto_risk_fraction_of_buying_power.\n"
        "If set and accountSummary is available, this can override per-symbol dollar risk.",
    )
    tip(ibkr_auto_risk, "BrokerSetting: auto_risk_fraction_of_buying_power\nFraction of buying power to use for per-symbol risk.")

    ccxt_exchange = QtWidgets.QLineEdit(self._effective_env_value("CCXT_EXCHANGE")[0])
    ccxt_default_type = QtWidgets.QComboBox()
    ccxt_default_type.addItems(["", "spot", "swap", "future", "margin"])
    ccxt_default_type.setCurrentText(self._effective_env_value("CCXT_DEFAULT_TYPE")[0].strip())
    ccxt_rate_limit = bool_chk("CCXT_ENABLE_RATE_LIMIT", "Enable rate limit")
    ccxt_sandbox = bool_chk("CCXT_SANDBOX", "Sandbox mode")
    ccxt_symbol_map = QtWidgets.QPlainTextEdit()
    ccxt_symbol_map.setPlaceholderText("SYMBOL=ccxt/SYMBOL, ... (or JSON); optional")
    ccxt_symbol_map.setMaximumHeight(90)
    ccxt_symbol_map.setPlainText(self._effective_env_value("CCXT_SYMBOL_MAP")[0].strip())
    ccxt_api_key = QtWidgets.QLineEdit(self._effective_env_value("CCXT_API_KEY")[0])
    ccxt_api_key.setEchoMode(QtWidgets.QLineEdit.Password)
    ccxt_secret = QtWidgets.QLineEdit(self._effective_env_value("CCXT_SECRET")[0])
    ccxt_secret.setEchoMode(QtWidgets.QLineEdit.Password)
    ccxt_password = QtWidgets.QLineEdit(self._effective_env_value("CCXT_PASSWORD")[0])
    ccxt_password.setEchoMode(QtWidgets.QLineEdit.Password)
    tip(ccxt_exchange, "CCXT_EXCHANGE\nExchange id (e.g. coinbase, binance). Required when using CCXT broker.")
    tip(ccxt_default_type, "CCXT_DEFAULT_TYPE\nOptional default market type (spot/swap/future/etc).")
    tip(ccxt_rate_limit, "CCXT_ENABLE_RATE_LIMIT\nEnable CCXT rate limiting.")
    tip(ccxt_sandbox, "CCXT_SANDBOX\nUse sandbox/testnet mode (if supported by the exchange).")
    tip(ccxt_symbol_map, "CCXT_SYMBOL_MAP\nOptional symbol mapping for CCXT (when your symbols differ).")
    tip(ccxt_api_key, "CCXT_API_KEY\nAPI key for CCXT exchange.\nIMPORTANT: For Coinbase, use ECDSA keys! (Ed25519 may cause permission errors with Futures).")
    tip(ccxt_secret, "CCXT_SECRET\nAPI secret for CCXT exchange.\nIMPORTANT: For Coinbase, use ECDSA keys! (Ed25519 may cause permission errors with Futures).")
    tip(ccxt_password, "CCXT_PASSWORD\nOptional password for CCXT exchange. Stored as env var; masked here.")

    capital_auto_chk = QtWidgets.QCheckBox("Auto-adjust daily")

    def browse_log() -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            dlg,
            "Select log file",
            log_edit.text() or str(settings.log_file),
            "Log files (*.log);;All files (*)",
        )
        if path:
            log_edit.setText(path)
            refresh_preview()

    log_browse.clicked.connect(browse_log)

    def refresh_preview() -> None:
        mode = mode_combo.currentText().strip()
        profile = profile_combo.currentText().strip()
        session = session_edit.text().strip() or "tradebot"
        log_path = log_edit.text().strip() or str(settings.log_file)
        args: list[str] = ["./scripts/tradebot.sh", "--restart", "-p", profile, "-m", mode, "-x"]
        args.append("true" if execute_chk.isChecked() else "false")
        if mode == "iterations":
            args.extend(["-i", str(iterations_spin.value())])
        sabb = sabbath_combo.currentIndex()
        if sabb == 1:
            args.append("--sabbath")
        elif sabb == 2:
            args.append("--no-sabbath")
        args.extend(["-n", session, "-l", log_path])
        comm_mode = commentary_combo.currentIndex()
        if comm_mode == 1:
            args.extend(["-c", "off"])
        elif comm_mode == 2:
            args.extend(["-c", "internal"])
        args.extend(["-t", str(commentary_min_spin.value())])
        cmd_preview.setText(" ".join(args))
        iterations_spin.setEnabled(mode == "iterations")

    for w in (
        app_env,
        profile_combo,
        mode_combo,
        iterations_spin,
        execute_chk,
        sabbath_combo,
        sabbath_enabled_combo,
        sabbath_astro_chk,
        sabbath_city,
        sabbath_tz,
        sabbath_start,
        sabbath_end,
        sabbath_lat,
        sabbath_lon,
        log_level_combo,
        session_edit,
        log_edit,
        commentary_combo,
        commentary_min_spin,
        commentary_max_calls,
        commentary_budget_path,
        market_data_mode,
        broker_mode,
        alt_md,
        alt_broker,
        ibkr_zerohash_tif,
        default_symbol,
        default_tf,
        max_candles,
        symbols_edit,
        cancel_orders,
        flatten_exit,
        intraday_flatten,
        allow_inherit,
        multi_positions,
        max_concurrent,
        startup_crypto_policy,
        scale_out,
        min_pos_scale,
        emergency_stop,
        max_adds,
        synth_stop_store,
        pos_hold_store,
        htf_combo,
        ltf_combo,
        trend_window_spin,
        trend_swing_spin,
        trend_min_swings_spin,
        trend_strength_spin,
        structure_score_spin,
        session_gate_combo,
        session_min_candles_spin,
        session_range_mult_spin,
        session_volume_mult_spin,
        session_overlap_start_spin,
        session_overlap_end_spin,
        pdt_guard_combo,
        max_roundtrips_spin,
        flip_enabled_combo,
        flip_cooldown_spin,
        cooldown_enabled_combo,
        cooldown_block_spin,
        cooldown_success_spin,
        cooldown_scope_combo,
        stick_to_active_combo,
        aggressive_mode_combo,
        aggressive_risk_spin,
        max_daily_loss_spin,
        max_exposure_spin,
        max_losses_spin,
        ibkr_host,
        ibkr_port,
        ibkr_crypto,
        ibkr_client_id,
        ibkr_account_id,
        ibkr_default_ccy,
        ibkr_paper,
        ibkr_read_only,
        ibkr_max_shares_override,
        ibkr_max_shares,
        ibkr_max_sym_risk_override,
        ibkr_max_sym_risk,
        ibkr_max_acct_risk_override,
        ibkr_max_acct_risk,
        ibkr_auto_risk_override,
        ibkr_auto_risk,
        capital_auto_chk,
        ccxt_exchange,
        ccxt_default_type,
        ccxt_rate_limit,
        ccxt_sandbox,
        icc_auto_entry_enabled_combo,
        icc_auto_entry_cooldown_spin,
        icc_auto_entry_min_htf_strength_spin,
        icc_auto_entry_require_sweep_combo,
    ):
        if isinstance(w, QtWidgets.QComboBox):
            w.currentTextChanged.connect(refresh_preview)
        elif isinstance(w, QtWidgets.QAbstractButton):
            w.toggled.connect(refresh_preview)
        elif isinstance(w, QtWidgets.QSpinBox):
            w.valueChanged.connect(refresh_preview)
        elif isinstance(w, QtWidgets.QLineEdit):
            w.textChanged.connect(refresh_preview)
        elif isinstance(w, QtWidgets.QPlainTextEdit):
            w.textChanged.connect(refresh_preview)

    def desired_typed_env() -> dict[str, str]:
        out: dict[str, str] = {}
        if app_env.text().strip():
            out["APP_ENVIRONMENT"] = app_env.text().strip()
        out["PROFILE_NAME"] = profile_combo.currentText().strip()
        out["BOT_MODE"] = mode_combo.currentText().strip()
        out["BOT_ITERATIONS"] = str(iterations_spin.value())
        out["EXECUTE_TRADES"] = "true" if execute_chk.isChecked() else "false"
        out["LOG_LEVEL"] = log_level_combo.currentText().strip().upper() or "INFO"
        out["SESSION_NAME"] = session_edit.text().strip() or "tradebot"
        out["TRADEBOT_LOG"] = log_edit.text().strip() or str(settings.log_file)

        sabb = sabbath_combo.currentIndex()
        out["BOT_SABBATH"] = "" if sabb == 0 else ("on" if sabb == 1 else "off")
        sabb_profile = sabbath_enabled_combo.currentIndex()
        out["SABBATH_ENABLED"] = "" if sabb_profile == 0 else ("true" if sabb_profile == 1 else "false")
        out["SABBATH_ASTRONOMICAL"] = "true" if sabbath_astro_chk.isChecked() else "false"
        if sabbath_city.text().strip():
            out["SABBATH_CITY"] = sabbath_city.text().strip()
        if sabbath_tz.text().strip():
            tz_value = sabbath_tz.text().strip()
            out["SABBATH_TIMEZONE"] = tz_value
            out["COMMENTARY_LLM_TZ"] = tz_value
            out["PROFILE_SESSION_OVERLAP_TIMEZONE"] = tz_value
        if sabbath_start.text().strip():
            out["SABBATH_START_LOCAL"] = sabbath_start.text().strip()
        if sabbath_end.text().strip():
            out["SABBATH_END_LOCAL"] = sabbath_end.text().strip()
        if sabbath_lat.text().strip():
            out["SABBATH_LAT"] = sabbath_lat.text().strip()
        if sabbath_lon.text().strip():
            out["SABBATH_LON"] = sabbath_lon.text().strip()

        out["MARKET_DATA_MODE"] = str(market_data_mode.currentData() or "primary").strip()
        out["BROKER_MODE"] = str(broker_mode.currentData() or "primary").strip()
        out["ALTERNATIVE_MARKET_DATA"] = str(alt_md.currentData() or alt_md.currentText()).strip()
        out["ALTERNATIVE_BROKER"] = str(alt_broker.currentData() or alt_broker.currentText()).strip()
        if default_symbol.text().strip():
            out["MARKET_DEFAULT_SYMBOL"] = default_symbol.text().strip()
        out["MARKET_DEFAULT_TIMEFRAME"] = default_tf.currentText().strip()
        out["MARKET_MAX_CANDLES"] = str(max_candles.value())
        out["MARKET_SYMBOLS"] = symbols_edit.toPlainText().strip()

        out["CANCEL_ORDERS_ON_START"] = "true" if cancel_orders.isChecked() else "false"
        out["FLATTEN_ON_EXIT"] = "true" if flatten_exit.isChecked() else "false"
        out["INTRADAY_FLATTEN"] = "true" if intraday_flatten.isChecked() else "false"
        out["ALLOW_INHERITED_POSITION"] = "true" if allow_inherit.isChecked() else "false"
        out["MULTI_POSITION_ENABLED"] = "true" if multi_positions.isChecked() else "false"
        out["MAX_CONCURRENT_POSITIONS"] = str(max_concurrent.value())
        out["STARTUP_CRYPTO_UNPROTECTED_POLICY"] = str(startup_crypto_policy.currentData() or "").strip()
        out["SCALE_OUT_FRACTION"] = f"{scale_out.value():.4f}".rstrip("0").rstrip(".")
        out["MIN_POSITION_SIZE_TO_SCALE"] = f"{min_pos_scale.value():.6f}".rstrip("0").rstrip(".")
        out["EMERGENCY_STOP_PCT"] = f"{emergency_stop.value():.4f}".rstrip("0").rstrip(".")
        out["MAX_SCALE_INS_PER_LEG"] = str(max_adds.value())
        if synth_stop_store.text().strip():
            out["SYNTH_STOP_STORE_PATH"] = synth_stop_store.text().strip()
        if pos_hold_store.text().strip():
            out["POSITION_HOLD_STORE_PATH"] = pos_hold_store.text().strip()
        out["ALLOW_DAY_TRADES"] = "true" if allow_day_trades.isChecked() else "false"
        out["MIN_HOLD_SECONDS"] = str(min_hold_seconds.value())

        out["FRICTION_FAIL_SAFE"] = "true" if friction_fs.isChecked() else "false"
        out["FRICTION_RISK_CAP"] = f"{friction_cap.value():.4f}".rstrip("0").rstrip(".")
        out["VIX_FAIL_SAFE"] = "true" if vix_fs.isChecked() else "false"
        out["VIX_RISK_CAP"] = f"{vix_cap.value():.4f}".rstrip("0").rstrip(".")
        out[AUTO_TUNE_ENABLED_ENV] = "true" if capital_auto_chk.isChecked() else "false"

        out["CONFLUENCE_EXTERNAL"] = "true" if confluence_external.isChecked() else "false"
        out["COMMITMENT_MODE"] = "true" if commitment_mode.isChecked() else "false"
        out["BUG_BYPASS_SCHEDULE"] = "true" if bypass_schedule.isChecked() else ""
        out["AUTO_RESTART_ON_ERROR"] = "true" if auto_restart_chk.isChecked() else "false"
        out["AUTO_RESTART_STALE_SECONDS"] = str(auto_restart_stale_spin.value())
        out["AUTO_RESTART_MIN_UPTIME_SECONDS"] = str(auto_restart_min_uptime_spin.value())
        out["AUTO_RESTART_COOLDOWN_SECONDS"] = str(auto_restart_cooldown_spin.value())
        out["PROFILE_HTF_TIMEFRAME"] = str(htf_combo.currentData() or "").strip()
        out["PROFILE_LTF_TIMEFRAME"] = str(ltf_combo.currentData() or "").strip()
        out["PROFILE_TREND_WINDOW"] = "" if trend_window_spin.value() < 0 else str(trend_window_spin.value())
        out["PROFILE_TREND_SWING_LOOKBACK"] = "" if trend_swing_spin.value() < 0 else str(trend_swing_spin.value())
        out["PROFILE_TREND_MIN_SWINGS"] = "" if trend_min_swings_spin.value() < 0 else str(trend_min_swings_spin.value())
        out["PROFILE_TREND_STRENGTH_FLOOR"] = (
            "" if trend_strength_spin.value() < 0 else f"{trend_strength_spin.value():.3f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_STRUCTURE_SCORE_THRESHOLD"] = (
            "" if structure_score_spin.value() < 0 else f"{structure_score_spin.value():.3f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_SESSION_GATE_ENABLED"] = str(session_gate_combo.currentData() or "").strip()
        out["PROFILE_SESSION_GATE_MIN_CANDLES"] = (
            "" if session_min_candles_spin.value() < 0 else str(session_min_candles_spin.value())
        )
        out["PROFILE_SESSION_RANGE_MULTIPLIER"] = (
            "" if session_range_mult_spin.value() < 0 else f"{session_range_mult_spin.value():.2f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_SESSION_VOLUME_MULTIPLIER"] = (
            "" if session_volume_mult_spin.value() < 0 else f"{session_volume_mult_spin.value():.2f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_SESSION_OVERLAP_START_HOUR"] = (
            "" if session_overlap_start_spin.value() < 0 else str(session_overlap_start_spin.value())
        )
        out["PROFILE_SESSION_OVERLAP_END_HOUR"] = (
            "" if session_overlap_end_spin.value() < 0 else str(session_overlap_end_spin.value())
        )
        out["PROFILE_PDT_GUARD_ENABLED"] = str(pdt_guard_combo.currentData() or "").strip()
        out["PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY"] = (
            "" if max_roundtrips_spin.value() < 0 else str(max_roundtrips_spin.value())
        )
        out["PROFILE_FLIP_ACTIONS_ENABLED"] = str(flip_enabled_combo.currentData() or "").strip()
        out["PROFILE_FLIP_COOLDOWN_SECONDS"] = (
            "" if flip_cooldown_spin.value() < 0 else str(flip_cooldown_spin.value())
        )
        out["PROFILE_COOLDOWN_ENABLED"] = str(cooldown_enabled_combo.currentData() or "").strip()
        out["PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK"] = (
            "" if cooldown_block_spin.value() < 0 else str(cooldown_block_spin.value())
        )
        out["PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS"] = (
            "" if cooldown_success_spin.value() < 0 else str(cooldown_success_spin.value())
        )
        out["PROFILE_COOLDOWN_SCOPE"] = str(cooldown_scope_combo.currentData() or "").strip()
        out["PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL"] = str(stick_to_active_combo.currentData() or "").strip()
        out["PROFILE_MAX_PYRAMID_ENTRIES"] = (
            "" if max_pyramid_entries_spin.value() < 0 else str(max_pyramid_entries_spin.value())
        )
        out["PROFILE_PYRAMID_SCORE_THRESHOLD"] = (
            "" if pyramid_score_threshold_spin.value() < 0 else f"{pyramid_score_threshold_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_HTF_NEUTRAL_EXIT_BARS"] = (
            "" if htf_neutral_exit_bars_spin.value() < 0 else str(htf_neutral_exit_bars_spin.value())
        )
        out["PROFILE_ICC_AUTO_ENTRY_ENABLED"] = str(icc_auto_entry_enabled_combo.currentData() or "").strip()
        out["PROFILE_ICC_AUTO_ENTRY_COOLDOWN_MINUTES"] = (
            "" if icc_auto_entry_cooldown_spin.value() < 0 else str(icc_auto_entry_cooldown_spin.value())
        )
        out["PROFILE_ICC_AUTO_ENTRY_MIN_HTF_STRENGTH"] = (
            "" if icc_auto_entry_min_htf_strength_spin.value() < 0 else f"{icc_auto_entry_min_htf_strength_spin.value():.2f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_AUTO_ENTRY_REQUIRE_SWEEP"] = str(icc_auto_entry_require_sweep_combo.currentData() or "").strip()
        out["PROFILE_ICC_ENTRY_SCORE_THRESHOLD"] = (
            "" if icc_entry_score_threshold_spin.value() < 0 else f"{icc_entry_score_threshold_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_SCORE_HTF_LTF_ALIGN_POINTS"] = (
            "" if icc_score_htf_ltf_align_points_spin.value() < 0 else f"{icc_score_htf_ltf_align_points_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_SCORE_SWEEP_POINTS"] = (
            "" if icc_score_sweep_points_spin.value() < 0 else f"{icc_score_sweep_points_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_SCORE_CONTINUATION_POINTS"] = (
            "" if icc_score_continuation_points_spin.value() < 0 else f"{icc_score_continuation_points_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_SCORE_STRONG_HTF_POINTS"] = (
            "" if icc_score_strong_htf_points_spin.value() < 0 else f"{icc_score_strong_htf_points_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_SCORE_PHASE_POINTS"] = (
            "" if icc_score_phase_points_spin.value() < 0 else f"{icc_score_phase_points_spin.value():.1f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_SCORE_HTF_STRENGTH_THRESHOLD"] = (
            "" if icc_score_htf_strength_threshold_spin.value() < 0 else f"{icc_score_htf_strength_threshold_spin.value():.2f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_ICC_AGGRESSIVE_MODE"] = str(aggressive_mode_combo.currentData() or "").strip()
        out["PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT"] = (
            "" if aggressive_risk_spin.value() < 0 else f"{aggressive_risk_spin.value():.3f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_MAX_DAILY_LOSS_PCT"] = (
            "" if max_daily_loss_spin.value() < 0 else f"{max_daily_loss_spin.value():.3f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_MAX_EXPOSURE_PCT"] = (
            "" if max_exposure_spin.value() < 0 else f"{max_exposure_spin.value():.3f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_BALANCE_CAP_PCT"] = (
             "" if balance_cap_spin.value() < 0 else f"{balance_cap_spin.value():.2f}".rstrip("0").rstrip(".")
        )
        out["PROFILE_MAX_CONSECUTIVE_LOSSES"] = (
            "" if max_losses_spin.value() < 0 else str(max_losses_spin.value())
        )

        comm_mode = commentary_combo.currentIndex()
        out["COMMENTARY_LLM"] = "" if comm_mode == 0 else ("off" if comm_mode == 1 else "internal")
        pol_idx = commentary_policy_combo.currentIndex()
        out["COMMENTARY_LLM_POLICY"] = "a_plus_or_4x" if pol_idx == 0 else ("a_plus_only" if pol_idx == 1 else "interval")
        if commentary_slots.text().strip():
            out["COMMENTARY_LLM_DAILY_SLOTS"] = commentary_slots.text().strip()
        out["COMMENTARY_LLM_MIN_SECONDS"] = str(commentary_min_spin.value())
        out["COMMENTARY_LLM_MAX_CALLS_PER_DAY"] = str(commentary_max_calls.value())
        if commentary_budget_path.text().strip():
            out["COMMENTARY_LLM_BUDGET_PATH"] = commentary_budget_path.text().strip()

        if ai_base.text().strip():
            out["TRADE_SCI_API_BASE_URL"] = ai_base.text().strip()
        if ai_key.text().strip():
            out["TRADE_SCI_API_KEY"] = ai_key.text().strip()
        if chatgpt_key.text().strip():
            out["CHATGPT_KEY"] = chatgpt_key.text().strip()
        out["TRADE_SCI_PROVIDER"] = str(provider_combo.currentData() or "").strip()
        if ai_model.text().strip():
            out["TRADE_SCI_MODEL_NAME"] = ai_model.text().strip()
        out["TRADE_SCI_TEMPERATURE"] = f"{ai_temp.value():.3f}".rstrip("0").rstrip(".")
        out["TRADE_SCI_MAX_TOKENS"] = str(ai_tokens.value())

        out["IBKR_HOST"] = ibkr_host.text().strip()
        out["IBKR_PORT"] = str(ibkr_port.value())
        out["IBKR_CRYPTO_EXCHANGE"] = ibkr_crypto.text().strip() or "ZEROHASH"
        out["IBKR_ZEROHASH_CRYPTO_TIF"] = str(ibkr_zerohash_tif.currentData() or "").strip()
        if ibkr_client_id.text().strip():
            out["IBKR_CLIENT_ID"] = ibkr_client_id.text().strip()
        if ibkr_account_id.text().strip():
            out["IBKR_ACCOUNT_ID"] = ibkr_account_id.text().strip()
        out["IBKR_PAPER"] = "true" if ibkr_paper.isChecked() else "false"
        out["IBKR_READ_ONLY"] = "true" if ibkr_read_only.isChecked() else "false"
        if ibkr_default_ccy.text().strip():
            out["IBKR_DEFAULT_CCY"] = ibkr_default_ccy.text().strip()
        out["IBKR_MAX_SHARES_PER_SYMBOL"] = (
            str(ibkr_max_shares.value()) if ibkr_max_shares_override.isChecked() else ""
        )
        out["IBKR_MAX_DOLLAR_RISK_PER_SYMBOL"] = (
            f"{ibkr_max_sym_risk.value():.2f}".rstrip("0").rstrip(".") if ibkr_max_sym_risk_override.isChecked() else ""
        )
        out["IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT"] = (
            f"{ibkr_max_acct_risk.value():.2f}".rstrip("0").rstrip(".") if ibkr_max_acct_risk_override.isChecked() else ""
        )
        out["IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER"] = (
            f"{ibkr_auto_risk.value():.4f}".rstrip("0").rstrip(".") if ibkr_auto_risk_override.isChecked() else ""
        )

        if ccxt_exchange.text().strip():
            out["CCXT_EXCHANGE"] = ccxt_exchange.text().strip()
        if ccxt_default_type.currentText().strip():
            out["CCXT_DEFAULT_TYPE"] = ccxt_default_type.currentText().strip()
        out["CCXT_ENABLE_RATE_LIMIT"] = "true" if ccxt_rate_limit.isChecked() else "false"
        out["CCXT_SANDBOX"] = "true" if ccxt_sandbox.isChecked() else "false"
        if ccxt_symbol_map.toPlainText().strip():
            out["CCXT_SYMBOL_MAP"] = ccxt_symbol_map.toPlainText().strip()
        if ccxt_api_key.text().strip():
            out["CCXT_API_KEY"] = ccxt_api_key.text().strip()
        if ccxt_secret.text().strip():
            out["CCXT_SECRET"] = ccxt_secret.text().strip()
        if ccxt_password.text().strip():
            out["CCXT_PASSWORD"] = ccxt_password.text().strip()
        return out

    # --- Build tab widgets ---
    bot_inner = QtWidgets.QWidget(dlg)
    bot_layout = QtWidgets.QVBoxLayout(bot_inner)
    bot_layout.addWidget(info)
    bot_form = QtWidgets.QFormLayout()
    bot_form.setLabelAlignment(QtCore.Qt.AlignRight)
    bot_form.addRow("Environment", app_env)
    bot_form.addRow("Profile", profile_combo)
    bot_form.addRow("Mode", mode_combo)
    bot_form.addRow("Iterations", iterations_spin)
    bot_form.addRow("LIVE trading", execute_chk)
    bot_form.addRow("Sabbath", sabbath_combo)
    bot_form.addRow("Log level", log_level_combo)
    bot_form.addRow("tmux session", session_edit)
    bot_form.addRow("Log file", log_row_w)
    bot_form.addRow("tmux restart cmd", cmd_preview)
    bot_layout.addLayout(bot_form)
    sabbath_group = QtWidgets.QGroupBox("Sabbath schedule")
    sabbath_form = QtWidgets.QFormLayout()
    sabbath_form.setLabelAlignment(QtCore.Qt.AlignRight)
    sabbath_form.addRow("Profile enable", sabbath_enabled_combo)
    sabbath_form.addRow("Start (Fri)", sabbath_start)
    sabbath_form.addRow("End (Sat)", sabbath_end)
    sabbath_group.setLayout(sabbath_form)
    bot_layout.addWidget(sabbath_group)
    gui_group = QtWidgets.QGroupBox("GUI")
    gui_v = QtWidgets.QVBoxLayout()
    gui_v.addWidget(autostart_bot_chk)
    gui_v.addWidget(keep_bot_chk)
    gui_group.setLayout(gui_v)
    bot_layout.addWidget(gui_group)
    auto_restart_group = QtWidgets.QGroupBox("Auto-Restart on Error")
    auto_restart_form = QtWidgets.QFormLayout()
    auto_restart_form.setLabelAlignment(QtCore.Qt.AlignRight)
    auto_restart_form.addRow("", auto_restart_chk)
    auto_restart_form.addRow("Stale data threshold", auto_restart_stale_spin)
    auto_restart_form.addRow("Min uptime before restart", auto_restart_min_uptime_spin)
    auto_restart_form.addRow("Cooldown between restarts", auto_restart_cooldown_spin)
    auto_restart_group.setLayout(auto_restart_form)
    bot_layout.addWidget(auto_restart_group)
    debug_group = QtWidgets.QGroupBox("Debug")
    debug_v = QtWidgets.QVBoxLayout()
    debug_v.addWidget(bypass_schedule)
    debug_group.setLayout(debug_v)
    bot_layout.addWidget(debug_group)
    bot_layout.addStretch(1)

    time_inner = QtWidgets.QWidget(dlg)
    time_layout = QtWidgets.QVBoxLayout(time_inner)
    time_group = QtWidgets.QGroupBox("Timezone & Astral (shared)")
    time_form = QtWidgets.QFormLayout()
    time_form.setLabelAlignment(QtCore.Qt.AlignRight)
    time_form.addRow("", sabbath_astro_chk)
    time_form.addRow("City", city_row_w)
    time_form.addRow("Primary timezone", tz_row_w)
    time_form.addRow("Latitude", sabbath_lat)
    time_form.addRow("Longitude", sabbath_lon)
    time_group.setLayout(time_form)
    time_layout.addWidget(time_group)
    time_layout.addStretch(1)

    market_inner = QtWidgets.QWidget(dlg)
    market_layout = QtWidgets.QVBoxLayout(market_inner)
    market_group = QtWidgets.QGroupBox("Market / Providers")
    market_form = QtWidgets.QFormLayout()
    market_form.setLabelAlignment(QtCore.Qt.AlignRight)
    market_form.addRow("Market Data Mode", market_data_mode)
    market_form.addRow("Execution Mode", broker_mode)
    market_form.addRow("Market Data", alt_md)
    market_form.addRow("Broker", alt_broker)
    market_form.addRow("Default symbol", default_symbol)
    market_form.addRow("Default timeframe", default_tf)
    market_form.addRow("Candle size (chart)", candle_size)
    market_form.addRow("Max candles", max_candles)
    market_form.addRow("Symbols override", symbols_edit)
    market_group.setLayout(market_form)
    market_layout.addWidget(market_group)
    market_layout.addStretch(1)

    runtime_inner = QtWidgets.QWidget(dlg)
    runtime_layout = QtWidgets.QVBoxLayout(runtime_inner)
    runtime_group = QtWidgets.QGroupBox("Runtime Safeguards")
    runtime_form = QtWidgets.QFormLayout()
    runtime_form.setLabelAlignment(QtCore.Qt.AlignRight)
    runtime_form.addRow(cancel_orders)
    runtime_form.addRow(flatten_exit)
    runtime_form.addRow(intraday_flatten)
    runtime_form.addRow(allow_inherit)
    runtime_form.addRow(multi_positions)
    runtime_form.addRow("Max concurrent positions", max_concurrent)
    runtime_form.addRow("Missing-stop policy (ZEROHASH crypto)", startup_crypto_policy)
    runtime_form.addRow("Scale out fraction", scale_out)
    runtime_form.addRow("Min position size to scale", min_pos_scale)
    runtime_form.addRow("Emergency stop pct", emergency_stop)
    runtime_form.addRow("Max scale-ins/leg", max_adds)
    runtime_form.addRow("Synthetic stop store", synth_row_w)
    runtime_form.addRow("Position hold store", pos_row_w)
    runtime_group.setLayout(runtime_form)
    runtime_layout.addWidget(runtime_group)

    # Day Trade Guards
    day_trade_group = QtWidgets.QGroupBox("Day Trade Guards")
    day_trade_form = QtWidgets.QFormLayout()
    day_trade_form.setLabelAlignment(QtCore.Qt.AlignRight)
    day_trade_form.addRow(allow_day_trades)
    day_trade_form.addRow("Min hold duration", min_hold_seconds)
    day_trade_group.setLayout(day_trade_form)
    runtime_layout.addWidget(day_trade_group)

    runtime_layout.addStretch(1)

    risk_inner = QtWidgets.QWidget(dlg)
    risk_layout = QtWidgets.QVBoxLayout(risk_inner)

    capital_group = QtWidgets.QGroupBox("Capital Calibration (ICC)")
    capital_layout = QtWidgets.QVBoxLayout()
    capital_desc = QtWidgets.QLabel(
        "One-time ICC setup that sizes risk to your actual account equity. "
        "Uses AI to recommend safe overrides (risk caps, exposure, auto-risk fraction)."
    )
    capital_desc.setWordWrap(True)
    capital_desc.setStyleSheet("color: " + theme.muted + ";")

    capital_btn_row = QtWidgets.QHBoxLayout()
    capital_run_btn = QtWidgets.QPushButton("ICC First-Time Setup")
    capital_run_btn.setStyleSheet(f"background-color: {theme.accent}; color: {theme.window}; font-weight: bold; padding: 6px;")
    capital_auto_chk.setChecked(
        os.getenv(AUTO_TUNE_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    )
    tip(
        capital_auto_chk,
        f"{AUTO_TUNE_ENABLED_ENV}\nEnable daily auto-calibration using live account equity.",
    )
    capital_btn_row.addWidget(capital_run_btn)
    capital_btn_row.addWidget(capital_auto_chk)
    capital_btn_row.addStretch(1)

    capital_status = QtWidgets.QLabel(_capital_status_text())
    capital_status.setStyleSheet("color: " + theme.muted + ";")

    capital_layout.addWidget(capital_desc)
    capital_layout.addLayout(capital_btn_row)
    capital_layout.addWidget(capital_status)
    capital_group.setLayout(capital_layout)
    risk_layout.addWidget(capital_group)

    risk_group = QtWidgets.QGroupBox("Risk Models (optional)")
    risk_form = QtWidgets.QFormLayout()
    risk_form.setLabelAlignment(QtCore.Qt.AlignRight)
    risk_form.addRow(friction_fs)
    risk_form.addRow("Friction risk cap", friction_cap)
    risk_form.addRow(vix_fs)
    risk_form.addRow("VIX risk cap", vix_cap)
    risk_group.setLayout(risk_form)
    risk_layout.addWidget(risk_group)
    aggressive_group = QtWidgets.QGroupBox("ICC Aggressive Mode (Phase 2, opt-in)")
    aggressive_form = QtWidgets.QFormLayout()
    aggressive_form.setLabelAlignment(QtCore.Qt.AlignRight)
    aggressive_form.addRow("Aggressive mode", aggressive_mode_combo)
    aggressive_form.addRow("Risk/trade %", aggressive_risk_spin)
    aggressive_form.addRow("Max daily loss %", max_daily_loss_spin)
    aggressive_form.addRow("Max exposure %", max_exposure_spin)
    aggressive_form.addRow("Safety Balance Cap %", balance_cap_spin)
    aggressive_form.addRow("Max consecutive losses", max_losses_spin)
    aggressive_group.setLayout(aggressive_form)
    risk_layout.addWidget(aggressive_group)
    risk_layout.addStretch(1)

    class _CapitalTuneWorker(QtCore.QObject):
        done = QtCore.Signal(object, str, float, str)
        error = QtCore.Signal(str)

        def __init__(
            self,
            *,
            settings_obj,
            profile_name: str,
            current: dict[str, str],
            context: dict[str, str],
            log_excerpt: str,
        ) -> None:
            super().__init__()
            self._settings = settings_obj
            self._profile_name = profile_name
            self._current = current
            self._context = context
            self._log_excerpt = log_excerpt

        def run(self) -> None:
            equity, broker = fetch_account_equity(self._settings)
            if equity is None:
                self.error.emit(broker or "Failed to fetch account equity")
                return
            try:
                result = request_capital_tune(
                    self._settings,
                    equity=equity,
                    broker=broker,
                    profile_name=self._profile_name,
                    current=self._current,
                    context=self._context,
                    log_excerpt=self._log_excerpt,
                )
            except Exception as exc:
                self.error.emit(str(exc))
                return
            self.done.emit(result.overrides, result.notes, result.equity, result.broker)

    _capital_thread: QtCore.QThread | None = None
    _capital_worker: _CapitalTuneWorker | None = None

    def _capital_context() -> dict[str, str]:
        def _auto_float(value: float) -> str:
            return "auto" if value < 0 else f"{value:.4f}".rstrip("0").rstrip(".")

        def _auto_int(value: int) -> str:
            return "auto" if value < 0 else str(value)

        return {
            "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT": _auto_float(aggressive_risk_spin.value()),
            "PROFILE_MAX_DAILY_LOSS_PCT": _auto_float(max_daily_loss_spin.value()),
            "PROFILE_MAX_EXPOSURE_PCT": _auto_float(max_exposure_spin.value()),
            "PROFILE_MAX_CONSECUTIVE_LOSSES": _auto_int(max_losses_spin.value()),
            "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL": (
                f"{ibkr_max_sym_risk.value():.2f}" if ibkr_max_sym_risk_override.isChecked() else "auto"
            ),
            "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT": (
                f"{ibkr_max_acct_risk.value():.2f}" if ibkr_max_acct_risk_override.isChecked() else "auto"
            ),
            "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER": (
                f"{ibkr_auto_risk.value():.4f}" if ibkr_auto_risk_override.isChecked() else "auto"
            ),
        }

    def _capital_full_context() -> dict[str, str]:
        merged = dict(initial_effective)
        for key, val in desired_typed_env().items():
            if val.strip() != "":
                merged[key] = val.strip()
        return sanitize_context(merged, redact_keys=secret_keys)

    def _apply_capital_overrides(overrides: dict[str, str]) -> None:
        if "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT" in overrides:
            aggressive_risk_spin.setValue(float(overrides["PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT"]))
        if "PROFILE_MAX_DAILY_LOSS_PCT" in overrides:
            max_daily_loss_spin.setValue(float(overrides["PROFILE_MAX_DAILY_LOSS_PCT"]))
        if "PROFILE_MAX_EXPOSURE_PCT" in overrides:
            max_exposure_spin.setValue(float(overrides["PROFILE_MAX_EXPOSURE_PCT"]))
        if "PROFILE_MAX_CONSECUTIVE_LOSSES" in overrides:
            max_losses_spin.setValue(int(float(overrides["PROFILE_MAX_CONSECUTIVE_LOSSES"])))

        if "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL" in overrides:
            ibkr_max_sym_risk_override.setChecked(True)
            ibkr_max_sym_risk.setValue(float(overrides["IBKR_MAX_DOLLAR_RISK_PER_SYMBOL"]))
        if "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT" in overrides:
            ibkr_max_acct_risk_override.setChecked(True)
            ibkr_max_acct_risk.setValue(float(overrides["IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT"]))
        if "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER" in overrides:
            ibkr_auto_risk_override.setChecked(True)
            ibkr_auto_risk.setValue(float(overrides["IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER"]))

    def _capital_done(overrides: object, notes: str, equity: float, broker: str) -> None:
        nonlocal _capital_thread, _capital_worker
        capital_run_btn.setEnabled(True)
        capital_run_btn.setText("ICC First-Time Setup")
        overrides_dict = dict(overrides or {})
        if not overrides_dict:
            QtWidgets.QMessageBox.information(
                dlg,
                "Capital Calibration",
                "AI did not recommend any changes for this account size.",
            )
            return
        _apply_capital_overrides(overrides_dict)
        apply_changes(show_message=False)

        summary = "\n".join(f"{k}={v}" for k, v in overrides_dict.items())
        dialog = QtWidgets.QDialog(dlg)
        dialog.setWindowTitle("Capital Calibration")
        dialog.setModal(True)
        dialog.resize(640, 420)
        dialog_layout = QtWidgets.QVBoxLayout(dialog)
        dialog_label = QtWidgets.QLabel("AI capital calibration recommendations applied to this session.")
        dialog_label.setWordWrap(True)
        dialog_layout.addWidget(dialog_label)
        dialog_text = QtWidgets.QTextEdit(dialog)
        dialog_text.setReadOnly(True)
        dialog_text.setPlainText(f"{summary}\n\nNotes: {notes or '—'}")
        dialog_layout.addWidget(dialog_text, 1)
        dialog_btns = QtWidgets.QDialogButtonBox(dialog)
        save_btn = dialog_btns.addButton("Save to .env", QtWidgets.QDialogButtonBox.AcceptRole)
        keep_btn = dialog_btns.addButton("Keep session only", QtWidgets.QDialogButtonBox.RejectRole)
        save_btn.clicked.connect(dialog.accept)
        keep_btn.clicked.connect(dialog.reject)
        dialog_layout.addWidget(dialog_btns)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            apply_tune_to_env(
                dotenv_path=dotenv_path,
                overrides=overrides_dict,
                equity=equity,
                broker=broker,
                notes=notes or "",
            )
            capital_status.setText(_capital_status_text())

        if _capital_thread is not None:
            _capital_thread.quit()
            _capital_thread.wait(500)
        _capital_thread = None
        _capital_worker = None

    def _capital_error(msg: str) -> None:
        nonlocal _capital_thread, _capital_worker
        capital_run_btn.setEnabled(True)
        capital_run_btn.setText("ICC First-Time Setup")
        QtWidgets.QMessageBox.warning(dlg, "Capital Calibration", msg)
        if _capital_thread is not None:
            _capital_thread.quit()
            _capital_thread.wait(500)
        _capital_thread = None
        _capital_worker = None

    class _CapitalTuneUi(QtCore.QObject):
        @QtCore.Slot(object, str, float, str)
        def handle_done(self, overrides: object, notes: str, equity: float, broker: str) -> None:
            _capital_done(overrides, notes, equity, broker)

        @QtCore.Slot(str)
        def handle_error(self, msg: str) -> None:
            _capital_error(msg)

    _capital_ui_handler = _CapitalTuneUi()
    _capital_ui_handler.moveToThread(QtCore.QCoreApplication.instance().thread())

    def _capital_run_clicked() -> None:
        nonlocal _capital_thread, _capital_worker
        capital_run_btn.setEnabled(False)
        capital_run_btn.setText("Running…")
        if _capital_thread is not None:
            _capital_thread.quit()
            _capital_thread.wait(250)

        _capital_thread = QtCore.QThread()
        log_path = log_edit.text().strip() or str(settings.log_file)
        _capital_worker = _CapitalTuneWorker(
            settings_obj=settings,
            profile_name=profile_combo.currentText().strip() or settings.app.profile_name,
            current=_capital_context(),
            context=_capital_full_context(),
            log_excerpt=load_log_excerpt(log_path),
        )
        _capital_worker.moveToThread(_capital_thread)
        _capital_thread.started.connect(_capital_worker.run)
        _capital_worker.done.connect(_capital_ui_handler.handle_done, QtCore.Qt.QueuedConnection)
        _capital_worker.error.connect(_capital_ui_handler.handle_error, QtCore.Qt.QueuedConnection)
        _capital_worker.done.connect(_capital_thread.quit)
        _capital_worker.error.connect(_capital_thread.quit)
        _capital_thread.finished.connect(_capital_worker.deleteLater)
        _capital_thread.finished.connect(_capital_thread.deleteLater)
        _capital_thread.start()

    capital_run_btn.clicked.connect(_capital_run_clicked)

    # --- Strategy - Core tab (HTF/LTF structure, trend detection, PDT guard) ---
    strategy_core_inner = QtWidgets.QWidget(dlg)
    strategy_core_layout = QtWidgets.QVBoxLayout(strategy_core_inner)

    # Strategy toggles
    strat_group = QtWidgets.QGroupBox("Strategy Toggles")
    strat_v = QtWidgets.QVBoxLayout()
    strat_v.addWidget(confluence_external)
    strat_v.addWidget(commitment_mode)
    strat_group.setLayout(strat_v)
    strategy_core_layout.addWidget(strat_group)

    # ICC Rules Summary
    icc_summary_group = QtWidgets.QGroupBox("ICC Rules Summary")
    icc_summary_layout = QtWidgets.QVBoxLayout()
    icc_summary = QtWidgets.QLabel(
        "Core ICC gates (doc-aligned):\n"
        "- HTF trend uses HH/HL vs LH/LL (close-based swings), otherwise neutral.\n"
        "- Indication = break of last swing close; no-trade zone between last swing high/low.\n"
        "- Entry requires sweep + HL/LH + BOS + continuation close beyond correction.\n"
        "- Trades follow HTF trend unless a confirmed HTF flip appears.\n"
        "- A+ entries require session expansion (range+volume) when the session gate is enabled.\n"
        "- Targets align to the next HTF swing level; exits require HTF invalidation unless emergency.\n"
        "- Flips are only allowed when explicitly enabled and venue supports shorts."
    )
    icc_summary.setWordWrap(True)
    icc_summary_layout.addWidget(icc_summary)
    icc_summary_group.setLayout(icc_summary_layout)
    strategy_core_layout.addWidget(icc_summary_group)

    # HTF/LTF Structure
    htf_ltf_group = QtWidgets.QGroupBox("HTF/LTF Structure (profile overrides)")
    htf_ltf_form = QtWidgets.QFormLayout()
    htf_ltf_form.setLabelAlignment(QtCore.Qt.AlignRight)
    htf_ltf_form.addRow("HTF timeframe", htf_combo)
    htf_ltf_form.addRow("LTF timeframe", ltf_combo)
    htf_ltf_form.addRow("Trend window", trend_window_spin)
    htf_ltf_form.addRow("Swing lookback", trend_swing_spin)
    htf_ltf_form.addRow("Min swings", trend_min_swings_spin)
    htf_ltf_form.addRow("Strength floor", trend_strength_spin)
    htf_ltf_form.addRow("Structure score threshold", structure_score_spin)
    htf_ltf_group.setLayout(htf_ltf_form)
    strategy_core_layout.addWidget(htf_ltf_group)


    # PDT Guard
    pdt_group = QtWidgets.QGroupBox("PDT Guard (equities day trading limits)")
    pdt_form = QtWidgets.QFormLayout()
    pdt_form.setLabelAlignment(QtCore.Qt.AlignRight)
    pdt_form.addRow("PDT guard", pdt_guard_combo)
    pdt_form.addRow("Max equity roundtrips/day", max_roundtrips_spin)
    pdt_group.setLayout(pdt_form)
    strategy_core_layout.addWidget(pdt_group)

    strategy_core_layout.addStretch(1)

    # --- Strategy - ICC tab (session health, pyramiding, cooldowns, flips) ---
    strategy_icc_inner = QtWidgets.QWidget(dlg)
    strategy_icc_layout = QtWidgets.QVBoxLayout(strategy_icc_inner)

    # Session Bias (A+ Gate)
    session_group = QtWidgets.QGroupBox("ICC Session Bias (A+ gate)")
    session_form = QtWidgets.QFormLayout()
    session_form.setLabelAlignment(QtCore.Qt.AlignRight)
    session_form.addRow("Session gate", session_gate_combo)
    session_form.addRow("Min candles", session_min_candles_spin)
    session_form.addRow("Range multiplier", session_range_mult_spin)
    session_form.addRow("Volume multiplier", session_volume_mult_spin)
    session_form.addRow("Overlap start hour", session_overlap_start_spin)
    session_form.addRow("Overlap end hour", session_overlap_end_spin)
    session_group.setLayout(session_form)
    strategy_icc_layout.addWidget(session_group)

    # Pyramiding
    pyramid_group = QtWidgets.QGroupBox("ICC Pyramiding (adding to winners)")
    pyramid_form = QtWidgets.QFormLayout()
    pyramid_form.setLabelAlignment(QtCore.Qt.AlignRight)
    pyramid_form.addRow("Max pyramid entries (per symbol)", max_pyramid_entries_spin)
    pyramid_form.addRow("Pyramid score threshold", pyramid_score_threshold_spin)
    pyramid_group.setLayout(pyramid_form)
    strategy_icc_layout.addWidget(pyramid_group)

    # Flips & Cooldowns
    flips_group = QtWidgets.QGroupBox("Flip Actions & Cooldowns")
    flips_form = QtWidgets.QFormLayout()
    flips_form.setLabelAlignment(QtCore.Qt.AlignRight)
    flips_form.addRow("Flip actions", flip_enabled_combo)
    flips_form.addRow("Flip cooldown (sec)", flip_cooldown_spin)
    flips_form.addRow("Cooldown enabled", cooldown_enabled_combo)
    flips_form.addRow("Cooldown cycles after block", cooldown_block_spin)
    flips_form.addRow("Cooldown cycles after success", cooldown_success_spin)
    flips_form.addRow("Cooldown scope", cooldown_scope_combo)
    flips_form.addRow("Stick to active symbol", stick_to_active_combo)
    flips_group.setLayout(flips_form)
    strategy_icc_layout.addWidget(flips_group)

    # HTF Neutral Exit
    exit_group = QtWidgets.QGroupBox("HTF Neutral Exit")
    exit_form = QtWidgets.QFormLayout()
    exit_form.setLabelAlignment(QtCore.Qt.AlignRight)
    exit_form.addRow("HTF neutral exit bars", htf_neutral_exit_bars_spin)
    exit_group.setLayout(exit_form)
    strategy_icc_layout.addWidget(exit_group)

    strategy_icc_layout.addStretch(1)

    # --- Strategy - Auto Entry tab (ICC auto-entry settings) ---
    strategy_auto_entry_inner = QtWidgets.QWidget(dlg)
    strategy_auto_entry_layout = QtWidgets.QVBoxLayout(strategy_auto_entry_inner)

    # Auto-Entry Settings
    auto_entry_group = QtWidgets.QGroupBox("ICC Auto-Entry Settings")
    auto_entry_form = QtWidgets.QFormLayout()
    auto_entry_form.setLabelAlignment(QtCore.Qt.AlignRight)
    auto_entry_form.addRow("Auto-entry enabled", icc_auto_entry_enabled_combo)
    auto_entry_form.addRow("Cooldown (minutes)", icc_auto_entry_cooldown_spin)
    auto_entry_form.addRow("Min HTF strength", icc_auto_entry_min_htf_strength_spin)
    auto_entry_form.addRow("Require sweep", icc_auto_entry_require_sweep_combo)
    auto_entry_group.setLayout(auto_entry_form)
    strategy_auto_entry_layout.addWidget(auto_entry_group)

    # Auto-Entry Description
    auto_entry_desc_group = QtWidgets.QGroupBox("About Auto-Entry")
    auto_entry_desc_layout = QtWidgets.QVBoxLayout()
    auto_entry_desc = QtWidgets.QLabel(
        "ICC Auto-Entry allows the bot to enter trades automatically when all ICC entry criteria are met:\n\n"
        "• HTF and LTF trend alignment\n"
        "• Liquidity sweep (if required)\n"
        "• Break of Structure (BOS)\n"
        "• Continuation close beyond correction range\n"
        "• Entry score meets threshold\n"
        "• HTF strength above minimum (if configured)\n\n"
        "When auto-entry is enabled, these trades execute without requiring AI confirmation, "
        "allowing faster execution on high-conviction ICC setups while still respecting cooldowns and risk limits."
    )
    auto_entry_desc.setWordWrap(True)
    auto_entry_desc_layout.addWidget(auto_entry_desc)
    auto_entry_desc_group.setLayout(auto_entry_desc_layout)
    strategy_auto_entry_layout.addWidget(auto_entry_desc_group)

    strategy_auto_entry_layout.addStretch(1)

    # --- Scoring tab (ICC point-based scoring system) ---
    scoring_inner = QtWidgets.QWidget(dlg)
    scoring_layout = QtWidgets.QVBoxLayout(scoring_inner)

    scoring_intro_group = QtWidgets.QGroupBox("ICC Point-Based Scoring System")
    scoring_intro_layout = QtWidgets.QVBoxLayout()
    scoring_intro = QtWidgets.QLabel(
        "ICC uses a point-based scoring system to evaluate entry quality:\n\n"
        "• HTF/LTF Alignment (30 pts): Both timeframes trending same direction\n"
        "• Liquidity Sweep (25 pts): Correction swept liquidity before continuation\n"
        "• Continuation (25 pts): BOS + close beyond correction range\n"
        "• Strong HTF (15 pts): HTF strength above threshold (bonus)\n"
        "• Phase Alignment (5 pts): Favorable market phase/session (bonus)\n\n"
        "Total possible: 100 points\n"
        "Default entry threshold: 55 points (core gates only)\n"
        "Default pyramid threshold: 70 points (requires stronger confirmation)\n\n"
        "Note: AI can override scores below threshold if enabled and provides strong justification."
    )
    scoring_intro.setWordWrap(True)
    scoring_intro_layout.addWidget(scoring_intro)
    scoring_intro_group.setLayout(scoring_intro_layout)
    scoring_layout.addWidget(scoring_intro_group)

    scoring_thresholds_group = QtWidgets.QGroupBox("Score Thresholds")
    scoring_thresholds_form = QtWidgets.QFormLayout()
    scoring_thresholds_form.setLabelAlignment(QtCore.Qt.AlignRight)
    scoring_thresholds_form.addRow("Entry score threshold", icc_entry_score_threshold_spin)
    scoring_thresholds_form.addRow("Pyramid score threshold", pyramid_score_threshold_spin)
    scoring_thresholds_group.setLayout(scoring_thresholds_form)
    scoring_layout.addWidget(scoring_thresholds_group)

    scoring_points_group = QtWidgets.QGroupBox("Point Allocation")
    scoring_points_form = QtWidgets.QFormLayout()
    scoring_points_form.setLabelAlignment(QtCore.Qt.AlignRight)
    scoring_points_form.addRow("HTF/LTF align points", icc_score_htf_ltf_align_points_spin)
    scoring_points_form.addRow("Sweep points", icc_score_sweep_points_spin)
    scoring_points_form.addRow("Continuation points", icc_score_continuation_points_spin)
    scoring_points_form.addRow("Strong HTF points", icc_score_strong_htf_points_spin)
    scoring_points_form.addRow("Phase alignment points", icc_score_phase_points_spin)
    scoring_points_group.setLayout(scoring_points_form)
    scoring_layout.addWidget(scoring_points_group)

    scoring_params_group = QtWidgets.QGroupBox("Scoring Parameters")
    scoring_params_form = QtWidgets.QFormLayout()
    scoring_params_form.setLabelAlignment(QtCore.Qt.AlignRight)
    scoring_params_form.addRow("HTF strength threshold", icc_score_htf_strength_threshold_spin)
    scoring_params_group.setLayout(scoring_params_form)
    scoring_layout.addWidget(scoring_params_group)

    scoring_layout.addStretch(1)

    commentary_inner = QtWidgets.QWidget(dlg)
    comm_layout = QtWidgets.QVBoxLayout(commentary_inner)
    comm_group = QtWidgets.QGroupBox("Commentary")
    comm_form = QtWidgets.QFormLayout()
    comm_form.setLabelAlignment(QtCore.Qt.AlignRight)
    comm_form.addRow("Mode", commentary_combo)
    comm_form.addRow("Policy", commentary_policy_combo)
    comm_form.addRow("Daily slots", commentary_slots)
    comm_form.addRow("Min seconds", commentary_min_spin)
    comm_form.addRow("Max calls/day", commentary_max_calls)
    comm_form.addRow("Budget file", commentary_budget_path)
    comm_group.setLayout(comm_form)
    comm_layout.addWidget(comm_group)
    comm_layout.addStretch(1)

    ai_inner = QtWidgets.QWidget(dlg)
    ai_layout = QtWidgets.QVBoxLayout(ai_inner)
    ai_group = QtWidgets.QGroupBox("AI")
    ai_form = QtWidgets.QFormLayout()
    ai_form.setLabelAlignment(QtCore.Qt.AlignRight)
    ai_form.addRow("Provider", provider_combo)
    ai_form.addRow("API base URL", ai_base)
    ai_form.addRow("API key", ai_key)
    ai_form.addRow("CHATGPT_KEY", chatgpt_key)
    ai_form.addRow("Model name", ai_model)
    ai_form.addRow("Temperature", ai_temp)
    ai_form.addRow("Max tokens", ai_tokens)
    ai_group.setLayout(ai_form)
    ai_layout.addWidget(ai_group)
    ai_layout.addStretch(1)

    ibkr_inner = QtWidgets.QWidget(dlg)
    ibkr_layout = QtWidgets.QVBoxLayout(ibkr_inner)
    ibkr_group = QtWidgets.QGroupBox("IBKR")
    ibkr_form = QtWidgets.QFormLayout()
    ibkr_form.setLabelAlignment(QtCore.Qt.AlignRight)
    ibkr_form.addRow("Host", ibkr_host)
    ibkr_form.addRow("Port", ibkr_port)
    ibkr_form.addRow("Crypto exchange", ibkr_crypto)
    ibkr_form.addRow("ZEROHASH crypto TIF", ibkr_zerohash_tif)
    ibkr_form.addRow("Client ID", ibkr_client_id)
    ibkr_form.addRow("Account ID", ibkr_account_id)
    ibkr_form.addRow("Default CCY", ibkr_default_ccy)
    ibkr_form.addRow("", ibkr_paper)
    ibkr_form.addRow("", ibkr_read_only)
    ibkr_form.addRow("Max shares/symbol", ibkr_max_shares_row)
    ibkr_form.addRow("Max $ risk/symbol", ibkr_max_sym_risk_row)
    ibkr_form.addRow("Max $ risk/account", ibkr_max_acct_risk_row)
    ibkr_form.addRow("Auto risk fraction", ibkr_auto_risk_row)
    ibkr_group.setLayout(ibkr_form)
    ibkr_layout.addWidget(ibkr_group)
    ibkr_layout.addStretch(1)

    ccxt_inner = QtWidgets.QWidget(dlg)
    ccxt_layout = QtWidgets.QVBoxLayout(ccxt_inner)
    ccxt_group = QtWidgets.QGroupBox("CCXT (alternative broker)")
    ccxt_form = QtWidgets.QFormLayout()
    ccxt_form.setLabelAlignment(QtCore.Qt.AlignRight)
    ccxt_form.addRow("Exchange", ccxt_exchange)
    ccxt_form.addRow("Default type", ccxt_default_type)
    ccxt_form.addRow("", ccxt_rate_limit)
    ccxt_form.addRow("", ccxt_sandbox)
    ccxt_form.addRow("Symbol map", ccxt_symbol_map)
    ccxt_form.addRow("API key", ccxt_api_key)
    ccxt_form.addRow("Secret", ccxt_secret)
    ccxt_form.addRow("Password", ccxt_password)
    ccxt_group.setLayout(ccxt_form)
    ccxt_layout.addWidget(ccxt_group)
    ccxt_layout.addStretch(1)

    # --- Advanced tab (raw env) ---
    adv_tab = QtWidgets.QWidget(dlg)
    adv_layout = QtWidgets.QVBoxLayout()
    filter_row = QtWidgets.QHBoxLayout()
    filter_label = QtWidgets.QLabel("Filter:")
    filter_edit = QtWidgets.QLineEdit()
    filter_edit.setPlaceholderText("Filter keys (e.g. IBKR_, CCXT_, TRADE_SCI_, COMMENTARY_, EXECUTE_TRADES)")
    tip(filter_edit, "ENV_FILTER\nType to filter keys (case-insensitive). Example: IBKR_ or TRADE_SCI_.")
    filter_row.addWidget(filter_label)
    filter_row.addWidget(filter_edit, 1)

    table = QtWidgets.QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(["Key", "Value", "Source", "Notes"])
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
    hdr = table.horizontalHeader()
    hdr.setStretchLastSection(False)
    hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
    hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
    hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
    hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
    table.setShowGrid(False)
    tip(
        table,
        "ENV_TABLE_EDIT\n"
        "Double-click a Value cell to edit it.\n"
        "Typed controls in other tabs take precedence.\n"
        "Secret keys are masked and must be set via the typed tabs.",
    )

    secret_keys = {
        "TRADE_SCI_API_KEY",
        "CHATGPT_KEY",
        "CCXT_API_KEY",
        "CCXT_SECRET",
        "CCXT_PASSWORD",
    }

    def build_rows() -> None:
        needle = filter_edit.text().strip().upper()
        table.setRowCount(0)
        keys = discovered_env_keys
        grouped = sorted(keys, key=lambda k: (classify(k), k))
        for k in grouped:
            if needle and needle not in k:
                continue
            val, src = self._effective_env_value(k)
            r = table.rowCount()
            table.insertRow(r)
            it_k = QtWidgets.QTableWidgetItem(k)
            it_k.setFlags(it_k.flags() & ~QtCore.Qt.ItemIsEditable)

            display = "********" if k in secret_keys and val else val
            it_v = QtWidgets.QTableWidgetItem(display)
            if k in secret_keys:
                it_v.setData(QtCore.Qt.UserRole, val)
                it_v.setFlags(it_v.flags() & ~QtCore.Qt.ItemIsEditable)

            it_src = QtWidgets.QTableWidgetItem(src or "unset")
            it_src.setFlags(it_src.flags() & ~QtCore.Qt.ItemIsEditable)
            it_notes = QtWidgets.QTableWidgetItem(classify(k))
            it_notes.setFlags(it_notes.flags() & ~QtCore.Qt.ItemIsEditable)
            if src == "override":
                it_src.setForeground(QtGui.QColor(theme.warn))
            elif src in ("env", ".env"):
                it_src.setForeground(QtGui.QColor(theme.muted))
            table.setItem(r, 0, it_k)
            table.setItem(r, 1, it_v)
            table.setItem(r, 2, it_src)
            table.setItem(r, 3, it_notes)

    build_rows()
    filter_edit.textChanged.connect(build_rows)

    btn_apply = QtWidgets.QPushButton("Apply (GUI)")
    btn_save = QtWidgets.QPushButton("Save to .env")
    btn_restart_tmux = QtWidgets.QPushButton("Restart tmux (apply to running bot)")
    btn_clear = QtWidgets.QPushButton("Clear Overrides")
    btn_reset_defaults = QtWidgets.QPushButton("Reset to Defaults")
    btn_close = QtWidgets.QPushButton("Close")
    btn_close.clicked.connect(dlg.accept)
    tip(
        btn_apply,
        "BTN_APPLY\nApply your changes immediately in this GUI session (updates in-process env overrides).",
    )
    tip(
        btn_save,
        "BTN_SAVE_DOTENV\nWrite current overrides into `.env` so future runs (GUI/tmux) use them by default.",
    )
    tip(
        btn_restart_tmux,
        "BTN_RESTART_TMUX\nApply + Save, then restart the tmux panes so the running dashboard/bot picks up changes.",
    )
    tip(
        btn_clear,
        "BTN_CLEAR_OVERRIDES\nRemove all GUI overrides and fall back to `.env` and/or your shell environment.",
    )
    tip(
        btn_reset_defaults,
        "BTN_RESET_DEFAULTS\nHard Reset: Revert .env to safe 'Feet Wet' defaults (Sim Mode, Intraday Profile).",
    )
    tip(btn_close, "BTN_CLOSE\nClose this settings dialog (no additional changes are applied).")

    def apply_changes(show_message: bool = True) -> None:
        self._set_bot_autostart(autostart_bot_chk.isChecked())
        self._set_bot_keep_running_on_close(keep_bot_chk.isChecked())

        typed = desired_typed_env()
        typed_keys = set(typed.keys())

        for r in range(table.rowCount()):
            key = table.item(r, 0).text()
            if key in typed_keys:
                continue
            item = table.item(r, 1)
            raw = item.data(QtCore.Qt.UserRole) if key in secret_keys else item.text()
            val = str(raw or "").strip()
            if val != initial_effective.get(key, ""):
                set_override(key, val)
            elif key in self._env_overrides:
                set_override(key, "")

        for key, val in typed.items():
            v = val.strip()
            if v != initial_effective.get(key, ""):
                set_override(key, v)
            elif key in self._env_overrides:
                set_override(key, "")

        build_rows()
        self._render_right()
        self._set_candle_tf(str(candle_size.currentData() or candle_size.currentText()).strip() or getattr(settings, 'candle_tf', '5 mins'))

        if show_message:
            QtWidgets.QMessageBox.information(
                dlg,
                "Applied",
                "Settings have been applied to the current GUI session.\n\n"
                "These changes are active now but won't persist after restart.\n"
                "Use 'Save to .env' to make them permanent."
            )
        if hasattr(self, "_safe_restart_bot"):
            self._safe_restart_bot(reason="apply")

    def save_to_dotenv() -> None:
        updates: dict[str, str] = {}
        for k, v in self._env_overrides.items():
            updates[k] = v
        for k, v in desired_typed_env().items():
            if v.strip() != "":
                updates[k] = v.strip()
        if not updates:
            QtWidgets.QMessageBox.information(dlg, "Save to .env", "No overrides set.")
            return
        msg = (
            f"This will write {len(updates)} key(s) into:\n\n{dotenv_path}\n\n"
            "This affects the tmux launcher (it sources .env). Continue?"
        )
        if QtWidgets.QMessageBox.question(dlg, "Confirm .env write", msg) != QtWidgets.QMessageBox.Yes:
            return
        try:
            _merge_dotenv(dotenv_path, updates)
            QtWidgets.QMessageBox.information(dlg, "Saved", f"Wrote updates to:\n{dotenv_path}")
            if hasattr(self, "_safe_restart_bot"):
                self._safe_restart_bot(reason="save")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(dlg, "Save failed", str(exc))

    def clear_overrides() -> None:
        for k in list(self._env_overrides.keys()):
            self._qsettings.remove(f"env/{k}")
            if k in dotenv_values:
                os.environ[k] = dotenv_values[k]
            else:
                os.environ.pop(k, None)
        self._env_overrides = {}
        build_rows()
        self._render_right()

    def restart_tmux() -> None:
        apply_changes()
        save_to_dotenv()
        cmd = cmd_preview.text().strip()
        if not cmd:
            return
        try:
            res = subprocess.run(
                ["bash", "-lc", cmd],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (res.stdout or "") + (("\n" + res.stderr) if res.stderr else "")
            if res.returncode != 0:
                QtWidgets.QMessageBox.critical(dlg, "tmux restart failed", out or f"exit={res.returncode}")
            else:
                QtWidgets.QMessageBox.information(dlg, "tmux restarted", out.strip() or "OK")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(dlg, "tmux restart failed", str(exc))

    def reset_to_defaults() -> None:
        msg = (
            "⚠️ HARD RESET ⚠️\n\n"
            "This will OVERWRITE specific keys in your .env file with the safe 'Feet Wet' defaults:\n"
            "• EXECUTE_TRADES=false (Simulation Mode)\n"
            "• PROFILE_NAME=intraday\n"
            "• MULTI_POSITION_ENABLED=false\n"
            "• IBKR_PORT=7497 (Paper)\n\n"
            "Your API keys and other custom settings will be preserved. Continue?"
        )
        if QtWidgets.QMessageBox.question(dlg, "Confirm Hard Reset", msg) != QtWidgets.QMessageBox.Yes:
            return

        defaults = {
            "EXECUTE_TRADES": "false",
            "PROFILE_NAME": "intraday",
            "MULTI_POSITION_ENABLED": "false",
            "IBKR_PORT": "7497",
            "LOG_LEVEL": "INFO",
        }

        # 1. Clear in-memory overrides
        self._env_overrides = {}

        # 2. Write defaults to .env
        try:
            _merge_dotenv(dotenv_path, defaults)

            # 3. Reload env to reflect changes in UI
            for k, v in defaults.items():
                if k in os.environ:
                    os.environ[k] = v

            build_rows()
            self._render_right()

            QtWidgets.QMessageBox.information(
                dlg,
                "Reset Complete",
                "Settings have been reset to 'Feet Wet' defaults.\n\n"
                "Please restart the bot/dashboard to ensure full effect."
            )

            if hasattr(self, "_safe_restart_bot"):
                self._safe_restart_bot(reason="reset")

        except Exception as exc:
            QtWidgets.QMessageBox.critical(dlg, "Reset Failed", str(exc))

    btn_apply.clicked.connect(lambda *_: apply_changes())
    btn_save.clicked.connect(save_to_dotenv)
    btn_restart_tmux.clicked.connect(restart_tmux)
    btn_clear.clicked.connect(clear_overrides)
    btn_reset_defaults.clicked.connect(reset_to_defaults)

    btns = QtWidgets.QHBoxLayout()
    btns.addWidget(btn_apply)
    btns.addWidget(btn_save)
    btns.addWidget(btn_restart_tmux)
    btns.addWidget(btn_clear)
    btns.addWidget(btn_reset_defaults)
    btns.addStretch(1)
    btns.addWidget(btn_close)

    adv_layout.addLayout(filter_row)
    adv_layout.addWidget(table, 1)
    adv_tab.setLayout(adv_layout)

    # ===================== Benchmark/Simulation Tab =====================
    benchmark_inner = QtWidgets.QWidget(dlg)
    benchmark_layout = QtWidgets.QVBoxLayout()

    # Title and description
    benchmark_title = QtWidgets.QLabel("Historical Simulation / Backtest")
    benchmark_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 8px;")
    benchmark_desc = QtWidgets.QLabel(
        "Validate your ICC strategy against historical data. This simulation replays past market data "
        "through your bot's logic to estimate performance without risking real capital."
    )
    benchmark_desc.setWordWrap(True)
    benchmark_desc.setStyleSheet("color: " + theme.muted + "; margin-bottom: 16px;")

    benchmark_layout.addWidget(benchmark_title)
    benchmark_layout.addWidget(benchmark_desc)

    # Input fields
    form_benchmark = QtWidgets.QFormLayout()
    form_benchmark.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
    form_benchmark.setLabelAlignment(QtCore.Qt.AlignRight)

    # Initial capital
    capital_input = QtWidgets.QDoubleSpinBox()
    capital_input.setRange(100, 10000000)
    capital_input.setValue(10000)
    capital_input.setPrefix("$")
    capital_input.setSingleStep(1000)
    form_benchmark.addRow(QtWidgets.QLabel("Initial Capital:"), capital_input)

    # Date range
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 years ago

    start_date_edit = QtWidgets.QDateEdit()
    start_date_edit.setCalendarPopup(True)
    start_date_edit.setDate(QtCore.QDate(start_date.year, start_date.month, start_date.day))
    form_benchmark.addRow(QtWidgets.QLabel("Start Date:"), start_date_edit)

    end_date_edit = QtWidgets.QDateEdit()
    end_date_edit.setCalendarPopup(True)
    end_date_edit.setDate(QtCore.QDate(end_date.year, end_date.month, end_date.day))
    form_benchmark.addRow(QtWidgets.QLabel("End Date:"), end_date_edit)

    # Symbols to test (multi-select list)
    symbols_label = QtWidgets.QLabel("Symbols to Test:")
    symbols_list = QtWidgets.QListWidget()
    symbols_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
    symbols_list.setMaximumHeight(150)
    available_symbols = settings.market.symbols or ["SPY", "QQQ", "BTCUSD", "ETHUSD"]
    for sym in available_symbols:
        item = QtWidgets.QListWidgetItem(sym)
        symbols_list.addItem(item)
        item.setSelected(True)  # Select all by default
    form_benchmark.addRow(symbols_label, symbols_list)

    benchmark_layout.addLayout(form_benchmark)

    # Run button and progress
    run_benchmark_btn = QtWidgets.QPushButton("Run Backtest")
    run_benchmark_btn.setStyleSheet(f"background-color: {theme.accent}; color: {theme.window}; font-weight: bold; padding: 8px;")

    benchmark_progress = QtWidgets.QProgressBar()
    benchmark_progress.setVisible(False)

    benchmark_layout.addWidget(run_benchmark_btn)
    benchmark_layout.addWidget(benchmark_progress)

    # Results display
    results_label = QtWidgets.QLabel("Results:")
    results_label.setStyleSheet("font-weight: bold; margin-top: 16px;")
    results_text = QtWidgets.QPlainTextEdit()
    results_text.setReadOnly(True)
    results_text.setPlainText("Run a backtest to see performance metrics and weekly P&L.\n\nThis may take several minutes depending on date range and number of symbols.")
    results_text.setMaximumHeight(300)

    benchmark_layout.addWidget(results_label)
    benchmark_layout.addWidget(results_text, 1)

    benchmark_inner.setLayout(benchmark_layout)

    class _BacktestWorker(QtCore.QObject):
        log = QtCore.Signal(str)
        done = QtCore.Signal(str)
        error = QtCore.Signal(str)

        def __init__(self, *, initial_capital: float, start_dt, end_dt, symbols: list[str], settings_obj) -> None:
            super().__init__()
            self._initial_capital = initial_capital
            self._start_dt = start_dt
            self._end_dt = end_dt
            self._symbols = symbols
            self._settings = settings_obj

        def run(self) -> None:
            try:
                from ib_insync import IB
                from tradebot_sci.simulation.backtester import Backtester
                from tradebot_sci.ai.client import TradeSciAIClient

                ib = IB()
                try:
                    host = self._settings.broker.host if self._settings.broker else "127.0.0.1"
                    port = self._settings.broker.port if self._settings.broker else 7497
                    ib.connect(host, port, clientId=998)
                    self.log.emit(f"Connected to IBKR at {host}:{port}")

                    ai_client = TradeSciAIClient(self._settings.ai)
                    backtester = Backtester(ib, self._settings, ai_client)

                    self.log.emit(
                        f"Simulating {len(self._symbols)} symbols from {self._start_dt.date()} to {self._end_dt.date()}..."
                    )
                    self.log.emit("Generating trading signals using ICC strategy...\n")
                    result = backtester.run_backtest(
                        initial_capital=self._initial_capital,
                        start_date=self._start_dt,
                        end_date=self._end_dt,
                        symbols=self._symbols,
                    )

                    output = "=" * 60 + "\n"
                    output += "BACKTEST RESULTS\n"
                    output += "=" * 60 + "\n\n"
                    output += f"Period: {result.start_date.date()} to {result.end_date.date()}\n"
                    output += f"Initial Capital: ${result.initial_capital:,.2f}\n"
                    output += f"Final Capital: ${result.final_capital:,.2f}\n"
                    output += f"Total P&L: ${result.total_pnl:,.2f} ({result.total_return_pct:+.2f}%)\n"
                    output += f"Max Drawdown: {result.max_drawdown_pct:.2f}%\n\n"

                    output += f"Total Trades: {len(result.trades)}\n"
                    output += f"Win Rate: {result.win_rate:.1f}%\n"
                    if result.avg_win > 0:
                        output += f"Avg Win: ${result.avg_win:.2f}\n"
                    if result.avg_loss < 0:
                        output += f"Avg Loss: ${result.avg_loss:.2f}\n"

                    output += "\n" + "=" * 60 + "\n"
                    output += "WEEKLY EQUITY CURVE\n"
                    output += "=" * 60 + "\n\n"

                    sorted_weeks = sorted(result.weekly_equity.items())
                    for week, equity in sorted_weeks:
                        pnl_from_start = equity - result.initial_capital
                        pct_from_start = (pnl_from_start / result.initial_capital) * 100
                        output += f"{week}: ${equity:,.2f} (P&L: ${pnl_from_start:+,.2f}, {pct_from_start:+.2f}%)\n"

                    output += "\n" + "=" * 60 + "\n"
                    output += "TRADE LOG (Recent 20)\n"
                    output += "=" * 60 + "\n\n"

                    for trade in result.trades[-20:]:
                        output += f"{trade.entry_time.date()} {trade.symbol} {trade.direction.upper()}: "
                        output += f"Entry=${trade.entry_price:.2f} Exit=${trade.exit_price:.2f} "
                        output += f"P&L=${trade.pnl:+.2f} ({trade.exit_reason})\n"

                    self.done.emit(output)
                finally:
                    if ib.isConnected():
                        ib.disconnect()
            except Exception as exc:
                import traceback

                self.error.emit(f"Backtest failed:\n\n{exc}\n\n{traceback.format_exc()}")

    _benchmark_thread: QtCore.QThread | None = None
    _benchmark_worker: _BacktestWorker | None = None
    _benchmark_cleanup_bound = False

    # Run backtest function
    def run_backtest_clicked():
        """Execute the historical backtest when user clicks Run."""
        nonlocal _benchmark_thread, _benchmark_worker
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            initial_capital = capital_input.value()
            start = start_date_edit.date()
            end = end_date_edit.date()

            start_dt = datetime(start.year(), start.month(), start.day(), tzinfo=ZoneInfo("UTC"))
            end_dt = datetime(end.year(), end.month(), end.day(), 23, 59, 59, tzinfo=ZoneInfo("UTC"))

            if start_dt >= end_dt:
                QtWidgets.QMessageBox.warning(dlg, "Invalid Date Range", "Start date must be before end date.")
                return

            selected_symbols = [item.text() for item in symbols_list.selectedItems()]
            if not selected_symbols:
                QtWidgets.QMessageBox.warning(dlg, "No Symbols", "Please select at least one symbol to test.")
                return

            run_benchmark_btn.setEnabled(False)
            benchmark_progress.setVisible(True)
            benchmark_progress.setRange(0, 0)
            results_text.setPlainText(
                "Running backtest...\nThis may take several minutes.\n\nFetching historical data from IBKR..."
            )

            if _benchmark_thread is not None:
                _benchmark_thread.quit()
                _benchmark_thread.wait(250)

            _benchmark_thread = QtCore.QThread()  # No parent - will be deleted via deleteLater
            _benchmark_worker = _BacktestWorker(
                initial_capital=initial_capital,
                start_dt=start_dt,
                end_dt=end_dt,
                symbols=selected_symbols,
                settings_obj=settings,
            )  # No parent - lives in different thread
            _benchmark_worker.moveToThread(_benchmark_thread)

            def _append_log(text: str) -> None:
                results_text.appendPlainText(text)

            def _finish_ok(output: str) -> None:
                results_text.setPlainText(output)
                run_benchmark_btn.setEnabled(True)
                benchmark_progress.setVisible(False)

            def _finish_err(msg: str) -> None:
                results_text.setPlainText(msg)
                run_benchmark_btn.setEnabled(True)
                benchmark_progress.setVisible(False)
                QtWidgets.QMessageBox.critical(dlg, "Backtest Error", msg.splitlines()[0])

            _benchmark_worker.log.connect(_append_log)
            _benchmark_worker.done.connect(_finish_ok)
            _benchmark_worker.error.connect(_finish_err)
            _benchmark_thread.started.connect(_benchmark_worker.run)
            _benchmark_worker.done.connect(_benchmark_thread.quit)
            _benchmark_worker.error.connect(_benchmark_thread.quit)
            _benchmark_thread.finished.connect(_benchmark_worker.deleteLater)
            _benchmark_thread.finished.connect(_benchmark_thread.deleteLater)
            _benchmark_thread.start()
        except Exception as e:
            import traceback

            error_msg = f"Backtest failed:\n\n{str(e)}\n\n{traceback.format_exc()}"
            results_text.setPlainText(error_msg)
            QtWidgets.QMessageBox.critical(dlg, "Backtest Error", str(e))
            run_benchmark_btn.setEnabled(True)
            benchmark_progress.setVisible(False)

    run_benchmark_btn.clicked.connect(run_backtest_clicked)

    def _cleanup_benchmark_thread() -> None:
        nonlocal _benchmark_thread, _benchmark_worker
        if _benchmark_thread is not None:
            if _benchmark_thread.isRunning():
                _benchmark_thread.quit()
                _benchmark_thread.wait(3000)
            _benchmark_thread = None
        _benchmark_worker = None

    if not _benchmark_cleanup_bound:
        dlg.finished.connect(_cleanup_benchmark_thread)
        _benchmark_cleanup_bound = True

    # --- Profiles tab (intuitive profile + symbol editor) ---
    profiles_inner = QtWidgets.QWidget(dlg)
    profiles_layout = QtWidgets.QVBoxLayout(profiles_inner)

    profiles_yaml = _load_profiles_yaml()
    profiles_data = profiles_yaml.get("profiles", {}) or {}

    profile_manage_combo = QtWidgets.QComboBox()
    for name in sorted(profiles_data.keys()):
        profile_manage_combo.addItem(name)
    if profile_manage_combo.count() == 0:
        profile_manage_combo.addItem(current_profile or "default")
    if current_profile:
        idx = profile_manage_combo.findText(current_profile)
        if idx >= 0:
            profile_manage_combo.setCurrentIndex(idx)

    profile_manage_row = QtWidgets.QHBoxLayout()
    profile_manage_row.addWidget(QtWidgets.QLabel("Profile"))
    profile_manage_row.addWidget(profile_manage_combo, 1)

    profile_create_btn = QtWidgets.QPushButton("Create profile…")
    profile_save_btn = QtWidgets.QPushButton("Save profile")
    profile_reset_btn = QtWidgets.QPushButton("Reload from disk")
    profile_manage_row.addWidget(profile_create_btn)
    profile_manage_row.addWidget(profile_save_btn)
    profile_manage_row.addWidget(profile_reset_btn)
    profile_manage_row_w = QtWidgets.QWidget(dlg)
    profile_manage_row_w.setLayout(profile_manage_row)

    profile_info = QtWidgets.QLabel(
        "Pick a profile, toggle the symbols you want active, and save. "
        "This updates config/settings_profiles.yaml."
    )
    profile_info.setWordWrap(True)
    profile_info.setStyleSheet("color: " + theme.muted + ";")

    symbols_list = QtWidgets.QListWidget()
    symbols_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
    symbols_list.setMinimumHeight(240)

    recommended_symbols_edit = QtWidgets.QPlainTextEdit()
    recommended_symbols_edit.setReadOnly(True)
    recommended_symbols_edit.setMaximumHeight(70)
    recommended_symbols_edit.setPlaceholderText("AI recommendations will appear here.")

    recommend_symbols_btn = QtWidgets.QPushButton("AI Recommendations")
    recommend_symbols_btn.setStyleSheet(
        f"background-color: {theme.accent}; color: {theme.window}; font-weight: bold; padding: 6px;"
    )
    tip(
        recommend_symbols_btn,
        "Ask the AI to enable only the most volatile ICC-friendly symbols from the available universe.",
    )

    symbol_add_edit = QtWidgets.QLineEdit()
    symbol_add_edit.setPlaceholderText("Add custom symbol (e.g., NVDA, BTCUSD)")
    symbol_add_btn = QtWidgets.QPushButton("Add")

    symbol_add_row = QtWidgets.QHBoxLayout()
    symbol_add_row.addWidget(symbol_add_edit, 1)
    symbol_add_row.addWidget(symbol_add_btn)
    symbol_add_row_w = QtWidgets.QWidget(dlg)
    symbol_add_row_w.setLayout(symbol_add_row)

    symbol_select_all = QtWidgets.QPushButton("Enable all")
    symbol_clear_all = QtWidgets.QPushButton("Disable all")
    symbol_use_defaults = QtWidgets.QPushButton("Use market defaults")

    symbol_controls = QtWidgets.QHBoxLayout()
    symbol_controls.addWidget(symbol_select_all)
    symbol_controls.addWidget(symbol_clear_all)
    symbol_controls.addWidget(symbol_use_defaults)
    symbol_controls.addStretch(1)
    symbol_controls_w = QtWidgets.QWidget(dlg)
    symbol_controls_w.setLayout(symbol_controls)

    profile_symbol_status = QtWidgets.QLabel("")
    profile_symbol_status.setStyleSheet("color: " + theme.muted + ";")

    def _available_symbols() -> list[str]:
        base_symbols = _base_market_symbols()
        combined = list(base_symbols)
        extra_symbols: list[str] = []
        for prof in profiles_data.values():
            for sym in (prof or {}).get("symbols", []) or []:
                extra_symbols.append(str(sym))
        for sym in (getattr(settings.market, "symbols", None) or []):
            extra_symbols.append(str(sym))
        combined.extend(_normalize_symbols(extra_symbols))
        return _normalize_symbols(combined)

    def _profile_record(name: str) -> dict[str, Any]:
        return copy.deepcopy(profiles_data.get(name, {}) or {})

    def _set_symbol_list(symbols: list[str], selected: set[str], using_defaults: bool) -> None:
        symbols_list.clear()
        for sym in symbols:
            item = QtWidgets.QListWidgetItem(sym)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            if using_defaults or sym in selected:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
            symbols_list.addItem(item)
        if using_defaults:
            profile_symbol_status.setText("Using market defaults (no profile override).")
        else:
            profile_symbol_status.setText(f"Active symbols: {len(selected)}/{len(symbols)}")

    def _get_checked_symbols() -> list[str]:
        checked: list[str] = []
        for idx in range(symbols_list.count()):
            item = symbols_list.item(idx)
            if item.checkState() == QtCore.Qt.Checked:
                checked.append(item.text())
        return _normalize_symbols(checked)

    def _refresh_profile_editor() -> None:
        name = profile_manage_combo.currentText().strip()
        record = _profile_record(name)
        symbols = _available_symbols()
        profile_symbols = record.get("symbols")
        using_defaults = profile_symbols is None
        selected = set(_normalize_symbols(profile_symbols or []))
        _set_symbol_list(symbols, selected, using_defaults)

        def _combo_state(combo: QtWidgets.QComboBox, key: str) -> None:
            raw = record.get(key)
            if isinstance(raw, bool):
                combo.setCurrentIndex(1 if raw else 2)
            else:
                combo.setCurrentIndex(0)

        _combo_state(auto_schedule_combo, "auto_schedule_enabled")
        _combo_state(sabbath_enabled_combo_profile, "sabbath_enabled")
        sabbath_tz_profile.setText(str(record.get("sabbath_timezone", "") or ""))
        sabbath_start_profile.setText(str(record.get("sabbath_start_local", "") or ""))
        sabbath_end_profile.setText(str(record.get("sabbath_end_local", "") or ""))

    def _collect_profile_updates() -> tuple[dict[str, Any], set[str]]:
        updates: dict[str, Any] = {}
        removals: set[str] = set()
        auto_schedule_raw = auto_schedule_combo.currentData()
        if auto_schedule_raw == "":
            removals.add("auto_schedule_enabled")
        else:
            updates["auto_schedule_enabled"] = auto_schedule_raw == "true"

        sabbath_raw = sabbath_enabled_combo_profile.currentData()
        if sabbath_raw == "":
            removals.add("sabbath_enabled")
        else:
            updates["sabbath_enabled"] = sabbath_raw == "true"

        for key, widget in (
            ("sabbath_timezone", sabbath_tz_profile),
            ("sabbath_start_local", sabbath_start_profile),
            ("sabbath_end_local", sabbath_end_profile),
        ):
            val = widget.text().strip()
            if val:
                updates[key] = val
            else:
                removals.add(key)
        return updates, removals

    def _save_profile_changes() -> None:
        name = profile_manage_combo.currentText().strip()
        if not name:
            QtWidgets.QMessageBox.warning(dlg, "Profile Save", "Select a profile first.")
            return
        record = _profile_record(name)
        selected = _get_checked_symbols()
        if selected:
            record["symbols"] = selected
        else:
            record.pop("symbols", None)

        updates, removals = _collect_profile_updates()
        record.update(updates)
        for key in removals:
            record.pop(key, None)

        profiles_data[name] = record
        profiles_yaml["profiles"] = profiles_data
        if _save_profiles_yaml(profiles_yaml):
            profile_symbol_status.setText(f"Saved {name} ({len(selected)} symbols).")

    def _reset_profiles_from_disk() -> None:
        nonlocal profiles_yaml, profiles_data
        profiles_yaml = _load_profiles_yaml()
        profiles_data = profiles_yaml.get("profiles", {}) or {}
        profile_manage_combo.blockSignals(True)
        profile_manage_combo.clear()
        for name in sorted(profiles_data.keys()):
            profile_manage_combo.addItem(name)
        profile_manage_combo.blockSignals(False)
        if profile_manage_combo.count() == 0:
            profile_manage_combo.addItem(current_profile or "default")
        _refresh_profile_editor()

    def _create_profile() -> None:
        base_name = profile_manage_combo.currentText().strip()
        new_name, ok = QtWidgets.QInputDialog.getText(
            dlg,
            "Create profile",
            "Profile name:",
            QtWidgets.QLineEdit.Normal,
            "",
        )
        new_name = new_name.strip()
        if not ok or not new_name:
            return
        if new_name in profiles_data:
            QtWidgets.QMessageBox.warning(dlg, "Create profile", "Profile already exists.")
            return
        base_record = _profile_record(base_name)
        profiles_data[new_name] = base_record
        profiles_yaml["profiles"] = profiles_data
        if not _save_profiles_yaml(profiles_yaml):
            return
        profile_manage_combo.addItem(new_name)
        profile_manage_combo.setCurrentText(new_name)
        if profile_combo.findText(new_name) < 0:
            profile_combo.addItem(new_name)
        _refresh_profile_editor()

    def _add_custom_symbol() -> None:
        raw = symbol_add_edit.text().strip()
        if not raw:
            return
        normalized = _normalize_symbols([raw])
        sym = normalized[0] if normalized else ""
        if not sym:
            return
        symbols = _available_symbols()
        if sym not in symbols:
            symbols.append(sym)
        selected = set(_get_checked_symbols())
        selected.add(sym)
        _set_symbol_list(symbols, selected, using_defaults=False)
        symbol_add_edit.clear()

    def _set_all_symbols(checked: bool) -> None:
        for idx in range(symbols_list.count()):
            item = symbols_list.item(idx)
            item.setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
        profile_symbol_status.setText(
            f"Active symbols: {len(_get_checked_symbols())}/{symbols_list.count()}"
        )

    def _use_market_defaults() -> None:
        name = profile_manage_combo.currentText().strip()
        record = _profile_record(name)
        record.pop("symbols", None)
        profiles_data[name] = record
        profiles_yaml["profiles"] = profiles_data
        if _save_profiles_yaml(profiles_yaml):
            _refresh_profile_editor()

    class _SymbolRecommendWorker(QtCore.QObject):
        done = QtCore.Signal(str)
        error = QtCore.Signal(str)

        def __init__(self, *, settings_obj, symbols: list[str]) -> None:
            super().__init__()
            self._settings = settings_obj
            self._symbols = symbols

        def run(self) -> None:
            try:
                from tradebot_sci.ai.client import TradeSciAIClient
            except Exception as exc:
                self.error.emit(str(exc))
                return
            try:
                ai_client = TradeSciAIClient(self._settings.ai)
                symbols_text = ", ".join(self._symbols)
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are Trade By SCI's ICC assistant. "
                            "Pick the most volatile, liquid symbols for ICC from the given universe. "
                            "Return only a comma-separated list of symbols from the universe. No extra text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Universe: {symbols_text}\n"
                            "Return 5-12 symbols, comma-separated."
                        ),
                    },
                ]
                response = ai_client.generate_text(messages)
                self.done.emit(response)
            except Exception as exc:
                self.error.emit(str(exc))

    _symbol_thread: QtCore.QThread | None = None
    _symbol_worker: _SymbolRecommendWorker | None = None
    _symbol_cleanup_bound = False

    def _parse_symbol_text(raw: str, allowed: set[str]) -> list[str]:
        tokens = _normalize_symbols(re.findall(r"[A-Za-z0-9._-]+", raw))
        return [t for t in tokens if t in allowed]

    def _apply_ai_symbols(symbols: list[str]) -> None:
        allowed = set(_available_symbols())
        symbols_set = set(symbols)
        for idx in range(symbols_list.count()):
            item = symbols_list.item(idx)
            sym = item.text().strip().upper()
            item.setCheckState(QtCore.Qt.Checked if sym in symbols_set else QtCore.Qt.Unchecked)
        profile_symbol_status.setText(f"AI enabled {len(symbols_set)}/{len(allowed)} symbols.")

    def _recommend_done(raw: str) -> None:
        nonlocal _symbol_thread, _symbol_worker
        recommend_symbols_btn.setEnabled(True)
        recommend_symbols_btn.setText("AI Recommendations")
        allowed = set(_available_symbols())
        parsed = _parse_symbol_text(raw, allowed)
        if not parsed:
            QtWidgets.QMessageBox.warning(
                dlg,
                "AI Recommendations",
                "AI response did not include any valid symbols from the available universe.",
            )
            recommended_symbols_edit.setPlainText("")
        else:
            recommended_symbols_edit.setPlainText(", ".join(parsed))
            _apply_ai_symbols(parsed)
        if _symbol_thread is not None:
            _symbol_thread.quit()
            _symbol_thread.wait(500)
        _symbol_thread = None
        _symbol_worker = None

    def _recommend_error(msg: str) -> None:
        nonlocal _symbol_thread, _symbol_worker
        recommend_symbols_btn.setEnabled(True)
        recommend_symbols_btn.setText("AI Recommendations")
        QtWidgets.QMessageBox.warning(dlg, "AI Recommendations", msg)
        if _symbol_thread is not None:
            _symbol_thread.quit()
            _symbol_thread.wait(500)
        _symbol_thread = None
        _symbol_worker = None

    class _SymbolRecommendUi(QtCore.QObject):
        @QtCore.Slot(str)
        def handle_done(self, raw: str) -> None:
            _recommend_done(raw)

        @QtCore.Slot(str)
        def handle_error(self, msg: str) -> None:
            _recommend_error(msg)

    _symbol_ui_handler = _SymbolRecommendUi()
    _symbol_ui_handler.moveToThread(QtCore.QCoreApplication.instance().thread())

    def _recommend_clicked() -> None:
        nonlocal _symbol_thread, _symbol_worker
        candidates = _available_symbols()
        if not candidates:
            QtWidgets.QMessageBox.warning(
                dlg,
                "AI Recommendations",
                "No symbols available. Add symbols or configure market defaults first.",
            )
            return
        recommend_symbols_btn.setEnabled(False)
        recommend_symbols_btn.setText("Running…")
        if _symbol_thread is not None:
            _symbol_thread.quit()
            _symbol_thread.wait(250)
        _symbol_thread = QtCore.QThread()
        _symbol_worker = _SymbolRecommendWorker(settings_obj=settings, symbols=candidates)
        _symbol_worker.moveToThread(_symbol_thread)
        _symbol_thread.started.connect(_symbol_worker.run)
        _symbol_worker.done.connect(_symbol_ui_handler.handle_done, QtCore.Qt.QueuedConnection)
        _symbol_worker.error.connect(_symbol_ui_handler.handle_error, QtCore.Qt.QueuedConnection)
        _symbol_worker.done.connect(_symbol_thread.quit)
        _symbol_worker.error.connect(_symbol_thread.quit)
        _symbol_thread.finished.connect(_symbol_worker.deleteLater)
        _symbol_thread.finished.connect(_symbol_thread.deleteLater)
        _symbol_thread.start()

    def _cleanup_symbol_thread() -> None:
        nonlocal _symbol_thread, _symbol_worker
        if _symbol_thread is not None:
            if _symbol_thread.isRunning():
                _symbol_thread.quit()
                _symbol_thread.wait(1000)
            _symbol_thread = None
        _symbol_worker = None

    if not _symbol_cleanup_bound:
        dlg.finished.connect(_cleanup_symbol_thread)
        _symbol_cleanup_bound = True

    profile_manage_combo.currentTextChanged.connect(_refresh_profile_editor)
    profile_create_btn.clicked.connect(_create_profile)
    profile_save_btn.clicked.connect(_save_profile_changes)
    profile_reset_btn.clicked.connect(_reset_profiles_from_disk)
    symbol_add_btn.clicked.connect(_add_custom_symbol)
    symbol_select_all.clicked.connect(lambda: _set_all_symbols(True))
    symbol_clear_all.clicked.connect(lambda: _set_all_symbols(False))
    symbol_use_defaults.clicked.connect(_use_market_defaults)
    recommend_symbols_btn.clicked.connect(_recommend_clicked)

    profiles_group = QtWidgets.QGroupBox("Profiles")
    profiles_group_layout = QtWidgets.QVBoxLayout()
    profiles_group_layout.addWidget(profile_manage_row_w)
    profiles_group_layout.addWidget(profile_info)
    profiles_group.setLayout(profiles_group_layout)

    symbols_group = QtWidgets.QGroupBox("Symbols (per profile)")
    symbols_layout = QtWidgets.QVBoxLayout()
    symbols_layout.addWidget(symbols_list, 1)
    symbols_layout.addWidget(recommended_symbols_edit)
    symbols_layout.addWidget(recommend_symbols_btn)
    symbols_layout.addWidget(symbol_add_row_w)
    symbols_layout.addWidget(symbol_controls_w)
    symbols_layout.addWidget(profile_symbol_status)
    symbols_group.setLayout(symbols_layout)

    active_group = QtWidgets.QGroupBox("Active Times (profile)")
    active_form = QtWidgets.QFormLayout()
    active_form.setLabelAlignment(QtCore.Qt.AlignRight)

    auto_schedule_combo = QtWidgets.QComboBox()
    auto_schedule_combo.addItem("Default (engine)", "")
    auto_schedule_combo.addItem("Enabled", "true")
    auto_schedule_combo.addItem("Disabled", "false")

    sabbath_enabled_combo_profile = QtWidgets.QComboBox()
    sabbath_enabled_combo_profile.addItem("Default (engine)", "")
    sabbath_enabled_combo_profile.addItem("Enabled", "true")
    sabbath_enabled_combo_profile.addItem("Disabled", "false")

    sabbath_tz_profile = QtWidgets.QLineEdit()
    sabbath_tz_profile.setPlaceholderText("America/New_York")
    sabbath_start_profile = QtWidgets.QLineEdit()
    sabbath_start_profile.setPlaceholderText("18:00")
    sabbath_end_profile = QtWidgets.QLineEdit()
    sabbath_end_profile.setPlaceholderText("18:00")

    active_form.addRow("Auto schedule", auto_schedule_combo)
    active_form.addRow("Sabbath enabled", sabbath_enabled_combo_profile)
    active_form.addRow("Sabbath timezone", sabbath_tz_profile)
    active_form.addRow("Sabbath start (Fri)", sabbath_start_profile)
    active_form.addRow("Sabbath end (Sat)", sabbath_end_profile)
    active_group.setLayout(active_form)

    profiles_layout.addWidget(profiles_group)
    profiles_layout.addWidget(symbols_group, 1)
    profiles_layout.addWidget(active_group)
    profiles_layout.addStretch(1)

    _refresh_profile_editor()

    # Create Strategy sub-tabs
    strategy_tabs = QtWidgets.QTabWidget(dlg)
    strategy_tabs.addTab(scroll(strategy_core_inner), "Core")
    strategy_tabs.addTab(scroll(strategy_icc_inner), "ICC")
    strategy_tabs.addTab(scroll(strategy_auto_entry_inner), "Auto Entry")

    tabs = QtWidgets.QTabWidget(dlg)
    tabs.addTab(scroll(bot_inner), "Bot")
    tabs.addTab(scroll(time_inner), "Time/Sabbath")
    tabs.addTab(scroll(market_inner), "Market")
    tabs.addTab(scroll(profiles_inner), "Profiles")
    tabs.addTab(scroll(runtime_inner), "Runtime")
    tabs.addTab(scroll(risk_inner), "Risk")
    tabs.addTab(strategy_tabs, "Strategy")
    tabs.addTab(scroll(scoring_inner), "Scoring")
    tabs.addTab(scroll(commentary_inner), "Commentary")
    tabs.addTab(scroll(ai_inner), "AI")
    tabs.addTab(scroll(ibkr_inner), "IBKR")
    tabs.addTab(scroll(ccxt_inner), "CCXT")
    tabs.addTab(scroll(benchmark_inner), "Benchmark")
    tabs.addTab(adv_tab, "Advanced (env)")

    layout = QtWidgets.QVBoxLayout()
    layout.addWidget(tabs, 1)
    layout.addLayout(btns)
    dlg.setLayout(layout)

    refresh_preview()
    dlg.exec()


def run_settings_only(repo_root: Path) -> int:
    """Run only the settings dialog for debugging purposes.
    
    Args:
        repo_root: Path to the repository root
        
    Returns:
        Exit code (0 for success)
    """
    import os
    import sys
    
    # Set up paths
    sys.path.insert(0, str(repo_root / "src"))
    os.chdir(repo_root)
    
    # Import dependencies
    from tradebot_sci.config.loader import load_settings
    
    # Create Qt application
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Tradebot SCI Settings")
    
    # Load settings
    settings = load_settings()
    
    # Create a minimal mock parent widget
    class MockParent(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self._bot_autostart = False
            self._bot_keep_running = False
            self._bot_keep_running_on_close = False
            self._repo_root = repo_root
            self._tmux_restart_preview = ""

        def _effective_env_value(self, key: str) -> tuple[str, str]:
            val = os.getenv(key, "")
            return (val, "env" if val else "default")

    parent = MockParent()
    
    # Discover environment keys from settings
    discovered_keys = [
        "IBKR_ACCOUNT", "IBKR_PORT", "IBKR_HOST",
        "CCXT_EXCHANGE", "CCXT_API_KEY", "CCXT_API_SECRET",
        "CHATGPT_KEY", "EXECUTE_TRADES", "LOG_LEVEL",
        "PROFILE_NAME", "SABBATH_MODE"
    ]
    
    # Empty dotenv values for now
    dotenv_values = {}
    
    # Call the settings dialog with theme_key
    try:
        open_settings_dialog(
            parent,
            settings,
            repo_root,
            discovered_keys,
            dotenv_values,
            "dark",  # theme_key parameter
        )
    except Exception as e:
        print(f"Error opening settings dialog: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0
