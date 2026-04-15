function subscribeToAsset(symbol, tf, since) {
    console.log(`[SUBSCRIBE] Attempting to subscribe to ${symbol} (${tf})${since ? ` since=${since}` : ''}. WS state: ${ws ? ws.readyState : 'null'}`);
    if (ws && ws.readyState === WebSocket.OPEN) {
        console.log(`[SUBSCRIBE] Sending subscription request for ${symbol} (${tf})...`);
        const msg = { type: 'subscribe', symbol, tf };
        if (since) msg.since = since;
        ws.send(JSON.stringify(msg));
    } else {
        console.warn(`[SUBSCRIBE] WebSocket not open. Cannot subscribe to ${symbol}`);
    }
}

/**
 * Global Set tracking symbols currently being flattened.
 * Survives DOM rebuilds so table renderers can show "Closing..." state.
 */
window._pendingFlattens = window._pendingFlattens || new Set();

/**
 * Send a manual Cash-Out (flatten) request for a symbol.
 * Called by Holdings panel and Analytics active positions.
 * @param {string} symbol - The symbol to close (e.g. 'EURUSD')
 * @returns {boolean} true if the message was sent
 */
function sendFlattenSymbol(symbol) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        console.log(`[CASH-OUT] Sending flatten request for ${symbol}`);
        ws.send(JSON.stringify({ type: 'flatten_symbol', symbol }));
        window._pendingFlattens.add(symbol);
        // Update ALL matching buttons across all panels immediately
        _syncAllCashOutButtons(symbol, 'closing');
        // Safety timeout: if no flatten_ack within 15s, reset the button
        // (the position likely closed but the ack was lost in transit)
        setTimeout(() => {
            if (window._pendingFlattens.has(symbol)) {
                console.warn(`[CASH-OUT] No flatten_ack for ${symbol} after 15s — resetting button`);
                window._pendingFlattens.delete(symbol);
                _syncAllCashOutButtons(symbol, 'reset');
            }
        }, 15000);
        return true;
    } else if (ws && ws.readyState === WebSocket.CONNECTING) {
        // WS is reconnecting — retry after 1s
        console.warn(`[CASH-OUT] WebSocket reconnecting. Will retry flatten for ${symbol} in 1s...`);
        window._pendingFlattens.add(symbol);
        _syncAllCashOutButtons(symbol, 'closing');
        setTimeout(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                console.log(`[CASH-OUT] Retry: Sending flatten request for ${symbol}`);
                ws.send(JSON.stringify({ type: 'flatten_symbol', symbol }));
            } else {
                console.error(`[CASH-OUT] Retry failed: WS still not open for ${symbol}`);
                window._pendingFlattens.delete(symbol);
                _syncAllCashOutButtons(symbol, 'error');
            }
        }, 1500);
        return true; // Tell caller it's in-progress (don't show NO WS)
    } else {
        console.warn(`[CASH-OUT] WebSocket not open (state: ${ws ? ws.readyState : 'null'}). Cannot flatten ${symbol}`);
        return false;
    }
}

/**
 * Sync all Cash Out buttons for a symbol across Holdings + Analytics panels.
 * @param {string} symbol
 * @param {'closing'|'ok'|'error'|'reset'} state
 * @param {string} [reason]
 */
function _syncAllCashOutButtons(symbol, state, reason) {
    const safeSym = symbol.replace(/[^a-zA-Z0-9]/g, '');
    const holdingsBtn = document.getElementById(`cashout-${safeSym}`);
    const analyticsBtn = document.getElementById(`analytics-cashout-${safeSym}`);
    const allBtns = [holdingsBtn, analyticsBtn].filter(Boolean);

    allBtns.forEach(btn => {
        if (state === 'closing') {
            btn._sending = true;
            btn._confirmed = true;
            const hasIcons = btn.querySelector && btn.closest('.cashout-btn, [class*="cashout"]');
            btn.innerHTML = hasIcons
                ? '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">sync</span>Closing...</span>'
                : '⏳ Closing...';
            btn.style.background = 'linear-gradient(135deg, rgba(20,184,166,0.2), rgba(16,185,129,0.2))';
            btn.style.borderColor = 'rgba(20,184,166,0.4)';
            btn.style.color = '#2dd4bf';
            btn.style.boxShadow = '0 0 20px rgba(20,184,166,0.2)';
            btn.style.animation = '';
            btn.style.pointerEvents = 'none';
        } else if (state === 'ok') {
            btn._sending = false;
            const hasIcons = btn.querySelector && btn.closest('.cashout-btn, [class*="cashout"]');
            btn.innerHTML = hasIcons
                ? '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">check_circle</span>Closed!</span>'
                : '✅ Closed!';
            btn.style.background = 'linear-gradient(135deg, rgba(16,185,129,0.2), rgba(52,211,153,0.2))';
            btn.style.borderColor = 'rgba(16,185,129,0.5)';
            btn.style.color = '#34d399';
            btn.style.boxShadow = '0 0 20px rgba(16,185,129,0.2)';
            btn.style.animation = '';
            btn.style.pointerEvents = 'none';
        } else if (state === 'error') {
            btn._sending = false;
            btn._confirmed = false;
            const hasIcons = btn.querySelector && btn.closest('.cashout-btn, [class*="cashout"]');
            btn.innerHTML = hasIcons
                ? '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">error</span>Failed</span>'
                : '❌ Failed';
            btn.style.background = 'linear-gradient(135deg, rgba(239,68,68,0.2), rgba(248,113,113,0.2))';
            btn.style.borderColor = 'rgba(239,68,68,0.5)';
            btn.style.color = '#f87171';
            btn.style.boxShadow = '0 0 20px rgba(239,68,68,0.2)';
            btn.style.animation = '';
            btn.style.pointerEvents = '';
        } else if (state === 'reset') {
            btn._sending = false;
            btn._confirmed = false;
            const hasIcons = btn.querySelector && btn.closest('.cashout-btn, [class*="cashout"]');
            btn.innerHTML = hasIcons
                ? '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">payments</span>Cash Out</span>'
                : '💰 Cash Out';
            btn.style.background = 'linear-gradient(135deg, rgba(249,115,22,0.12), rgba(239,68,68,0.12))';
            btn.style.borderColor = 'rgba(249,115,22,0.3)';
            btn.style.color = '#fb923c';
            btn.style.boxShadow = '0 0 10px rgba(249,115,22,0.08)';
            btn.style.animation = '';
            btn.style.pointerEvents = '';
        }
    });
}
// Expose globally for cross-module access
window.sendFlattenSymbol = sendFlattenSymbol;
window._syncAllCashOutButtons = _syncAllCashOutButtons;

// [WEBSOCKET] Connect to Python Backend
const DEFAULT_WS_URL = 'ws://localhost:8080/ws';
let ws;
let WS_URL = DEFAULT_WS_URL;

// Shared timeframe normalizer (used by WS message handlers)
const normalizeTf = (t) => t.toLowerCase().trim();

async function connectWebSocket() {
    try {
        const env = await window.api.invoke('read-env');
        if (env.GUI_WS_URL) {
            WS_URL = env.GUI_WS_URL;
        }
    } catch (err) {
        console.warn("Failed to read GUI_WS_URL from .env, using default:", WS_URL);
    }

    console.log(`Connecting to Live Data Stream (${WS_URL})...`);
    ws = new WebSocket(WS_URL);

    let pingInterval;

    ws.onopen = () => {
        window._isWsConnected = true;
        window._wsReconnectAttempts = 0;
        
        // Give the backend a 20s grace period on startup before enforcing health heartbeat
        window._lastHealthUpdate = Date.now() + 20000;
        
        // Let the Vitals tab re-render immediately to reflect connected state if it's open
        if (typeof renderTab === 'function' && document.querySelector('.vitals-banner')) {
            renderTab();
        }

        console.log("Connected to Live Data Stream.");
        updateStatus('connected', '--');

        // Subscribe to current UI selection on open
        const symbol = document.getElementById('chart-symbol-label')?.innerText;
        const tf = document.getElementById('chart-tf-label')?.innerText || '15m';
        if (symbol) subscribeToAsset(symbol, tf);

        if (pingInterval) clearInterval(pingInterval);
        ws._lastPong = Date.now(); // Initialize to prevent immediate timeout
        pingInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const now = Date.now();
                if (now - ws._lastPong > 15000) {
                    console.warn("[WS] Ping timeout (No pong in 15s). Forcing reconnect...");
                    ws.close();
                    return;
                }
                
                // Guard against Zombie backend: verify actual health data is flowing
                // Backend broadcasts health every 30s, so give it up to 45s before assuming a zombie crash
                if (window._lastHealthUpdate && (now - window._lastHealthUpdate > 45000)) {
                    console.warn("[WS] Health Vitals timeout (No loop data in 45s). Bot loop stalled. Forcing reconnect...");
                    ws.close();
                    return;
                }

                ws._lastPing = now;
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 5000);

        // Periodic candle tick to keep chart live
        // Sends a lightweight 'tick' request that fetches only 2 candles
        // and updates the current bar smoothly (instead of full 200-candle history reload)
        if (window._chartRefreshInterval) clearInterval(window._chartRefreshInterval);
        window._chartRefreshInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const sym = document.getElementById('chart-symbol-label')?.innerText?.trim();
                const tf = document.getElementById('chart-tf-label')?.innerText?.trim() || '15m';
                if (sym) {
                    ws.send(JSON.stringify({ type: 'tick', symbol: sym, tf }));
                }
            }
        }, 3000); // Tick every 3 seconds for live price movement
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);



            if (msg.type === 'pong') {
                ws._lastPong = Date.now();
                if (ws._lastPing) {
                    const latency = Date.now() - ws._lastPing;
                    if (typeof statusLatency !== 'undefined' && statusLatency) {
                        statusLatency.textContent = `${latency}ms`;
                    }
                }
            } else if (msg.type === 'history') {
                const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
                const currentTfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
                // normalizeTf defined at module scope

                if (msg.symbol === currentSym && normalizeTf(msg.tf) === normalizeTf(currentTfRaw)) {
                    console.log(`[CHART] Received history for ${msg.symbol} ${msg.tf} (${msg.data.length} candles).`);

                    const fixedData = msg.data.map(c => ({
                        time: utcToLocal(c.time),
                        open: c.open, high: c.high, low: c.low, close: c.close
                    }));
                    // Store raw data with volume for VWAP
                    rawCandleData = msg.data.map(c => ({
                        time: utcToLocal(c.time),
                        open: c.open, high: c.high, low: c.low, close: c.close,
                        volume: c.volume || 0
                    }));
                    candleData = fixedData;
                    // Apply Heikin-Ashi if active
                    const displayData = chartMode === 'heikinashi' ? calculateHeikinAshi(fixedData) : fixedData;
                    candleSeries.setData(displayData);
                    if (typeof hideMarketClosedOverlay === 'function') hideMarketClosedOverlay();

                    if (indicatorSeries) {
                        // Use theme candle colors for volume bars
                        const themeNow = window.ThemeEngine ? window.ThemeEngine.THEMES[window.ThemeEngine.getActiveThemeId()] : null;
                        const volUp = (themeNow && themeNow.candleUp) || '#2dd4bf';
                        const volDown = (themeNow && themeNow.candleDown) || '#f43f5e';
                        const volumeData = msg.data.map(c => {
                            const isUp = c.close >= c.open;
                            return {
                                time: utcToLocal(c.time),
                                value: c.volume || 0,
                                color: isUp ? volUp : volDown
                            };
                        });
                        console.log(`[CHART-VOLUME] Setting ${volumeData.length} volume bars. Sample:`, volumeData[volumeData.length - 1]);
                        indicatorSeries.setData(volumeData);
                    }

                    updateIndicators();

                    const msgSym = msg.symbol.toUpperCase();
                    if (previousSymbol !== msgSym) {
                        clearTradeMarkers();
                        previousSymbol = msgSym;
                    }

                    tradeMarkers = markerCache[msgSym] || [];
                    if (candleSeries) {
                        candleSeries.setMarkers(tradeMarkers);
                    }

                    if (lastHoldings && lastHoldings.positions) {
                        const pos = parsePositionFromHoldings(lastHoldings.positions, msg.symbol);
                        if (pos) {
                            updatePositionLines(pos);
                        }
                    }

                    chart.timeScale().fitContent();
                }
            } else if (msg.type === 'candle') {
                const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
                const currentTfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
                // normalizeTf defined at module scope
                const symMatch = msg.symbol === currentSym;
                const tfMatch = normalizeTf(msg.tf) === normalizeTf(currentTfRaw);

                if (symMatch && tfMatch) {
                    const localTime = utcToLocal(msg.data.time);

                    // Guard: skip candles older than the chart's last known bar
                    const lastTime = candleData.length > 0 ? candleData[candleData.length - 1].time : 0;
                    if (localTime < lastTime) {
                        console.warn(`[CHART] Stale candle skipped: candle=${localTime} < chart=${lastTime} (diff=${lastTime - localTime}s)`);
                        return;
                    }

                    const newBar = {
                        time: localTime,
                        open: msg.data.open, high: msg.data.high, low: msg.data.low, close: msg.data.close
                    };
                    const newRawBar = { ...newBar, volume: msg.data.volume || 0 };

                    // Keep candleData and rawCandleData in sync for indicator calculations
                    if (candleData.length > 0 && candleData[candleData.length - 1].time === localTime) {
                        candleData[candleData.length - 1] = newBar;
                        if (rawCandleData.length > 0) rawCandleData[rawCandleData.length - 1] = newRawBar;
                    } else {
                        candleData.push(newBar);
                        rawCandleData.push(newRawBar);
                    }

                    // Update the chart — apply HA transform if active
                    try {
                        if (chartMode === 'heikinashi') {
                            candleSeries.setData(calculateHeikinAshi(candleData));
                        } else {
                            candleSeries.update(newBar);
                        }
                    } catch (e) {
                        console.warn(`[CANDLE-RX] update() failed, falling back to setData: ${e.message}`);
                        const displayData = chartMode === 'heikinashi' ? calculateHeikinAshi(candleData) : candleData;
                        candleSeries.setData(displayData);
                    }

                    // Update indicators on each new candle
                    updateIndicators();

                    if (indicatorSeries && typeof msg.data.volume !== 'undefined') {
                        const isUp = msg.data.close >= msg.data.open;
                        const themeNow = window.ThemeEngine ? window.ThemeEngine.THEMES[window.ThemeEngine.getActiveThemeId()] : null;
                        const volUp = (themeNow && themeNow.candleUp) || '#2dd4bf';
                        const volDown = (themeNow && themeNow.candleDown) || '#f43f5e';
                        try {
                            indicatorSeries.update({
                                time: localTime,
                                value: msg.data.volume,
                                color: isUp ? volUp : volDown
                            });
                        } catch (e) {
                            console.warn(`[CHART] Volume update failed: ${e.message}`);
                        }
                    }
                }
            } else if (msg.type === 'holdings') {
                // Dedicated holdings message — updates the Holdings panel directly
                // without needing to parse log lines (more reliable, faster)
                if (msg.data) {
                    updateHoldingsTable(msg.data);
                }
            } else if (msg.type === 'log') {
                parseLogLine(msg.data);
                appendLog(msg.level || "INFO", msg.data);
                
                // Intercept Eval logs for Modal
                if (msg.data.includes("PROP FIRM EVALUATION FAILED") || msg.data.includes("PROP FIRM EVALUATION PASSED")) {
                    const isPass = msg.data.includes("PASSED");
                    const modal = document.getElementById('eval-popup-modal');
                    const icon = document.getElementById('eval-popup-icon');
                    const title = document.getElementById('eval-popup-title');
                    const message = document.getElementById('eval-popup-message');
                    
                    if (modal && icon && title && message) {
                        const innerBox = modal.querySelector('.max-w-md');
                        if (isPass) {
                            icon.textContent = "stars";
                            icon.className = "material-symbols-outlined text-6xl text-yellow-400 mb-4 animate-bounce drop-shadow-[0_0_15px_rgba(250,204,21,0.5)]";
                            title.textContent = "EVALUATION PASSED!";
                            title.className = "text-2xl font-black text-yellow-400 uppercase tracking-widest mb-2";
                            message.textContent = "Congratulations! You successfully reached the profit target. You are now ready for a funded account!";
                            if (innerBox) innerBox.className = "bg-[#0f172a] border-2 border-yellow-500/50 rounded-2xl p-8 max-w-md w-full shadow-[0_0_50px_rgba(250,204,21,0.3)] flex flex-col items-center text-center transform scale-100 transition-transform duration-300 relative";
                        } else {
                            icon.textContent = "cancel";
                            icon.className = "material-symbols-outlined text-6xl text-red-500 mb-4 animate-bounce drop-shadow-[0_0_15px_rgba(239,68,68,0.5)]";
                            title.textContent = "EVALUATION FAILED";
                            title.className = "text-2xl font-black text-red-500 uppercase tracking-widest mb-2";
                            message.textContent = msg.data.includes("DAILY LOSS") ? "You breached the Daily Drawdown limit. Your account has been liquidated." : "You breached the Overall Max Drawdown limit. Your account has been liquidated.";
                            if (innerBox) innerBox.className = "bg-[#0f172a] border-2 border-red-500/50 rounded-2xl p-8 max-w-md w-full shadow-[0_0_50px_rgba(239,68,68,0.3)] flex flex-col items-center text-center transform scale-100 transition-transform duration-300 relative";
                        }
                        modal.classList.remove('hidden');
                    }
                }
            } else if (msg.type === 'state') {
                const data = msg.data;
                if (data.pnl_stats && data.pnl_stats[pnlTimeframe] !== undefined) {
                    currentRealizedPnL = parseFloat(data.pnl_stats[pnlTimeframe]);
                    refreshMainPnlDisplay();
                }
                if (data.capital !== undefined) {
                    const capitalEl = document.getElementById('account-capital');
                    if (capitalEl) capitalEl.innerText = data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    // Store live capital for analytics.js to use (prevents stale ledger override)
                    window.__liveCapital = data.capital;
                    // Sync "Capital Now" stat card with live value
                    const capNowEl = document.getElementById('metric-capital-end');
                    if (capNowEl) capNowEl.innerText = '$' + data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    // Seed "Capital Start" if still at default $0.00
                    const capStartEl = document.getElementById('metric-capital-start');
                    if (capStartEl && (capStartEl.innerText === '$0.00' || capStartEl.innerText === '$0')) {
                        capStartEl.innerText = '$' + data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    }
                    // Update Net Change
                    const capChangeEl = document.getElementById('metric-capital-change');
                    if (capChangeEl && capStartEl) {
                        const startVal = parseFloat(capStartEl.innerText.replace(/[$,]/g, '')) || 0;
                        const change = data.capital - startVal;
                        capChangeEl.innerText = (change >= 0 ? '+' : '') + '$' + change.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                        capChangeEl.style.color = change >= 0 ? '#2dd4bf' : '#f87171';
                    }
                }
                if (data.cash !== undefined) {
                    const cashEl = document.getElementById('account-cash');
                    if (cashEl) cashEl.innerText = data.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }
                if (data.profile) {
                    const profileEl = document.getElementById('status-profile');
                    if (profileEl) {
                        profileEl.innerText = data.profile.toUpperCase();
                        profileEl.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
                    }
                }
                if (data.is_sabbath !== undefined) {
                    window.isSabbath = !!data.is_sabbath;
                    const sabbathEl = document.getElementById('status-sabbath');
                    if (sabbathEl) {
                        if (data.is_sabbath) sabbathEl.classList.remove('hidden');
                        else sabbathEl.classList.add('hidden');
                    }
                }
                if (data.is_eval !== undefined) {
                    const evalEl = document.getElementById('status-eval');
                    if (evalEl) {
                        if (data.is_eval && (data.is_paper || window.isPaper)) evalEl.classList.remove('hidden');
                        else evalEl.classList.add('hidden');
                    }
                }
                // Track paper mode globally so analytics uses the right data source
                if (data.is_paper !== undefined) {
                    const wasPaper = !!window.isPaper;
                    window.isPaper = !!data.is_paper;
                    const resetBtn = document.getElementById('btn-reset-paper');
                    if (resetBtn) {
                        if (data.is_paper) {
                            resetBtn.classList.remove('hidden');
                            resetBtn.classList.add('flex');
                        } else {
                            resetBtn.classList.add('hidden');
                            resetBtn.classList.remove('flex');
                        }
                    }
                    // When paper mode state arrives (especially on first WS connect),
                    // re-trigger the analytics panel so it queries with the correct paperMode flag.
                    // This fixes the startup race where analytics loads before WS sends is_paper.
                    if (wasPaper !== !!data.is_paper) {
                        console.log(`[WS] Paper mode changed: ${wasPaper} -> ${!!data.is_paper}, refreshing analytics`);
                        if (window.analyticsModule && typeof window.analyticsModule.refresh === 'function') {
                            window.analyticsModule.refresh();
                        }
                    }
                }
                if (data.symbols && Array.isArray(data.symbols) && data.symbols.length > 0) {
                    WATCHED_SYMBOLS.splice(0, WATCHED_SYMBOLS.length, ...data.symbols);
                    const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                    const newIdx = WATCHED_SYMBOLS.indexOf(currentSym);
                    if (newIdx !== -1) currentSymbolIndex = newIdx;
                    else {
                        currentSymbolIndex = 0;
                        updateSymbolDisplay();
                    }
                }
                saveState();
            } else if (msg.type === 'health') {
                // Store health vitals globally for the Vitals tab
                window.__healthVitals = msg.data;
                window.__healthVitals._receivedAt = Date.now();
                window._lastHealthUpdate = Date.now(); // Reset the zombie watchdog timer


                // Update sidebar health summary
                const healthSummary = document.getElementById('health-summary');
                const healthDot = document.getElementById('health-overall-dot');
                const healthText = document.getElementById('health-overall-text');
                if (healthSummary && healthDot && healthText) {
                    const overall = msg.data.overall || 'healthy';
                    const colorMap = {
                        healthy: { dot: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]', text: 'text-emerald-400' },
                        warning: { dot: 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]', text: 'text-amber-400' },
                        critical: { dot: 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)] animate-pulse', text: 'text-red-400' },
                    };
                    const colors = colorMap[overall] || colorMap.healthy;
                    healthDot.className = `w-2 h-2 rounded-full ${colors.dot}`;
                    healthText.className = `text-[9px] ${colors.text} font-bold uppercase tracking-wider`;

                    const vitals = msg.data.vitals || {};
                    const counts = { healthy: 0, warning: 0, critical: 0 };
                    Object.values(vitals).forEach(v => { counts[v.status] = (counts[v.status] || 0) + 1; });

                    if (overall === 'healthy') {
                        healthText.textContent = `Vitals: All Clear (${counts.healthy}/8)`;
                    } else if (overall === 'warning') {
                        healthText.textContent = `Vitals: ${counts.warning} Warning`;
                    } else {
                        healthText.textContent = `Vitals: ${counts.critical} Critical`;
                    }

                    // Visibility logic
                    if (overall === 'healthy') {
                        if (!window._healthAllClearDismissed) {
                            healthSummary.classList.remove('hidden');
                            healthSummary.style.transition = 'opacity 0.4s ease';
                            healthSummary.style.opacity = '1';
                            
                            if (window._healthFadeTimer) clearTimeout(window._healthFadeTimer);
                            window._healthFadeTimer = setTimeout(() => {
                                healthSummary.style.opacity = '0';
                                setTimeout(() => {
                                    healthSummary.classList.add('hidden');
                                    window._healthAllClearDismissed = true;
                                }, 400);
                            }, 5000);
                        } else {
                            if (!healthSummary.classList.contains('hidden')) {
                                healthSummary.style.opacity = '0';
                                setTimeout(() => healthSummary.classList.add('hidden'), 400);
                            }
                        }
                    } else {
                        if (window._healthFadeTimer) clearTimeout(window._healthFadeTimer);
                        healthSummary.classList.remove('hidden');
                        healthSummary.style.transition = 'opacity 0.4s ease';
                        healthSummary.style.opacity = '1';
                    }
                }

                // Auto-refresh the Nurse's Station Tab if it's currently open
                if (typeof renderTab === 'function' && document.querySelector('.vitals-banner')) {
                    if (typeof hideTooltip === 'function') hideTooltip(); // Clean up lingering tooltips
                    renderTab();
                }

                // Red badge on Vitals settings tab
                const vitalsBadge = document.getElementById('vitals-badge');
                if (vitalsBadge) {
                    const hasCritical = msg.data.overall === 'critical' || msg.data.overall === 'warning';
                    vitalsBadge.classList.toggle('hidden', !hasCritical);
                    if (msg.data.overall === 'critical') {
                        vitalsBadge.className = 'ml-auto w-2 h-2 rounded-full bg-red-500 animate-pulse';
                    } else if (msg.data.overall === 'warning') {
                        vitalsBadge.className = 'ml-auto w-2 h-2 rounded-full bg-amber-500 animate-pulse';
                    }
                }

                // If the Vitals tab is currently rendered, refresh it
                if (typeof window._refreshVitalsTab === 'function') {
                    window._refreshVitalsTab();
                }
            } else if (msg.type === 'ai_commentary') {
                updateAIInsightPanel(msg.content, msg.timestamp, msg.next_update_in);
            } else if (msg.type === 'flatten_ack') {
                // Backend acknowledged a Cash-Out request
                const sym = msg.symbol || '??';

                if (msg.status === 'ok') {
                    console.log(`[CASH-OUT] ✅ ${sym} flatten acknowledged by backend`);
                    if (typeof appendLog === 'function') {
                        appendLog('INFO', `[MANUAL EXIT] ⚡ ${sym} position closed successfully.`);
                    }
                    // Remove from pending set and sync all buttons
                    window._pendingFlattens.delete(sym);
                    _syncAllCashOutButtons(sym, 'ok');
                } else {
                    console.warn(`[CASH-OUT] ❌ ${sym} flatten failed: ${msg.reason || 'unknown'}`);
                    if (typeof appendLog === 'function') {
                        appendLog('ERROR', `[MANUAL EXIT] Failed to close ${sym}: ${msg.reason || 'unknown'}`);
                    }
                    // Remove from pending set and show error state
                    window._pendingFlattens.delete(sym);
                    _syncAllCashOutButtons(sym, 'error');
                    // Auto-reset error state after 4s
                    setTimeout(() => {
                        _syncAllCashOutButtons(sym, 'reset');
                    }, 4000);
                }
            }
        } catch (e) {
            console.error("WS Parse Error", e);
        }
    };

    ws.onclose = () => {
        window._isWsConnected = false;
        window._wsReconnectAttempts = (window._wsReconnectAttempts || 0) + 1;

        // Try to trigger re-render of settings to show disconnected state
        if (typeof renderTab === 'function' && document.querySelector('.vitals-banner')) {
            renderTab();
        }

        console.warn("Live Data Stream Disconnected. Retrying in 5s...");
        updateStatus('disconnected', '--');
        if (document.getElementById('status-dot')) {
            document.getElementById('status-dot').className = 'w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]';
        }
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
        console.error("WS Error", err);
        ws.close();
    };
}

// Start WS
// Initialized later in init()
