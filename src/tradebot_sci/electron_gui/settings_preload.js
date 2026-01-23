const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    readEnv: () => ipcRenderer.invoke('read-env'),
    saveEnv: (updates) => ipcRenderer.invoke('save-env', updates),
    readProfiles: () => ipcRenderer.invoke('read-profiles'),
    saveProfiles: (content) => ipcRenderer.invoke('save-profiles', content),
    resolveCity: (cityName) => ipcRenderer.invoke('resolve-city', cityName),
    closeSettings: () => ipcRenderer.send('close-settings'),
    minimizeWindow: () => ipcRenderer.send('minimize-window'),
    maximizeWindow: () => ipcRenderer.send('maximize-window'),
    closeWindow: () => ipcRenderer.send('close-window'),
});
