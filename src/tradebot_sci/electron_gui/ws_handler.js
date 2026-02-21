function subscribeToAsset(symbol, tf) {
    console.log(`[SUBSCRIBE] Attempting to subscribe to ${symbol} (${tf}). WS state: ${ws ? ws.readyState : 'null'}`);
    if (ws && ws.readyState === WebSocket.OPEN) {
        console.log(`[SUBSCRIBE] Sending subscription request for ${symbol} (${tf})...`);
        ws.send(JSON.stringify({ type: 'subscribe', symbol, tf }));
    } else {
        console.warn(`[SUBSCRIBE] WebSocket not open. Cannot subscribe to ${symbol}`);
    }
}

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
        console.log("Connected to Live Data Stream.");
        updateStatus('connected', '--');

        // Subscribe to current UI selection on open
        const symbol = document.getElementById('chart-symbol-label')?.innerText;
        const tf = document.getElementById('chart-tf-label')?.innerText || '15m';
        if (symbol) subscribeToAsset(symbol, tf);

        // Start Ping-Pong
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws._lastPing = Date.now();
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
                if (ws._lastPing) {
                    const latency = Date.now() - ws._lastPing;
                    if (statusLatency) statusLatency.textContent = `${latency}ms`;
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
            } else if (msg.type === 'log') {
                parseLogLine(msg.data);
                appendLog(msg.level || "INFO", msg.data);
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
                    // Show/hide the Reset Paper button in analytics
                    const resetBtn = document.getElementById('btn-reset-paper');
                    if (resetBtn) {
                        if (data.is_sabbath) {
                            resetBtn.classList.remove('hidden');
                            resetBtn.classList.add('flex');
                        } else {
                            resetBtn.classList.add('hidden');
                            resetBtn.classList.remove('flex');
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
            } else if (msg.type === 'ai_commentary') {
                updateAIInsightPanel(msg.content, msg.timestamp, msg.next_update_in);
            }
        } catch (e) {
            console.error("WS Parse Error", e);
        }
    };

    ws.onclose = () => {
        console.warn("Live Data Stream Disconnected. Retrying in 5s...");
        updateStatus('disconnected', '--');
        if (pingInterval) clearInterval(pingInterval);
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
        console.error("WS Error", err);
        ws.close();
    };
}

// Start WS
// Initialized later in init()
