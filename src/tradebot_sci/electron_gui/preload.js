const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    // Basic IPC
    send: (channel, data) => {
        let validChannels = ["toMain", "start-bot", "stop-bot", "minimize-window", "maximize-window", "close-window", "open-settings", "get-bot-status", "update-active-profile"];
        if (validChannels.includes(channel)) {
            ipcRenderer.send(channel, data);
        }
    },
    on: (channel, func) => {
        let validChannels = ["fromMain", "bot-status", "env-updated", "config-updated", "bot-restarted"];
        if (validChannels.includes(channel)) {
            // Wrap func so we can map it back for removeListener
            const wrapper = (event, ...args) => func(...args);
            if (!func._ipcWrappers) func._ipcWrappers = {};
            func._ipcWrappers[channel] = wrapper;
            ipcRenderer.on(channel, wrapper);
        }
    },
    removeListener: (channel, func) => {
        if (func._ipcWrappers && func._ipcWrappers[channel]) {
            ipcRenderer.removeListener(channel, func._ipcWrappers[channel]);
            delete func._ipcWrappers[channel];
        }
    },
    // Analytics IPC (invoke for async responses)
    getTradeHistory: (filter, paperMode) => ipcRenderer.invoke('get-trade-history', filter, paperMode),
    getAnalyticsSummary: (filter, paperMode) => ipcRenderer.invoke('get-analytics-summary', filter, paperMode),
    getLogFiles: () => ipcRenderer.invoke('get-log-files'),
    onEnvUpdated: (callback) => ipcRenderer.on('env-updated', (event, data) => callback(data)),

    // Profiles IPC (legacy - kept for backwards compatibility)
    readProfiles: () => ipcRenderer.invoke('read-profiles'),
    saveProfiles: (content) => ipcRenderer.invoke('save-profiles', content),
    readProfilesJson: () => ipcRenderer.invoke('read-profiles-json'),
    saveProfilesJson: (data) => ipcRenderer.invoke('save-profiles-json', data),
    onProfilesUpdated: (callback) => ipcRenderer.on('profiles-updated', (event, data) => callback(data)),

    // NEW: Unified config.json API
    readConfig: () => ipcRenderer.invoke('read-config'),
    saveConfig: (config) => ipcRenderer.invoke('save-config', config),
    readSecrets: () => ipcRenderer.invoke('read-secrets'),
    saveSecrets: (secrets) => ipcRenderer.invoke('save-secrets', secrets),
    onConfigUpdated: (callback) => ipcRenderer.on('config-updated', (event, data) => callback(data)),

    // NEW: UI Layout API
    readUiLayouts: () => ipcRenderer.invoke('read-ui-layouts'),
    saveUiLayouts: (layouts) => ipcRenderer.invoke('save-ui-layouts', layouts),

    // Settings IPC (legacy - kept for backwards compatibility)
    readEnv: () => ipcRenderer.invoke('read-env'),
    saveEnv: (updates) => ipcRenderer.invoke('save-env', updates),
    resolveCity: (cityName) => ipcRenderer.invoke('resolve-city', cityName),
    readProfileStrategies: (profileName) => ipcRenderer.invoke('read-profile-strategies', profileName),
    saveProfileStrategies: (profileName, strategies) => ipcRenderer.invoke('save-profile-strategies', profileName, strategies),
    startBot: (opts) => ipcRenderer.send('start-bot', opts),
    stopBot: () => ipcRenderer.send('stop-bot'),
    restartBot: () => ipcRenderer.send('restart-bot'),
    getBotStatus: () => ipcRenderer.send('get-bot-status'),
    onBotStatus: (callback) => ipcRenderer.on('bot-status', (event, data) => callback(data)),
    logNotice: (message, color) => ipcRenderer.send('log-notice', { message, color }),

    getMOTD: () => ipcRenderer.invoke('get-motd'),
    // Generic invoke for flexibility
    invoke: (channel, ...args) => ipcRenderer.invoke(channel, ...args),

    // Self-Update
    checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
    applyUpdate: () => ipcRenderer.invoke('apply-update'),

    // Paper Trading Reset
    resetPaperTrading: () => ipcRenderer.invoke('reset-paper-trading'),

    // Help Documentation
    listHelpDocs: () => ipcRenderer.invoke('list-help-docs'),
    readHelpDoc: (filename) => ipcRenderer.invoke('read-help-doc', filename),

    // Replay Backtest — live streaming
    onBacktestProgress: (callback) => ipcRenderer.on('backtest-progress', (_event, line) => callback(line)),
    offBacktestProgress: () => ipcRenderer.removeAllListeners('backtest-progress'),
});

// We can also expose specific APIs for the backend connection if needed
// e.g. WebSocket management
