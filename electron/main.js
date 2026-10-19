// electron/main.js
const path = require('path');
const fs = require('fs');
const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage } = require('electron');
const { spawn, spawnSync, execFile } = require('child_process');
const http = require('http');

let flaskProcess = null;
let splash = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let backendReady = false;

// Shutdown timings
const SHUTDOWN_REQUEST_TIMEOUT_MS = 2000;
const BACKEND_TERM_GRACE_MS = 800;
const BACKEND_KILL_GRACE_MS = 800;
const APP_FORCE_EXIT_MS = 4000;

// ---------- App identity & icon defaults ----------
app.setName('Reading Presence');
if (process.platform === 'win32') {
    // Helps Windows taskbar pinning + correct icon usage for the .exe
    app.setAppUserModelId('com.frosty63.goodreads-rpc');
}

// The icon is drawn as SVG in the repository and as native PNG/ICO/ICNS
// by scripts/generate_icons.py during packaging. No downloaded artwork.
function loadFaviconNativeImage() {
    const root = path.resolve(__dirname, '..', 'frontend', 'public');
    for (const name of ['book-icon.png', 'book-icon.svg', 'favicon.ico']) {
        const filePath = path.join(root, name);
        if (!fs.existsSync(filePath)) continue;
        const image = name.endsWith('.svg')
            ? nativeImage.createFromDataURL(
                'data:image/svg+xml;base64,' + fs.readFileSync(filePath).toString('base64')
            )
            : nativeImage.createFromPath(filePath);
        if (!image.isEmpty()) return image;
    }
    return null;
}

function createTrayNativeImage() {
    if (process.platform === 'darwin') {
        // Monochrome template artwork follows the macOS menu-bar theme.
        const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">' +
            '<path fill="black" d="M11 18C8 16 5 16 2 17V5C6 4 9 5 11 7C13 5 16 4 20 5V17C17 16 14 16 11 18Z"/>' +
            '<path stroke="white" stroke-width="1.2" d="M11 7V18"/></svg>';
        const image = nativeImage.createFromDataURL('data:image/svg+xml;base64,' +
            Buffer.from(svg).toString('base64')).resize({width: 22, height: 22});
        image.setTemplateImage(true);
        return image;
    }
    const image = loadFaviconNativeImage();
    return image && !image.isEmpty() ? image.resize({width: 24, height: 24}) : nativeImage.createEmpty();
}

// ---------- single instance guard ----------
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) app.quit();
app.on('second-instance', () => {
    if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();
    }
});

// ---------- crash guards ----------
process.on('uncaughtException', (err) => console.error('[uncaughtException]', err));
process.on('unhandledRejection', (reason) => console.error('[unhandledRejection]', reason));

// ---------- Rosetta check (mac) ----------
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

// ---------- resolve backend ----------
function getFlaskBinary() {
    const base = path.join(__dirname, '..', 'build');
    const buildBase = fs.existsSync(base) ? base : path.join(process.resourcesPath, 'app', 'build');
    if (process.platform === 'win32') {
        return { binaryPath: path.join(buildBase, 'app', 'app', 'app.exe'), launcher: null, args: [] };
    }
    if (process.platform === 'darwin') {
        const armPath = path.join(buildBase, 'app-mac-arm64', 'app_mac_bin_arm64');
        const x64Path = path.join(buildBase, 'app-mac-x86_64', 'app_mac_bin_x86_64');
        const arch = process.arch;
        if (arch === 'arm64') {
            if (fs.existsSync(armPath)) return { binaryPath: armPath, launcher: null, args: [] };
            if (fs.existsSync(x64Path) && isRosettaInstalled()) return { binaryPath: x64Path, launcher: 'arch', args: ['-x86_64', x64Path] };
        }
        if (fs.existsSync(x64Path) && arch === 'x64') return { binaryPath: x64Path, launcher: null, args: [] };
        throw new Error(`No valid macOS binary found for architecture: ${arch}`);
    }
    if (process.platform === 'linux') {
        return { binaryPath: path.join(buildBase, 'app-linux', 'app_linux_bin'), launcher: null, args: [] };
    }
    throw new Error(`Unsupported platform: ${process.platform}`);
}

// ---------- load local config (minimizeToTray on first boot) ----------
function loadLocalConfig() {
    try {
        const home = process.env[process.platform === 'win32' ? 'USERPROFILE' : 'HOME'];
        const configRoot = process.platform === 'win32' ? (process.env.APPDATA || home) : process.platform === 'darwin' ? path.join(home, 'Library', 'Application Support') : (process.env.XDG_CONFIG_HOME || path.join(home, '.config'));
        const configPath = path.join(configRoot, 'GoodreadsRPC', 'app_config.json');
        if (fs.existsSync(configPath)) return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    } catch (e) {
        console.error('Failed to parse local config:', e);
    }
    return {};
}
const localConfig = {
    minimizeToTray: true,
    minimizeOnMinimize: false,
    startOnStartup: false,
    ...loadLocalConfig(),
};

function getAutostartFilePath() {
    const configRoot = process.env.XDG_CONFIG_HOME || path.join(app.getPath('home'), '.config');
    return path.join(configRoot, 'autostart', 'reading-presence.desktop');
}

function setStartOnStartup(enabled) {
    if (!app.isPackaged && enabled) {
        throw new Error('Launch-at-login is available in packaged desktop builds');
    }
    if (process.platform === 'linux') {
        const autostartPath = getAutostartFilePath();
        if (!enabled) {
            if (fs.existsSync(autostartPath)) fs.unlinkSync(autostartPath);
            return;
        }
        fs.mkdirSync(path.dirname(autostartPath), {recursive: true});
        const executable = process.execPath.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        const desktopEntry = [
            '[Desktop Entry]', 'Type=Application', 'Version=1.0',
            'Name=Reading Presence',
            'Comment=Show reading activity on Discord',
            'Exec="' + executable + '"',
            'Terminal=false', 'X-GNOME-Autostart-enabled=true', ''
        ].join('\n');
        fs.writeFileSync(autostartPath, desktopEntry, {mode: 0o600});
        return;
    }
    if (process.platform === 'win32' || process.platform === 'darwin') {
        app.setLoginItemSettings({openAtLogin: enabled, openAsHidden: true});
        return;
    }
    throw new Error('Launch-at-login is not available on this platform');
}

function applyWindowPreferences(preferences) {
    const next = {
        minimizeToTray: Boolean(preferences.minimizeToTray),
        minimizeOnMinimize: Boolean(preferences.minimizeOnMinimize),
        startOnStartup: Boolean(preferences.startOnStartup),
    };
    // Register startup before updating the running preferences; a failure
    // leaves the checkbox unchanged in the renderer.
    setStartOnStartup(next.startOnStartup);
    Object.assign(localConfig, next);
    return next;
}

ipcMain.handle('app:set-preferences', (event, preferences) => {
    if (!mainWindow || event.sender !== mainWindow.webContents) {
        throw new Error('Unrecognized settings window');
    }
    return applyWindowPreferences(preferences || {});
});

// ---------- preload bridge for renderer IPC ----------
function getPreloadPath() {
    const devPreload = path.resolve(__dirname, 'preload.js');
    if (fs.existsSync(devPreload)) return devPreload;
    const packagedPreload = path.join(process.resourcesPath, 'preload.js');
    return fs.existsSync(packagedPreload) ? packagedPreload : undefined;
}

// ---------- app lifecycle ----------
app.whenReady().then(async () => {
    try {
        if (localConfig.startOnStartup) {
            try { setStartOnStartup(true); } catch (error) { console.error('Autostart setup failed:', error); }
        }
        createSplash();
        await launchBackendWithRetries();
        await waitForFlask();
        backendReady = true;
        createMainWindow();
    } catch (err) {
        console.error('Backend failed to come online:', err);
        showSplashError(err);
        setupTray(); // still allow user to Quit
    }

    // macOS dock icon should use favicon.png if available
    if (process.platform === 'darwin') {
        const fav = loadFaviconNativeImage();
        if (fav && !fav.isEmpty()) {
            try { app.dock?.setIcon(fav); } catch {}
        }
    }
});

// ---------- splash ----------
function createSplash() {
    try {
        splash = new BrowserWindow({
            width: 420, height: 320, frame: false, alwaysOnTop: true, resizable: false, show: false,
            icon: loadFaviconNativeImage() || undefined
        });
        const splashPath = path.resolve(__dirname, '..', 'frontend', 'public', 'splash.html');
        if (fs.existsSync(splashPath)) splash.loadFile(splashPath);
        else splash.loadURL('data:text/html,<h2>Starting…</h2>');
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
    try { splash.loadURL(`data:text/html,${encodeURIComponent(html)}`); } catch {}
}

// ---------- backend launch with retries ----------
async function launchBackendWithRetries(maxAttempts = 3) {
    const { binaryPath, launcher, args } = getFlaskBinary();
    if (!fs.existsSync(binaryPath) && !launcher) throw new Error(`Backend not found at ${binaryPath}`);

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
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
                shell: false,
                stdio: 'ignore',
                windowsHide: true,
                detached: false
            });
            let failedEarly = false;
            flaskProcess.on('error', (err) => { failedEarly = true; reject(err); });
            setTimeout(() => {
                if (!failedEarly && flaskProcess && !flaskProcess.killed) resolve();
                else reject(new Error('Backend died immediately'));
            }, 400);
        } catch (e) { reject(e); }
    });
}

function waitForFlask(retries = 75) {
    return new Promise((resolve, reject) => {
        const tryOnce = () => {
            http.get('http://127.0.0.1:5000/api/hello', (res) => {
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
        const iconImage = loadFaviconNativeImage() || undefined;

        mainWindow = new BrowserWindow({
            width: 1120, height: 800, minWidth: 760, minHeight: 610, show: false,
            icon: iconImage, // <-- UI window/taskbar icon defaults to favicon.ico
            webPreferences: {
                nodeIntegration: false,
                contextIsolation: true,
                sandbox: true,
                preload: getPreloadPath() // expose ipc to renderer safely
            }
        });

        mainWindow.loadFile(path.resolve(__dirname, '..', 'frontend', 'build', 'index.html'));
        mainWindow.once('ready-to-show', () => {
            if (splash && !splash.isDestroyed()) splash.close();
            splash = null;
            mainWindow.show();
        });

        mainWindow.on('minimize', (event) => {
            if (!isQuitting && localConfig.minimizeOnMinimize) {
                if (!tray) setupTray();
                if (tray) {
                    event.preventDefault();
                    mainWindow.hide();
                    if (process.platform === 'darwin') app.dock?.hide();
                }
            }
        });

        mainWindow.on('close', (e) => {
            if (isQuitting) return; // actual quit path
            if (localConfig.minimizeToTray) {
                if (!tray) setupTray();
                if (!tray) {
                    e.preventDefault();
                    hardExit();
                    return;
                }
                e.preventDefault();
                mainWindow.hide();
                if (process.platform === 'darwin') { try { app.dock?.hide(); } catch {} }
            } else {
                e.preventDefault();
                hardExit(); // Exit from the window close when not minimizing
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
        const trayImage = createTrayNativeImage();
        if (trayImage.isEmpty()) throw new Error('Tray icon could not be generated');
        tray = new Tray(trayImage);
        const menu = Menu.buildFromTemplate([
            { label: 'Show App', click: () => {
                    if (process.platform === 'darwin') { try { app.dock?.show(); } catch {} }
                    if (mainWindow) mainWindow.show();
                }
            },
            { type: 'separator' },
            { label: 'Quit', click: () => hardExit() }
        ]);
        tray.setToolTip('Reading Presence');
        tray.setContextMenu(menu);
        const restoreWindow = () => {
            if (process.platform === 'darwin') { try { app.dock?.show(); } catch {} }
            if (mainWindow) {
                if (mainWindow.isMinimized()) mainWindow.restore();
                mainWindow.show();
                mainWindow.focus();
            }
        };
        tray.on('double-click', restoreWindow);
        if (process.platform !== 'darwin') tray.on('click', restoreWindow);
    } catch (e) { console.error('Failed to setup tray:', e); }
}

// Renderer-triggered full quit
ipcMain.on('force-quit', () => hardExit());

// === Exit orchestration ===
function hardExit() {
    if (isQuitting) return;
    isQuitting = true;

    const absoluteKill = setTimeout(() => {
        try { destroyUi(); } catch {}
        process.exit(0);
    }, APP_FORCE_EXIT_MS).unref?.();

    gracefulShutdown()
        .catch(() => {})
        .finally(() => {
            clearTimeout(absoluteKill);
            destroyUi();
            app.quit();
            setTimeout(() => process.exit(0), 500).unref?.();
        });
}

function gracefulShutdown() {
    return new Promise((resolve) => {
        try { if (splash && !splash.isDestroyed()) splash.close(); } catch {}
        try { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close(); } catch {}

        const done = () => {
            try { if (tray) tray.destroy(); } catch {}
            tray = null;
            resolve();
        };

        const req = http.request({
            hostname: '127.0.0.1', port: 5000, path: '/shutdown',
            method: 'POST', timeout: SHUTDOWN_REQUEST_TIMEOUT_MS
        }, () => {
            setTimeout(() => {
                escalateKillChain().finally(done);
            }, BACKEND_TERM_GRACE_MS);
        });

        req.on('error', () => {
            escalateKillChain().finally(done);
        });

        try { req.end(); } catch { escalateKillChain().finally(done); }
    });
}

async function escalateKillChain() {
    const processToStop = flaskProcess;
    if (!processToStop) return;

    try {
        if (processToStop.exitCode === null) processToStop.kill('SIGTERM');
    } catch (error) {
        console.error('Could not terminate backend:', error);
    }
    await delay(BACKEND_TERM_GRACE_MS);

    if (processToStop.exitCode === null) {
        try {
            if (process.platform === 'win32') {
                await new Promise((resolve) => {
                    execFile('taskkill', ['/PID', String(processToStop.pid), '/T', '/F'],
                        () => resolve());
                });
            } else {
                processToStop.kill('SIGKILL');
            }
        } catch (error) {
            console.error('Could not force-stop backend:', error);
        }
    }
    await delay(BACKEND_KILL_GRACE_MS);
    if (flaskProcess === processToStop) flaskProcess = null;
}

function destroyUi() {
    try { if (mainWindow && !mainWindow.isDestroyed()) { mainWindow.removeAllListeners(); mainWindow.destroy(); } } catch {}
    try { if (splash && !splash.isDestroyed()) { splash.removeAllListeners(); splash.destroy(); } } catch {}
    try { if (tray) tray.destroy(); } catch {}
    tray = null; splash = null; mainWindow = null;

    app.removeAllListeners('window-all-closed');
    app.removeAllListeners('before-quit');
    app.removeAllListeners('activate');
    app.removeAllListeners('second-instance');
}

// Helpers
function delay(ms) { return new Promise((r) => setTimeout(r, ms)); }

app.on('window-all-closed', () => {
    if (!isQuitting && !localConfig.minimizeToTray) hardExit();
});
app.on('before-quit', (event) => {
    if (isQuitting) return;
    event.preventDefault();
    hardExit();
});
app.on('activate', () => {
    if (mainWindow) mainWindow.show();
    else if (backendReady) createMainWindow();
});
