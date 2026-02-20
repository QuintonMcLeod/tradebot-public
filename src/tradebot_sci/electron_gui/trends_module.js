/**
 * Trends Module — Live trend indicator dashboard
 * Parses [TREND-DATA] JSON from the WebSocket log channel and renders
 * 6 indicator cards with live values, status badges, and rich tooltips.
 *
 * Exposes window.trendsModule = { init, refresh, updateIndicators }
 */
(() => {
    'use strict';

    // ── Indicator metadata (tooltips) ──────────────────────────────────
    const INDICATORS = {
        adx: {
            name: 'ADX',
            fullName: 'Average Directional Index',
            icon: 'trending_up',
            color: '#f59e0b',
            description: 'Measures the STRENGTH of a trend on a 0-100 scale, regardless of direction. Uses Wilder\'s 14-period smoothing of directional movement.',
            goodFor: 'Filtering out choppy, ranging markets before committing to a trade. When ADX is above 20-25, there\'s a real trend worth trading.',
            notGoodFor: 'Telling you WHICH direction to trade — ADX only measures strength, not direction. It also lags behind fast reversals since it uses smoothed averages.',
            ranges: [
                { max: 20, label: 'No Trend', color: '#ef4444' },
                { max: 40, label: 'Developing', color: '#f59e0b' },
                { max: 60, label: 'Strong', color: '#22c55e' },
                { max: 100, label: 'Extreme', color: '#06b6d4' },
            ],
            format: v => v.toFixed(1),
            maxVal: 100,
        },
        rsi: {
            name: 'RSI',
            fullName: 'Relative Strength Index',
            icon: 'speed',
            color: '#8b5cf6',
            description: 'Measures momentum by comparing recent gains vs losses over 14 periods. Ranges from 0 (max oversold) to 100 (max overbought).',
            goodFor: 'Spotting overbought/oversold extremes that may precede reversals or pullbacks. Great for mean-reversion setups and identifying divergences.',
            notGoodFor: 'Strong trending markets — RSI can stay "overbought" (>70) for extended periods in a bull run, giving premature exit signals. Not a standalone entry trigger.',
            ranges: [
                { max: 30, label: 'Oversold', color: '#22c55e' },
                { max: 70, label: 'Neutral', color: '#94a3b8' },
                { max: 100, label: 'Overbought', color: '#ef4444' },
            ],
            format: v => v.toFixed(1),
            maxVal: 100,
        },
        macd: {
            name: 'MACD',
            fullName: 'Moving Average Convergence Divergence',
            icon: 'stacked_line_chart',
            color: '#06b6d4',
            description: 'Tracks momentum shifts using the difference between a 12-period and 26-period EMA. The signal line (9-EMA of MACD) confirms crossovers. The histogram shows the gap between them.',
            goodFor: 'Catching trend changes early — bullish crossover (MACD crosses above signal) or bearish crossover. The histogram helps visualize momentum acceleration.',
            notGoodFor: 'Choppy, sideways markets where the MACD line oscillates around zero, producing frequent false crossover signals (whipsaws). Lags behind price in fast moves.',
            ranges: [],
            format: v => {
                if (typeof v === 'object') return `H: ${v.histogram > 0 ? '+' : ''}${v.histogram.toFixed(5)}`;
                return v.toFixed(5);
            },
            maxVal: null,
        },
        bollinger: {
            name: 'Bollinger',
            fullName: 'Bollinger Bands',
            icon: 'expand',
            color: '#ec4899',
            description: 'Plots bands at ±2 standard deviations around a 20-period SMA. Bandwidth measures volatility — tight bands (squeeze) often precede explosive moves.',
            goodFor: 'Detecting volatility squeezes before breakouts, and identifying mean-reversion opportunities when price touches the outer bands.',
            notGoodFor: 'Strong trends where price "rides the band" — touching the upper band in an uptrend is NOT a sell signal. Squeeze detection can have false starts.',
            ranges: [],
            format: v => {
                if (typeof v === 'object') return `BW: ${v.bandwidth.toFixed(2)}${v.squeeze ? ' 🔹 SQUEEZE' : ''}`;
                return v.toFixed(3);
            },
            maxVal: null,
        },
        supertrend: {
            name: 'Supertrend',
            fullName: 'Supertrend (ATR-Based)',
            icon: 'moving',
            color: '#10b981',
            description: 'An ATR-based trailing indicator that flips between bullish and bearish. Uses a 10-period ATR with a 3x multiplier to create dynamic support/resistance levels.',
            goodFor: 'Clean, binary trend direction signals — either long or short. Acts as a dynamic trailing stop-loss and works well in clearly trending markets.',
            notGoodFor: 'Ranging/choppy markets where it flip-flops rapidly between long and short, generating whipsaw losses. Not suitable for tight ranges or consolidation.',
            ranges: [],
            format: v => {
                if (typeof v === 'object') return v.direction.toUpperCase();
                return String(v);
            },
            maxVal: null,
        },
        ema_ribbon: {
            name: 'EMA Ribbon',
            fullName: 'EMA Ribbon (8/21/55)',
            icon: 'ssid_chart',
            color: '#3b82f6',
            description: 'Three EMAs (8, 21, 55 period) layered to show trend alignment. When all three are stacked in order (8>21>55 for bullish), the trend has strong conviction across timeframes.',
            goodFor: 'Confirming multi-timeframe trend alignment and identifying high-conviction entries. When the ribbon fans out (aligned), trend-following strategies have the best edge.',
            notGoodFor: 'Quick reversals or scalping — EMAs are inherently lagging. In volatile markets, the ribbon tangles frequently, giving unclear signals during transitions.',
            ranges: [],
            format: v => {
                if (typeof v === 'object') return v.aligned ? `✓ ${v.direction.toUpperCase()}` : '✗ TANGLED';
                return String(v);
            },
            maxVal: null,
        },
    };

    // ── State ──────────────────────────────────────────────────────────
    let trendData = {};     // { symbol: { adx, rsi, macd, ... } }
    let selectedSymbol = null;
    let initialized = false;
    let tooltipTimer = null;

    // ── Public API ─────────────────────────────────────────────────────
    function updateIndicators(data) {
        if (!data || !data.symbol) return;
        trendData[data.symbol] = data;
        if (!selectedSymbol) selectedSymbol = data.symbol;
        if (initialized) render();
    }

    function init() {
        if (initialized) { render(); return; }
        initialized = true;
        buildLayout();
        render();
    }

    function refresh() {
        render();
    }

    // ── Layout Builder ─────────────────────────────────────────────────
    function buildLayout() {
        const container = document.getElementById('view-trends');
        if (!container) return;
        container.innerHTML = '';

        // Symbol bar
        const symBar = document.createElement('div');
        symBar.id = 'trends-symbol-bar';
        symBar.className = 'trends-symbol-bar';
        container.appendChild(symBar);

        // Cards grid
        const grid = document.createElement('div');
        grid.id = 'trends-grid';
        grid.className = 'trends-grid';
        container.appendChild(grid);

        // Build 6 cards
        for (const [key, meta] of Object.entries(INDICATORS)) {
            const card = document.createElement('div');
            card.className = 'trends-card';
            card.id = `tc-${key}`;
            card.innerHTML = `
                <div class="tc-header">
                    <div class="tc-title-wrap">
                        <span class="material-symbols-outlined tc-icon" style="color:${meta.color}">${meta.icon}</span>
                        <span class="tc-name">${meta.name}</span>
                        <span class="tc-badge" id="tc-badge-${key}">—</span>
                    </div>
                    <span class="material-symbols-outlined tc-info-btn" data-indicator="${key}">info</span>
                </div>
                <div class="tc-value" id="tc-val-${key}">—</div>
                ${meta.maxVal ? `<div class="tc-gauge-wrap"><div class="tc-gauge-bg"><div class="tc-gauge-fill" id="tc-gauge-${key}" style="width:0%;background:${meta.color}"></div></div></div>` : '<div class="tc-detail" id="tc-detail-${key}"></div>'}
                <div class="tc-tooltip hidden" id="tc-tip-${key}">
                    <div class="tc-tip-title">${meta.fullName}</div>
                    <p class="tc-tip-desc">${meta.description}</p>
                    <div class="tc-tip-section">
                        <span class="tc-tip-label good">✓ Good For</span>
                        <p>${meta.goodFor}</p>
                    </div>
                    <div class="tc-tip-section">
                        <span class="tc-tip-label bad">✗ Not Good For</span>
                        <p>${meta.notGoodFor}</p>
                    </div>
                </div>
            `;
            grid.appendChild(card);
        }

        // Tooltip events
        grid.querySelectorAll('.tc-info-btn').forEach(btn => {
            btn.addEventListener('mouseenter', (e) => {
                const key = e.target.dataset.indicator;
                const tip = document.getElementById(`tc-tip-${key}`);
                if (tip) {
                    clearTimeout(tooltipTimer);
                    // Hide all other tooltips
                    grid.querySelectorAll('.tc-tooltip').forEach(t => t.classList.add('hidden'));
                    tip.classList.remove('hidden');
                }
            });
            btn.addEventListener('mouseleave', (e) => {
                const key = e.target.dataset.indicator;
                const tip = document.getElementById(`tc-tip-${key}`);
                tooltipTimer = setTimeout(() => {
                    if (tip) tip.classList.add('hidden');
                }, 300);
            });
        });

        // Keep tooltip open when hovering over it
        grid.querySelectorAll('.tc-tooltip').forEach(tip => {
            tip.addEventListener('mouseenter', () => clearTimeout(tooltipTimer));
            tip.addEventListener('mouseleave', () => {
                tooltipTimer = setTimeout(() => tip.classList.add('hidden'), 200);
            });
        });
    }

    // ── Render ──────────────────────────────────────────────────────────
    function render() {
        renderSymbolBar();
        renderCards();
    }

    function renderSymbolBar() {
        const bar = document.getElementById('trends-symbol-bar');
        if (!bar) return;

        const symbols = Object.keys(trendData).sort();
        if (symbols.length === 0) {
            bar.innerHTML = '<span class="trends-empty">Waiting for trend data…</span>';
            return;
        }

        bar.innerHTML = symbols.map(sym => {
            const isActive = sym === selectedSymbol;
            return `<button class="trends-sym-btn ${isActive ? 'active' : ''}" data-sym="${sym}">${sym}</button>`;
        }).join('');

        bar.querySelectorAll('.trends-sym-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                selectedSymbol = btn.dataset.sym;
                render();
            });
        });
    }

    function renderCards() {
        const data = trendData[selectedSymbol];
        if (!data) return;

        for (const [key, meta] of Object.entries(INDICATORS)) {
            const raw = data[key];
            if (raw === undefined || raw === null) continue;

            // Value display
            const valEl = document.getElementById(`tc-val-${key}`);
            if (valEl) valEl.textContent = meta.format(raw);

            // Badge
            const badgeEl = document.getElementById(`tc-badge-${key}`);
            if (badgeEl) {
                const badge = getBadge(key, raw);
                badgeEl.textContent = badge.label;
                badgeEl.style.background = badge.color + '22';
                badgeEl.style.color = badge.color;
                badgeEl.style.borderColor = badge.color + '44';
            }

            // Gauge (for ADX, RSI)
            const gaugeEl = document.getElementById(`tc-gauge-${key}`);
            if (gaugeEl && meta.maxVal) {
                const pct = Math.min(100, Math.max(0, (typeof raw === 'number' ? raw : 0) / meta.maxVal * 100));
                gaugeEl.style.width = `${pct}%`;
                // Dynamic color from ranges
                const badge = getBadge(key, raw);
                gaugeEl.style.background = badge.color;
            }

            // Detail line (for complex indicators)
            const detailEl = document.getElementById(`tc-detail-${key}`);
            if (detailEl && typeof raw === 'object') {
                detailEl.innerHTML = getDetailHTML(key, raw);
            }
        }
    }

    function getBadge(key, raw) {
        const meta = INDICATORS[key];
        const val = typeof raw === 'number' ? raw : 0;

        // Range-based badges
        if (meta.ranges && meta.ranges.length > 0 && typeof raw === 'number') {
            for (const r of meta.ranges) {
                if (val <= r.max) return { label: r.label, color: r.color };
            }
            return { label: 'Unknown', color: '#94a3b8' };
        }

        // Direction-based badges
        if (typeof raw === 'object') {
            if (raw.direction === 'long') return { label: 'BULLISH', color: '#22c55e' };
            if (raw.direction === 'short') return { label: 'BEARISH', color: '#ef4444' };
            if (raw.aligned === true) return { label: raw.direction === 'long' ? 'BULLISH' : 'BEARISH', color: raw.direction === 'long' ? '#22c55e' : '#ef4444' };
            if (raw.aligned === false) return { label: 'TANGLED', color: '#f59e0b' };
            if (raw.squeeze === true) return { label: 'SQUEEZE', color: '#ec4899' };
            if (raw.histogram !== undefined) return { label: raw.histogram > 0 ? 'BULLISH' : 'BEARISH', color: raw.histogram > 0 ? '#22c55e' : '#ef4444' };
        }

        return { label: '—', color: '#94a3b8' };
    }

    function getDetailHTML(key, data) {
        switch (key) {
            case 'macd':
                const hColor = data.histogram >= 0 ? '#22c55e' : '#ef4444';
                return `
                    <span class="tc-detail-item">MACD: <b>${data.macd >= 0 ? '+' : ''}${data.macd.toFixed(5)}</b></span>
                    <span class="tc-detail-item">Signal: <b>${data.signal.toFixed(5)}</b></span>
                    <span class="tc-detail-item" style="color:${hColor}">Hist: <b>${data.histogram >= 0 ? '+' : ''}${data.histogram.toFixed(5)}</b></span>
                `;
            case 'bollinger':
                return `
                    <span class="tc-detail-item">Upper: <b>${data.upper.toFixed(4)}</b></span>
                    <span class="tc-detail-item">Mid: <b>${data.middle.toFixed(4)}</b></span>
                    <span class="tc-detail-item">Lower: <b>${data.lower.toFixed(4)}</b></span>
                    <span class="tc-detail-item">BW: <b>${data.bandwidth.toFixed(2)}</b>${data.squeeze ? ' <span style="color:#ec4899;font-weight:700">SQUEEZE</span>' : ''}</span>
                `;
            case 'supertrend':
                const stColor = data.direction === 'long' ? '#22c55e' : '#ef4444';
                return `
                    <span class="tc-detail-item" style="color:${stColor}">Direction: <b>${data.direction.toUpperCase()}</b></span>
                    <span class="tc-detail-item">Level: <b>${data.value.toFixed(4)}</b></span>
                `;
            case 'ema_ribbon':
                return `
                    <span class="tc-detail-item">EMA 8: <b>${data.ema8.toFixed(4)}</b></span>
                    <span class="tc-detail-item">EMA 21: <b>${data.ema21.toFixed(4)}</b></span>
                    <span class="tc-detail-item">EMA 55: <b>${data.ema55.toFixed(4)}</b></span>
                `;
            default:
                return '';
        }
    }

    // ── Export ──────────────────────────────────────────────────────────
    window.trendsModule = { init, refresh, updateIndicators };
})();
