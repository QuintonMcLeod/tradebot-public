// CODING RULE: Do NOT insert watermark tags (e.g. [AGENT_NAME], [AI FIX], etc.)
// into comments or log statements. Write clean, professional comments only.
// See AGENTS.md for full guidelines.

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');
const logParser = require('./log_parser');

// Suppress EPIPE errors on stdout/stderr — these are non-fatal pipe breaks
// when the parent process (terminal/launcher) closes before Electron finishes writing.
process.stdout?.on('error', (err) => { if (err.code !== 'EPIPE') throw err; });
process.stderr?.on('error', (err) => { if (err.code !== 'EPIPE') throw err; });

let mainWindow;
let settingsWindow;
let botRunning = false;

// Helper to determine OS
const isWindows = () => process.platform === 'win32';

// Helper to find repo root reliably
const DOTENV_PATH = path.join(__dirname, '../../../.env');
const PROFILES_PATH = path.join(__dirname, '../../../config/settings_profiles.yaml');
const CONFIG_JSON_PATH = path.join(__dirname, '../../../config.json');
const SECRETS_PATH = path.join(__dirname, '../../../.env.secrets');

// Setup IPC handlers (called after app ready)
function setupIpcHandlers() {
    // IPC Handlers for Settings Data
    ipcMain.handle('read-env', async () => {
        if (!fs.existsSync(DOTENV_PATH)) return {};
        const content = fs.readFileSync(DOTENV_PATH, 'utf8');
        const env = {};
        content.split('\n').forEach(line => {
            const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)$/);
            if (match) env[match[1]] = match[2];
        });
        return env;
    });

    ipcMain.handle('save-env', async (event, updates) => {
        let content = fs.existsSync(DOTENV_PATH) ? fs.readFileSync(DOTENV_PATH, 'utf8') : '';
        let lines = content.split('\n');
        const keys = Object.keys(updates);

        keys.forEach(key => {
            let found = false;
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].startsWith(`${key}=`)) {
                    lines[i] = `${key}=${updates[key]}`;
                    found = true;
                    break;
                }
            }
            if (!found) lines.push(`${key}=${updates[key]}`);
        });

        fs.writeFileSync(DOTENV_PATH, lines.join('\n'));

        // Notify all windows
        BrowserWindow.getAllWindows().forEach(win => {
            win.webContents.send('env-updated', updates);
        });

        return { success: true };
    });

    ipcMain.handle('read-profiles', async () => {
        if (!fs.existsSync(PROFILES_PATH)) return "";
        return fs.readFileSync(PROFILES_PATH, 'utf8');
    });

    ipcMain.handle('save-profiles', async (event, content) => {
        fs.writeFileSync(PROFILES_PATH, content);
        return { success: true };
    });

    ipcMain.handle('read-profiles-json', async () => {
        const yaml = require('js-yaml');
        if (!fs.existsSync(PROFILES_PATH)) return {};
        try {
            const content = fs.readFileSync(PROFILES_PATH, 'utf8');
            return yaml.load(content) || {};
        } catch (e) {
            console.error("[MAIN] YAML Load Error:", e);
            return {};
        }
    });

    ipcMain.handle('save-profiles-json', async (event, data) => {
        const yaml = require('js-yaml');
        try {
            const content = yaml.dump(data, { lineWidth: -1, noRefs: true });
            fs.writeFileSync(PROFILES_PATH, content);
            return { success: true };
        } catch (e) {
            console.error("[MAIN] YAML Save Error:", e);
            return { success: false, error: e.message };
        }
    });

    // =============================================
    // NEW: Unified config.json handlers
    // =============================================
    ipcMain.handle('read-config', async () => {
        if (!fs.existsSync(CONFIG_JSON_PATH)) {
            console.warn("[MAIN] config.json not found, returning empty object");
            return {};
        }
        try {
            const content = fs.readFileSync(CONFIG_JSON_PATH, 'utf8');
            return JSON.parse(content);
        } catch (e) {
            console.error("[MAIN] Config JSON Load Error:", e);
            return {};
        }
    });

    ipcMain.handle('save-config', async (event, config) => {
        try {
            const content = JSON.stringify(config, null, 2);
            fs.writeFileSync(CONFIG_JSON_PATH, content);
            console.log("[MAIN] Saved config.json");

            // Notify all windows that config changed
            BrowserWindow.getAllWindows().forEach(win => {
                win.webContents.send('config-updated', config);
            });

            return { success: true };
        } catch (e) {
            console.error("[MAIN] Config JSON Save Error:", e);
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('read-secrets', async () => {
        if (!fs.existsSync(SECRETS_PATH)) return {};
        const content = fs.readFileSync(SECRETS_PATH, 'utf8');
        const secrets = {};
        content.split('\n').forEach(line => {
            if (line.startsWith('#') || !line.trim()) return;
            const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
            if (match) secrets[match[1]] = match[2];
        });
        return secrets;
    });

    ipcMain.handle('save-secrets', async (event, secrets) => {
        try {
            let content = "# API Keys and Secrets - DO NOT COMMIT TO GIT\n\n";
            for (const [key, value] of Object.entries(secrets)) {
                content += `${key}=${value}\n`;
            }
            fs.writeFileSync(SECRETS_PATH, content);
            return { success: true };
        } catch (e) {
            console.error("[MAIN] Secrets Save Error:", e);
            return { success: false, error: e.message };
        }
    });

    // City / Location Resolver (Ported Logic)
    ipcMain.handle('resolve-city', async (event, cityName) => {
        const cities = {
            "New York": { lat: 40.7128, lon: -74.0060, tz: "America/New_York" },
            "Los Angeles": { lat: 34.0522, lon: -118.2437, tz: "America/Los_Angeles" },
            "Chicago": { lat: 41.8781, lon: -87.6298, tz: "America/Chicago" },
            "Miami": { lat: 25.7617, lon: -80.1918, tz: "America/New_York" },
            "Jerusalem": { lat: 31.7683, lon: 35.2137, tz: "Asia/Jerusalem" },
            "London": { lat: 51.5074, lon: -0.1278, tz: "Europe/London" }
        };
        return cities[cityName] || null;
    });

    ipcMain.handle('read-profile-strategies', async (event, profileName) => {
        const yaml = require('js-yaml');
        if (!fs.existsSync(PROFILES_PATH)) return null;
        const content = fs.readFileSync(PROFILES_PATH, 'utf8');
        const profiles = yaml.load(content);
        return profiles?.profiles?.[profileName]?.strategies || null;
    });

    ipcMain.handle('save-profile-strategies', async (event, profileName, strategies) => {
        const yaml = require('js-yaml');
        if (!fs.existsSync(PROFILES_PATH)) return { success: false, error: 'Profiles file missing' };
        const content = fs.readFileSync(PROFILES_PATH, 'utf8');
        const profiles = yaml.load(content);

        if (!profiles.profiles) profiles.profiles = {};
        if (!profiles.profiles[profileName]) profiles.profiles[profileName] = {};

        profiles.profiles[profileName].strategies = strategies;

        fs.writeFileSync(PROFILES_PATH, yaml.dump(profiles, { lineWidth: -1 }));
        return { success: true };
    });

    // Analytics IPC Handlers
    ipcMain.handle('get-trade-history', async (event, filter = '24h') => {
        console.log('[ANALYTICS-IPC] get-trade-history called with filter:', filter);
        try {
            const data = await logParser.getTradeHistory(filter);
            console.log('[ANALYTICS-IPC] Trade history result - trades:', data.trades?.length, 'capital:', data.capital?.length);
            return { success: true, data };
        } catch (error) {
            console.error('[ANALYTICS-IPC] Error getting trade history:', error);
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('get-analytics-summary', async (event, filter = '24h') => {
        console.log('[ANALYTICS-IPC] get-analytics-summary called with filter:', filter);
        try {
            const data = await logParser.getTradeHistory(filter);
            console.log('[ANALYTICS-IPC] Raw data - trades:', data.trades?.length, 'capital:', data.capital?.length);
            const summary = logParser.calculateAnalyticsSummary(data);
            console.log('[ANALYTICS-IPC] Summary calculated - totalTrades:', summary.totalTrades);
            return { success: true, data: summary };
        } catch (error) {
            console.error('[ANALYTICS-IPC] Error calculating summary:', error);
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('get-log-files', async () => {
        try {
            const files = logParser.getLogFiles();
            return { success: true, data: files };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    // =============================================
    // Help Documentation
    // =============================================
    const DOCS_DIR = path.join(__dirname, '../../../Documentation');
    const RTFM_DIR = path.join(DOCS_DIR, 'RTFM');

    const HELP_CATALOG = [
        { filename: 'HOW_TO_USE.md', title: 'First Time? Everything You Need to Launch Your First Trade', category: 'guide', icon: 'rocket_launch', description: 'First time? Start here. This is the practical, no-fluff guide to getting the bot running and making trades. Prerequisites, first-time setup, broker configuration, risk profiles, and your first live trade — everything from install to execution, with no detours into architecture or philosophy.', featured: true },
        { filename: 'RTFM/01_PHILOSOPHY.md', title: 'Born From Late-Stage Capitalism: Why This Bot Exists', category: 'rtfm', icon: 'psychology', description: 'Welcome to TradeBot SCI Enterprise. It has no fancy marketing name. It has no singular author. It is a tool, forged in the fires of late-stage capitalism, designed with one singular, ruthless purpose: To Make Money. Food prices are climbing faster than a crypto shitcoin. Insurance premiums are ridiculous. Companies are firing millions of people while executives buy another yacht to park inside their bigger yacht.' },
        { filename: 'RTFM/02_SKELETON_ARCH.md', title: 'Inside the Machine: The Complete Skeletal Architecture', category: 'rtfm', icon: 'account_tree', description: '"It\'s alive! ...mostly." This document explains the anatomy of the application. If 01_PHILOSOPHY was the soul, this is the bones. The high-level architecture covers every module — the Electron GUI, the runtime loop, the strategy engine, the broker layer, and the market data pipeline — and shows exactly how data flows between them.' },
        { filename: 'RTFM/03_FUNCTIONS_DATA.md', title: 'Under the Hood: Every Function, Every Data Packet', category: 'rtfm', icon: 'data_object', description: '"The devil is in the details. And the bugs." If you are debugging this thing, you need to know what the data actually looks like. These are the core data objects — MarketSnapshot, TradeDecision, PositionState — the packets passed around like hot potatoes through every layer of the system. Every field, every type, every edge case documented.' },
        { filename: 'RTFM/04_MAP_TOC.md', title: 'Lost in the Codebase? The Complete Navigation Map', category: 'rtfm', icon: 'map', description: '"Where is main.py again?" The project structure is classic Python with an Electron GUI layer on top. This is the complete navigational map of the entire repository — every directory, every module, every source file — organized as a tree with annotations explaining what each piece does and how it relates to the whole.' },
        { filename: 'RTFM/05_COOKBOOK.md', title: 'Recipes for Traders: A Cookbook of Common Tasks', category: 'rtfm', icon: 'menu_book', description: '"Give a man a fish, he trades for a day. Teach a man to configure the bot, he loses money automatically." Here are the common tasks you might want to perform: adding a new symbol, switching strategies, tweaking risk parameters, customizing scan intervals, configuring multi-broker setups. Each recipe includes both GUI and config file methods.' },
        { filename: 'RTFM/06_PANIC_BUTTON.md', title: 'Something Is Wrong — The Emergency Panic Protocol', category: 'rtfm', icon: 'emergency', description: '"Something is wrong. Make it stop." So the bot is screaming in red text, or worse — it\'s doing nothing at all. Don\'t panic. Read this. Covers every emergency scenario: Kill Switch activation, insufficient funds, broker disconnects, stuck positions, API rate limits, and the nuclear option — how to flatten everything and shut down safely.' },
        { filename: 'RTFM/07_COCKPIT_CONTROLS.md', title: 'What Does This Button Do? The Complete Cockpit Guide', category: 'rtfm', icon: 'tune', description: '"What does this button do?" — Last words of a former trader. The bot is configured through the Settings GUI, config.json, or config/settings_profiles.yaml. This guide covers every control in the cockpit: trading profiles, risk sliders, strategy selectors, broker toggles, safety shields, and the hidden power-user settings most people never find.' },
        { filename: 'RTFM/08_API_SETUP.md', title: 'Connecting to the World: Every Broker, Every API Key', category: 'rtfm', icon: 'key', description: '"The bot is only as smart as its connection." This guide explains specifically how to connect the bot to the outside world. Step-by-step configuration for every supported integration: the AI Brain (TradeSci, OpenAI, Gemini, Claude), Interactive Brokers for stocks and futures, OANDA for forex, and CCXT for crypto exchanges like Gemini and Coinbase.' },
        { filename: 'RTFM/09_FEET_WET_STRATEGY.md', title: '20 Weapons of War: The Complete Strategy Arsenal', category: 'rtfm', icon: 'strategy', description: '"One strategy doesn\'t fit all markets. Choose your weapon wisely — or let Meta-SCI choose for you." TradeBot SCI supports 20 distinct trading strategies, each optimized for different market conditions. You can assign different strategies to different asset classes, or use Meta-SCI to let the bot pick the best one automatically via tournament-style scoring.', featured: true },
        { filename: 'RTFM/14_READING_THE_SCOREBOARD.md', title: 'Am I Winning? How to Read Your Performance Metrics', category: 'rtfm', icon: 'monitoring', description: '"If you can\'t measure it, you can\'t improve it." So the bot is running. Trades are happening. Numbers are flying across your screen. But what do they actually mean? This guide teaches you the Big Five metrics — Profit Factor, Win Rate, Max Drawdown, R:R, and Expectancy — how to read the dashboard, and when to worry versus when to be patient.' },
        { filename: 'RTFM/11_GHOST_IN_MACHINE.md', title: 'I Think, Therefore I Trade: The AI Decision Engine', category: 'rtfm', icon: 'smart_toy', description: '"I think, therefore I trade." You know the bot trades. But how does it decide? This document explains the Brain (strategy/engine.py), the Strategy Arsenal of 20 distinct weapons, and the Soul — the AI Backup system. The bot isn\'t locked to one strategy. It can assign different strategies per asset class, or use Meta-SCI to choose automatically based on real-time market conditions.' },
        { filename: 'RTFM/12_TIME_MACHINE.md', title: 'I Have to Go Back: The Trinity of Backtesting', category: 'rtfm', icon: 'history', description: '"I have to go back." You have discovered that there are actually three ways to time-travel in this repository. This document explains the Trinity of Backtesting: the Easy Way (GUI Benchmark for normal humans), the Intermediate Way (CLI scripts for power users), and the Hard Way (raw engine calls for developers who want full control over every parameter).' },
        { filename: 'RTFM/13_ENV_VARS.md', title: 'Every Toggle, Every Flag: The Environment Variable Bible', category: 'rtfm', icon: 'settings_applications', description: 'The comprehensive reference for every environment variable used by TradeBot SCI — including purpose, usage, and meaningful defaults. Covers GUI_AUTOSTART_BOT, GUI_KEEP_BOT_RUNNING, kill switches, API keys, feature flags, broker credentials, AI model selection, logging levels, and every hidden toggle the bot knows about.' },
        { filename: 'RTFM/15_NIGHT_WATCH.md', title: 'The Night Watch: Sleeping While Your Money Works', category: 'rtfm', icon: 'bedtime', description: '"The market never sleeps. Neither does your anxiety." So you\'ve got an open position and the clock says 11 PM. Your spouse is already asleep. Your dog is judging you. This guide explains how the bot handles overnight and weekend positions — server-side stops, weekend gap protection, and why checking your phone at 3 AM is a sign you need to fix your position sizing, not your alarm.' },
        { filename: 'RTFM/16_WAR_ROOM.md', title: 'The War Room: Decoding the Log Output', category: 'rtfm', icon: 'terminal', description: '"I see the Matrix now. It\'s mostly INFO lines." You opened the log panel. You saw a wall of text scrolling at the speed of anxiety. This guide teaches you every log tag — [STATE], [GUARD], [DECISION], [ENTRY], [EXIT] — what they mean, how to read a trade\'s lifecycle, and when red lines are actually scary versus when they\'re just the bot talking to itself.' },
        { filename: 'RTFM/17_SABBATH_PROTOCOL.md', title: 'The Sabbath Protocol: When the Bot Takes a Day Off', category: 'rtfm', icon: 'synagogue', description: '"Even God rested on the seventh day. The bot just switches to paper trading." Some of us observe the Sabbath. The markets don\'t. This guide explains how the bot automatically swaps to the Paper Broker during Sabbath, keeps scanning and analyzing in paper mode, and seamlessly resumes live trading when Sabbath ends — all calculated astronomically based on your location.' },
        { filename: 'RTFM/18_SHIELD_WALL.md', title: 'The Shield Wall: Risk Management Deep Dive', category: 'rtfm', icon: 'shield', description: '"The fastest way to go broke is to be right 90% of the time and blow up on the other 10%." Every layer of risk management explained: position sizing formulas, the Leverage Sentry, Daily Loss Limit circuit breaker, ICC Gatekeeper, Position Lock, and ATR Armor. With the actual math behind each one. Because the best trade is the catastrophic trade you never took.' },
        { filename: 'RTFM/19_HYBRID_ENGINE.md', title: 'The Hybrid Engine: Multi-Broker Orchestration', category: 'rtfm', icon: 'hub', description: '"One broker is a dependency. Two brokers is a strategy. Three brokers is an empire." How the bot routes trades to different brokers based on asset class: OANDA for forex, CCXT for crypto, IBKR for stocks. Simple mode, primary mode, and full hybrid mode explained. Architecture diagrams, routing logic, and when to add complexity versus when to keep it simple.' },
        { filename: 'RTFM/20_AUTOPILOT.md', title: 'The Autopilot: Auto-Schedule & Profile Switching', category: 'rtfm', icon: 'schedule', description: '"The bot doesn\'t have a 9-to-5. It has a 24/7 and a strong opinion about when to show up." How Auto-Schedule automatically switches trading profiles based on active market sessions — London forex at 3 AM, NY overlap at 8 AM, crypto during off-hours and weekends. Maximum coverage, zero wasted scans.' },
        { filename: 'RTFM/21_DASHBOARD.md', title: 'The Dashboard: Reading the GUI Like a Fighter Pilot', category: 'rtfm', icon: 'dashboard', description: '"If fighter pilots can land on aircraft carriers using instruments, you can read a P&L number." A zone-by-zone breakdown of every element in the GUI: the chart (candles, indicators, price lines), the sidebar (holdings, decisions, P&L), the log panel, and the controls. What healthy looks like versus what should worry you.' },
        { filename: 'RTFM/22_PAPER_TIGERS.md', title: 'Paper Tigers: Simulation & Paper Trading', category: 'rtfm', icon: 'science', description: '"Would you test a parachute by jumping off a cliff? Then don\'t test a trading strategy with real money." Everything about paper trading: what it simulates, what it doesn\'t, how the Paper Broker works, the difference between paper mode and backtesting, and the graduation checklist for going live. Plus the harsh truth about what paper trading can\'t teach you.' },
        { filename: 'RTFM/23_UPDATE_PROTOCOL.md', title: 'The Update Protocol: How the Bot Updates Itself', category: 'rtfm', icon: 'system_update', description: '"In the future, software updates itself. We\'re living in the future. It\'s terrifying." How the self-update mechanism works: git fetch, version comparison, one-click apply. What gets updated (code), what doesn\'t (your config), and why your open positions are completely safe during updates. Plus how to roll back if you don\'t like the new version.' },
        { filename: 'RTFM/24_MONEY_PSYCHOLOGY.md', title: 'Money Psychology: The 8 Emotional Traps The Bot Prevents', category: 'rtfm', icon: 'psychology_alt', description: '"The market is designed to do whatever hurts the most people." This article isn\'t about code — it\'s about you. The eight emotional traps that destroy traders: FOMO, revenge trading, sunk cost fallacy, overconfidence, analysis paralysis, anchoring bias, the \"just one more\" syndrome, and recency bias. How each one works, and how the bot\'s features specifically prevent each one.' },
        { filename: 'RTFM/25_CRYPTO_FRONTIER.md', title: 'The Crypto Frontier: The Wild West of 24/7 Markets', category: 'rtfm', icon: 'currency_bitcoin', description: '"Crypto: where stability means it only moved 8% today." How crypto trading differs from forex — 24/7 hours, extreme volatility, variable spreads, whale manipulation, and flash crashes. Crypto-optimized strategies, quantity steps, fee awareness, and why the bot uses wider stops and smaller positions for crypto. Plus the pairs you should actually trade versus the ones from Reddit.' },
        { filename: 'RTFM/26_FOREX_THEATER.md', title: 'The Forex Theater: Sessions, Spreads, and the Global Money Dance', category: 'rtfm', icon: 'public', description: '"The forex market is a theater. Three acts per day. The actors are central banks with printing presses." A full guide to the three forex sessions (Tokyo, London, New York), their personalities, best strategies for each, the London fake-out, spread economics, the dead zone, the carry trade, and a personality guide for every major currency pair. Including why NZD/USD is sensitive to dairy prices.' },
        { filename: 'RTFM/27_POSITION_ALCHEMY.md', title: 'Position Alchemy: The Art and Science of SL, TP, and Trailing Stops', category: 'rtfm', icon: 'auto_graph', description: '"The entry is science. The exit is art. The stop-loss is religion." Deep dive into every exit mechanism: ATR-based stop-losses, risk/reward take-profits, trailing stops with activation thresholds, breakeven trails, and the exit priority stack. With actual formulas, examples, and the philosophy of why exits matter more than entries.' },
        { filename: 'RTFM/28_COMPOUND_EFFECT.md', title: 'The Compound Effect: Turning 2% Into Financial Freedom', category: 'rtfm', icon: 'trending_up', description: '"Compound interest is the eighth wonder of the world." This article isn\'t about quick wins — it\'s about the math of patience. How 2% per month turns $10K into $107K over 10 years. Why consistency beats performance. The drawdown recovery math. The three enemies of compounding. The 1,000-day rule. And why the bot is designed to be a patient predator, not a frantic gambler.' },
        { filename: 'RTFM/29_DEATH_SPIRAL_DIARIES.md', title: 'The Death Spiral Diaries: 188 Trades, 3 Wins, and $17 of Pain', category: 'rtfm', icon: 'local_fire_department', description: 'A true (and tragically hilarious) account of how a stop-loss shorter than a tweet, a breakeven floor that didn\'t understand spreads, and a Python cache with commitment issues conspired to turn $135 into $118 over one Sunday night. 188 trades. 3 wins. 1.4% win rate. Lessons learned the expensive way, so you don\'t have to.' },
    ];

    try {
        ipcMain.handle('list-help-docs', async () => {
            console.log('[MAIN] list-help-docs handler called, returning', HELP_CATALOG.length, 'docs');
            return { success: true, data: HELP_CATALOG };
        });

        ipcMain.handle('read-help-doc', async (event, filename) => {
            try {
                // Security: only allow filenames from the catalog
                const valid = HELP_CATALOG.find(d => d.filename === filename);
                if (!valid) return { success: false, error: 'Invalid document' };

                const filePath = path.join(DOCS_DIR, filename);
                const resolved = path.resolve(filePath);
                if (!resolved.startsWith(path.resolve(DOCS_DIR))) {
                    return { success: false, error: 'Path traversal denied' };
                }

                if (!fs.existsSync(filePath)) {
                    return { success: false, error: `Document not found: ${resolved}` };
                }

                const content = fs.readFileSync(filePath, 'utf8');
                return { success: true, data: { filename, title: valid.title, content } };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        console.log('[MAIN] Help IPC handlers registered successfully');
    } catch (err) {
        console.error('[MAIN] FAILED to register help IPC handlers:', err);
    }

    // =============================================
    // Paper Trading Reset
    // =============================================
    const DATA_DIR = path.join(__dirname, '../../../data');

    // ── Theme persistence (filesystem-backed) ──
    const themePath = path.join(__dirname, 'theme-state.json');
    ipcMain.handle('save-theme', async (_event, themeId) => {
        try { fs.writeFileSync(themePath, JSON.stringify({ theme: themeId })); } catch (e) { }
        return true;
    });
    ipcMain.handle('get-theme', async () => {
        try {
            if (fs.existsSync(themePath)) {
                const data = JSON.parse(fs.readFileSync(themePath, 'utf8'));
                return data.theme || null;
            }
        } catch (e) { }
        return null;
    });

    ipcMain.handle('reset-paper-trading', async () => {
        console.log('[MAIN] Resetting paper trading...');

        // Step 1: Kill the bot
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "run_dev_bot[.]py"';
        await new Promise((resolve) => {
            exec(killCmd, (err) => {
                if (err && err.code !== 1) console.warn('[MAIN] Kill during reset:', err.message);
                resolve();
            });
        });

        // Wait a full 2s for the process to die and flush
        await new Promise(r => setTimeout(r, 2000));

        // Step 2: Reset paper data files
        try {
            const now = new Date().toISOString();

            // paper_state.json
            const paperState = {
                balance: 10000.0,
                positions: {},
                updated_at: now
            };
            fs.writeFileSync(path.join(DATA_DIR, 'paper_state.json'), JSON.stringify(paperState, null, 2));

            // paper_ledger.json
            const paperLedger = {
                version: 1,
                last_updated: now,
                sundown_timezone: "America/New_York",
                current_day: {
                    day_start: "",
                    pnl_realized: 0.0,
                    pnl_unrealized: 0.0,
                    trades: 0,
                    wins: 0,
                    losses: 0,
                    capital_at_start: 10000.0,
                    capital_now: 10000.0,
                    best_trade: 0.0,
                    worst_trade: 0.0,
                    by_symbol: {},
                    by_strategy: {},
                    spread_costs: 0.0,
                    trade_log: []
                },
                days: []
            };
            fs.writeFileSync(path.join(DATA_DIR, 'paper_ledger.json'), JSON.stringify(paperLedger, null, 2));

            // paper_trade_results.json
            fs.writeFileSync(path.join(DATA_DIR, 'paper_trade_results.json'), '[]');

            console.log('[MAIN] Paper trading files reset to $10,000');
        } catch (err) {
            console.error('[MAIN] Failed to reset paper files:', err.message);
            return { success: false, error: err.message };
        }

        // Step 3: Re-start the bot
        setTimeout(() => {
            ipcMain.emit('start-bot');
        }, 1000);

        return { success: true };
    });

    // =============================================
    // Self-Update via Git Pull
    // =============================================
    const REPO_ROOT = path.join(__dirname, '../../../');

    ipcMain.handle('check-for-updates', async () => {
        return new Promise((resolve) => {
            exec('git fetch origin', { cwd: REPO_ROOT }, (fetchErr) => {
                if (fetchErr) {
                    console.error('[MAIN] git fetch failed:', fetchErr.message);
                    return resolve({ available: false, error: fetchErr.message });
                }

                // Detect the remote's default branch (main for public, master for private)
                exec('git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || echo ""', { cwd: REPO_ROOT }, (brErr, brOut) => {
                    let branch = brOut.trim().replace('refs/remotes/origin/', '');
                    if (!branch) {
                        // Fallback: check if origin/main exists, else origin/master
                        exec('git rev-parse --verify origin/main 2>/dev/null && echo main || echo master', { cwd: REPO_ROOT }, (fbErr, fbOut) => {
                            branch = fbOut.trim().split('\n').pop();
                            compareWithBranch(branch, resolve);
                        });
                        return;
                    }
                    compareWithBranch(branch, resolve);
                });
            });
        });

        function compareWithBranch(branch, resolve) {
            exec(`git rev-list HEAD..origin/${branch} --count`, { cwd: REPO_ROOT }, (err, stdout) => {
                if (err) {
                    console.error('[MAIN] git rev-list failed:', err.message);
                    return resolve({ available: false, error: err.message });
                }

                const behind = parseInt(stdout.trim(), 10) || 0;
                if (behind === 0) {
                    return resolve({ available: false, behind: 0 });
                }

                exec(`git log HEAD..origin/${branch} --oneline --max-count=10`, { cwd: REPO_ROOT }, (logErr, logOut) => {
                    const summary = logErr ? '' : logOut.trim();
                    console.log(`[MAIN] Updates available: ${behind} commits behind origin/${branch}`);
                    resolve({ available: true, behind, summary, branch });
                });
            });
        }
    });

    ipcMain.handle('apply-update', async () => {
        console.log('[MAIN] Applying update...');

        // Detect the remote's default branch
        const branch = await new Promise((resolve) => {
            exec('git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || echo ""', { cwd: REPO_ROOT }, (brErr, brOut) => {
                let b = brOut.trim().replace('refs/remotes/origin/', '');
                if (!b) {
                    exec('git rev-parse --verify origin/main 2>/dev/null && echo main || echo master', { cwd: REPO_ROOT }, (fbErr, fbOut) => {
                        resolve(fbOut.trim().split('\n').pop());
                    });
                    return;
                }
                resolve(b);
            });
        });
        console.log(`[MAIN] Detected branch for update: ${branch}`);

        // Step 1: Stop bot if running
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "run_dev_bot[.]py"';
        await new Promise((resolve) => {
            exec(killCmd, (err) => {
                if (err && err.code !== 1) console.warn('[MAIN] Kill during update:', err.message);
                resolve();
            });
        });

        // Step 2: Force-reset to remote branch (download-only, no merge conflicts)
        const pullResult = await new Promise((resolve) => {
            exec(`git fetch origin ${branch} && git reset --hard origin/${branch}`, { cwd: REPO_ROOT, timeout: 30000 }, (err, stdout, stderr) => {
                if (err) {
                    console.error('[MAIN] git reset failed:', err.message);
                    return resolve({ success: false, error: stderr || err.message });
                }
                console.log('[MAIN] git reset output:', stdout.trim());
                resolve({ success: true, output: stdout.trim() });
            });
        });

        if (!pullResult.success) {
            return { success: false, error: pullResult.error };
        }

        // Step 3: Reload the Electron window (picks up new HTML/JS/CSS)
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('fromMain', {
                type: 'gui-notice',
                message: 'Update applied! Restarting bot...',
                color: 'blue'
            });

            // Small delay so the notice is visible
            await new Promise(r => setTimeout(r, 1500));
            mainWindow.reload();
        }

        // Step 4: Restart bot — kill again to be sure, wait for it to die, then start fresh
        const postKillCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "run_dev_bot[.]py"';
        await new Promise((resolve) => {
            exec(postKillCmd, () => resolve());
        });

        // Wait for the old process to fully exit
        await new Promise((resolve) => {
            let attempts = 0;
            const waitForDeath = setInterval(() => {
                exec('pgrep -f "run_dev_bot[.]py"', (err, stdout) => {
                    const stillRunning = !!(stdout && stdout.trim());
                    attempts++;
                    if (!stillRunning || attempts >= 10) {
                        clearInterval(waitForDeath);
                        resolve();
                    }
                });
            }, 500);
        });

        console.log('[MAIN] Old bot process confirmed dead. Starting fresh...');
        // Small extra delay for cleanup
        await new Promise(r => setTimeout(r, 1000));
        ipcMain.emit('start-bot');

        return { success: true, output: pullResult.output };
    });
}

// Watch profiles for external changes
function startProfilesWatcher(win) {
    if (!fs.existsSync(PROFILES_PATH)) return;

    let watchTimeout;
    fs.watch(PROFILES_PATH, (event) => {
        if (event === 'change') {
            // Debounce to avoid multiple triggers during one write
            clearTimeout(watchTimeout);
            watchTimeout = setTimeout(async () => {
                const yaml = require('js-yaml');
                try {
                    const content = fs.readFileSync(PROFILES_PATH, 'utf8');
                    const json = yaml.load(content);
                    console.log("[MAIN] Profiles YAML changed externally, notifying UI...");
                    if (win) win.webContents.send('profiles-updated', json);
                    // Also notify settings window if open
                    if (settingsWindow) settingsWindow.webContents.send('profiles-updated', json);
                } catch (e) {
                    console.error("[MAIN] Error reading profiles on change:", e);
                }
            }, 100);
        }
    });
}

// Handle Log Tailing
function startLogWatcher(win) {
    const logPath = path.join(__dirname, '../../../logs/tradebot.log');
    if (!fs.existsSync(logPath)) return;

    let fileSize = fs.statSync(logPath).size;
    const startPos = Math.max(0, fileSize - 2048);
    const stream = fs.createReadStream(logPath, { start: startPos });
    stream.on('data', (chunk) => {
        win.webContents.send('fromMain', { type: 'log-chunk', data: chunk.toString() });
    });

    fs.watchFile(logPath, { interval: 500 }, (curr, prev) => {
        if (curr.mtime <= prev.mtime) return;
        const newFileSize = curr.size;
        const sizeDiff = newFileSize - fileSize;
        if (sizeDiff <= 0) {
            fileSize = newFileSize;
            return;
        }
        const buffer = Buffer.alloc(sizeDiff);
        const fd = fs.openSync(logPath, 'r');
        fs.readSync(fd, buffer, 0, sizeDiff, fileSize);
        fs.closeSync(fd);
        fileSize = newFileSize;
        win.webContents.send('fromMain', { type: 'log-update', line: buffer.toString() });
    });
}

function checkBotStatus(win, force = false) {
    exec('pgrep -f "run_dev_bot[.]py"', (err, stdout) => {
        // More robust status check
        const isRunning = !!(stdout && stdout.trim());
        if (force || isRunning !== botRunning) {
            botRunning = isRunning;
            console.log(`[MAIN] Bot Status changed: ${botRunning ? 'RUNNING' : 'STOPPED'}`);
            if (win) win.webContents.send('bot-status', { running: botRunning });
        }
    });
}

function createSettingsWindow() {
    if (settingsWindow) {
        settingsWindow.focus();
        return;
    }

    settingsWindow = new BrowserWindow({
        width: 1615,
        height: 850,
        backgroundColor: '#020617',
        frame: false,
        resizable: true,
        icon: path.join(__dirname, 'assets/icon_robot.png'),
        webPreferences: {
            preload: path.join(__dirname, 'settings_preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
    });

    settingsWindow.loadFile('settings.html');
    settingsWindow.on('closed', () => { settingsWindow = null; });
}

function createWindow() {
    const statePath = path.join(__dirname, 'window-state.json');
    let state = { width: 1611, height: 1368 };
    try {
        if (fs.existsSync(statePath)) state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    } catch (e) { }

    const win = new BrowserWindow({
        x: state.x, y: state.y, width: state.width, height: state.height,
        resizable: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
        backgroundColor: '#020617',
        frame: false,
        icon: path.join(__dirname, 'assets/icon_robot.png'),
    });

    win.loadFile('index.html');
    mainWindow = win;

    win.on('close', () => {
        try { fs.writeFileSync(statePath, JSON.stringify(win.getBounds())); } catch (e) { }
        if (settingsWindow) {
            settingsWindow.close();
            settingsWindow = null;
        }
    });

    win.webContents.once('did-finish-load', () => {
        startLogWatcher(win);
        startProfilesWatcher(win);
        setInterval(() => checkBotStatus(win), 2000);
    });

    ipcMain.on('start-bot', async () => {
        console.log('[MAIN] Start signal received.');
        const debugLogPath = path.join(__dirname, '../../../logs/gui_start_debug.log');
        const timestamp = new Date().toISOString();
        fs.appendFileSync(debugLogPath, `[${timestamp}] START SIGNAL RECEIVED\n`);

        // 1. Check if already running
        let isStarted = await new Promise(resolve => {
            exec('pgrep -f "run_dev_bot[.]py"', (err, stdout) => {
                resolve(!!(stdout && stdout.trim()));
            });
        });

        if (isStarted) {
            console.log('[MAIN] Bot already running.');
            mainWindow.webContents.send('fromMain', { type: 'gui-notice', message: "Bot already running", color: 'teal' });
            return;
        }

        // 2. Clear old stdout log to get fresh errors
        const stdoutPath = path.join(__dirname, '../../../logs/bot_stdout.log');
        try { if (fs.existsSync(stdoutPath)) fs.truncateSync(stdoutPath); } catch (e) { }

        // 3. Command construction
        let spawnCmd = isWindows()
            ? `cd /d "${path.join(__dirname, '../../../')}" && ".venv/Scripts/python.exe" -m tradebot_sci.runtime.controller --daemon`
            : `bash "${path.join(__dirname, '../../../scripts/tradebot.sh')}" --daemon`;

        console.log(`[MAIN] Executing: ${spawnCmd}`);
        fs.appendFileSync(debugLogPath, `[${timestamp}] EXEC: ${spawnCmd}\n`);

        exec(spawnCmd, (error, stdout, stderr) => {
            if (error) {
                console.error(`[MAIN] Exec Error: ${error}`);
                mainWindow.webContents.send('fromMain', { type: 'gui-notice', message: "Start Command Failed", color: 'red' });
                return;
            }

            // 4. VERIFICATION LOOP
            // We wait and check 3 times over 6 seconds to ensure it STICKS
            let checks = 0;
            const checkInterval = setInterval(() => {
                exec('pgrep -f "run_dev_bot[.]py"', (err, stdout) => {
                    const running = !!(stdout && stdout.trim());
                    if (running) {
                        console.log('[MAIN] Verification: Bot is running.');
                        if (checks >= 2) {
                            clearInterval(checkInterval);
                            mainWindow.webContents.send('fromMain', { type: 'gui-notice', message: "Bot Started Successfully", color: 'teal' });
                            checkBotStatus(mainWindow, true);
                        }
                    } else {
                        console.error('[MAIN] Verification: Bot FAILED to stay alive.');
                        clearInterval(checkInterval);

                        // Read stdout for capture
                        let errorDetail = "Process died unexpectedly.";
                        try {
                            if (fs.existsSync(stdoutPath)) {
                                const logs = fs.readFileSync(stdoutPath, 'utf8');
                                errorDetail = logs.split('\n').filter(l => l.trim()).slice(-3).join('\n') || errorDetail;
                            }
                        } catch (e) { }

                        mainWindow.webContents.send('fromMain', {
                            type: 'gui-notice',
                            message: "Bot Startup Failed",
                            detail: errorDetail,
                            color: 'red'
                        });
                        checkBotStatus(mainWindow, true);
                    }
                    checks++;
                });
            }, 2000);
        });
    });

    ipcMain.on('stop-bot', () => {
        console.log('[MAIN] Stopping bot...');
        const cmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "run_dev_bot[.]py"';

        exec(cmd, (error) => {
            if (error && error.code !== 1 && error.code !== 128) console.error(`[MAIN] Stop error: ${error}`);
            setTimeout(() => checkBotStatus(mainWindow, true), 1000);
        });
    });

    ipcMain.on('restart-bot', () => {
        console.log('[MAIN] Restarting bot...');
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "run_dev_bot[.]py"';

        exec(killCmd, () => {
            setTimeout(() => {
                // Re-trigger start logic
                ipcMain.emit('start-bot');
            }, 2000);
        });
    });

    ipcMain.on('get-bot-status', () => { checkBotStatus(mainWindow, true); });



    ipcMain.on('minimize-window', (e) => {
        const win = BrowserWindow.fromWebContents(e.sender);
        if (win) win.minimize();
    });

    ipcMain.on('maximize-window', (e) => {
        const win = BrowserWindow.fromWebContents(e.sender);
        if (win) {
            if (win.isMaximized()) win.unmaximize();
            else win.maximize();
        }
    });

    ipcMain.on('close-window', (e) => {
        const win = BrowserWindow.fromWebContents(e.sender);
        if (win) win.close();
    });

    ipcMain.on('open-settings', () => createSettingsWindow());
    ipcMain.on('close-settings', () => { if (settingsWindow) settingsWindow.close(); });

    ipcMain.on('log-notice', (event, { message, color }) => {
        const timestamp = new Date().toISOString();
        const logMsg = `[GUI-NOTICE] [${timestamp}] ${message} (${color})\n`;
        const debugLogPath = path.join(__dirname, '../../../logs/gui_notices.log');
        try {
            fs.appendFileSync(debugLogPath, logMsg);
        } catch (e) {
            console.error("Failed to write gui notice:", e);
        }
        // Echo to all windows
        BrowserWindow.getAllWindows().forEach(win => {
            win.webContents.send('fromMain', { type: 'gui-notice', message, color, timestamp });
        });
    });
}

app.whenReady().then(() => {
    setupIpcHandlers();
    createWindow();
    startProfilesWatcher(null); // Will be attached in createWindow
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
