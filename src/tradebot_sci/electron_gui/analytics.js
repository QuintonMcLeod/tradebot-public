/**
 * Analytics Renderer — Premium Glass Dashboard
 * Handles charts, metrics, breakdowns, and data loading for the Graph tab.
 * Uses glass-card design system from analytics.css.
 */

let winLossPieChart = null;
let equityChart = null;
let equityAreaSeries = null;
let currentFilter = '24h';

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

function initAnalytics() {
    console.log('[ANALYTICS] Initializing...');
    setupTimeFilters();
    loadAnalyticsData(currentFilter);
}

function setupTimeFilters() {
    const pills = document.querySelectorAll('.time-filter-btn');
    pills.forEach(btn => {
        btn.addEventListener('click', () => {
            pills.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            loadAnalyticsData(currentFilter);
        });
    });
}

// ═══════════════════════════════════════════════════════════
// DATA LOADING
// ═══════════════════════════════════════════════════════════

async function loadAnalyticsData(filter) {
    console.log(`[ANALYTICS] Loading data for filter: ${filter}`);
    showLoadingState();

    try {
        if (!window.api || !window.api.getAnalyticsSummary) {
            console.error('[ANALYTICS] API not available');
            showErrorState('API not available');
            return;
        }

        const result = await window.api.getAnalyticsSummary(filter);
        console.log('[ANALYTICS] Result:', result?.success, 'source:', result?.data?._source);

        if (result && result.success) {
            const d = result.data;
            updateMetrics(d);
            updateCharts(d);
            updateTradeHistory(d.trades || []);
            updateSymbolBreakdown(d.symbolStats || {});
            updateStrategyBreakdown(d.strategyStats || {});
            updateSundownBadge(d);
            updateSourceBadge(d);
        } else {
            showErrorState(result?.error || 'Failed to load');
            updateMetrics({});
        }
    } catch (err) {
        console.error('[ANALYTICS] Exception:', err);
        showErrorState(err.message);
        updateMetrics({});
    }
}

// ═══════════════════════════════════════════════════════════
// LOADING / ERROR
// ═══════════════════════════════════════════════════════════

function showLoadingState() {
    const ids = [
        'metric-pnl', 'metric-pnl-pct', 'metric-winrate', 'metric-wins',
        'metric-losses', 'metric-total-trades', 'metric-rr', 'metric-pf',
        'metric-spread-costs', 'metric-avg-win', 'metric-avg-loss',
        'metric-best', 'metric-worst', 'metric-gross-profit', 'metric-gross-loss',
        'metric-capital-start', 'metric-capital-end', 'metric-capital-change'
    ];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '...';
    });
}

function showErrorState(error) {
    const tbody = document.getElementById('trade-history-body');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align:center; color:#f87171; padding:32px 16px;">
                    <span class="material-symbols-outlined" style="font-size:28px; display:block; margin-bottom:8px; opacity:0.4;">error</span>
                    Error: ${error || 'Unknown'}
                </td>
            </tr>
        `;
    }
    updateMetrics({});
}

// ═══════════════════════════════════════════════════════════
// METRICS
// ═══════════════════════════════════════════════════════════

function updateMetrics(data) {
    data = data || {};

    // Hero PnL
    const pnl = parseFloat(data.totalPnl) || 0;
    const pnlEl = document.getElementById('metric-pnl');
    if (pnlEl) {
        pnlEl.textContent = formatCurrency(pnl);
        // Update CSS class for text-shadow glow
        pnlEl.className = `hero-value ${pnl >= 0 ? 'positive' : 'negative'}`;
    }

    const pnlPct = parseFloat(data.capitalChangePct) || 0;
    const pnlPctEl = document.getElementById('metric-pnl-pct');
    if (pnlPctEl) {
        pnlPctEl.textContent = `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`;
        pnlPctEl.style.color = pnlPct >= 0 ? 'rgba(52, 211, 153, 0.55)' : 'rgba(248, 113, 113, 0.55)';
    }

    // Win Rate card
    set('metric-winrate', `${data.winRate ?? 0}%`);
    set('metric-wins', data.totalWins ?? 0);
    set('metric-losses', data.totalLosses ?? 0);

    // Trades card
    set('metric-total-trades', data.totalTrades ?? 0);
    set('metric-rr', data.riskReward && data.riskReward !== 'N/A' ? `R:R ${data.riskReward}:1` : 'R:R N/A');

    // Metrics strip
    set('metric-pf', data.profitFactor && data.profitFactor !== 'N/A' ? data.profitFactor : '0.00');
    set('metric-avg-win', formatCurrency(data.avgWin ?? 0));
    set('metric-avg-loss', formatCurrency(data.avgLoss ?? 0));
    set('metric-best', formatCurrency(data.bestTrade ?? 0));
    set('metric-worst', formatCurrency(data.worstTrade ?? 0));

    // Spread cost
    const spreadEl = document.getElementById('metric-spread-costs');
    if (spreadEl) {
        const s = parseFloat(data.spreadCosts) || 0;
        spreadEl.textContent = `Spread: ${formatCurrency(s)}`;
    }

    // Performance grid
    set('metric-gross-profit', formatCurrency(data.grossProfit ?? 0));
    set('metric-gross-loss', formatCurrency(data.grossLoss ?? 0));
    set('metric-capital-start', formatCurrency(data.capitalStart ?? 0));
    set('metric-capital-end', formatCurrency(data.capitalEnd ?? 0));

    const capChange = parseFloat(data.capitalChange) || 0;
    const capEl = document.getElementById('metric-capital-change');
    if (capEl) {
        capEl.textContent = formatCurrency(capChange, true);
        capEl.style.color = capChange >= 0 ? '#2dd4bf' : '#f87171';
    }

    // R:R in grid
    set('metric-rr-grid', data.riskReward && data.riskReward !== 'N/A' ? `${data.riskReward}:1` : 'N/A');

    // Trade count badge
    const tcEl = document.getElementById('trade-count');
    if (tcEl) tcEl.textContent = `${data.totalTrades ?? 0} trades`;
}

function set(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatCurrency(value, showSign = false) {
    const n = parseFloat(value) || 0;
    const abs = Math.abs(n).toFixed(2);
    const sign = showSign ? (n >= 0 ? '+' : '-') : (n < 0 ? '-' : '');
    return `${sign}$${abs}`;
}

// ═══════════════════════════════════════════════════════════
// CHARTS
// ═══════════════════════════════════════════════════════════

function updateCharts(data) {
    updateWinLossPie(data);
    updateEquityCurve(data);
}

function updateWinLossPie(data) {
    const canvas = document.getElementById('chart-winloss-pie');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const wins = parseInt(data.totalWins) || 0;
    const losses = parseInt(data.totalLosses) || 0;
    const breakeven = parseInt(data.breakeven) || 0;
    const total = wins + losses + breakeven;

    if (winLossPieChart) winLossPieChart.destroy();

    if (total === 0) {
        winLossPieChart = new Chart(ctx, {
            type: 'doughnut',
            data: { labels: ['No Data'], datasets: [{ data: [1], backgroundColor: ['rgba(71, 85, 105, 0.2)'], borderWidth: 0 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: '68%', plugins: { legend: { display: false } } }
        });
        return;
    }

    const labels = [], vals = [], bg = [], bdr = [];
    if (wins > 0) { labels.push('Wins'); vals.push(wins); bg.push('rgba(16, 185, 129, 0.75)'); bdr.push('#10b981'); }
    if (losses > 0) { labels.push('Losses'); vals.push(losses); bg.push('rgba(239, 68, 68, 0.75)'); bdr.push('#ef4444'); }
    if (breakeven > 0) { labels.push('B/E'); vals.push(breakeven); bg.push('rgba(71, 85, 105, 0.5)'); bdr.push('#64748b'); }

    winLossPieChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: vals, backgroundColor: bg, borderColor: bdr, borderWidth: 2, hoverOffset: 6 }] },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '68%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#64748b', font: { size: 10, weight: 'bold', family: 'Inter' }, padding: 14, usePointStyle: true, pointStyle: 'circle' }
                },
                tooltip: {
                    backgroundColor: 'rgba(2, 6, 23, 0.95)', titleColor: '#f1f5f9', bodyColor: '#94a3b8',
                    borderColor: 'rgba(20, 184, 166, 0.25)', borderWidth: 1, padding: 10, cornerRadius: 8,
                    callbacks: { label: c => ` ${c.label}: ${c.parsed} (${((c.parsed / total) * 100).toFixed(1)}%)` }
                }
            },
            animation: { animateRotate: true, animateScale: true }
        },
        plugins: [{
            id: 'centerText',
            beforeDraw(chart) {
                const { ctx, chartArea } = chart;
                const cx = chartArea.left + (chartArea.right - chartArea.left) / 2;
                const cy = chartArea.top + (chartArea.bottom - chartArea.top) / 2;
                ctx.save();
                ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                ctx.font = 'bold 28px Inter, sans-serif'; ctx.fillStyle = '#f1f5f9';
                ctx.fillText(total.toString(), cx, cy - 6);
                ctx.font = '9px Inter, sans-serif'; ctx.fillStyle = '#475569';
                ctx.fillText('TRADES', cx, cy + 14);
                ctx.restore();
            }
        }]
    });
}

function updateEquityCurve(data) {
    const container = document.getElementById('chart-equity-curve');
    if (!container) return;
    container.innerHTML = '';

    const history = data.capitalHistory || [];
    if (history.length === 0) {
        container.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#475569;font-size:13px;"><span class="material-symbols-outlined" style="margin-right:8px;opacity:0.4;">timeline</span>No capital data</div>';
        return;
    }

    equityChart = LightweightCharts.createChart(container, {
        layout: { background: { type: 'Solid', color: 'transparent' }, textColor: '#475569', fontFamily: 'Inter, sans-serif', fontSize: 10 },
        grid: { vertLines: { color: 'rgba(255, 255, 255, 0.02)' }, horzLines: { color: 'rgba(255, 255, 255, 0.02)' } },
        rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.08 } },
        timeScale: { borderVisible: false, timeVisible: true },
        crosshair: { vertLine: { color: 'rgba(20, 184, 166, 0.2)', width: 1, style: 3 }, horzLine: { color: 'rgba(20, 184, 166, 0.2)', width: 1, style: 3 } }
    });

    const tzOff = new Date().getTimezoneOffset() * 60;
    const points = history
        .filter(c => c.nav || c.balance)
        .map(c => {
            const ts = typeof c.timestamp === 'string' ? new Date(c.timestamp) : c.timestamp;
            return { time: Math.floor(ts.getTime() / 1000) - tzOff, value: c.nav || c.balance };
        })
        .sort((a, b) => a.time - b.time);

    // Dedupe
    const unique = [];
    const seen = new Set();
    for (let i = points.length - 1; i >= 0; i--) {
        if (!seen.has(points[i].time)) { seen.add(points[i].time); unique.unshift(points[i]); }
    }

    if (unique.length === 0) {
        container.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#475569;font-size:13px;">No chart data</div>';
        return;
    }

    const up = (unique[unique.length - 1]?.value || 0) >= (unique[0]?.value || 0);
    equityAreaSeries = equityChart.addAreaSeries({
        lineColor: up ? 'rgba(16, 185, 129, 0.9)' : 'rgba(239, 68, 68, 0.9)',
        topColor: up ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
        bottomColor: up ? 'rgba(16, 185, 129, 0.0)' : 'rgba(239, 68, 68, 0.0)',
        lineWidth: 2,
        priceFormat: { type: 'price', precision: 2, minMove: 0.01 }
    });
    equityAreaSeries.setData(unique);
    equityChart.timeScale().fitContent();

    const ro = new ResizeObserver(entries => {
        if (entries.length > 0 && equityChart) {
            const { width, height } = entries[0].contentRect;
            equityChart.applyOptions({ width, height });
        }
    });
    ro.observe(container);
}

// ═══════════════════════════════════════════════════════════
// BREAKDOWN TABLES (using analytics.css bar classes)
// ═══════════════════════════════════════════════════════════

function updateSymbolBreakdown(symbolStats) {
    const tbody = document.getElementById('symbol-breakdown-body');
    if (!tbody) return;

    const entries = Object.entries(symbolStats).sort((a, b) => Math.abs(b[1].pnl) - Math.abs(a[1].pnl));
    if (entries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#475569;font-style:italic;padding:24px 16px;">No symbol data yet</td></tr>';
        return;
    }

    const maxPnl = Math.max(...entries.map(([, s]) => Math.abs(s.pnl)), 0.01);
    tbody.innerHTML = entries.map(([sym, s]) => {
        const pnl = parseFloat(s.pnl) || 0;
        const cls = pnl >= 0 ? 'positive' : 'negative';
        const barW = Math.min((Math.abs(pnl) / maxPnl) * 100, 100);
        return `
            <tr>
                <td style="font-weight:700; color:#e2e8f0;">${sym}</td>
                <td style="text-align:center;">${s.trades || 0}</td>
                <td style="text-align:center;">
                    <span style="color:#34d399;">${s.wins || 0}</span>
                    <span style="color:#334155;">/</span>
                    <span style="color:#f87171;">${s.losses || 0}</span>
                </td>
                <td style="text-align:right; font-weight:700; color:${pnl >= 0 ? '#34d399' : '#f87171'};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td>
                    <div class="breakdown-bar-track">
                        <div class="breakdown-bar-fill ${cls}" style="width:${barW}%"></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function updateStrategyBreakdown(strategyStats) {
    const tbody = document.getElementById('strategy-breakdown-body');
    if (!tbody) return;

    const entries = Object.entries(strategyStats).sort((a, b) => Math.abs(b[1].pnl) - Math.abs(a[1].pnl));
    if (entries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#475569;font-style:italic;padding:24px 16px;">No strategy data yet</td></tr>';
        return;
    }

    const maxPnl = Math.max(...entries.map(([, s]) => Math.abs(s.pnl)), 0.01);
    tbody.innerHTML = entries.map(([strat, s]) => {
        const pnl = parseFloat(s.pnl) || 0;
        const cls = pnl >= 0 ? 'purple' : 'negative';
        const barW = Math.min((Math.abs(pnl) / maxPnl) * 100, 100);
        const name = strat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        return `
            <tr>
                <td style="font-weight:700; color:#e2e8f0;">${name}</td>
                <td style="text-align:center;">
                    <span style="color:#34d399;">${s.wins || 0}</span>
                    <span style="color:#334155;">/</span>
                    <span style="color:#f87171;">${s.losses || 0}</span>
                </td>
                <td style="text-align:right; font-weight:700; color:${pnl >= 0 ? '#a78bfa' : '#f87171'};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td>
                    <div class="breakdown-bar-track">
                        <div class="breakdown-bar-fill ${cls}" style="width:${barW}%"></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// ═══════════════════════════════════════════════════════════
// BADGES
// ═══════════════════════════════════════════════════════════

function updateSundownBadge(data) {
    const badge = document.getElementById('analytics-sundown-badge');
    const label = document.getElementById('analytics-sundown-label');
    if (!badge || !label) return;

    if (data.dayStart && (data._source || '').includes('ledger')) {
        try {
            const ds = new Date(data.dayStart);
            const time = ds.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
            label.textContent = `Day Start: ${time}`;
            badge.classList.remove('hidden');
        } catch (_) { badge.classList.add('hidden'); }
    } else {
        badge.classList.add('hidden');
    }
}

function updateSourceBadge(data) {
    const badge = document.getElementById('analytics-source-badge');
    const label = document.getElementById('analytics-source-label');
    if (!badge || !label) return;
    const src = data._source || '';
    if (src.includes('ledger') && src.includes('log')) {
        label.textContent = '📊 Ledger + Logs';
    } else if (src.includes('ledger')) {
        label.textContent = '📊 Ledger';
    } else {
        label.textContent = '📄 Log Parse';
    }
    badge.classList.remove('hidden');
}

/** Calculate human-readable duration from a timestamp to now */
function formatDuration(entryTime) {
    try {
        const entry = typeof entryTime === 'string' ? new Date(entryTime) : entryTime;
        const now = new Date();
        const diffMs = now - entry;
        if (diffMs < 0) return '--';

        const mins = Math.floor(diffMs / 60000);
        const hrs = Math.floor(mins / 60);
        const days = Math.floor(hrs / 24);

        if (days > 0) return `${days}d ${hrs % 24}h`;
        if (hrs > 0) return `${hrs}h ${mins % 60}m`;
        return `${mins}m`;
    } catch (_) { return '--'; }
}

// ═══════════════════════════════════════════════════════════
// TRADE HISTORY (using side-badge from analytics.css)
// ═══════════════════════════════════════════════════════════

function updateTradeHistory(trades) {
    const tbody = document.getElementById('trade-history-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `
            <tr id="no-trades-row">
                <td colspan="7" style="text-align:center; color:#475569; padding:40px 16px;">
                    <span class="material-symbols-outlined" style="font-size:28px; display:block; margin-bottom:8px; opacity:0.25;">search_off</span>
                    <span style="font-style:italic;">No trades found in this period</span>
                </td>
            </tr>
        `;
        return;
    }

    // Separate active positions and closed trades
    const active = trades.filter(t => t._active);
    const closed = trades.filter(t => !t._active);

    // Render active positions first with a distinct style
    if (active.length > 0) {
        const headerRow = document.createElement('tr');
        headerRow.innerHTML = `
            <td colspan="7" style="padding:8px 16px; font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:#34d399; background:rgba(16,185,129,0.06); border-bottom:1px solid rgba(16,185,129,0.1);">
                <span class="material-symbols-outlined" style="font-size:13px; vertical-align:-2px; margin-right:4px;">radio_button_checked</span>
                Active Positions (${active.length})
            </td>
        `;
        tbody.appendChild(headerRow);

        active.forEach(trade => {
            const row = document.createElement('tr');
            row.style.background = 'rgba(16,185,129,0.03)';

            let time = '--';
            const ts = trade.timestamp || trade.time;
            if (ts) {
                try {
                    const d = typeof ts === 'string' ? new Date(ts) : ts;
                    time = d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                } catch (_) { /* ignore */ }
            }

            const pnl = parseFloat(trade.pnl) || 0;
            const pnlColor = pnl >= 0 ? '#34d399' : '#f87171';
            const side = (trade.side || 'long').toUpperCase();
            const sideClass = side === 'SHORT' ? 'short' : 'long';
            const duration = formatDuration(trade.timestamp || trade.time);
            const strategy = trade.strategy ? trade.strategy.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : '--';

            row.innerHTML = `
                <td style="color:#64748b; font-size:11px;">${time}</td>
                <td style="font-weight:700; color:#e2e8f0;">${trade.symbol || '--'} <span style="font-size:8px;padding:1px 5px;border-radius:4px;background:rgba(16,185,129,0.15);color:#34d399;font-weight:800;letter-spacing:0.05em;">LIVE</span></td>
                <td style="text-align:center;"><span class="side-badge ${sideClass}">${side}</span></td>
                <td style="text-align:right; font-weight:700; color:${pnlColor};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td style="color:#34d399; font-size:11px; font-weight:600;">⏱ ${duration}</td>
                <td style="color:#94a3b8; font-size:11px;">${strategy}</td>
                <td style="color:#475569; font-size:11px;">${trade.reason || '--'}</td>
            `;
            tbody.appendChild(row);
        });
    }

    // Render closed trades
    if (closed.length > 0) {
        if (active.length > 0) {
            const headerRow = document.createElement('tr');
            headerRow.innerHTML = `
                <td colspan="7" style="padding:8px 16px; font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:#64748b; background:rgba(71,85,105,0.06); border-bottom:1px solid rgba(71,85,105,0.1);">
                    <span class="material-symbols-outlined" style="font-size:13px; vertical-align:-2px; margin-right:4px;">receipt_long</span>
                    Closed Trades (${closed.length})
                </td>
            `;
            tbody.appendChild(headerRow);
        }

        closed.forEach(trade => {
            const row = document.createElement('tr');

            let time = '--';
            const ts = trade.timestamp || trade.time;
            if (ts) {
                try {
                    const d = typeof ts === 'string' ? new Date(ts) : ts;
                    time = d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                } catch (_) { /* ignore */ }
            }

            const pnl = parseFloat(trade.pnl) || 0;
            const pnlColor = pnl >= 0 ? '#34d399' : '#f87171';
            const side = (trade.side || 'long').toUpperCase();
            const sideClass = side === 'SHORT' ? 'short' : 'long';
            const strategy = trade.strategy ? trade.strategy.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : '--';

            row.innerHTML = `
                <td style="color:#64748b; font-size:11px;">${time}</td>
                <td style="font-weight:700; color:#e2e8f0;">${trade.symbol || '--'}</td>
                <td style="text-align:center;"><span class="side-badge ${sideClass}">${side}</span></td>
                <td style="text-align:right; font-weight:700; color:${pnlColor};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td style="color:#475569; font-size:11px;">--</td>
                <td style="color:#94a3b8; font-size:11px;">${strategy}</td>
                <td style="color:#475569; font-size:11px; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${trade.reason || '--'}</td>
            `;
            tbody.appendChild(row);
        });
    }
}

// ═══════════════════════════════════════════════════════════
// REFRESH & EXPORT
// ═══════════════════════════════════════════════════════════

function refreshAnalytics() {
    loadAnalyticsData(currentFilter);
}

window.analyticsModule = {
    init: initAnalytics,
    refresh: refreshAnalytics,
    loadData: loadAnalyticsData
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(initAnalytics, 100));
} else {
    setTimeout(initAnalytics, 100);
}
