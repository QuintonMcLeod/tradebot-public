/**
 * Backtest Module — GUI-based strategy backtester
 * Uses the same glass/card design system as analytics.css
 * All colors via CSS variables from the theme engine.
 */

(function () {
    'use strict';

    // ── Browser-safe API shim ─────────────────────────────────
    const api = window.api || {
        invoke: async () => null,
        readConfig: async () => ({}),
        send: () => { },
        on: () => { },
    };

    // ── State ────────────────────────────────────────────────
    let _running = false;
    let _profiles = [];
    let _profileData = {};   // full profile objects from config.json
    let _recordedSymbols = [];

    // ── DOM refs (lazy) ──────────────────────────────────────
    const $ = id => document.getElementById(id);

    // ── Init (called when Backtest nav is clicked) ───────────
    function init() {
        _loadProfiles();
        _loadRecordedData();
        _wireEvents();
    }

    // ── Load profiles into dropdown ──────────────────────────
    async function _loadProfiles() {
        try {
            const config = await api.readConfig();
            _profileData = config?.profiles || {};
            _profiles = Object.keys(_profileData);
            const sel = $('bt-profile-select');
            if (!sel) return;
            sel.innerHTML = _profiles.map(p =>
                `<option value="${p}" ${p === config?.active_profile ? 'selected' : ''}>${p}</option>`
            ).join('');
            // Load symbols for the initially selected profile
            _updateSymbolPills();
        } catch (e) {
            console.warn('[Backtest] Failed to load profiles:', e);
        }
    }

    // ── Load recorded data info ──────────────────────────────
    async function _loadRecordedData() {
        try {
            const info = await api.invoke('get-recording-info');
            if (!info) return;
            _recordedSymbols = info.symbols || [];
            _updateSymbolPills();
            _updateDateRange(info);
        } catch (e) {
            console.warn('[Backtest] No recorded data available:', e);
        }
    }

    function _updateSymbolPills() {
        const container = $('bt-symbol-pills');
        if (!container) return;

        // Get symbols from selected profile, fall back to recorded, then defaults
        const sel = $('bt-profile-select');
        const selectedProfile = sel?.value;
        const profileSymbols = selectedProfile && _profileData[selectedProfile]?.symbols;

        let symbols;
        if (_recordedSymbols.length > 0) {
            symbols = _recordedSymbols;
        } else if (Array.isArray(profileSymbols) && profileSymbols.length > 0) {
            symbols = profileSymbols;
        } else {
            symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURJPY', 'GBPJPY', 'AUDJPY'];
        }

        container.innerHTML = symbols.map(s => `
            <label class="bt-symbol-pill" data-symbol="${s}">
                <input type="checkbox" value="${s}" checked class="hidden">
                <span class="pill-text">${s}</span>
            </label>
        `).join('');

        // Wire click toggle
        container.querySelectorAll('.bt-symbol-pill').forEach(pill => {
            pill.addEventListener('click', () => {
                const cb = pill.querySelector('input');
                cb.checked = !cb.checked;
                pill.classList.toggle('active', cb.checked);
            });
            // Initial state
            pill.classList.add('active');
        });
    }

    function _updateDateRange(info) {
        const startInput = $('bt-start-date');
        const endInput = $('bt-end-date');
        if (!startInput || !endInput) return;

        if (info.earliest) startInput.value = info.earliest;
        if (info.latest) endInput.value = info.latest;
    }

    // ── Wire events ──────────────────────────────────────────
    function _wireEvents() {
        const runBtn = $('bt-run-btn');
        if (runBtn && !runBtn._wired) {
            runBtn.addEventListener('click', _runBacktest);
            runBtn._wired = true;
        }

        // Mode toggle
        const modeToggle = $('bt-mode-toggle');
        if (modeToggle && !modeToggle._wired) {
            modeToggle.addEventListener('change', () => {
                const label = $('bt-mode-label');
                if (label) label.textContent = modeToggle.checked ? 'Replay Mode' : 'Bar Close';
            });
            modeToggle._wired = true;
        }

        // Profile dropdown → update symbols on change
        const profileSel = $('bt-profile-select');
        if (profileSel && !profileSel._wired) {
            profileSel.addEventListener('change', () => _updateSymbolPills());
            profileSel._wired = true;
        }
    }

    // ── Run backtest (Replayer) ───────────────────────────────────────────
    async function _runBacktest() {
        if (_running) return;

        const startDate = $('bt-start-date')?.value;
        const endDate = $('bt-end-date')?.value;

        // Get selected symbols
        const pills = document.querySelectorAll('#bt-symbol-pills input:checked');
        const symbols = Array.from(pills).map(cb => cb.value);

        if (!startDate || !endDate) {
            _showStatus('Please select a date range', 'error');
            return;
        }
        if (symbols.length === 0) {
            _showStatus('Please select at least one symbol', 'error');
            return;
        }

        _running = true;
        _showStatus('Replay running...', 'running');
        _setRunButtonState(true);
        _hideResults();
        _showLogStream();

        // Register live progress listener
        if (window.api?.onBacktestProgress) {
            window.api.onBacktestProgress((line) => _appendLogLine(line));
        }

        try {
            const result = await api.invoke('run-backtest', {
                start_date: startDate,
                end_date: endDate,
                symbols: symbols,
                balance: 5700,
            });

            if (result?.error) {
                _showStatus(result.error, 'error');
            } else {
                _showStatus('Replay complete \u2713', 'success');
                _renderResults(result);
            }
        } catch (e) {
            _showStatus(`Error: ${e.message || e}`, 'error');
        } finally {
            _running = false;
            _setRunButtonState(false);
            if (window.api?.offBacktestProgress) window.api.offBacktestProgress();
        }
    }

    // ── Live log stream panel ─────────────────────────────────────────────
    function _showLogStream() {
        let panel = $('bt-log-stream');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'bt-log-stream';
            panel.style.cssText = 'background:var(--surface-2,#0d1117);border:1px solid var(--border,#30363d);border-radius:8px;padding:12px;margin:12px 0;max-height:220px;overflow-y:auto;font-family:monospace;font-size:11px;color:var(--text-secondary,#8b949e);line-height:1.5;';
            const anchor = $('bt-results') || document.body;
            anchor.parentElement ? anchor.parentElement.insertBefore(panel, anchor) : document.body.appendChild(panel);
        }
        panel.innerHTML = '<span style="color:var(--accent,#58a6ff)">\u25cf Replay starting\u2026</span><br>';
        panel.style.display = 'block';
    }

    function _appendLogLine(line) {
        const panel = $('bt-log-stream');
        if (!panel) return;
        let c = line
            .replace(/\[GUILLOTINE/g, '<span style="color:#f97316">[GUILLOTINE')
            .replace(/\[SAR/g, '<span style="color:#a78bfa">[SAR')
            .replace(/\[PHOENIX/g, '<span style="color:#34d399">[PHOENIX')
            .replace(/\[ERROR\]/g, '<span style="color:#f87171">[ERROR]</span>')
            .replace(/\[REPLAY\]/g, '<span style="color:#60a5fa">[REPLAY]</span>');
        const diff = (c.match(/<span/g) || []).length - (c.match(/<\/span>/g) || []).length;
        for (let i = 0; i < diff; i++) c += '</span>';
        panel.innerHTML += c + '<br>';
        panel.scrollTop = panel.scrollHeight;
    }


    // ── Status badge ─────────────────────────────────────────
    function _showStatus(msg, type) {
        const badge = $('bt-status-badge');
        if (!badge) return;
        badge.textContent = msg;
        badge.className = 'bt-status-badge';
        if (type === 'error') badge.classList.add('error');
        else if (type === 'running') badge.classList.add('running');
        else if (type === 'success') badge.classList.add('success');
        badge.classList.remove('hidden');
    }

    function _setRunButtonState(running) {
        const btn = $('bt-run-btn');
        if (!btn) return;
        if (running) {
            btn.innerHTML = `<span class="material-symbols-outlined bt-spin" style="font-size:16px;">progress_activity</span> Running...`;
            btn.disabled = true;
            btn.style.opacity = '0.6';
        } else {
            btn.innerHTML = `<span class="material-symbols-outlined" style="font-size:16px;">play_arrow</span> Run Backtest`;
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    }

    // ── Hide results ─────────────────────────────────────────
    function _hideResults() {
        const resultsSection = $('bt-results');
        if (resultsSection) resultsSection.classList.add('hidden');
    }

    // ── Render results ───────────────────────────────────────
    function _renderResults(data) {
        const resultsSection = $('bt-results');
        if (!resultsSection) return;
        resultsSection.classList.remove('hidden');

        // Hero metrics
        const pnl = data.total_pnl || 0;
        const winRate = data.win_rate || 0;
        const trades = data.total_trades || 0;
        const maxDD = data.max_drawdown || 0;

        const pnlEl = $('bt-metric-pnl');
        if (pnlEl) {
            pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
            pnlEl.style.color = pnl >= 0 ? 'var(--success)' : 'var(--error)';
        }

        const wrEl = $('bt-metric-winrate');
        if (wrEl) wrEl.textContent = `${winRate.toFixed(1)}%`;

        const trEl = $('bt-metric-trades');
        if (trEl) trEl.textContent = trades;

        const ddEl = $('bt-metric-drawdown');
        if (ddEl) ddEl.textContent = `${maxDD.toFixed(2)}%`;

        // Profit Factor
        const pfEl = $('bt-metric-pf');
        if (pfEl) pfEl.textContent = (data.profit_factor || 0).toFixed(2);

        // Avg Win/Loss
        const awEl = $('bt-metric-avgwin');
        if (awEl) awEl.textContent = `$${(data.avg_win || 0).toFixed(2)}`;
        const alEl = $('bt-metric-avgloss');
        if (alEl) alEl.textContent = `$${(data.avg_loss || 0).toFixed(2)}`;

        // R:R
        const rrEl = $('bt-metric-rr');
        if (rrEl) rrEl.textContent = data.risk_reward ? `${data.risk_reward.toFixed(1)}:1` : 'N/A';

        // Trade history table
        _renderTradeHistory(data.trades || []);

        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function _renderTradeHistory(trades) {
        const tbody = $('bt-trade-tbody');
        if (!tbody) return;

        if (trades.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:40px 16px; font-style:italic;">
                <span class="material-symbols-outlined" style="font-size:28px; display:block; margin-bottom:8px; opacity:0.25;">search_off</span>
                No trades in this backtest
            </td></tr>`;
            return;
        }

        tbody.innerHTML = trades.map(t => {
            const pnl = t.pnl || 0;
            const isWin = pnl >= 0;
            return `<tr>
                <td style="color:var(--text-secondary);">${t.time ? new Date(t.time).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--'}</td>
                <td style="font-weight:700; color:var(--text-main);">${t.symbol || '--'}</td>
                <td style="text-align:center;"><span class="side-badge ${t.side || ''}">${(t.side || '--').toUpperCase()}</span></td>
                <td style="text-align:center;"><span class="wl-dot ${isWin ? 'win' : 'loss'}"></span>${isWin ? 'Win' : 'Loss'}</td>
                <td style="text-align:right; font-weight:700; color:${isWin ? 'var(--success)' : 'var(--error)'};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td style="color:var(--text-muted);">${t.duration || '--'}</td>
                <td style="color:var(--text-muted);">${t.reason || '--'}</td>
            </tr>`;
        }).join('');
    }

    // ── Expose module ────────────────────────────────────────
    window.backtestModule = { init };

})();
