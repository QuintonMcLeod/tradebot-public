// ═══════════════════════════════════════════════════════════
// PROFILES MODULE - Integrated Profile Editor
// ═══════════════════════════════════════════════════════════
window.profilesModule = (function () {
    let allProfiles = {};
    let selectedProfileName = null;
    let activeProfileName = null;   // the bot's currently active profile
    let originalProfileData = null;
    let changeCount = 0;
    let initialized = false;
    let _saveTimer = null;   // debounce timer for auto-save

    /**
     * Fetch and update Realized PnL metrics based on timeframe
     */
    async function updateRealizedPnL() {
        try {
            const result = await window.api.invoke('get-analytics-summary', pnlTimeframe);
            if (result && result.success) {
                const summary = result.data;
                if (summary) {
                    const pnlVal = summary.totalNetWorth || summary.totalPnl || 0;

                    // Update global state for sidebar sync
                    currentRealizedPnL = pnlVal;
                    refreshMainPnlDisplay();

                    // Update chips if they exist (backward compatibility or future proofing)
                    const pnlEl = document.getElementById('realized-pnl-chip');
                    const tradeEl = document.getElementById('trade-count-chip');
                    const labelEl = document.getElementById('pnl-timeframe-label');

                    if (pnlEl) {
                        pnlEl.textContent = `${pnlVal >= 0 ? '+' : ''}$${pnlVal.toFixed(2)}`;
                        pnlEl.className = `text-[10px] font-black ${pnlVal >= 0 ? 'text-emerald-400' : 'text-rose-500'} drop-shadow-sm`;
                    }
                    if (tradeEl) tradeEl.textContent = summary.totalTrades || 0;
                    if (labelEl) labelEl.textContent = `Profits & Losses (${pnlTimeframe.toUpperCase()})`;
                }
            }
        } catch (err) {
            console.error('[PNL] Failed to update realized PnL:', err);
        }
    }
    // Expose to global scope so callers outside this IIFE can access it
    window.updateRealizedPnL = updateRealizedPnL;

    // ──────────────────────────────────────────────────────────────
    // STRATEGY_OPTIONS — master list for Profile Editor dropdowns.
    // HOW TO ADD A NEW STRATEGY:
    //   1. Add { value: 'your_key', label: 'Display Name' } below
    //   2. Also add to: settings_integrated.js (System Tab + Strategy Toolbox + STRATEGIES object)
    //   4. Register in: src/tradebot_sci/strategy/engine.py STRATEGY_MAP
    //   5. Add to Meta-SCI regime groups if applicable: strategy/variants/meta_sci.py
    // ──────────────────────────────────────────────────────────────
    const STRATEGY_OPTIONS = [
        { value: 'rubberband_reaper', label: 'Rubberband Reaper' },
        { value: 'robocop', label: 'RoboCop' },
        { value: 'evolution', label: 'Robot Evolution' },
        { value: 'quantum', label: 'Quantum' },
        { value: 'mean_reversion', label: 'Mean Reversion' },
        { value: 'hyper_scalper', label: 'HyperScalper' },
        { value: 'london_breakout', label: 'London Breakout' },
        { value: 'orb_breakout', label: 'ORB' },
        { value: 'volatility_breakout', label: 'Volatility Breakout' },
        { value: 'aggregator', label: 'Singularity Aggregator' },
        { value: 'meta_sci', label: 'Meta-SCI (AI Ensemble)' },
        { value: 'forex_conductor', label: 'Forex Conductor (Session Scheduler)' },
        { value: 'icc_core_standalone', label: 'ICC Core (ICT Methodology)' },
        { value: 'supply_demand', label: 'Supply & Demand' },
        { value: 'trend_rider', label: 'Trend Rider (EMA Pullback)' },
        { value: 'session_momentum', label: 'Session Momentum (VWAP)' },
        { value: 'bearish_engulfing', label: 'Engulfing Reversal' },
        { value: 'yoyo', label: 'Yo-Yo (Momentum Reversal)' },
        // 🪙 Crypto-Specific Strategies
        { value: 'crypto_rsi_macd', label: '🪙 RSI + MACD (Crypto)' },
        { value: 'crypto_vwap_reversion', label: '🪙 VWAP Reversion (Crypto)' },
        { value: 'crypto_double_macd', label: '🪙 Double MACD Scalper (Crypto)' },
        { value: 'crypto_grid', label: '🪙 Virtual Grid (Crypto)' }
    ];

    const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];

    async function init() {
        if (initialized) return;
        injectCustomStyles();
        await loadProfiles();
        setupEventListeners();
        renderProfileList();
        initialized = true;
    }

    function injectCustomStyles() {
        if (document.getElementById('profile-custom-styles')) return;
        const style = document.createElement('style');
        style.id = 'profile-custom-styles';
        style.textContent = `
            /* Custom Scrollbar for Profile Editor */
            #profile-tab-content::-webkit-scrollbar, #profile-list::-webkit-scrollbar {
                width: 6px;
            }
            #profile-tab-content::-webkit-scrollbar-track, #profile-list::-webkit-scrollbar-track {
                background: transparent;
            }
            #profile-tab-content::-webkit-scrollbar-thumb, #profile-list::-webkit-scrollbar-thumb {
                background: rgba(20, 184, 166, 0.2);
                border-radius: 10px;
            }
            #profile-tab-content:hover::-webkit-scrollbar-thumb, #profile-list:hover::-webkit-scrollbar-thumb {
                background: rgba(20, 184, 166, 0.4);
            }

            /* Premium Range Slider */
            .premium-slider {
                -webkit-appearance: none;
                width: 100%;
                height: 4px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.05);
                outline: none;
                transition: background 0.2s ease;
            }
            .premium-card:hover .premium-slider {
                background: rgba(255, 255, 255, 0.1);
            }
            .premium-slider::-webkit-slider-thumb {
                -webkit-appearance: none;
                appearance: none;
                width: 14px;
                height: 14px;
                border-radius: 50%;
                background: #14b8a6;
                cursor: pointer;
                box-shadow: 0 0 10px rgba(20, 184, 166, 0.5);
                transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
            }
            .premium-slider::-webkit-slider-thumb:hover {
                transform: scale(1.3);
                box-shadow: 0 0 15px rgba(20, 184, 166, 0.8);
            }

            /* Custom Select Dropdown Arrow Hiding */
            .premium-select {
                -webkit-appearance: none;
                -moz-appearance: none;
                appearance: none;
                background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2314b8a6' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
                background-repeat: no-repeat;
                background-position: right 12px center;
                background-size: 14px;
                padding-right: 32px !important;
            }
            
            /* Toggle Switch Animation */
            .premium-toggle-knob {
                transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), background-color 0.3s ease;
            }
            
            /* Select Options Styling (Limited by OS, but helps in some browsers) */
            .premium-select option {
                background: #0f172a;
                color: #e2e8f0;
                padding: 8px;
            }
            
            /* Premium Card Base */
            .premium-card {
                background: linear-gradient(135deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.005) 100%);
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 14px;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }
            .premium-card:hover {
                border-color: rgba(20, 184, 166, 0.2);
                background: linear-gradient(135deg, rgba(20,184,166,0.04) 0%, rgba(255,255,255,0.01) 100%);
                box-shadow: 0 8px 25px rgba(0,0,0,0.2), inset 0 0 0 1px rgba(20, 184, 166, 0.05);
                transform: translateY(-1px);
            }

            /* Tooltip Styles */
            [data-tooltip] {
                position: relative;
            }
            [data-tooltip]:hover::after {
                content: attr(data-tooltip);
                position: absolute;
                top: calc(100% + 8px);
                left: 50%;
                transform: translateX(-50%);
                background: rgba(15, 23, 42, 0.95);
                color: #94a3b8;
                font-size: 11px;
                font-weight: 500;
                line-height: 1.5;
                padding: 8px 12px;
                border-radius: 8px;
                border: 1px solid rgba(20, 184, 166, 0.2);
                box-shadow: 0 8px 24px rgba(0,0,0,0.4), 0 0 12px rgba(20,184,166,0.1);
                max-width: 320px;
                white-space: normal;
                z-index: 9999;
                pointer-events: none;
                animation: tooltipIn 0.2s ease;
            }
            @keyframes tooltipIn {
                from { opacity: 0; transform: translateX(-50%) translateY(-4px); }
                to { opacity: 1; transform: translateX(-50%) translateY(0); }
            }
        `;
        document.head.appendChild(style);
    }

    async function loadProfiles() {
        try {
            const result = await window.api.invoke('read-profiles');
            if (result) {
                // Parse YAML using simple regex (no external lib needed for reading)
                allProfiles = parseYaml(result);
            }
            // Read active_profile from config so sidebar dots render correctly on startup
            const config = await window.api.readConfig();
            if (config && config.active_profile) {
                activeProfileName = config.active_profile;
            }
        } catch (err) {
            console.error('[PROFILES] Load failed:', err);
            allProfiles = {};
        }
    }

    function parseYaml(yamlStr) {
        // Simple YAML parser for profiles structure
        const profiles = {};
        const lines = yamlStr.split('\n');
        let currentProfile = null;
        let currentKey = null;
        let inSymbols = false;
        let inStrategies = false;

        for (let line of lines) {
            // Skip comments and empty
            if (!line.trim() || line.trim().startsWith('#')) continue;

            // Profile name (2 spaces indent)
            const profileMatch = line.match(/^  ([a-z_0-9]+):$/);
            if (profileMatch) {
                currentProfile = profileMatch[1];
                profiles[currentProfile] = { symbols: [], strategies: {} };
                inSymbols = false;
                inStrategies = false;
                continue;
            }

            if (!currentProfile) continue;

            // Property (4 spaces indent)
            const propMatch = line.match(/^    ([a-z_]+):\s*(.*)$/);
            if (propMatch) {
                const key = propMatch[1];
                // Strip inline comments (e.g., "value  # comment")
                let val = propMatch[2].split('#')[0].trim();
                inSymbols = key === 'symbols' && !val;
                inStrategies = key === 'strategies' && !val;
                if (!inSymbols && !inStrategies && val) {
                    // Parse value
                    if (val === 'null' || val === '~') { /* skip — keep default */ }
                    else if (val === 'true') profiles[currentProfile][key] = true;
                    else if (val === 'false') profiles[currentProfile][key] = false;
                    else if (!isNaN(parseFloat(val)) && /^[\d.\-]+$/.test(val)) profiles[currentProfile][key] = parseFloat(val);
                    else profiles[currentProfile][key] = val.replace(/^['"]|['"]$/g, '');
                }
                continue;
            }

            // Symbol list item (4 spaces + -)
            if (inSymbols) {
                const symMatch = line.match(/^    - (.+)$/);
                if (symMatch) {
                    profiles[currentProfile].symbols.push(symMatch[1].trim().replace(/^['"]|['"]$/g, ''));
                }
            }

            // Strategy item (6 spaces)
            if (inStrategies) {
                const stratMatch = line.match(/^      ([a-z_]+):\s*(.+)$/);
                if (stratMatch) {
                    // Strip inline comments
                    profiles[currentProfile].strategies[stratMatch[1]] = stratMatch[2].split('#')[0].trim();
                }
            }
        }
        return profiles;
    }

    function setupEventListeners() {
        // Profile tabs removed — single merged view renders automatically

        // Save / Revert
        document.getElementById('btn-save-profile')?.addEventListener('click', saveProfile);
        document.getElementById('btn-revert-profile')?.addEventListener('click', revertChanges);
        document.getElementById('btn-delete-profile')?.addEventListener('click', deleteProfile);
        document.getElementById('btn-new-profile')?.addEventListener('click', createNewProfile);
    }

    function renderProfileList() {
        const list = document.getElementById('profile-list');
        if (!list) return;
        list.innerHTML = '';

        Object.keys(allProfiles).forEach(name => {
            const profile = allProfiles[name];
            const item = document.createElement('div');
            item.dataset.profile = name;
            Object.assign(item.style, {
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '12px 14px', borderRadius: '12px', cursor: 'pointer',
                transition: 'all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)', color: '#94a3b8',
                background: 'transparent', border: '1px solid transparent',
                marginBottom: '4px', position: 'relative', overflow: 'hidden'
            });
            item.onmouseover = function () {
                if (!this.classList.contains('profile-active')) {
                    this.style.background = 'linear-gradient(90deg, rgba(255,255,255,0.03) 0%, transparent 100%)';
                    this.style.borderColor = 'rgba(255,255,255,0.05)';
                    this.style.color = '#cbd5e1';
                    this.style.transform = 'translateX(2px)';
                }
            };
            item.onmouseout = function () {
                if (!this.classList.contains('profile-active')) {
                    this.style.background = 'transparent';
                    this.style.borderColor = 'transparent';
                    this.style.color = '#94a3b8';
                    this.style.transform = 'translateX(0)';
                }
            };

            const symbolCount = Array.isArray(profile.symbols) ? profile.symbols.length : 0;
            const stratName = profile.strategy_variant ? formatName(profile.strategy_variant) : '--';

            // Pick a contextual icon based on profile name keywords
            const iconMap = { crypto: 'currency_bitcoin', forex: 'currency_exchange', stock: 'candlestick_chart', scalp: 'bolt', swing: 'trending_up', intraday: 'schedule', all: 'public', continuous: 'all_inclusive', futures: 'show_chart' };
            let profileIcon = 'tune';
            const nameLower = name.toLowerCase();
            for (const [keyword, icon] of Object.entries(iconMap)) {
                if (nameLower.includes(keyword)) { profileIcon = icon; break; }
            }

            // Active indicator dot (green glow if this is the bot's active profile)
            const currentActive = activeProfileName || (typeof configData !== 'undefined' && configData.active_profile);
            const isActiveProfile = currentActive === name;
            const dotColor = isActiveProfile ? '#10b981' : 'transparent';
            const dotGlow = isActiveProfile ? '0 0 8px #10b981, 0 0 16px rgba(16,185,129,0.3)' : 'none';

            item.innerHTML = `
            <div class="profile-accent-bar" style="position:absolute; left:0; top:0; bottom:0; width:3px; background:#14b8a6; opacity:0; transition:opacity 0.3s ease, box-shadow 0.3s ease;"></div>
            <div style="width:38px; height:38px; border-radius:12px; display:flex; align-items:center; justify-content:center; background:rgba(20,184,166,0.06); border:1px solid rgba(20,184,166,0.12); flex-shrink:0; box-shadow: 0 2px 8px rgba(0,0,0,0.15); transition:all 0.3s ease; position:relative;">
                <span class="material-symbols-outlined" style="font-size:18px; color:#5eead4; opacity:0.7; transition:opacity 0.3s ease;">${profileIcon}</span>
                <span class="profile-active-dot" style="position:absolute; bottom:-1px; right:-1px; width:10px; height:10px; border-radius:50%; background:${dotColor}; border:2px solid rgba(15,23,42,0.9); box-shadow:${dotGlow}; transition:all 0.4s ease;"></span>
            </div>
            <div style="flex:1; min-width:0; z-index:1;">
                <div style="font-size:13px; font-weight:800; color:inherit; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; letter-spacing:-0.01em; transition:color 0.3s ease;">${formatName(name)}</div>
                <div style="font-size:10px; color:#64748b; margin-top:2px; font-weight:500;">${symbolCount} sym · ${stratName}</div>
            </div>
        `;

            item.addEventListener('click', () => selectProfile(name));
            list.appendChild(item);
        });
    }

    function formatName(name) {
        return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    function selectProfile(name) {
        selectedProfileName = name;
        originalProfileData = JSON.parse(JSON.stringify(allProfiles[name]));

        // Update sidebar active state with premium glow
        document.querySelectorAll('#profile-list > div').forEach(item => {
            const isActive = item.dataset.profile === name;
            const accentBar = item.querySelector('.profile-accent-bar');

            if (isActive) {
                item.classList.add('profile-active');
                item.style.background = 'linear-gradient(90deg, rgba(20,184,166,0.1) 0%, rgba(20,184,166,0.02) 100%)';
                item.style.borderColor = 'rgba(20,184,166,0.2)';
                item.style.color = '#f8fafc';
                item.style.boxShadow = '0 4px 15px rgba(0,0,0,0.2)';
                item.style.transform = 'translateX(4px)';
                if (accentBar) {
                    accentBar.style.opacity = '1';
                    accentBar.style.boxShadow = '0 0 10px #14b8a6, 0 0 20px #14b8a6';
                }
                const title = item.querySelector('div[style*="font-size:13px"]');
                if (title) title.style.color = '#5eead4';
            } else {
                item.classList.remove('profile-active');
                item.style.background = 'transparent';
                item.style.borderColor = 'transparent';
                item.style.color = '#94a3b8';
                item.style.boxShadow = 'none';
                item.style.transform = 'translateX(0)';
                if (accentBar) {
                    accentBar.style.opacity = '0';
                    accentBar.style.boxShadow = 'none';
                }
                const title = item.querySelector('div[style*="font-size:13px"]');
                if (title) title.style.color = 'inherit';
            }
        });

        // Update header
        document.getElementById('profile-name-display').textContent = formatName(name);
        document.getElementById('profile-desc-display').textContent = `${Array.isArray(allProfiles[name].symbols) ? allProfiles[name].symbols.length : 0} symbols`;
        document.getElementById('profile-activate-btn')?.classList.remove('hidden');
        document.getElementById('btn-delete-profile')?.classList.remove('hidden');

        // Sync activate button state
        updateActivateButton();

        // Hide empty state, render merged view
        document.getElementById('profile-empty-state')?.classList.add('hidden');
        renderTabContent();

        resetChangeCounter();
    }

    function renderTabContent() {
        if (!selectedProfileName) return;
        const profile = allProfiles[selectedProfileName];
        const container = document.getElementById('profile-tab-content');
        if (!container) return;

        let html = '<div class="max-w-2xl mx-auto">';

        // AI Optimize button
        html += `
        <div id="ai-optimize-wrapper" data-tooltip="One-click smart tuning. The AI reads every symbol in this profile, identifies what you're trading (crypto, forex, stocks, etc.), then recommends the best strategies, safety shields, risk limits, performance boosters, and trend indicators — all tailored to your portfolio. Results are saved directly to your config." style="margin-bottom:24px;">
            <button id="btn-ai-optimize" style="
                width:100%; padding:14px 20px; border:1px solid rgba(20,184,166,0.3); border-radius:12px;
                background:linear-gradient(135deg, rgba(20,184,166,0.08), rgba(99,102,241,0.08));
                color:#5eead4; font-size:13px; font-weight:700; letter-spacing:0.02em;
                cursor:pointer; display:flex; align-items:center; justify-content:center; gap:10px;
                transition:all 0.3s ease; position:relative; overflow:hidden;
            ">
                <span class="material-symbols-outlined" style="font-size:18px;">auto_awesome</span>
                <span id="ai-optimize-text">AI Optimize</span>
                <span id="ai-optimize-spinner" style="display:none;">
                    <svg width="18" height="18" viewBox="0 0 24 24" style="animation:spin 1s linear infinite;">
                        <circle cx="12" cy="12" r="10" stroke="#5eead4" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/>
                    </svg>
                </span>
            </button>
            <p style="font-size:10px; color:#64748b; margin:8px 0 0 0; text-align:center; line-height:1.4;">Analyzes your symbols and automatically configures strategies, safety, risk, and trend detection for you.</p>
            <div id="ai-optimize-result" style="display:none; margin-top:12px; padding:14px 18px; border-radius:10px;
                background:rgba(20,184,166,0.06); border:1px solid rgba(20,184,166,0.15);
                font-size:12px; color:#94a3b8; line-height:1.6;">
            </div>
        </div>
        <style>
            @keyframes spin { to { transform: rotate(360deg); } }
            #btn-ai-optimize:hover {
                background:linear-gradient(135deg, rgba(20,184,166,0.15), rgba(99,102,241,0.15)) !important;
                border-color:rgba(20,184,166,0.5) !important;
                box-shadow: 0 0 20px rgba(20,184,166,0.15);
            }
            #btn-ai-optimize.loading {
                pointer-events:none; opacity:0.7;
                background:linear-gradient(135deg, rgba(20,184,166,0.05), rgba(99,102,241,0.12), rgba(20,184,166,0.05)) !important;
                background-size:200% 200% !important;
                animation: shimmer 2s ease-in-out infinite;
            }
            @keyframes shimmer { 0%,100% { background-position:0% 50%; } 50% { background-position:100% 50%; } }
        </style>`;

        html += renderSymbolsTab(profile);
        html += '</div>';
        container.innerHTML = html;
        attachTabEventListeners();

        // Restore previous AI Optimize result if one exists for this profile
        (async () => {
            try {
                const savedConfig = await window.api.readConfig() || {};
                const history = savedConfig.ai_optimize_history?.[selectedProfileName];
                if (history && history.reasonings) {
                    const resultEl = document.getElementById('ai-optimize-result');
                    if (resultEl) {
                        const ts = new Date(history.timestamp);
                        const timeStr = ts.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
                        const r = history.reasonings;
                        const rec = history.applied_settings || {};
                        const categoryStyle = 'padding:10px 14px; border-radius:8px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); margin-top:8px;';
                        const labelStyle = 'font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px;';
                        const textStyle = 'font-size:12px; color:#94a3b8; line-height:1.5;';
                        const trendEnabled = Object.entries(rec).filter(([k, v]) => k.startsWith('TREND_') && k.endsWith('_ENABLED') && v === true).map(([k]) => k.replace('TREND_', '').replace('_ENABLED', ''));
                        resultEl.innerHTML = `
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                <div style="color:#64748b; font-weight:700; font-size:13px;">📋 Last AI Optimization</div>
                                <div style="font-size:10px; color:#64748b;">🕐 ${timeStr}</div>
                            </div>
                            <div style="margin-bottom:12px; color:#94a3b8; font-size:12px;">${r.summary || ''}</div>
                            <div style="${categoryStyle}"><div style="${labelStyle} color:#a78bfa;">🎯 Strategy</div><div style="${textStyle}">${r.strategies || r.strategy || ''}</div></div>
                            <div style="${categoryStyle}"><div style="${labelStyle} color:#818cf8;">⚙️ Workshop</div><div style="${textStyle}">${r.strategy || ''}</div></div>
                            <div style="${categoryStyle}"><div style="${labelStyle} color:#f59e0b;">🛡️ Safety</div><div style="${textStyle}">${r.safety || ''}</div></div>
                            <div style="${categoryStyle}"><div style="${labelStyle} color:#22c55e;">📈 Performance</div><div style="${textStyle}">${r.performance || ''}</div></div>
                            <div style="${categoryStyle}"><div style="${labelStyle} color:#f472b6;">📊 Trend</div><div style="${textStyle}">${r.trend || ''}</div>
                                ${trendEnabled.length ? `<div style="margin-top:4px; font-size:11px; color:#4ade80;">Active: ${trendEnabled.join(', ')}</div>` : ''}
                            </div>
                        `;
                        resultEl.style.display = 'block';
                    }
                }
            } catch (e) { console.warn('[PROFILES] Could not restore AI optimize history:', e); }
        })();

        // Wire up AI Optimize button click
        const optimizeBtn = document.getElementById('btn-ai-optimize');
        if (optimizeBtn) {
            optimizeBtn.addEventListener('click', async () => {
                const textEl = document.getElementById('ai-optimize-text');
                const spinnerEl = document.getElementById('ai-optimize-spinner');
                const resultEl = document.getElementById('ai-optimize-result');

                // Start loading
                optimizeBtn.classList.add('loading');
                textEl.textContent = 'Analyzing profile...';
                spinnerEl.style.display = 'inline';
                resultEl.style.display = 'none';

                try {
                    const result = await window.api.invoke('ai-recommend', selectedProfileName);

                    if (!result.success) {
                        resultEl.innerHTML = `<span style="color:#f87171;">❌ ${result.error}</span>`;
                        resultEl.style.display = 'block';
                        return;
                    }

                    const rec = result.recommendations;

                    // Extract reasoning before applying settings
                    const reasonings = {
                        strategies: rec.reasoning_strategies || '',
                        strategy: rec.reasoning_strategy || '',
                        safety: rec.reasoning_safety || '',
                        performance: rec.reasoning_performance || '',
                        trend: rec.reasoning_trend || '',
                        summary: rec.reasoning_summary || rec.reasoning || 'Settings optimized for your profile.',
                    };
                    // Remove reasoning keys so they're not saved as env vars
                    delete rec.reasoning_strategies;
                    delete rec.reasoning_strategy;
                    delete rec.reasoning_safety;
                    delete rec.reasoning_performance;
                    delete rec.reasoning_trend;
                    delete rec.reasoning_summary;
                    delete rec.reasoning;

                    // Apply ALL recommendations to config.json (no .env writes)
                    const CONFIG_SAVE_MAP = {
                        // Safety section
                        'SAFETY_STABILITY_MODE_ENABLED': ['safety', 'safety_stability_mode_enabled'],
                        'SAFETY_ATR_SHIELD_ENABLED': ['safety', 'safety_atr_shield_enabled'],
                        'STOP_ATR_MULTIPLIER': ['safety', 'stop_atr_multiplier'],
                        'BREAKEVEN_TRAIL_PCT': ['safety', 'breakeven_trail_pct'],
                        'SAFETY_DRAWDOWN_BREAKER_ENABLED': ['safety', 'safety_drawdown_breaker_enabled'],
                        'SAFETY_DRAWDOWN_MAX_PCT': ['safety', 'safety_drawdown_max_pct'],
                        'SAFETY_SESSION_LOCKOUT_ENABLED': ['safety', 'safety_session_lockout_enabled'],
                        'SAFETY_SESSION_LOCKOUT_HOUR': ['safety', 'safety_session_lockout_hour'],
                        'SAFETY_GREED_GUARD_ENABLED': ['safety', 'safety_greed_guard_enabled'],
                        'SAFETY_GREED_GUARD_TARGET': ['safety', 'safety_greed_guard_target'],
                        'SAFETY_CHURN_BURNER_ENABLED': ['safety', 'safety_churn_burner_enabled'],
                        'SAFETY_CHURN_BURNER_MAX': ['safety', 'safety_churn_burner_max'],
                        'SAFETY_LEVERAGE_SENTRY_ENABLED': ['safety', 'safety_leverage_sentry_enabled'],
                        'SAFETY_MAX_TOTAL_LEVERAGE': ['safety', 'safety_max_total_leverage'],
                        'SAFETY_VOLATILITY_VETO_ENABLED': ['safety', 'safety_volatility_veto_enabled'],
                        'SAFETY_STREAK_BREAKER_ENABLED': ['safety', 'safety_streak_breaker_enabled'],
                        'SAFETY_OPENING_SENTRY_ENABLED': ['safety', 'safety_opening_sentry_enabled'],
                        'SAFETY_SENTIMENT_SHIELD_ENABLED': ['safety', 'safety_sentiment_shield_enabled'],
                        'SAFETY_STALE_SNIPER_ENABLED': ['safety', 'safety_stale_sniper_enabled'],
                        'SAFETY_STALE_SNIPER_BARS': ['safety', 'safety_stale_sniper_bars'],
                        'SAFETY_FLASH_TRAP_ENABLED': ['safety', 'safety_flash_trap_enabled'],
                        'SAFETY_REGIME_FLIP_ENABLED': ['safety', 'safety_regime_flip_enabled'],
                        'BLOCK_COUNTER_TREND_ENTRIES': ['safety', 'block_counter_trend_entries'],
                        'RISK_REWARD_RATIO': ['safety', 'risk_reward_ratio'],
                        'WEALTH_EXIT_GAMMA_ENABLED': ['safety', 'wealth_exit_gamma_enabled'],
                        'WEALTH_EXIT_MOONSHOT_ENABLED': ['safety', 'wealth_exit_moonshot_enabled'],
                        'WEALTH_EXIT_BLOWOFF_ENABLED': ['safety', 'wealth_exit_blowoff_enabled'],
                        // Risk section
                        'RISK_PER_TRADE_PCT': ['risk', 'risk_per_trade_pct'],
                        'RISK_PER_TRADE_DOLLARS': ['risk', 'risk_per_trade_dollars'],
                        'MAX_EXPOSURE_PCT': ['risk', 'max_exposure_pct'],
                        'LIMIT_LOSS_DAILY_PCT': ['risk', 'limit_loss_daily_pct'],
                        'MAX_LOSS_PER_TRADE_DOLLARS': ['risk', 'max_loss_per_trade_dollars'],
                        // Performance section
                        'TRAILING_STOP_ENABLED': ['performance', 'trailing_stop_enabled'],
                        // Global section
                        'STRATEGY_CRYPTO': ['global', 'strategy_crypto'],
                        'STRATEGY_FOREX': ['global', 'strategy_forex'],
                        'STRATEGY_STOCKS': ['global', 'strategy_stocks'],
                        'STRATEGY_ETF': ['global', 'strategy_etf'],
                        'STRATEGY_METALS': ['global', 'strategy_metals'],
                        'STRATEGY_FUTURES': ['global', 'strategy_futures'],
                        'MULTI_POSITION_ENABLED': ['global', 'multi_position_enabled'],
                        'MAX_CONCURRENT_POSITIONS': ['global', 'max_concurrent_positions'],
                        'SMART_POSITIONS_ENABLED': ['global', 'smart_positions_enabled'],
                        'AUTO_FLATTEN_ON_CLOSE': ['global', 'flatten_on_exit'],
                        'MAX_PYRAMID_ENTRIES': ['global', 'max_pyramid_entries'],
                        'PYRAMID_PROFIT_BUFFER_PCT': ['global', 'pyramid_profit_buffer_pct'],
                        'PYRAMID_RISK_LOAD': ['global', 'pyramid_risk_load'],
                        'PYRAMID_RISK_SCALE': ['global', 'pyramid_risk_scale'],
                        'BREAKEVEN_TRAIL_AFTER_PYRAMIDS': ['global', 'breakeven_trail_after_pyramids'],
                        'TRAILING_STOP_MIN_PROFIT_PCT': ['global', 'trailing_stop_min_profit_pct'],
                        'MIN_HOLD_HOURS': ['global', 'min_hold_hours'],
                        'MAX_HOLD_HOURS': ['global', 'max_hold_hours'],
                        'HTF_NEUTRAL_EXIT_BARS': ['global', 'htf_neutral_exit_bars'],
                        'TARGET_PROFIT_DAILY_PCT': ['global', 'target_profit_daily_pct'],
                    };

                    // Read current config and merge
                    const currentConfig = await window.api.readConfig() || {};
                    const activeProfile = currentConfig.active_profile;
                    const enabledModes = [];

                    for (const [key, val] of Object.entries(rec)) {
                        // Performance modes → aggregate into comma-separated string
                        if (key.startsWith('PERFORMANCE_MODE_')) {
                            const mode = key.replace('PERFORMANCE_MODE_', '').toLowerCase();
                            if (val === true && mode !== 'none') enabledModes.push(mode);
                            continue;
                        }

                        // Trend toggles → save to global config
                        if (key.startsWith('TREND_') && key.endsWith('_ENABLED')) {
                            if (!currentConfig.global) currentConfig.global = {};
                            currentConfig.global[key.toLowerCase()] = val;
                            continue;
                        }

                        // Config-mapped settings → save to proper section
                        const mapping = CONFIG_SAVE_MAP[key];
                        if (mapping) {
                            const [section, field] = mapping;
                            if (!currentConfig[section]) currentConfig[section] = {};

                            // Normalize percent fields: AI returns 2 (meaning 2%),
                            // but Pydantic expects 0.02 (decimal fraction ≤ 1)
                            const DECIMAL_FRACTION_FIELDS = new Set([
                                'risk_per_trade_pct', 'limit_loss_daily_pct',
                                'max_exposure_pct', 'short_risk_pct',
                                'max_risk_cap_override',
                                'pyramid_profit_buffer_pct',
                                'trailing_stop_min_profit_pct',
                                'target_profit_daily_pct',
                                'breakeven_trail_pct',
                            ]);
                            let finalVal = val;
                            if (DECIMAL_FRACTION_FIELDS.has(field) && typeof val === 'number' && val > 1) {
                                finalVal = val / 100;
                            }

                            currentConfig[section][field] = finalVal;
                        }
                    }

                    // Set aggregated performance mode
                    if (!currentConfig.performance) currentConfig.performance = {};
                    currentConfig.performance.performance_mode = enabledModes.length > 0 ? enabledModes.join(',') : 'none';

                    // Save AI Optimize history for this profile
                    if (!currentConfig.ai_optimize_history) currentConfig.ai_optimize_history = {};
                    currentConfig.ai_optimize_history[selectedProfileName] = {
                        timestamp: new Date().toISOString(),
                        reasonings,
                        applied_settings: { ...rec },
                    };

                    // Save everything to config.json
                    await window.api.invoke('save-config', currentConfig);

                    // Build per-category reasoning cards
                    const categoryStyle = 'padding:10px 14px; border-radius:8px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); margin-top:8px;';
                    const labelStyle = 'font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px;';
                    const textStyle = 'font-size:12px; color:#94a3b8; line-height:1.5;';

                    // Count what changed
                    const trendEnabled = Object.entries(rec).filter(([k, v]) => k.startsWith('TREND_') && k.endsWith('_ENABLED') && v === true).map(([k]) => k.replace('TREND_', '').replace('_ENABLED', ''));
                    const perfFoundation = Object.entries(rec).filter(([k, v]) => k.startsWith('PERFORMANCE_MODE_') && !['SNIPER', 'REGIME_SYNC', 'HOUSE_MONEY', 'WHALE', 'CONTRARIAN', 'SURFER', 'HYDRA', 'COIL', 'ALPHA', 'GAMMA', 'SENTIMENT', 'GHOST', 'PHOENIX', 'RUNNER'].some(m => k.includes(m)) && v === true).map(([k]) => k.replace('PERFORMANCE_MODE_', ''));
                    const perfMultipliers = Object.entries(rec).filter(([k, v]) => k.startsWith('PERFORMANCE_MODE_') && ['SNIPER', 'REGIME_SYNC', 'HOUSE_MONEY', 'WHALE', 'CONTRARIAN', 'SURFER', 'HYDRA', 'COIL', 'ALPHA', 'GAMMA', 'SENTIMENT', 'GHOST', 'PHOENIX', 'RUNNER'].some(m => k.includes(m)) && v === true).map(([k]) => k.replace('PERFORMANCE_MODE_', ''));

                    const timeStr = new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
                    resultEl.innerHTML = `
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                            <div style="color:#5eead4; font-weight:700; font-size:14px;">✨ AI Optimization Applied</div>
                            <div style="font-size:10px; color:#64748b;">🕐 ${timeStr}</div>
                        </div>
                        <div style="margin-bottom:12px; color:#e2e8f0; font-size:12px;">${reasonings.summary}</div>

                        <div style="${categoryStyle}">
                            <div style="${labelStyle} color:#a78bfa;">🎯 Strategy Selection</div>
                            <div style="${textStyle}">${reasonings.strategies || 'Strategies selected for your asset classes.'}</div>
                            ${['STRATEGY_CRYPTO', 'STRATEGY_FOREX', 'STRATEGY_STOCKS', 'STRATEGY_ETF', 'STRATEGY_METALS', 'STRATEGY_FUTURES']
                            .filter(k => rec[k])
                            .map(k => `<div style="margin-top:3px; font-size:11px; color:#c4b5fd;">${k.replace('STRATEGY_', '')}: <span style="color:#e2e8f0; font-weight:600;">${rec[k]}</span></div>`)
                            .join('')}
                        </div>

                        <div style="${categoryStyle}">
                            <div style="${labelStyle} color:#818cf8;">⚙️ Strategy Workshop</div>
                            <div style="${textStyle}">${reasonings.strategy || 'Default strategy settings applied.'}</div>
                            ${rec.RISK_PER_TRADE_PCT ? `<div style="margin-top:4px; font-size:11px; color:#5eead4;">Risk: ${rec.RISK_PER_TRADE_PCT}% per trade · ${rec.RISK_REWARD_RATIO || '2.0'}:1 R:R · Pyramid: ${rec.MAX_PYRAMID_ENTRIES || '3'} entries</div>` : ''}
                        </div>

                        <div style="${categoryStyle}">
                            <div style="${labelStyle} color:#f59e0b;">🛡️ Safety & Shields</div>
                            <div style="${textStyle}">${reasonings.safety || 'Safety settings configured for your risk profile.'}</div>
                        </div>

                        <div style="${categoryStyle}">
                            <div style="${labelStyle} color:#22c55e;">📈 Performance & Profits</div>
                            <div style="${textStyle}">${reasonings.performance || 'Performance modes optimized.'}</div>
                            ${perfFoundation.length ? `<div style="margin-top:4px; font-size:11px; color:#4ade80;">Foundation: ${perfFoundation.join(', ')}</div>` : ''}
                            ${perfMultipliers.length ? `<div style="margin-top:2px; font-size:11px; color:#5eead4;">Multipliers: ${perfMultipliers.join(', ')}</div>` : ''}
                        </div>

                        <div style="${categoryStyle}">
                            <div style="${labelStyle} color:#f472b6;">📊 Trend Detection</div>
                            <div style="${textStyle}">${reasonings.trend || 'Trend indicators selected for your asset mix.'}</div>
                            ${trendEnabled.length ? `<div style="margin-top:4px; font-size:11px; color:#4ade80;">Active: ${trendEnabled.join(', ')}</div>` : ''}
                        </div>
                    `;
                    resultEl.style.display = 'block';

                } catch (err) {
                    resultEl.innerHTML = `<span style="color:#f87171;">❌ ${err.message || 'Unknown error'}</span>`;
                    resultEl.style.display = 'block';
                } finally {
                    optimizeBtn.classList.remove('loading');
                    textEl.textContent = 'AI Optimize';
                    spinnerEl.style.display = 'none';
                }
            });
        }
    }

    function _sectionHeader(label, icon, tooltip) {
        const tipAttr = tooltip ? ` data-tooltip="${tooltip}"` : '';
        return `<div style="display:flex; align-items:center; gap:12px; margin-bottom:18px; padding-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.04); position:relative;"${tipAttr}>
            <div style="position:absolute; bottom:-1px; left:0; width:40px; height:2px; background:linear-gradient(90deg, #14b8a6, transparent); border-radius:2px; box-shadow: 0 0 8px rgba(20,184,166,0.5);"></div>
            <div style="width:28px; height:28px; border-radius:8px; background:rgba(20,184,166,0.1); display:flex; align-items:center; justify-content:center; border:1px solid rgba(20,184,166,0.2); box-shadow: inset 0 1px 0 rgba(255,255,255,0.1);">
                <span class="material-symbols-outlined" style="font-size:16px; color:#5eead4;">${icon}</span>
            </div>
            <span style="font-size:11px; font-weight:900; text-transform:uppercase; letter-spacing:0.15em; color:#f8fafc; text-shadow: 0 2px 4px rgba(0,0,0,0.5);">${label}</span>
        </div>`;
    }

    // Tooltip definitions for all settings (layman-friendly)
    const PROFILE_TOOLTIPS = {
        'strategy_variant': 'The default trading algorithm this profile uses when no asset-specific strategy is set.',
        'htf_timeframe': 'Higher timeframe — the "big picture" chart the bot checks for overall market direction (e.g., 1h means hourly candles).',
        'ltf_timeframe': 'Lower timeframe — the "zoom in" chart the bot uses for precise entry/exit timing.',
        'strategies.crypto': 'Which trading strategy to use specifically for cryptocurrency trades.',
        'strategies.forex': 'Which trading strategy to use specifically for forex (currency pair) trades.',
        'strategies.stocks': 'Which trading strategy to use specifically for stock trades.',
        'strategies.etf': 'Which trading strategy to use specifically for ETF (exchange-traded fund) trades.',
        'strategies.metals': 'Which trading strategy to use specifically for precious metals (gold, silver) trades.',
        'strategies.futures': 'Which trading strategy to use specifically for futures contract trades.',
        'session_gate_enabled': 'Only trade during active market hours. Prevents trades during low-volume off-hours when spreads are wider.',
        'continuous_mode': 'Run this profile around the clock without stopping. Best for 24/7 crypto markets.',
        'crypto_only': 'Restrict this profile to only trade cryptocurrency symbols, ignoring any forex or stock symbols.',
    };

    function renderGeneralTab(profile) {
        return `
            ${_sectionHeader('Core Settings', 'settings')}
            ${renderSelect('strategy_variant', 'Default Strategy', profile.strategy_variant, STRATEGY_OPTIONS)}
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px;">
                ${renderSelect('htf_timeframe', 'HTF Timeframe', profile.htf_timeframe, TIMEFRAME_OPTIONS.map(t => ({ value: t, label: t })))}
                ${renderSelect('ltf_timeframe', 'LTF Timeframe', profile.ltf_timeframe, TIMEFRAME_OPTIONS.map(t => ({ value: t, label: t })))}
            </div>
            <div style="margin-top:28px;">${_sectionHeader('Asset Strategies', 'category')}</div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                ${['crypto', 'forex', 'stocks', 'etf', 'metals', 'futures'].map(asset =>
            renderSelect(`strategies.${asset}`, asset.charAt(0).toUpperCase() + asset.slice(1), profile.strategies?.[asset] || profile.strategy_variant, STRATEGY_OPTIONS)
        ).join('')}
            </div>
        `;
    }

    function renderSymbolsTab(profile) {
        const symbols = Array.isArray(profile.symbols) ? profile.symbols : [];
        return `
            ${_sectionHeader('Trading Symbols', 'monitoring', 'These are the ticker symbols (like BTCUSD or EUR_USD) that the bot will actively monitor and trade within this profile. The bot only trades what you add here — it won\'t touch anything else.')}
            <p style="font-size:10px; color:#64748b; margin-bottom:12px;">Type a ticker symbol (e.g. BTCUSD, EUR_USD) and press Enter to add it to this profile.</p>
            <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.04); border-radius:14px; padding:16px; min-height:200px; display:flex; flex-wrap:wrap; gap:8px; align-content:flex-start;">
                ${symbols.map(s => `
                    <span class="symbol-chip" data-symbol="${s}" style="display:inline-flex; align-items:center; gap:6px; padding:6px 14px; background:rgba(20,184,166,0.06); border:1px solid rgba(20,184,166,0.12); border-radius:999px; font-size:11px; font-weight:700; color:#5eead4; transition:all 0.2s ease;">
                        ${s}
                        <span class="remove-symbol material-symbols-outlined" style="font-size:12px; cursor:pointer; opacity:0.5; transition:all 0.15s ease;" onmouseover="this.style.opacity='1'; this.style.color='#f87171';" onmouseout="this.style.opacity='0.5'; this.style.color='inherit';">close</span>
                    </span>
                `).join('')}
                <input type="text" id="symbol-input" placeholder="Add symbol..." style="flex:1; min-width:100px; background:transparent; border:none; outline:none; font-size:12px; color:#e2e8f0; padding:6px 0;">
            </div>
        `;
    }

    function renderScheduleTab(profile) {
        return `
            ${_sectionHeader('Trading Schedule', 'schedule')}
        <div style="display:flex; flex-direction:column; gap:10px;">
            ${renderToggle('session_gate_enabled', 'Session Gate', profile.session_gate_enabled)}
            ${renderToggle('continuous_mode', 'Continuous (24/7)', profile.continuous_mode)}
            ${renderToggle('crypto_only', 'Crypto Only', profile.crypto_only)}
        </div>
        `;
    }

    function renderSelect(key, label, value, options) {
        const tip = PROFILE_TOOLTIPS[key] || '';
        return `
            < div class="premium-card" style = "padding:14px 18px; display:flex; align-items:center; justify-content:space-between;" ${tip ? `data-tooltip="${tip}"` : ''}>
                <span style="font-size:13px; font-weight:700; color:#cbd5e1; letter-spacing:-0.01em;">${label}</span>
                <select class="premium-select" data-key="${key}" style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:8px 14px; font-size:12px; font-weight:600; color:#5eead4; min-width:160px; outline:none; cursor:pointer; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2), 0 1px 2px rgba(255,255,255,0.02); transition:all 0.2s ease;"
                    onmouseover="this.style.borderColor='rgba(20,184,166,0.4)'; this.style.boxShadow='inset 0 2px 4px rgba(0,0,0,0.2), 0 0 10px rgba(20,184,166,0.1)';"
                    onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'; this.style.boxShadow='inset 0 2px 4px rgba(0,0,0,0.2), 0 1px 2px rgba(255,255,255,0.02)';">
                    ${options.map(o => `<option value="${o.value || o}" ${(value === (o.value || o)) ? 'selected' : ''}>${o.label || o}</option>`).join('')}
                </select>
            </div >
            `;
    }

    function renderSlider(key, label, value, min, max, step, suffix, mult = 1) {
        const display = (value * mult).toFixed(mult > 1 ? 1 : 2);
        return `
            < div class="premium-card" style = "padding:16px 20px;" >
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
                    <span style="font-size:13px; font-weight:700; color:#cbd5e1; letter-spacing:-0.01em;">${label}</span>
                    <div style="background:rgba(20,184,166,0.1); border:1px solid rgba(20,184,166,0.2); padding:4px 12px; border-radius:8px; box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);">
                        <span style="font-size:14px; font-weight:900; color:#5eead4; font-variant-numeric: tabular-nums;" id="val-${key}">${display}${suffix}</span>
                    </div>
                </div>
                <input type="range" class="premium-slider slider-range" data-key="${key}" data-mult="${mult}" data-suffix="${suffix}" min="${min}" max="${max}" step="${step}" value="${value}">
            </div>
        `;
    }

    function renderToggle(key, label, value) {
        // Build the toggle design. Active = teal gradient, Inactive = dark glass
        const bg = value ? 'linear-gradient(135deg, #14b8a6, #06b6d4)' : 'rgba(0,0,0,0.4)';
        const border = value ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.05)';
        const knobPos = value ? 'translateX(18px)' : 'translateX(0)';
        const knobBg = value ? '#ffffff' : '#94a3b8';
        const shadow = value ? '0 0 12px rgba(20,184,166,0.6)' : 'inset 0 2px 4px rgba(0,0,0,0.2)';
        const tip = PROFILE_TOOLTIPS[key] || '';

        return `
            < div class="premium-card premium-toggle-container" data - state="${value}" data - key="${key}" style = "padding:14px 18px; display:flex; align-items:center; justify-content:space-between; cursor:pointer;" ${tip ? `data-tooltip="${tip}"` : ''}
        onclick = "window.profilesModule._simulateToggleClick(this)" >
                <span style="font-size:13px; font-weight:700; color:#cbd5e1; letter-spacing:-0.01em;">${label}</span>
                <div class="premium-toggle-track" style="width:42px; height:24px; border-radius:999px; background:${bg}; border:1px solid ${border}; position:relative; transition:all 0.3s ease; box-shadow: ${shadow};">
                    <div class="premium-toggle-knob" style="position:absolute; left:3px; top:2px; width:18px; height:18px; border-radius:50%; background:${knobBg}; box-shadow:0 2px 4px rgba(0,0,0,0.3); transform:${knobPos};"></div>
                </div>
            </div >
            `;
    }

    // A helper exposed for the custom toggle click
    window.profilesModule = window.profilesModule || {};
    window.profilesModule._simulateToggleClick = function (el) {
        const key = el.dataset.key;
        const currentState = el.dataset.state === 'true';
        const newState = !currentState;

        // Update DOM visually immediately
        el.dataset.state = newState.toString();
        const track = el.querySelector('.premium-toggle-track');
        const knob = el.querySelector('.premium-toggle-knob');

        if (newState) {
            track.style.background = 'linear-gradient(135deg, #14b8a6, #06b6d4)';
            track.style.borderColor = 'rgba(255,255,255,0.2)';
            track.style.boxShadow = '0 0 12px rgba(20,184,166,0.6)';
            knob.style.transform = 'translateX(18px)';
            knob.style.background = '#ffffff';
        } else {
            track.style.background = 'rgba(0,0,0,0.4)';
            track.style.borderColor = 'rgba(255,255,255,0.05)';
            track.style.boxShadow = 'inset 0 2px 4px rgba(0,0,0,0.2)';
            knob.style.transform = 'translateX(0)';
            knob.style.background = '#94a3b8';
        }

        // Dispatch logic
        setNestedValue(allProfiles[selectedProfileName], key, newState);
        incrementChangeCounter();
    };

    function attachTabEventListeners() {
        // Selects
        document.querySelectorAll('#profile-tab-content .premium-select').forEach(el => {
            el.addEventListener('change', handleFieldChange);
        });

        // Sliders
        document.querySelectorAll('#profile-tab-content .premium-slider').forEach(el => {
            el.addEventListener('input', handleSliderChange);
        });

        // Toggles (handled by inline onclick now)
        // document.querySelectorAll('#profile-tab-content .premium-toggle-container').forEach(el => {
        //     el.addEventListener('click', handleToggleClick);
        // });

        // Symbols (always attached since merged view)
        document.getElementById('symbol-input')?.addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.value.trim()) {
                const sym = e.target.value.trim().toUpperCase();
                if (!allProfiles[selectedProfileName].symbols) allProfiles[selectedProfileName].symbols = [];
                if (!allProfiles[selectedProfileName].symbols.includes(sym)) {
                    allProfiles[selectedProfileName].symbols.push(sym);
                    renderTabContent();
                    incrementChangeCounter();
                }
                e.target.value = '';
            }
        });
        document.querySelectorAll('.remove-symbol').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const sym = e.target.closest('.symbol-chip').dataset.symbol;
                allProfiles[selectedProfileName].symbols = (allProfiles[selectedProfileName].symbols || []).filter(s => s !== sym);
                renderTabContent();
                incrementChangeCounter();
            });
        });
    }

    function handleFieldChange(e) {
        const key = e.target.dataset.key;
        setNestedValue(allProfiles[selectedProfileName], key, e.target.value);
        incrementChangeCounter();
    }

    function handleSliderChange(e) {
        const key = e.target.dataset.key;
        const mult = parseFloat(e.target.dataset.mult) || 1;
        const suffix = e.target.dataset.suffix || '';
        const val = parseFloat(e.target.value);
        document.getElementById(`val - ${key} `).textContent = `${(val * mult).toFixed(mult > 1 ? 1 : 2)}${suffix} `;
        setNestedValue(allProfiles[selectedProfileName], key, val);
        incrementChangeCounter();
    }

    function handleToggleClick(e) {
        const toggle = e.currentTarget;
        const key = toggle.dataset.key;
        const isActive = toggle.classList.contains('active');
        toggle.classList.toggle('active', !isActive);
        setNestedValue(allProfiles[selectedProfileName], key, !isActive);
        incrementChangeCounter();
    }

    function setNestedValue(obj, path, value) {
        const keys = path.split('.');
        let current = obj;
        for (let i = 0; i < keys.length - 1; i++) {
            if (!current[keys[i]]) current[keys[i]] = {};
            current = current[keys[i]];
        }
        current[keys[keys.length - 1]] = value;
    }

    function incrementChangeCounter() {
        changeCount++;
        const el = document.getElementById('profile-change-counter');
        if (el) el.textContent = 'Saving...';
        // Debounced auto-save (800ms after last change)
        clearTimeout(_saveTimer);
        _saveTimer = setTimeout(() => saveProfile(), 800);
    }

    function resetChangeCounter() {
        changeCount = 0;
        const el = document.getElementById('profile-change-counter');
        if (el) el.textContent = 'All changes saved';
    }

    async function saveProfile() {
        try {
            // Build YAML string
            let yaml = 'profiles:\n';
            for (const [name, profile] of Object.entries(allProfiles)) {
                yaml += `  ${name}: \n`;
                for (const [key, val] of Object.entries(profile)) {
                    if (key === 'symbols' && Array.isArray(val)) {
                        yaml += `    symbols: \n`;
                        val.forEach(s => yaml += `    - ${s} \n`);
                    } else if (key === 'strategies' && typeof val === 'object') {
                        yaml += `    strategies: \n`;
                        for (const [asset, strat] of Object.entries(val)) {
                            yaml += `      ${asset}: ${strat} \n`;
                        }
                    } else if (typeof val === 'boolean') {
                        yaml += `    ${key}: ${val} \n`;
                    } else if (typeof val === 'number') {
                        yaml += `    ${key}: ${val} \n`;
                    } else if (val !== null && val !== undefined) {
                        yaml += `    ${key}: ${val} \n`;
                    }
                }
            }
            await window.api.invoke('save-profiles', yaml);
            originalProfileData = JSON.parse(JSON.stringify(allProfiles[selectedProfileName]));
            resetChangeCounter();
            appendLog("SUCCESS", `[PROFILES] Profile "${selectedProfileName}" saved.`);
        } catch (err) {
            console.error('[PROFILES] Save failed:', err);
            appendLog("ERROR", `[PROFILES] Save failed: ${err.message} `);
        }
    }

    function revertChanges() {
        if (!selectedProfileName || !originalProfileData) return;
        allProfiles[selectedProfileName] = JSON.parse(JSON.stringify(originalProfileData));
        renderTabContent();
        resetChangeCounter();
        appendLog("INFO", `[PROFILES] Changes reverted for "${selectedProfileName}".`);
    }

    async function deleteProfile() {
        if (!selectedProfileName) return;
        if (!confirm(`Delete profile "${formatName(selectedProfileName)}" ? `)) return;
        delete allProfiles[selectedProfileName];
        selectedProfileName = null;
        originalProfileData = null;
        renderProfileList();
        document.getElementById('profile-tab-content').innerHTML = `
                < div id = "profile-empty-state" style = "display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; text-align:center;" >
                <div style="width:100px; height:100px; border-radius:24px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg, rgba(255,255,255,0.02) 0%, transparent 100%); border:1px solid rgba(255,255,255,0.04); margin-bottom:1.5rem; box-shadow: inset 0 2px 10px rgba(255,255,255,0.02), 0 10px 30px rgba(0,0,0,0.2);">
                    <span class="material-symbols-outlined" style="font-size:42px; color:#475569; filter:drop-shadow(0 4px 6px rgba(0,0,0,0.5));">folder_open</span>
                </div>
                <h3 style="font-size:16px; font-weight:800; color:#cbd5e1; margin:0 0 6px; letter-spacing:-0.02em;">No Profile Selected</h3>
                <p style="font-size:12px; color:#64748b; margin:0; max-width:220px; line-height:1.5;">Select a profile from the sidebar to view metrics and edit strategies.</p>
            </div >
            `;
        document.getElementById('btn-delete-profile')?.classList.add('hidden');
        document.getElementById('profile-name-display').textContent = 'Select a Profile';
        document.getElementById('profile-desc-display').textContent = 'Choose a profile from the sidebar';
        document.getElementById('profile-status')?.classList.add('hidden');
        await saveProfile();
    }

    function createNewProfile() {
        const name = prompt('Enter new profile name (lowercase, underscores):');
        if (!name) return;
        const safeName = name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
        if (allProfiles[safeName]) {
            alert('Profile already exists!');
            return;
        }
        allProfiles[safeName] = {
            strategy_variant: 'rubberband_reaper',
            htf_timeframe: '15m',
            ltf_timeframe: '5m',
            symbols: [],
            risk_per_trade_pct: 0.02,
            max_concurrent_positions: 1,
            icc_auto_entry_enabled: true,
            strategies: {}
        };
        renderProfileList();
        selectProfile(safeName);
        incrementChangeCounter();
    }

    // ── Activate Profile (set as the bot's active profile) ──────
    function activateProfile() {
        if (!selectedProfileName) return;

        // Update local cache
        activeProfileName = selectedProfileName;

        // Update configData directly
        if (typeof configData !== 'undefined') {
            configData.active_profile = selectedProfileName;
        }

        // Use settings_integrated's updateValue + autoSave if available
        if (typeof updateValue === 'function') {
            updateValue('APP_PROFILE', selectedProfileName);
        }
        if (typeof autoSave === 'function') {
            autoSave();
        }

        // Update button state
        updateActivateButton();

        // Re-render sidebar to update green dots
        renderProfileList();
        // Re-select to restore sidebar highlight
        selectProfile(selectedProfileName);

        console.log(`[PROFILES] Activated profile: ${selectedProfileName}`);
    }

    // Sync the activate button's visual state with configData.active_profile
    function updateActivateButton() {
        const btn = document.getElementById('profile-activate-btn');
        const dot = document.getElementById('profile-activate-dot');
        const text = document.getElementById('profile-activate-text');
        if (!btn || !dot || !text) return;

        const currentActive = activeProfileName || (typeof configData !== 'undefined' && configData.active_profile);
        const isActive = currentActive === selectedProfileName;

        if (isActive) {
            // Green glow — activated
            btn.style.background = 'rgba(16,185,129,0.1)';
            btn.style.color = '#34d399';
            btn.style.borderColor = 'rgba(16,185,129,0.3)';
            dot.style.background = '#10b981';
            dot.style.boxShadow = '0 0 8px #10b981, 0 0 16px rgba(16,185,129,0.4)';
            text.textContent = 'Activated';
        } else {
            // Red — not active
            btn.style.background = 'rgba(239,68,68,0.08)';
            btn.style.color = '#f87171';
            btn.style.borderColor = 'rgba(239,68,68,0.2)';
            dot.style.background = '#ef4444';
            dot.style.boxShadow = 'none';
            text.textContent = 'Activate';
        }
    }

    return { init, activateProfile };
})();
