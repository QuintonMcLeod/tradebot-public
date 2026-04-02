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
    
    // Sort State
    let _btSortKey = null;
    let _btSortDir = null;
    let _lastBtTrades = [];
    let _lastBtMetrics = null;
    let _btInitialCapital = 0;

    // ── DOM refs (lazy) ──────────────────────────────────────
    const $ = id => document.getElementById(id);

    // ── Init (called when Backtest nav is clicked) ───────────
    function init() {
        _loadProfiles();
        _loadRecordedData();
        _wireEvents();
        _setupKineticScroll();
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

        // Get symbols from selected profile first, fall back to recorded, then defaults
        const sel = $('bt-profile-select');
        const selectedProfile = sel?.value;
        const profileSymbols = selectedProfile && _profileData[selectedProfile]?.symbols;

        let symbols;
        if (Array.isArray(profileSymbols) && profileSymbols.length > 0) {
            symbols = profileSymbols;
        } else if (_recordedSymbols.length > 0) {
            symbols = _recordedSymbols;
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

        if (info.latest) {
            endInput.value = info.latest;
            const endDate = new Date(info.latest);
            if (!isNaN(endDate.getTime())) {
                endDate.setDate(endDate.getDate() - 14);
                const yyyy = endDate.getFullYear();
                const mm = String(endDate.getMonth() + 1).padStart(2, '0');
                const dd = String(endDate.getDate()).padStart(2, '0');
                startInput.value = `${yyyy}-${mm}-${dd}`;
            } else if (info.earliest) {
                startInput.value = info.earliest;
            }
        } else if (info.earliest) {
            startInput.value = info.earliest;
        }
    }

    // ── Wire events ──────────────────────────────────────────
    function _wireEvents() {
        const runBtn = $('bt-run-btn');
        if (runBtn && !runBtn._wired) {
            runBtn.addEventListener('click', _runBacktest);
            runBtn._wired = true;
        }

        const clearBtn = $('bt-clear-btn');
        if (clearBtn && !clearBtn._wired) {
            clearBtn.addEventListener('click', _clearBacktest);
            clearBtn._wired = true;
        }

        const exportBtn = $('bt-export-csv');
        if (exportBtn && !exportBtn._wired) {
            exportBtn.addEventListener('click', _exportCSV);
            exportBtn._wired = true;
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

        // Sort headers
        document.querySelectorAll('.bt-sortable-th').forEach(th => {
            if (!th._wired) {
                th.addEventListener('click', _handleBtSortClick);
                th._wired = true;
            }
        });
    }

    // ── Sorting Logic ──────────────────────────────────────────
    function _sortBtValue(trade, key) {
        switch (key) {
            case 'time': return new Date(trade.time || 0).getTime();
            case 'symbol': return (trade.symbol || '').toLowerCase();
            case 'side': return (trade.side || 'long').toLowerCase();
            case 'result': {
                const pnl = parseFloat(trade.pnl) || 0;
                return pnl > 0 ? 2 : (pnl < 0 ? 0 : 1);
            }
            case 'pnl': return parseFloat(trade.pnl) || 0;
            case 'duration': {
                if (trade.duration_seconds) return trade.duration_seconds;
                if (trade.duration) return trade.duration; // Fallback string sort if secs missing
                return 0;
            }
            case 'reason': return (trade.reason || '').toLowerCase();
            case 'strategy': return (typeof trade.strategy === 'string' ? trade.strategy : (trade.strategy_name || '')).toLowerCase();
            case 'capital': return trade._runningCapital || 0;
            default: return 0;
        }
    }

    function _sortBtTrades(trades) {
        if (!_btSortKey || !_btSortDir) return trades;
        const key = _btSortKey;
        const mult = _btSortDir === 'asc' ? 1 : -1;
        return [...trades].sort((a, b) => {
            const va = _sortBtValue(a, key);
            const vb = _sortBtValue(b, key);
            if (typeof va === 'string' && typeof vb === 'string') return mult * va.localeCompare(vb);
            if (typeof va === 'string') return mult * -1; // Numbers first
            if (typeof vb === 'string') return mult * 1;
            return mult * (va - vb);
        });
    }

    function _updateBtSortHeaders() {
        document.querySelectorAll('.bt-sortable-th').forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
            if (th.dataset.sortKey === _btSortKey) {
                if (_btSortDir === 'asc') th.classList.add('sort-asc');
                if (_btSortDir === 'desc') th.classList.add('sort-desc');
            }
        });
    }

    function _handleBtSortClick(e) {
        const th = e.currentTarget;
        const key = th.dataset.sortKey;
        if (!key) return;

        if (_btSortKey === key) {
            if (_btSortDir === 'asc') _btSortDir = 'desc';
            else if (_btSortDir === 'desc') { _btSortKey = null; _btSortDir = null; }
        } else {
            _btSortKey = key;
            _btSortDir = 'desc';
        }

        _updateBtSortHeaders();
        if (_lastBtTrades.length > 0) {
            _renderTradeHistory(_lastBtTrades, true);
        }
    }

    // ── Run backtest (Replayer) ───────────────────────────────────────────
    async function _runBacktest() {
        if (_running) return;

        const startDate = $('bt-start-date')?.value;
        const endDate = $('bt-end-date')?.value;
        const startCapital = parseFloat($('bt-start-capital')?.value || 100);
        const strategyOverride = $('bt-strategy-select')?.value || null;

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
        _showProgressBar();

        // Register live progress listener
        if (window.api?.onBacktestProgress) {
            window.api.onBacktestProgress((data) => _updateProgressBar(data));
        }

        try {
            const useApiFallback = !$('bt-mode-toggle').checked;
            const result = await api.invoke('run-backtest', {
                start_date: startDate,
                end_date: endDate,
                symbols: symbols,
                balance: startCapital,
                strategy: strategyOverride,
                use_api_fallback: useApiFallback,
            });

            if (result?.error) {
                _showStatus(result.error, 'error');
            } else {
                _showStatus('Replay complete \u2713', 'success');
                // Hide progress bar on success
                const panel = $('bt-progress-panel');
                if (panel) panel.style.display = 'none';
                _renderResults(result);
            }
        } catch (e) {
            _showStatus(`Error: ${e.message || e}`, 'error');
        } finally {
            _running = false;
            _setRunButtonState(false);
            const panel = $('bt-progress-panel');
            if (panel && result?.error) panel.style.display = 'none';
            if (window.api?.offBacktestProgress) window.api.offBacktestProgress();
        }
    }

    // ── Live Progress Panel ─────────────────────────────────────────────
    function _showProgressBar() {
        let panel = $('bt-progress-panel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'bt-progress-panel';
            panel.style.cssText = 'background:var(--surface-2,#0d1117);border:1px solid var(--border,#30363d);border-radius:8px;padding:16px;margin:12px 0;flex-shrink:0;';
            const anchor = $('bt-results') || document.body;
            anchor.parentElement ? anchor.parentElement.insertBefore(panel, anchor) : document.body.appendChild(panel);
        }
        panel.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="color:var(--text-primary,#c9d1d9);font-weight:600;font-size:13px;">Simulating Timeline...</span>
                <span id="bt-progress-text" style="color:var(--text-secondary,#8b949e);font-size:12px;font-variant-numeric:tabular-nums;">0%</span>
            </div>
            <div style="width:100%;height:6px;background:var(--surface-3,#21262d);border-radius:3px;overflow:hidden;">
                <div id="bt-progress-fill" style="width:0%;height:100%;background:var(--accent,#58a6ff);transition:width 0.2s ease;"></div>
            </div>
            <div id="bt-progress-details" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;font-size:11px;color:var(--text-secondary,#8b949e);">
            </div>
        `;
        panel.style.display = 'block';
        
        // Hide legacy log stream if it's there
        const logPanel = $('bt-log-stream');
        if (logPanel) logPanel.style.display = 'none';
    }

    function _updateProgressBar(progressState) {
        if (!progressState || typeof progressState !== 'object') return;
        
        // If the payload from main is an array, it likely comes from a rogue string log that snuck through
        // but our main.js now emits an object map of symbols.
        if (Array.isArray(progressState)) return;
        
        let totalPct = 0;
        let count = 0;
        let detailsHtml = '';

        for (const sym in progressState) {
            const p = progressState[sym];
            totalPct += p.pct;
            count++;
            const color = p.pct === 100 ? 'var(--success,#3fb950)' : 'var(--text-secondary,#8b949e)';
            const detailsText = p.details ? ` <span style="color:var(--text-secondary,#8b949e);margin-left:4px;">${p.details}</span>` : '';
            detailsHtml += `<div style="background:var(--surface-1,#010409);padding:4px 8px;border-radius:4px;border:1px solid var(--border,#30363d);"><span style="color:var(--text-primary,#c9d1d9)">${sym}</span> <span style="color:${color}">${p.pct}%</span>${detailsText}</div>`;
        }

        if (count > 0) {
            const avgPct = Math.round(totalPct / count);
            const fill = $('bt-progress-fill');
            const text = $('bt-progress-text');
            const details = $('bt-progress-details');
            
            if (fill) fill.style.width = `${avgPct}%`;
            if (text) text.textContent = `${avgPct}%`;
            if (details) details.innerHTML = detailsHtml;
        }
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
        if (!data) return;
        _lastBtMetrics = data;
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

        // Total Capital (final balance after backtest)
        const capEl = $('bt-metric-capital');
        if (capEl) {
            const finalBal = data.final_capital || data.final_balance || (data.initial_capital || 0) + pnl;
            capEl.textContent = `$${finalBal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            capEl.style.color = pnl >= 0 ? 'var(--success)' : 'var(--error)';
        }

        // Payout — same velocity-based logic as the Payout Mentor
        const payoutEl = $('bt-metric-payout');
        if (payoutEl) {
            if (pnl <= 0) {
                payoutEl.textContent = '$0.00';
                payoutEl.style.color = 'var(--text-muted)';
            } else {
                const initCap = data.initial_capital || parseFloat($('bt-start-capital')?.value || 100);
                const velocityPct = initCap > 0 ? (pnl / initCap) * 100 : 0;
                const recommendedPct = velocityPct >= 2.5 ? 0.75 : 0.50;
                const payout = pnl * recommendedPct;
                payoutEl.textContent = `$${payout.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                payoutEl.style.color = '#34d399';
            }
        }

        // Risk Rate — from selected profile config
        const riskEl = $('bt-metric-risk');
        if (riskEl) {
            const selProfile = $('bt-profile-select')?.value;
            const profCfg = selProfile ? _profileData[selProfile] : null;
            const isDynamic = profCfg?.risk_dynamic_auto === true || profCfg?.risk_dynamic_auto === 'true';
            const riskPct = parseFloat(profCfg?.risk_per_trade_pct || 0);
            if (isDynamic) {
                riskEl.textContent = 'Dynamic';
                riskEl.style.color = '#a78bfa';  // purple for AI-driven
            } else if (riskPct > 0) {
                riskEl.textContent = `${riskPct}%`;
                riskEl.style.color = riskPct >= 3 ? 'var(--error)' : '#fbbf24';
            } else {
                riskEl.textContent = '1%';
                riskEl.style.color = '#fbbf24';
            }
        }

        // Store initial capital for running capital computation
        _btInitialCapital = data.initial_capital || parseFloat($('bt-start-capital')?.value || 100);

        // Trade history table
        _renderTradeHistory(data.trades || []);

        // Show export button if we have trades
        const exportBtn = $('bt-export-csv');
        if (exportBtn) {
            if ((data.trades || []).length > 0) {
                exportBtn.style.display = 'flex';
            } else {
                exportBtn.style.display = 'none';
            }
        }

        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function _renderTradeHistory(trades, isReSort = false) {
        const tbody = $('bt-trade-tbody');
        if (!tbody) return;

        if (!isReSort) _lastBtTrades = trades || [];

        // Compute running capital for each trade (based on chronological order)
        // Sort by time first for capital calculation
        const chronological = [..._lastBtTrades].sort((a, b) => {
            const ta = new Date(a.time || 0).getTime();
            const tb = new Date(b.time || 0).getTime();
            return ta - tb;
        });
        let runCap = _btInitialCapital;
        for (const t of chronological) {
            runCap += (t.pnl || 0);
            t._runningCapital = runCap;
        }

        const sorted = _sortBtTrades(_lastBtTrades);

        if (sorted.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-dim); padding:40px 16px; font-style:italic;">
                <span class="material-symbols-outlined" style="font-size:28px; display:block; margin-bottom:8px; opacity:0.25;">search_off</span>
                No trades in this backtest
            </td></tr>`;
            return;
        }

        tbody.innerHTML = sorted.map(t => {
            const pnl = t.pnl || 0;
            const isWin = pnl >= 0;
            const cap = t._runningCapital || 0;
            const capColor = cap >= _btInitialCapital ? 'var(--success)' : 'var(--error)';
            const stratStr = typeof t.strategy === 'string' ? t.strategy : (t.strategy_name || '--');
            return `<tr>
                <td style="color:var(--text-secondary);">${t.time ? new Date(t.time).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--'}</td>
                <td style="font-weight:700; color:var(--text-main);">${t.symbol || '--'}</td>
                <td style="text-align:center;"><span class="side-badge ${t.side || ''}">${(t.side || '--').toUpperCase()}</span></td>
                <td style="text-align:center;"><span class="wl-dot ${isWin ? 'win' : 'loss'}"></span>${isWin ? 'Win' : 'Loss'}</td>
                <td style="text-align:right; font-weight:700; color:${isWin ? 'var(--success)' : 'var(--error)'};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td style="text-align:right; font-weight:600; color:${capColor}; font-variant-numeric:tabular-nums;">$${cap.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                <td style="color:var(--text-muted);">${t.duration || '--'}</td>
                <td style="color:var(--text-muted);">${stratStr}</td>
                <td style="color:var(--text-muted);">${t.reason || '--'}</td>
            </tr>`;
        }).join('');
    }

    function _clearBacktest() {
        if (_running) return;
        
        // Hide and clear results
        _hideResults();
        
        // Clear log stream
        const panel = $('bt-log-stream');
        if (panel) {
            panel.innerHTML = '';
            panel.style.display = 'none';
        }
        
        // Hide export button
        const exportBtn = $('bt-export-csv');
        if (exportBtn) exportBtn.style.display = 'none';
        
        // Reset status badge
        _showStatus('Ready', 'ready');
        
        // Note: we don't clear the configuration inputs so the user can easily re-run a slightly modified test
    }

    // ── Export CSV ────────────────────────────────────────────
    function _exportCSV() {
        if (!_lastBtTrades || _lastBtTrades.length === 0) return;

        const headers = ['Time', 'Symbol', 'Side', 'Result', 'PnL', 'Capital', 'Duration', 'Exit Reason'];
        const rows = _lastBtTrades.map(t => {
            const pnl = t.pnl || 0;
            const timeStr = t.time ? new Date(t.time).toLocaleString() : '';
            return [
                timeStr,
                t.symbol || '',
                (t.side || '').toUpperCase(),
                pnl >= 0 ? 'Win' : 'Loss',
                pnl.toFixed(2),
                (t._runningCapital || 0).toFixed(2),
                t.duration || '',
                t.reason || '',
            ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(',');
        });

        const m = _lastBtMetrics || {};
        const pnl = m.total_pnl || 0;
        const summaryRows = [
            ['Total PnL', (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2)],
            ['Win Rate', (m.win_rate || 0).toFixed(1) + '%'],
            ['Total Trades', m.total_trades || 0],
            ['Max Drawdown', (m.max_drawdown || 0).toFixed(2) + '%'],
            ['Profit Factor', (m.profit_factor || 0).toFixed(2)],
            ['Avg Win', '$' + (m.avg_win || 0).toFixed(2)],
            ['Avg Loss', '$' + (m.avg_loss || 0).toFixed(2)],
            ['Risk:Reward', m.risk_reward ? m.risk_reward.toFixed(1) + ':1' : 'N/A'],
            ['Final Capital', '$' + (m.final_capital || m.final_balance || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })],
            [],
            ['--- TRADE LOG ---', '']
        ].map(row => row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));

        const csv = [...summaryRows, headers.join(','), ...rows].join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `backtest_trades_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ── Smooth Scrolling (target-based lerp) ──────────────────
    // Each wheel tick pushes a target further; an animation loop
    // eases the actual scroll position toward the target so
    // multiple ticks blend into one fluid, decelerating glide.
    function _setupKineticScroll() {
        const el = document.getElementById('view-backtest');
        if (!el) return;

        // Force instant scrollTop so our lerp loop works
        el.style.scrollBehavior = 'auto';

        let target = el.scrollTop;
        let running = false;
        const speed = 400;   // pixels per wheel notch (generous throw)
        const ease = 0.04;  // lerp factor (lower = longer rolling stop)

        el.addEventListener('wheel', (e) => {
            // Only capture vertical scrolling
            if (e.deltaY === 0) return;
            e.preventDefault();

            // Normalize delta
            let d = e.deltaY;
            if (e.deltaMode === 1) d *= 20;            // line mode
            else if (e.deltaMode === 2) d *= el.clientHeight;  // page mode

            // Push the target (direction only, fixed step size for consistency)
            target += Math.sign(d) * speed;

            // Clamp to scrollable range
            const max = el.scrollHeight - el.clientHeight;
            target = Math.max(0, Math.min(target, max));

            if (!running) { running = true; step(); }
        }, { passive: false });

        // Sync target when user drags the scrollbar manually
        let wheelActive = false;
        el.addEventListener('wheel', () => { wheelActive = true; }, { passive: true });
        el.addEventListener('scroll', () => {
            if (!wheelActive && !running) {
                target = el.scrollTop;
            }
            wheelActive = false;
        });

        function step() {
            const diff = target - el.scrollTop;
            if (Math.abs(diff) < 1) {
                el.scrollTop = target;
                running = false;
                return;
            }
            el.scrollTop += diff * ease;
            requestAnimationFrame(step);
        }
    }

    // ── Expose module ────────────────────────────────────────
    window.backtestModule = { init };

})();
