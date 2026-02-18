// ═══════════════════════════════════════════════════════════
// PROFILES MODULE - Integrated Profile Editor
// ═══════════════════════════════════════════════════════════
window.profilesModule = (function () {
    let allProfiles = {};
    let selectedProfileName = null;
    let originalProfileData = null;
    let changeCount = 0;
    let initialized = false;

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
        { value: 'icc_core', label: 'ICC (Standard)' },
        { value: 'supply_demand', label: 'Supply & Demand' },
        { value: 'trend_rider', label: 'Trend Rider (EMA Pullback)' },
        { value: 'session_momentum', label: 'Session Momentum (VWAP)' },
        { value: 'bearish_engulfing', label: 'Engulfing Reversal' },
        // 🪙 Crypto-Specific Strategies
        { value: 'crypto_rsi_macd', label: '🪙 RSI + MACD (Crypto)' },
        { value: 'crypto_vwap_reversion', label: '🪙 VWAP Reversion (Crypto)' },
        { value: 'crypto_double_macd', label: '🪙 Double MACD Scalper (Crypto)' },
        { value: 'crypto_grid', label: '🪙 Virtual Grid (Crypto)' }
    ];

    const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];

    async function init() {
        if (initialized) return;
        await loadProfiles();
        setupEventListeners();
        renderProfileList();
        initialized = true;
    }

    async function loadProfiles() {
        try {
            const result = await window.api.invoke('read-profiles');
            if (result) {
                // Parse YAML using simple regex (no external lib needed for reading)
                allProfiles = parseYaml(result);
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
                    if (val === 'true') profiles[currentProfile][key] = true;
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
        // Tab navigation
        document.getElementById('profile-tabs')?.querySelectorAll('.profile-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.profile-tab-btn').forEach(b => {
                    b.classList.remove('active', 'bg-teal-500/20', 'text-teal-300', 'border', 'border-teal-500/40');
                    b.classList.add('text-slate-400');
                });
                btn.classList.add('active', 'bg-teal-500/20', 'text-teal-300', 'border', 'border-teal-500/40');
                btn.classList.remove('text-slate-400');
                renderTabContent(btn.dataset.tab);
            });
        });

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
            item.className = 'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-white/5 text-slate-400 hover:text-white transition-all';
            item.dataset.profile = name;

            const symbolCount = profile.symbols?.length || 0;
            item.innerHTML = `
                <span class="material-symbols-outlined text-base opacity-60">tune</span>
                <div class="flex-1 min-w-0">
                    <div class="text-xs font-bold truncate">${formatName(name)}</div>
                    <div class="text-[9px] text-slate-500">${symbolCount} symbols</div>
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

        // Update sidebar active state
        document.querySelectorAll('#profile-list > div').forEach(item => {
            const isActive = item.dataset.profile === name;
            item.className = isActive
                ? 'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer bg-teal-500/20 text-teal-300 border border-teal-500/30'
                : 'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-white/5 text-slate-400 hover:text-white transition-all';
        });

        // Update header
        document.getElementById('profile-name-display').textContent = formatName(name);
        document.getElementById('profile-desc-display').textContent = `${allProfiles[name].symbols?.length || 0} symbols`;
        document.getElementById('profile-status')?.classList.remove('hidden');
        document.getElementById('btn-delete-profile')?.classList.remove('hidden');

        // Hide empty state, render first tab
        document.getElementById('profile-empty-state')?.classList.add('hidden');
        const firstTab = document.querySelector('.profile-tab-btn');
        if (firstTab) firstTab.click();

        resetChangeCounter();
    }

    function renderTabContent(tabName) {
        if (!selectedProfileName) return;
        const profile = allProfiles[selectedProfileName];
        const container = document.getElementById('profile-tab-content');
        if (!container) return;

        let html = '<div class="max-w-2xl mx-auto">';

        switch (tabName) {
            case 'general':
                html += renderGeneralTab(profile);
                break;
            case 'symbols':
                html += renderSymbolsTab(profile);
                break;
            case 'risk':
                html += renderRiskTab(profile);
                break;
            case 'icc':
                html += renderIccTab(profile);
                break;
            case 'schedule':
                html += renderScheduleTab(profile);
                break;
        }

        html += '</div>';
        container.innerHTML = html;
        attachTabEventListeners(tabName);
    }

    function renderGeneralTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Core Settings</div>
            ${renderSelect('strategy_variant', 'Default Strategy', profile.strategy_variant, STRATEGY_OPTIONS)}
            <div class="grid grid-cols-2 gap-3 mt-3">
                ${renderSelect('htf_timeframe', 'HTF Timeframe', profile.htf_timeframe, TIMEFRAME_OPTIONS.map(t => ({ value: t, label: t })))}
                ${renderSelect('ltf_timeframe', 'LTF Timeframe', profile.ltf_timeframe, TIMEFRAME_OPTIONS.map(t => ({ value: t, label: t })))}
            </div>
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20 mt-6">Asset Strategies</div>
            <div class="grid grid-cols-2 gap-3">
                ${['crypto', 'forex', 'stocks', 'etf', 'metals', 'futures'].map(asset =>
            renderSelect(`strategies.${asset}`, asset.charAt(0).toUpperCase() + asset.slice(1), profile.strategies?.[asset] || profile.strategy_variant, STRATEGY_OPTIONS)
        ).join('')}
            </div>
        `;
    }

    function renderSymbolsTab(profile) {
        const symbols = profile.symbols || [];
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Trading Symbols</div>
            <p class="text-[10px] text-slate-500 mb-3">Type a symbol and press Enter to add.</p>
            <div class="bg-black/40 border border-white/5 rounded-xl p-4 min-h-[200px] flex flex-wrap gap-2 content-start">
                ${symbols.map(s => `
                    <span class="symbol-chip inline-flex items-center gap-1 px-3 py-1.5 bg-teal-500/15 border border-teal-500/30 rounded-full text-[11px] font-bold text-teal-400" data-symbol="${s}">
                        ${s}
                        <span class="remove-symbol material-symbols-outlined text-xs cursor-pointer opacity-60 hover:opacity-100 hover:text-red-400">close</span>
                    </span>
                `).join('')}
                <input type="text" id="symbol-input" placeholder="Add symbol..." class="flex-1 min-w-[100px] bg-transparent border-none outline-none text-xs text-white placeholder:text-slate-600">
            </div>
        `;
    }

    function renderRiskTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Risk Management</div>
            <div class="space-y-3">
                ${renderSlider('risk_per_trade_pct', 'Risk Per Trade', profile.risk_per_trade_pct || 0.02, 0.01, 0.30, 0.01, '%', 100)}
                ${renderSlider('max_concurrent_positions', 'Max Positions', profile.max_concurrent_positions || 1, 1, 10, 1, '')}
                ${renderSlider('max_pyramid_entries', 'Pyramid Entries', profile.max_pyramid_entries || 3, 1, 10, 1, '')}
                ${renderToggle('multi_position_enabled', 'Multi-Position Mode', profile.multi_position_enabled)}
            </div>
        `;
    }

    function renderIccTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">ICC Scoring</div>
            <div class="space-y-3">
                ${renderSlider('icc_entry_score_threshold', 'Entry Threshold', profile.icc_entry_score_threshold || 60, 0, 100, 5, '')}
                ${renderSlider('icc_score_continuation_points', 'Continuation Pts', profile.icc_score_continuation_points || 60, 0, 100, 5, '')}
                ${renderSlider('icc_score_sweep_points', 'Sweep Points', profile.icc_score_sweep_points || 25, 0, 50, 5, '')}
                ${renderToggle('icc_auto_entry_enabled', 'Auto Entry', profile.icc_auto_entry_enabled)}
                ${renderToggle('icc_aggressive_mode', 'Aggressive Mode', profile.icc_aggressive_mode)}
            </div>
        `;
    }

    function renderScheduleTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Trading Schedule</div>
            <div class="space-y-3">
                ${renderToggle('session_gate_enabled', 'Session Gate', profile.session_gate_enabled)}
                ${renderToggle('sabbath_enabled', 'Sabbath Mode', profile.sabbath_enabled)}
                ${renderToggle('continuous_mode', 'Continuous (24/7)', profile.continuous_mode)}
                ${renderToggle('crypto_only', 'Crypto Only', profile.crypto_only)}
            </div>
        `;
    }

    function renderSelect(key, label, value, options) {
        return `
            <div class="bg-black/30 border border-white/5 rounded-xl p-3 flex items-center justify-between">
                <span class="text-xs font-bold text-slate-300">${label}</span>
                <select class="input-field bg-black/60 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white min-w-[140px]" data-key="${key}">
                    ${options.map(o => `<option value="${o.value || o}" ${(value === (o.value || o)) ? 'selected' : ''}>${o.label || o}</option>`).join('')}
                </select>
            </div>
        `;
    }

    function renderSlider(key, label, value, min, max, step, suffix, mult = 1) {
        const display = (value * mult).toFixed(mult > 1 ? 1 : 2);
        return `
            <div class="bg-black/30 border border-white/5 rounded-xl p-4">
                <div class="flex justify-between items-center mb-2">
                    <span class="text-xs font-bold text-slate-300">${label}</span>
                    <span class="text-lg font-black text-teal-400" id="val-${key}">${display}${suffix}</span>
                </div>
                <input type="range" class="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer slider-range" data-key="${key}" data-mult="${mult}" data-suffix="${suffix}" min="${min}" max="${max}" step="${step}" value="${value}">
            </div>
        `;
    }

    function renderToggle(key, label, value) {
        return `
            <div class="bg-black/30 border border-white/5 rounded-xl p-3 flex items-center justify-between">
                <span class="text-xs font-bold text-slate-300">${label}</span>
                <div class="toggle-switch ${value ? 'active' : ''}" data-key="${key}">
                    <div class="toggle-knob"></div>
                </div>
            </div>
        `;
    }

    function attachTabEventListeners(tabName) {
        // Selects
        document.querySelectorAll('#profile-tab-content select').forEach(el => {
            el.addEventListener('change', handleFieldChange);
        });

        // Sliders
        document.querySelectorAll('#profile-tab-content .slider-range').forEach(el => {
            el.addEventListener('input', handleSliderChange);
        });

        // Toggles
        document.querySelectorAll('#profile-tab-content .toggle-switch').forEach(el => {
            el.addEventListener('click', handleToggleClick);
        });

        // Symbols
        if (tabName === 'symbols') {
            document.getElementById('symbol-input')?.addEventListener('keydown', e => {
                if (e.key === 'Enter' && e.target.value.trim()) {
                    const sym = e.target.value.trim().toUpperCase();
                    if (!allProfiles[selectedProfileName].symbols) allProfiles[selectedProfileName].symbols = [];
                    if (!allProfiles[selectedProfileName].symbols.includes(sym)) {
                        allProfiles[selectedProfileName].symbols.push(sym);
                        renderTabContent('symbols');
                        incrementChangeCounter();
                    }
                    e.target.value = '';
                }
            });
            document.querySelectorAll('.remove-symbol').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const sym = e.target.closest('.symbol-chip').dataset.symbol;
                    allProfiles[selectedProfileName].symbols = (allProfiles[selectedProfileName].symbols || []).filter(s => s !== sym);
                    renderTabContent('symbols');
                    incrementChangeCounter();
                });
            });
        }
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
        document.getElementById(`val-${key}`).textContent = `${(val * mult).toFixed(mult > 1 ? 1 : 2)}${suffix}`;
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
        document.getElementById('profile-change-counter').textContent = `${changeCount} unsaved change${changeCount !== 1 ? 's' : ''}`;
    }

    function resetChangeCounter() {
        changeCount = 0;
        document.getElementById('profile-change-counter').textContent = '0 unsaved changes';
    }

    async function saveProfile() {
        try {
            // Build YAML string
            let yaml = 'profiles:\n';
            for (const [name, profile] of Object.entries(allProfiles)) {
                yaml += `  ${name}:\n`;
                for (const [key, val] of Object.entries(profile)) {
                    if (key === 'symbols' && Array.isArray(val)) {
                        yaml += `    symbols:\n`;
                        val.forEach(s => yaml += `    - ${s}\n`);
                    } else if (key === 'strategies' && typeof val === 'object') {
                        yaml += `    strategies:\n`;
                        for (const [asset, strat] of Object.entries(val)) {
                            yaml += `      ${asset}: ${strat}\n`;
                        }
                    } else if (typeof val === 'boolean') {
                        yaml += `    ${key}: ${val}\n`;
                    } else if (typeof val === 'number') {
                        yaml += `    ${key}: ${val}\n`;
                    } else if (val !== null && val !== undefined) {
                        yaml += `    ${key}: ${val}\n`;
                    }
                }
            }
            await window.api.invoke('save-profiles', yaml);
            originalProfileData = JSON.parse(JSON.stringify(allProfiles[selectedProfileName]));
            resetChangeCounter();
            appendLog("SUCCESS", `[PROFILES] Profile "${selectedProfileName}" saved.`);
        } catch (err) {
            console.error('[PROFILES] Save failed:', err);
            appendLog("ERROR", `[PROFILES] Save failed: ${err.message}`);
        }
    }

    function revertChanges() {
        if (!selectedProfileName || !originalProfileData) return;
        allProfiles[selectedProfileName] = JSON.parse(JSON.stringify(originalProfileData));
        const activeTab = document.querySelector('.profile-tab-btn.active');
        if (activeTab) renderTabContent(activeTab.dataset.tab);
        resetChangeCounter();
        appendLog("INFO", `[PROFILES] Changes reverted for "${selectedProfileName}".`);
    }

    async function deleteProfile() {
        if (!selectedProfileName) return;
        if (!confirm(`Delete profile "${formatName(selectedProfileName)}"?`)) return;
        delete allProfiles[selectedProfileName];
        selectedProfileName = null;
        originalProfileData = null;
        renderProfileList();
        document.getElementById('profile-tab-content').innerHTML = `
            <div id="profile-empty-state" class="flex flex-col items-center justify-center h-full text-center">
                <span class="material-symbols-outlined text-5xl text-slate-600 mb-3">folder_open</span>
                <p class="text-slate-500 text-sm">Select a profile from the sidebar</p>
            </div>
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

    return { init };
})();
