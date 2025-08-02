const path = require('path');
const fs = require('fs');
const { app, BrowserWindow, Tray, Menu } = require('electron');
const { spawn, spawnSync } = require('child_process');
const http = require('http');

let flaskProcess = null;
let splash = null;
let mainWindow = null;
let tray = null;

// Only allow one instance
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    app.quit();
}

// Check Rosetta (macOS)
let rosettaAvailable = null;
function isRosettaInstalled() {
    if (rosettaAvailable !== null) return rosettaAvailable;
    try {
        const res = spawnSync('arch', ['-x86_64', 'true']);
        rosettaAvailable = res.status === 0;
    } catch {
        rosettaAvailable = false;
    }
    return rosettaAvailable;
}

// Determine binary path
function getFlaskBinary() {
    const base = path.join(__dirname, '..', 'build');

    if (process.platform === 'win32') {
        return { binaryPath: path.join(base, 'app', 'app', 'app.exe'), archPrefix: null };
    }

    if (process.platform === 'darwin') {
        const armPath = path.join(base, 'app-mac-arm64', 'app_mac_bin_arm64');
        const x64Path = path.join(base, 'app-mac-x86_64', 'app_mac_bin_x86_64');
        const arch = process.arch;

        if (arch === 'arm64') {
            if (fs.existsSync(armPath)) return { binaryPath: armPath, archPrefix: null };
            if (fs.existsSync(x64Path) && isRosettaInstalled()) return { binaryPath: x64Path, archPrefix: 'arch' };
        }

        if (fs.existsSync(x64Path)) return { binaryPath: x64Path, archPrefix: null };
        throw new Error(`No valid macOS binary found for architecture: ${arch}`);
    }

    if (process.platform === 'linux') {
        return { binaryPath: path.join(base, 'app-linux', 'app_linux_bin'), archPrefix: null };
    }

    throw new Error(`Unsupported platform: ${process.platform}`);
}

// Load JSON config from user dir
function loadLocalConfig() {
    const home = process.env[process.platform === "win32" ? "USERPROFILE" : "HOME"];
    const configPath = path.join(home, ".config", "app_config.json");
    if (fs.existsSync(configPath)) {
        try {
            return JSON.parse(fs.readFileSync(configPath, "utf-8"));
        } catch (e) {
            console.error("Failed to parse config:", e);
        }
    }
    return {};
}
const config = loadLocalConfig();

// Start the app
app.whenReady().then(() => {
    createSplash();

    const { binaryPath, archPrefix } = getFlaskBinary();
    if (!fs.existsSync(binaryPath)) {
        splash.loadURL(`data:text/html,<h1>Backend not found</h1><p>${binaryPath}</p>`);
        return setTimeout(() => app.quit(), 5000);
    }

    const args = archPrefix === 'arch' ? ['-x86_64', binaryPath] : [binaryPath];

    flaskProcess = spawn(archPrefix || args[0], archPrefix ? args.slice(1) : [], {
        shell: true,
        stdio: 'inherit',
        windowsHide: true
    });

    flaskProcess.on('error', err => {
        console.error("Flask failed:", err);
        const msg = archPrefix
            ? `<h1>Rosetta 2 Required</h1><p>Run: <code>softwareupdate --install-rosetta</code></p>`
            : "<h1>Flask failed to start</h1>";
        splash.loadURL(`data:text/html,${encodeURIComponent(msg)}`);
        setTimeout(() => app.quit(), 6000);
    });

    waitForFlask()
        .then(() => {
            createMainWindow();
        })
        .catch(err => {
            console.error("Flask never came online:", err);
            splash.loadURL(`data:text/html,<h1>Backend failed</h1><p>${err.message}</p>`);
            setTimeout(() => app.quit(), 5000);
        });
});

function createSplash() {
    splash = new BrowserWindow({
        width: 400,
        height: 300,
        frame: false,
        alwaysOnTop: true,
        resizable: false,
        show: false,
    });
    splash.loadFile(path.resolve(__dirname, '..', 'frontend', 'public', 'splash.html'));
    splash.once('ready-to-show', () => splash.show());
}

function waitForFlask(retries = 50) {
    return new Promise((resolve, reject) => {
        const interval = setInterval(() => {
            console.log(`Waiting for Flask... (${retries} retries left)`);
            http.get('http://localhost:5000/api/hello', res => {
                if (res.statusCode === 200) {
                    clearInterval(interval);
                    resolve();
                }
            }).on('error', () => {
                if (--retries <= 0) {
                    clearInterval(interval);
                    reject(new Error("Flask failed to respond"));
                }
            });
        }, 200);
    });
}

function createMainWindow() {
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

    mainWindow.on('close', (e) => {
        if (config.minimizeToTray) {
            e.preventDefault();
            mainWindow.hide();
        }
    });

    setupTray();
}

function setupTray() {
    let trayIcon = path.join(__dirname, 'iconTemplate.png');
    if (!fs.existsSync(trayIcon)) trayIcon = undefined;

    tray = new Tray(trayIcon);
    const contextMenu = Menu.buildFromTemplate([
        { label: 'Show App', click: () => mainWindow.show() },
        { label: 'Quit', click: () => { shutdown(); app.quit(); } }
    ]);
    tray.setToolTip('Goodreads Discord RPC');
    tray.setContextMenu(contextMenu);
    tray.on('double-click', () => mainWindow.show());
}

function shutdown() {
    if (flaskProcess) {
        const req = http.request({
            hostname: 'localhost',
            port: 5000,
            path: '/shutdown',
            method: 'POST'
        }, res => {
            console.log(`Flask shutdown response: ${res.statusCode}`);
        });

        req.on('error', (err) => {
            console.error("Flask shutdown failed:", err);
            flaskProcess.kill();
        });

        req.end();
        flaskProcess = null;
    }
}

// Handle graceful exits
app.on('will-quit', shutdown);
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
app.on('second-instance', () => {
    if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
    }
});
