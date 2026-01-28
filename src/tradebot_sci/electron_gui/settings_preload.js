const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    readEnv: () => ipcRenderer.invoke('read-env'),
    saveEnv: (updates) => ipcRenderer.invoke('save-env', updates),
    readProfiles: () => ipcRenderer.invoke('read-profiles'),
    saveProfiles: (content) => ipcRenderer.invoke('save-profiles', content),
    resolveCity: (cityName) => ipcRenderer.invoke('resolve-city', cityName),
    readProfileStrategies: (profileName) => ipcRenderer.invoke('read-profile-strategies', profileName),
    saveProfileStrategies: (profileName, strategies) => ipcRenderer.invoke('save-profile-strategies', profileName, strategies),
    closeSettings: () => ipcRenderer.send('close-settings'),
    minimizeWindow: () => ipcRenderer.send('minimize-window'),
    maximizeWindow: () => ipcRenderer.send('maximize-window'),
    closeWindow: () => ipcRenderer.send('close-window'),
    onEnvUpdated: (callback) => ipcRenderer.on('env-updated', (event, data) => callback(data)),

    // Bot Lifecycle Controls
    startBot: () => ipcRenderer.send('start-bot'),
    stopBot: () => ipcRenderer.send('stop-bot'),
    restartBot: () => ipcRenderer.send('restart-bot'),
    getBotStatus: () => ipcRenderer.send('get-bot-status'),
    onBotStatus: (callback) => ipcRenderer.on('bot-status', (event, data) => callback(data)),
});
