const path = require('path');
const fs = require('fs');
const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const http = require('http');

let flaskProcess;
let splash;
let mainWindow;

function getFlaskBinary() {
    const base = path.join(__dirname, '..', 'build');
    switch (process.platform) {
        case 'win32':
            return path.join(base, 'app', 'app', 'app.exe');
        case 'darwin':
            return path.join(base, 'app-mac', 'app_mac_bin'); // match PyInstaller output
        case 'linux':
            return path.join(base, 'app-linux', 'app_linux_bin'); // match PyInstaller output
        default:
            throw new Error("Unsupported OS");
    }
}

const flaskStartupTimeout = setTimeout(() => {
    console.error("Flask startup timed out");
    splash.loadURL('data:text/html,<h1>Backend timed out</h1>');
    setTimeout(() => app.quit(), 5000);
}, 10000); // 10s

function waitForFlask(retries = 50) {
    return new Promise((resolve, reject) => {
        const interval = setInterval(() => {
            console.log(`Waiting for Flask... (${retries} retries left)`);
            http.get('http://localhost:5000/api/hello', res => {
                if (res.statusCode === 200) {
                    console.log("Flask responded successfully");
                    clearInterval(interval);
                    resolve();
                }
            }).on('error', () => {
                if (--retries <= 0) {
                    clearInterval(interval);
                    reject(new Error("Flask failed to start"));
                }
            });
        }, 200);
    });
}


function createWindow() {
    // Splash screen
    splash = new BrowserWindow({
        width: 400,
        height: 300,
        frame: false,
        alwaysOnTop: true,
        transparent: false,
        resizable: false,
        show: false
    });
    
    splash.loadFile(path.resolve(__dirname, '..', 'frontend', 'public', 'splash.html'));
    splash.once('ready-to-show', () => splash.show());

    // Main app window
    mainWindow = new BrowserWindow({
        width: 800,
        height: 600,
        show: false,
        webPreferences: { nodeIntegration: false }
    });

    mainWindow.loadFile(path.resolve(__dirname, '..', 'frontend', 'build', 'index.html'));

    mainWindow.once('ready-to-show', () => {
        if (splash) splash.close();
        mainWindow.show();
    });
}

app.whenReady().then(() => {
    const flaskPath = getFlaskBinary();

    if (!fs.existsSync(flaskPath)) {
        console.error("Flask binary not found at:", flaskPath);
        app.quit();
        return;
    }

    flaskProcess = spawn(flaskPath, [], {
        shell: true,
        stdio: 'inherit',
        windowsHide: true
    });

    flaskProcess.on('error', err => {
        console.error("Failed to start Flask process:", err);
        app.quit();
    });

    waitForFlask()
        .then(() => {
            clearTimeout(flaskStartupTimeout);
            createWindow();
        })
        .catch(err => {
            clearTimeout(flaskStartupTimeout);
            console.error("Flask never came online:", err);
            splash.loadURL('data:text/html,<h1>Backend failed to start</h1><p>' + err.message + '</p>');
            setTimeout(() => app.quit(), 5000);
        });
});

function shutdown() {
    if (flaskProcess) {
        flaskProcess.kill();
        flaskProcess = null;
    }
}

app.on('will-quit', shutdown);
app.on('window-all-closed', () => {
    shutdown();
    if (process.platform !== 'darwin') app.quit();
    if (flaskProcess) {
        flaskProcess.kill();
        flaskProcess = null;
    }
});
