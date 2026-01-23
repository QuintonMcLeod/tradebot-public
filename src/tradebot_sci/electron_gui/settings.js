/**
 * Tradebot SCI Settings Interface
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => init());

// ═══════════════════════════════════════════════════════════
// STATE MANAGEMENT
// ═══════════════════════════════════════════════════════════

let envData = {};
let profilesContent = "";
let currentTab = 'system';
let subTabs = { brokers: 'ibkr', strategy: 'risk' };
let localChanges = {};
let changeCount = 0;

// ═══════════════════════════════════════════════════════════
// TOOLTIP LIBRARY - Detailed, layman-friendly explanations
// ═══════════════════════════════════════════════════════════

const TOOLTIPS = {
    // System Settings
    APP_PROFILE: "Trading profiles define which markets you trade (stocks, forex, crypto), how often the bot checks for opportunities, and when it's allowed to trade. Think of it like choosing between 'day trader mode' vs '24/7 crypto mode'.",
    STRATEGY_VARIANT: "The trading strategy determines HOW the bot decides to enter and exit trades. Each strategy has different rules - some are aggressive scalpers, others wait for perfect setups. Choose based on your risk tolerance and market conditions.",
    BOT_MODE: "Controls how the bot runs: 'Continuous' keeps trading forever until you stop it. 'Scheduled' only trades during specific hours (like market open). 'Iterations' runs a fixed number of trade cycles then stops.",
    EXECUTE_TRADES: "The master ON/OFF switch for real trading. When OFF, the bot analyzes markets and shows what it WOULD do, but never places actual orders. Perfect for testing strategies without risking real money.",
    GUI_AUTOSTART_BOT: "When enabled, the trading bot automatically starts running as soon as you open this application. When disabled, you'll need to manually click 'Start' to begin trading.",
    CONTINUOUS_MODE: "Keeps the bot running indefinitely without stopping between trading sessions. Useful for 24/7 crypto markets. Disable this if you want the bot to pause after each session.",

    // Timeframes
    CANDLE_TIMEFRAME: "The main chart timeframe the bot watches. '15m' means each candle represents 15 minutes of price action. Shorter timeframes (1m, 5m) = more trades but more noise. Longer (1h, 4h) = fewer but higher-quality signals.",
    HTF_TIMEFRAME: "Higher TimeFrame - the 'big picture' view. The bot checks this larger timeframe to understand the overall market direction (trending up, down, or sideways) before taking trades on the smaller timeframe.",
    LTF_TIMEFRAME: "Lower TimeFrame - used for precise entry timing. Once the higher timeframe confirms the trend, the bot watches this smaller timeframe to find the perfect moment to enter a trade.",

    // Trend Detection
    TREND_WINDOW: "How many candles back the bot looks to determine the trend direction. More candles = smoother, more reliable trend detection but slower to react to changes.",
    LTF_TREND_WINDOW: "Same as Trend Window but for the lower timeframe. Fewer candles here means faster reaction to short-term price moves.",
    TREND_SWING_LOOKBACK: "How many candles on each side must be lower/higher to identify a swing point (local high or low). Higher = fewer but more significant swing points identified.",
    TREND_MIN_SWINGS: "Minimum number of swing highs/lows needed to confirm a trend. More swings required = more confidence the trend is real, but slower to identify new trends.",
    TREND_STRENGTH_FLOOR: "Minimum trend strength (0-1) before the bot considers it tradeable. 0.25 means the trend must be at least 25% strong - prevents trading in weak, uncertain markets.",

    // Risk Management
    RISK_PER_TRADE_PCT: "How much of your account you're willing to lose on a single trade. 1% means if you have $10,000, you risk losing $100 max per trade. Higher = bigger profits AND losses. Most professionals use 1-2%.",
    SHORT_RISK_PCT: "Risk percentage specifically for short (betting price goes down) positions. Some traders use lower risk for shorts since losses are theoretically unlimited.",
    MAX_EXPOSURE_PCT: "Maximum total risk across ALL open positions combined. If set to 10% with a $10,000 account, total risk across all trades can't exceed $1,000.",
    MAX_DAILY_LOSS_PCT: "Safety circuit breaker - if you lose this percentage of your account in one day, the bot stops trading to prevent catastrophic losses. Like a daily loss limit at a casino.",
    RISK_PER_TRADE_DOLLARS: "Fixed dollar amount to risk per trade instead of percentage. Useful if you want consistent $50 or $100 risk regardless of account size.",
    MAX_LOSS_PER_TRADE_DOLLARS: "Absolute maximum dollars you can lose on any single trade, even if percentage calculation says otherwise. A hard safety cap.",

    // Position Management
    MULTI_POSITION_ENABLED: "Allow the bot to have multiple trades open at the same time across different symbols. When disabled, it finishes one trade before starting another.",
    MAX_CONCURRENT_POSITIONS: "Maximum number of trades that can be open simultaneously. More positions = more diversification but also more complexity and capital required.",

    // Pyramiding
    MAX_PYRAMID_ENTRIES: "Maximum times the bot can add to a winning position. 'Pyramiding' means buying more as a trade goes in your favor. 1 = no adding, just the initial entry.",
    PYRAMID_PROFIT_BUFFER_PCT: "Minimum profit percentage required before the bot will add to a position. Prevents adding too early before the trade proves itself.",
    PYRAMID_RISK_LOAD: "Risk percentage for the FIRST add to a winning position. Often set higher since the trade has already proven profitable.",
    PYRAMID_RISK_SCALE: "Risk percentage for subsequent adds after the first. Usually lower than Load since you're adding to an already-large position.",
    BREAKEVEN_TRAIL_AFTER_PYRAMIDS: "After this many pyramid adds, move your stop-loss to breakeven (entry price). Protects profits on scaled-up positions. 0 = disabled.",
    BREAKEVEN_TRAIL_PCT: "How far above breakeven to trail your stop. 0.003 = 0.3%, so if you bought at $100, stop moves to $100.30 instead of exactly $100.",

    // ICC Settings
    ICC_AUTO_ENTRY_ENABLED: "Enable automatic trade entries based on ICC (Indication-Correction-Continuation) signals. The core pattern recognition system.",
    ICC_AGGRESSIVE_MODE: "When enabled, the bot uses larger position sizes on high-confidence setups. More aggressive but higher risk/reward.",
    ICC_AUTO_ENTRY_REQUIRE_SWEEP: "Require a 'liquidity sweep' (price briefly breaks a level then reverses) before entering. These setups have higher win rates but occur less frequently.",
    ICC_AUTO_ENTRY_MIN_HTF_STRENGTH: "Minimum trend strength on higher timeframe before ICC entries are allowed. Filters out trades against weak or uncertain trends.",
    ICC_CONFIRMATION_BARS: "Number of candles to wait after a signal before confirming the entry. More bars = more confirmation but potentially worse entry price.",
    ICC_ENTRY_SCORE_THRESHOLD: "Minimum score (0-100) a setup must achieve before the bot will trade it. Higher = pickier about setups, fewer but better trades.",

    // ICC Scoring
    ICC_SCORE_CONTINUATION_POINTS: "Points awarded when price shows clear continuation in the trend direction after a correction. Key component of the ICC pattern.",
    ICC_SCORE_SWEEP_POINTS: "Points awarded for liquidity sweeps - when price briefly breaks support/resistance to trigger stop-losses before reversing. High-probability signal.",
    ICC_SCORE_HTF_LTF_ALIGN_POINTS: "Points when both higher and lower timeframes agree on direction. Alignment = higher probability trades.",
    ICC_SCORE_STRONG_HTF_POINTS: "Bonus points when the higher timeframe trend is particularly strong, not just present.",
    ICC_SCORE_PHASE_POINTS: "Points for favorable market phase - trending markets score higher than choppy/ranging markets.",
    ICC_SCORE_INDICATION_POINTS: "Points for the initial trend indication signal (break of structure). The first sign a trade setup may be forming.",

    // Exit Settings
    EXIT_ON_HTF_FLIP_ONLY_IF_LOSING: "Exit when higher timeframe trend flips, but ONLY if the trade is currently losing. Lets winners run if trend temporarily weakens.",
    AUTO_FLATTEN_ON_CLOSE: "Automatically close all positions at the end of the trading session. Prevents overnight/weekend risk.",
    TRAILING_STOP_ENABLED: "Enable trailing stops that follow price up (for longs) or down (for shorts), locking in profits as the trade moves in your favor.",
    TRAILING_STOP_MIN_PROFIT_PCT: "Minimum profit percentage before the trailing stop activates. Prevents premature stop-outs on normal price fluctuations.",
    STOP_ATR_MULTIPLIER: "Stop distance as multiple of ATR (Average True Range). ATR measures volatility - higher multiplier = wider stops, more room for price to move.",
    MIN_HOLD_HOURS: "Minimum hours to hold a position before allowing exits. Prevents panic-selling or premature exits. 0 = no minimum.",
    MAX_HOLD_HOURS: "Maximum hours to hold a position - force exit after this time regardless of profit/loss. 0 = hold forever if needed.",
    HTF_NEUTRAL_EXIT_BARS: "Exit if higher timeframe stays neutral (no clear trend) for this many bars. Prevents capital from being tied up in directionless markets.",

    // Broker Settings - IBKR
    IBKR_HOST: "IP address of your Interactive Brokers TWS or Gateway. Usually 127.0.0.1 if running on the same computer.",
    IBKR_PORT: "Connection port for IBKR. Use 7497 for Paper Trading in TWS, 7496 for Live TWS, 4002 for Paper Gateway, 4001 for Live Gateway.",
    IBKR_CLIENT_ID: "Unique identifier for this connection. If running multiple bots, each needs a different Client ID.",
    IBKR_ACCOUNT_ID: "Your IBKR account number. Found in Account Management. Format like DU1234567 (paper) or U1234567 (live).",
    IBKR_PAPER: "Enable paper trading mode - uses IBKR's simulated trading environment. Always test here before going live!",
    IBKR_READ_ONLY: "Read-only mode - bot can view positions and data but cannot place orders. Safe for monitoring.",
    IBKR_DEFAULT_CCY: "Default currency for the account. Usually USD but could be EUR, GBP, etc. for international accounts.",

    // Broker Settings - OANDA
    OANDA_ACCOUNT_ID: "Your OANDA account ID - found in your OANDA account settings or dashboard. Format like 101-001-1234567-001.",
    OANDA_API_KEY: "Your OANDA API access token. Generate one in OANDA's hub under 'Manage API Access'. Keep this secret!",
    OANDA_ENVIRONMENT: "Choose 'practice' for demo trading with fake money, or 'live' for real money trading. Always test in practice first!",
    OANDA_READ_ONLY: "Read-only mode - bot can fetch prices and positions but cannot place orders. Good for monitoring without trading.",

    // Broker Settings - CCXT/Coinbase
    CCXT_EXCHANGE: "The cryptocurrency exchange to connect to. Currently supports Coinbase and other CCXT-compatible exchanges.",
    CCXT_DEFAULT_TYPE: "Market type: 'spot' for regular buying/selling, 'swap' for perpetual futures, 'future' for dated futures contracts.",
    CCXT_API_KEY: "Your exchange API key - created in your exchange's API settings. Enables the bot to trade on your behalf.",
    CCXT_SECRET: "Your API secret key - paired with the API key. Never share this! Required to authenticate trades.",
    CCXT_SANDBOX: "Enable sandbox/testnet mode for the exchange. Trade with fake money to test your setup safely.",
    CCXT_ENABLE_RATE_LIMIT: "Automatically respect exchange rate limits to avoid getting temporarily banned for too many requests.",

    // Crypto Order Settings
    CRYPTO_FRACTIONAL_ENABLED: "Allow buying fractional amounts (0.001 BTC instead of whole coins). Required for expensive cryptos with small accounts.",
    CRYPTO_MIN_NOTIONAL_USD: "Minimum trade size in USD. Exchanges have minimums - trades below this will be rejected.",
    CRYPTO_MAX_NOTIONAL_USD: "Maximum trade size in USD. Safety limit to prevent accidentally huge orders.",
    CRYPTO_ORDER_TYPE: "Order execution type: 'LIMIT' places orders at specific prices (may not fill), 'MARKET' fills immediately at current price.",

    // Data Routing
    MARKET_DATA_MODE: "Where price data comes from: 'primary' (IBKR), 'alternative' (CCXT/Coinbase), 'oanda' for forex, or 'hybrid' for multiple sources.",
    BROKER_MODE: "Where orders are sent: 'primary' (IBKR), 'alternative' (crypto exchanges), 'oanda' for forex, or 'hybrid' for smart routing.",
    ALTERNATIVE_MARKET_DATA: "Backup data source if primary fails: 'mock' for testing, 'coinbase'/'ccxt' for crypto, 'oanda' for forex.",
    ALTERNATIVE_BROKER: "Backup broker if primary is unavailable: 'mock' for simulation, 'ccxt' for crypto, 'oanda' for forex.",

    // AI Settings
    TRADE_SCI_PROVIDER: "AI service for market analysis: 'gemini' (Google), 'openai' (GPT-4), 'claude' (Anthropic), 'deepseek', or 'openrouter' for multiple models.",
    TRADE_SCI_MODEL_NAME: "Specific AI model to use. Different models have different capabilities and costs. Default is optimized for trading analysis.",
    CHATGPT_KEY: "API key for your chosen AI provider. Get this from their developer portal. Required for AI-powered commentary.",
    AI_TEMPERATURE: "AI creativity level (0-2). Lower = more consistent/predictable responses. Higher = more creative but potentially erratic. 0.2 recommended.",
    AI_MAX_TOKENS: "Maximum response length from AI. Higher = more detailed analysis but costs more. 2048 is good for trading commentary.",
    COMMENTARY_LLM_POLICY: "When to request AI analysis: 'a_plus_or_4x' for best setups or 4x daily, 'a_plus_only' for only exceptional setups, 'interval' for fixed schedule.",
    COMMENTARY_LLM_DAILY_SLOTS: "Specific times to request AI commentary (HH:MM format). Example: 09:00,12:00,18:00 for market open, midday, and close.",
    COMMENTARY_LLM_MAX_CALLS_PER_DAY: "Maximum AI API calls per day. Prevents runaway costs. Each call provides fresh market analysis.",

    // Sabbath Settings
    SABBATH_ENABLED: "Block new trade entries during the Jewish Sabbath (Friday sunset to Saturday sunset). Existing positions are managed but no new trades opened.",
    SABBATH_ASTRONOMICAL: "Calculate Sabbath times using actual sunset based on your location, rather than fixed clock times. More accurate for religious observance.",
    SABBATH_TIMEZONE: "Your timezone for Sabbath calculations. Use IANA format like 'America/New_York' or 'Europe/London'.",
    SABBATH_LAT: "Your latitude for astronomical sunset calculations. Positive for North, negative for South. Example: 40.7128 for New York City.",
    SABBATH_LON: "Your longitude for astronomical calculations. Negative for West, positive for East. Example: -74.0060 for New York City.",
    SABBATH_START_LOCAL: "Fixed start time if not using astronomical mode. Default 18:00 (6 PM) is typical Friday evening start.",
    SABBATH_END_LOCAL: "Fixed end time if not using astronomical mode. Default 18:00 Saturday is about an hour after sunset in most locations.",

    // Session Settings
    SESSION_GATE_ENABLED: "Only allow trading during active market sessions. Prevents trading during low-liquidity periods.",
    SESSION_OVERLAP_START_HOUR: "Hour when active trading session starts (0-23). 12 = noon. Best to trade when major markets overlap.",
    SESSION_OVERLAP_END_HOUR: "Hour when active trading session ends (0-23). 16 = 4 PM. Position management continues after this.",
    SESSION_OVERLAP_TIMEZONE: "Timezone for session hours. UTC is universal, or use your local timezone.",
    AUTO_SCHEDULE_ENABLED: "Automatically switch between equity hours (9:30-4 ET) and crypto (24/7) based on what you're trading.",
};

const TABS = {
    system: { icon: 'dashboard', label: 'System', render: renderSystemTab },
    strategy: { icon: 'precision_manufacturing', label: 'Strategy', render: renderStrategyTab },
    brokers: { icon: 'lan', label: 'Brokers', render: renderBrokersTab },
    ai: { icon: 'auto_awesome', label: 'Intelligence', render: renderAITab },
    schedule: { icon: 'event_repeat', label: 'Schedule', render: renderScheduleTab },
    advanced: { icon: 'terminal', label: 'Advanced', render: renderAdvancedTab }
};

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

async function init() {
    setupGlobalEvents();

    // Load data from backend
    try {
        if (window.electronAPI) {
            envData = await window.electronAPI.readEnv() || {};
            profilesContent = await window.electronAPI.readProfiles() || "";
        }
    } catch (e) {
        console.error("Data load failed:", e);
    }

    switchTab('system');
}

function setupGlobalEvents() {
    // Navigation buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Window controls (with safety checks)
    const btnClose = document.getElementById('btn-close');
    const btnMinimize = document.getElementById('btn-minimize');
    const btnSave = document.getElementById('btn-save');
    const btnRevert = document.getElementById('btn-revert');
    const searchInput = document.getElementById('setting-search');

    if (btnClose) {
        btnClose.addEventListener('click', () => {
            if (window.electronAPI?.closeWindow) {
                window.electronAPI.closeWindow();
            }
        });
    }

    if (btnMinimize) {
        btnMinimize.addEventListener('click', () => {
            if (window.electronAPI?.minimizeWindow) {
                window.electronAPI.minimizeWindow();
            }
        });
    }

    if (btnSave) {
        btnSave.addEventListener('click', saveAll);
    }

    if (btnRevert) {
        btnRevert.addEventListener('click', () => {
            if (confirm("Discard all unsaved changes?")) location.reload();
        });
    }

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            if (currentTab === 'advanced') renderAdvancedTab(document.getElementById('tab-content'), e.target.value);
        });
    }
}

// ═══════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });

    const searchContainer = document.getElementById('search-container');
    if (searchContainer) {
        searchContainer.classList.toggle('hidden', tabId !== 'advanced');
    }
    renderTab();
}

function renderTab() {
    const container = document.getElementById('tab-content');
    if (!container) return;
    container.innerHTML = '';

    if (TABS[currentTab]) {
        try {
            TABS[currentTab].render(container);
        } catch (e) {
            console.error("Error rendering tab:", e);
            container.innerHTML = `<div style="color: red; padding: 20px;">Error rendering tab: ${e.message}</div>`;
        }
    } else {
        console.error("[SETTINGS] Tab not found in TABS:", currentTab);
        container.innerHTML = `<div style="color: orange; padding: 20px;">Tab "${currentTab}" not found</div>`;
    }
}

window.setSubTab = (category, tab) => {
    subTabs[category] = tab;
    renderTab();
};

// ═══════════════════════════════════════════════════════════
// UI BUILDERS
// ═══════════════════════════════════════════════════════════

function createSectionHeader(title, icon = null) {
    const header = document.createElement('div');
    header.className = 'settings-label text-glow-teal';
    header.innerHTML = icon
        ? `<span class="material-symbols-outlined">${icon}</span>${title}`
        : title;
    return header;
}

function createCard(title, desc, key, controlType, options = {}) {
    const card = document.createElement('div');
    card.className = 'control-card';

    card.innerHTML = `
        <div class="card-info">
            <span class="card-title">${title}</span>
            <span class="card-desc">${desc}</span>
        </div>
        <div class="card-control no-drag"></div>
    `;

    const controlContainer = card.querySelector('.card-control');
    const value = envData[key] || options.default || '';

    if (TOOLTIPS[key]) {
        card.addEventListener('mouseenter', (e) => showTooltip(e, key, TOOLTIPS[key]));
        card.addEventListener('mouseleave', hideTooltip);
    }

    if (controlType === 'toggle') {
        const toggle = document.createElement('div');
        toggle.className = `toggle ${value === 'true' ? 'toggle-active' : ''}`;
        toggle.addEventListener('click', () => {
            const active = toggle.classList.toggle('toggle-active');
            updateValue(key, active ? 'true' : 'false');
        });
        controlContainer.appendChild(toggle);
    }
    else if (controlType === 'input') {
        const input = document.createElement('input');
        input.type = options.password ? 'password' : (options.number ? 'number' : 'text');
        input.className = 'input-field';
        input.value = value;
        input.placeholder = options.placeholder || '';
        if (options.min !== undefined) input.min = options.min;
        if (options.max !== undefined) input.max = options.max;
        if (options.step !== undefined) input.step = options.step;
        input.addEventListener('change', (e) => updateValue(key, e.target.value));
        controlContainer.appendChild(input);
    }
    else if (controlType === 'dropdown') {
        const select = document.createElement('select');
        select.className = 'input-field appearance-none';
        options.items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.value;
            opt.textContent = item.label;
            opt.selected = item.value === value;
            select.appendChild(opt);
        });
        select.addEventListener('change', (e) => updateValue(key, e.target.value));
        controlContainer.appendChild(select);
    }

    return card;
}

function createSliderCard(title, desc, key, min, max, step, unit = '%') {
    const card = document.createElement('div');
    card.className = 'slider-card';
    const value = envData[key] || min;

    card.innerHTML = `
        <div class="slider-header">
            <div>
                <div class="slider-title">${title}</div>
                <div class="slider-desc">${desc}</div>
            </div>
            <div class="slider-value">${value}<span class="slider-value-small">${unit}</span></div>
        </div>
        <input type="range" class="slider-input" min="${min}" max="${max}" step="${step}" value="${value}">
        <div class="slider-key">${key}</div>
    `;

    const slider = card.querySelector('.slider-input');
    const valueDisplay = card.querySelector('.slider-value');

    slider.addEventListener('input', (e) => {
        valueDisplay.innerHTML = `${e.target.value}<span class="slider-value-small">${unit}</span>`;
        updateValue(key, e.target.value);
    });

    return card;
}

function createSubNav(items, category) {
    const nav = document.createElement('div');
    nav.className = 'sub-nav';

    items.forEach(item => {
        const btn = document.createElement('button');
        btn.className = `sub-nav-btn ${subTabs[category] === item.id ? 'active' : ''}`;
        btn.textContent = item.label;
        btn.onclick = () => setSubTab(category, item.id);
        nav.appendChild(btn);
    });

    return nav;
}

function createDivider() {
    const div = document.createElement('div');
    div.className = 'section-divider';
    return div;
}

function createWarningBox(text) {
    const box = document.createElement('div');
    box.className = 'warning-box';
    box.innerHTML = `
        <span class="material-symbols-outlined">warning</span>
        <div class="warning-box-content">${text}</div>
    `;
    return box;
}

// ═══════════════════════════════════════════════════════════
// TAB RENDERERS
// ═══════════════════════════════════════════════════════════

function renderSystemTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    // Core Runtime
    section.appendChild(createSectionHeader('Core Runtime', 'dashboard'));

    section.appendChild(createCard('Active Profile', 'Select symbol universe & trading cadence', 'APP_PROFILE', 'dropdown', {
        items: [
            { value: 'auto_schedule', label: 'Auto (Equities/Crypto)' },
            { value: 'forex_intraday', label: 'Forex Intraday' },
            { value: 'forex_oanda', label: 'OANDA Forex' },
            { value: 'crypto_247', label: 'Crypto 24/7' },
            { value: 'intraday', label: 'Standard Intraday' },
            { value: 'coinbase_futures', label: 'Coinbase Futures' },
            { value: 'coinbase_futures_nano', label: 'Coinbase Nano Futures' }
        ]
    }));

    section.appendChild(createCard('Strategy Variant', 'Trading strategy algorithm', 'STRATEGY_VARIANT', 'dropdown', {
        items: [
            { value: 'rubberband_reaper', label: 'Rubberband Reaper (Anti-Martingale)' },
            { value: 'robocop', label: 'RoboCop (Aggressive ICC)' },
            { value: 'evolution', label: 'Robot Evolution (NTZ Scalper)' },
            { value: 'quantum', label: 'Quantum (Trend Following)' },
            { value: 'mean_reversion', label: 'Mean Reversion (Bollinger/RSI)' },
            { value: 'hyper_scalper', label: 'HyperScalper (EMA Crossover)' },
            { value: 'london_breakout', label: 'London Breakout (Session)' },
            { value: 'volatility_breakout', label: 'Volatility Breakout' },
            { value: 'aggregator', label: 'Singularity Aggregator (Multi-Strategy)' }
        ],
        default: 'rubberband_reaper'
    }));

    section.appendChild(createCard('Execution Mode', 'How the bot cycles through iterations', 'BOT_MODE', 'dropdown', {
        items: [
            { value: 'continuous', label: 'Continuous Loop' },
            { value: 'scheduled', label: 'Session Windows' },
            { value: 'iterations', label: 'Fixed Iterations' }
        ]
    }));

    section.appendChild(createCard('Live Trading', 'Master switch for real order execution', 'EXECUTE_TRADES', 'toggle'));
    section.appendChild(createCard('Auto-Start Bot', 'Launch bot automatically with GUI', 'GUI_AUTOSTART_BOT', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Continuous Mode', 'Keep runtime alive indefinitely', 'CONTINUOUS_MODE', 'toggle'));

    section.appendChild(createDivider());

    // Timeframes
    section.appendChild(createSectionHeader('Timeframes', 'schedule'));

    section.appendChild(createCard('Candle Timeframe', 'Primary data timeframe', 'CANDLE_TIMEFRAME', 'dropdown', {
        items: [
            { value: '1m', label: '1 Minute' },
            { value: '5m', label: '5 Minutes' },
            { value: '15m', label: '15 Minutes' },
            { value: '1h', label: '1 Hour' },
            { value: '4h', label: '4 Hours' }
        ],
        default: '15m'
    }));

    section.appendChild(createCard('HTF Timeframe', 'Higher timeframe for trend analysis', 'HTF_TIMEFRAME', 'dropdown', {
        items: [
            { value: '15m', label: '15 Minutes' },
            { value: '1h', label: '1 Hour' },
            { value: '4h', label: '4 Hours' },
            { value: '1d', label: 'Daily' }
        ],
        default: '1h'
    }));

    section.appendChild(createCard('LTF Timeframe', 'Lower timeframe for entry precision', 'LTF_TIMEFRAME', 'dropdown', {
        items: [
            { value: '1m', label: '1 Minute' },
            { value: '5m', label: '5 Minutes' },
            { value: '15m', label: '15 Minutes' }
        ],
        default: '5m'
    }));

    section.appendChild(createDivider());

    // Trend Detection
    section.appendChild(createSectionHeader('Trend Detection', 'trending_up'));

    section.appendChild(createCard('Trend Window', 'Candles for HTF trend analysis', 'TREND_WINDOW', 'input', { number: true, default: '12', min: 5, max: 50 }));
    section.appendChild(createCard('LTF Trend Window', 'Candles for LTF trend analysis', 'LTF_TREND_WINDOW', 'input', { number: true, default: '8', min: 3, max: 30 }));
    section.appendChild(createCard('Swing Lookback', 'Fractal lookback for swing detection', 'TREND_SWING_LOOKBACK', 'input', { number: true, default: '2', min: 1, max: 5 }));
    section.appendChild(createCard('Min Swings', 'Minimum swings for trend classification', 'TREND_MIN_SWINGS', 'input', { number: true, default: '2', min: 1, max: 5 }));
    section.appendChild(createCard('Strength Floor', 'Minimum strength for non-neutral trend', 'TREND_STRENGTH_FLOOR', 'input', { number: true, default: '0.25', min: 0, max: 1, step: 0.05 }));

    container.appendChild(section);
}

function renderStrategyTab(container) {
    // Sub-navigation
    container.appendChild(createSubNav([
        { id: 'risk', label: 'Risk & Sizing' },
        { id: 'pyramid', label: 'Pyramiding' },
        { id: 'icc', label: 'ICC Scoring' },
        { id: 'exits', label: 'Exit Logic' },
        { id: 'yaml', label: 'YAML Editor' }
    ], 'strategy'));

    const section = document.createElement('div');
    section.className = 'settings-section';

    if (subTabs.strategy === 'risk') {
        section.appendChild(createSectionHeader('Risk Management', 'account_balance'));

        // Slider Grid
        const grid = document.createElement('div');
        grid.className = 'card-grid';
        grid.appendChild(createSliderCard('Risk Per Trade', 'Percentage of equity', 'RISK_PER_TRADE_PCT', 0.1, 5.0, 0.1, '%'));
        grid.appendChild(createSliderCard('Short Risk', 'Risk for short positions', 'SHORT_RISK_PCT', 0.1, 5.0, 0.1, '%'));
        grid.appendChild(createSliderCard('Max Exposure', 'Total open risk limit', 'MAX_EXPOSURE_PCT', 5, 100, 5, '%'));
        grid.appendChild(createSliderCard('Max Daily Loss', 'Daily loss circuit breaker', 'MAX_DAILY_LOSS_PCT', 1, 20, 1, '%'));
        section.appendChild(grid);

        section.appendChild(createCard('Fixed Risk ($)', 'Fixed dollar risk (overrides %)', 'RISK_PER_TRADE_DOLLARS', 'input', { number: true, placeholder: '0.00' }));
        section.appendChild(createCard('Max Loss Per Trade ($)', 'Hard cap per trade', 'MAX_LOSS_PER_TRADE_DOLLARS', 'input', { number: true, default: '500' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Position Management', 'layers'));

        section.appendChild(createCard('Multi-Position', 'Trade multiple symbols simultaneously', 'MULTI_POSITION_ENABLED', 'toggle'));
        section.appendChild(createCard('Max Concurrent Positions', 'Maximum open positions', 'MAX_CONCURRENT_POSITIONS', 'input', { number: true, default: '1', min: 1, max: 10 }));

    } else if (subTabs.strategy === 'pyramid') {
        section.appendChild(createSectionHeader('Pyramid Configuration', 'stacked_line_chart'));

        section.appendChild(createCard('Max Pyramid Entries', 'Total entries per position', 'MAX_PYRAMID_ENTRIES', 'input', { number: true, default: '6', min: 1, max: 20 }));
        section.appendChild(createCard('Profit Buffer %', 'Min profit before first add', 'PYRAMID_PROFIT_BUFFER_PCT', 'input', { number: true, default: '0.0015', min: 0, max: 0.05, step: 0.0005 }));

        const pyramidGrid = document.createElement('div');
        pyramidGrid.className = 'card-grid';
        pyramidGrid.appendChild(createSliderCard('Load Risk', 'First add risk %', 'PYRAMID_RISK_LOAD', 5, 100, 5, '%'));
        pyramidGrid.appendChild(createSliderCard('Scale Risk', 'Subsequent adds risk %', 'PYRAMID_RISK_SCALE', 5, 50, 5, '%'));
        section.appendChild(pyramidGrid);

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Breakeven Trail', 'shield'));

        section.appendChild(createCard('Trail After N Pyramids', '0 = disabled', 'BREAKEVEN_TRAIL_AFTER_PYRAMIDS', 'input', { number: true, default: '1', min: 0, max: 10 }));
        section.appendChild(createCard('Trail Percentage', 'Above breakeven (0.003 = 0.3%)', 'BREAKEVEN_TRAIL_PCT', 'input', { number: true, default: '0.003', min: 0, max: 0.05, step: 0.001 }));

    } else if (subTabs.strategy === 'icc') {
        section.appendChild(createSectionHeader('ICC Auto-Entry', 'auto_mode'));

        section.appendChild(createCard('ICC Auto-Entry', 'Auto-enter on valid signals', 'ICC_AUTO_ENTRY_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Aggressive Mode', 'Enable aggressive sizing', 'ICC_AGGRESSIVE_MODE', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Require Sweep', 'Must have liquidity sweep', 'ICC_AUTO_ENTRY_REQUIRE_SWEEP', 'toggle'));
        section.appendChild(createCard('Min HTF Strength', 'Minimum trend strength', 'ICC_AUTO_ENTRY_MIN_HTF_STRENGTH', 'input', { number: true, default: '0.25', min: 0, max: 1, step: 0.05 }));
        section.appendChild(createCard('Confirmation Bars', 'Bars to confirm signal', 'ICC_CONFIRMATION_BARS', 'input', { number: true, default: '2', min: 1, max: 5 }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('ICC Scoring Weights', 'leaderboard'));

        section.appendChild(createCard('Entry Score Threshold', 'Minimum score for entry', 'ICC_ENTRY_SCORE_THRESHOLD', 'input', { number: true, default: '35', min: 0, max: 100 }));

        const scoreGrid = document.createElement('div');
        scoreGrid.className = 'card-grid';
        scoreGrid.appendChild(createSliderCard('Continuation', 'Points for continuation', 'ICC_SCORE_CONTINUATION_POINTS', 0, 100, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Sweep', 'Points for liquidity sweep', 'ICC_SCORE_SWEEP_POINTS', 0, 50, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('HTF/LTF Align', 'Points for alignment', 'ICC_SCORE_HTF_LTF_ALIGN_POINTS', 0, 50, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Strong HTF', 'Points for strong trend', 'ICC_SCORE_STRONG_HTF_POINTS', 0, 30, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Phase', 'Points for good phase', 'ICC_SCORE_PHASE_POINTS', 0, 20, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Indication', 'Points for indication', 'ICC_SCORE_INDICATION_POINTS', 0, 20, 5, 'pts'));
        section.appendChild(scoreGrid);

    } else if (subTabs.strategy === 'exits') {
        section.appendChild(createSectionHeader('Exit Configuration', 'exit_to_app'));

        section.appendChild(createCard('HTF Flip Exit (Loss Only)', 'Exit on flip only if losing', 'EXIT_ON_HTF_FLIP_ONLY_IF_LOSING', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Auto-Flatten on Close', 'Flatten positions at session end', 'AUTO_FLATTEN_ON_CLOSE', 'toggle'));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Trailing Stop', 'trending_down'));

        section.appendChild(createCard('Trailing Stop Enabled', 'Enable trailing stop logic', 'TRAILING_STOP_ENABLED', 'toggle'));
        section.appendChild(createCard('Min Profit to Trail', 'Activate at this profit %', 'TRAILING_STOP_MIN_PROFIT_PCT', 'input', { number: true, default: '1.0', min: 0, max: 10, step: 0.5 }));
        section.appendChild(createCard('Stop ATR Multiplier', 'Distance from structure', 'STOP_ATR_MULTIPLIER', 'input', { number: true, default: '1.5', min: 0.5, max: 3, step: 0.1 }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Hold Time Rules', 'timer'));

        section.appendChild(createCard('Min Hold Hours', '0 = disabled', 'MIN_HOLD_HOURS', 'input', { number: true, default: '0', min: 0, max: 48 }));
        section.appendChild(createCard('Max Hold Hours', '0 = disabled', 'MAX_HOLD_HOURS', 'input', { number: true, default: '0', min: 0, max: 168 }));
        section.appendChild(createCard('HTF Neutral Exit Bars', 'Exit after N neutral bars', 'HTF_NEUTRAL_EXIT_BARS', 'input', { number: true, default: '48', min: 0, max: 200 }));

    } else if (subTabs.strategy === 'yaml') {
        section.appendChild(createSectionHeader('Profiles YAML Editor', 'code'));
        section.appendChild(createWarningBox('<strong>Warning:</strong> Direct YAML editing. Invalid syntax will break the bot. Use the other tabs for safer configuration.'));

        const editor = document.createElement('textarea');
        editor.id = 'profiles-editor';
        editor.value = profilesContent;
        editor.addEventListener('input', (e) => {
            profilesContent = e.target.value;
            localChanges['_profiles_'] = true;
            updateChangeCounter();
        });
        section.appendChild(editor);
    }

    container.appendChild(section);
}

function renderBrokersTab(container) {
    // Sub-navigation
    container.appendChild(createSubNav([
        { id: 'ibkr', label: 'Interactive Brokers' },
        { id: 'oanda', label: 'OANDA Forex' },
        { id: 'ccxt', label: 'Coinbase / CCXT' },
        { id: 'routing', label: 'Data Routing' }
    ], 'brokers'));

    const section = document.createElement('div');
    section.className = 'settings-section';

    if (subTabs.brokers === 'ibkr') {
        section.appendChild(createSectionHeader('IBKR Connection', 'lan'));

        section.appendChild(createCard('Host', 'TWS/Gateway IP address', 'IBKR_HOST', 'input', { default: '127.0.0.1' }));
        section.appendChild(createCard('Port', '7497 (Paper) / 4001 (Live Gateway)', 'IBKR_PORT', 'input', { number: true, default: '7497' }));
        section.appendChild(createCard('Client ID', 'Unique connection identifier', 'IBKR_CLIENT_ID', 'input', { number: true, default: '1' }));
        section.appendChild(createCard('Account ID', 'Specific sub-account', 'IBKR_ACCOUNT_ID', 'input'));
        section.appendChild(createCard('Paper Trading', 'Use paper trading mode', 'IBKR_PAPER', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Read Only', 'Monitor mode only (no orders)', 'IBKR_READ_ONLY', 'toggle'));
        section.appendChild(createCard('Default Currency', 'Base currency for positions', 'IBKR_DEFAULT_CCY', 'input', { default: 'USD' }));

    } else if (subTabs.brokers === 'oanda') {
        section.appendChild(createSectionHeader('OANDA Forex Connection', 'currency_exchange'));

        section.appendChild(createCard('Account ID', 'Your OANDA account number', 'OANDA_ACCOUNT_ID', 'input', { placeholder: '101-001-1234567-001' }));
        section.appendChild(createCard('API Key', 'OANDA API access token', 'OANDA_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('Environment', 'Trading environment', 'OANDA_ENVIRONMENT', 'dropdown', {
            items: [
                { value: 'practice', label: 'Practice (Demo)' },
                { value: 'live', label: 'Live (Real Money)' }
            ],
            default: 'practice'
        }));
        section.appendChild(createCard('Read Only', 'Monitor only (no trading)', 'OANDA_READ_ONLY', 'toggle', { default: 'true' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('OANDA Info', 'info'));

        const infoBox = document.createElement('div');
        infoBox.className = 'warning-box';
        infoBox.style.borderColor = 'rgba(20, 184, 166, 0.3)';
        infoBox.innerHTML = `
            <span class="material-symbols-outlined" style="color: var(--accent);">lightbulb</span>
            <div class="warning-box-content">
                <strong>Getting Started with OANDA:</strong><br>
                1. Create an OANDA account at oanda.com<br>
                2. Go to "Manage API Access" in your account settings<br>
                3. Generate a new API token and copy it here<br>
                4. Your Account ID is shown in your account dashboard<br>
                5. Always test with Practice mode first!
            </div>
        `;
        section.appendChild(infoBox);

    } else if (subTabs.brokers === 'ccxt') {
        section.appendChild(createSectionHeader('Coinbase / CCXT Engine', 'currency_bitcoin'));

        section.appendChild(createCard('Exchange ID', 'Provider name', 'CCXT_EXCHANGE', 'input', { default: 'coinbase' }));
        section.appendChild(createCard('Market Type', 'Asset class', 'CCXT_DEFAULT_TYPE', 'dropdown', {
            items: [
                { value: 'spot', label: 'Spot' },
                { value: 'swap', label: 'Swap' },
                { value: 'future', label: 'Future' }
            ]
        }));
        section.appendChild(createCard('API Key', 'Access identifier', 'CCXT_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('API Secret', 'Secure key', 'CCXT_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Sandbox Mode', 'Enable testnet', 'CCXT_SANDBOX', 'toggle'));
        section.appendChild(createCard('Rate Limit', 'Built-in rate limiting', 'CCXT_ENABLE_RATE_LIMIT', 'toggle', { default: 'true' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Crypto Order Settings', 'paid'));

        section.appendChild(createCard('Fractional Enabled', 'Allow fractional sizing', 'CRYPTO_FRACTIONAL_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Min Notional (USD)', 'Minimum trade size', 'CRYPTO_MIN_NOTIONAL_USD', 'input', { number: true, default: '20' }));
        section.appendChild(createCard('Max Notional (USD)', 'Maximum trade size', 'CRYPTO_MAX_NOTIONAL_USD', 'input', { number: true, default: '1000000' }));
        section.appendChild(createCard('Order Type', 'Limit vs Market', 'CRYPTO_ORDER_TYPE', 'dropdown', {
            items: [
                { value: 'LIMIT', label: 'Limit (Safer)' },
                { value: 'MARKET', label: 'Market (Guaranteed Fill)' }
            ]
        }));

    } else if (subTabs.brokers === 'routing') {
        section.appendChild(createSectionHeader('Data & Execution Routing', 'route'));

        section.appendChild(createCard('Market Data Mode', 'Primary data source', 'MARKET_DATA_MODE', 'dropdown', {
            items: [
                { value: 'primary', label: 'Primary (IBKR)' },
                { value: 'oanda', label: 'OANDA Forex' },
                { value: 'alternative', label: 'Alternative (CCXT)' },
                { value: 'hybrid', label: 'Hybrid' },
                { value: 'coinbase_futures', label: 'Coinbase Futures' }
            ]
        }));
        section.appendChild(createCard('Broker Mode', 'Execution routing', 'BROKER_MODE', 'dropdown', {
            items: [
                { value: 'primary', label: 'Primary (IBKR)' },
                { value: 'oanda', label: 'OANDA Forex' },
                { value: 'alternative', label: 'Alternative (CCXT)' },
                { value: 'hybrid', label: 'Hybrid' },
                { value: 'coinbase_futures', label: 'Coinbase Futures' }
            ]
        }));
        section.appendChild(createCard('Alternative Data', 'Fallback data source', 'ALTERNATIVE_MARKET_DATA', 'dropdown', {
            items: [
                { value: 'mock', label: 'Mock' },
                { value: 'oanda', label: 'OANDA' },
                { value: 'coinbase', label: 'Coinbase' },
                { value: 'ccxt', label: 'CCXT' }
            ]
        }));
        section.appendChild(createCard('Alternative Broker', 'Fallback execution', 'ALTERNATIVE_BROKER', 'dropdown', {
            items: [
                { value: 'mock', label: 'Mock' },
                { value: 'oanda', label: 'OANDA' },
                { value: 'ccxt', label: 'CCXT' },
                { value: 'coinbase_futures', label: 'Coinbase Futures' }
            ]
        }));
    }

    container.appendChild(section);
}

function renderAITab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('AI Provider', 'smart_toy'));

    section.appendChild(createCard('AI Provider', 'Backend service', 'TRADE_SCI_PROVIDER', 'dropdown', {
        items: [
            { value: 'gemini', label: 'Google Gemini Pro' },
            { value: 'openai', label: 'OpenAI (GPT-4)' },
            { value: 'claude', label: 'Anthropic Claude' },
            { value: 'deepseek', label: 'DeepSeek' },
            { value: 'openrouter', label: 'OpenRouter' }
        ]
    }));

    section.appendChild(createCard('Model Name', 'e.g., gemini-1.5-pro-002', 'TRADE_SCI_MODEL_NAME', 'input'));
    section.appendChild(createCard('API Key', 'Provider authentication', 'CHATGPT_KEY', 'input', { password: true }));
    section.appendChild(createCard('Temperature', 'Response randomness (0-2)', 'AI_TEMPERATURE', 'input', { number: true, default: '0.2', min: 0, max: 2, step: 0.1 }));
    section.appendChild(createCard('Max Tokens', 'Response length limit', 'AI_MAX_TOKENS', 'input', { number: true, default: '2048' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('AI Commentary', 'comment'));

    section.appendChild(createCard('Commentary Policy', 'When to invoke AI', 'COMMENTARY_LLM_POLICY', 'dropdown', {
        items: [
            { value: 'a_plus_or_4x', label: 'A+ Setup or 4x Daily' },
            { value: 'a_plus_only', label: 'A+ Setup Only' },
            { value: 'interval', label: 'Fixed Interval' }
        ]
    }));
    section.appendChild(createCard('Daily Slots', 'Comma-separated HH:MM', 'COMMENTARY_LLM_DAILY_SLOTS', 'input', { placeholder: '09:00,12:00,18:00,22:00' }));
    section.appendChild(createCard('Max Daily Calls', 'API cost cap', 'COMMENTARY_LLM_MAX_CALLS_PER_DAY', 'input', { number: true, default: '20' }));

    container.appendChild(section);
}

function renderScheduleTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('Sabbath Configuration', 'synagogue'));

    // City Resolver
    const resolver = document.createElement('div');
    resolver.className = 'city-resolver';
    resolver.innerHTML = `
        <div style="flex: 1;">
            <label style="display: block; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Location Resolver</label>
            <input type="text" id="city-input" placeholder="Enter City (e.g. New York)" class="input-field" style="width: 100%;">
        </div>
        <button id="btn-resolve">Resolve</button>
    `;
    section.appendChild(resolver);

    section.appendChild(createCard('Enable Sabbath', 'Block trades during Sabbath', 'SABBATH_ENABLED', 'toggle'));
    section.appendChild(createCard('Astronomical Mode', 'Use actual sunset times', 'SABBATH_ASTRONOMICAL', 'toggle'));
    section.appendChild(createCard('Timezone', 'IANA zone name', 'SABBATH_TIMEZONE', 'input', { default: 'America/New_York' }));
    section.appendChild(createCard('Latitude', 'Decimal coordinate', 'SABBATH_LAT', 'input'));
    section.appendChild(createCard('Longitude', 'Decimal coordinate', 'SABBATH_LON', 'input'));
    section.appendChild(createCard('Start Time', 'Friday sunset (HH:MM)', 'SABBATH_START_LOCAL', 'input', { default: '18:00' }));
    section.appendChild(createCard('End Time', 'Saturday sunset (HH:MM)', 'SABBATH_END_LOCAL', 'input', { default: '18:00' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Session Gate', 'access_time'));

    section.appendChild(createCard('Session Gate Enabled', 'Enforce session health checks', 'SESSION_GATE_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Overlap Start Hour', 'Active session start (0-23)', 'SESSION_OVERLAP_START_HOUR', 'input', { number: true, default: '12', min: 0, max: 23 }));
    section.appendChild(createCard('Overlap End Hour', 'Active session end (0-23)', 'SESSION_OVERLAP_END_HOUR', 'input', { number: true, default: '16', min: 0, max: 23 }));
    section.appendChild(createCard('Session Timezone', 'For overlap hours', 'SESSION_OVERLAP_TIMEZONE', 'input', { default: 'UTC' }));
    section.appendChild(createCard('Auto Schedule', 'Auto switch equities/crypto', 'AUTO_SCHEDULE_ENABLED', 'toggle'));

    container.appendChild(section);

    // City resolver event
    resolver.querySelector('#btn-resolve').addEventListener('click', async () => {
        const city = resolver.querySelector('#city-input').value;
        if (!city) return;

        const btn = resolver.querySelector('#btn-resolve');
        btn.textContent = 'RESOLVING...';

        const res = await window.electronAPI.resolveCity(city);
        if (res) {
            updateValue('SABBATH_LAT', res.lat.toString());
            updateValue('SABBATH_LON', res.lon.toString());
            updateValue('SABBATH_TIMEZONE', res.tz);
            renderTab();
        } else {
            alert("City not found. Please enter Lat/Lon manually.");
            btn.textContent = 'RESOLVE';
        }
    });
}

function renderAdvancedTab(container, filter = "") {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('All Environment Variables', 'terminal'));

    const filteredKeys = Object.keys(envData).filter(key =>
        key.toLowerCase().includes(filter.toLowerCase()) ||
        (envData[key] && envData[key].toLowerCase().includes(filter.toLowerCase()))
    ).sort();

    filteredKeys.forEach(key => {
        const row = document.createElement('div');
        row.className = 'advanced-row';
        row.innerHTML = `
            <div style="width: 280px; flex-shrink: 0; font-size: 10px; font-weight: 700; font-family: 'SF Mono', monospace; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis;">${key}</div>
            <input type="text" class="flex-1" style="background: transparent; border: none; font-size: 13px; color: var(--text-secondary); outline: none; font-family: 'SF Mono', monospace;" value="${envData[key] || ''}">
        `;
        row.querySelector('input').addEventListener('change', (e) => updateValue(key, e.target.value));
        section.appendChild(row);
    });

    if (filteredKeys.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding: 40px; text-align: center; color: var(--text-dim); font-style: italic;';
        empty.textContent = 'No variables match your search.';
        section.appendChild(empty);
    }

    container.appendChild(section);
}

// ═══════════════════════════════════════════════════════════
// DATA ACTIONS
// ═══════════════════════════════════════════════════════════

function updateValue(key, value) {
    envData[key] = value;
    localChanges[key] = value;
    updateChangeCounter();
}

function updateChangeCounter() {
    changeCount = Object.keys(localChanges).length;
    const el = document.getElementById('change-counter');
    const saveBtn = document.getElementById('btn-save');

    if (changeCount > 0) {
        el.textContent = `${changeCount} unsaved change${changeCount > 1 ? 's' : ''} detected`;
        el.className = 'text-xs text-rose-400 font-bold';
        saveBtn.classList.add('animate-pulse');
    } else {
        el.textContent = 'All settings synced to disk';
        el.className = 'text-xs text-slate-500 font-bold';
        saveBtn.classList.remove('animate-pulse');
    }
}

async function saveAll() {
    if (changeCount === 0) return;

    const indicator = document.getElementById('save-indicator');
    if (indicator) indicator.style.opacity = '1';

    try {
        if (!window.electronAPI) {
            throw new Error("Not connected to Electron backend");
        }

        const envUpdates = { ...localChanges };
        delete envUpdates['_profiles_'];

        if (Object.keys(envUpdates).length > 0 && window.electronAPI.saveEnv) {
            await window.electronAPI.saveEnv(envUpdates);
        }
        if (localChanges['_profiles_'] && window.electronAPI.saveProfiles) {
            await window.electronAPI.saveProfiles(profilesContent);
        }

        localChanges = {};
        updateChangeCounter();
        setTimeout(() => { if (indicator) indicator.style.opacity = '0'; }, 2000);
    } catch (e) {
        alert("Save Error: " + e.message);
        if (indicator) indicator.style.opacity = '0';
    }
}

// ═══════════════════════════════════════════════════════════
// TOOLTIP
// ═══════════════════════════════════════════════════════════

function showTooltip(e, title, content) {
    const popup = document.getElementById('tooltip-popup');
    document.getElementById('tooltip-title').textContent = title;
    document.getElementById('tooltip-content').textContent = content;

    // Position tooltip first
    const rect = e.currentTarget.getBoundingClientRect();
    popup.style.left = `${rect.right + 16}px`;
    popup.style.top = `${rect.top}px`;

    // Then show it using class
    popup.classList.add('visible');
}

function hideTooltip() {
    const popup = document.getElementById('tooltip-popup');
    popup.classList.remove('visible');
}

// ═══════════════════════════════════════════════════════════
// START (init is called from DOMContentLoaded handler at top)
// ═══════════════════════════════════════════════════════════
