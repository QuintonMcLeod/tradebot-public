from __future__ import annotations
import os

from functools import lru_cache
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, NonNegativeInt, PositiveInt, field_validator
from tradebot_sci.config.broker import BrokerSettings, OandaSettings, PaxosSettings, KrakenSettings


class LoggingSettings(BaseModel):
    level: str = Field(default="INFO", description="Root log level")
    file: str = Field(default="logs/tradebot.log", description="Path to rotating log file")
    max_bytes: PositiveInt = Field(default=1_048_576, description="Max bytes before rotation")
    backup_count: PositiveInt = Field(default=5, description="Number of rotated files to keep")


class PerAssetStrategies(BaseModel):
    """Per-asset-class strategy configuration."""
    crypto: str = "rubberband_reaper"
    forex: str = "rubberband_reaper"
    stocks: str = "quantum"
    etf: str = "quantum"
    metals: str = "mean_reversion"
    futures: str = "volatility_breakout"
    meta_sci: str = "meta_sci"


class AISettings(BaseModel):
    provider: str = Field(
        default_factory=lambda: os.getenv("TRADE_SCI_PROVIDER", "openai"),
        description="LLM provider: openai|gemini|claude|deepseek|openrouter|custom",
    )
    base_url: HttpUrl = Field(
        default_factory=lambda: os.getenv("TRADE_SCI_API_BASE_URL", "https://api.openai.com/v1"),
        description="Base URL for Trade by SCI compatible API"
    )
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("TRADE_SCI_API_KEY") or os.getenv("CHATGPT_KEY"),
        description="API key for authentication"
    )
    model_name: str = Field(
        default_factory=lambda: os.getenv("TRADE_SCI_MODEL_NAME", "trade-sci-max-icc"),
        description="Model identifier"
    )
    temperature: float = Field(
        default_factory=lambda: float(os.getenv("TRADE_SCI_TEMPERATURE", "0.2")),
        ge=0.0,
        le=2.0
    )
    max_tokens: PositiveInt = Field(
        default_factory=lambda: int(os.getenv("TRADE_SCI_MAX_TOKENS", "2048"))
    )
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
        default_factory=lambda: os.getenv("EXCHANGE_PROVIDER", "primary"),
        description="DEPRECATED: Use market_data_mode and broker_mode instead. Selects global mode.",
    )
    market_data_mode: Literal["primary", "alternative", "hybrid", "coinbase_futures", "oanda", "gemini", "kraken"] = Field(
        default_factory=lambda: os.getenv("MARKET_DATA_MODE", os.getenv("EXCHANGE_PROVIDER", "primary")),
        description="Selects the market data provider strategy (primary=IBKR, alternative=Crypto plugin, hybrid=Mix, coinbase_futures=Coinbase V3 Futures, oanda=OANDA v20).",
    )
    broker_mode: Literal["primary", "alternative", "hybrid", "coinbase_futures", "oanda", "gemini", "kraken"] = Field(
        default_factory=lambda: os.getenv("BROKER_MODE", os.getenv("EXCHANGE_PROVIDER", "primary")),
        description="Selects the broker execution strategy (primary=IBKR, alternative=CCXT, hybrid=Mix, coinbase_futures=Coinbase V3 Futures, oanda=OANDA v20).",
    )
    alternative_market_data: Literal["mock", "coinbase", "coinbase_futures", "ccxt", "oanda", "gemini", "kraken"] = Field(
        default="mock",
        description="Market data backend to use when exchange_provider=alternative (mock, ccxt, oanda, or coinbase).",
    )
    alternative_broker: Literal["mock", "ccxt", "coinbase_futures", "oanda", "gemini", "kraken"] = Field(
        default="mock",
        description="Execution backend to use when exchange_provider=alternative and EXECUTE_TRADES=true (mock, ccxt, or oanda).",
    )
    crypto_routing: CryptoRoutingSettings = Field(
        default_factory=CryptoRoutingSettings,
        description="Routing information for crypto contracts",
    )
    primary_market_provider: str = Field(
        default_factory=lambda: os.getenv("PRIMARY_PROVIDER", os.getenv("EXCHANGE_PROVIDER", "ibkr")),
        description="The provider to use when 'primary' is requested (e.g., oanda or ibkr)."
    )
    primary_broker: str = Field(
        default_factory=lambda: os.getenv("PRIMARY_BROKER", os.getenv("EXCHANGE_PROVIDER", "ibkr")),
        description="The broker to use when 'primary' is requested (e.g., oanda or ibkr)."
    )
    primary_forex: str = Field(
        default_factory=lambda: os.getenv("PRIMARY_FOREX", "oanda"),
        description="The provider/broker to use for Forex assets in routed/hybrid modes."
    )
    primary_crypto: str = Field(
        default_factory=lambda: os.getenv("PRIMARY_CRYPTO", "gemini"),
        description="The provider/broker to use for Crypto assets in routed/hybrid modes."
    )
    primary_equities: str = Field(
        default_factory=lambda: os.getenv("PRIMARY_EQUITIES", "disabled"),
        description="The provider/broker to use for Equities in routed/hybrid modes."
    )
    trading_confirmation: Optional[str] = Field(
        default=None,
        description="User confirmation for live trading. Set to 'YES' to bypass interactive confirmation."
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
    name: Optional[str] = Field(
        default=None,
        description="Internal name for the profile.",
    )
    strategy_variant: str = Field(
        default="rubberband_reaper",
        description="Legacy single strategy (fallback) for the profile.",
    )
    strategies: Optional[PerAssetStrategies] = Field(
        default=None,
        description="Per-asset-class strategy overrides.",
    )
    candle_timeframe: str = Field(
        default="5m",
        description="Candle timeframe for the profile (e.g. 1m, 5m, 15m, 1h).",
    )
    market_poll_interval_seconds: PositiveInt = Field(
        default=60,
        description="Seconds between market data poll cycles.",
    )
    ai_decision_interval_seconds: PositiveInt = Field(
        default=300,
        description="Seconds between AI decision cycles.",
    )
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
    adx_gate_threshold: float = Field(
        default=12.0,  # Forex-tuned (was 20 — too high for forex 1H)
        ge=0.0,
        le=100.0,
        description="ADX value below which entries are blocked (no trend). Set to 0 to disable.",
    )
    trend_chop_threshold: float = Field(
        default=8.0,  # Forex-tuned (was 15 — too high for forex 1H)
        ge=0.0,
        le=100.0,
        description="ADX value below which the market is considered choppy. Direction is forced neutral. Must be <= adx_gate_threshold.",
    )
    # ── Trend Indicator Toggles ──────────────────────────────────────
    trend_adx_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_ADX_ENABLED", "true").lower() == "true",
        description="Enable ADX trend-strength gate.",
    )
    trend_rsi_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_RSI_ENABLED", "false").lower() == "true",
        description="Enable RSI overbought/oversold gate.",
    )
    trend_macd_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_MACD_ENABLED", "false").lower() == "true",
        description="Enable MACD momentum-crossover gate.",
    )
    trend_bollinger_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_BOLLINGER_ENABLED", "false").lower() == "true",
        description="Enable Bollinger squeeze gate.",
    )
    trend_supertrend_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_SUPERTREND_ENABLED", "false").lower() == "true",
        description="Enable Supertrend direction gate.",
    )
    trend_ema_ribbon_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_EMA_RIBBON_ENABLED", "false").lower() == "true",
        description="Enable EMA Ribbon alignment gate.",
    )
    trend_ichimoku_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_ICHIMOKU_ENABLED", "false").lower() == "true",
        description="Enable Ichimoku Cloud direction gate.",
    )
    trend_parabolic_sar_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_PARABOLIC_SAR_ENABLED", "false").lower() == "true",
        description="Enable Parabolic SAR direction gate.",
    )
    trend_vwap_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_VWAP_ENABLED", "false").lower() == "true",
        description="Enable VWAP direction gate.",
    )
    trend_hull_ma_enabled: bool = Field(
        default_factory=lambda: os.getenv("TREND_HULL_MA_ENABLED", "false").lower() == "true",
        description="Enable Hull Moving Average direction gate.",
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
    block_counter_trend_entries: bool = Field(
        default=True,
        description="Block entries that go against the HTF trend direction (e.g., no longs in bearish HTF, no shorts in bullish HTF).",
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
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Standard risk per trade as a fraction of equity.",
    )
    balance_cap_pct: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Maximum fraction of liquid balance allowed for a single asset's total exposure.",
    )
    target_leverage: float = Field(
        default=50.0,
        ge=1.0,
        le=100.0,
        description="Target leverage for the asset class. Forex default 50x (OANDA provides 50:1 on majors).",
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
        default=60.0,
        ge=0.0,
        description="Points awarded when continuation is confirmed.",
    )
    icc_score_indication_points: float = Field(
        default=10.0,
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
    # Reversal Logic Settings
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
    # ── Stop-and-Reverse (fires on ANY stop loss exit) ─────────────
    stop_and_reverse_enabled: bool = Field(
        default=False,
        description="When a stop fires, immediately open opposite direction with 1R TP. Different from RSI reversal logic.",
    )
    counter_reversal_enabled: bool = Field(
        default=False,
        description="When SAR drops to -0.2R, open a 2× counter-reversal in the opposite direction to capitalize on failed SAR.",
    )
    sar_keep_open: bool = Field(
        default=False,
        description="If True, SAR stays open when CR fires (CR at -0.5R). If False, SAR closes at B/E and CR fires at that point.",
    )
    cr_risk_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="If >0, CR uses this % of capital for sizing instead of 2× SAR. 0 = use 2× SAR (default).",
    )
    reversal_tp_r: float = Field(
        default=1.0,
        ge=0.5,
        le=10.0,
        description="Take profit target in R-multiples for stop-and-reverse entries (1.0 = 1R).",
    )
    reversal_cost_aware_tp: bool = Field(
        default=True,
        description="Add estimated spread/fee buffer to reversal TP so net PnL is a true 1:1 after costs.",
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
    # ── Guillotine / tiered loss-cap thresholds ─────────────────────────────
    guillotine_r_threshold: float = Field(
        default=-0.3,
        description="Legacy single-threshold Guillotine R-multiple (backtester compat).",
    )
    tier1_r_threshold: float = Field(
        default=-0.30,
        description="R-multiple that triggers Tier-1 Guillotine cut (default -0.30 — was -0.15 which was too tight).",
    )
    tier1_cut_fraction: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Fraction of position to close at Tier-1 Guillotine (0.80 = 80%).",
    )
    tier2_r_threshold: float = Field(
        default=-0.60,
        description="R-multiple that triggers Tier-2 Guillotine cut on residual position.",
    )
    tier2_cut_fraction: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Fraction of remaining position to close at Tier-2 Guillotine (0.80 = 80%).",
    )
    # ── Safety guards (profile-level overrides) ─────────────────────────────
    safety_regime_flip_enabled: bool = Field(
        default=True,
        description="Exit position when HTF regime flips against the trade direction.",
    )
    safety_drawdown_breaker_enabled: bool = Field(
        default=True,
        description="Halt new entries when daily drawdown exceeds safety_drawdown_max_pct.",
    )
    safety_drawdown_max_pct: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Daily drawdown threshold (10%) before drawdown breaker halts entries.",
    )
    safety_streak_breaker_enabled: bool = Field(
        default=True,
        description="Pause a symbol after N consecutive losses.",
    )
    safety_atr_shield_enabled: bool = Field(
        default=True,
        description="Scale down stops / block entries when ATR is extreme.",
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
        default=16.0,
        ge=0.0,
        description="Maximum hours to hold before Day Trade Enforcer activates (0 disables). "
                    "Grace period starts at 70%, emergency exit at 100%, hard kill at 130%.",
    )
    # trailing_stop_enabled: REMOVED — lives exclusively in PerformanceSettings (models.py:979)
    # to prevent split-brain between PositionExitConfig (default=False) and PerformanceSettings (default=True)
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
        default=False,  # Default OFF - perpetual futures have no EOD settlement
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
    stop_atr_multiplier: float = Field(
        default=1.5,
        ge=0.5,
        le=5.0,
        description="Standard stop distance as a multiple of ATR.",
    )
    stability_mode_active: bool = Field(
        default=False,
        description="When true, enforces ultra-conservative risk and entry filters.",
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
        default=True,
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
        default_factory=lambda: {
            "BTCUSD": 0.0001,
            "ETHUSD": 0.001,
            "SOLUSD": 0.01,
            "XRPUSD": 0.01,
            "LINKUSD": 0.01,
            "LTCUSD": 0.001,
            "DOGEUSD": 1.0,
            "ZECUSD": 0.001,
            "BCHUSD": 0.001,
            "AAVEUSD": 0.001,
            "COMPUSD": 0.001,
            "MATICUSD": 0.1,
        },
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
    sabbath_start_local: Any = Field(
        default="18:00",
        description="Local time (HH:MM) when Sabbath entry blocks start on Friday",
    )
    sabbath_end_local: Any = Field(
        default="18:00",
        description="Local time (HH:MM) when Sabbath entry blocks end on Saturday",
    )

    @field_validator("sabbath_start_local", "sabbath_end_local", mode="before")
    @classmethod
    def validate_sabbath_time(cls, v: Any) -> str:
        if isinstance(v, int):
            # YAML parses "18:00" as 1080 (18 * 60)
            hours = v // 60
            minutes = v % 60
            return f"{hours:02d}:{minutes:02d}"
        return str(v)
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
        default="",
        description="Path to the JSON file that stores synthetic stop records (auto-resolved if empty)",
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
        default=0.10,
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
    limit_loss_daily_pct: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Maximum loss allowed for the daily interval (0.05 = 5%).",
    )
    limit_loss_weekly_pct: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Maximum loss allowed for the weekly interval (0.15 = 15%).",
    )
    limit_loss_monthly_pct: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Maximum loss allowed for the monthly interval (0.25 = 25%).",
    )
    target_profit_daily_pct: float = Field(
        default=0.0,
        ge=0.0,
        description="Profit target for the daily interval (0.02 = 2%). 0 disables.",
    )
    target_profit_weekly_pct: float = Field(
        default=0.0,
        ge=0.0,
        description="Profit target for the weekly interval (0.05 = 5%). 0 disables.",
    )
    target_profit_monthly_pct: float = Field(
        default=0.0,
        ge=0.0,
        description="Profit target for the monthly interval (0.10 = 10%). 0 disables.",
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
    multi_position_enabled: bool = Field(
        default=True,
        description="Allow multiple positions concurrently for this profile.",
    )
    max_concurrent_positions: Optional[PositiveInt] = Field(
        default=None,
        description="Optional override for runtime.max_concurrent_positions. If set, overrides the global setting.",
    )
    max_daily_trades: Optional[PositiveInt] = Field(
        default=None,
        description="Maximum number of trade entries allowed per day per symbol.",
    )
    nuclear_overrides_enabled: bool = Field(
        default=False,
        description="Bypass all hard-coded safety ceilings. WARNING: HIGH RISK OF LIQUIDATION.",
    )
    max_risk_cap_override: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Override the hard 5% risk per trade cap. Only active in Nuclear Mode.",
    )
    compounding_cap_override: float = Field(
        default=10000.0,
        ge=0.0,
        description="Override the hard $10k compounding capital cap. Only active in Nuclear Mode.",
    )
    pyramid_cap_override: float = Field(
        default=750.0,
        ge=0.0,
        description="Override the hard $750 pyramid risk saturation cap. Only active in Nuclear Mode.",
    )
    meta_sci_enabled: bool = Field(
        default=False,
        description="Master toggle for Meta-SCI Auto Strategy logic within this profile.",
    )
    meta_sci_min_consensus: int = Field(
        default=1,
        ge=1,
        description="Minimum number of strategies that must agree on direction (consensus) for a Meta-SCI entry.",
    )
    meta_sci_exclude_list: list[str] = Field(
        default_factory=list,
        description="Strategies to exclude from the Meta-SCI ensemble (e.g., ['evolution']).",
    )

    def get_strategy_for_symbol(self, symbol: str) -> str:
        """
        Get the appropriate strategy for a given symbol.

        Priority: config.json globals (promoted by loader) → profile defaults → legacy fallback.
        Note: STRATEGY_* env vars are intentionally NOT checked here — they go stale
        because the Electron GUI writes to .env but config.json globals are the SSOT.

        Args:
            symbol: The trading symbol

        Returns:
            Strategy variant name
        """
        from tradebot_sci.utils.symbol_classifier import AssetClass, classify_symbol
        asset_class = classify_symbol(symbol)

        # 1. Check profile strategies (populated from config.json globals by loader)
        if self.strategies is not None:
            strategy_map = {
                AssetClass.CRYPTO: self.strategies.crypto,
                AssetClass.FOREX: self.strategies.forex,
                AssetClass.STOCKS: self.strategies.stocks,
                AssetClass.ETF: self.strategies.etf,
                AssetClass.METALS: self.strategies.metals,
                AssetClass.FUTURES: self.strategies.futures,
            }
            res = strategy_map.get(asset_class)
            if res:
                return res

        # 2. Fallback to legacy single strategy
        res = self.strategy_variant
        if res:
            return res
            
        # 3. Last Resort Fallback Map (Strictly Enforce Conductor for Forex)
        if asset_class == AssetClass.FOREX:
            return "forex_conductor"
        elif asset_class == AssetClass.CRYPTO:
            return "meta_sci"
        
        return "meta_sci"
class AppSettings(BaseModel):
    name: str = Field(default="tradebot-sci-enterprise")
    environment: str = Field(default="dev")
    profile_name: str = Field(default="intraday")


class ScheduleSession(BaseModel):
    name: str
    start: Any  # "HH:MM"
    end: Any    # "HH:MM"

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_time_string(cls, v: Any) -> str:
        if isinstance(v, int):
            hours = v // 60
            minutes = v % 60
            return f"{hours:02d}:{minutes:02d}"
        return str(v)


class ScheduleSettings(BaseModel):
    timezone: str = Field(default="America/New_York")
    sessions: list[ScheduleSession] = Field(default_factory=list)


class RoboCopSettings(BaseModel):
    combat_mode_enabled: bool = Field(
        default_factory=lambda: os.getenv("COMBAT_MODE_ENABLED", "True").lower() == "true",
        description="Bypass human delays (Session, Confirmation)"
    )
    fast_exit_enabled: bool = Field(
        default_factory=lambda: os.getenv("ROBO_FAST_EXIT_ENABLED", "True").lower() == "true"
    )
    chop_scalp_enabled: bool = Field(
        default_factory=lambda: os.getenv("ROBO_CHOP_SCALP_ENABLED", "True").lower() == "true"
    )
    runner_grace_enabled: bool = Field(
        default_factory=lambda: os.getenv("RUNNER_GRACE_ENABLED", "True").lower() == "true"
    )
    entry_score_threshold: float = Field(
        default_factory=lambda: float(os.getenv("ROBO_ENTRY_SCORE_THRESHOLD", "35.0"))
    )


class SafetySettings(BaseModel):
    """
    ⚠️  DEPRECATED — DO NOT ADD NEW FIELDS HERE ⚠️

    SafetySettings is a VESTIGIAL class from the old dual-config system where
    safety parameters lived in a separate top-level config.json["safety"] block
    and were read by code that called `settings.safety.*`.

    THE NEW CANONICAL APPROACH:
    ─────────────────────────────────────────────────────────────────────────
    1. Pick a profile in the GUI (e.g. forex_continuous).
    2. If "Profile Overrides" is ON, the profile's own values are the globals.
    3. All safety-related settings now live in TradingProfileSettings (models.py)
       and are stored in config.json["profiles"][<name>] OR in config.json["global"]
       (which is auto-promoted into the profile by the universal promotion loop
       in loader.py lines 223-238 when a profile key is absent).

    The fields in this class are kept only for backward compatibility with legacy
    code that still reads `settings.safety.xyz`.  They are NOT authoritative.
    For the real value, use: `settings.get_active_profile().xyz`

    DO NOT READ: settings.safety.* for any new code.
    DO READ:     settings.get_active_profile().*
    """
    emergency_stop_pct: float = Field(
        default_factory=lambda: float(os.getenv("EMERGENCY_STOP_PCT", "0.01")),
        ge=0.0
    )
    friction_fail_safe: bool = Field(
        default_factory=lambda: os.getenv("FRICTION_FAIL_SAFE", "False").lower() == "true"
    )
    friction_risk_cap: float = Field(default=0.02)
    vix_fail_safe: bool = Field(default=False)
    vix_risk_cap: float = Field(default=0.03)
    sabbath_astronomical: bool = Field(default=True)
    sabbath_city: str = Field(default="Atlanta")
    sabbath_enabled: bool = Field(
        default_factory=lambda: os.getenv("SABBATH_ENABLED", "True").lower() == "true"
    )
    sabbath_end_local: str = Field(default="18:00")
    sabbath_lat: float = Field(default=33.764)
    sabbath_lon: float = Field(default=-84.386)
    sabbath_start_local: str = Field(default="18:00")
    sabbath_timezone: str = Field(default="America/New_York")
    profile_pdt_guard_enabled: bool = Field(default=True)
    disable_friction_guard: bool = Field(default=True)

    # --- ATR & Armor ---
    safety_atr_shield_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_ATR_SHIELD_ENABLED", "True").lower() == "true"
    )
    breakeven_trail_pct: float = Field(
        default_factory=lambda: float(os.getenv("BREAKEVEN_TRAIL_PCT", "0.0"))
    )
    risk_reward_ratio: float = Field(
        default_factory=lambda: float(os.getenv("RISK_REWARD_RATIO", "0.0"))
    )

    # --- Advanced Exit Shields ---
    safety_sentiment_shield_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_SENTIMENT_SHIELD_ENABLED", "False").lower() == "true"
    )
    safety_volatility_veto_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_VOLATILITY_VETO_ENABLED", "False").lower() == "true"
    )
    safety_stale_sniper_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_STALE_SNIPER_ENABLED", "False").lower() == "true"
    )
    safety_stale_sniper_bars: int = Field(
        default_factory=lambda: int(os.getenv("SAFETY_STALE_SNIPER_BARS", "20"))
    )
    safety_flash_trap_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_FLASH_TRAP_ENABLED", "False").lower() == "true"
    )
    wealth_exit_gamma_enabled: bool = Field(
        default_factory=lambda: os.getenv("WEALTH_EXIT_GAMMA_ENABLED", "False").lower() == "true"
    )
    wealth_exit_blowoff_enabled: bool = Field(
        default_factory=lambda: os.getenv("WEALTH_EXIT_BLOWOFF_ENABLED", "False").lower() == "true"
    )
    wealth_exit_moonshot_enabled: bool = Field(
        default_factory=lambda: os.getenv("WEALTH_EXIT_MOONSHOT_ENABLED", "False").lower() == "true"
    )
    safety_regime_flip_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_REGIME_FLIP_ENABLED", "False").lower() == "true"
    )
    greedy_exit_max_hold_hours: float = Field(
        default_factory=lambda: float(os.getenv("GREEDY_EXIT_MAX_HOLD_HOURS", "8.0")),
        ge=0.0,
        description="Maximum hours before Greedy Exit forces a close (0 disables). "
                    "Trail tightens in the second half of this window.",
    )

    # --- Safety Suite 2.0 ---
    safety_drawdown_breaker_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_DRAWDOWN_BREAKER_ENABLED", "True").lower() == "true"
    )
    safety_session_lockout_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_SESSION_LOCKOUT_ENABLED", "True").lower() == "true"
    )
    safety_session_lockout_hour: int = Field(
        default_factory=lambda: int(os.getenv("SAFETY_SESSION_LOCKOUT_HOUR", "16"))
    )
    safety_opening_sentry_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_OPENING_SENTRY_ENABLED", "True").lower() == "true"
    )
    safety_greed_guard_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_GREED_GUARD_ENABLED", "True").lower() == "true"
    )
    safety_greed_guard_target: float = Field(
        default_factory=lambda: float(os.getenv("SAFETY_GREED_GUARD_TARGET", "100.0"))
    )
    safety_streak_breaker_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_STREAK_BREAKER_ENABLED", "True").lower() == "true"
    )
    safety_churn_burner_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_CHURN_BURNER_ENABLED", "True").lower() == "true"
    )
    safety_churn_burner_max: int = Field(
        default_factory=lambda: int(os.getenv("SAFETY_CHURN_BURNER_MAX", "5"))
    )
    safety_leverage_sentry_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_LEVERAGE_SENTRY_ENABLED", "False").lower() == "true"
    )
    safety_max_total_leverage: float = Field(
        default_factory=lambda: float(os.getenv("SAFETY_MAX_TOTAL_LEVERAGE", "3.0"))
    )
    safety_fee_shield_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_FEE_SHIELD_ENABLED", "True").lower() == "true"
    )
    safety_volatility_min_pct: float = Field(
        default_factory=lambda: float(os.getenv("SAFETY_VOLATILITY_MIN_PCT", "0.01"))
    )
    safety_volatility_max_pct: float = Field(
        default_factory=lambda: float(os.getenv("SAFETY_VOLATILITY_MAX_PCT", "5.0"))
    )
    safety_drawdown_max_pct: float = Field(
        default_factory=lambda: float(os.getenv("SAFETY_DRAWDOWN_MAX_PCT", "0.05")),
        description="Maximum drawdown from HWM before Drawdown Breaker triggers (0.05 = 5%).",
    )
    safety_streak_max_losses: int = Field(
        default_factory=lambda: int(os.getenv("SAFETY_STREAK_MAX_LOSSES", "3")),
        description="Consecutive losses before Streak Breaker triggers a cooldown pause.",
    )
    safety_greedy_min_age_seconds: int = Field(
        default_factory=lambda: int(os.getenv("SAFETY_GREEDY_MIN_AGE_SECONDS", "300")),
        description="Minimum position age (seconds) before Greedy Exit floor can trigger.",
    )
    safety_fee_rt_pct: float = Field(
        default_factory=lambda: float(os.getenv("SAFETY_FEE_RT_PCT", "0.003")),
        description="Estimated round-trip fee as decimal (0.003 = 0.3% OANDA spread). "
                    "Override via env: Gemini ~0.008, IBKR ~0.002.",
    )


class PerformanceSettings(BaseModel):
    compounding_cap_override: float = Field(default=100000.0)
    pyramid_cap_override: float = Field(default=750000.0)
    performance_mode: str = Field(
        default_factory=lambda: os.getenv("PERFORMANCE_MODE", "kelly,sniper,regime_sync,runner,sentiment")
    )
    trailing_stop_enabled: bool = Field(
        default_factory=lambda: os.getenv("TRAILING_STOP_ENABLED", "True").lower() == "true"
    )


class RiskSettings(BaseModel):
    """
    ⚠️  DEPRECATED — DO NOT ADD NEW FIELDS HERE ⚠️

    RiskSettings is a VESTIGIAL class from the old dual-config system where
    risk parameters lived in a separate top-level config.json["risk"] block
    and were read as `settings.risk.*`.

    THE NEW CANONICAL APPROACH:
    ─────────────────────────────────────────────────────────────────────────
    ALL risk settings now live in TradingProfileSettings (models.py) and are
    stored in config.json["profiles"][<name>] OR in config.json["global"].
    The loader auto-promotes global keys into profiles (loader.py:223-238).

    There is NO MORE distinction between "profile-level" and "global" settings
    for risk.  The active profile IS the single source of truth:

        profile = settings.get_active_profile()
        risk_pct = profile.risk_per_trade_pct   ← CORRECT
        risk_pct = settings.risk.risk_per_trade_pct  ← DEPRECATED (might be stale)

    In particular:
    - config.json["risk"]["risk_per_trade_pct"] is an OLD field. Ignore it.
    - config.json["global"]["risk_per_trade_pct"] is the current default.
    - config.json["profiles"][<name>]["risk_per_trade_pct"] overrides the default.

    The GUI's "Profile Overrides" toggle controls whether the profile's saved
    values replace the current globals when you switch profiles.

    DO NOT READ: settings.risk.* for any new code.
    DO READ:     settings.get_active_profile().*
    """
    base_risk_pct: float = Field(
        default_factory=lambda: float(os.getenv("PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT", "0.20"))
    )
    compound_profits: bool = Field(default=True)
    infinite_pyramiding: bool = Field(default=True)
    max_pyramid_entries: int = Field(default=3)
    pyramid_trigger_pct: float = Field(default=0.0001)
    pyramid_risk_load: float = Field(default=1.00)
    pyramid_risk_scale: float = Field(default=1.00)
    stagnation_exit_enabled: bool = Field(
        default_factory=lambda: os.getenv("STAGNATION_EXIT_ENABLED", "False").lower() == "true"
    )
    stagnation_exit_minutes: int = Field(
        default_factory=lambda: int(os.getenv("STAGNATION_EXIT_MINUTES", "60"))
    )
    chop_scalp_target_usd: float = Field(default=1.00)
    chop_strength_threshold: float = Field(default=0.5)
    smart_positions_enabled: bool = Field(
        default_factory=lambda: os.getenv("SMART_POSITIONS_ENABLED", "False").lower() == "true",
        description="Only allow new positions if Unrealized PnL > Risk of new trade."
    )

    # ── Promoted from profiles (global source of truth) ─────────
    risk_per_trade_pct: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="Standard risk per trade as a fraction of equity (e.g. 0.01 = 1.0%).",
    )
    risk_per_trade_dollars: float = Field(
        default=0.0, ge=0.0,
        description="Fixed risk per trade in account currency. Overrides pct when > 0.",
    )
    short_risk_pct: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="Risk percentage for short positions.",
    )
    aggressive_risk_per_trade_pct: float = Field(
        default=0.10, ge=0.0, le=1.0,
        description="Aggressive risk for high-confidence setups.",
    )
    max_exposure_pct: float = Field(
        default=0.40, ge=0.0, le=1.0,
        description="Maximum total risk across all open positions.",
    )
    limit_loss_daily_pct: float = Field(
        default=0.60, ge=0.0, le=1.0,
        description="Circuit breaker: stop trading for the day if hit.",
    )
    icc_auto_entry_enabled: bool = Field(default=False)
    icc_aggressive_mode: bool = Field(default=True)
    icc_entry_score_threshold: float = Field(default=60.0, ge=0.0, le=100.0)
    icc_auto_entry_require_sweep: bool = Field(default=False)
    icc_auto_entry_min_htf_strength: float = Field(default=0.4, ge=0.0, le=1.0)
    icc_confirmation_bars: int = Field(default=2, ge=1, le=10)
    icc_max_bars_after_sweep: int = Field(default=30, ge=1)
    icc_require_liquidity_grab: bool = Field(default=False)
    icc_strict_mode: bool = Field(default=False)
    icc_high_score_override_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    icc_two_signal_override_enabled: bool = Field(default=False)
    icc_auto_entry_cooldown_minutes: int = Field(default=15, ge=0)
    icc_auto_entry_min_score: float = Field(default=0.02, ge=0.0)
    icc_score_continuation_points: float = Field(default=60.0, ge=0.0, le=100.0)
    icc_score_sweep_points: float = Field(default=25.0, ge=0.0, le=100.0)
    icc_score_htf_ltf_align_points: float = Field(default=30.0, ge=0.0, le=100.0)
    icc_score_strong_htf_points: float = Field(default=15.0, ge=0.0, le=100.0)
    icc_score_phase_points: float = Field(default=5.0, ge=0.0, le=100.0)
    icc_score_indication_points: float = Field(default=10.0, ge=0.0, le=100.0)
    icc_score_htf_strength_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class RuntimeSettings(BaseModel):
    cancel_orders_on_start: bool = Field(
        default_factory=lambda: os.getenv("CANCEL_ORDERS_ON_START", "False").lower() == "true"
    )
    execute_trades: bool = Field(
        default_factory=lambda: os.getenv("EXECUTE_TRADES", "False").lower() == "true",
        description="Master toggle for live trade execution. If false, bot runs in simulation only."
    )
    flatten_on_exit: bool = Field(
        default_factory=lambda: os.getenv("FLATTEN_ON_EXIT", "False").lower() == "true"
    )
    intraday_flatten: bool = Field(
        default_factory=lambda: os.getenv("INTRADAY_FLATTEN", "False").lower() == "true",
        description="Flatten at session end for intraday mode",
    )
    allow_day_trades: bool = Field(
        default_factory=lambda: os.getenv("ALLOW_DAY_TRADES", "False").lower() == "true",
        description="When false, exits are blocked until the minimum hold duration elapses.",
    )
    min_hold_seconds: PositiveInt = Field(
        default_factory=lambda: int(os.getenv("MIN_HOLD_SECONDS", "300")),
        description="Minimum seconds a position must be held before exits or TP orders are permitted when day trades are disabled.",
    )
    min_equity_for_margin: float = Field(
        default_factory=lambda: float(os.getenv("MIN_EQUITY_FOR_MARGIN", "2000.0")),
        ge=0.0,
        description="Minimum NetLiquidation required before margin, short, or FX trades proceed.",
    )
    position_hold_store_path: str = Field(
        default_factory=lambda: os.getenv("POSITION_HOLD_STORE_PATH", ""),
        description="Path where position-open timestamps are persisted across restarts (auto-resolved if empty).",
    )
    allow_inherited_position: bool = Field(
        default_factory=lambda: os.getenv("ALLOW_INHERITED_POSITION", "False").lower() == "true",
        description="Allow runs to start with an existing broker position instead of auto-flattening",
    )
    pnl_timeframe: str = Field(
        default_factory=lambda: os.getenv("GUI_PNL_TIMEFRAME", "24h"),
        description="Default timeframe for PnL display in the GUI (holdings, 24h, week, month, year, all)"
    )
    time_format: str = Field(
        default_factory=lambda: os.getenv("GUI_TIME_FORMAT", "24h"),
        description="Time axis format for the chart display: '12h' (AM/PM) or '24h'."
    )
    global_default_risk_pct: float = Field(
        default_factory=lambda: float(os.getenv("GLOBAL_DEFAULT_RISK_PCT", "0.015")),
        ge=0.0,
        le=1.0,
        description="Global floor for risk per trade as a fraction of equity (e.g. 0.04 for 4%)."
    )
    # ... rest of fields can use internal defaults unless needed ...
    infer_position_hold_from_executions: bool = Field(default=False)
    infer_position_hold_lookback_days: int = Field(default=7, ge=1)
    scale_out_fraction: float = Field(
        default=0.95,  # Guillotine: close 95% at de-risk trigger
        ge=0.0,
        le=1.0
    )
    min_position_size_to_scale: float = Field(
        default=1.0,
        ge=0.0
    )
    emergency_stop_pct: float = Field(
        default_factory=lambda: float(os.getenv("EMERGENCY_STOP_PCT", "0.01")),
        ge=0.0
    )
    keep_alive_interval_seconds: int = Field(default=300, ge=0)
    strike_max_consecutive: PositiveInt = Field(default=3)
    strike_cooldown_cycles: PositiveInt = Field(default=3)
    guard_block_threshold: PositiveInt = Field(default=6)
    guard_block_cooldown_cycles: PositiveInt = Field(default=1)
    allow_local_stops: bool = Field(default=False)
    local_stop_symbols: list[str] = Field(default_factory=list)
    max_scale_ins_per_leg: int = Field(
        default_factory=lambda: int(os.getenv("MAX_SCALE_INS_PER_LEG", "2")),
        ge=0
    )
    multi_position_enabled: bool = Field(
        default_factory=lambda: os.getenv("MULTI_POSITION_ENABLED", "True").lower() == "true"
    )
    max_concurrent_positions: PositiveInt = Field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_POSITIONS", "1"))
    )
    auto_restart_on_error: bool = Field(
        default_factory=lambda: os.getenv("AUTO_RESTART_ON_ERROR", "False").lower() == "true"
    )
    auto_restart_stale_seconds: int = Field(
        default_factory=lambda: int(os.getenv("AUTO_RESTART_STALE_SECONDS", "300")),
        ge=30
    )
    auto_restart_min_uptime_seconds: int = Field(
        default_factory=lambda: int(os.getenv("AUTO_RESTART_MIN_UPTIME_SECONDS", "120")),
        ge=0
    )
    auto_restart_cooldown_seconds: int = Field(
        default_factory=lambda: int(os.getenv("AUTO_RESTART_COOLDOWN_SECONDS", "600")),
        ge=0
    )
    ws_server_port: PositiveInt = Field(
        default_factory=lambda: int(os.getenv("WS_SERVER_PORT", "8080")),
        description="Port for the bot's WebSocket server (default 8080)."
    )
    friday_fade_enabled: bool = Field(
        default_factory=lambda: os.getenv("FRIDAY_FADE_ENABLED", "True").lower() == "true",
        description="Global safety: Drops Forex risk to 0.25% after 12PM EST on Fridays."
    )
    gui_capital_display_mode: Literal["equity", "cash"] = Field(
        default_factory=lambda: os.getenv("GUI_CAPITAL_DISPLAY_MODE", "equity"),
        description="Dashboard display preference: 'equity' for total net worth, 'cash' for buying power."
    )


    simulation_risk_cap: float = Field(
        default_factory=lambda: float(os.getenv("SIMULATION_RISK_CAP", "1.0")),
        ge=0.0,
        le=1.0,
        description="Maximum allowed risk per trade as a fraction of equity (safety cap)."
    )

    # --- AI Commentary Settings ---
    commentary_enabled: bool = Field(
        default_factory=lambda: os.getenv("COMMENTARY_ENABLED", "True").lower() == "true",
        description="Master toggle for AI commentary feature."
    )
    commentary_policy: str = Field(
        default_factory=lambda: os.getenv("COMMENTARY_LLM_POLICY", "interval"),
        description="Commentary trigger policy: 'disabled', 'interval', 'schedule', or 'on_signal'."
    )
    commentary_interval_minutes: int = Field(
        default_factory=lambda: int(os.getenv("COMMENTARY_INTERVAL_MINUTES", "30")),
        ge=1,
        le=120,
        description="Interval in minutes between AI commentary updates (when policy='interval')."
    )
    commentary_daily_slots: str = Field(
        default_factory=lambda: os.getenv("COMMENTARY_LLM_DAILY_SLOTS", ""),
        description="Comma-separated HH:MM times for scheduled commentary (when policy='schedule')."
    )
    commentary_max_daily_calls: int = Field(
        default_factory=lambda: int(os.getenv("COMMENTARY_LLM_MAX_CALLS_PER_DAY", "12")),
        ge=1,
        description="Hard limit on AI API calls per day to prevent runaway costs."
    )


class Settings(BaseModel):
    app: AppSettings
    logging: LoggingSettings
    ai: AISettings
    market: MarketSettings
    profiles: Dict[str, TradingProfileSettings]
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    robocop: RoboCopSettings = Field(default_factory=RoboCopSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    broker: Optional[BrokerSettings] = None
    oanda: Optional[OandaSettings] = None
    paxos: Optional[PaxosSettings] = None
    kraken: Optional[KrakenSettings] = None

    def get_active_profile(self) -> TradingProfileSettings:
        profile_name = self.app.profile_name
        profile = self.profiles.get(profile_name)
        if profile:
            return profile

        # Fallback to first available profile if requested one is missing
        if self.profiles:
            first_profile_name = next(iter(self.profiles))
            logger.warning(
                f"[CONFIG] Profile '{profile_name}' not found. Falling back to '{first_profile_name}'. "
                f"Available profiles: {list(self.profiles.keys())}"
            )
            return self.profiles[first_profile_name]

        logger.error(f"[CONFIG] Profiles dictionary is EMPTY. Settings object: {self}")
        raise KeyError(f"Profile '{profile_name}' not found and no other profiles available.")


@lru_cache
def get_cached_settings(settings: Settings) -> Settings:
    return settings


class UserConfig:
    def _settings(self):
        from tradebot_sci.config.loader import get_settings
        return get_settings()

    @property
    def STRATEGY_VARIANT(self): 
        s = self._settings()
        return s.profiles.get(s.app.profile_name).strategy_variant
    @property
    def BASE_RISK_PCT(self):
        # DEPRECATED: reads from settings.risk (old dual-config). Use get_active_profile().risk_per_trade_pct
        s = self._settings(); return s.risk.base_risk_pct
    @property
    def COMPOUND_PROFITS(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.compound_profits
    @property
    def INFINITE_PYRAMIDING(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.infinite_pyramiding
    @property
    def MAX_PYRAMID_ENTRIES(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().max_pyramid_entries
        return self._settings().risk.max_pyramid_entries
    @property
    def PYRAMID_TRIGGER_PCT(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.pyramid_trigger_pct
    @property
    def PYRAMID_RISK_LOAD(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.pyramid_risk_load
    @property
    def PYRAMID_RISK_SCALE(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.pyramid_risk_scale
    @property
    def STAGNATION_EXIT_ENABLED(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.stagnation_exit_enabled
    @property
    def STAGNATION_EXIT_MINUTES(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.stagnation_exit_minutes
    @property
    def CHOP_SCALP_TARGET_USD(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.chop_scalp_target_usd
    @property
    def CHOP_STRENGTH_THRESHOLD(self):
        # DEPRECATED: reads from settings.risk. Use get_active_profile().* equivalent
        return self._settings().risk.chop_strength_threshold
    @property
    def COMBAT_MODE_ENABLED(self): return self._settings().robocop.combat_mode_enabled
    @property
    def ROBO_FAST_EXIT_ENABLED(self): return self._settings().robocop.fast_exit_enabled
    @property
    def CHOP_TP_EXIT_ENABLED(self): return self._settings().robocop.fast_exit_enabled # alias for now
    @property
    def CHOP_MAX_BARS(self): return 10
    @property
    def ROBO_CHOP_SCALP_ENABLED(self): return self._settings().robocop.chop_scalp_enabled
    @property
    def RUNNER_GRACE_ENABLED(self): return self._settings().robocop.runner_grace_enabled
    @property
    def ROBO_ENTRY_SCORE_THRESHOLD(self): return self._settings().robocop.entry_score_threshold
    @property
    def SMART_POSITIONS_ENABLED(self): return self._settings().risk.smart_positions_enabled
    @property
    def FRIDAY_FADE_ENABLED(self): return self._settings().runtime.friday_fade_enabled
    @property
    def STOP_ATR_MULTIPLIER(self) -> float:
        # config.json globals are the SSOT; env vars intentionally NOT
        # checked here to prevent stale values from overriding.
        s = self._settings()
        profile = s.profiles.get(s.app.profile_name)
        return getattr(profile, "stop_atr_multiplier", 1.5)

    @property
    def STABILITY_MODE_ACTIVE(self) -> bool:
        # config.json globals are the SSOT; env vars intentionally NOT
        # checked here to prevent stale values from overriding.
        s = self._settings()
        profile = s.profiles.get(s.app.profile_name)
        return getattr(profile, "stability_mode_active", False)

# Create a singleton instance to keep legacy code working
UserConfig = UserConfig()
