const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

let mainWindow;
let settingsWindow;
let botRunning = false;

// Helper to find repo root reliably
const DOTENV_PATH = path.join(__dirname, '../../../.env');
const PROFILES_PATH = path.join(__dirname, '../../../config/settings_profiles.yaml');

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

// City / Location Resolver (Ported Logic)
ipcMain.handle('resolve-city', async (event, cityName) => {
    // Simple mock or mapping based on QT logic 'Resolve'
    // In a real app, this might call a geocoding API.
    // For now, we mimic the QT behavior of resolving common US cities.
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
        const isRunning = !!stdout.trimmed || !!stdout.trim();
        if (force || isRunning !== botRunning) {
            botRunning = isRunning;
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
        width: 1100,
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
    });

    win.loadFile('index.html');
    mainWindow = win;

    win.on('close', () => {
        try { fs.writeFileSync(statePath, JSON.stringify(win.getBounds())); } catch (e) { }
    });

    win.webContents.once('did-finish-load', () => {
        startLogWatcher(win);
        setInterval(() => checkBotStatus(win), 2000);
    });

    ipcMain.on('start-bot', () => {
        exec('bash scripts/tradebot.sh --gui --daemon');
    });

    ipcMain.on('stop-bot', () => {
        exec('pkill -f run_dev_bot.py');
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

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
