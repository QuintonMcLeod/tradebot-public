/**
 * Quantum Harmony Settings v2.0
 * Premium Trading Bot Configuration Interface
 */

const { electronAPI } = window;

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
// TOOLTIP LIBRARY
// ═══════════════════════════════════════════════════════════

const TOOLTIPS = {
    APP_PROFILE: "Pick a profile that defines symbol universe, cadence, and schedule rules.",
    BOT_MODE: "continuous: run forever | scheduled: session windows | iterations: fixed loop count",
    EXECUTE_TRADES: "Master switch for live order placement. Disable for simulation mode.",
    GUI_AUTOSTART_BOT: "Automatically start the core bot process when the GUI opens.",
    IBKR_PORT: "Default: 7497 (Paper TWS) or 4001 (Gateway Live).",
    CCXT_API_KEY: "API key for exchange authentication (e.g. Coinbase).",
    TRADE_SCI_PROVIDER: "Select AI backend: gemini, openai, claude, deepseek.",
    SABBATH_ENABLED: "Block new trades during the Friday/Saturday Sabbath window.",
    SABBATH_ASTRONOMICAL: "Use actual sunset times instead of fixed hours.",
    RISK_PER_TRADE_PCT: "Risk per trade as a percentage of total equity.",
    MAX_EXPOSURE_PCT: "Maximum total exposure across all open positions.",
    COMMENTARY_LLM_POLICY: "When to refresh AI commentary: interval vs A+ setup only.",
    HTF_TIMEFRAME: "Higher timeframe for trend analysis (e.g., 1h, 4h).",
    LTF_TIMEFRAME: "Lower timeframe for entry precision (e.g., 5m, 15m).",
    CANDLE_TIMEFRAME: "Primary candle timeframe for market data.",
    ICC_ENTRY_SCORE_THRESHOLD: "Minimum score required for ICC auto-entry.",
    MAX_PYRAMID_ENTRIES: "Maximum pyramid entries per position (1 = no pyramid).",
    BREAKEVEN_TRAIL_AFTER_PYRAMIDS: "Move stop to BE after N pyramids (0 = disabled).",
    BREAKEVEN_TRAIL_PCT: "Trail percentage above breakeven (0.003 = 0.3%).",
    PYRAMID_RISK_LOAD: "Risk % for first pyramid add (Load phase).",
    PYRAMID_RISK_SCALE: "Risk % for subsequent pyramid adds (Scale phase).",
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
    try {
        envData = await electronAPI.readEnv();
        profilesContent = await electronAPI.readProfiles();
        setupGlobalEvents();
        switchTab('system');
    } catch (e) {
        console.error("Initialization Failed:", e);
    }
}

function setupGlobalEvents() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    document.getElementById('btn-close').addEventListener('click', () => electronAPI.closeWindow());
    document.getElementById('btn-minimize').addEventListener('click', () => electronAPI.minimizeWindow());
    document.getElementById('btn-save').addEventListener('click', saveAll);
    document.getElementById('btn-revert').addEventListener('click', () => {
        if (confirm("Discard all unsaved changes?")) location.reload();
    });

    document.getElementById('setting-search').addEventListener('input', (e) => {
        if (currentTab === 'advanced') renderAdvancedTab(document.getElementById('tab-content'), e.target.value);
    });
}

// ═══════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });

    document.getElementById('search-container').classList.toggle('hidden', tabId !== 'advanced');
    renderTab();
}

function renderTab() {
    const container = document.getElementById('tab-content');
    container.innerHTML = '';
    if (TABS[currentTab]) TABS[currentTab].render(container);
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
            { value: 'crypto_247', label: 'Crypto 24/7' },
            { value: 'intraday', label: 'Standard Intraday' },
            { value: 'coinbase_futures', label: 'Coinbase Futures' },
            { value: 'coinbase_futures_nano', label: 'Coinbase Nano Futures' }
        ]
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
                { value: 'alternative', label: 'Alternative (CCXT)' },
                { value: 'hybrid', label: 'Hybrid' },
                { value: 'coinbase_futures', label: 'Coinbase Futures' }
            ]
        }));
        section.appendChild(createCard('Broker Mode', 'Execution routing', 'BROKER_MODE', 'dropdown', {
            items: [
                { value: 'primary', label: 'Primary (IBKR)' },
                { value: 'alternative', label: 'Alternative (CCXT)' },
                { value: 'hybrid', label: 'Hybrid' },
                { value: 'coinbase_futures', label: 'Coinbase Futures' }
            ]
        }));
        section.appendChild(createCard('Alternative Data', 'Fallback data source', 'ALTERNATIVE_MARKET_DATA', 'dropdown', {
            items: [
                { value: 'mock', label: 'Mock' },
                { value: 'coinbase', label: 'Coinbase' },
                { value: 'ccxt', label: 'CCXT' }
            ]
        }));
        section.appendChild(createCard('Alternative Broker', 'Fallback execution', 'ALTERNATIVE_BROKER', 'dropdown', {
            items: [
                { value: 'mock', label: 'Mock' },
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

        const res = await electronAPI.resolveCity(city);
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
    indicator.style.opacity = '1';

    try {
        const envUpdates = { ...localChanges };
        delete envUpdates['_profiles_'];

        if (Object.keys(envUpdates).length > 0) await electronAPI.saveEnv(envUpdates);
        if (localChanges['_profiles_']) await electronAPI.saveProfiles(profilesContent);

        localChanges = {};
        updateChangeCounter();
        setTimeout(() => indicator.style.opacity = '0', 2000);
    } catch (e) {
        alert("Critical Save Error: " + e.message);
        indicator.style.opacity = '0';
    }
}

// ═══════════════════════════════════════════════════════════
// TOOLTIP
// ═══════════════════════════════════════════════════════════

function showTooltip(e, title, content) {
    const popup = document.getElementById('tooltip-popup');
    document.getElementById('tooltip-title').textContent = title;
    document.getElementById('tooltip-content').textContent = content;

    popup.style.opacity = '1';
    popup.style.transform = 'translateY(0) scale(1)';
    popup.style.pointerEvents = 'auto';

    // Position tooltip
    const rect = e.currentTarget.getBoundingClientRect();
    popup.style.left = `${rect.right + 16}px`;
    popup.style.top = `${rect.top}px`;
}

function hideTooltip() {
    const popup = document.getElementById('tooltip-popup');
    popup.style.opacity = '0';
    popup.style.transform = 'translateY(4px) scale(0.98)';
    popup.style.pointerEvents = 'none';
}

// ═══════════════════════════════════════════════════════════
// START
// ═══════════════════════════════════════════════════════════

init();
