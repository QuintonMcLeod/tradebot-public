#!/usr/bin/env python3
"""
=============================================================================
LEGACY CONFIG IMPORT TOOL
=============================================================================

Run this script if you're upgrading from an older version of TradeBotSCI
that used .env and YAML files for configuration.

This script will:
  1. Read your existing .env file
  2. Read your settings_profiles.yaml and settings_base.yaml 
  3. Merge everything into the new config.json format
  4. Extract API keys into a separate .env.secrets file
  5. Create backups of your old config files

USAGE:
  python tools/import_legacy_config.py

After running, you can safely delete your old .env and YAML config files.
The new system uses only config.json and .env.secrets.
=============================================================================
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

# Try to import yaml, fall back gracefully
try:
    import yaml
except ImportError:
    print("PyYAML not installed. Run: pip install pyyaml")
    exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = PROJECT_ROOT / "config"

OLD_ENV = PROJECT_ROOT / ".env"
OLD_PROFILES_YAML = CONFIG_DIR / "settings_profiles.yaml"
OLD_BASE_YAML = CONFIG_DIR / "settings_base.yaml"

NEW_CONFIG_JSON = PROJECT_ROOT / "config.json"
NEW_SECRETS = PROJECT_ROOT / ".env.secrets"
BACKUP_DIR = PROJECT_ROOT / "config_backup"

# Keys that are secrets (should go to .env.secrets, not config.json)
SECRET_KEYS = {
    "TRADE_SCI_API_KEY",
    "CHATGPT_KEY",
    "OANDA_API_KEY",
    "GEMINI_API_KEY",
    "GEMINI_API_SECRET",
    "CCXT_API_KEY",
    "CCXT_SECRET",
    "PAXOS_API_KEY",
    "PAXOS_API_SECRET",
}

# Keys to skip (comments or deprecated)
SKIP_KEYS = {"#"}


def parse_env_file(path: Path) -> dict:
    """Parse a .env file into a dictionary."""
    if not path.exists():
        return {}
    
    result = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
            if match:
                key, value = match.groups()
                # Remove surrounding quotes
                value = value.strip('"').strip("'")
                result[key] = value
    return result


def load_yaml_file(path: Path) -> dict:
    """Load a YAML file, return empty dict if missing."""
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def convert_value(value: str):
    """Convert string value to appropriate Python type."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "none" or value == "":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def categorize_env_key(key: str) -> str:
    """Determine which section a key belongs to."""
    key_upper = key.upper()
    
    if key_upper in SECRET_KEYS:
        return "secret"
    
    # Broker settings
    if any(x in key_upper for x in ["IBKR_", "OANDA_", "GEMINI_", "CCXT_", "PAXOS_", "BROKER"]):
        return "brokers"
    
    # AI/LLM settings
    if any(x in key_upper for x in ["TRADE_SCI_", "CHATGPT", "COMMENTARY_LLM", "AI_"]):
        return "ai"
    
    # Safety settings
    if any(x in key_upper for x in ["SAFETY_", "PDT_", "GUARD", "SABBATH", "EMERGENCY", "FRICTION", "VIX"]):
        return "safety"
    
    # Performance settings
    if any(x in key_upper for x in ["PERFORMANCE_", "TRAILING_", "COMPOUNDING", "PYRAMID", "KELLY", "FLYWHEEL"]):
        return "performance"
    
    # Risk settings
    if any(x in key_upper for x in ["RISK_", "MAX_LOSS", "MAX_DAILY", "EXPOSURE"]):
        return "risk"
    
    # Profile overrides
    if key_upper.startswith("PROFILE_"):
        return "profile_override"
    
    # Default to global
    return "global"


def build_config(env_data: dict, profiles_yaml: dict, base_yaml: dict) -> tuple[dict, dict]:
    """
    Build the new config.json structure and extract secrets.
    Returns (config_dict, secrets_dict).
    """
    config = {
        "active_profile": env_data.get("APP_PROFILE", "forex_crypto_hybrid"),
        "global": {},
        "brokers": {
            "primary_forex": env_data.get("BROKER_FOREX", env_data.get("PRIMARY_BROKER", "oanda")),
            "primary_crypto": env_data.get("BROKER_CRYPTO", "gemini"),
            "primary_equities": env_data.get("BROKER_EQUITIES", "ibkr"),
            "ibkr": {},
            "oanda": {},
            "gemini": {},
            "ccxt": {},
        },
        "ai": {
            "provider": env_data.get("TRADE_SCI_PROVIDER", "deepseek"),
            "model": env_data.get("TRADE_SCI_MODEL_NAME", "deepseek-chat"),
            "temperature": convert_value(env_data.get("TRADE_SCI_TEMPERATURE", "0")),
            "max_tokens": convert_value(env_data.get("TRADE_SCI_MAX_TOKENS", "1024")),
            "commentary_policy": env_data.get("COMMENTARY_LLM_POLICY", "on_signal"),
            "commentary_daily_slots": env_data.get("COMMENTARY_LLM_DAILY_SLOTS", "09:00,12:00,18:00,22:00"),
            "commentary_timezone": env_data.get("COMMENTARY_LLM_TZ", "America/New_York"),
        },
        "safety": {},
        "performance": {},
        "risk": {},
        "profiles": profiles_yaml.get("profiles", {}),
    }
    
    secrets = {}
    
    # Process all env keys
    for key, value in env_data.items():
        category = categorize_env_key(key)
        converted = convert_value(value)
        
        if category == "secret":
            secrets[key] = value  # Keep secrets as strings
            continue
        
        if category == "profile_override":
            # Strip PROFILE_ prefix and add to active profile
            clean_key = key.replace("PROFILE_", "").lower()
            active = config["active_profile"]
            if active in config["profiles"]:
                config["profiles"][active][clean_key] = converted
            continue
        
        # Map specific keys to their sections
        if category == "brokers":
            if key.startswith("IBKR_"):
                config["brokers"]["ibkr"][key.replace("IBKR_", "").lower()] = converted
            elif key.startswith("OANDA_"):
                config["brokers"]["oanda"][key.replace("OANDA_", "").lower()] = converted
            elif key.startswith("GEMINI_"):
                config["brokers"]["gemini"][key.replace("GEMINI_", "").lower()] = converted
            elif key.startswith("CCXT_"):
                config["brokers"]["ccxt"][key.replace("CCXT_", "").lower()] = converted
            else:
                config["brokers"][key.lower()] = converted
        elif category == "safety":
            config["safety"][key.lower()] = converted
        elif category == "performance":
            config["performance"][key.lower()] = converted
        elif category == "risk":
            config["risk"][key.lower()] = converted
        else:
            config["global"][key.lower()] = converted
    
    return config, secrets


def create_backup():
    """Create backup of old config files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / timestamp
    backup_path.mkdir(parents=True, exist_ok=True)
    
    files_to_backup = [OLD_ENV, OLD_PROFILES_YAML, OLD_BASE_YAML]
    for f in files_to_backup:
        if f.exists():
            shutil.copy2(f, backup_path / f.name)
            print(f"  Backed up: {f.name}")
    
    return backup_path


def write_secrets_file(secrets: dict, path: Path):
    """Write secrets to .env.secrets file."""
    with open(path, "w") as f:
        f.write("# API Keys and Secrets - DO NOT COMMIT TO GIT\n")
        f.write("# Generated by migrate_to_json.py\n\n")
        for key, value in sorted(secrets.items()):
            f.write(f"{key}={value}\n")


def main():
    print("=" * 60)
    print("Config Migration: .env + YAML → config.json")
    print("=" * 60)
    
    # Step 1: Create backup
    print("\n[1/5] Creating backup...")
    backup_path = create_backup()
    print(f"  Backup created at: {backup_path}")
    
    # Step 2: Load existing config files
    print("\n[2/5] Loading existing config files...")
    env_data = parse_env_file(OLD_ENV)
    print(f"  Loaded {len(env_data)} keys from .env")
    
    profiles_yaml = load_yaml_file(OLD_PROFILES_YAML)
    profile_count = len(profiles_yaml.get("profiles", {}))
    print(f"  Loaded {profile_count} profiles from settings_profiles.yaml")
    
    base_yaml = load_yaml_file(OLD_BASE_YAML)
    print(f"  Loaded {len(base_yaml)} keys from settings_base.yaml")
    
    # Step 3: Build new config structure
    print("\n[3/5] Building new config structure...")
    config, secrets = build_config(env_data, profiles_yaml, base_yaml)
    print(f"  Config sections: {list(config.keys())}")
    print(f"  Extracted {len(secrets)} secret keys")
    
    # Step 4: Write new files
    print("\n[4/5] Writing new config files...")
    
    with open(NEW_CONFIG_JSON, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"  Created: {NEW_CONFIG_JSON}")
    
    write_secrets_file(secrets, NEW_SECRETS)
    print(f"  Created: {NEW_SECRETS}")
    
    # Step 5: Verify
    print("\n[5/5] Verifying...")
    with open(NEW_CONFIG_JSON, "r") as f:
        verify = json.load(f)
    print(f"  config.json is valid JSON with {len(verify['profiles'])} profiles")
    print(f"  Active profile: {verify['active_profile']}")
    
    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
    print(f"\nNext steps:")
    print(f"  1. Review {NEW_CONFIG_JSON}")
    print(f"  2. Review {NEW_SECRETS} (add to .gitignore!)")
    print(f"  3. Update Python backend to load from config.json")
    print(f"  4. Update Electron GUI to read/write config.json")


if __name__ == "__main__":
    main()
