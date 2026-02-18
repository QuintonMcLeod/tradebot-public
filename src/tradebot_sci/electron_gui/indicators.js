// ═══════════════════════════════════════════════════════════════
//  indicators.js — Technical indicator calculations
//  Extracted from renderer.js for maintainability.
// ═══════════════════════════════════════════════════════════════

window.Indicators = (() => {

    function calculateSMA(data, period) {
        const result = [];
        for (let i = period - 1; i < data.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) {
                sum += data[i - j].close;
            }
            result.push({ time: data[i].time, value: sum / period });
        }
        return result;
    }

    function calculateEMA(data, period) {
        const result = [];
        const multiplier = 2 / (period + 1);

        // Start with SMA for the first EMA value
        if (data.length < period) return result;

        let sum = 0;
        for (let i = 0; i < period; i++) {
            sum += data[i].close;
        }
        let ema = sum / period;
        result.push({ time: data[period - 1].time, value: ema });

        for (let i = period; i < data.length; i++) {
            ema = (data[i].close - ema) * multiplier + ema;
            result.push({ time: data[i].time, value: ema });
        }
        return result;
    }

    function calculateBollingerBands(data, period = 20, stdDevMultiplier = 2) {
        const upper = [], middle = [], lower = [];
        for (let i = period - 1; i < data.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += data[i - j].close;
            const mean = sum / period;
            let sqSum = 0;
            for (let j = 0; j < period; j++) sqSum += Math.pow(data[i - j].close - mean, 2);
            const stdDev = Math.sqrt(sqSum / period);
            const t = data[i].time;
            upper.push({ time: t, value: mean + stdDevMultiplier * stdDev });
            middle.push({ time: t, value: mean });
            lower.push({ time: t, value: mean - stdDevMultiplier * stdDev });
        }
        return { upper, middle, lower };
    }

    function calculateVWAP(data) {
        // data must have .close and .volume (use rawCandleData)
        const result = [];
        let cumVol = 0, cumTP = 0;
        for (let i = 0; i < data.length; i++) {
            const tp = (data[i].high + data[i].low + data[i].close) / 3;
            const vol = data[i].volume || 0;
            cumVol += vol;
            cumTP += tp * vol;
            if (cumVol > 0) {
                result.push({ time: data[i].time, value: cumTP / cumVol });
            }
        }
        return result;
    }

    function calculateRSI(data, period = 14) {
        const result = [];
        if (data.length < period + 1) return result;
        let gains = 0, losses = 0;
        for (let i = 1; i <= period; i++) {
            const change = data[i].close - data[i - 1].close;
            if (change >= 0) gains += change;
            else losses -= change;
        }
        let avgGain = gains / period;
        let avgLoss = losses / period;
        const rsi = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
        result.push({ time: data[period].time, value: rsi });
        for (let i = period + 1; i < data.length; i++) {
            const change = data[i].close - data[i - 1].close;
            avgGain = (avgGain * (period - 1) + (change >= 0 ? change : 0)) / period;
            avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
            const r = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
            result.push({ time: data[i].time, value: r });
        }
        return result;
    }

    function calculateHeikinAshi(data) {
        if (!data || data.length === 0) return [];
        const result = [];
        for (let i = 0; i < data.length; i++) {
            const c = data[i];
            const haClose = (c.open + c.high + c.low + c.close) / 4;
            const haOpen = i === 0
                ? (c.open + c.close) / 2
                : (result[i - 1].open + result[i - 1].close) / 2;
            const haHigh = Math.max(c.high, haOpen, haClose);
            const haLow = Math.min(c.low, haOpen, haClose);
            result.push({ time: c.time, open: haOpen, high: haHigh, low: haLow, close: haClose });
        }
        return result;
    }

    return {
        calculateSMA,
        calculateEMA,
        calculateBollingerBands,
        calculateVWAP,
        calculateRSI,
        calculateHeikinAshi,
    };
})();
