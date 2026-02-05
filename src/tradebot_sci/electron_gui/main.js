const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');
const logParser = require('./log_parser');

let mainWindow;
let settingsWindow;
let botRunning = false;

// Helper to determine OS
const isWindows = () => process.platform === 'win32';

// Helper to find repo root reliably
const DOTENV_PATH = path.join(__dirname, '../../../.env');
const PROFILES_PATH = path.join(__dirname, '../../../config/settings_profiles.yaml');

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
    exec('pgrep -f run_dev_bot.py', (err, stdout) => {
        // [ANTIGRAVITY FIX] More robust status check
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
        icon: path.join(__dirname, 'assets/stitch_avatar.png'),
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

    ipcMain.on('start-bot', () => {
        console.log('[MAIN] Start signal received.');

        // Define Command based on OS
        let spawnCmd = '';
        if (isWindows()) {
            // Windows: Use python directly from root
            // We assume 'python' is in PATH or .venv is active in this session (unlikely in GUI spawn)
            // Best bet: Try ".venv\Scripts\python" then "python"
            const venvPy = path.join(__dirname, '../../../.venv/Scripts/python.exe');
            const targetScript = "tradebot_sci.runtime.controller"; // Module execution

            // Note: We need to set cwd to project root for module import to work
            const projectRoot = path.join(__dirname, '../../../');

            const pyExe = fs.existsSync(venvPy) ? `"${venvPy}"` : "python";

            // Construct command: python -m tradebot_sci.runtime.controller --daemon
            spawnCmd = `cd /d "${projectRoot}" && ${pyExe} -m ${targetScript} --daemon`;
        } else {
            const scriptPath = path.join(__dirname, '../../../scripts/tradebot.sh');
            spawnCmd = `bash "${scriptPath}" --daemon`;
        }

        // Check status first
        checkBotStatus(null, true); // Update state internally
        if (botRunning) {
            console.log('[MAIN] Bot seems running. Ignoring start.');
            return;
        }

        console.log(`[MAIN] Starting bot with: ${spawnCmd}`);
        const botProcess = exec(spawnCmd, (error, stdout, stderr) => {
            if (error) console.error(`[MAIN] Start error: ${error}`);
            if (stdout) console.log(`[MAIN] Start stdout: ${stdout}`);
            if (stderr) console.error(`[MAIN] Start stderr: ${stderr}`);
            setTimeout(() => checkBotStatus(mainWindow, true), 3000);
        });
    });

    ipcMain.on('stop-bot', () => {
        console.log('[MAIN] Stopping bot...');
        const cmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f run_dev_bot.py';

        exec(cmd, (error) => {
            if (error && error.code !== 1 && error.code !== 128) console.error(`[MAIN] Stop error: ${error}`);
            setTimeout(() => checkBotStatus(mainWindow, true), 1000);
        });
    });

    ipcMain.on('restart-bot', () => {
        console.log('[MAIN] Restarting bot...');
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f run_dev_bot.py';

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
}

app.whenReady().then(() => {
    setupIpcHandlers();
    createWindow();
    startProfilesWatcher(null); // Will be attached in createWindow
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
