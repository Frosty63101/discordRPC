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

// --- single instance guard ---
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) app.quit();
app.on('second-instance', () => {
    if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();
    }
});

// --- crash guards ---
process.on('uncaughtException', (err) => console.error('[uncaughtException]', err));
process.on('unhandledRejection', (reason) => console.error('[unhandledRejection]', reason));

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
            if (fs.existsSync(x64Path) && isRosettaInstalled()) return { binaryPath: x64Path, launcher: 'arch', args: ['-x86_64', x64Path] };
        }
        if (fs.existsSync(x64Path)) return { binaryPath: x64Path, launcher: null, args: [] };
        throw new Error(`No valid macOS binary found for architecture: ${arch}`);
    }
    if (process.platform === 'linux') {
        return { binaryPath: path.join(base, 'app-linux', 'app_linux_bin'), launcher: null, args: [] };
    }
    throw new Error(`Unsupported platform: ${process.platform}`);
}

// --- load config (for minimizeToTray decision on first boot) ---
function loadLocalConfig() {
    try {
        const home = process.env[process.platform === 'win32' ? 'USERPROFILE' : 'HOME'];
        const configPath = path.join(home, '.config', 'app_config.json');
        if (fs.existsSync(configPath)) return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    } catch (e) {
        console.error('Failed to parse local config:', e);
    }
    return {};
}
const localConfig = loadLocalConfig();

// --- tray image generator ---
function makeSvg({ template = false }) {
    if (template) {
        return `
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">
                <rect x="1" y="1" width="20" height="20" rx="5" ry="5" fill="black"/>
                <text x="50%" y="57%" text-anchor="middle" font-size="11" font-weight="700"
                            font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"
                            fill="white">G</text>
            </svg>
        `;
    }
    return `
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">
            <defs>
                <linearGradient id="g" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stop-color="#2563eb"/>
                    <stop offset="100%" stop-color="#1d4ed8"/>
                </linearGradient>
            </defs>
            <rect x="1" y="1" width="20" height="20" rx="5" ry="5" fill="url(#g)"/>
            <text x="50%" y="57%" text-anchor="middle" font-size="11" font-weight="700"
                        font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"
                        fill="white">G</text>
        </svg>
    `;
}

function createTrayNativeImage() {
    const candidate = path.join(__dirname, 'iconTemplate.png');
    if (fs.existsSync(candidate)) {
        const img = nativeImage.createFromPath(candidate);
        if (!img.isEmpty()) {
            if (process.platform === 'darwin') img.setTemplateImage(true);
            return img;
        }
    }
    const svg = makeSvg({ template: process.platform === 'darwin' });
    const dataUrl = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
    let img = nativeImage.createFromDataURL(dataUrl);
    if (!img.isEmpty()) {
        try {
            const png1x = img.resize({ width: 22, height: 22 }).toPNG();
            const png2x = img.resize({ width: 44, height: 44 }).toPNG();
            const multi = nativeImage.createEmpty();
            multi.addRepresentation({ scaleFactor: 1, width: 22, height: 22, buffer: png1x });
            multi.addRepresentation({ scaleFactor: 2, width: 44, height: 44, buffer: png2x });
            if (process.platform === 'darwin') multi.setTemplateImage(true);
            return multi;
        } catch {
            if (process.platform === 'darwin') img.setTemplateImage(true);
            return img;
        }
    }
    return nativeImage.createFromDataURL(
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABhH6NsgAAAABJRU5ErkJggg=='
    );
}

// --- app lifecycle ---
app.whenReady().then(async () => {
    try {
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
});

// --- splash ---
function createSplash() {
    try {
        splash = new BrowserWindow({
            width: 420, height: 320, frame: false, alwaysOnTop: true, resizable: false, show: false,
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

// --- backend launch with retries ---
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
                shell: process.platform === 'win32',
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
            width: 900, height: 680, show: false,
            webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true }
        });
        mainWindow.loadFile(path.resolve(__dirname, '..', 'frontend', 'build', 'index.html'));
        mainWindow.once('ready-to-show', () => {
            if (splash && !splash.isDestroyed()) splash.close();
            splash = null;
            mainWindow.show();
        });

        mainWindow.on('close', (e) => {
            if (isQuitting) return; // actual quit path
            if (localConfig.minimizeToTray) {
                e.preventDefault();
                if (!tray) setupTray();
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
        tray.setToolTip('Goodreads Discord RPC');
        tray.setContextMenu(menu);
        tray.on('double-click', () => {
            if (process.platform === 'darwin') { try { app.dock?.show(); } catch {} }
            if (mainWindow) mainWindow.show();
        });
    } catch (e) { console.error('Failed to setup tray:', e); }
}

// Renderer-triggered full quit
ipcMain.on('force-quit', () => hardExit());

// === Exit orchestration ===
function hardExit() {
    if (isQuitting) return;
    isQuitting = true;

    // Final safety: if something hangs, force the process down hard.
    const absoluteKill = setTimeout(() => {
        try { destroyUi(); } catch {}
        process.exit(0);
    }, APP_FORCE_EXIT_MS).unref?.();

    gracefulShutdown()
        .catch(() => {})
        .finally(() => {
            clearTimeout(absoluteKill);
            // Ensure all windows are gone before quitting
            destroyUi();
            app.quit();
            // If Electron refuses to die (rare), nuke it, kill it with fire and salt the earth behind you:
            setTimeout(() => process.exit(0), 500).unref?.();
        });
}

function gracefulShutdown() {
    return new Promise((resolve) => {
        // Close windows early so the user sees immediate exit
        try { if (splash && !splash.isDestroyed()) splash.close(); } catch {}
        try { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close(); } catch {}

        const done = () => {
            try { if (tray) tray.destroy(); } catch {}
            tray = null;
            resolve();
        };

        // 1) Ask nicely
        const req = http.request({
            hostname: 'localhost', port: 5000, path: '/shutdown',
            method: 'POST', timeout: SHUTDOWN_REQUEST_TIMEOUT_MS
        }, () => {
            // 2) Give it a moment to die on its own
            setTimeout(() => {
                escalateKillChain().finally(done);
            }, BACKEND_TERM_GRACE_MS);
        });

        req.on('error', () => {
            // If request fails, kill it immediately with extreme prejudice
            escalateKillChain().finally(done);
        });

        try { req.end(); } catch { escalateKillChain().finally(done); }
    });
}

async function escalateKillChain() {
    tryKillBackend('SIGTERM');
    await delay(BACKEND_TERM_GRACE_MS);

    // If it somehow is still around, power word kill
    if (flaskProcess && !flaskProcess.killed) {
        try {
            if (process.platform === 'win32') {
                execFile('taskkill', ['/PID', String(flaskProcess.pid), '/T', '/F'], () => {});
            } else {
                tryKillBackend('SIGKILL');
            }
        } catch (e) { console.error('Force kill error:', e); }
    }
    await delay(BACKEND_KILL_GRACE_MS);
}

function tryKillBackend(signal) {
    try {
        if (flaskProcess && !flaskProcess.killed) flaskProcess.kill(signal || 'SIGTERM');
    } catch (e) {
        console.error('Error killing backend:', e);
    } finally {
        // Null it even if kill failed
        flaskProcess = null;
    }
}

function destroyUi() {
    // Tear down windows and listeners 
    try {
        if (mainWindow && !mainWindow.isDestroyed()) { mainWindow.removeAllListeners(); mainWindow.destroy(); }
    } catch {}
    try {
        if (splash && !splash.isDestroyed()) { splash.removeAllListeners(); splash.destroy(); }
    } catch {}
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
    // If user is exiting, finish the job. Otherwise honor minimizeToTray on macOS.
    if (isQuitting) return;
    if (process.platform !== 'darwin' && !localConfig.minimizeToTray) hardExit();
});
app.on('before-quit', () => { isQuitting = true; });
app.on('activate', () => {
    if (mainWindow) mainWindow.show();
    else if (backendReady) createMainWindow();
});
