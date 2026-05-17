"""
Central path resolution for user data directories.

Separates user-generated runtime data from the application source code,
using OS-appropriate directories:

    Linux:   ~/.config/tradebot-sci-gui/<instance_id>/
    macOS:   ~/Library/Application Support/tradebot-sci-gui/<instance_id>/
    Windows: %APPDATA%/tradebot-sci-gui/<instance_id>/

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

APP_NAME = "tradebot-sci-gui"

# ── Application root (where the source code lives) ─────────────────────
APP_DIR = Path(__file__).resolve().parent.parent.parent
"""Root of the application install (contains src/, Documentation/, scripts/)."""


def get_active_instance_name(ws_url: str | None) -> str:
    if not ws_url:
        return "local"
    if "localhost" in ws_url or "127.0.0.1" in ws_url:
        return "local"
    import hashlib
    h = hashlib.md5(ws_url.encode("utf-8")).hexdigest()[:8]
    return f"remote-{h}"


def get_root_config_dir() -> Path:
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
    if ws_url:
        return get_active_instance_name(ws_url)

    root_dir = get_root_config_dir()
    active_file = root_dir / "active_instance.txt"
    if active_file.is_file():
        try:
            name = active_file.read_text(encoding="utf-8").strip()
            if name:
                return name
        except Exception:
            pass

    env_file = APP_DIR / ".env"
    if env_file.is_file():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GUI_WS_URL="):
                        ws_url = line.split("=", 1)[1].strip()
                        return get_active_instance_name(ws_url)
        except Exception:
            pass

    return "local"


def get_user_data_dir(instance_id: str) -> Path:
    """Return the OS-appropriate user data directory for the instance."""
    td = os.environ.get("TRADEBOT_DATA_DIR")
    if td:
        p = Path(td)
        if p.name in ("data", "logs", "config"):
            p = p.parent
        if p.name == instance_id or instance_id in str(p):
            return p
        return p / instance_id

    return get_root_config_dir() / instance_id


# ── Resolved directories ──────────────────────────────────────────────
INSTANCE_ID   = get_instance_id()
USER_DATA_DIR = get_user_data_dir(INSTANCE_ID)
DATA_DIR      = USER_DATA_DIR / "data"
LOG_DIR       = Path("/app/logs") / INSTANCE_ID if os.environ.get("TRADEBOT_DATA_DIR") == "/app/data" else USER_DATA_DIR / "logs"
CONFIG_FILE   = USER_DATA_DIR / "config.json"
SECRETS_FILE  = USER_DATA_DIR / ".env.secrets"
CONFIG_DIR    = USER_DATA_DIR / "config"


def ensure_dirs() -> None:
    """Create user data directories if they don't exist."""
    for d in [USER_DATA_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Auto-migrate legacy top-level data/logs/config into the instance subdirectory if empty
    legacy_root = get_root_config_dir().parent / "tradebot-sci"
    
    legacy_config = legacy_root / "config.json"
    if legacy_config.is_file() and not CONFIG_FILE.exists():
        try: shutil.copy2(legacy_config, CONFIG_FILE)
        except Exception: pass

    legacy_secrets = legacy_root / ".env.secrets"
    if legacy_secrets.is_file() and not SECRETS_FILE.exists():
        try: shutil.copy2(legacy_secrets, SECRETS_FILE)
        except Exception: pass

    legacy_data = legacy_root / "data"
    if legacy_data.is_dir() and DATA_DIR != legacy_data:
        for fname in os.listdir(legacy_data):
            src = legacy_data / fname
            dst = DATA_DIR / fname
            if src.is_file() and not dst.exists():
                if INSTANCE_ID.startswith("remote-") and fname in ("ledger.json", "paper_ledger.json", "trade_results.json", "paper_trade_results.json", "paper_state.json"):
                    continue
                try: shutil.copy2(src, dst)
                except Exception: pass
            elif src.is_dir() and not dst.exists():
                if fname == "local" or fname.startswith("remote-") or fname.startswith("instance_"):
                    continue
                try: shutil.copytree(src, dst)
                except Exception: pass

    legacy_logs = legacy_root / "logs"
    if legacy_logs.is_dir() and LOG_DIR != legacy_logs:
        for fname in os.listdir(legacy_logs):
            src = legacy_logs / fname
            dst = LOG_DIR / fname
            if src.is_file() and not dst.exists():
                if INSTANCE_ID.startswith("remote-") and fname.endswith(".log"):
                    continue
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

    # If old_data is the same as USER_DATA_DIR (e.g. TRADEBOT_DATA_DIR=/app/data in Docker/K8s),
    # or if USER_DATA_DIR is inside old_data, do not attempt legacy migration to avoid infinite recursion.
    try:
        if USER_DATA_DIR.resolve() == old_data.resolve() or USER_DATA_DIR.resolve().is_relative_to(old_data.resolve()):
            return
    except AttributeError:
        # Fallback for Python < 3.9
        if USER_DATA_DIR.resolve() == old_data.resolve() or str(USER_DATA_DIR.resolve()).startswith(str(old_data.resolve())):
            return

    migrated = []

    # ── Migrate data/ (check for critical files inside) ──────────────
    if old_data.is_dir():
        for fname in os.listdir(old_data):
            src = old_data / fname
            dst = DATA_DIR / fname
            if src.is_file() and not dst.exists():
                if INSTANCE_ID.startswith("remote-") and fname in ("ledger.json", "paper_ledger.json", "trade_results.json", "paper_trade_results.json", "paper_state.json"):
                    continue
                shutil.copy2(src, dst)
                migrated.append(f"data/{fname} -> {dst}")
            elif src.is_dir() and not dst.exists():
                if fname == "local" or fname.startswith("remote-") or fname.startswith("instance_"):
                    continue
                # Prevent copying a directory into its own child directory
                try:
                    if dst.resolve().is_relative_to(src.resolve()):
                        continue
                except AttributeError:
                    if str(dst.resolve()).startswith(str(src.resolve())):
                        continue

                shutil.copytree(src, dst)
                migrated.append(f"data/{fname}/ -> {dst}")

    # ── Migrate logs/ ───────────────────────────────────────────────
    if old_logs.is_dir():
        for fname in os.listdir(old_logs):
            src = old_logs / fname
            dst = LOG_DIR / fname
            if src.is_file() and not dst.exists():
                if INSTANCE_ID.startswith("remote-") and fname.endswith(".log"):
                    continue
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

