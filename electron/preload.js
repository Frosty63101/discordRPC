// The renderer only gets explicit desktop capabilities, not unrestricted IPC.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
    setPreferences: (preferences) => ipcRenderer.invoke('app:set-preferences', {
        minimizeToTray: Boolean(preferences.minimizeToTray),
        minimizeOnMinimize: Boolean(preferences.minimizeOnMinimize),
        startOnStartup: Boolean(preferences.startOnStartup),
    }),
    quit: () => ipcRenderer.send('force-quit'),
});
