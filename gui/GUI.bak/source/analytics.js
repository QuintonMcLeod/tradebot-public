/**
 * Analytics Renderer Logic
 * Handles charts, metrics display, and data loading for the Analytics view
 */

// Chart instances
let winLossPieChart = null;
let equityCurveChart = null;

// Current filter state
let currentFilter = '24h';

// LightweightCharts instance for equity curve
let equityChart = null;
let equityAreaSeries = null;

/**
 * Initialize the analytics module
 */
function initAnalytics() {
    console.log('[ANALYTICS] Initializing...');

    // Setup time filter buttons
    setupTimeFilters();

    // Load initial data
    loadAnalyticsData(currentFilter);
}

/**
 * Setup time filter button handlers
 */
function setupTimeFilters() {
    const filterBtns = document.querySelectorAll('.time-filter-btn');

    filterBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Update active state
            filterBtns.forEach(b => {
                b.classList.remove('active', 'bg-teal-500/20', 'text-teal-300', 'border', 'border-teal-500/40');
                b.classList.add('text-slate-400');
            });
            e.target.classList.add('active', 'bg-teal-500/20', 'text-teal-300', 'border', 'border-teal-500/40');
            e.target.classList.remove('text-slate-400');

            // Load new data
            const filter = e.target.dataset.filter;
            currentFilter = filter;
            loadAnalyticsData(filter);
        });
    });
}

/**
 * Load analytics data for the given time filter
 */
async function loadAnalyticsData(filter) {
    console.log(`[ANALYTICS] Loading data for filter: ${filter}`);

    // Show loading state
    showLoadingState();

    try {
        // Check if API is available
        if (!window.api || !window.api.getAnalyticsSummary) {
            console.error('[ANALYTICS] API not available');
            showErrorState('API not available');
            return;
        }

        console.log('[ANALYTICS] Calling getAnalyticsSummary...');
        const result = await window.api.getAnalyticsSummary(filter);
        console.log('[ANALYTICS] Result received:', result);

        if (result && result.success) {
            console.log('[ANALYTICS] Data loaded successfully');
            console.log('[ANALYTICS] Trades:', result.data.totalTrades);
            console.log('[ANALYTICS] Capital entries:', result.data.capitalHistory?.length || 0);
            updateMetrics(result.data);
            updateCharts(result.data);
            updateTradeHistory(result.data.trades || []);
        } else {
            console.error('[ANALYTICS] Error:', result?.error || 'Unknown error');
            showErrorState(result?.error || 'Failed to load data');
            // Still try to show zeros
            updateMetrics({});
        }
    } catch (error) {
        console.error('[ANALYTICS] Exception:', error);
        showErrorState(error.message);
        // Still try to show zeros
        updateMetrics({});
    }
}

/**
 * Show loading state on metrics
 */
function showLoadingState() {
    const metricIds = [
        'metric-wins', 'metric-losses', 'metric-winrate', 'metric-rr',
        'metric-pnl', 'metric-pnl-pct', 'metric-avg-win', 'metric-avg-loss',
        'metric-best', 'metric-worst', 'metric-pf', 'metric-capital-start',
        'metric-capital-end', 'metric-capital-change'
    ];

    metricIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<span class="animate-pulse">...</span>';
    });
}

/**
 * Show error state
 */
function showErrorState(error) {
    console.error('[ANALYTICS] Error state:', error);
    // Show error in trade history table
    const tbody = document.getElementById('trade-history-body');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="px-6 py-12 text-center text-red-400 italic">
                    <span class="material-symbols-outlined text-4xl mb-2 block opacity-50">error</span>
                    Error loading data: ${error || 'Unknown error'}
                </td>
            </tr>
        `;
    }

    // Also clear loading state on metrics
    updateMetrics({});
}

/**
 * Update all metric displays
 */
function updateMetrics(data) {
    console.log('[ANALYTICS] Updating metrics with data:', data);

    // Ensure data is an object
    data = data || {};

    // Primary metrics
    setMetric('metric-wins', data.totalWins ?? 0);
    setMetric('metric-losses', data.totalLosses ?? 0);
    setMetric('metric-winrate', `${data.winRate ?? 0}%`);
    setMetric('metric-rr', data.riskReward && data.riskReward !== 'N/A' ? `${data.riskReward}:1` : 'N/A');

    // PnL with color
    const pnl = parseFloat(data.totalPnl) || 0;
    const pnlEl = document.getElementById('metric-pnl');
    if (pnlEl) {
        pnlEl.textContent = formatCurrency(pnl);
        pnlEl.className = `text-3xl font-black ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`;
    }

    // PnL percentage
    const pnlPct = parseFloat(data.capitalChangePct) || 0;
    const pnlPctEl = document.getElementById('metric-pnl-pct');
    if (pnlPctEl) {
        pnlPctEl.textContent = `${pnlPct >= 0 ? '+' : ''}${pnlPct}%`;
        pnlPctEl.className = `text-3xl font-black ${pnlPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`;
    }

    // Secondary metrics
    setMetric('metric-avg-win', formatCurrency(data.avgWin ?? 0));
    setMetric('metric-avg-loss', formatCurrency(data.avgLoss ?? 0), true);
    setMetric('metric-best', formatCurrency(data.bestTrade ?? 0));
    setMetric('metric-worst', formatCurrency(data.worstTrade ?? 0), true);
    setMetric('metric-pf', data.profitFactor && data.profitFactor !== 'N/A' ? data.profitFactor : '0.00');

    // Capital metrics
    setMetric('metric-capital-start', formatCurrency(data.capitalStart ?? 0));
    setMetric('metric-capital-end', formatCurrency(data.capitalEnd ?? 0));

    const capitalChange = parseFloat(data.capitalChange) || 0;
    const capitalChangeEl = document.getElementById('metric-capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = formatCurrency(capitalChange, true);
        capitalChangeEl.className = `text-2xl font-black ${capitalChange >= 0 ? 'text-emerald-400' : 'text-red-400'}`;
    }

    // Trade count
    const tradeCountEl = document.getElementById('trade-count');
    if (tradeCountEl) {
        tradeCountEl.textContent = `${data.totalTrades ?? 0} trades`;
    }

    console.log('[ANALYTICS] Metrics update complete');
}

/**
 * Set a single metric value
 */
function setMetric(id, value, isNegative = false) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}

/**
 * Format currency value
 */
function formatCurrency(value, showSign = false) {
    const num = parseFloat(value) || 0;
    const formatted = Math.abs(num).toFixed(2);
    const sign = showSign ? (num >= 0 ? '+' : '-') : (num < 0 ? '-' : '');
    return `${sign}$${formatted}`;
}

/**
 * Update all charts
 */
function updateCharts(data) {
    updateWinLossPie(data);
    updateEquityCurve(data);
}

/**
 * Update Win/Loss pie chart
 */
function updateWinLossPie(data) {
    const canvas = document.getElementById('chart-winloss-pie');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const wins = parseInt(data.totalWins) || 0;
    const losses = parseInt(data.totalLosses) || 0;
    const total = wins + losses;

    // Destroy existing chart
    if (winLossPieChart) {
        winLossPieChart.destroy();
    }

    // If no data, show empty state
    if (total === 0) {
        winLossPieChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['No Data'],
                datasets: [{
                    data: [1],
                    backgroundColor: ['rgba(100, 116, 139, 0.3)'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: { display: false }
                }
            }
        });
        return;
    }

    winLossPieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Wins', 'Losses'],
            datasets: [{
                data: [wins, losses],
                backgroundColor: [
                    'rgba(16, 185, 129, 0.8)',  // Emerald
                    'rgba(239, 68, 68, 0.8)'    // Red
                ],
                borderColor: [
                    'rgba(16, 185, 129, 1)',
                    'rgba(239, 68, 68, 1)'
                ],
                borderWidth: 2,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#94a3b8',
                        font: {
                            size: 11,
                            weight: 'bold'
                        },
                        padding: 20,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(2, 6, 23, 0.95)',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(20, 184, 166, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function (context) {
                            const pct = ((context.parsed / total) * 100).toFixed(1);
                            return ` ${context.label}: ${context.parsed} (${pct}%)`;
                        }
                    }
                }
            },
            animation: {
                animateRotate: true,
                animateScale: true
            }
        },
        plugins: [{
            id: 'centerText',
            beforeDraw: function (chart) {
                const ctx = chart.ctx;
                const centerX = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
                const centerY = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2;

                ctx.save();
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';

                // Total number
                ctx.font = 'bold 28px Inter, sans-serif';
                ctx.fillStyle = '#f1f5f9';
                ctx.fillText(total.toString(), centerX, centerY - 8);

                // Label
                ctx.font = '10px Inter, sans-serif';
                ctx.fillStyle = '#64748b';
                ctx.fillText('TRADES', centerX, centerY + 14);

                ctx.restore();
            }
        }]
    });
}

/**
 * Update Equity Curve chart using LightweightCharts
 */
function updateEquityCurve(data) {
    const container = document.getElementById('chart-equity-curve');
    if (!container) return;

    // Clear existing chart
    container.innerHTML = '';

    const capitalHistory = data.capitalHistory || [];
    console.log('[ANALYTICS] Equity curve - capital history entries:', capitalHistory.length);

    // If no data, show empty state
    if (capitalHistory.length === 0) {
        container.innerHTML = `
            <div class="h-full flex items-center justify-center text-slate-500 text-sm italic">
                <span class="material-symbols-outlined mr-2">timeline</span>
                No capital data available
            </div>
        `;
        return;
    }

    // Create chart
    equityChart = LightweightCharts.createChart(container, {
        layout: {
            background: { type: 'Solid', color: 'transparent' },
            textColor: '#64748b',
            fontFamily: 'Inter, sans-serif'
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.03)' }
        },
        rightPriceScale: {
            borderVisible: false,
            scaleMargins: { top: 0.1, bottom: 0.1 }
        },
        timeScale: {
            borderVisible: false,
            timeVisible: true
        },
        crosshair: {
            vertLine: { color: 'rgba(20, 184, 166, 0.3)', width: 1 },
            horzLine: { color: 'rgba(20, 184, 166, 0.3)', width: 1 }
        }
    });

    // Prepare data - timestamps are ISO strings, convert to Date objects
    const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
    const chartData = capitalHistory
        .filter(c => c.nav || c.balance)
        .map(c => {
            // Handle both Date objects and ISO strings
            const ts = typeof c.timestamp === 'string' ? new Date(c.timestamp) : c.timestamp;
            return {
                time: Math.floor(ts.getTime() / 1000) - tzOffsetSeconds,
                value: c.nav || c.balance
            };
        })
        .sort((a, b) => a.time - b.time);

    // Remove duplicates (keep last value for each timestamp)
    const uniqueData = [];
    const seenTimes = new Set();
    for (let i = chartData.length - 1; i >= 0; i--) {
        if (!seenTimes.has(chartData[i].time)) {
            seenTimes.add(chartData[i].time);
            uniqueData.unshift(chartData[i]);
        }
    }

    if (uniqueData.length === 0) {
        container.innerHTML = `
            <div class="h-full flex items-center justify-center text-slate-500 text-sm italic">
                <span class="material-symbols-outlined mr-2">timeline</span>
                No capital data available
            </div>
        `;
        return;
    }

    // Determine if overall positive or negative
    const startValue = uniqueData[0]?.value || 0;
    const endValue = uniqueData[uniqueData.length - 1]?.value || 0;
    const isPositive = endValue >= startValue;

    // Create area series
    equityAreaSeries = equityChart.addAreaSeries({
        lineColor: isPositive ? 'rgba(16, 185, 129, 1)' : 'rgba(239, 68, 68, 1)',
        topColor: isPositive ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)',
        bottomColor: isPositive ? 'rgba(16, 185, 129, 0.0)' : 'rgba(239, 68, 68, 0.0)',
        lineWidth: 2,
        priceFormat: {
            type: 'price',
            precision: 2,
            minMove: 0.01
        }
    });

    equityAreaSeries.setData(uniqueData);
    equityChart.timeScale().fitContent();

    // Handle resize
    const resizeObserver = new ResizeObserver(entries => {
        if (entries.length > 0 && equityChart) {
            const { width, height } = entries[0].contentRect;
            equityChart.applyOptions({ width, height });
        }
    });
    resizeObserver.observe(container);
}

/**
 * Update trade history table
 */
function updateTradeHistory(trades) {
    const tbody = document.getElementById('trade-history-body');
    if (!tbody) return;

    // Clear existing rows
    tbody.innerHTML = '';

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `
            <tr id="no-trades-row">
                <td colspan="5" class="px-6 py-12 text-center text-slate-500 italic">
                    <span class="material-symbols-outlined text-4xl mb-2 block opacity-30">search_off</span>
                    No trades found in this period
                </td>
            </tr>
        `;
        return;
    }

    trades.forEach((trade, index) => {
        const row = document.createElement('tr');
        row.className = 'hover:bg-teal-500/5 transition-colors';

        // Format timestamp - handle both Date objects and ISO strings
        let time = '--';
        if (trade.timestamp) {
            try {
                const ts = typeof trade.timestamp === 'string' ? new Date(trade.timestamp) : trade.timestamp;
                time = ts.toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                console.error('[ANALYTICS] Error parsing trade timestamp:', e);
            }
        }

        // Format PnL
        const pnl = parseFloat(trade.pnl) || 0;
        const pnlClass = pnl >= 0 ? 'text-emerald-400' : 'text-red-400';
        const pnlText = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;

        // Format side
        const side = (trade.side || 'long').toUpperCase();
        const sideClass = side === 'SHORT' ? 'text-red-400 bg-red-400/10' : 'text-emerald-400 bg-emerald-400/10';

        row.innerHTML = `
            <td class="px-6 py-3 text-slate-500 text-xs">${time}</td>
            <td class="px-4 py-3 font-bold text-slate-200">${trade.symbol || '--'}</td>
            <td class="px-4 py-3 text-center">
                <span class="px-2 py-1 rounded text-[10px] font-bold ${sideClass}">${side}</span>
            </td>
            <td class="px-4 py-3 text-right font-bold ${pnlClass}">${pnlText}</td>
            <td class="px-4 py-3 text-slate-400 text-xs truncate max-w-xs">${trade.reason || '--'}</td>
        `;

        tbody.appendChild(row);
    });
}

/**
 * Refresh analytics data (can be called externally)
 */
function refreshAnalytics() {
    loadAnalyticsData(currentFilter);
}

// Export for external use
window.analyticsModule = {
    init: initAnalytics,
    refresh: refreshAnalytics,
    loadData: loadAnalyticsData
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        // Delay init to ensure Chart.js is loaded
        setTimeout(initAnalytics, 100);
    });
} else {
    setTimeout(initAnalytics, 100);
}
