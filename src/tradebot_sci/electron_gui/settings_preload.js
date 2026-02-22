const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // Legacy env/YAML methods (kept for backwards compatibility)
    readEnv: () => ipcRenderer.invoke('read-env'),
    saveEnv: (updates) => ipcRenderer.invoke('save-env', updates),
    readProfiles: () => ipcRenderer.invoke('read-profiles'),
    saveProfiles: (content) => ipcRenderer.invoke('save-profiles', content),
    readProfilesJson: () => ipcRenderer.invoke('read-profiles-json'),
    saveProfilesJson: (data) => ipcRenderer.invoke('save-profiles-json', data),
    resolveCity: (cityName) => ipcRenderer.invoke('resolve-city', cityName),
    readProfileStrategies: (profileName) => ipcRenderer.invoke('read-profile-strategies', profileName),
    saveProfileStrategies: (profileName, strategies) => ipcRenderer.invoke('save-profile-strategies', profileName, strategies),
    closeSettings: () => ipcRenderer.send('close-settings'),
    minimizeWindow: () => ipcRenderer.send('minimize-window'),
    maximizeWindow: () => ipcRenderer.send('maximize-window'),
    closeWindow: () => ipcRenderer.send('close-window'),
    onEnvUpdated: (callback) => ipcRenderer.on('env-updated', (event, data) => callback(data)),
    onProfilesUpdated: (callback) => ipcRenderer.on('profiles-updated', (event, data) => callback(data)),

    // NEW: Unified config.json API
    readConfig: () => ipcRenderer.invoke('read-config'),
    saveConfig: (config) => ipcRenderer.invoke('save-config', config),
    readSecrets: () => ipcRenderer.invoke('read-secrets'),
    saveSecrets: (secrets) => ipcRenderer.invoke('save-secrets', secrets),
    onConfigUpdated: (callback) => ipcRenderer.on('config-updated', (event, data) => callback(data)),

    // Bot Lifecycle Controls
    startBot: () => ipcRenderer.send('start-bot'),
    stopBot: () => ipcRenderer.send('stop-bot'),
    restartBot: () => ipcRenderer.send('restart-bot'),
    getBotStatus: () => ipcRenderer.send('get-bot-status'),
    onBotStatus: (callback) => ipcRenderer.on('bot-status', (event, data) => callback(data)),

    // AI Optimize
    aiRecommend: (profileName) => ipcRenderer.invoke('ai-recommend', profileName),
});
