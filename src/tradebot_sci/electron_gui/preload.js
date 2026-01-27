const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    // Basic IPC
    send: (channel, data) => {
        let validChannels = ["toMain", "start-bot", "stop-bot", "minimize-window", "maximize-window", "close-window", "open-settings", "get-bot-status"];
        if (validChannels.includes(channel)) {
            ipcRenderer.send(channel, data);
        }
    },
    on: (channel, func) => {
        let validChannels = ["fromMain", "bot-status", "env-updated"];
        if (validChannels.includes(channel)) {
            ipcRenderer.on(channel, (event, ...args) => func(...args));
        }
    },
    // Analytics IPC (invoke for async responses)
    getTradeHistory: (filter) => ipcRenderer.invoke('get-trade-history', filter),
    getAnalyticsSummary: (filter) => ipcRenderer.invoke('get-analytics-summary', filter),
    getLogFiles: () => ipcRenderer.invoke('get-log-files'),
    onEnvUpdated: (callback) => ipcRenderer.on('env-updated', (event, data) => callback(data)),
});

// We can also expose specific APIs for the backend connection if needed
// e.g. WebSocket management
