"""
Central path resolution for user data directories.

Separates user-generated runtime data from the application source code,
using OS-appropriate directories:

    Linux:   ~/.config/tradebot-sci/
    macOS:   ~/Library/Application Support/tradebot-sci/
    Windows: %APPDATA%/tradebot-sci/

All runtime state (ledger, trade results, logs, config, secrets) lives
in the user data directory. The application directory only contains
source code, documentation, and templates.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "tradebot-sci"

# ── Application root (where the source code lives) ─────────────────────
APP_DIR = Path(__file__).resolve().parent.parent.parent
"""Root of the application install (contains src/, Documentation/, scripts/)."""


def get_user_data_dir() -> Path:
    """Return the OS-appropriate user data directory."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    else:
        # Linux / BSD — respect XDG_CONFIG_HOME
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(xdg) / APP_NAME


def get_instance_id() -> str:
    """Return the unique instance identifier for scoping data and logs."""
    iid = os.environ.get("TRADEBOT_INSTANCE_ID")
    if iid:
        return iid

    ws_url = os.environ.get("GUI_WS_URL")
    if not ws_url:
        env_file = APP_DIR / ".env"
        if env_file.is_file():
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("GUI_WS_URL="):
                            ws_url = line.split("=", 1)[1].strip()
                            break
            except Exception:
                pass

    if ws_url:
        import re
        m = re.search(r":(\d+)", ws_url)
        if m:
            return f"instance_{m.group(1)}"
        clean = re.sub(r"[^A-Za-z0-9_]", "_", ws_url)
        return f"instance_{clean}"

    return "instance_8080"


# ── Resolved directories ──────────────────────────────────────────────
USER_DATA_DIR = get_user_data_dir()
INSTANCE_ID   = get_instance_id()
DATA_DIR      = USER_DATA_DIR / "data" / INSTANCE_ID
LOG_DIR       = USER_DATA_DIR / "logs" / INSTANCE_ID
CONFIG_FILE   = USER_DATA_DIR / "config.json"
SECRETS_FILE  = USER_DATA_DIR / ".env.secrets"
CONFIG_DIR    = USER_DATA_DIR / "config"


def ensure_dirs() -> None:
    """Create user data directories if they don't exist."""
    for d in [USER_DATA_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Auto-migrate legacy top-level data/logs into the instance subdirectory if empty
    legacy_data = USER_DATA_DIR / "data"
    if legacy_data.is_dir() and DATA_DIR != legacy_data:
        for fname in os.listdir(legacy_data):
            src = legacy_data / fname
            dst = DATA_DIR / fname
            if src.is_file() and not dst.exists():
                try: shutil.copy2(src, dst)
                except Exception: pass

    legacy_logs = USER_DATA_DIR / "logs"
    if legacy_logs.is_dir() and LOG_DIR != legacy_logs:
        for fname in os.listdir(legacy_logs):
            src = legacy_logs / fname
            dst = LOG_DIR / fname
            if src.is_file() and not dst.exists():
                try: shutil.copy2(src, dst)
                except Exception: pass


def migrate_if_needed() -> None:
    """
    One-time migration: copy data from the old app-relative locations
    to the new user data directory when files are missing from the
    new location but present in the old one.

    Copies: data/, logs/, config.json, .env.secrets, config/settings_profiles.yaml
    Leaves old files in place as backup.
    """
    ensure_dirs()

    old_data     = APP_DIR / "data"
    old_logs     = APP_DIR / "logs"
    old_config   = APP_DIR / "config.json"
    old_secrets  = APP_DIR / ".env.secrets"
    old_profiles = APP_DIR / "config" / "settings_profiles.yaml"

    migrated = []

    # ── Migrate data/ (check for critical files inside) ──────────────
    if old_data.is_dir():
        for fname in os.listdir(old_data):
            src = old_data / fname
            dst = DATA_DIR / fname
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)
                migrated.append(f"data/{fname} -> {dst}")
            elif src.is_dir() and not dst.exists():
                shutil.copytree(src, dst)
                migrated.append(f"data/{fname}/ -> {dst}")

    # ── Migrate logs/ ───────────────────────────────────────────────
    if old_logs.is_dir():
        for fname in os.listdir(old_logs):
            src = old_logs / fname
            dst = LOG_DIR / fname
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)
                migrated.append(f"logs/{fname} -> {dst}")

    # ── Migrate config.json ─────────────────────────────────────────
    if old_config.is_file() and not CONFIG_FILE.exists():
        shutil.copy2(old_config, CONFIG_FILE)
        migrated.append(f"config.json -> {CONFIG_FILE}")

    # ── Migrate .env.secrets ────────────────────────────────────────
    if old_secrets.is_file() and not SECRETS_FILE.exists():
        shutil.copy2(old_secrets, SECRETS_FILE)
        migrated.append(f".env.secrets -> {SECRETS_FILE}")

    # ── Migrate settings_profiles.yaml ──────────────────────────────
    if old_profiles.is_file() and not (CONFIG_DIR / "settings_profiles.yaml").exists():
        shutil.copy2(old_profiles, CONFIG_DIR / "settings_profiles.yaml")
        migrated.append(f"config/settings_profiles.yaml -> {CONFIG_DIR / 'settings_profiles.yaml'}")

    if migrated:
        logger.warning("=" * 60)
        logger.warning("[PATHS] User data migrated to new location:")
        logger.warning(f"[PATHS]   {USER_DATA_DIR}")
        for m in migrated:
            logger.warning(f"[PATHS]   {m}")
        logger.warning("[PATHS] Old files left in place as backup.")
        logger.warning("[PATHS] You can safely delete them once verified.")
        logger.warning("=" * 60)

