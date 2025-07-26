const path = require('path');
const fs = require('fs');
const { app, BrowserWindow } = require('electron');
const { spawn, spawnSync } = require('child_process');
const http = require('http');

let flaskProcess;
let splash;
let mainWindow;

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
            if (fs.existsSync(armPath)) {
                return { binaryPath: armPath, archPrefix: null };
            } else if (fs.existsSync(x64Path) && isRosettaInstalled()) {
                return { binaryPath: x64Path, archPrefix: 'arch' };
            }
        }

        if (fs.existsSync(x64Path)) {
            return { binaryPath: x64Path, archPrefix: null };
        }

        throw new Error(`No valid macOS binary found for architecture: ${arch}`);
    }

    if (process.platform === 'linux') {
        return { binaryPath: path.join(base, 'app-linux', 'app_linux_bin'), archPrefix: null };
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

    const { binaryPath, archPrefix } = getFlaskBinary();

    if (!fs.existsSync(binaryPath)) {
        console.error("Flask binary not found at:", binaryPath);
        splash.loadURL('data:text/html,<h1>Backend not found</h1>');
        setTimeout(() => app.quit(), 3000);
        return;
    }

    const spawnArgs = archPrefix === 'arch' ? ['-x86_64', binaryPath] : [binaryPath];

    flaskProcess = spawn(archPrefix || spawnArgs[0], archPrefix ? spawnArgs.slice(1) : [], {
        shell: true,
        stdio: 'inherit',
        windowsHide: true
    });

    flaskProcess.on('error', err => {
        console.error("Failed to start Flask process:", err);
        const isRosetta = archPrefix === 'arch';
        const msg = isRosetta
    ? encodeURIComponent(
        `<h1>Rosetta 2 Required</h1>
        <p>This app requires Rosetta 2 to run the backend on Apple Silicon Macs.</p>
        <p>Run this command in Terminal:</p>
        <code>softwareupdate --install-rosetta</code>
        <p><a href="https://support.apple.com/en-us/HT211861" target="_blank">Apple Support: About Rosetta</a></p>`
        )
    : encodeURIComponent('<h1>Flask failed to start</h1>');

        splash.loadURL(`data:text/html,${msg}`);

        setTimeout(() => app.quit(), 5000);
    });

    flaskProcess.on('exit', (code) => {
        if (code !== 0 && archPrefix === 'arch') {
            splash.loadURL(`data:text/html,<h1>Rosetta launch failed</h1><p>Try running this:</p><code>softwareupdate --install-rosetta</code>`);
        }
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
