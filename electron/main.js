const path = require('path');
const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');

function getFlaskBinary() {
    const base = path.join(__dirname, 'backend', 'dist');
    switch (process.platform) {
        case 'win32': return path.join(base, 'app', 'app.exe');
        case 'darwin': return path.join(base, 'app-mac', 'app-mac');
        case 'linux': return path.join(base, 'app-linux', 'app-linux');
    }
}

let flaskProcess;

function createWindow() {
    const win = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: { nodeIntegration: false }
    });

    win.loadFile(path.join(__dirname, 'frontend', 'build', 'index.html'));
}

app.whenReady().then(() => {
    flaskProcess = spawn(getFlaskBinary(), [], { shell: true, stdio: 'inherit' });
    createWindow();
});

app.on('will-quit', () => {
    if (flaskProcess) flaskProcess.kill();
});
