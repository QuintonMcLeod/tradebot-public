const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow;

const { exec } = require('child_process');

let botRunning = false;

// Handle Log Tailing
function startLogWatcher(win) {
    const logPath = path.join(__dirname, '../../../logs/tradebot.log');

    console.log("Looking for log file at:", logPath);

    if (!fs.existsSync(logPath)) {
        console.error("Log file not found:", logPath);
        return;
    }

    let fileSize = fs.statSync(logPath).size;

    // Initial read of last 2KB to populate
    const startPos = Math.max(0, fileSize - 2048);
    const stream = fs.createReadStream(logPath, { start: startPos });
    stream.on('data', (chunk) => {
        win.webContents.send('fromMain', { type: 'log-chunk', data: chunk.toString() });
    });

    // Watch for updates
    fs.watchFile(logPath, { interval: 500 }, (curr, prev) => {
        if (curr.mtime <= prev.mtime) return;

        const newFileSize = curr.size;
        const sizeDiff = newFileSize - fileSize;

        if (sizeDiff <= 0) {
            fileSize = newFileSize; // Log rotated or truncated
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
        const isRunning = !!stdout.trim();
        if (force || isRunning !== botRunning) {
            botRunning = isRunning;
            if (win) win.webContents.send('bot-status', { running: botRunning });
        }
    });
}

function createWindow() {
    const statePath = path.join(__dirname, 'window-state.json');
    let state = { width: 1611, height: 1368 };

    try {
        if (fs.existsSync(statePath)) {
            state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
        }
    } catch (e) {
        console.error("Failed to load window state:", e);
    }

    const win = new BrowserWindow({
        x: state.x,
        y: state.y,
        width: state.width,
        height: state.height,
        resizable: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: true,
            contextIsolation: false,
        },
        backgroundColor: '#0f172a',
        titleBarStyle: 'hidden',
    });

    win.loadFile('index.html');
    mainWindow = win;

    // Save state on close
    win.on('close', () => {
        try {
            const bounds = win.getBounds();
            fs.writeFileSync(statePath, JSON.stringify(bounds));
        } catch (e) {
            console.error("Failed to save window state:", e);
        }
    });

    // Start watching logs when window is ready
    win.webContents.once('did-finish-load', () => {
        startLogWatcher(win);
        setInterval(() => checkBotStatus(win), 2000);
    });

    // Handle Start Bot
    ipcMain.on('start-bot', () => {
        console.log("Starting Bot (Daemon mode)...");
        // We use --gui --daemon so it loads the env and bot but skips launching another Electron
        exec('bash scripts/tradebot.sh --gui --daemon', (err, stdout, stderr) => {
            if (err) {
                console.error("Start Bot Error:", err);
                return;
            }
            console.log("Start Bot Output:", stdout);
        });
    });

    // Handle Stop Bot
    ipcMain.on('stop-bot', () => {
        console.log("Stopping Bot...");
        exec('pkill -f run_dev_bot.py', (err) => {
            if (err) console.error("Stop Bot Error:", err);
        });
    });

    // Handle initial status request
    ipcMain.on('get-bot-status', (event) => {
        checkBotStatus(mainWindow, true);
    });
}

app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});
