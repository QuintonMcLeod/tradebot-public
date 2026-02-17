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


# ── Resolved directories ──────────────────────────────────────────────
USER_DATA_DIR = get_user_data_dir()
DATA_DIR      = USER_DATA_DIR / "data"
LOG_DIR       = USER_DATA_DIR / "logs"
CONFIG_FILE   = USER_DATA_DIR / "config.json"
SECRETS_FILE  = USER_DATA_DIR / ".env.secrets"
CONFIG_DIR    = USER_DATA_DIR / "config"


def ensure_dirs() -> None:
    """Create user data directories if they don't exist."""
    for d in [USER_DATA_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR]:
        d.mkdir(parents=True, exist_ok=True)


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

