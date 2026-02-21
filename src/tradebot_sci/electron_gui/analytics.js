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

        const result = await window.api.getAnalyticsSummary(filter, !!window.isSabbath);
        console.log('[ANALYTICS] Result:', result?.success, 'source:', result?.data?._source);

        if (result && result.success) {
            const d = result.data;
            updateMetrics(d);
            updateCharts(d);
            // Store per-broker data at module level
            _capitalHistoryAll = d.capitalHistory || [];
            _capitalHistoryByBroker = d.capitalHistoryByBroker || {};
            _capitalByBroker = d.capitalByBroker || {};
            _activeBrokerTab = 'all';
            buildBrokerTabs();
            // For the "All" tab, show only combined ('all') or untagged snapshots
            // so per-broker entries don't get picked by the minute-based dedup
            updateCapitalTimeline(getFilteredCapitalHistory('all'), currentFilter);
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
                <td colspan="10" style="text-align:center; color:#f87171; padding:32px 16px;">
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
    // Use live WebSocket capital if available (avoids stale ledger value)
    const liveCapital = window.__liveCapital;
    const effectiveCapEnd = (liveCapital && liveCapital > 0) ? liveCapital : (data.capitalEnd ?? 0);
    set('metric-capital-end', formatCurrency(effectiveCapEnd));

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
// CAPITAL TIMELINE
// ═══════════════════════════════════════════════════════════

let capitalTimelineChart = null;
let _capitalHistoryAll = [];         // "All" combined data
let _capitalHistoryByBroker = {};    // Per-broker data
let _capitalByBroker = {};           // Latest per-broker NAV
let _activeBrokerTab = 'all';

function updateCapitalTimeline(capitalHistory, filter, brokerTag) {
    const container = document.getElementById('capital-timeline-container');
    const label = document.getElementById('capital-timeline-label');
    if (!container) return;

    // Destroy previous chart
    if (capitalTimelineChart) {
        try { capitalTimelineChart.remove(); } catch (e) { }
        capitalTimelineChart = null;
    }

    const points = capitalHistory
        .filter(c => (c.nav || c.balance) && c.timestamp)
        .map(c => ({
            time: new Date(c.timestamp),
            nav: c.nav || c.balance
        }))
        .sort((a, b) => a.time - b.time);

    // Dedupe by rounding to nearest minute
    const deduped = [];
    const seenMin = new Set();
    for (const p of points) {
        const key = Math.floor(p.time.getTime() / 60000);
        if (!seenMin.has(key)) { seenMin.add(key); deduped.push(p); }
    }

    // Granularity label
    const granularity = {
        '24h': 'hourly', '1h': 'minutely', '4h': 'hourly',
        'week': 'daily', 'month': 'weekly', 'year': 'monthly', 'all': 'monthly'
    }[filter] || 'daily';

    if (deduped.length < 2) {
        container.innerHTML = `
            <div style="color:#475569; font-size:13px; text-align:center; padding:24px;">
                <span class="material-symbols-outlined" style="opacity:0.3; margin-right:6px; vertical-align:middle;">timeline</span>
                ${deduped.length === 0 ? 'No capital data yet — collecting snapshots every 5 min' : 'Need at least 2 data points — collecting...'}
            </div>`;
        if (label) label.textContent = `${deduped.length} point${deduped.length !== 1 ? 's' : ''}`;
        return;
    }

    if (label) label.textContent = `${deduped.length} snapshots · ${granularity}`;

    // Prepare chart data
    const tzOff = new Date().getTimezoneOffset() * 60;
    const chartData = deduped.map(p => ({
        time: Math.floor(p.time.getTime() / 1000) - tzOff,
        value: p.nav
    }));

    // Dedupe by time value (LightweightCharts requires unique timestamps)
    const uniqueData = [];
    const seenTime = new Set();
    for (let i = chartData.length - 1; i >= 0; i--) {
        if (!seenTime.has(chartData[i].time)) {
            seenTime.add(chartData[i].time);
            uniqueData.unshift(chartData[i]);
        }
    }

    const startNav = uniqueData[0].value;
    const endNav = uniqueData[uniqueData.length - 1].value;
    const isUp = endNav >= startNav;

    // Create chart
    container.innerHTML = '';
    container.style.position = 'relative';
    capitalTimelineChart = LightweightCharts.createChart(container, {
        layout: {
            background: { type: 'Solid', color: 'transparent' },
            textColor: '#475569',
            fontFamily: 'Inter, sans-serif',
            fontSize: 10
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.02)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.02)' }
        },
        rightPriceScale: {
            borderVisible: false,
            scaleMargins: { top: 0.08, bottom: 0.08 }
        },
        timeScale: {
            borderVisible: false,
            timeVisible: true,
            secondsVisible: false,
            rightOffset: 2,
            barSpacing: Math.max(6, Math.min(20, 600 / uniqueData.length))
        },
        crosshair: {
            vertLine: { color: 'rgba(34, 211, 238, 0.25)', width: 1, style: 3 },
            horzLine: { color: 'rgba(34, 211, 238, 0.25)', width: 1, style: 3 }
        },
        height: 140
    });

    const series = capitalTimelineChart.addAreaSeries({
        lineColor: isUp ? 'rgba(16, 185, 129, 0.9)' : 'rgba(239, 68, 68, 0.9)',
        topColor: isUp ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
        bottomColor: isUp ? 'rgba(16, 185, 129, 0.0)' : 'rgba(239, 68, 68, 0.0)',
        lineWidth: 2,
        crosshairMarkerRadius: 5,
        crosshairMarkerBorderColor: '#0f172a',
        crosshairMarkerBackgroundColor: isUp ? '#34d399' : '#f87171',
        priceFormat: { type: 'price', precision: 2, minMove: 0.01 }
    });
    series.setData(uniqueData);
    capitalTimelineChart.timeScale().fitContent();

    // Tooltip div
    const tooltip = document.createElement('div');
    tooltip.style.cssText = 'position:absolute; display:none; left:0; top:4px; background:rgba(15,23,42,0.95); border:1px solid rgba(34,211,238,0.3); border-radius:8px; padding:8px 12px; font-size:11px; color:#e2e8f0; pointer-events:none; z-index:100; backdrop-filter:blur(8px); box-shadow:0 4px 20px rgba(0,0,0,0.4); white-space:nowrap;';
    container.appendChild(tooltip);

    capitalTimelineChart.subscribeCrosshairMove(param => {
        if (!param || !param.time || !param.seriesData || param.seriesData.size === 0) {
            tooltip.style.display = 'none';
            return;
        }
        const data = param.seriesData.get(series);
        if (!data) { tooltip.style.display = 'none'; return; }

        const nav = data.value;
        const change = nav - startNav;
        const sign = change >= 0 ? '+' : '';
        const color = change >= 0 ? '#34d399' : '#f87171';

        // Format time from epoch
        const d = new Date((param.time + tzOff) * 1000);
        const timeStr = (granularity === 'hourly' || granularity === 'minutely')
            ? d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
            : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

        tooltip.innerHTML = `
            <div style="font-weight:600; margin-bottom:4px; color:#22d3ee;">${timeStr}</div>
            <div>NAV: <span style="font-weight:700;">$${nav.toFixed(2)}</span></div>
            <div>Change: <span style="color:${color}; font-weight:600;">${sign}$${change.toFixed(2)}</span></div>
        `;
        tooltip.style.display = 'block';

        const x = param.point?.x || 0;
        const cw = container.clientWidth;
        tooltip.style.left = (x > cw / 2 ? x - 160 : x + 20) + 'px';
    });

    // Handle resize
    const ro = new ResizeObserver(entries => {
        if (entries.length > 0 && capitalTimelineChart) {
            const { width, height } = entries[0].contentRect;
            capitalTimelineChart.applyOptions({ width, height: Math.max(height, 140) });
        }
    });
    ro.observe(container);
}

// ── Broker Tab Builder ──────────────────────────────────────
const BROKER_ENV_MAP = {
    oanda: 'OANDA_API_KEY',
    ccxt: 'CCXT_API_KEY',
    gemini: 'GEMINI_API_KEY',
    kraken: 'KRAKEN_API_KEY',
    paxos: 'PAXOS_API_KEY',
    ibkr: 'IBKR_HOST'
};
const BROKER_LABELS = {
    oanda: 'OANDA', ccxt: 'CCXT', gemini: 'Gemini',
    kraken: 'Kraken', paxos: 'Paxos', ibkr: 'IBKR'
};

async function buildBrokerTabs() {
    const tabBar = document.getElementById('capital-timeline-tabs');
    if (!tabBar) return;

    // Reset to just the "All" tab
    tabBar.innerHTML = '';
    const allBtn = document.createElement('button');
    allBtn.className = 'timeline-tab active';
    allBtn.dataset.broker = 'all';
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => selectBrokerTab('all'));
    tabBar.appendChild(allBtn);

    // Discover configured brokers from env
    let env = {};
    try {
        if (window.api && window.api.invoke) {
            env = await window.api.invoke('read-env') || {};
        }
    } catch (e) {
        console.warn('[ANALYTICS] Could not read env for broker tabs:', e);
    }

    // Also check which brokers have data in the per-broker snapshots
    const brokerSet = new Set(Object.keys(_capitalHistoryByBroker));

    for (const [brokerId, envKey] of Object.entries(BROKER_ENV_MAP)) {
        const hasKey = env[envKey] && env[envKey].trim().length > 0;
        const hasData = brokerSet.has(brokerId);
        if (hasKey || hasData) {
            const btn = document.createElement('button');
            btn.className = 'timeline-tab' + (brokerId === _activeBrokerTab ? ' active' : '');
            btn.dataset.broker = brokerId;
            btn.textContent = BROKER_LABELS[brokerId] || brokerId.toUpperCase();
            btn.addEventListener('click', () => selectBrokerTab(brokerId));
            tabBar.appendChild(btn);
        }
    }
}

/**
 * Get capital history filtered for a specific broker tab.
 * For 'all': only include snapshots tagged 'all' or untagged (historical day-start entries),
 * so per-broker snapshots (oanda/ccxt) don't shadow the combined value during dedup.
 */
function getFilteredCapitalHistory(brokerId) {
    if (brokerId === 'all') {
        return _capitalHistoryAll.filter(c => !c.broker || c.broker === 'all');
    }
    return _capitalHistoryByBroker[brokerId] || [];
}

function selectBrokerTab(brokerId) {
    _activeBrokerTab = brokerId;
    // Update tab styling
    const tabBar = document.getElementById('capital-timeline-tabs');
    if (tabBar) {
        tabBar.querySelectorAll('.timeline-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.broker === brokerId);
        });
    }
    // Re-render chart with filtered data
    updateCapitalTimeline(getFilteredCapitalHistory(brokerId), currentFilter, brokerId);
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

/** Format duration for a closed trade using available data */
function formatClosedDuration(trade) {
    // 1. Pre-computed duration string from ledger (e.g. "3h 15m 42s")
    if (trade.duration) return trade.duration;
    // 2. Duration in seconds from TradeResult
    if (trade.duration_seconds != null && trade.duration_seconds > 0) {
        return _formatSeconds(trade.duration_seconds);
    }
    // 3. Compute from opened_at → closed_at timestamps
    if (trade.opened_at && trade.closed_at) {
        try {
            const open = new Date(trade.opened_at);
            const close = new Date(trade.closed_at);
            const diffSec = (close - open) / 1000;
            if (diffSec > 0) return _formatSeconds(diffSec);
        } catch (_) { /* fall through */ }
    }
    return null;
}

/** Convert seconds to human-readable duration */
function _formatSeconds(totalSec) {
    const days = Math.floor(totalSec / 86400);
    const hrs = Math.floor((totalSec % 86400) / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    if (days > 0) return `${days}d ${hrs}h`;
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
}

// TRADE HISTORY (using side-badge from analytics.css)
// ═══════════════════════════════════════════════════════════

// ── Sort state ──────────────────────────────────────────────
let _tradeHistorySortKey = null;    // e.g. 'pnl', 'time', 'symbol'
let _tradeHistorySortDir = null;    // 'asc' | 'desc' | null
let _lastTrades = [];               // Cached for re-sort

/** Extract a comparable value from a trade by sort key */
function _sortValue(trade, key) {
    switch (key) {
        case 'time': {
            const ts = trade.timestamp || trade.time;
            return ts ? new Date(ts).getTime() : 0;
        }
        case 'symbol': return (trade.symbol || '').toLowerCase();
        case 'side': return (trade.side || 'long').toLowerCase();
        case 'result': {
            const pnl = parseFloat(trade.pnl) || 0;
            return pnl > 0 ? 2 : (pnl < 0 ? 0 : 1); // WIN > B/E > LOSS
        }
        case 'pnl': return parseFloat(trade.pnl) || 0;
        case 'pnlPct': return parseFloat(trade.pct || trade.pnlPct) || 0;
        case 'spread': return parseFloat(trade.spread) || 0;
        case 'duration': {
            // Compute duration in seconds for numeric sort
            if (trade.duration_seconds) return trade.duration_seconds;
            const ts = trade.timestamp || trade.time;
            if (ts) {
                const d = typeof ts === 'string' ? new Date(ts) : ts;
                return (Date.now() - d.getTime()) / 1000;
            }
            return 0;
        }
        case 'strategy': return (trade.strategy || '').toLowerCase();
        case 'reason': return (trade.reason || '').toLowerCase();
        default: return 0;
    }
}

/** Sort a trades array by the current sort state */
function _sortTrades(trades) {
    if (!_tradeHistorySortKey || !_tradeHistorySortDir) return trades;
    const key = _tradeHistorySortKey;
    const mult = _tradeHistorySortDir === 'asc' ? 1 : -1;
    return [...trades].sort((a, b) => {
        const va = _sortValue(a, key);
        const vb = _sortValue(b, key);
        if (typeof va === 'string') return mult * va.localeCompare(vb);
        return mult * (va - vb);
    });
}

/** Update sort-arrow CSS classes on all headers */
function _updateSortHeaders() {
    document.querySelectorAll('.sortable-th').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sortKey === _tradeHistorySortKey) {
            if (_tradeHistorySortDir === 'asc') th.classList.add('sort-asc');
            if (_tradeHistorySortDir === 'desc') th.classList.add('sort-desc');
        }
    });
}

/** Handle header click — cycle: asc → desc → none */
function _handleSortClick(e) {
    const th = e.currentTarget;
    const key = th.dataset.sortKey;
    if (!key) return;

    if (_tradeHistorySortKey === key) {
        // Same column: cycle direction
        if (_tradeHistorySortDir === 'asc') {
            _tradeHistorySortDir = 'desc';
        } else if (_tradeHistorySortDir === 'desc') {
            _tradeHistorySortKey = null;
            _tradeHistorySortDir = null;
        }
    } else {
        // New column: default to desc (most useful for PnL, time)
        _tradeHistorySortKey = key;
        _tradeHistorySortDir = 'desc';
    }

    _updateSortHeaders();
    // Re-render with cached trades
    if (_lastTrades.length > 0) {
        updateTradeHistory(_lastTrades);
    }
}

function updateTradeHistory(trades) {
    const tbody = document.getElementById('trade-history-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    // Cache trades for re-sort and bind sort headers
    _lastTrades = trades || [];
    document.querySelectorAll('.sortable-th').forEach(th => {
        th.removeEventListener('click', _handleSortClick);
        th.addEventListener('click', _handleSortClick);
    });
    _updateSortHeaders();

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `
            <tr id="no-trades-row">
                <td colspan="10" style="text-align:center; color:#475569; padding:40px 16px;">
                    <span class="material-symbols-outlined" style="font-size:28px; display:block; margin-bottom:8px; opacity:0.25;">search_off</span>
                    <span style="font-style:italic;">No trades found in this period</span>
                </td>
            </tr>
        `;
        return;
    }

    // Separate active positions and closed trades, then sort each group
    const active = _sortTrades(trades.filter(t => t._active));
    const closed = _sortTrades(trades.filter(t => !t._active));

    // Render active positions first with a distinct style
    if (active.length > 0) {
        const headerRow = document.createElement('tr');
        headerRow.innerHTML = `
            <td colspan="10" style="padding:8px 16px; font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:#34d399; background:rgba(16,185,129,0.06); border-bottom:1px solid rgba(16,185,129,0.1);">
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
            const pnlPct = parseFloat(trade.pct || trade.pnlPct) || 0;
            const spread = parseFloat(trade.spread) || 0;

            row.innerHTML = `
                <td style="color:#64748b; font-size:11px;">${time}</td>
                <td style="font-weight:700; color:#e2e8f0;">${trade.symbol || '--'} <span style="font-size:8px;padding:1px 5px;border-radius:4px;background:rgba(16,185,129,0.15);color:#34d399;font-weight:800;letter-spacing:0.05em;">LIVE</span></td>
                <td style="text-align:center;"><span class="side-badge ${sideClass}">${side}</span></td>
                <td style="text-align:center;"><span style="font-size:9px;padding:2px 8px;border-radius:4px;background:rgba(16,185,129,0.12);color:#34d399;font-weight:800;letter-spacing:0.05em;">OPEN</span></td>
                <td style="text-align:right; font-weight:700; color:${pnlColor};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td style="text-align:right; font-size:11px; color:${pnlPct >= 0 ? '#34d399' : '#f87171'};">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</td>
                <td style="text-align:right; font-size:11px; color:#475569;">--</td>
                <td style="color:#34d399; font-size:11px; font-weight:600;">⏱ ${duration}</td>
                <td style="color:#94a3b8; font-size:11px;">${strategy}</td>
                <td style="color:#34d399; font-size:11px; font-weight:600;">● Active Position</td>
            `;
            tbody.appendChild(row);
        });
    }

    // Render closed trades
    if (closed.length > 0) {
        if (active.length > 0) {
            const headerRow = document.createElement('tr');
            headerRow.innerHTML = `
                <td colspan="10" style="padding:8px 16px; font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:#64748b; background:rgba(71,85,105,0.06); border-bottom:1px solid rgba(71,85,105,0.1);">
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
            const pnlPct = parseFloat(trade.pct || trade.pnlPct) || 0;
            const spread = parseFloat(trade.spread) || 0;

            // Result badge
            let resultBadge;
            if (pnl > 0) {
                resultBadge = '<span style="font-size:9px;padding:2px 8px;border-radius:4px;background:rgba(16,185,129,0.12);color:#34d399;font-weight:800;letter-spacing:0.05em;">WIN</span>';
            } else if (pnl < 0) {
                resultBadge = '<span style="font-size:9px;padding:2px 8px;border-radius:4px;background:rgba(239,68,68,0.12);color:#f87171;font-weight:800;letter-spacing:0.05em;">LOSS</span>';
            } else {
                resultBadge = '<span style="font-size:9px;padding:2px 8px;border-radius:4px;background:rgba(71,85,105,0.15);color:#64748b;font-weight:800;letter-spacing:0.05em;">B/E</span>';
            }

            row.innerHTML = `
                <td style="color:#64748b; font-size:11px;">${time}</td>
                <td style="font-weight:700; color:#e2e8f0;">${trade.symbol || '--'}</td>
                <td style="text-align:center;"><span class="side-badge ${sideClass}">${side}</span></td>
                <td style="text-align:center;">${resultBadge}</td>
                <td style="text-align:right; font-weight:700; color:${pnlColor};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
                <td style="text-align:right; font-size:11px; color:${pnlPct >= 0 ? '#34d399' : '#f87171'};">${pnlPct !== 0 ? (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%' : '--'}</td>
                <td style="text-align:right; font-size:11px; color:#475569;">${spread > 0 ? '$' + spread.toFixed(2) : '--'}</td>
                <td style="color:#34d399; font-size:11px; font-weight:600;">${(() => { const d = formatClosedDuration(trade); return d ? '⏱ ' + d : '--'; })()}</td>
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

// ═══════════════════════════════════════════════════════════
// AUTO-REFRESH TIMER (30-second countdown with ring animation)
// ═══════════════════════════════════════════════════════════

const REFRESH_INTERVAL = 30; // seconds
const RING_CIRCUMFERENCE = 2 * Math.PI * 10; // ~62.83 (r=10 from SVG)
let refreshCountdown = REFRESH_INTERVAL;
let refreshTimerID = null;

function startRefreshTimer() {
    stopRefreshTimer();
    refreshCountdown = REFRESH_INTERVAL;
    updateCountdownUI();
    refreshTimerID = setInterval(() => {
        refreshCountdown--;
        updateCountdownUI();
        if (refreshCountdown <= 0) {
            triggerAutoRefresh();
        }
    }, 1000);
}

function stopRefreshTimer() {
    if (refreshTimerID) {
        clearInterval(refreshTimerID);
        refreshTimerID = null;
    }
}

function triggerAutoRefresh() {
    const badge = document.getElementById('analytics-refresh-badge');
    if (badge) badge.classList.add('refreshing');

    refreshAnalytics();

    // Flash amber briefly then reset
    setTimeout(() => {
        if (badge) badge.classList.remove('refreshing');
        refreshCountdown = REFRESH_INTERVAL;
        updateCountdownUI();
    }, 500);
}

function updateCountdownUI() {
    const textEl = document.getElementById('refresh-countdown-text');
    const ringEl = document.getElementById('refresh-ring-progress');
    if (textEl) textEl.textContent = refreshCountdown;
    if (ringEl) {
        // Progress: full ring at REFRESH_INTERVAL, empty at 0
        const progress = refreshCountdown / REFRESH_INTERVAL;
        const offset = RING_CIRCUMFERENCE * (1 - progress);
        ringEl.style.strokeDashoffset = offset;
    }
}

// Clicking the badge triggers immediate refresh
document.addEventListener('DOMContentLoaded', () => {
    const badge = document.getElementById('analytics-refresh-badge');
    if (badge) {
        badge.style.cursor = 'pointer';
        badge.addEventListener('click', () => {
            triggerAutoRefresh();
        });
    }

    // Reset Paper Trading button — two-step confirm flow
    const resetBtn = document.getElementById('btn-reset-paper');
    const resetText = document.getElementById('reset-paper-text');
    let resetConfirmTimeout = null;
    let resetPending = false;

    if (resetBtn && resetText) {
        resetBtn.addEventListener('click', async () => {
            if (resetPending) return; // Already executing

            if (!resetBtn._confirmed) {
                // Step 1: Show confirm state
                resetBtn._confirmed = true;
                resetText.textContent = 'Sure? Confirm';
                resetBtn.style.background = 'linear-gradient(135deg, rgba(245,158,11,0.3), rgba(249,115,22,0.3))';
                resetBtn.style.borderColor = 'rgba(245,158,11,0.6)';
                resetBtn.style.color = '#fbbf24';
                resetBtn.style.boxShadow = '0 0 20px rgba(245,158,11,0.25)';
                resetBtn.style.animation = 'pulse 1.5s ease-in-out infinite';

                // Auto-revert after 3s if not confirmed
                resetConfirmTimeout = setTimeout(() => {
                    resetBtn._confirmed = false;
                    resetText.textContent = 'Reset Paper';
                    resetBtn.style.background = 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(249,115,22,0.15))';
                    resetBtn.style.borderColor = 'rgba(239,68,68,0.35)';
                    resetBtn.style.color = '#f87171';
                    resetBtn.style.boxShadow = '0 0 15px rgba(239,68,68,0.1)';
                    resetBtn.style.animation = '';
                }, 3000);
                return;
            }

            // Step 2: Execute reset
            clearTimeout(resetConfirmTimeout);
            resetPending = true;
            resetText.textContent = 'Resetting...';
            resetBtn.style.background = 'linear-gradient(135deg, rgba(20,184,166,0.2), rgba(16,185,129,0.2))';
            resetBtn.style.borderColor = 'rgba(20,184,166,0.4)';
            resetBtn.style.color = '#2dd4bf';
            resetBtn.style.boxShadow = '0 0 20px rgba(20,184,166,0.2)';
            resetBtn.style.animation = '';
            resetBtn.style.pointerEvents = 'none';

            try {
                const result = await window.api.resetPaperTrading();
                if (result.success) {
                    resetText.textContent = '✓ Reset Complete';
                    resetBtn.style.color = '#34d399';
                    // Refresh analytics data
                    setTimeout(() => refreshAnalytics(), 3000);
                } else {
                    resetText.textContent = '✗ Failed';
                    resetBtn.style.color = '#f87171';
                }
            } catch (err) {
                console.error('[ANALYTICS] Reset paper trading error:', err);
                resetText.textContent = '✗ Error';
                resetBtn.style.color = '#f87171';
            }

            // Revert button after 4s
            setTimeout(() => {
                resetBtn._confirmed = false;
                resetPending = false;
                resetText.textContent = 'Reset Paper';
                resetBtn.style.background = 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(249,115,22,0.15))';
                resetBtn.style.borderColor = 'rgba(239,68,68,0.35)';
                resetBtn.style.color = '#f87171';
                resetBtn.style.boxShadow = '0 0 15px rgba(239,68,68,0.1)';
                resetBtn.style.pointerEvents = '';
            }, 4000);
        });
    }
});

window.analyticsModule = {
    init: initAnalytics,
    refresh: refreshAnalytics,
    loadData: loadAnalyticsData,
    startTimer: startRefreshTimer,
    stopTimer: stopRefreshTimer
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => { initAnalytics(); startRefreshTimer(); }, 100);
    });
} else {
    setTimeout(() => { initAnalytics(); startRefreshTimer(); }, 100);
}
