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
    // [ANTIGRAVITY] Self-Update via Git Pull
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

        // Step 2: Git pull using detected branch
        const pullResult = await new Promise((resolve) => {
            exec(`git pull --ff-only origin ${branch}`, { cwd: REPO_ROOT, timeout: 30000 }, (err, stdout, stderr) => {
                if (err) {
                    console.error('[MAIN] git pull failed:', err.message);
                    return resolve({ success: false, error: stderr || err.message });
                }
                console.log('[MAIN] git pull output:', stdout.trim());
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
                message: 'Update applied! Reloading...',
                color: 'blue'
            });

            // Small delay so the notice is visible
            await new Promise(r => setTimeout(r, 1500));
            mainWindow.reload();
        }

        // Step 4: Restart bot after UI reload settles
        setTimeout(() => {
            ipcMain.emit('start-bot');
        }, 4000);

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
        icon: path.join(__dirname, 'assets/icon.png'),
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
        icon: path.join(__dirname, 'assets/icon.png'),
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

    ipcMain.on('restart-bot', () => {
        console.log('[MAIN] Restarting bot due to settings change...');
        exec('pkill -f run_dev_bot.py', () => {
            // Wait a moment for process to die
            setTimeout(() => {
                exec('bash scripts/tradebot.sh --gui --daemon');
            }, 1000);
        });
    });

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
