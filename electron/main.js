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

    if (process.platform === 'win32') {
        return path.join(base, 'app', 'app', 'app.exe');
    }

    if (process.platform === 'darwin') {
        const macDir = path.join(base, 'app-mac');
        const arch = process.arch;
        const armPath = path.join(macDir, 'app_mac_bin_arm64');
        const x64Path = path.join(macDir, 'app_mac_bin_x86_64');

        if (arch === 'arm64' && fs.existsSync(armPath)) return armPath;
        if (fs.existsSync(x64Path)) return x64Path;

        throw new Error(`No valid macOS binary found for architecture: ${arch}`);
    }

    if (process.platform === 'linux') {
        return path.join(base, 'app-linux', 'app_linux_bin');
    }

    throw new Error(`Unsupported platform: ${process.platform}`);
}


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
    // 🟢 1. Show splash screen right away
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

    const flaskStartupTimeout = setTimeout(() => {
        console.error("Flask startup timed out");
        splash.loadURL('data:text/html,<h1>Backend timed out</h1>');
        setTimeout(() => app.quit(), 5000);
    }, 20000); // 20s

    const flaskPath = getFlaskBinary();

    if (!fs.existsSync(flaskPath)) {
        console.error("Flask binary not found at:", flaskPath);
        splash.loadURL('data:text/html,<h1>Backend not found</h1>');
        setTimeout(() => app.quit(), 3000);
        return;
    }

    flaskProcess = spawn(flaskPath, [], {
        shell: true,
        stdio: 'inherit',
        windowsHide: true
    });

    flaskProcess.on('error', err => {
        console.error("Failed to start Flask process:", err);
        splash.loadURL('data:text/html,<h1>Flask failed to start</h1>');
        setTimeout(() => app.quit(), 3000);
    });

    waitForFlask()
        .then(() => {
            clearTimeout(flaskStartupTimeout);
            createWindow();
        })
        .catch(err => {
            clearTimeout(flaskStartupTimeout);
            console.error("Flask never came online:", err);
            if (splash) {
                splash.loadURL(`data:text/html,<h1>Backend failed</h1><p>${err.message}</p>`);
            }
            setTimeout(() => app.quit(), 5000);
        });
});

function shutdown() {
    if (flaskProcess) {
        const req = http.request({
            hostname: 'localhost',
            port: 5000,
            path: '/shutdown',
            method: 'POST'
        }, res => {
            console.log(`Flask shutdown response: ${res.statusCode}`);
            flaskProcess = null;
        });

        req.on('error', (err) => {
            console.error("Error shutting down Flask:", err);
            flaskProcess.kill();
            flaskProcess = null;
        });

        req.end();
    }
}

app.on('will-quit', shutdown);
app.on('window-all-closed', () => {
    shutdown();
    if (process.platform !== 'darwin') app.quit();
});
