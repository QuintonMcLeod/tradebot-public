# Analytics/Graph Page Implementation Plan

## Overview
Add a comprehensive Analytics page to the Electron GUI dashboard that displays trade history, performance metrics, and visualizations. The page will parse log files to extract trade data and present it with beautiful charts, tables, and statistics.

---

## Phase 1: Infrastructure & Data Layer

### 1.1 Add Chart.js Dependency
**File:** `src/tradebot_sci/electron_gui/package.json`
- Add `chart.js` and `chartjs-plugin-datalabels` for pie charts, bar charts, histograms
- LightweightCharts already available for equity curves

### 1.2 Create Analytics Preload Script
**File:** `src/tradebot_sci/electron_gui/analytics_preload.js`
- Expose IPC methods for reading/parsing log files
- Create secure bridge between main process and analytics renderer

### 1.3 Create Log Parser Module (Main Process)
**File:** `src/tradebot_sci/electron_gui/log_parser.js`
- Parse log files to extract trade records
- Identify patterns:
  - `[EXIT]` lines for closed trades with PnL
  - `[HOLDINGS]` lines for position snapshots
  - `[OANDA/IBKR/CCXT] Account Summary` for capital tracking
  - `[DECISION]` / `[STRUCTURE]` for strategy decisions
  - Timestamp parsing for time filtering
- Return structured trade data:
  ```javascript
  {
    timestamp: Date,
    symbol: string,
    side: 'long' | 'short',
    action: 'entry' | 'exit',
    pnl: number,
    strategy: string,
    entryPrice: number,
    exitPrice: number,
    size: number,
    reason: string
  }
  ```

### 1.4 Add IPC Handlers (Main Process)
**File:** `src/tradebot_sci/electron_gui/main.js`
- `ipcMain.handle('get-trade-history', timeFilter)` - Returns parsed trades
- `ipcMain.handle('get-capital-history', timeFilter)` - Returns capital snapshots
- `ipcMain.handle('get-analytics-summary', timeFilter)` - Returns computed metrics

---

## Phase 2: Analytics View (Renderer)

### 2.1 Create Analytics HTML Structure
**File:** `src/tradebot_sci/electron_gui/index.html`
- Add new view section `#view-analytics` (hidden by default)
- Structure:
  ```
  ┌─────────────────────────────────────────────────────────┐
  │  TIME FILTER TABS: [1H] [24H] [Week] [Month] [All]     │
  ├─────────────────────────────────────────────────────────┤
  │  SUMMARY CARDS (2x3 Grid)                              │
  │  ┌────────┐ ┌────────┐ ┌────────┐                      │
  │  │ Wins   │ │ Losses │ │ Win %  │                      │
  │  │  12    │ │   5    │ │ 70.6%  │                      │
  │  └────────┘ └────────┘ └────────┘                      │
  │  ┌────────┐ ┌────────┐ ┌────────┐                      │
  │  │ PnL    │ │ R:R    │ │Capital │                      │
  │  │+$45.20 │ │  1.8   │ │$126.50 │                      │
  │  └────────┘ └────────┘ └────────┘                      │
  ├─────────────────────────────────────────────────────────┤
  │  CHARTS ROW (Side by Side)                             │
  │  ┌─────────────────┐  ┌─────────────────┐              │
  │  │   PIE CHART     │  │   EQUITY CURVE  │              │
  │  │   Win/Loss      │  │   ──────────    │              │
  │  │     70%/30%     │  │                 │              │
  │  └─────────────────┘  └─────────────────┘              │
  ├─────────────────────────────────────────────────────────┤
  │  ADDITIONAL METRICS ROW                                │
  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐│
  │  │ Avg    │ │ Avg    │ │ Best   │ │ Worst  │ │ Profit ││
  │  │ Win    │ │ Loss   │ │ Trade  │ │ Trade  │ │ Factor ││
  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘│
  ├─────────────────────────────────────────────────────────┤
  │  TRADE LIST TABLE (Scrollable)                         │
  │  ┌─────────────────────────────────────────────────────┐│
  │  │ Time | Symbol | Side | Entry | Exit | PnL | Strat  ││
  │  │──────────────────────────────────────────────────────││
  │  │ 10:30| EURUSD | LONG | 1.174 | 1.176| +$2 | RBR    ││
  │  │ ...  │ ...    │ ...  │ ...   │ ...  │ ... │ ...    ││
  │  └─────────────────────────────────────────────────────┘│
  └─────────────────────────────────────────────────────────┘
  ```

### 2.2 Create Analytics CSS
**File:** `src/tradebot_sci/electron_gui/settings.css` (extend existing)
- Add `.analytics-section` styles
- Add `.metric-card` component (large number display)
- Add `.chart-container` for chart wrappers
- Add `.trade-table` with alternating row colors
- Add `.time-filter-tabs` component
- Use existing design tokens (teal accent, glass effects, gradients)

### 2.3 Create Analytics Renderer Logic
**File:** `src/tradebot_sci/electron_gui/analytics.js`
- Initialize Chart.js instances (pie chart, equity curve)
- Implement time filter logic (1h, 24h, week, month)
- Compute metrics from trade data:
  - **Core Metrics (9)**:
    1. Number of Wins
    2. Number of Losses
    3. Win Rate (%)
    4. Risk-to-Reward Ratio
    5. Total PnL ($)
    6. PnL Percentage (%)
    7. Capital at Start
    8. Capital at End
    9. Net Change
  - **Additional Metrics (5)**:
    10. Average Win ($)
    11. Average Loss ($)
    12. Best Trade ($)
    13. Worst Trade ($)
    14. Profit Factor (gross profit / gross loss)
- Populate trade list table with sorting
- Handle view switching (show/hide based on nav selection)

---

## Phase 3: Navigation Integration

### 3.1 Update View Switching Logic
**File:** `src/tradebot_sci/electron_gui/renderer.js`
- Modify `nav-graph` click handler to:
  - Hide dashboard view (`#view-dashboard`)
  - Show analytics view (`#view-analytics`)
  - Trigger data refresh via IPC
- Add `nav-dashboard` handler to:
  - Hide analytics view
  - Show dashboard view

### 3.2 View Structure Changes
**File:** `src/tradebot_sci/electron_gui/index.html`
- Wrap existing dashboard content in `#view-dashboard`
- Add `#view-analytics` section (initially hidden)
- Both views share the same sidebar/titlebar

---

## Phase 4: Chart Implementations

### 4.1 Win/Loss Pie Chart
- Chart.js doughnut chart
- Colors: Green (#10b981) for wins, Red (#ef4444) for losses
- Center text showing total trades
- Animated entrance

### 4.2 Equity Curve
- LightweightCharts area chart
- Shows capital over time within selected period
- Green fill for positive trend, red for negative
- Tooltips showing exact values

### 4.3 PnL Histogram (Bonus)
- Chart.js bar chart
- Distribution of trade PnL amounts
- Helps visualize trade size consistency

### 4.4 Strategy Breakdown Pie (Bonus)
- Shows which strategies contributed to wins/losses
- Useful for identifying best-performing strategies

---

## Phase 5: Polish & UX

### 5.1 Loading States
- Skeleton loaders while parsing logs
- Smooth transitions between time filters

### 5.2 Empty States
- "No trades in this period" message with icon
- Guidance to check earlier periods

### 5.3 Responsive Design
- Cards stack on smaller windows
- Charts resize appropriately

### 5.4 Animations
- Fade-in for view transitions
- Counter animations for numbers
- Chart entrance animations

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `package.json` | MODIFY | Add chart.js dependency |
| `main.js` | MODIFY | Add analytics IPC handlers |
| `log_parser.js` | CREATE | Trade log parsing logic |
| `analytics_preload.js` | CREATE | IPC bridge for analytics |
| `index.html` | MODIFY | Add analytics view structure |
| `renderer.js` | MODIFY | View switching logic |
| `analytics.js` | CREATE | Analytics renderer logic |
| `settings.css` | MODIFY | Add analytics styles |

---

## Metrics Specification

### Core Metrics (User Requested)
| # | Metric | Calculation | Display |
|---|--------|-------------|---------|
| 1 | Wins | Count where pnl > 0 | "12" |
| 2 | Losses | Count where pnl < 0 | "5" |
| 3 | Win Rate | wins / total * 100 | "70.6%" |
| 4 | R:R Ratio | avg_win / abs(avg_loss) | "1.8:1" |
| 5 | Total PnL | Sum of all pnl | "+$45.20" / "-$12.30" |
| 6 | PnL % | pnl / starting_capital * 100 | "+3.2%" |
| 7 | Capital Start | First capital reading in period | "$1,000.00" |
| 8 | Capital End | Last capital reading in period | "$1,045.20" |
| 9 | Trade List | All trades in period | Table |

### Additional Metrics (5 Recommended)
| # | Metric | Calculation | Display |
|---|--------|-------------|---------|
| 10 | Avg Win | Sum(wins) / count(wins) | "+$4.50" |
| 11 | Avg Loss | Sum(losses) / count(losses) | "-$2.50" |
| 12 | Best Trade | Max(pnl) | "+$15.00" |
| 13 | Worst Trade | Min(pnl) | "-$8.00" |
| 14 | Profit Factor | gross_profit / gross_loss | "1.8" |

---

## Time Filters

| Filter | Lookback | Log Parsing |
|--------|----------|-------------|
| 1 Hour | 60 min | Last ~60 log entries |
| 24 Hours | 24 hr | ~1000-2000 entries |
| Week | 7 days | Multiple log rotations |
| Month | 30 days | All available logs |

---

## Design Notes

### Color Palette (from settings.css)
- **Background**: `#020617` (slate-950)
- **Card Background**: `rgba(15, 23, 42, 0.4)` with blur
- **Accent (Teal)**: `#14b8a6`
- **Purple Accent**: `#8b5cf6`
- **Success/Win**: `#10b981`
- **Error/Loss**: `#ef4444`
- **Text Primary**: `#f1f5f9`
- **Text Secondary**: `#94a3b8`

### Component Patterns
- Glass cards with border glow on hover
- Gradient backgrounds with radial gradients
- Smooth transitions (0.25s cubic-bezier)
- Material Symbols for icons

---

## Implementation Order

1. **Infrastructure** (Phase 1): 1.1 → 1.2 → 1.3 → 1.4
2. **View Structure** (Phase 2): 2.1 → 2.2
3. **Navigation** (Phase 3): 3.1 → 3.2
4. **Renderer Logic** (Phase 2): 2.3
5. **Charts** (Phase 4): 4.1 → 4.2 → (4.3, 4.4 optional)
6. **Polish** (Phase 5): As time permits

---

## Dependencies to Add

```json
{
  "dependencies": {
    "chart.js": "^4.4.1",
    "chartjs-plugin-datalabels": "^2.2.0"
  }
}
```

---

## Risk Mitigation

1. **Large Log Files**: Implement pagination and lazy loading
2. **Missing Data**: Handle logs with incomplete trade records gracefully
3. **Date Parsing**: Robust timestamp parsing with timezone handling
4. **Memory**: Stream-parse large files instead of loading all at once
