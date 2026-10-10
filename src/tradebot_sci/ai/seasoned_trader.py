import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("sys.seasoned_trader")

class SentinelMemory:
    """
    Persistent scratchpad for the Seasoned Trader AI.
    Allows the 20-year veteran model to store thoughts, remember prior setting
    adjustments, track the PnL consequence of those adjustments, and maintain
    cohesive session continuity across stateless API calls.
    """
    def __init__(self, cache_dir: str = "/tmp/tradebot_ai_cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.memory_file = os.path.join(self.cache_dir, "sentinel_memory.json")
        self._memory = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[Sentinel] Error loading memory: {e}")
        
        return {
            "session_start": datetime.now().isoformat(),
            "notes": [],
            "last_action": None,
            "performance_tracker": []
        }

    def save(self):
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self._memory, f, indent=4)
        except Exception as e:
            logger.error(f"[Sentinel] Error saving memory: {e}")

    def add_note(self, content: str):
        self._memory["notes"].append({
            "timestamp": datetime.now().isoformat(),
            "content": content
        })
        # Keep last 50 notes
        if len(self._memory["notes"]) > 50:
            self._memory["notes"] = self._memory["notes"][-50:]
        self.save()

    def record_action(self, action_type: str, details: dict):
        action_obj = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "details": details
        }
        self._memory["last_action"] = action_obj
        self._memory["performance_tracker"].append(action_obj)
        if len(self._memory["performance_tracker"]) > 20:
             self._memory["performance_tracker"] = self._memory["performance_tracker"][-20:]
        self.save()

    def get_contextual_memory(self) -> str:
        """Formats the memory cache into a tight prompt block."""
        lines = ["[AI SELF-NOTES (Persistent Scratchpad)]"]
        for note in self._memory.get("notes", [])[-5:]:
            lines.append(f" - [{note['timestamp']}] {note['content']}")
            
        lines.append("\n[RECENT ACTIONS]")
        for action in self._memory.get("performance_tracker", [])[-3:]:
             lines.append(f" - {action['type']}: {json.dumps(action['details'])}")
             
        return "\n".join(lines)


# ── SETTINGS REFERENCE (Tooltip Dictionary for AI Context) ──────────────────
# This curated subset of the GUI's tooltip library gives the AI a layman's
# understanding of what each setting does, enabling intelligent adjustments.

SENTINEL_TOOLTIP_REFERENCE = {
    # ── Risk Management ──
    "RISK_PER_TRADE_PCT": "How much of your entire account to risk on a single trade. 0.01 = 1%. Never risk more than you can stomach.",
    "MAX_EXPOSURE_PCT": "Maximum total risk across ALL open trades combined. Acts as a portfolio-level cap.",
    "LIMIT_LOSS_DAILY_PCT": "If you lose this % of your account in one day, the bot stops trading for the rest of the day.",
    "RISK_REWARD_RATIO": "For every dollar risked, how many dollars do you want to target? 2.0 means risk $1 to make $2.",
    "MAX_LOSS_PER_TRADE_DOLLARS": "Absolute hard dollar cap on any single trade loss, overriding percentage math.",
    "TARGET_PROFIT_DAILY_PCT": "If you make this much profit today, the bot stops to lock in gains.",

    # ── Safety Shields ──
    "SAFETY_STABILITY_MODE_ENABLED": "Master survival protocol. Forces strict 1% risk, 75+ grade trades only, and disables aggressive modes during rough patches.",
    "SAFETY_DRAWDOWN_BREAKER_ENABLED": "If account drops by a set %, bot locks down for 24 hours.",
    "SAFETY_DRAWDOWN_MAX_PCT": "The drawdown threshold that triggers the breaker.",
    "SAFETY_GREED_GUARD_ENABLED": "Stops trading after hitting the daily profit target so you don't give gains back.",
    "SAFETY_GREED_GUARD_TARGET": "The daily profit % that triggers Greed Guard.",
    "SAFETY_STREAK_BREAKER_ENABLED": "After 3 losses in a row on a symbol, puts that symbol in timeout for 4 hours.",
    "SAFETY_CHURN_BURNER_ENABLED": "Prevents too many trades per hour in choppy markets.",
    "SAFETY_LEVERAGE_SENTRY_ENABLED": "Blocks new trades if total leverage gets too high.",
    "SAFETY_MAX_TOTAL_LEVERAGE": "Maximum total leverage allowed across all open positions.",
    "SAFETY_VOLATILITY_VETO_ENABLED": "Prevents trading if volatility is too low (boring) or too high (explosive).",
    "SAFETY_OPENING_SENTRY_ENABLED": "Blocks trading during the wild first 15 minutes after market open.",
    "SAFETY_SESSION_LOCKOUT_ENABLED": "Stops new trades after a set hour (usually noon) when markets get messy.",
    "SAFETY_ROLLOVER_DEADZONE_ENABLED": "Blocks trades at 5 PM EST when banks close books and spreads spike.",
    "SAFETY_SENTIMENT_SHIELD_ENABLED": "Asks the AI to review a chart before entering. Cancels if AI says 'dangerous'.",
    "SAFETY_ATR_SHIELD_ENABLED": "Auto-moves stop-loss to breakeven once trade is safely in profit.",
    "SAFETY_FEE_SHIELD_ENABLED": "Blocks trades where the potential reward isn't large enough to cover broker spreads/commissions.",
    "SAFETY_FEE_RT_PCT": "The minimum profit buffer in % required by the Fee Shield to clear broker fees.",
    "BLOCK_COUNTER_TREND_ENTRIES": "Blocks the bot from trading against the big-picture trend direction.",

    # ── Position & Pyramiding ──
    "MULTI_POSITION_ENABLED": "Allows multiple trades open at the same time.",
    "MAX_CONCURRENT_POSITIONS": "Maximum number of simultaneous open trades.",
    "CONDUCTOR_PYRAMID_ENABLED": "Allows adding more money to winning trades (pyramiding).",
    "CONDUCTOR_PYRAMID_START_R": "Profit level (in R-multiples) before the first pyramid fires.",
    "MAX_PYRAMID_ENTRIES": "Maximum extra entries on a winning trade. 1 = no pyramiding.",

    # ── Exit & Trailing ──
    "TRAILING_STOP_ENABLED": "Trailing stop that follows price upward, locking in profit.",
    "TRAILING_STOP_MIN_PROFIT_PCT": "Minimum profit before trailing stop activates.",
    "WINNER_GIVEBACK_ENABLED": "If enabled, uses the 'Winner Giveback' strategy in the exit router to protect profit after MFE hits 1.5R. Highly recommended for trending markets.",
    "WINNER_GIVEBACK_PCT": "The percentage of peak profit (MFE) you are willing to give back before exiting. 0.30 = 30%. Lower values (0.15) are tighter; higher (0.50) are looser.",
    "STOP_ATR_MULTIPLIER": "Distance of stop-loss from entry, as a multiple of ATR (market volatility).",
    "MIN_HOLD_HOURS": "Minimum time a trade must be held before it can be closed.",
    "MAX_HOLD_HOURS": "Maximum time a trade is allowed to stay open.",
    "AUTO_FLATTEN_ON_CLOSE": "Close ALL trades when the trading session ends.",

    # ── Strategy ──
    "STRATEGY_VARIANT": "The default trading algorithm for the profile (e.g. meta_sci, supply_demand, rubberband_reaper).",
    "STRATEGY_CRYPTO": "Which strategy to use specifically for crypto trades.",
    "STRATEGY_FOREX": "Which strategy to use specifically for forex trades.",
    "STRATEGY_STOCKS": "Which strategy to use specifically for stock trades.",

    # ── Timeframes ──
    "HTF_TIMEFRAME": "Higher timeframe — the big-picture chart for overall market direction (e.g., 1h).",
    "LTF_TIMEFRAME": "Lower timeframe — the zoomed-in chart for precise entry timing (e.g., 5m).",

    # ── Session & Schedule ──
    "SESSION_GATE_ENABLED": "Only trade during active, busy market hours. Naps during quiet hours.",
    "CONTINUOUS_MODE": "Run the bot 24/7 with no breaks between sessions.",

    # ── Sabbath ──
    "SABBATH_ENABLED": "Stop all trading during the Jewish Sabbath (Friday sunset to Saturday sunset).",
    "SABBATH_ASTRONOMICAL": "Use real astronomy to calculate sunset times instead of fixed clock times.",
    "SABBATH_TIMEZONE": "Timezone for Sabbath calculations (e.g., America/New_York).",
}

# ── Profile-specific tooltips (for AI understanding of profile fields) ──
# Every key advertised here must be inside config/loader.py's profile
# whitelist. Nested keys under "strategies" are the one exception: the loader
# merges that sub-dict as a whole. Advertising a key outside the whitelist
# invites the AI to write a profile that the loader then rejects fatally.
SENTINEL_PROFILE_REFERENCE = {
    "strategy_variant": "Default trading algorithm for this profile.",
    "htf_timeframe": "Higher timeframe — big-picture market direction chart.",
    "ltf_timeframe": "Lower timeframe — zoomed-in entry timing chart.",
    "symbols": "List of ticker symbols this profile actively monitors and trades.",
    "continuous_mode": "Run 24/7 without session breaks.",
    "risk_dynamic_auto": "Size each trade from live market conditions instead of a fixed percentage.",
    "strategies.crypto": "Strategy override for crypto trades.",
    "strategies.forex": "Strategy override for forex trades.",
    "strategies.stocks": "Strategy override for stock trades.",
    "strategies.etf": "Strategy override for ETF trades.",
    "strategies.metals": "Strategy override for metals trades.",
    "strategies.futures": "Strategy override for futures trades.",
}


# ── AUTOPILOT DAEMON ────────────────────────────────────────────────────────
import threading
import yaml
from tradebot_sci.paths import CONFIG_FILE, DATA_DIR, CONFIG_DIR
from tradebot_sci.ai.news_scraper import RSSNewsScraper
from tradebot_sci.runtime.sabbath import SabbathContext
from datetime import timedelta

# Path to the profiles YAML — same file the Electron GUI reads/writes
PROFILES_YAML = CONFIG_DIR / "settings_profiles.yaml"
# Fallback to project-local config dir if XDG path doesn't exist
_LEGACY_PROFILES = Path(__file__).resolve().parents[2] / "config" / "settings_profiles.yaml"


class SeasonedTraderDaemon:
    """
    The 20-Year Veteran AI Autopilot.
    Monitors global market states, ingests news, manages risk parameters dynamically,
    manages profiles & schedules, respects Sabbath boundaries, and maintains temporal
    continuity through the SentinelMemory system.
    """
    def __init__(self, ai_client, config_payload: dict, controller=None):
        self.ai = ai_client
        self.controller = controller
        self.ws_server = controller.ws_server if controller else None
        self.interval_mins = int(config_payload.get("AI_AUTOPILOT_INTERVAL_MINS", 30))
        self.personality = config_payload.get("AI_PERSONALITY", "veteran")
        self.monetary_path = config_payload.get("AI_MONETARY_PATH", "balanced")
        self.memory = SentinelMemory() # Kept SentinelMemory as per original
        self.news_scraper = RSSNewsScraper() # Kept RSSNewsScraper as per original
        self.running = False
        self._thread = None
        self.cfg = config_payload or {}

    # ── Profile I/O ─────────────────────────────────────────────────────────

    def _get_profiles_path(self) -> Path:
        """Resolve the active profiles YAML path."""
        if PROFILES_YAML.exists():
            return PROFILES_YAML
        if _LEGACY_PROFILES.exists():
            return _LEGACY_PROFILES
        return PROFILES_YAML  # default write target

    def _read_profiles(self) -> dict:
        """Read all profiles from settings_profiles.yaml."""
        path = self._get_profiles_path()
        if not path.exists():
            return {}
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            return data.get("profiles", {}) if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"[Sentinel] Failed to read profiles: {e}")
            return {}

    def _write_profiles(self, profiles: dict) -> bool:
        """Write profiles back to settings_profiles.yaml atomically.

        Same temp-file-plus-replace discipline as _write_config: a failed
        dump must not leave a half-written YAML behind.
        """
        path = self._get_profiles_path()
        tmp_file = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_file, 'w', encoding="utf-8") as f:
                yaml.dump({"profiles": profiles}, f, default_flow_style=False, width=1000)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, path)
            logger.info(f"[Sentinel] Profiles YAML saved to {path}")
            return True
        except Exception as e:
            logger.error(f"[Sentinel] Failed to write profiles: {e}")
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except Exception:
                pass
            return False

    # ── HARD BLOCKLIST: Keys the AI must NEVER modify ──────────────────
    # These are architecturally load-bearing settings that break the
    # strategy pipeline if changed (e.g., MTF alignment gate requires
    # specific timeframe pairings — changing ltf to 1m starves ADX).
    _PROFILE_MODIFY_BLOCKLIST = {
        "htf_timeframe", "mtf_timeframe", "ltf_timeframe",
        "timeframe", "execution_timeframe",
        "execute_trades", # [SAFETY] AI must NEVER toggle live trading
    }

    def _allowed_profile_keys(self) -> set:
        """The loader's profile whitelist.

        Imported lazily from the loader rather than duplicated here so the two
        cannot drift apart. Imported at call time because the loader pulls in
        the full settings model graph at import time.
        """
        from tradebot_sci.config.loader import _REAL_PROFILE_KEYS
        return _REAL_PROFILE_KEYS

    def _screen_profile_updates(self, name: str, updates: dict) -> dict:
        """Return only the profile keys an AI-supplied payload is allowed to set.

        Applied to create as well as modify. A profile holding any key outside
        the loader's whitelist makes load_settings() raise a fatal error, which
        stops the bot from starting until a human edits config.json by hand.
        """
        allowed = self._allowed_profile_keys()
        screened = {}
        for key, val in (updates or {}).items():
            if not isinstance(key, str):
                logger.warning(f"[Sentinel] BLOCKED: non-string profile key {key!r} on profile '{name}'.")
                continue
            if key in self._PROFILE_MODIFY_BLOCKLIST:
                logger.warning(f"[Sentinel] BLOCKED: AI attempted to modify '{key}' on profile '{name}' — this key is architecturally protected.")
                continue
            if key not in allowed:
                logger.warning(
                    f"[Sentinel] BLOCKED: '{key}' is not a valid profile key on profile '{name}'. "
                    f"Allowed keys are: {sorted(allowed)}."
                )
                continue
            screened[key] = val
        return screened

    def _modify_profile(self, name: str, updates: dict):
        """Patch fields on an existing profile in config.json (authoritative source)."""
        config = self._read_config_for_write()
        if config is None:
            logger.error(f"[Sentinel] Aborting modification of profile '{name}': config.json is unreadable.")
            return False
        profiles = config.get("profiles", {})
        if name not in profiles or not isinstance(profiles[name], dict):
            logger.warning(f"[Sentinel] Cannot modify profile '{name}' — not found in config.json.")
            return False
        # Strip blocked and non-whitelisted keys before applying
        updates = self._screen_profile_updates(name, updates)
        if not updates:
            logger.info(f"[Sentinel] All requested profile modifications for '{name}' were blocked.")
            return False
        profiles[name] = dict(profiles[name])
        for key, val in updates.items():
            if key == "strategies" and isinstance(val, dict):
                existing = profiles[name].get("strategies")
                merged = dict(existing) if isinstance(existing, dict) else {}
                merged.update(val)
                profiles[name]["strategies"] = merged
            else:
                profiles[name][key] = val
        config["profiles"] = profiles
        if not self._write_config(config):
            logger.error(f"[Sentinel] Failed to write profile '{name}' to config.json.")
            return False
        # Mirror to YAML for backwards compatibility
        try:
            yaml_profiles = self._read_profiles()
            if name in yaml_profiles:
                yaml_profiles[name].update(updates)
                self._write_profiles(yaml_profiles)
        except Exception:
            pass
        self.memory.record_action("PROFILE_MODIFY", {"profile": name, "updates": updates})
        logger.info(f"[Sentinel] Modified profile '{name}' in config.json: {list(updates.keys())}")
        return True

    def _create_profile(self, name: str, new_config: dict):
        """Create a new profile entry in config.json (authoritative source)."""
        config = self._read_config_for_write()
        if config is None:
            logger.error(f"[Sentinel] Aborting creation of profile '{name}': config.json is unreadable.")
            return False
        profiles = config.get("profiles", {})
        if name in profiles:
            logger.warning(f"[Sentinel] Profile '{name}' already exists in config.json — skipping create.")
            return False
        # Merge with sensible defaults. Every key here is inside the loader's
        # profile whitelist — a default outside it would make load_settings()
        # reject the whole config.
        defaults = {
            "strategy_variant": "meta_sci",
            "htf_timeframe": "1h",
            "ltf_timeframe": "5m",
            "symbols": [],
            "strategies": {},
        }
        defaults.update(self._screen_profile_updates(name, new_config))
        profiles[name] = defaults
        config["profiles"] = profiles
        if not self._write_config(config):
            logger.error(f"[Sentinel] Failed to write profile '{name}' to config.json.")
            return False
        # Mirror to YAML for backwards compatibility
        try:
            yaml_profiles = self._read_profiles()
            yaml_profiles[name] = defaults.copy()
            self._write_profiles(yaml_profiles)
        except Exception:
            pass
        self.memory.record_action("PROFILE_CREATE", {"profile": name, "config": defaults})
        logger.info(f"[Sentinel] Created profile '{name}' in config.json")
        return True

    # ── Config I/O (for schedule management) ────────────────────────────────

    def _read_config(self) -> dict:
        """Read config.json for read-only consumers.

        Degrades to an empty mapping when the file is missing or unreadable,
        which is safe for callers that only build a status report.
        Read-modify-write cycles must use _read_config_for_write() instead.
        """
        data = self._read_config_for_write()
        return {} if data is None else data

    def _read_config_for_write(self):
        """Read config.json for a read-modify-write cycle.

        Returns an empty dict when the file does not exist — creating it is
        then the correct outcome. Returns None when the file exists but could
        not be parsed or does not contain a JSON object.

        Callers MUST abort the mutation on None. Falling back to an empty
        dict here would let a transient parse failure replace the whole file
        with a stub containing only the adjusted section, destroying
        everything the mutation did not touch (API keys, brokers, profiles,
        schedule).
        """
        if not CONFIG_FILE.exists():
            return {}
        try:
            with open(CONFIG_FILE, 'r', encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(
                f"[Sentinel] Refusing to modify config: {CONFIG_FILE} could not be parsed ({e}). "
                "No changes were written."
            )
            return None
        if not isinstance(data, dict):
            logger.error(
                f"[Sentinel] Refusing to modify config: {CONFIG_FILE} does not contain a JSON object "
                f"(found {type(data).__name__}). No changes were written."
            )
            return None
        return data

    def _write_config(self, config: dict) -> bool:
        """Write config.json atomically. Returns True when the write succeeded.

        The new content goes to a temporary file in the same directory and is
        then moved over the target with os.replace, so a serialisation or I/O
        failure leaves the previous config untouched instead of a truncated
        file. Opening the real path with 'w' truncates it before json.dump
        runs, which is exactly the failure this avoids.
        """
        if not isinstance(config, dict):
            logger.error(
                f"[Sentinel] Refusing to write config: expected a dict, got {type(config).__name__}."
            )
            return False
        tmp_file = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_file, 'w', encoding="utf-8") as f:
                json.dump(config, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, CONFIG_FILE)
            logger.info("[Sentinel] config.json saved.")
            return True
        except Exception as e:
            logger.error(f"[Sentinel] Failed to write config: {e}")
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except Exception:
                pass
            return False

    # ── Sabbath Awareness ───────────────────────────────────────────────────

    def _get_sabbath_status(self, config: dict) -> dict:
        """Evaluate current Sabbath state from config."""
        try:
            # Sabbath settings live in the `safety` section of config.json;
            # `schedule` and `global` are only legacy fallbacks. Reading the
            # wrong section made every caller see sabbath_active=False while
            # the trading loop was actually observing Sabbath.
            def _section(name: str) -> dict:
                value = config.get(name, {})
                return value if isinstance(value, dict) else {}

            safety_cfg = _section("safety")
            schedule_cfg = _section("schedule")
            global_cfg = _section("global")

            def _lookup(key: str, default):
                for source in (safety_cfg, schedule_cfg, global_cfg):
                    if key in source:
                        return source[key]
                return default

            # Build a minimal profile-like object for SabbathContext
            class _SabbathProfile:
                sabbath_enabled = _lookup("sabbath_enabled", False)
                sabbath_astronomical = _lookup("sabbath_astronomical", False)
                sabbath_timezone = _lookup("sabbath_timezone", "America/New_York")
                sabbath_start_local = _lookup("sabbath_start_local", "18:00")
                sabbath_end_local = _lookup("sabbath_end_local", "18:00")
                sabbath_lat = _lookup("sabbath_lat", None)
                sabbath_lon = _lookup("sabbath_lon", None)

            from datetime import timezone
            ctx = SabbathContext(_SabbathProfile())
            active, start, end = ctx.evaluate(datetime.now(timezone.utc))
            return {
                "enabled": _SabbathProfile.sabbath_enabled,
                "active": active,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "timezone": _SabbathProfile.sabbath_timezone,
                "astronomical": _SabbathProfile.sabbath_astronomical,
            }
        except Exception as e:
            logger.warning(f"[Sentinel] Sabbath status check failed: {e}")
            return {"enabled": False, "active": False, "error": str(e)}

    # ── Commentary Broadcast ────────────────────────────────────────────────

    def _broadcast_change_commentary(self, explanation: str):
        """Push a detailed change explanation to the GUI commentary feed."""
        if not explanation or not explanation.strip():
            return
        if self.ws_server and hasattr(self.ws_server, 'broadcast_commentary_sync'):
            timestamp = datetime.now().strftime("%I:%M %p")
            self.ws_server.broadcast_commentary_sync(
                explanation.strip(),
                timestamp,
                next_update_in=self.interval_mins * 60,
            )
            logger.info("[Sentinel] Commentary broadcast to GUI.")
        else:
            logger.info(f"[Sentinel] Commentary (no WS): {explanation[:200]}")

    def _broadcast_initial_briefing(self):
        """Fire the startup 'battle plan' to the Insight panel when Autopilot activates."""
        try:
            state_payload = self._build_system_state_payload()

            briefing_prompt = (
                f"You are the '{self.personality}' 20-year veteran autonomous trading manager.\n"
                "You have JUST been activated as the Autopilot for this trading bot.\n"
                "The user is watching the AI Insight panel and wants to see your INITIAL BATTLE PLAN.\n\n"
                "Write a detailed, confident opening briefing that covers:\n"
                "1. Your first impression of the current account state (capital, recent P&L)\n"
                "2. What profiles and symbols are active, and your initial read on them\n"
                "3. Current market conditions based on the news feed\n"
                "4. Your strategic plan for the next few hours \u2014 what you're watching for\n"
                "5. Any immediate concerns or adjustments you're considering\n"
                "6. Your check-in interval and how you'll communicate going forward\n\n"
                f"Monetary path goal: {self.monetary_path}\n"
                f"Your check-in interval: every {self.interval_mins} minutes\n\n"
                "Write this as a confident, professional briefing. 2-4 paragraphs. "
                "Speak directly to the user. Be specific about numbers and symbols. "
                "Do NOT return JSON \u2014 just write the briefing text."
            )

            messages = [
                {"role": "system", "content": briefing_prompt},
                {"role": "user", "content": state_payload}
            ]

            logger.info("[Sentinel] Generating initial battle plan briefing...")
            briefing = self.ai.generate_text(messages)
            if briefing and briefing.strip():
                full_briefing = f"\ud83e\udd16 AUTOPILOT ACTIVATED\n\n{briefing.strip()}"
                self._broadcast_change_commentary(full_briefing)
                self.memory.add_note(f"[BRIEFING] Initial battle plan delivered to user.")
                logger.info("[Sentinel] Initial briefing broadcast successfully.")
            else:
                raise ValueError("AI returned empty briefing")
        except Exception as e:
            logger.error(f"[Sentinel] Initial briefing generation failed: {e}", exc_info=True)
            # Fallback: broadcast a simple activation message
            fallback = (
                f"\ud83e\udd16 AUTOPILOT ACTIVATED\n\n"
                f"The 20-year veteran AI is now managing your bot. "
                f"Monetary path: {self.monetary_path}. "
                f"Checking in every {self.interval_mins} minutes. "
                f"First full analysis incoming shortly..."
            )
            self._broadcast_change_commentary(fallback)

    # ── System State Payload Builder ────────────────────────────────────────

    @staticmethod
    def _ledger_trade_entries(ldata) -> list:
        """Flatten a ledger file into a list of closed-trade dicts.

        The SCI 2.0 ledger keeps trades under days[].trade_log, with the day in
        progress under current_day.trade_log. Reading a top-level "trades" or
        "history" key (neither of which exists in that schema) always yielded an
        empty list, so the prompt reported "0 Wins / 0 Losses | Net PnL: $0.00"
        no matter what the bot had actually done. Top-level list/trades/history
        shapes are still accepted for older ledgers.
        """
        if isinstance(ldata, list):
            return [t for t in ldata if isinstance(t, dict)]
        if not isinstance(ldata, dict):
            return []

        entries = []
        days = ldata.get("days")
        for day in [ldata.get("current_day")] + (list(days) if isinstance(days, list) else []):
            if not isinstance(day, dict):
                continue
            trade_log = day.get("trade_log")
            if isinstance(trade_log, list):
                entries.extend(t for t in trade_log if isinstance(t, dict))
        if entries:
            return entries

        for legacy_key in ("trades", "history", "closed_trades"):
            legacy = ldata.get(legacy_key)
            if isinstance(legacy, list):
                return [t for t in legacy if isinstance(t, dict)]
        return entries

    def _summarise_24h_performance(self, ledger_file) -> tuple:
        """Return (wins, losses, net_pnl) over trades closed in the last 24h.

        Never raises: a missing, empty or malformed ledger reports a flat zero,
        and a bad timestamp or PnL skips only the entry it belongs to.
        """
        try:
            if not ledger_file.exists():
                return 0, 0, 0.0
            with open(ledger_file, 'r', encoding="utf-8") as f:
                ldata = json.load(f)
        except Exception as e:
            logger.warning(f"[Sentinel] Failed to read ledger {ledger_file}: {e}")
            return 0, 0, 0.0

        wins, losses, pnl_24h = 0, 0, 0.0
        for trade in self._ledger_trade_entries(ldata):
            stamp = trade.get("closed_at") or trade.get("exit_time") or trade.get("time")
            if not stamp:
                continue
            try:
                closed_at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            # Compare like with like: a tz-aware timestamp needs a tz-aware "now".
            reference = datetime.now(closed_at.tzinfo) if closed_at.tzinfo else datetime.now()
            if reference - closed_at > timedelta(hours=24):
                continue
            try:
                pnl = float(trade.get("pnl", 0) or 0)
            except (TypeError, ValueError):
                continue
            pnl_24h += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1
        return wins, losses, pnl_24h

    def _build_system_state_payload(self) -> str:
        """Aggregates all bot state, profiles, Sabbath, schedule, and tooltips into one context block."""
        from tradebot_sci.paths import DATA_DIR
        
        config = self._read_config()
            
        active_prof = config.get("active_profile", "default")
        prof_settings = config.get("profiles", {}).get(active_prof, {})
        
        execute_trades = config.get("global", {}).get("execute_trades", config.get("runtime", {}).get("execute_trades", False))
        trading_mode = "LIVE" if execute_trades else "PAPER TRADING"

        # ── Read capital from correct runtime state store ──
        state_file = DATA_DIR / "state.json" if execute_trades else DATA_DIR / "paper_state.json"
        state_data = {}
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
            except Exception: pass

        current_capital = state_data.get("balance", state_data.get("capital", None))

        # ── Read trade history from correct ledger ──
        ledger_file = DATA_DIR / "ledger.json" if execute_trades else DATA_DIR / "paper_ledger.json"
        
        # Fallback to secondary check if state file lacked balance
        if current_capital is None and ledger_file.exists():
            try:
                with open(ledger_file, 'r') as f:
                    ledger_data = json.load(f)
                if isinstance(ledger_data, dict):
                    current_capital = ledger_data.get("balance", ledger_data.get("equity", None))
                    # Check new SCI 2.0 ledger schema
                    if current_capital is None:
                        c_day = ledger_data.get("current_day", {})
                        if isinstance(c_day, dict):
                            current_capital = c_day.get("capital_now", c_day.get("capital_at_start", None))
            except Exception: pass

        if current_capital is None:
            current_capital = 0.0

        now = datetime.now()
        wins, losses, pnl_24h = self._summarise_24h_performance(ledger_file)

        # Prop-firm evaluation parameters live in the `risk` section; the
        # active profile is a plain dict, so reading them off it always
        # produced 0.0 and made the prop-firm branch unreachable.
        risk_cfg = config.get("risk", {})
        if not isinstance(risk_cfg, dict):
            risk_cfg = {}

        def _float_or_zero(value) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        prop_tier = _float_or_zero(risk_cfg.get("prop_challenge_tier_usd", 0.0))
        prop_max_loss = _float_or_zero(risk_cfg.get("prop_challenge_max_loss_pct", 0.0))
        
        if trading_mode == "PAPER TRADING" and prop_tier > 0:
            target = 8.0  # Generic default target, prop-specific if available
            daily = 5.0
            maxx = prop_max_loss * 100 if prop_max_loss > 0 else 10.0
            trading_mode = f"PAPER TRADING (PROP FIRM EVALUATION) | Tier: ${prop_tier:,.2f} | Target: +{target}% | Limit: -{maxx}%"

        # Strategy: read from profile (lowercase keys)
        strategy_variant = prof_settings.get("strategy_variant", "unknown")
        strategies_map = prof_settings.get("strategies", {})
        strategy_summary = strategy_variant
        if strategies_map:
            strategy_parts = [f"{asset}={strat}" for asset, strat in strategies_map.items() if strat]
            if strategy_parts:
                strategy_summary = ", ".join(strategy_parts)

        # Risk: read from profile (lowercase keys)
        risk_pct = prof_settings.get("risk_per_trade_pct",
                   config.get("global", {}).get("risk_per_trade_pct",
                   config.get("risk", {}).get("risk_per_trade_pct", "Unknown")))

        # Symbols
        symbols = prof_settings.get("symbols") or []

        lines = [
            "=== SYSTEM STATUS REPORT ===",
            f"Timestamp: {now.isoformat()}",
            f"Trading Mode: {trading_mode}",
            f"Active Profile: {active_prof}",
            f"Monetary Path Goal: {self.monetary_path}",
            f"Current Capital: ${current_capital:.2f}",
            f"24h Performance: {wins} Wins / {losses} Losses | Net PnL: ${pnl_24h:.2f}",
            f"Strategies: {strategy_summary}",
            f"Active Symbols: {', '.join(symbols[:12]) if symbols else 'None configured'}",
            f"Risk Per Trade: {risk_pct}",
        ]

        # ── Broker / Exchange Availability ──
        # Credentials live in the `brokers` section, one nested sub-dict per
        # venue (brokers.oanda.environment). `broker` is not a key anything
        # writes, so reading it always fell through to the assumed default.
        broker_cfg = config.get("brokers", {})
        if not isinstance(broker_cfg, dict):
            broker_cfg = {}

        def _broker_section(name: str) -> dict:
            value = broker_cfg.get(name, {})
            return value if isinstance(value, dict) else {}

        oanda_cfg = _broker_section("oanda")
        ibkr_cfg = _broker_section("ibkr")
        ccxt_cfg = _broker_section("ccxt")
        gemini_cfg = _broker_section("gemini")

        available_exchanges = []
        if oanda_cfg.get("account_id") or oanda_cfg.get("environment") or broker_cfg.get("oanda_account_id"):
            available_exchanges.append("OANDA (Forex/Metals/Indices)")
        if ibkr_cfg.get("host") or ibkr_cfg.get("port") or broker_cfg.get("ibkr_host") or broker_cfg.get("ibkr_port"):
            available_exchanges.append("IBKR (Stocks/ETFs/Futures/Options)")
        if broker_cfg.get("coinbase_api_key") or gemini_cfg.get("api_key"):
            available_exchanges.append("Coinbase (Crypto)")
        ccxt_exchange = ccxt_cfg.get("exchange") or broker_cfg.get("ccxt_exchange")
        if ccxt_exchange:
            available_exchanges.append(f"CCXT:{ccxt_exchange} (Crypto)")

        # Check secrets file for credentials too (ONLY read key names, never values)
        try:
            from tradebot_sci.paths import USER_DATA_DIR
            _sf = USER_DATA_DIR / ".env.secrets"
            if _sf.exists():
                _secret_keys = set()
                with open(_sf, 'r') as _fh:
                    for _line in _fh:
                        _line = _line.strip()
                        if '=' in _line and not _line.startswith('#'):
                            _secret_keys.add(_line.split('=', 1)[0].strip())
                if 'OANDA_API_KEY' in _secret_keys and 'OANDA (Forex/Metals/Indices)' not in available_exchanges:
                    available_exchanges.append("OANDA (Forex/Metals/Indices)")
                if any('COINBASE' in k for k in _secret_keys) and not any('Crypto' in e for e in available_exchanges):
                    available_exchanges.append("Coinbase (Crypto)")
        except Exception:
            pass

        if not available_exchanges:
            available_exchanges.append("OANDA (Forex/Metals/Indices) — assumed default")

        has_crypto = any('Crypto' in e for e in available_exchanges)
        lines.append(f"Connected Exchanges: {', '.join(available_exchanges)}")
        lines.append(f"Crypto Trading Available: {'YES' if has_crypto else 'NO — do NOT create or activate crypto profiles'}")

        # ── Feature 2: Sabbath Status ──
        sabbath = self._get_sabbath_status(config)
        lines.append("\n=== SABBATH STATUS ===")
        lines.append(f"Sabbath Enabled: {sabbath.get('enabled', False)}")
        lines.append(f"Sabbath Active RIGHT NOW: {sabbath.get('active', False)}")
        if sabbath.get('enabled'):
            lines.append(f"Current Window: {sabbath.get('window_start', '?')} → {sabbath.get('window_end', '?')}")
            lines.append(f"Timezone: {sabbath.get('timezone', '?')}")
            lines.append(f"Astronomical (sunset-based): {sabbath.get('astronomical', False)}")

        # ── Feature 1: Profiles Summary ──
        # Use config.json profiles (authoritative, matches GUI) rather than
        # settings_profiles.yaml which can be stale / out of sync.
        profiles = config.get("profiles", {})
        lines.append("\n=== PROFILES ===")
        lines.append(f"Active Profile: {active_prof}")
        lines.append(f"Total Profiles: {len(profiles)}")
        for pname, pdata in profiles.items():
            if not isinstance(pdata, dict):
                continue
            symbols = pdata.get("symbols") or []
            strat = pdata.get("strategy_variant", "unknown")
            strats_map = pdata.get("strategies", {})
            if strats_map and isinstance(strats_map, dict):
                strat_parts = [f"{a}={s}" for a, s in strats_map.items() if s]
                strat_label = ", ".join(strat_parts) if strat_parts else strat
            else:
                strat_label = strat
            htf = pdata.get("htf_timeframe", "?")
            marker = " (ACTIVE)" if pname == active_prof else ""
            lines.append(f"  - {pname}{marker}: [{', '.join(str(s) for s in symbols[:8])}{'...' if len(symbols) > 8 else ''}] | strategy={strat_label} | HTF={htf}")

        # ── Feature 3: Schedule Sessions ──
        schedule = config.get("schedule", {})
        sessions = schedule.get("sessions", [])
        lines.append("\n=== SCHEDULE SESSIONS ===")
        if sessions:
            for i, sess in enumerate(sessions):
                sname = sess.get("profile_name", "?")
                mode = sess.get("mode", "custom")
                start_t = sess.get("start_time", "?")
                end_t = sess.get("end_time", "?")
                days = sess.get("days_of_week", [])
                lines.append(f"  Session {i+1}: \"{sname}\" {','.join(days) if days else 'all days'} {start_t}-{end_t} ({mode})")
        else:
            lines.append("  No scheduled sessions configured.")

        # ── Feature 4: Settings Reference Guide (Tooltip Dictionary) ──
        lines.append("\n=== SETTINGS REFERENCE GUIDE ===")
        lines.append("Use this to understand what each setting does before changing it:")
        for key, tooltip in SENTINEL_TOOLTIP_REFERENCE.items():
            lines.append(f"  {key}: {tooltip}")
        lines.append("\n--- Profile Field Reference ---")
        for key, tooltip in SENTINEL_PROFILE_REFERENCE.items():
            lines.append(f"  {key}: {tooltip}")

        # ── Feature 5: Live Market Data (Candles, Indicators, Positions) ──
        try:
            market_data = self._build_market_data_payload(config, prof_settings, active_prof)
            if market_data:
                lines.append(market_data)
        except Exception as e:
            lines.append(f"\n=== MARKET DATA ===\n  (Unavailable: {e})")

        # ── Feature 6: Trading Analytics (Win/Loss, Profit Factor, Calendar) ──
        try:
            analytics_data = self._build_analytics_payload()
            if analytics_data:
                lines.append(analytics_data)
        except Exception as e:
            lines.append(f"\n=== ANALYTICS ===\n  (Unavailable: {e})")

        # ── Feature 7: Rejection Journal (Safety Gate Awareness) ──
        try:
            from tradebot_sci.runtime.rejection_journal import rejection_journal
            gate_summary = rejection_journal.get_summary()
            total_rejections = rejection_journal.total_rejections
            if gate_summary:
                lines.append(f"\n=== TRADE REJECTIONS (this session: {total_rejections} total) ===")
                lines.append("Gate breakdown:")
                for gate, count in sorted(gate_summary.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  {gate}: {count} rejections")
                # Show the 10 most recent rejections for context
                recent = rejection_journal.get_recent(10)
                if recent:
                    lines.append("Recent rejections:")
                    for r in recent:
                        lines.append(f"  [{r.timestamp.strftime('%H:%M')}] {r.symbol} — {r.reason}")
                lines.append("⚠️ If ONE gate is blocking ALL trades, it may need to be disabled or investigated.")
        except Exception as e:
            lines.append(f"\n=== REJECTIONS ===\n  (Unavailable: {e})")

        # ── Persistent Memory & News ──
        lines.append("\n" + self.memory.get_contextual_memory())
        lines.append("\n=== GLOBAL NEWS & RSS ===")
        lines.append(self.news_scraper.get_latest_news_context())

        return "\n".join(lines)

    def _build_market_data_payload(self, config: dict, prof_settings: dict, active_prof: str) -> str:
        """
        Fetches live candle data, computes indicators, reads open positions,
        and returns a compact text summary for the AI.
        """
        from tradebot_sci.market.indicators import (
            calculate_ema, calculate_rsi, calculate_sma,
            calculate_macd, calculate_bollinger_bands,
        )

        lines = ["\n=== LIVE MARKET DATA ==="]

        # ── Get active symbols from the profile ──
        symbols = prof_settings.get("symbols") or []
        if not symbols:
            lines.append("  No symbols configured in active profile.")
            return "\n".join(lines)

        # ── Get the LTF/HTF timeframes from the profile ──
        ltf = prof_settings.get("ltf_timeframe", config.get("global", {}).get("ltf_timeframe", "15m"))
        htf = prof_settings.get("htf_timeframe", config.get("global", {}).get("htf_timeframe", "4h"))

        # ── Create market data provider (lazy, from saved credentials) ──
        provider = self._get_market_provider(config)
        if not provider:
            lines.append("  Market data provider unavailable (no OANDA credentials).")
            return "\n".join(lines)

        # ── Open Positions ──
        execute_trades = config.get("global", {}).get(
            "execute_trades", config.get("runtime", {}).get("execute_trades", False)
        )
        positions = self._read_open_positions(execute_trades)
        if positions:
            lines.append("\n--- OPEN POSITIONS ---")
            for pos in positions:
                sym = pos.get("symbol", "?")
                side = pos.get("side", "long").upper()
                entry = pos.get("entry_price", 0)
                sl = pos.get("stop_loss", "None")
                tp = pos.get("take_profit", "None")
                size = pos.get("size", pos.get("units", 0))
                pnl = pos.get("unrealized_pnl", pos.get("pnl", 0))
                entry_time = pos.get("entry_time", "?")
                mfe = pos.get("mfe_usd", 0.0)
                mae = pos.get("mae_usd", 0.0)
                lines.append(
                    f"  {sym} {side} | entry={entry} | SL={sl} | TP={tp} "
                    f"| size={size} | PnL=${pnl} | MFE=${mfe} | MAE=${mae} | opened={entry_time}"
                )
        else:
            lines.append("\n--- OPEN POSITIONS ---\n  No open positions.")

        # ── Per-Symbol Market Analysis (limit to first 8 symbols to manage token usage) ──
        analysis_symbols = symbols[:8]
        lines.append(f"\n--- CHART DATA ({ltf} candles) ---")

        for sym in analysis_symbols:
            try:
                # Fetch 100 candles for indicator computation (show last 10)
                candles = provider.get_latest_candles(str(sym), ltf, limit=100)
                if not candles or len(candles) < 5:
                    lines.append(f"\n  [{sym}] No candle data available.")
                    continue

                closes = [c.close for c in candles]
                highs = [c.high for c in candles]
                lows = [c.low for c in candles]

                # Current price
                current = closes[-1]
                prev_close = closes[-2] if len(closes) > 1 else current
                pct_change = ((current - prev_close) / prev_close * 100) if prev_close else 0

                # Daily range (from fetched candles)
                session_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
                session_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)

                # Indicators
                ema21 = calculate_ema(closes, 21)
                ema50 = calculate_ema(closes, 50)
                sma200 = calculate_sma(closes, 200) if len(closes) >= 200 else calculate_sma(closes, len(closes))
                rsi = calculate_rsi(closes, 14)
                macd_line, signal_line, histogram = calculate_macd(closes, 12, 26, 9)
                bb_lower, bb_middle, bb_upper = calculate_bollinger_bands(closes, 20, 2.0)

                # Price vs EMA positioning
                above_ema21 = "ABOVE" if current > ema21 else "BELOW"
                above_ema50 = "ABOVE" if current > ema50 else "BELOW"
                trend_bias = "BULLISH" if ema21 > ema50 else "BEARISH" if ema50 > ema21 else "NEUTRAL"

                # RSI zone
                if rsi > 70:
                    rsi_zone = "OVERBOUGHT"
                elif rsi < 30:
                    rsi_zone = "OVERSOLD"
                else:
                    rsi_zone = "NEUTRAL"

                # MACD signal
                macd_signal = "BULLISH" if histogram > 0 else "BEARISH"

                # Dynamic decimal precision
                dp = 2 if current > 100 else (4 if current > 1 else 5)

                lines.append(f"\n  [{sym}]")
                lines.append(f"    Price: {current:.{dp}f} ({pct_change:+.2f}%) | Range: {session_low:.{dp}f} - {session_high:.{dp}f}")
                lines.append(f"    EMA 21: {ema21:.{dp}f} ({above_ema21}) | EMA 50: {ema50:.{dp}f} ({above_ema50}) | Trend: {trend_bias}")
                if sma200 > 0:
                    lines.append(f"    SMA 200: {sma200:.{dp}f} ({'ABOVE' if current > sma200 else 'BELOW'})")
                lines.append(f"    RSI(14): {rsi:.1f} ({rsi_zone})")
                lines.append(f"    MACD: {macd_line:.{dp}f} | Signal: {signal_line:.{dp}f} | Hist: {histogram:.{dp}f} ({macd_signal})")
                if bb_upper > 0:
                    bb_pos = "UPPER" if current > bb_middle else "LOWER"
                    lines.append(f"    Bollinger: [{bb_lower:.{dp}f} / {bb_middle:.{dp}f} / {bb_upper:.{dp}f}] Price in {bb_pos} half")

                # Last 10 candles as compact OHLC table
                recent = candles[-10:]
                lines.append(f"    Last {len(recent)} candles (OHLCV):")
                for c in recent:
                    ts = c.timestamp.strftime("%m/%d %H:%M") if hasattr(c.timestamp, 'strftime') else str(c.timestamp)
                    vol = getattr(c, 'volume', 0) or 0
                    lines.append(f"      {ts} | O={c.open:.{dp}f} H={c.high:.{dp}f} L={c.low:.{dp}f} C={c.close:.{dp}f} V={int(vol)}")

                # Bid/Ask spread
                try:
                    ticker = provider.get_ticker(str(sym))
                    if ticker and ticker.bid and ticker.ask:
                        spread_pips = abs(ticker.ask - ticker.bid)
                        lines.append(f"    Bid: {ticker.bid:.{dp}f} | Ask: {ticker.ask:.{dp}f} | Spread: {spread_pips:.{dp}f}")
                except Exception:
                    pass

            except Exception as e:
                lines.append(f"\n  [{sym}] Error fetching data: {e}")

        return "\n".join(lines)

    def _get_market_provider(self, config: dict):
        """Lazily create an OANDA market data provider, or return ReplayProvider from controller."""
        if self.controller and hasattr(self.controller, "replay_provider") and self.controller.replay_provider:
            return self.controller.replay_provider

        # [SILENCE] If live trading is disabled and no replay is active, we return None
        # to prevent polling live OANDA APIs for market data ingestion.
        execute_trades = config.get("runtime", {}).get("execute_trades", False)
        if not execute_trades:
            return None

        if hasattr(self, '_market_provider') and self._market_provider:
            return self._market_provider
        try:
            from tradebot_sci.market.oanda_provider import OandaMarketDataProvider

            # Primary: use os.getenv (populated by load_dotenv in loader.py)
            account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
            api_key = os.environ.get("OANDA_API_KEY", "")

            # Fallback: parse .env.secrets directly if env vars aren't set
            if not account_id or not api_key:
                from tradebot_sci.paths import USER_DATA_DIR
                secrets_file = USER_DATA_DIR / ".env.secrets"
                if secrets_file.exists():
                    with open(secrets_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if '=' in line and not line.startswith('#'):
                                k, v = line.split('=', 1)
                                k, v = k.strip(), v.strip().strip('"').strip("'")
                                if k == "OANDA_ACCOUNT_ID" and not account_id:
                                    account_id = v
                                elif k == "OANDA_API_KEY" and not api_key:
                                    api_key = v

            # The venue settings live under brokers.oanda. Reading the
            # non-existent `broker` key left this empty, and the account-ID
            # prefix guess below then handed a live account whose ID does not
            # start with "001-" a practice data provider.
            oanda_cfg = config.get("brokers", {}).get("oanda", {}) if isinstance(config.get("brokers"), dict) else {}
            if not isinstance(oanda_cfg, dict):
                oanda_cfg = {}
            environment = oanda_cfg.get("environment",
                                    config.get("global", {}).get("oanda_environment", ""))
            # Auto-detect environment from account ID if not set
            if not environment:
                if account_id.startswith("001-"):
                    environment = "live"
                else:
                    environment = "practice"

            if not account_id or not api_key:
                logger.warning("[Sentinel] No OANDA credentials found for market data (checked env + .env.secrets).")
                return None

            self._market_provider = OandaMarketDataProvider(account_id, api_key, environment)
            logger.info(f"[Sentinel] OANDA market data provider created (env={environment})")
            return self._market_provider
        except Exception as e:
            logger.warning(f"[Sentinel] Failed to create market data provider: {e}")
            return None

    def _read_open_positions(self, execute_trades=None) -> list:
        """Read current open positions from the live or paper state store.

        The source has to follow execute_trades, exactly like the capital read
        in _build_system_state_payload: in live mode the paper store holds
        stale simulations and handing them to the model misrepresents the
        account. Prefers the controller's executor snapshot when one is
        available, since that is the state the trading loop is acting on.
        """
        if execute_trades is None:
            config = self._read_config()
            execute_trades = config.get("global", {}).get(
                "execute_trades", config.get("runtime", {}).get("execute_trades", False)
            )

        snapshot_positions = self._read_controller_positions()
        if execute_trades and snapshot_positions is not None:
            return snapshot_positions

        positions = []
        state_file = DATA_DIR / ("state.json" if execute_trades else "paper_state.json")
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding="utf-8") as f:
                    state = json.load(f)
                raw_positions = state.get("positions", {}) if isinstance(state, dict) else {}
                if isinstance(raw_positions, dict):
                    # state stores positions as {symbol: {...}}
                    for sym, pos_data in raw_positions.items():
                        if isinstance(pos_data, dict):
                            pos_data = dict(pos_data)
                            pos_data["symbol"] = sym
                            positions.append(pos_data)
                elif isinstance(raw_positions, list):
                    positions = [p for p in raw_positions if isinstance(p, dict)]
            except Exception as e:
                logger.warning(f"[Sentinel] Failed to read positions from {state_file}: {e}")
        return positions

    def _read_controller_positions(self):
        """Snapshot open positions from the controller's executors, or None.

        Returns None when no executor is reachable so the caller can fall back
        to the state file rather than reporting an empty book.
        """
        if self.controller is None:
            return None
        snapshots = []
        for attr in ("executor_real", "executor", "paper_executor"):
            executor = getattr(self.controller, attr, None)
            if executor is None or not hasattr(executor, "get_open_position_snapshot"):
                continue
            try:
                symbols = []
                if hasattr(executor, "list_open_position_symbols"):
                    symbols = list(executor.list_open_position_symbols() or [])
                if not symbols:
                    holdings = getattr(executor, "positions", None)
                    if isinstance(holdings, dict):
                        symbols = list(holdings.keys())
                for sym in symbols:
                    snap = executor.get_open_position_snapshot(sym)
                    if isinstance(snap, dict):
                        snap = dict(snap)
                        snap.setdefault("symbol", sym)
                        if not snap.get("is_dust", False):
                            snapshots.append(snap)
                return snapshots
            except Exception as e:
                logger.warning(f"[Sentinel] Failed to snapshot positions from {attr}: {e}")
                return None
        return None

    def _build_analytics_payload(self) -> str:
        """
        Reads trade_results.json and computes comprehensive trading analytics:
        win/loss ratio, profit factor, R:R, duration, strategy breakdown, daily calendar.
        """
        lines = ["\n=== TRADING ANALYTICS ==="]

        # Determine paper vs live mode to read the correct results file
        config = self._read_config()
        execute_trades = config.get("runtime", {}).get("execute_trades", False)
        if execute_trades:
            results_file = DATA_DIR / "trade_results.json"
            lines.append("  Mode: LIVE")
        else:
            results_file = DATA_DIR / "paper_trade_results.json"
            lines.append("  Mode: PAPER TRADING")
            # Fallback to live results if paper results don't exist yet
            if not results_file.exists():
                results_file = DATA_DIR / "trade_results.json"
        if not results_file.exists():
            lines.append("  No trade history available.")
            return "\n".join(lines)

        try:
            with open(results_file, 'r') as f:
                raw = json.load(f)
            trades = raw if isinstance(raw, list) else []
        except Exception as e:
            lines.append(f"  Failed to read trade results: {e}")
            return "\n".join(lines)

        if not trades:
            lines.append("  No completed trades yet.")
            return "\n".join(lines)

        # ── Overall Stats ──
        total = len(trades)
        wins = [t for t in trades if t.get("is_win", False)]
        losses = [t for t in trades if not t.get("is_win", False)]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total * 100) if total > 0 else 0

        total_pnl = sum(float(t.get("pnl_usd", 0)) for t in trades)
        avg_pnl = total_pnl / total if total > 0 else 0

        # Profit factor = gross profit / gross loss
        gross_profit = sum(float(t.get("pnl_usd", 0)) for t in wins) if wins else 0
        gross_loss = abs(sum(float(t.get("pnl_usd", 0)) for t in losses)) if losses else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # Average risk/reward (avg win / avg loss)
        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss_amt = (gross_loss / loss_count) if loss_count > 0 else 0
        avg_rr = (avg_win / avg_loss_amt) if avg_loss_amt > 0 else 0

        # Average trade duration
        durations = [float(t["duration_seconds"]) for t in trades if t.get("duration_seconds") is not None]
        avg_duration_mins = (sum(durations) / len(durations) / 60) if durations else 0

        # Best / worst trade
        best = max(trades, key=lambda t: float(t.get("pnl_usd", 0)))
        worst = min(trades, key=lambda t: float(t.get("pnl_usd", 0)))

        lines.append(f"\n--- OVERALL PERFORMANCE ({total} trades) ---")
        lines.append(f"  Win/Loss: {win_count}W / {loss_count}L ({win_rate:.1f}% win rate)")
        lines.append(f"  Total PnL: ${total_pnl:.2f} | Avg PnL/Trade: ${avg_pnl:.2f}")
        lines.append(f"  Profit Factor: {profit_factor:.2f}")
        lines.append(f"  Avg Win: ${avg_win:.2f} | Avg Loss: -${avg_loss_amt:.2f} | Avg R:R: {avg_rr:.2f}")
        lines.append(f"  Avg Trade Duration: {avg_duration_mins:.1f} min")
        lines.append(f"  Best Trade: {best.get('symbol','?')} ${float(best.get('pnl_usd',0)):+.2f}")
        lines.append(f"  Worst Trade: {worst.get('symbol','?')} ${float(worst.get('pnl_usd',0)):+.2f}")

        # ── MFE/MAE Analysis ──
        mfes = [float(t.get("mfe_usd", 0)) for t in trades if t.get("mfe_usd") is not None]
        maes = [float(t.get("mae_usd", 0)) for t in trades if t.get("mae_usd") is not None]
        
        if mfes:
            avg_mfe = sum(mfes) / len(mfes)
            avg_mae = sum(maes) / len(maes) if maes else 0
            mfe_mae_ratio = abs(avg_mfe / avg_mae) if avg_mae != 0 else avg_mfe
            
            # Analyze "Left on Table" (MFE vs final PnL for winners)
            winner_mfes = [float(t.get("mfe_usd", 0)) for t in wins if t.get("mfe_usd") is not None]
            winner_pnls = [float(t.get("pnl_usd", 0)) for t in wins]
            avg_winner_giveback = 0.0
            if winner_mfes:
                givebacks = [(m - p) for m, p in zip(winner_mfes, winner_pnls) if m > 0]
                avg_winner_giveback = sum(givebacks) / len(givebacks) if givebacks else 0

            lines.append("\n--- EXCURSION ANALYSIS (MFE/MAE) ---")
            lines.append(f"  Avg MFE (Peak Profit): ${avg_mfe:.2f}")
            lines.append(f"  Avg MAE (Peak Drawdown): ${avg_mae:.2f}")
            lines.append(f"  MFE/MAE Ratio: {mfe_mae_ratio:.2f}")
            lines.append(f"  Avg Winner Giveback: ${avg_winner_giveback:.2f} (Profit left on table)")
            lines.append("  💡 Insight: If Avg Winner Giveback is high, consider tightening TP or Trailing Stop.")
            lines.append("  💡 Insight: If MAE is consistently near SL before winning, consider wider SL or later entry.")

        # ── Timeframe Breakdown ──
        now = datetime.now()
        def _filter_trades(delta_hours):
            cutoff = now - timedelta(hours=delta_hours)
            filtered = []
            for t in trades:
                ct = t.get("closed_at", t.get("exit_time", ""))
                if ct:
                    try:
                        dt = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
                        if dt.replace(tzinfo=None) >= cutoff:
                            filtered.append(t)
                    except Exception:
                        continue
            return filtered

        lines.append("\n--- TIMEFRAME BREAKDOWN ---")
        for label, hours in [("24h", 24), ("7d", 168), ("30d", 720)]:
            subset = _filter_trades(hours)
            if subset:
                w = sum(1 for t in subset if t.get("is_win", False))
                l = len(subset) - w
                pnl = sum(float(t.get("pnl_usd", 0)) for t in subset)
                wr = (w / len(subset) * 100) if subset else 0
                lines.append(f"  {label}: {len(subset)} trades | {w}W/{l}L ({wr:.0f}%) | PnL: ${pnl:+.2f}")
            else:
                lines.append(f"  {label}: No trades")

        # ── Per-Strategy Breakdown ──
        strat_stats = {}
        for t in trades:
            strat = t.get("strategy", t.get("strategy_name", "unknown")) or "unknown"
            if strat not in strat_stats:
                strat_stats[strat] = {"wins": 0, "losses": 0, "pnl": 0.0}
            if t.get("is_win", False):
                strat_stats[strat]["wins"] += 1
            else:
                strat_stats[strat]["losses"] += 1
            strat_stats[strat]["pnl"] += float(t.get("pnl_usd", 0))

        if strat_stats:
            lines.append("\n--- BY STRATEGY ---")
            for strat, s in sorted(strat_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
                st = s["wins"] + s["losses"]
                wr = (s["wins"] / st * 100) if st > 0 else 0
                lines.append(f"  {strat}: {st} trades | {s['wins']}W/{s['losses']}L ({wr:.0f}%) | PnL: ${s['pnl']:+.2f}")

        # ── Daily Performance Calendar (last 14 days) ──
        daily = {}
        for t in trades:
            ct = t.get("closed_at", t.get("exit_time", ""))
            if ct:
                try:
                    dt = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
                    day_key = dt.strftime("%Y-%m-%d")
                    if day_key not in daily:
                        daily[day_key] = {"trades": 0, "wins": 0, "pnl": 0.0}
                    daily[day_key]["trades"] += 1
                    daily[day_key]["pnl"] += float(t.get("pnl_usd", 0))
                    if t.get("is_win", False):
                        daily[day_key]["wins"] += 1
                except Exception:
                    continue

        if daily:
            lines.append("\n--- DAILY PERFORMANCE CALENDAR ---")
            # Show last 14 days only
            sorted_days = sorted(daily.keys(), reverse=True)[:14]
            for day in sorted_days:
                d = daily[day]
                wr = (d["wins"] / d["trades"] * 100) if d["trades"] > 0 else 0
                emoji = "🟢" if d["pnl"] > 0 else "🔴" if d["pnl"] < 0 else "⚪"
                lines.append(f"  {emoji} {day}: {d['trades']} trades | {d['wins']}W ({wr:.0f}%) | ${d['pnl']:+.2f}")

        return "\n".join(lines)

    # ── SETTINGS ADJUSTMENT GUARD ───────────────────────────────────────────
    # Keys the AI must never write, whatever section they map to.
    # NUCLEAR_OVERRIDES_ENABLED together with MAX_RISK_CAP_OVERRIDE is the
    # dangerous pair: strategy/safety_guard.py raises the per-trade risk cap to
    # whatever MAX_RISK_CAP_OVERRIDE says once Nuclear Mode is on, so both keys
    # being writable puts 100% of the account on a single trade.
    _SETTINGS_HARD_DENYLIST = {
        "nuclear_overrides_enabled",
        "max_risk_cap_override",
        "execute_trades",
    }
    # Sections whose *_enabled toggles turn a safety mechanism off.
    _SAFETY_GATED_SECTIONS = {"safety", "risk"}

    def _settings_section_classes(self) -> list:
        """(model class, config section) pairs used to map and validate keys."""
        from tradebot_sci.config.models import (
            Settings, RiskSettings, SafetySettings,
            PerformanceSettings, TradingProfileSettings,
            RuntimeSettings, AppSettings
        )
        # Ordered most general to most specific so that a field name appearing
        # in more than one model resolves to the most specific section.
        return [
            (Settings, "global"),
            (TradingProfileSettings, "global"),
            (AppSettings, "global"),
            (RuntimeSettings, "runtime"),
            (PerformanceSettings, "performance"),
            (SafetySettings, "safety"),
            (RiskSettings, "risk"),
        ]

    def _build_settings_section_map(self) -> dict:
        """Map UPPER_CASE setting name -> (section, field_name, model class)."""
        section_map = {}
        for cls, section_name in self._settings_section_classes():
            for field_name in cls.model_fields.keys():
                section_map[field_name.upper()] = (section_name, field_name, cls)
        return section_map

    @classmethod
    def _settings_key_denied_reason(cls, section: str, field: str):
        """Return why this section/field pair may not be written, or None."""
        if field in cls._SETTINGS_HARD_DENYLIST:
            return "this key is safety-critical and may never be changed by the AI"
        if field.startswith("safety_"):
            return "safety_* keys are safety-critical and may never be changed by the AI"
        if field.endswith("_enabled") and section in cls._SAFETY_GATED_SECTIONS:
            return (
                f"'{field}' is an enable/disable flag in the {section} section "
                "and may never be changed by the AI"
            )
        return None

    @staticmethod
    def _coerce_adjustment_value(val):
        """Coerce an AI-supplied scalar to bool/number, leaving anything else alone."""
        if isinstance(val, str):
            if val.lower() in ("true", "false"):
                return val.lower() == "true"
            try:
                number = float(val)
            except ValueError:
                return val
            return int(number) if number == int(number) else number
        return val

    def _screen_settings_adjustments(self, adjustments: dict) -> tuple:
        """Map, screen and type-coerce AI-supplied settings keys.

        Returns (candidates, rejected) where candidates maps the UPPER_CASE key
        to (section, field, model class, coerced value) and rejected is a list of
        {"key", "reason"} for everything refused.
        """
        section_map = self._build_settings_section_map()
        candidates = {}
        rejected = []
        for key, val in adjustments.items():
            if not isinstance(key, str) or not key.strip():
                rejected.append({"key": str(key), "reason": "setting name must be a non-empty string"})
                continue
            # Look the key up case-insensitively: the map is keyed by the model's
            # upper-cased field name, and a lowercase key was previously dropped.
            lookup = key.strip().upper()
            mapping = section_map.get(lookup)
            if mapping is None:
                logger.warning(f"[Sentinel] No config mapping for key '{key}' — skipping.")
                rejected.append({"key": key, "reason": "no such setting"})
                continue
            section, field, cls = mapping
            denied = self._settings_key_denied_reason(section, field)
            if denied:
                logger.warning(f"[Sentinel] REFUSED: AI attempted to change '{key}' — {denied}.")
                rejected.append({"key": key, "reason": denied})
                continue
            candidates[lookup] = (section, field, cls, self._coerce_adjustment_value(val))
        return candidates, rejected

    def _build_candidate_models(self, candidates: dict, config: dict = None) -> tuple:
        """Construct the Pydantic section models for a proposed change set.

        Returns (models, reason). models maps the section model class to the
        instance built from the proposal, and reason names the first failure.
        Construction is what enforces the declared field bounds (for example
        RiskSettings.risk_per_trade_pct is Ge(0.0) Le(1.0)), so a value outside
        its bounds surfaces here as a ValidationError rather than in the config.
        """
        by_class = {}
        for section, field, cls, value in candidates.values():
            by_class.setdefault(cls, {})[field] = value
        # Existing values are folded in as the base so cross-field invariants
        # are checked against the real configuration. If the stored section
        # itself cannot be constructed, the proposal is validated on its own —
        # the proposed values are checked against the model either way.
        stored_by_class = {}
        if isinstance(config, dict):
            for section, _field, cls, _value in candidates.values():
                section_data = config.get(section)
                if not isinstance(section_data, dict):
                    continue
                stored_by_class.setdefault(cls, {}).update(
                    {k: v for k, v in section_data.items() if k in cls.model_fields}
                )
        models = {}
        reason = None
        for cls, fields in by_class.items():
            merged = dict(stored_by_class.get(cls, {}))
            merged.update(fields)
            try:
                models[cls] = cls(**merged)
                continue
            except Exception as e:
                reason = f"invalid value(s) for {sorted(fields)}: {e}"
            try:
                models[cls] = cls(**fields)
                reason = None
            except Exception as e:
                reason = f"invalid value(s) for {sorted(fields)}: {e}"
                break
        return models, reason

    def _check_risk_invariants(self, models: dict):
        """Return a reason string when the candidate breaks a risk invariant.

        Only checks that a single field's own bounds cannot express: the field
        level type/range validation already ran during model construction.
        """
        from tradebot_sci.config.models import RiskSettings, SafetySettings

        risk = models.get(RiskSettings)
        if risk is not None:
            if getattr(risk, "nuclear_overrides_enabled", False):
                return "nuclear_overrides_enabled cannot be enabled"
            risk_pct = float(getattr(risk, "risk_per_trade_pct", 0.0) or 0.0)
            exposure_cap = float(getattr(risk, "max_exposure_pct", 0.0) or 0.0)
            if exposure_cap > 0 and risk_pct > exposure_cap:
                return (
                    f"risk_per_trade_pct {risk_pct} exceeds the portfolio "
                    f"max_exposure_pct {exposure_cap}"
                )
            daily_cap = float(getattr(risk, "limit_loss_daily_pct", 0.0) or 0.0)
            if daily_cap > 0 and risk_pct > daily_cap:
                return (
                    f"risk_per_trade_pct {risk_pct} exceeds the daily loss "
                    f"limit {daily_cap}"
                )

        safety = models.get(SafetySettings)
        if safety is not None:
            if float(getattr(safety, "emergency_stop_pct", 0.0) or 0.0) <= 0.0:
                return "emergency_stop_pct must be greater than zero"
        return None

    def _execute_synthetic_preflight(self, proposed_changes: dict) -> bool:
        """
        Requirement 8.2: Synthetic Pre-Flight Tests
        Validates a proposed settings change before anything is written.

        This is a cheap structural check, not a simulation: the keys are run
        through the adjustment guard, the candidate values are built into their
        real Pydantic section models (which enforces the declared field bounds),
        and the risk-critical invariants that no single field's bounds can
        express are verified. Returns False with a logged reason when the
        candidate is not structurally safe.
        """
        if not isinstance(proposed_changes, dict) or not proposed_changes:
            return True

        logger.info("[Sentinel] Executing Synthetic Pre-Flight Test on proposed config.")
        candidates, rejected = self._screen_settings_adjustments(proposed_changes)
        if rejected:
            blockers = "; ".join(f"{r['key']} ({r['reason']})" for r in rejected)
            logger.warning(f"[Sentinel] Synthetic Pre-Flight failed: {blockers}")
            return False
        if not candidates:
            logger.warning("[Sentinel] Synthetic Pre-Flight failed: no valid setting to apply.")
            return False

        models, reason = self._build_candidate_models(candidates)
        if reason is None:
            reason = self._check_risk_invariants(models)
        if reason:
            logger.warning(f"[Sentinel] Synthetic Pre-Flight failed: {reason}")
            return False

        logger.info("[Sentinel] Synthetic Pre-Flight passed safely.")
        return True

    @staticmethod
    def _describe_settings_outcome(applied: dict, rejected: list, explanation: str) -> str:
        """Describe a settings change using what was actually written."""
        lines = []
        if applied:
            lines.append("Applied settings: " + ", ".join(f"{k}={applied[k]}" for k in sorted(applied)))
        else:
            lines.append("No settings were changed.")
        if rejected:
            lines.append("Refused: " + "; ".join(f"{r['key']} ({r['reason']})" for r in rejected))
        if explanation and explanation.strip():
            # Never present the model's claim of a change as fact when part or
            # all of it was refused.
            if rejected:
                lines.append(f"Model's stated intent (not applied as written): {explanation.strip()}")
            else:
                lines.append(explanation.strip())
        return "\n".join(lines)

    def _apply_schedule_actions(self, cfg: dict, schedule_actions: list):
        """Apply AI schedule actions to an already-read config dict and save it."""
        if not isinstance(cfg.get("schedule"), dict):
            cfg["schedule"] = {}
        if not isinstance(cfg["schedule"].get("sessions"), list):
            cfg["schedule"]["sessions"] = []

        schedule_changed = False
        for action in schedule_actions:
            if not isinstance(action, dict):
                continue
            act_type = action.get("action", "")
            if act_type == "create_session":
                new_session = {
                    "profile_name": action.get("profile_name", "default"),
                    "start_time": action.get("start_time", "09:00"),
                    "end_time": action.get("end_time", "17:00"),
                    "days_of_week": action.get("days_of_week", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
                    "mode": action.get("mode", "custom"),
                    "weeks_of_month": action.get("weeks_of_month", [1, 2, 3, 4, 5]),
                    "paper_trade_off_hours": action.get("paper_trade_off_hours", False),
                }
                cfg["schedule"]["sessions"].append(new_session)
                schedule_changed = True
                self.memory.record_action("SCHEDULE_CREATE", new_session)
                logger.info(f"[Sentinel] Created schedule session for '{new_session['profile_name']}'")
            elif act_type == "delete_session":
                # Coerce the index rather than trusting its type: a string index
                # made the range comparison raise TypeError, which aborted the
                # whole cycle after earlier mutations had already been applied.
                raw_index = action.get("index", None)
                if raw_index is None or isinstance(raw_index, bool):
                    logger.warning(f"[Sentinel] Ignoring delete_session with invalid index {raw_index!r}.")
                    continue
                try:
                    idx = int(raw_index)
                except (TypeError, ValueError):
                    logger.warning(f"[Sentinel] Ignoring delete_session with non-integer index {raw_index!r}.")
                    continue
                if 0 <= idx < len(cfg["schedule"]["sessions"]):
                    removed = cfg["schedule"]["sessions"].pop(idx)
                    schedule_changed = True
                    self.memory.record_action("SCHEDULE_DELETE", {"index": idx, "removed": removed})
                    logger.info(f"[Sentinel] Deleted schedule session at index {idx}")

        if schedule_changed:
            self._write_config(cfg)

    def _engage_kill_switch(self, reason: str) -> bool:
        """Halt trading via the controller. Returns True when the halt took effect.

        controller.is_halted() reads ws_server._halted and is what the trading
        loop consults, so the kill switch has to go through the controller.
        Logging and broadcasting alone left the bot trading while the operator
        was told it had stopped.
        """
        if self.controller is None or not hasattr(self.controller, "halt"):
            logger.error("[Sentinel] Kill switch requested but no halt mechanism is reachable.")
            return False
        try:
            self.controller.halt(f"AI kill switch: {str(reason)[:200]}")
        except Exception as e:
            logger.error(f"[Sentinel] Kill switch halt call failed: {e}", exc_info=True)
            return False
        if hasattr(self.controller, "is_halted"):
            try:
                return bool(self.controller.is_halted())
            except Exception:
                return True
        return True

    def _evaluate_and_adjust(self):
        """Core AI Autonomous Evaluation Sequence."""
        # ── Feature 2: Sabbath Guard ──
        # Check if Sabbath is active BEFORE calling the AI
        config = self._read_config()
        sabbath = self._get_sabbath_status(config)
        sabbath_active = sabbath.get("active", False)
        
        execute_trades = config.get("global", {}).get("execute_trades", config.get("runtime", {}).get("execute_trades", False))
        is_paper = not execute_trades

        sabbath_instruction = ""
        if sabbath_active:
            if is_paper:
                sabbath_instruction = (
                    "\n\n⚠️ SABBATH IS CURRENTLY ACTIVE, BUT YOU ARE IN PAPER TRADING MODE.\n"
                    "Because this is a simulated paper-trading environment and not real commerce, "
                    "you ARE permitted to continue evaluating profiles, monitoring the simulation, "
                    "and adjusting parameters. You do not need to halt operations for Sabbath "
                    "since no real money is being risked.\n"
                )
            else:
                sabbath_instruction = (
                    "\n\n⚠️ SABBATH IS CURRENTLY ACTIVE. You MUST NOT:\n"
                    "  - Create, modify, or delete any profiles\n"
                    "  - Create or delete any schedule sessions\n"
                    "  - Adjust any settings that affect trade execution\n"
                    "  - Trigger the kill switch (trades are already paused)\n"
                    "You MAY only observe, analyze, and write memory notes for the next cycle.\n"
                    "Return empty arrays/objects for profile_actions, schedule_actions, and adjust_settings.\n"
                )
        
        from tradebot_sci.ai.architecture_reference import ARCHITECTURE_COURSE
        system_prompt = (
            f"You are the '{self.personality}' 20-year veteran autonomous trading manager.\n"
            "Your objective is to review the current bot status, profiles, schedules, global news, and past actions.\n"
            "You possess complete authority over execution, pipeline routing, profile management, and scheduling.\n"
            "\n"
            "BEFORE making ANY changes, you MUST understand how the system works.\n"
            "The following is a mandatory architecture reference:\n"
            f"{ARCHITECTURE_COURSE}\n"
            f"{sabbath_instruction}\n"
            'You MUST return a JSON explicitly matching this schema:\n'
            '{\n'
            '    "analysis": "Your detailed thoughts and reasoning about the current state",\n'
            '    "proposed_interval_mins": 30,\n'
            '    "trigger_kill_switch": false,\n'
            '    "adjust_settings": { "RISK_PER_TRADE_PCT": "0.01" },\n'
            '    "bypass_strategy_routing": "",\n'
            '    "memory_note_for_next_cycle": "Short cohesive note for yourself",\n'
            '\n'
            '    "profile_actions": [\n'
            '        {"action": "modify", "profile": "profile_name", "updates": {"symbols": ["EUR_USD"]}},\n'
            '        {"action": "create", "profile": "new_name", "config": {"strategy_variant": "meta_sci", "symbols": ["BTCUSD"], "htf_timeframe": "15m"}}\n'
            '    ],\n'
            '\n'
            '    "schedule_actions": [\n'
            '        {"action": "create_session", "profile_name": "my_profile", "start_time": "09:00", "end_time": "17:00",\n'
            '         "days_of_week": ["Monday","Tuesday","Wednesday","Thursday","Friday"], "mode": "custom"},\n'
            '        {"action": "delete_session", "index": 0}\n'
            '    ],\n'
            '\n'
            '    "change_explanation": "Detailed explanation of changes made and WHY. Leave empty string if no changes.",\n'
            '    "insight_commentary": "Your ongoing thinking, observations, and plans for the user\'s Insight panel. ALWAYS provide this, even when making no changes. Be specific about what you see in the data and what you\'re watching for next."\n'
            '}\n'
            '\n'
            'RULES:\n'
            '- Use the SETTINGS REFERENCE GUIDE to understand what each setting does before changing it.\n'
            '- If you make ANY changes, you MUST provide a detailed change_explanation.\n'
            '- EVEN IF you make NO changes, you MUST still provide insight_commentary — your current thinking, what you\'re observing, and what you\'re planning.\n'
            '- profile_actions and schedule_actions should be empty arrays [] if no changes needed.\n'
            '- adjust_settings should be an empty object {} if no settings changes needed.\n'
            '- When creating profiles, use lowercase_underscore names.\n'
            '- When modifying symbols, provide the COMPLETE new symbol list (not a diff).\n'
            '\n'
            'CRITICAL ANTI-REPETITION RULES:\n'
            '- The user sees ALL of your previous insight_commentary messages as a scrollable history.\n'
            '- You MUST NOT repeat the same analysis, numbers, or phrasing from your memory_note_for_next_cycle or previous cycles.\n'
            '- Each insight_commentary MUST contain NEW observations, NEW data points, or NEW thinking.\n'
            '- If market conditions have NOT changed, say so briefly and focus on WHAT you are watching for and WHEN you expect things to shift.\n'
            '- If you already reported specific stats (e.g. "45.7% win rate over 46 trades"), do NOT repeat them unless they have CHANGED.\n'
            '- Vary your language. Never start two consecutive messages the same way.\n'
            '- If nothing is happening, it is perfectly fine to say "Markets are quiet, no action needed. Watching [X] for [Y]." in 1-2 sentences.\n'
            '\n'
            'SETTINGS CHANGE RATE-LIMITING:\n'
            '- Do NOT adjust the same setting more than once per 3 cycles (approximately 1.5 hours).\n'
            '- If you already adjusted a setting, do NOT adjust it again unless conditions have MATERIALLY changed.\n'
            '- Check your memory_note_for_next_cycle for recent changes you made — do not redo them.\n'
            '- Making the SAME adjustment repeatedly is a serious error.\n'
            '\n'
            'ZERO TRADE PROTOCOL:\n'
            '- If you observe 0 trades over multiple days AND the market conditions you are observing are A or B grade (strong trends, clean structure, good volatility), then 0 trades is a problem worth investigating.\n'
            '- In that case, check the Rejection Journal. If a safety guard (Fee Shield, Volatility Veto, etc.) is consistently blocking setups that YOU believe are valid, adjust it via "adjust_settings" or disable it to unblock trading.\n'
            '- However, if the market is genuinely bad (C, D, or F grade — choppy, ranging, low volatility, no structure), then 0 trades is the CORRECT outcome. Do NOT force trades into a bad market just to avoid zero trades. Sitting out bad conditions IS the veteran move.\n'
            '- In short: bad market + zero trades = patience. Good market + zero trades = broken settings that need fixing.\n'
            '\n'
            'EXCHANGE / BROKER CONSTRAINTS:\n'
            '- Check the "Connected Exchanges" and "Crypto Trading Available" fields in the status report.\n'
            '- If Crypto Trading Available is "NO", you MUST NOT create, modify, or activate any crypto profiles or suggest crypto trading.\n'
            '- Only propose profiles and symbols for asset classes supported by the connected exchanges.\n'
            '- OANDA US does NOT allow metals trading (XAU/USD, XAG/USD, etc.) — this is a US regulatory restriction (CFTC). Do NOT suggest gold, silver, or any metal pairs.\n'
            '- OANDA US supports: Forex pairs and CFD indices ONLY. No metals, no crypto.\n'
            '- MFE/MAE OPTIMIZATION PROTOCOL:\n'
            '    * You are now provided with MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion) for all trades.\n'
            '    * MFE is the peak profit a trade reached before closing. MAE is the peak drawdown it hit.\n'
            '    * If MFE is high but the trade closed at a loss (Winner Giveback), the bot is "giving back" too much. TWEAK: Decrease RISK_REWARD_RATIO or enable/tighten TRAILING_STOP_MIN_PROFIT_PCT.\n'
            '    * If MAE is consistently large (approaching SL) before the trade turns into a win, your entries are too early. TWEAK: Switch to a slower HTF/LTF pairing or increase STOP_ATR_MULTIPLIER.\n'
            '    * If MFE/MAE ratio is low (< 1.0), the strategy is "unclean"—it takes more heat than heat it generates. Consider switching strategy_variant.\n'
            '\n'
            'HANDS-OFF SETTINGS (DO NOT TOUCH):\n'
            '- NEVER modify htf_timeframe, mtf_timeframe, or ltf_timeframe on ANY profile. These are architecturally load-bearing.\n'
            '- The MTF Alignment gate in the Forex Conductor requires specific timeframe pairings (4h/1h/5m) to function. Changing ltf_timeframe to 1m starves the ADX indicator of data, causing it to return "neutral" on every tick, which permanently blocks the alignment gate and results in ZERO TRADES.\n'
            '- You previously changed ltf_timeframe from 5m to 1m and it silently killed all trading for 24+ hours. This was catastrophic.\n'
            '- If you believe a timeframe change is needed, EXPLAIN YOUR REASONING in insight_commentary and let the human operator decide. Never make the change yourself.\n'
            '- Similarly, do NOT change: strategy_variant (use profile_actions to switch strategies instead), execution_timeframe, or any key prefixed with "trend_" (these are indicator toggles calibrated by the developer).\n'
            '\n'
            'FOREX PROFILE GUIDELINES:\n'
            '- For Forex profiles, ensure Dynamic Risk is enabled ("risk_dynamic_auto": true).\n'
            '- Restrict trading universe to the 5 Core Majors (EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCHF). Avoid JPY/CAD crosses as they bleed capital.\n'
            '- Disable Greed Guard, Rollover Deadzone, Drawdown Breaker, and Leverage Sentry, as these conflict with Conductor internal logic.\n'
            '\n'
            'INSIGHT COMMENTARY GUIDELINES:\n'
            '- The user reads your insight_commentary in a panel on their dashboard.\n'
            '- Write 2-3 sentences about what you\'re seeing and thinking RIGHT NOW.\n'
            '- Mention specific symbols, numbers, and market conditions.\n'
            '- Reference the CHART DATA and INDICATORS when making observations — cite specific RSI, EMA, and price levels.\n'
            '- If you made changes, explain them in change_explanation. If not, still provide your observations in insight_commentary.\n'
            '- Be conversational and confident — you\'re a veteran talking to your client.\n'
        )
        
        try:
            # Built inside the try: assembling the payload touches the ledger,
            # market data and news feeds, and a failure there used to escape the
            # handler entirely and kill the daemon thread silently.
            state_payload = self._build_system_state_payload()
            # Format expects ChatMessage schema natively
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": state_payload}
            ]

            logger.info("[Sentinel] Requesting autonomous evaluation from cognitive backend...")
            response_json_str = self.ai.raw_chat(messages, expect_json=True)
            
            import re
            cleaned_str = re.sub(r'```(?:json)?\s*', '', response_json_str).strip()
            if cleaned_str.endswith('```'):
                cleaned_str = cleaned_str[:-3].strip()
                
            decision = json.loads(cleaned_str)
            
            analysis = decision.get("analysis", "")
            next_interval = decision.get("proposed_interval_mins", self.interval_mins)
            kill_switch = decision.get("trigger_kill_switch", False)
            adjustments = decision.get("adjust_settings", {})
            router_bypass = decision.get("bypass_strategy_routing", "")
            note = decision.get("memory_note_for_next_cycle", "")
            profile_actions = decision.get("profile_actions", [])
            schedule_actions = decision.get("schedule_actions", [])
            change_explanation = decision.get("change_explanation", "")
            insight_commentary = decision.get("insight_commentary", "")
            
            # ── Sabbath hard block — reject all mutations ──
            if sabbath_active and not is_paper:
                if adjustments or profile_actions or schedule_actions or kill_switch:
                    logger.warning("[Sentinel] Sabbath is active — rejecting all mutations from AI response.")
                    self.memory.add_note("[SABBATH] AI attempted changes during Sabbath — all blocked.")
                    adjustments = {}
                    profile_actions = []
                    schedule_actions = []
                    kill_switch = False
                    change_explanation = "Sabbath is active. No changes were made. Observing only."

            # 1. Self-Adjusting Intervals (Req #7)
            # bool is an int subclass, so testing __int__ accepted
            # "proposed_interval_mins": true and set a 1-minute interval.
            if isinstance(next_interval, bool):
                logger.warning(
                    f"[Sentinel] Rejecting proposed interval {next_interval!r} — a boolean is not "
                    "a valid interval."
                )
            elif isinstance(next_interval, (int, float)) and 1 <= float(next_interval) <= 1440:
                self.interval_mins = int(next_interval)
            elif next_interval is not None:
                logger.warning(
                    f"[Sentinel] Rejecting proposed interval {next_interval!r} — expected a number "
                    "between 1 and 1440."
                )
                
            # 2. Add structural memory
            if note:
                self.memory.add_note(note)
                
            # 3. Execution Kill Switch (Req #8.5)
            if kill_switch:
                halted = self._engage_kill_switch(analysis)
                if halted:
                    logger.critical("[Sentinel] KILL SWITCH AUTHORIZED BY AI. Halting logic matrix.")
                    self.memory.record_action("KILL_SWITCH", {"reason": analysis})
                    self._broadcast_change_commentary(
                        change_explanation or f"🚨 KILL SWITCH ACTIVATED: {analysis[:300]}"
                    )
                else:
                    # Never tell the operator trading stopped when nothing did.
                    reason = (
                        "🚨 KILL SWITCH REQUESTED BUT UNAVAILABLE: no halt mechanism is reachable, "
                        "so trading is still running. Stop the bot manually.\n\n"
                        f"Stated reason: {analysis[:300]}"
                    )
                    self.memory.record_action("KILL_SWITCH_FAILED", {"reason": analysis})
                    self._broadcast_change_commentary(reason)
                return
                
            # 4. Strategy Bypass Override (Req #8.4)
            if router_bypass:
                logger.warning(f"[Sentinel] Bypassing native router. Enforcing route: {router_bypass}")
                self.memory.record_action("ROUTER_BYPASS", {"target": router_bypass})
                
            # 5. Iterative Pre-Flight Overrides (Req #8.1 & 8.2)
            if adjustments and isinstance(adjustments, dict):
                if self._execute_synthetic_preflight(adjustments):
                    logger.info(f"[Sentinel] Applying secure metric adjustments: {sorted(adjustments)}")
                    outcome = self._apply_settings_adjustments(adjustments)
                    applied = outcome.get("applied", {})
                    declined = outcome.get("rejected", [])
                    # Record and report the outcome, not the request: a key that
                    # was refused must not be stored or announced as applied.
                    if applied:
                        self.memory.record_action("SETTINGS_UPDATE", applied)
                    if declined:
                        self.memory.record_action("SETTINGS_REJECT", {"rejected": declined})
                    if applied or declined:
                        change_explanation = self._describe_settings_outcome(
                            applied, declined, change_explanation
                        )
                else:
                    logger.warning("[Sentinel] Pre-flight failed. Rejecting parameter update.")
                    self.memory.record_action("PRE_FLIGHT_REJECT", adjustments)
                    change_explanation = self._describe_settings_outcome(
                        {},
                        [{"key": key, "reason": "failed the structural pre-flight check"} for key in adjustments],
                        change_explanation,
                    )

            # 6. Feature 1: Profile Actions
            if profile_actions and isinstance(profile_actions, list):
                for action in profile_actions:
                    if not isinstance(action, dict):
                        continue
                    act_type = action.get("action", "")
                    if act_type == "modify":
                        pname = action.get("profile", "")
                        updates = action.get("updates", {})
                        if pname and updates:
                            if self._modify_profile(pname, updates):
                                logger.info(f"[Sentinel] Modified profile '{pname}': {list(updates.keys())}")
                    elif act_type == "create":
                        pname = action.get("profile", "")
                        pconfig = action.get("config", {})
                        if pname:
                            if self._create_profile(pname, pconfig):
                                logger.info(f"[Sentinel] Created profile '{pname}'")
                    elif act_type == "delete":
                        pname = action.get("profile", "")
                        if pname:
                            cfg = self._read_config_for_write()
                            if cfg is None:
                                logger.error(f"[Sentinel] Aborting deletion of profile '{pname}': config.json is unreadable.")
                                continue
                            cfg_profiles = cfg.get("profiles", {})
                            if pname in cfg_profiles:
                                del cfg_profiles[pname]
                                cfg["profiles"] = cfg_profiles
                                self._write_config(cfg)
                                # Mirror to YAML
                                try:
                                    yaml_profiles = self._read_profiles()
                                    if pname in yaml_profiles:
                                        del yaml_profiles[pname]
                                        self._write_profiles(yaml_profiles)
                                except Exception:
                                    pass
                                self.memory.record_action("PROFILE_DELETE", {"profile": pname})
                                logger.info(f"[Sentinel] Deleted profile '{pname}' from config.json")

            # 7. Feature 3: Schedule Actions
            if schedule_actions and isinstance(schedule_actions, list):
                cfg = self._read_config_for_write()
                if cfg is None:
                    logger.error("[Sentinel] Aborting schedule actions: config.json is unreadable.")
                else:
                    self._apply_schedule_actions(cfg, schedule_actions)

            # 8. Feature 5: Broadcast Insight Commentary (ALWAYS — every cycle)
            # Priority: change_explanation (if changes were made) > insight_commentary (ongoing)
            broadcast_text = ""
            if change_explanation and change_explanation.strip():
                broadcast_text = change_explanation.strip()
            if insight_commentary and insight_commentary.strip():
                if broadcast_text:
                    broadcast_text += f"\n\n📊 {insight_commentary.strip()}"
                else:
                    broadcast_text = insight_commentary.strip()

            if broadcast_text:
                self._broadcast_change_commentary(broadcast_text)
                # Store a condensed version in memory
                self.memory.add_note(f"[INSIGHT] {broadcast_text[:300]}")
            
        except Exception as e:
            logger.error(f"[Sentinel] Cognitive evaluation error: {e}", exc_info=True)
            headline, detail = self._classify_evaluation_error(e)
            error_msg = f"⚠️ {headline}\n\n{detail}"
            self._broadcast_change_commentary(error_msg)

    @staticmethod
    def _classify_evaluation_error(error: Exception) -> tuple:
        """Return (headline, detail) describing why an evaluation cycle failed.

        The catch-all here used to report every failure — including a malformed
        JSON response and internal errors — as "the cognitive backend rejected
        the request ... verify your API Keys", which sent the operator after
        credentials that were never the problem.
        """
        text = str(error).lower()
        if isinstance(error, json.JSONDecodeError) or ("json" in text and "decode" in text):
            return (
                "AUTOPILOT RESPONSE PARSE ERROR",
                "The cognitive backend replied, but the response was not valid JSON, so no "
                f"decision could be read and nothing was changed.\n{error}",
            )
        if any(token in text for token in (
            "401", "403", "unauthor", "invalid api key", "invalid_api_key", "api key",
            "authentication", "permission denied", "forbidden",
        )):
            return (
                "AUTOPILOT AUTH ERROR",
                "The cognitive backend rejected the request as unauthorised.\n"
                f"{error}\n\nPlease verify your API Keys, Model Name, and Network Connection.",
            )
        if any(token in text for token in (
            "timeout", "timed out", "connection", "network", "unreachable", "dns",
            "ssl", "temporarily unavailable", "reset by peer",
        )):
            return (
                "AUTOPILOT NETWORK ERROR",
                f"The cognitive backend could not be reached.\n{error}\n\n"
                "Check your network connection and the backend endpoint.",
            )
        if any(token in text for token in ("rate limit", "429", "quota", "overloaded", "too many requests")):
            return (
                "AUTOPILOT RATE LIMITED",
                f"The cognitive backend is throttling requests.\n{error}\n\n"
                "Reduce the check-in frequency or wait for the quota to reset.",
            )
        return (
            "AUTOPILOT INTERNAL ERROR",
            f"The evaluation cycle failed inside the bot ({type(error).__name__}).\n{error}\n\n"
            "This is not an API credential problem. See the log for the traceback.",
        )

    def _apply_settings_adjustments(self, adjustments: dict) -> dict:
        """Apply settings adjustments to config.json, mapping to the correct sections.

        Returns {"applied": {key: written value}, "rejected": [{"key", "reason"}]}
        so the caller records and broadcasts what actually happened rather than
        what the model intended.
        """
        result = {"applied": {}, "rejected": []}
        if not isinstance(adjustments, dict) or not adjustments:
            return result

        cfg = self._read_config_for_write()
        if cfg is None:
            logger.error("[Sentinel] Rejecting all settings adjustments: config.json is unreadable.")
            result["rejected"] = [
                {"key": key, "reason": "config.json could not be read; nothing was written"}
                for key in adjustments
            ]
            return result

        candidates, rejected = self._screen_settings_adjustments(adjustments)
        result["rejected"].extend(rejected)
        if not candidates:
            return result

        # Reject the whole set when any proposed value fails its model: writing
        # the subset that happens to validate would apply half of an adjustment
        # the AI reasoned about as a unit.
        _models, reason = self._build_candidate_models(candidates, cfg)
        if reason:
            logger.error(f"[Sentinel] Rejecting all settings adjustments: {reason}")
            result["rejected"].extend({"key": key, "reason": reason} for key in candidates)
            return result

        for key, (section, field, _cls, value) in candidates.items():
            section_data = cfg.get(section)
            if not isinstance(section_data, dict):
                section_data = {}
            section_data[field] = value
            cfg[section] = section_data
            result["applied"][key] = value

        if not self._write_config(cfg):
            failed = list(result["applied"])
            result["applied"] = {}
            result["rejected"].extend({"key": key, "reason": "config.json write failed"} for key in failed)
        return result

    def loop(self):
        logger.info("[Sentinel] Seasoned Trader Daemon initiated.")
        self.running = True

        # Wait for the Electron GUI to reconnect its WebSocket before broadcasting the initial briefing.
        # Hard backend restarts trigger a 5s GUI reconnect penalty; if we emit too fast, it goes into the void.
        wait_loops = 0
        while self.running and wait_loops < 30:
            if self.ws_server and self.ws_server.clients:
                break
            time.sleep(0.5)
            wait_loops += 1

        # Fire the initial battle plan briefing on first activation
        try:
            self._broadcast_initial_briefing()
        except Exception as e:
            logger.error(f"[Sentinel] Initial briefing failed: {e}", exc_info=True)

        last_eval_time = None
        last_real_eval_time = 0.0

        while self.running:
            # Wake up frequently to tick the simulation time delta
            time.sleep(5)

            try:
                # 1. Fetch current simulated or real time
                latest_time = None
                is_replay = False
                if self.controller and getattr(self.controller, "replay_provider", None):
                    # We are in Replay mode! Sync to simulated market time
                    sim_time = getattr(self.controller.replay_provider, "sim_time", None)
                    if sim_time:
                        latest_time = sim_time
                        is_replay = True

                if not latest_time:
                    # Default to real wall-clock time if not replaying
                    from datetime import datetime
                    latest_time = datetime.now()

                # 2. Bootstrap first interval
                if last_eval_time is None:
                    last_eval_time = latest_time
                    last_real_eval_time = time.time()
                    self._evaluate_and_adjust()
                    logger.info(f"[Sentinel] First evaluation passed. Synchronizing next cycle to {self.interval_mins} mins.")
                    continue

                # 3. Check time delta (handles both 1:1 real-time and x300 Replay-time)
                delta = latest_time - last_eval_time
                if delta.total_seconds() >= (self.interval_mins * 60):
                    # Apply a strict wall-clock throttling guard for Replay Mode.
                    # If we are rapidly fast-forwarding an entire week in 3 minutes,
                    # we do NOT want the AI to make an API call for every 30-min candle.
                    # Restrict it to the user's configured interval in REAL-WORLD minutes
                    # so it behaves exactly like a live 24/7 session.
                    real_now = time.time()
                    real_delta = real_now - last_real_eval_time

                    if is_replay and real_delta < (self.interval_mins * 60):
                        # Sync the sim cursor forward without firing the expensive LLM.
                        # We skip the execution to avoid spamming the UI.
                        last_eval_time = latest_time
                        continue

                    self._evaluate_and_adjust()
                    last_eval_time = latest_time
                    last_real_eval_time = time.time()
                    logger.debug(f"[Sentinel] Cycle sync boundary met. (SimDelta={delta.total_seconds()}s, RealDelta={real_delta:.1f}s)")
            except Exception as e:
                # One bad cycle must not kill the daemon: log the traceback so the
                # failure is visible and keep the schedule running.
                logger.error(f"[Sentinel] Evaluation cycle failed: {e}", exc_info=True)
                time.sleep(5)

    def _thread_main(self):
        """Thread entry point that keeps the daemon alive across unexpected failures.

        Without this, an exception escaping loop() terminated the daemon thread
        silently: no traceback, no restart, autopilot simply gone.
        """
        while self.running:
            try:
                self.loop()
                return
            except Exception as e:
                logger.error(f"[Sentinel] Seasoned Trader loop crashed: {e}", exc_info=True)
                if not self.running:
                    return
                logger.warning("[Sentinel] Restarting Seasoned Trader loop in 5s.")
                time.sleep(5)

    def start(self):
        if not self._thread or not self._thread.is_alive():
            self.running = True
            self._thread = threading.Thread(
                target=self._thread_main, name="seasoned-trader", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0):
        """Stop the daemon and wait for the cycle in flight to finish.

        Joining matters: runtime/loop.py stops the daemon and immediately builds
        a replacement, so returning while the old thread is still mid-cycle
        leaves two daemons doing read-modify-write on the same config and memory
        files. Safe to call when the daemon was never started.
        """
        self.running = False
        thread = self._thread
        if thread is None:
            return
        if thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(
                    f"[Sentinel] Daemon thread still running after {timeout}s; "
                    "not waiting any longer."
                )
        if not thread.is_alive():
            self._thread = None
