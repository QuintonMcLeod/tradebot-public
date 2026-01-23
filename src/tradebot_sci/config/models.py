from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, NonNegativeInt, PositiveInt
from tradebot_sci.config.broker import BrokerSettings, OandaSettings


class LoggingSettings(BaseModel):
    level: str = Field(default="INFO", description="Root log level")
    file: str = Field(default="logs/tradebot.log", description="Path to rotating log file")
    max_bytes: PositiveInt = Field(default=1_048_576, description="Max bytes before rotation")
    backup_count: PositiveInt = Field(default=5, description="Number of rotated files to keep")


class AISettings(BaseModel):
    provider: str = Field(
        default="openai",
        description="LLM provider: openai|gemini|claude|deepseek|openrouter|custom",
    )
    base_url: HttpUrl = Field(description="Base URL for Trade by SCI compatible API")
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    model_name: str = Field(default="trade-sci-max-icc", description="Model identifier")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: PositiveInt = Field(default=2048)
    timeout_seconds: PositiveInt = Field(default=30)


class CryptoRoutingSettings(BaseModel):
    default_exchange: str = Field(
        default="PAXOS",
        description="Default exchange/custodian to use for crypto contracts (PAXOS or ZEROHASH)",
    )
    overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Per-symbol exchange override for crypto (e.g., BTCUSD: ZEROHASH)",
    )


class MarketSettings(BaseModel):
    default_symbol: str = Field(default="SPY")
    default_timeframe: str = Field(default="5m")
    max_candles: PositiveInt = Field(default=200)
    symbols: list[str] = Field(default_factory=list, description="Symbols the scanner will consider")
    exchange_provider: Literal["primary", "alternative", "hybrid", "coinbase_futures", "oanda"] = Field(
        default="primary",
        description="DEPRECATED: Use market_data_mode and broker_mode instead. Selects global mode.",
    )
    market_data_mode: Literal["primary", "alternative", "hybrid", "coinbase_futures", "oanda"] = Field(
        default="primary",
        description="Selects the market data provider strategy (primary=IBKR, alternative=Crypto plugin, hybrid=Mix, coinbase_futures=Coinbase V3 Futures, oanda=OANDA v20).",
    )
    broker_mode: Literal["primary", "alternative", "hybrid", "coinbase_futures", "oanda"] = Field(
        default="primary",
        description="Selects the broker execution strategy (primary=IBKR, alternative=CCXT, hybrid=Mix, coinbase_futures=Coinbase V3 Futures, oanda=OANDA v20).",
    )
    alternative_market_data: Literal["mock", "coinbase", "coinbase_futures", "ccxt", "oanda"] = Field(
        default="mock",
        description="Market data backend to use when exchange_provider=alternative (mock, ccxt, oanda, or coinbase).",
    )
    alternative_broker: Literal["mock", "ccxt", "coinbase_futures", "oanda"] = Field(
        default="mock",
        description="Execution backend to use when exchange_provider=alternative and EXECUTE_TRADES=true (mock, ccxt, or oanda).",
    )
    crypto_routing: CryptoRoutingSettings = Field(
        default_factory=CryptoRoutingSettings,
        description="Routing information for crypto contracts",
    )
    coinbase_futures: CoinbaseFuturesSettings = Field(
        default_factory=lambda: CoinbaseFuturesSettings(),
        description="Settings specific to Coinbase Futures mode",
    )


class CoinbaseFuturesSettings(BaseModel):
    target_leverage: float = Field(default=1.0, ge=1.0, le=10.0, description="Target leverage for futures positions")
    margin_buffer_pct: float = Field(default=0.1, ge=0.0, le=0.5, description="Buffer above maintenance margin")
    use_cross_margin: bool = Field(default=True, description="Use cross margin if supported")


class TradingProfileSettings(BaseModel):
    candle_timeframe: str
    market_poll_interval_seconds: PositiveInt
    ai_decision_interval_seconds: PositiveInt
    htf_timeframe: str = Field(
        default="4h",
        description="Higher timeframe used for ICC structure trend (default 4h).",
    )
    ltf_timeframe: str | None = Field(
        default=None,
        description="Lower timeframe used for ICC execution structure; defaults to candle_timeframe when unset.",
    )
    trend_window: PositiveInt = Field(
        default=18,
        description="Number of candles used for swing-structure trend detection on HTF.",
    )
    ltf_trend_window: PositiveInt | None = Field(
        default=None,
        description="Optional number of candles used for swing-structure trend detection on LTF.",
    )
    trend_swing_lookback: PositiveInt = Field(
        default=2,
        description="Fractal lookback used to detect swing highs/lows.",
    )
    trend_min_swings: PositiveInt = Field(
        default=2,  # Lowered from 3 to allow trend detection in real markets
        description="Minimum confirmed swings required to classify trend (HH/HL or LH/LL).",
    )
    trend_strength_floor: float = Field(
        default=0.3,  # Lowered from 0.5 to detect realistic trends with minor pullbacks
        ge=0.0,
        le=1.0,
        description="Minimum structure strength required to treat a trend as non-neutral.",
    )
    session_gate_enabled: bool = Field(
        default=True,
        description="When true, enforces volume/range expansion for session-aware entries.",
    )
    session_gate_min_candles: PositiveInt = Field(
        default=15,
        description="Minimum candles required before enforcing session health gates.",
    )
    session_range_multiplier: float = Field(
        default=1.02,
        ge=0.0,
        description="Range expansion multiplier required for session health (recent vs prior).",
    )
    session_volume_multiplier: float = Field(
        default=1.02,
        ge=0.0,
        description="Volume expansion multiplier required for session health (recent vs prior).",
    )
    session_overlap_start_hour: int = Field(
        default=12,
        ge=0,
        le=23,
        description="Session bias start hour (local, inclusive) for FX/crypto time-of-day filters.",
    )
    session_overlap_end_hour: int = Field(
        default=16,
        ge=0,
        le=23,
        description="Session bias end hour (local, exclusive) for FX/crypto time-of-day filters.",
    )
    session_overlap_timezone: str = Field(
        default="UTC",
        description="Timezone used for session bias hours (IANA name, e.g., UTC, America/New_York).",
    )
    auto_schedule_enabled: bool = Field(
        default=False,
        description="When true, trades equities during US market hours and crypto during off-hours (Sabbath rules still apply).",
    )
    structure_score_threshold: float = Field(
        default=0.3,
        ge=0.0,
        description="Threshold above which structure is clean enough to trade",
    )
    icc_auto_entry_enabled: bool = Field(
        default=False,
        description="When true, auto-enter on ICC sweep+continuation without AI veto.",
    )
    icc_auto_entry_cooldown_minutes: PositiveInt = Field(
        default=15,
        description="Minimum minutes between ICC auto-entry signals for same symbol.",
    )
    icc_auto_entry_min_htf_strength: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum HTF trend strength required for ICC auto-entry (prevents weak trend trades).",
    )
    icc_auto_entry_require_sweep: bool = Field(
        default=False,
        description="When true, requires a liquidity sweep before ICC continuation can trigger auto-entry. Default false because backtesting shows sweep requirement prevents all entries in real market conditions.",
    )
    icc_auto_entry_allow_chop: bool = Field(
        default=True,
        description="When false, standing aside during identified chop phase.",
    )
    ratchet_risk_enabled: bool = Field(
        default=False,
        description="Enable multi-tier risk ratchet based on account capital.",
    )
    risk_per_trade_dollars: float = Field(
        default=0.0,
        ge=0.0,
        description="Fixed risk per trade in account currency. Overrides risk_per_trade_pct when > 0.",
    )
    risk_per_trade_pct: float = Field(
        default=0.015,
        ge=0.0,
        le=1.0,
        description="Standard risk per trade as a fraction of equity.",
    )
    icc_entry_score_threshold: float = Field(
        default=60.0,
        ge=0.0,
        description="Minimum ICC points required to allow a new entry (replaces hard ICC gates).",
    )
    icc_score_htf_ltf_align_points: float = Field(
        default=30.0,
        ge=0.0,
        description="Points awarded when HTF/LTF trends align (HTF may be neutral).",
    )
    icc_score_sweep_points: float = Field(
        default=25.0,
        ge=0.0,
        description="Points awarded when a liquidity sweep is detected.",
    )
    icc_score_continuation_points: float = Field(
        default=25.0,
        ge=0.0,
        description="Points awarded when continuation is confirmed.",
    )
    icc_score_indication_points: float = Field(
        default=0.0,
        ge=0.0,
        description="Points awarded when an HTF indication (break of structure) is detected.",
    )
    icc_score_strong_htf_points: float = Field(
        default=15.0,
        ge=0.0,
        description="Points awarded when HTF trend strength exceeds the configured threshold.",
    )
    icc_score_phase_points: float = Field(
        default=5.0,
        ge=0.0,
        description="Points awarded when phase is not chop.",
    )
    icc_score_htf_strength_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="HTF trend strength threshold used for strong-trend scoring.",
    )
    # [ANTIGRAVITY] Reversal Logic Settings
    enable_reversal_logic: bool = Field(
        default=False,
        description="Enable 'Liquidity Reversal' pattern detection (Robot Logic).",
    )
    reversal_rsi_threshold: float = Field(
        default=30.0,
        ge=0.0,
        le=100.0,
        description="RSI threshold for reversal detection (Oversold < X, Overbought > 100-X).",
    )
    max_volume_ratio: float = Field(
        default=2.5,
        ge=1.0,
        description="Max relative volume allowed to avoid 'Falling Knife' scenarios.",
    )
    reversal_risk_per_trade: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="Specific risk % for high-confidence reversal setups.",
    )
    friction_stop_floor_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum stop-loss % used for Target calculation (to account for fees).",
    )
    target_risk_multiplier: float = Field(
        default=3.0,
        ge=1.0,
        description="Reward multiplier used for target projection relative to Effective Risk.",
    )
    moon_trailer_enabled: bool = Field(
        default=False,
        description="Enable aggressive profit trailing (Moon Trailer).",
    )
    moon_trailer_tp_trigger_pct: float = Field(
        default=0.05,
        ge=0.0,
        description="Price move % required to trigger Moon Trailer (e.g. 0.05 = 5%).",
    )
    moon_trailer_trail_pct: float = Field(
        default=0.025,
        ge=0.0,
        description="Trailing distance as % of price (e.g. 0.025 = 2.5%).",
    )
    icc_two_signal_override_enabled: bool = Field(
        default=False,
        description="When true, allow entries on sweep + continuation or sweep + indication even if score is below threshold.",
    )
    enable_pyramiding: bool = Field(
        default=False,
        description="Enable multi-tier scaling into winning trades.",
    )
    max_pyramid_count: int = Field(
        default=2,
        ge=0,
        description="Maximum number of additional entries (pyramids) allowed per trade.",
    )
    pyramid_risk_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description="Factor by which to multiply risk for each consecutive pyramid tier.",
    )
    pyramid_risk_tiers: list[float] = Field(
        default_factory=list,
        description="Explicit risk % for each pyramid tier (overrides multiplier if provided). Example: [0.5, 0.8] for 50% and 80%.",
    )
    pyramid_min_rr_trigger: float = Field(
        default=1.0,
        ge=0.0,
        description="Minimum Reward-to-Risk ratio on original trade before allowing first pyramid.",
    )
    min_hold_hours: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum hours to hold before allowing non-stop exits (0 disables).",
    )
    allow_loss_exit_after_hold: bool = Field(
        default=False,
        description="When true, exit signals after min_hold_hours can close losing trades.",
    )
    max_hold_hours: float = Field(
        default=0.0,
        ge=0.0,
        description="Maximum hours to hold before forcing a time-based exit (0 disables).",
    )
    trailing_stop_enabled: bool = Field(
        default=False,
        description="When true, trail stop loss to HTF swing structure once in profit.",
    )
    trailing_stop_min_profit_pct: float = Field(
        default=1.0,
        ge=0.0,
        description="Minimum profit percent required before trailing stop activates.",
    )
    backtest_disable_stops: bool = Field(
        default=False,
        description="When true, backtests ignore stop-loss exits.",
    )
    profit_exit_after_hold: bool = Field(
        default=False,
        description="When true, exit on first profitable bar after min_hold_hours.",
    )
    max_pyramid_entries: int = Field(
        default=3,
        ge=1,
        description="Max number of entries per position (1 = no pyramid, 3 = initial + 2 adds)",
    )
    pyramid_score_threshold: float = Field(
        default=70.0,
        ge=0.0,
        description="Score needed for pyramid entries (higher than initial entry threshold)",
    )
    htf_neutral_exit_bars: int = Field(
        default=48,
        ge=0,
        description="Exit if HTF neutral for this many bars (48 bars = 4h on 5m chart)",
    )
    breakeven_trail_after_pyramids: int = Field(
        default=0,
        ge=0,
        description="After this many pyramid entries, move stop to breakeven + trail. 0 disables.",
    )
    breakeven_trail_pct: float = Field(
        default=0.01,
        ge=0.0,
        description="Trail percentage above breakeven once activated (0.01 = 1%).",
    )
    auto_flatten_on_close: bool = Field(
        default=False,  # [ANTIGRAVITY] Default OFF - perpetual futures have no EOD settlement
        description="When true, sessions auto-flatten/cancel at every scheduled window. "
                    "WARNING: Keep OFF for Coinbase Nano futures (perpetual-style contracts).",
    )
    symbols: Optional[list[str]] = Field(
        default=None,
        description="Optional override of the symbol universe for this profile",
    )
    max_open_positions: Optional[PositiveInt] = Field(
        default=None,
        description="Alias for max_concurrent_positions; used in many existing YAML configs.",
    )
    pdt_guard_enabled: bool = Field(
        default=False,
        description="Enable lightweight PDT roundtrip guarding for equities",
    )
    flip_actions_enabled: bool = Field(
        default=False,
        description="Allow flip_to_long/flip_to_short actions when reversing an existing position.",
    )
    flip_cooldown_seconds: PositiveInt = Field(
        default=600,
        description="Minimum seconds between flip actions when PDT guard is active.",
    )
    max_equity_roundtrips_per_day: PositiveInt = Field(
        default=2,
        description="Maximum equity roundtrips allowed per day when PDT guard is active",
    )
    continuous_mode: bool = Field(
        default=False,
        description="Keep the runtime loop alive indefinitely regardless of iteration limits",
    )
    crypto_only: bool = Field(
        default=False,
        description="Treat the profile as crypto-only for flatten/confirmation logic",
    )
    cooldown_enabled: bool = Field(
        default=True,
        description="Enable profile-level cooldowns after guard blocks or successes",
    )
    cooldown_cycles_after_block: PositiveInt = Field(
        default=3,
        description="Cycles to skip a symbol following a blocked attempt",
    )
    cooldown_cycles_after_success: NonNegativeInt = Field(
        default=0,
        description="Cycles to skip a symbol after a successful entry",
    )
    cooldown_scope: str = Field(
        default="symbol",
        description="Apply cooldown per symbol ('symbol') or globally ('global')",
    )
    stick_to_active_symbol_until: str = Field(
        default="cycle_end",
        description="How long to avoid rotating away from the active symbol",
    )
    crypto_fractional_enabled: bool = Field(
        default=False,
        description="Allow fractional crypto sizing when the profile supports it",
    )
    crypto_min_notional_usd: float = Field(
        default=20.0,
        description="Minimum notional for fractional crypto trades",
    )
    crypto_max_notional_usd: Optional[float] = Field(
        default=None,
        description="Optional cap on crypto notional exposures (None = no cap)",
    )
    crypto_qty_steps: Dict[str, float] = Field(
        default_factory=lambda: {"BTCUSD": 0.0001, "ETHUSD": 0.001, "SOLUSD": 0.01},
        description="Per-crypto symbol quantity steps for fractional orders",
    )
    crypto_order_type: Literal["LIMIT", "MARKET"] = Field(
        default="LIMIT",
        description="Order type for crypto entries (LIMIT=safer but risk rejection, MARKET=guaranteed fill but accepts slippage).",
    )
    pair_selector_enabled: bool = Field(
        default=False,
        description="When true (typically crypto profiles), dynamically selects a tradable crypto basket using liquidity gates.",
    )
    pair_selector_refresh_seconds: PositiveInt = Field(
        default=300,
        description="How often to refresh pair selection when enabled.",
    )
    pair_selector_min_volume_usd_24h: float = Field(
        default=1_000_000.0,
        ge=0.0,
        description="Minimum estimated 24h quote volume (USD) for a crypto pair to be considered.",
    )
    pair_selector_max_spread_bps: float = Field(
        default=25.0,
        ge=0.0,
        description="Maximum bid/ask spread in basis points for a crypto pair to be considered.",
    )
    pair_selector_min_depth_usd: float = Field(
        default=50_000.0,
        ge=0.0,
        description="Minimum estimated top-of-book depth (USD) for a crypto pair to be considered.",
    )
    pair_selector_max_pairs: PositiveInt = Field(
        default=5,
        description="Maximum number of pairs to return when pair selector is enabled.",
    )
    maker_first_enabled: bool = Field(
        default=True,
        description="Prefer maker (post-only limit) entries when urgency is low and structure allows.",
    )
    maker_first_offset_bps: float = Field(
        default=0.0,
        ge=0.0,
        description="Optional price offset in bps from best bid/ask for post-only maker orders.",
    )
    taker_max_slippage_bps: float = Field(
        default=30.0,
        ge=0.0,
        description="Max slippage (bps) tolerated for taker-style market entries (best-effort).",
    )
    order_timeout_seconds: PositiveInt = Field(
        default=30,
        description="Timeout before cancelling a resting entry order (alternative/mock broker).",
    )
    sabbath_enabled: bool = Field(
        default=False,
        description="When true, blocks new entries during the Sabbath window",
    )
    sabbath_timezone: str = Field(
        default="America/New_York",
        description="Timezone used to compute Sabbath start/end hours",
    )
    sabbath_start_local: str = Field(
        default="18:00",
        description="Local time (HH:MM) when Sabbath entry blocks start on Friday",
    )
    sabbath_end_local: str = Field(
        default="18:00",
        description="Local time (HH:MM) when Sabbath entry blocks end on Saturday",
    )
    sabbath_lat: float | None = Field(
        default=None,
        description="Optional latitude for astronomical Sabbath calculations",
    )
    sabbath_lon: float | None = Field(
        default=None,
        description="Optional longitude for astronomical Sabbath calculations",
    )
    sabbath_astronomical: bool = Field(
        default=False,
        description="If true and astral is installed, use actual sunset times instead of fixed hours",
    )
    synthetic_stop_persistence_enabled: bool = Field(
        default=True,
        description="Persist synthetic stop state to disk for ZEROHASH crypto",
    )
    synthetic_stop_store_path: str = Field(
        default="data/synthetic_stops.json",
        description="Path to the JSON file that stores synthetic stop records",
    )
    startup_crypto_unprotected_policy: Literal["FLATTEN", "REARM"] = Field(
        default="FLATTEN",
        description="What to do on startup when a crypto position lacks a persisted stop",
    )
    rearm_stop_distance_pct: float = Field(
        default=0.02,
        description="Percentage distance from entry to place rearmed stops (when REARM policy active)",
    )
    synthetic_stop_integrity_interval: PositiveInt = Field(
        default=10,
        description="Number of evaluate cycles between synthetic stop integrity checks",
    )
    runtime_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Override runtime settings when this profile is active",
    )
    icc_aggressive_mode: bool = Field(
        default=True,
        description="Enable opt-in aggressive ICC sizing and guardrails (Phase 2 only).",
    )
    aggressive_risk_per_trade_pct: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="Default risk per trade as a fraction of equity when aggressive mode is enabled.",
    )
    max_daily_loss_pct: float = Field(
        default=0.06,
        ge=0.0,
        le=1.0,
        description="Max daily loss as a fraction of starting equity before blocking new entries (aggressive mode).",
    )
    max_exposure_pct: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Max total open risk as a fraction of equity (aggressive mode).",
    )
    max_consecutive_losses: PositiveInt = Field(
        default=2,
        description="Consecutive loss count before blocking entries (aggressive mode).",
    )
    multi_position_enabled: Optional[bool] = Field(
        default=None,
        description="Optional override for runtime.multi_position_enabled. If set, overrides the global setting.",
    )
    max_concurrent_positions: Optional[PositiveInt] = Field(
        default=None,
        description="Optional override for runtime.max_concurrent_positions. If set, overrides the global setting.",
    )


class AppSettings(BaseModel):
    name: str = Field(default="tradebot-sci-enterprise")
    environment: str = Field(default="dev")
    profile_name: str = Field(default="intraday")


class ScheduleSession(BaseModel):
    name: str
    start: str  # "HH:MM"
    end: str    # "HH:MM"


class ScheduleSettings(BaseModel):
    timezone: str = Field(default="America/New_York")
    sessions: list[ScheduleSession] = Field(default_factory=list)


class RuntimeSettings(BaseModel):
    cancel_orders_on_start: bool = Field(default=False)
    flatten_on_exit: bool = Field(default=False)
    intraday_flatten: bool = Field(
        default=False,
        description="Flatten at session end for intraday mode",
    )
    allow_day_trades: bool = Field(
        default=False,
        description="When false, exits are blocked until the minimum hold duration elapses.",
    )
    min_hold_seconds: PositiveInt = Field(
        default=300,
        description="Minimum seconds a position must be held before exits or TP orders are permitted when day trades are disabled.",
    )
    min_equity_for_margin: float = Field(
        default=2000.0,
        ge=0.0,
        description="Minimum NetLiquidation required before margin, short, or FX trades proceed.",
    )
    position_hold_store_path: str = Field(
        default="data/position_holds.json",
        description="Path where position-open timestamps are persisted across restarts.",
    )
    allow_inherited_position: bool = Field(
        default=False,
        description="Allow runs to start with an existing broker position instead of auto-flattening",
    )
    infer_position_hold_from_executions: bool = Field(
        default=False,
        description="Best-effort inference of inherited position age from recent IBKR executions (fallback uses now).",
    )
    infer_position_hold_lookback_days: int = Field(
        default=7,
        ge=1,
        description="Lookback window (days) for execution-history inference of inherited position age.",
    )
    scale_out_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    min_position_size_to_scale: float = Field(
        default=1.0,
        ge=0.0,
        description="Minimum absolute position size before scaling out; below this we fully flatten",
    )
    emergency_stop_pct: float = Field(default=0.01, ge=0.0, description="Fallback stop distance as fraction of price")
    keep_alive_interval_seconds: int = Field(
        default=300,
        ge=0,
        description="Interval in seconds to ping IBKR API during idle periods (0 disables keep-alive)",
    )
    strike_max_consecutive: PositiveInt = Field(
        default=3,
        description="Maximum consecutive risk suppressions before a symbol is temporarily skipped",
    )
    strike_cooldown_cycles: PositiveInt = Field(
        default=3,
        description="Number of cycles to skip a symbol after it hits the strike limit",
    )
    guard_block_threshold: PositiveInt = Field(
        default=6,
        description="Guard block streak before activating cooldown (per symbol)",
    )
    guard_block_cooldown_cycles: PositiveInt = Field(
        default=1,
        description="Number of scheduler cycles to skip after guard block streak triggers",
    )
    allow_local_stops: bool = Field(
        default=False,
        description="Allow client-side local stop logic when the venue rejects stop orders",
    )
    local_stop_symbols: list[str] = Field(
        default_factory=list,
        description="Symbols that should use local-stop protection even if stop support is missing for others",
    )
    max_scale_ins_per_leg: int = Field(
        default=2,
        ge=0,
        description="Maximum number of scale_in adds allowed per position leg (0 disables scale_in).",
    )
    multi_position_enabled: bool = Field(
        default=True,  # [ANTIGRAVITY FIX] Changed default to True to prevent blocking if config load fails
        description=(
            "When true, the bot may hold multiple concurrent positions (up to max_concurrent_positions). "
            "When false, new entries are blocked while any other position is open."
        ),
    )
    max_concurrent_positions: PositiveInt = Field(
        default=1,
        description="Maximum number of concurrent open positions when multi_position_enabled is true.",
    )
    auto_restart_on_error: bool = Field(
        default=False,
        description="Allow the bot to self-restart if IBKR health checks stay unhealthy for too long.",
    )
    auto_restart_stale_seconds: int = Field(
        default=300,
        ge=30,
        description="Seconds without healthy IBKR account data/connection before auto-restart triggers.",
    )
    auto_restart_min_uptime_seconds: int = Field(
        default=120,
        ge=0,
        description="Minimum uptime before auto-restart can trigger (prevents boot loops).",
    )
    auto_restart_cooldown_seconds: int = Field(
        default=600,
        ge=0,
        description="Minimum seconds between auto-restarts (prevents rapid restart loops).",
    )


class Settings(BaseModel):
    app: AppSettings
    logging: LoggingSettings
    ai: AISettings
    market: MarketSettings
    profiles: Dict[str, TradingProfileSettings]
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    broker: Optional[BrokerSettings] = None
    oanda: Optional[OandaSettings] = None

    def get_active_profile(self) -> TradingProfileSettings:
        profile = self.profiles.get(self.app.profile_name)
        if profile:
            return profile
        raise KeyError(f"Profile '{self.app.profile_name}' not found in configuration")


@lru_cache
def get_cached_settings(settings: Settings) -> Settings:
    return settings


class UserConfig:
    # Strategy Selection
    # Variants: 'evolution', 'robocop', 'quantum', 'london_breakout', 'mean_reversion', 'hyperscalper'
    STRATEGY_VARIANT = 'rubberband_reaper'  # The Rubberband Reaper (+865%, 39% WR, 3.7:1 R:R)
    
    # Extreme Risk Management (Goal: 100%-400% / week) 
    # VERIFIED: +7,036% PnL with Tiered Risk (20%/10%/1%)
    # Tiered Risk (Anti-Martingale):
    #   - Below $1,000: 20% (aggressive growth)
    #   - $1,000-$5,000: 10% (growth)
    #   - Above $5,000: 1% (wealth protection)
    BASE_RISK_PCT = 0.20        # 20% starting risk (tiered down as account grows)
    COMPOUND_PROFITS = True     # Reinvest all gains for exponential growth
    
    # Singularity Pyramiding (Infinite Scale)
    # NOTE: Super-Extreme mode (RSI <15/>85) prevents over-scaling
    INFINITE_PYRAMIDING = True  # bypass MAX_PYRAMID_ENTRIES
    MAX_PYRAMID_ENTRIES = 1000  # Effective infinity
    PYRAMID_TRIGGER_PCT = 0.0001 # 0.01% (Instant Load)
    PYRAMID_RISK_LOAD = 1.00    # 100% Risk on Load (Aggressive)
    PYRAMID_RISK_SCALE = 1.00   # 100% Risk on Scale (Aggressive)
    
    # Efficiency Gates
    STAGNATION_EXIT_ENABLED = False
    STAGNATION_EXIT_MINUTES = 60  # Kill trade if PnL <= 0 after 60 mins
    
    # Chop Scalp
    CHOP_SCALP_TARGET_USD = 1.00  # Bank profits in weak trends (Increased from 0.40)
    CHOP_STRENGTH_THRESHOLD = 0.5 # Below this is considered "Chop"
    
    # RoboCop Optimization (Machine Speed)
    COMBAT_MODE_ENABLED = True   # Bypass human delays (Session, Confirmation)
    
    # Fast Exit Logic ("Chop Top")
    ROBO_FAST_EXIT_ENABLED = True
    CHOP_TP_EXIT_ENABLED = False
    CHOP_MAX_BARS = 10           # Exit if in chop for > 10 bars and profitable (Increased from 3)
    
    # Robot Strategy Evolution (Robot Speed)
    ROBO_CHOP_SCALP_ENABLED = True # Trade inside the range (NTZ)
    RUNNER_GRACE_ENABLED = True    # Allow winners to run during momentum
    ROBO_ENTRY_SCORE_THRESHOLD = 35.0 # Quality over quantity
