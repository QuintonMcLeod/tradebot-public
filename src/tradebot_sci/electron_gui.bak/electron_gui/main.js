const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow;

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

function createWindow() {
    const win = new BrowserWindow({
        width: 1600,
        height: 900,
        resizable: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false, // Security best practice
            contextIsolation: true,
        },
        backgroundColor: '#0f172a', // Match theme
        titleBarStyle: 'hidden', // Custom title bar if desired
    });

    win.loadFile('index.html');
    mainWindow = win;

    // Start watching logs when window is ready
    win.webContents.once('did-finish-load', () => {
        startLogWatcher(win);
    });

    // Open DevTools for debugging
    // win.webContents.openDevTools({ mode: 'detach' });
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
