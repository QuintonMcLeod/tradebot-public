// --- Trade Marker Functions ---
function addTradeMarker(time, isBuy, symbol, price, customText = null) {
    const sym = symbol.toUpperCase();
    if (!markerCache[sym]) markerCache[sym] = [];

    // Enhanced marker styling for better visibility
    const marker = {
        time: time,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: customText || (isBuy ? `▶ BUY ${price?.toFixed(2) || ''}` : `◀ SELL ${price?.toFixed(2) || ''}`),
        size: 2,
    };

    console.log(`[MARKER-CACHE] Adding to ${sym}:`, marker);

    // Deduplicate: Don't add if we already have a marker at this time with this shape
    const exists = markerCache[sym].some(m => m.time === marker.time && m.shape === marker.shape);
    if (!exists) {
        markerCache[sym].push(marker);
        markerCache[sym].sort((a, b) => a.time - b.time);

        const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
        if (sym === currentSym) {
            tradeMarkers = markerCache[sym];
            console.log(`[CHART-RENDER] Setting markers for ${sym} (count: ${tradeMarkers.length})`);
            if (candleSeries) {
                candleSeries.setMarkers(tradeMarkers);
            }
        }
    }
}

// Exit marker function for closed trades
function addExitMarker(time, isWin, symbol, price, pnlPct, customText = null) {
    const sym = symbol.toUpperCase();
    if (!markerCache[sym]) markerCache[sym] = [];

    const pnlStr = pnlPct ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%` : '';
    const marker = {
        time: time,
        position: 'aboveBar',
        color: isWin ? '#10b981' : '#f43f5e',  // Emerald for win, Rose for loss
        shape: 'square',  // Square shape for exits (different from arrows for entries)
        text: customText || `EXIT ${price?.toFixed(2) || ''} ${pnlStr}`,
        size: 2,
    };

    const exists = markerCache[sym].some(m => m.time === marker.time && m.shape === marker.shape);
    if (!exists) {
        markerCache[sym].push(marker);
        markerCache[sym].sort((a, b) => a.time - b.time);

        const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
        if (sym === currentSym) {
            tradeMarkers = markerCache[sym];
            if (candleSeries) {
                candleSeries.setMarkers(tradeMarkers);
            }
        }
    }
}

function clearTradeMarkers() {
    tradeMarkers = [];
    if (candleSeries) {
        candleSeries.setMarkers([]);
    }
}

// --- Position Line Functions ---
function updatePositionLines(position) {
    // Always clear existing lines first to prevent duplicates
    clearPositionLines();

    if (!candleSeries || !position) {
        return;
    }

    const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
    if (position.symbol?.toUpperCase() !== currentSym) {
        return;
    }

    currentPosition = position;

    // Entry is shown as an ARROW MARKER (positioned on the correct candle)
    // SL and TP are shown as horizontal lines

    // Stop Loss Line (Red)
    if (position.sl) {
        stopLossLine = candleSeries.createPriceLine({
            price: position.sl,
            color: '#ef4444',
            lineWidth: 2,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `SL @ ${position.sl.toFixed(4)}`,
        });
    }

    // Take Profit Line (Green)
    if (position.tp) {
        takeProfitLine = candleSeries.createPriceLine({
            price: position.tp,
            color: '#22c55e',
            lineWidth: 2,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `TP @ ${position.tp.toFixed(4)}`,
        });
    }

    console.log(`[CHART] Drew position lines for ${position.symbol}: SL=${position.sl}, TP=${position.tp}`);
}

function clearPositionLines() {
    if (candleSeries) {
        // Remove existing price lines if they exist
        if (entryPriceLine) {
            candleSeries.removePriceLine(entryPriceLine);
            entryPriceLine = null;
        }
        if (stopLossLine) {
            candleSeries.removePriceLine(stopLossLine);
            stopLossLine = null;
        }
        if (takeProfitLine) {
            candleSeries.removePriceLine(takeProfitLine);
            takeProfitLine = null;
        }
    }
    currentPosition = null;
}

function parsePositionFromHoldings(holdings, symbol) {
    if (!holdings || !Array.isArray(holdings)) return null;

    const pos = holdings.find(h => h.symbol?.toUpperCase() === symbol.toUpperCase());
    if (!pos) return null;

    return {
        symbol: pos.symbol,
        side: pos.side || pos.direction,
        entry: pos.entry_price || pos.avg_price,
        entryTime: pos.opened_at || pos.entry_time,  // ISO timestamp
        sl: pos.stop_loss || pos.sl,
        tp: pos.take_profit || pos.tp,
        size: Math.abs(pos.size || 0),
    };
}
