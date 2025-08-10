const path = require('path');
const fs = require('fs');
const { app, BrowserWindow, Tray, Menu, ipcMain, dialog } = require('electron');
const { spawn, spawnSync } = require('child_process');
const http = require('http');

let flaskProcess = null;
let splash = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let backendReady = false;

// --- single instance guard ---
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    app.quit();
}
app.on('second-instance', () => {
    if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();
    }
});

// --- crash guards ---
process.on('uncaughtException', (err) => {
    console.error('[uncaughtException]', err);
});
process.on('unhandledRejection', (reason) => {
    console.error('[unhandledRejection]', reason);
});

// --- Rosetta check (mac) ---
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

// --- resolve backend ---
function getFlaskBinary() {
    const base = path.join(__dirname, '..', 'build');

    if (process.platform === 'win32') {
        return { binaryPath: path.join(base, 'app', 'app', 'app.exe'), launcher: null, args: [] };
    }

    if (process.platform === 'darwin') {
        const armPath = path.join(base, 'app-mac-arm64', 'app_mac_bin_arm64');
        const x64Path = path.join(base, 'app-mac-x86_64', 'app_mac_bin_x86_64');
        const arch = process.arch;

        if (arch === 'arm64') {
            if (fs.existsSync(armPath)) return { binaryPath: armPath, launcher: null, args: [] };
            if (fs.existsSync(x64Path) && isRosettaInstalled()) {
                return { binaryPath: x64Path, launcher: 'arch', args: ['-x86_64', x64Path] };
            }
        }
        if (fs.existsSync(x64Path)) return { binaryPath: x64Path, launcher: null, args: [] };
        throw new Error(`No valid macOS binary found for architecture: ${arch}`);
    }

    if (process.platform === 'linux') {
        return { binaryPath: path.join(base, 'app-linux', 'app_linux_bin'), launcher: null, args: [] };
    }

    throw new Error(`Unsupported platform: ${process.platform}`);
}

// --- load config from user dir for minimizeToTray on first boot ---
function loadLocalConfig() {
    try {
        const home = process.env[process.platform === 'win32' ? 'USERPROFILE' : 'HOME'];
        const configPath = path.join(home, '.config', 'app_config.json');
        if (fs.existsSync(configPath)) {
            return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
        }
    } catch (e) {
        console.error('Failed to parse local config:', e);
    }
    return {};
}
const localConfig = loadLocalConfig();

// --- app lifecycle ---
app.whenReady().then(async () => {
    try {
        createSplash();
        await launchBackendWithRetries(); // keep app alive; no auto-quit
        await waitForFlask();
        backendReady = true;
        createMainWindow();
    } catch (err) {
        // Don’t die — show actionable error and keep tray so user can Quit
        console.error('Backend failed to come online:', err);
        showSplashError(err);
        setupTray(); // allow user to quit from tray
    }
});

// --- splash ---
function createSplash() {
    try {
        splash = new BrowserWindow({
            width: 420,
            height: 320,
            frame: false,
            alwaysOnTop: true,
            resizable: false,
            show: false,
        });
        const splashPath = path.resolve(__dirname, '..', 'frontend', 'public', 'splash.html');
        if (fs.existsSync(splashPath)) {
            splash.loadFile(splashPath);
        } else {
            splash.loadURL('data:text/html,<h2>Starting…</h2>');
        }
        splash.once('ready-to-show', () => splash.show());
    } catch (e) {
        console.error('Failed to create splash:', e);
    }
}

function showSplashError(err) {
    const html = `
        <h1>Backend failed to start</h1>
        <pre>${(err && err.message) ? err.message : String(err)}</pre>
        <p>Check logs or try again.</p>
        <button onclick="location.reload()">Retry</button>
    `;
    try {
        splash.loadURL(`data:text/html,${encodeURIComponent(html)}`);
    } catch {
        // ignore
    }
}

// --- backend launch with retries (never auto-quit) ---
async function launchBackendWithRetries(maxAttempts = 3) {
    const { binaryPath, launcher, args } = getFlaskBinary();
    if (!fs.existsSync(binaryPath) && !launcher) {
        throw new Error(`Backend not found at ${binaryPath}`);
    }

    let attempt = 0;
    while (attempt < maxAttempts) {
        attempt++;
        try {
            await launchBackendOnce(launcher, binaryPath, args);
            return;
        } catch (e) {
            console.error(`Backend launch attempt ${attempt} failed:`, e);
            await delay(1500);
        }
    }
    throw new Error(`Backend failed after ${maxAttempts} attempts.`);
}

function launchBackendOnce(launcher, binaryPath, args) {
    return new Promise((resolve, reject) => {
        try {
            const cmd = launcher || binaryPath;
            const finalArgs = launcher ? args : [];

            flaskProcess = spawn(cmd, finalArgs, {
                shell: process.platform === 'win32',
                stdio: 'ignore',
                windowsHide: true,
                detached: false
            });

            let failedEarly = false;

            flaskProcess.on('error', (err) => {
                failedEarly = true;
                reject(err);
            });

            // Give it a short moment to see if it kills itself or not
            setTimeout(() => {
                if (!failedEarly && flaskProcess && !flaskProcess.killed) {
                    resolve();
                }
            }, 400);
        } catch (e) {
            reject(e);
        }
    });
}

function waitForFlask(retries = 75) {
    return new Promise((resolve, reject) => {
        const tryOnce = () => {
            http.get('http://localhost:5000/api/hello', (res) => {
                if (res.statusCode === 200) return resolve();
                if (--retries <= 0) return reject(new Error(`Flask responded with ${res.statusCode}`));
                setTimeout(tryOnce, 250);
            }).on('error', () => {
                if (--retries <= 0) return reject(new Error('Flask failed to respond'));
                setTimeout(tryOnce, 250);
            });
        };
        tryOnce();
    });
}

function createMainWindow() {
    try {
        mainWindow = new BrowserWindow({
            width: 900,
            height: 680,
            show: false,
            webPreferences: {
                nodeIntegration: false,
                contextIsolation: true,
                sandbox: true
            }
        });

        mainWindow.loadFile(path.resolve(__dirname, '..', 'frontend', 'build', 'index.html'));

        mainWindow.once('ready-to-show', () => {
            if (splash && !splash.isDestroyed()) splash.close();
            splash = null;
            mainWindow.show();
        });

        mainWindow.on('close', (e) => {
            if (isQuitting) return; 
            if (localConfig.minimizeToTray) {
                e.preventDefault();
                mainWindow.hide();
                if (!tray) setupTray();
            } else {
                e.preventDefault();
                isQuitting = true;
                gracefulShutdown().finally(() => app.quit());
            }
        });

        setupTray();
    } catch (e) {
        console.error('Failed to create main window:', e);
        if (splash && !splash.isDestroyed()) showSplashError(e);
    }
}

function setupTray() {
    try {
        if (tray) return;
        let trayIcon = path.join(__dirname, 'iconTemplate.png');
        if (!fs.existsSync(trayIcon)) trayIcon = undefined;

        tray = new Tray(trayIcon);
        const menu = Menu.buildFromTemplate([
            { label: 'Show App', click: () => { if (mainWindow) mainWindow.show(); } },
            { type: 'separator' },
            { label: 'Quit', click: () => { isQuitting = true; gracefulShutdown().finally(() => app.quit()); } }
        ]);
        tray.setToolTip('Goodreads Discord RPC');
        tray.setContextMenu(menu);
        tray.on('double-click', () => { if (mainWindow) mainWindow.show(); });
    } catch (e) {
        console.error('Failed to setup tray:', e);
    }
}

ipcMain.on('force-quit', () => {
    isQuitting = true;
    gracefulShutdown().finally(() => app.quit());
});

function gracefulShutdown() {
    return new Promise((resolve) => {
        const done = () => {
            try { if (tray) tray.destroy(); } catch {}
            tray = null;
            resolve();
        };

        // Ask nicely
        const shutdownReq = http.request({
            hostname: 'localhost',
            port: 5000,
            path: '/shutdown',
            method: 'POST',
            timeout: 2000
        }, (res) => {
            console.log(`Flask shutdown response: ${res.statusCode}`);
            // kill it with fire if it doesn't respond
            setTimeout(() => {
                tryKillBackend();
                done();
            }, 500);
        });

        shutdownReq.on('error', () => {
            // If kill it with more fire
            tryKillBackend();
            done();
        });

        try { shutdownReq.end(); } catch { tryKillBackend(); done(); }
    });
}

function tryKillBackend() {
    try {
        if (flaskProcess && !flaskProcess.killed) {
            if (process.platform === 'win32') {
                flaskProcess.kill('SIGTERM');
            } else {
                flaskProcess.kill('SIGTERM');
            }
        }
    } catch (e) {
        console.error('Error killing backend:', e);
    } finally {
        flaskProcess = null;
    }
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        if (!localConfig.minimizeToTray) {
            isQuitting = true;
            gracefulShutdown().finally(() => app.quit());
        }
    }
});

app.on('before-quit', () => { isQuitting = true; });

app.on('activate', () => {
    if (mainWindow) {
        mainWindow.show();
    } else if (backendReady) {
        createMainWindow();
    }
});
