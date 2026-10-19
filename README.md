
# discordRPC

A Discord Rich Presence application that displays your current reading activity from Goodreads, StoryGraph, and Audiobookshelf.

## Features

- Display current book from Goodreads
- Display current book from StoryGraph
- Display currently playing audiobooks from Audiobookshelf using a server URL, API key, and user UUID
- Fallback Goodreads/StoryGraph extraction using stable book links and structured metadata instead of only CSS classes
- Real-time Discord Rich Presence updates
- Automatic synchronization

## Installation

### From Release

1. Download the latest release from the [Releases](https://github.com/Frosty63101/discordRPC/releases) page
2. Extract the archive
3. Run the executable
4. Configure your credentials (see [Configuration](#configuration))

### From Source

For manually packaged releases (not just the CI workflow), generate the
native open-book app icons first:

```bash
python -m pip install Pillow
python scripts/generate_icons.py
```

This creates the `.ico`, `.icns`, and `.png` from code. The SVG artwork is
available without this step when running in development.



#### Prerequisites (All Platforms)

- **Node.js 18+** (with npm)
- **Python 3.11+**
- **Git**
- **Discord** installed and running

#### Windows

1. Clone the repository:
    ```cmd
    git clone https://github.com/Frosty63101/discordRPC.git
    cd discordRPC
    ```

2. Install Python dependencies:
    ```cmd
    pip install -r backend/requirements.txt
    ```

3. Install and cache Playwright browsers:
    ```powershell
    $env:PLAYWRIGHT_BROWSERS_PATH = "$(Get-Location)\backend\.pw-browsers"
    python -m playwright install chromium
    ```

4. Zip Playwright browsers for bundling:
    ```powershell
    $browsers = "$(Get-Location)\backend\.pw-browsers"
    $zip = "$(Get-Location)\backend\playwright-browsers.zip"
    Compress-Archive -Path "$browsers\*" -DestinationPath $zip
    Remove-Item -Recurse -Force $browsers
    ```

5. Build the Python backend:
    ```cmd
    pip install pyinstaller
    pyinstaller backend/app.spec
    xcopy /s /e /y dist\* build\app\
    rmdir /s /q backend\build dist
    ```

6. Install and build the frontend:
    ```cmd
    cd frontend
    npm install
    npm run build
    cd ..
    ```

7. Package the Electron app:
    ```cmd
    npm install --save-dev electron @electron/packager
    npx @electron/packager . DiscordRPC --platform=win32 --arch=x64 --icon=frontend/public/book-icon.ico --out=dist --overwrite --prune=true
    ```

8. Your app is now in `dist/DiscordRPC-win32-x64/`

#### macOS (x86_64)

1. Clone the repository:
    ```bash
    git clone https://github.com/Frosty63101/discordRPC.git
    cd discordRPC
    ```

2. Install Python dependencies:
    ```bash
    pip install -r backend/requirements.txt
    ```

3. Install Playwright browsers:
    ```bash
    export PLAYWRIGHT_BROWSERS_PATH=0
    python -m playwright install chromium
    cd backend
    python3 - <<'EOF'
    import playwright, pathlib, zipfile
    browsers = pathlib.Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    outZip = pathlib.Path("playwright-browsers.zip")
    with zipfile.ZipFile(outZip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in browsers.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(browsers))
    print("Wrote", outZip)
    EOF
    cd ..
    ```

4. Remove Playwright cache:
    ```bash
    python3 - <<'EOF'
    import playwright, pathlib, shutil
    browsers = pathlib.Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    shutil.rmtree(browsers, ignore_errors=True)
    EOF
    ```

5. Rebuild PyInstaller bootloader for x86_64:
    ```bash
    git clone https://github.com/pyinstaller/pyinstaller.git
    cd pyinstaller/bootloader
    python3 ./waf distclean all --target-arch=64bit
    cd ../..
    pip install ./pyinstaller
    ```

6. Build the Python backend:
    ```bash
    export ARCHFLAGS="-arch x86_64"
    pyinstaller backend/app-mac-x86_64.spec
    mkdir -p build/app-mac-x86_64
    cp -R dist/app_mac_x86_64/* build/app-mac-x86_64/
    chmod +x build/app-mac-x86_64/app_mac_bin_x86_64
    rm -rf backend/build dist
    ```

7. Install and build the frontend:
    ```bash
    cd frontend
    npm install
    npm run build
    cd ..
    ```

8. Package the Electron app:
    ```bash
    npm install --save-dev electron @electron/packager
    npx electron-packager . DiscordRPC --platform=darwin --arch=x64 --icon=frontend/public/book-icon.icns --out=dist --overwrite --prune=true
    ```

9. Your app is now at `dist/DiscordRPC-darwin-x64/DiscordRPC.app`

#### macOS (arm64/Apple Silicon)

1. Clone the repository:
    ```bash
    git clone https://github.com/Frosty63101/discordRPC.git
    cd discordRPC
    ```

2. Install Python dependencies:
    ```bash
    pip install -r backend/requirements.txt
    ```

3. Install Playwright browsers:
    ```bash
    export PLAYWRIGHT_BROWSERS_PATH=0
    python -m playwright install chromium
    cd backend
    python3 - <<'EOF'
    import playwright, pathlib, zipfile
    browsers = pathlib.Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    outZip = pathlib.Path("playwright-browsers.zip")
    with zipfile.ZipFile(outZip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in browsers.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(browsers))
    print("Wrote", outZip)
    EOF
    cd ..
    ```

4. Remove Playwright cache:
    ```bash
    python3 - <<'EOF'
    import playwright, pathlib, shutil
    browsers = pathlib.Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    shutil.rmtree(browsers, ignore_errors=True)
    EOF
    ```

5. Rebuild PyInstaller bootloader for arm64:
    ```bash
    git clone https://github.com/pyinstaller/pyinstaller.git
    cd pyinstaller/bootloader
    python3 ./waf distclean all --target-arch=64bit-arm
    cd ../..
    pip install ./pyinstaller
    ```

6. Build the Python backend:
    ```bash
    export ARCHFLAGS="-arch arm64"
    pyinstaller backend/app-mac-arm64.spec
    mkdir -p build/app-mac-arm64
    cp -R dist/app_mac_arm64/* build/app-mac-arm64/
    chmod +x build/app-mac-arm64/app_mac_bin_arm64
    rm -rf backend/build dist
    ```

7. Install and build the frontend:
    ```bash
    cd frontend
    npm install
    npm run build
    cd ..
    ```

8. Package the Electron app:
    ```bash
    npm install --save-dev electron @electron/packager
    npx electron-packager . DiscordRPC --platform=darwin --arch=arm64 --icon=frontend/public/book-icon.icns --out=dist --overwrite --prune=true
    ```

9. Your app is now at `dist/DiscordRPC-darwin-arm64/DiscordRPC.app`

#### Linux

1. Clone the repository:
    ```bash
    git clone https://github.com/Frosty63101/discordRPC.git
    cd discordRPC
    ```

2. Install system dependencies:
    ```bash
    sudo apt update
    sudo apt install -y python3 python3-pip
    ```

3. Install Python dependencies:
    ```bash
    pip3 install -r backend/requirements.txt
    ```

4. Install Playwright system dependencies and browsers:
    ```bash
    python3 -m playwright install-deps
    export PLAYWRIGHT_BROWSERS_PATH=0
    python3 -m playwright install chromium
    cd backend
    python3 - <<'EOF'
    import playwright, pathlib, zipfile
    browsers = pathlib.Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    outZip = pathlib.Path("playwright-browsers.zip")
    with zipfile.ZipFile(outZip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in browsers.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(browsers))
    print("Wrote", outZip)
    EOF
    cd ..
    ```

5. Remove Playwright cache:
    ```bash
    python3 - <<'EOF'
    import playwright, pathlib, shutil
    browsers = pathlib.Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    shutil.rmtree(browsers, ignore_errors=True)
    EOF
    ```

6. Build the Python backend:
    ```bash
    pip3 install pyinstaller
    pyinstaller backend/app-linux.spec
    mkdir -p build/app-linux
    cp dist/app_linux_bin build/app-linux/
    rm -rf backend/build dist
    ```

7. Install and build the frontend:
    ```bash
    cd frontend
    npm install
    npm run build
    cd ..
    ```

8. Package the Electron app:
    ```bash
    npm install --save-dev electron @electron/packager
    npx electron-packager . DiscordRPC --platform=linux --arch=x64 --icon=frontend/public/book-icon.png --out=dist --overwrite --prune=true
    ```

9. Your app is now in `dist/DiscordRPC-linux-x64/`

## Book cover images in Discord

The Discord activity uses the book's cover as its **large image** when a valid,
public HTTPS image is available. It tries the provider's cover first, then Open
Library by ISBN or a title/author match. Cover results (including misses) are
cached for six hours to avoid excess requests. Discord gets only the public image
URL, never your Audiobookshelf API key, private cookies, or local server address.

A private Audiobookshelf cover endpoint usually cannot be loaded by Discord,
even if the desktop app can see it. Open Library can supply the equivalent public
cover for those books. If no suitable image is available, the activity falls back
to the `book` image asset previously used by the app. Upload an image named
`book` in the Discord Developer Portal to ensure this fallback has artwork.

External image URLs must be accessible without authentication and may still be
rejected or not rendered by Discord if the server blocks Discord's media proxy.

## Desktop interface and appearance

The dashboard now includes separate Reading Source and App Settings panels,
light/dark/system appearance (following your operating system when set to
System), a book-cover preview, Discord connect/disconnect/test actions, and an
activity log with a scrollable **50-line** history from the real
`gr_rpc_log.txt` log file. The log updates every five seconds, with a
**Follow newest** toggle to keep your scroll position while reading older lines.

Desktop preferences are saved in the existing platform-specific
`GoodreadsRPC/app_config.json` file and sent immediately to Electron:

- **Close to system tray**: click the window's close button to hide it; use
  the tray icon's Show App option to restore it.
- **Minimize to system tray**: optionally hide to tray on the minimize button
  (disabled by default so ordinary taskbar minimizing still works).
- **Launch at login**: uses native login-item registration on Windows/macOS,
  or `~/.config/autostart/reading-presence.desktop` on most Linux desktops
  (honors XDG_CONFIG_HOME).
- **Start presence automatically**: starts the Discord connection when the
  desktop app opens, separately from launching the app at login.

The **Quit app** button and tray's **Quit** command actually terminate the
backend and the desktop process. For a Windows/macOS/Linux app icon, the
code-drawn open-book illustration is sourced in
`frontend/public/book-icon.svg` and native icon files are generated by
`python scripts/generate_icons.py` (requires `pip install Pillow`).
The GitHub Actions packaging workflow automatically creates the corresponding
ICO, ICNS, and PNG icons. The system tray uses a monochrome template on macOS.

**Linux limitation:** login autostart requires a desktop environment following
the freedesktop XDG autostart convention. It is not meaningful on headless
systems without a desktop session. Desktop notifications/system tray support
may vary by Linux desktop environment.

## Configuration

### Goodreads ID

1. Visit [Goodreads.com](https://www.goodreads.com)
2. Go to your profile
3. Your ID is in the URL: `goodreads.com/user/show/**YOUR_ID**`

### StoryGraph Remember Cookie

1. Log in to [StoryGraph](https://www.storygraph.com)
2. Open Browser DevTools (F12)
3. Go to Application → Cookies
4. Find the `remember` cookie and copy its value
5. Paste it into the application settings

### Audiobookshelf

Choose **Audiobookshelf** from Platform, then enter:
1. **Server URL:** `https://books.example.com` or `http://localhost:13378` (reachable from this computer).
2. **API Key:** the Audiobookshelf user token, which is sent to the server as a Bearer token.
3. **User UUID:** the user ID returned by Audiobookshelf's `/api/users` endpoint or displayed in its user configuration.

Save the config before starting presence. The app uses `/api/users/online` for currently active playback and `/api/users/{userId}/listening-sessions` for recent choices. Reading activity clears from Discord when no active session is detected. Depending on server permissions, listing online sessions may require an administrative API token. The server may report a recently stopped session for a short time. User IDs may have `usr_` prefixes depending on the server; copy them exactly.

**Security:** the key is stored in your local application configuration; do not commit the key to this repository or share diagnostic logs containing credentials. Use HTTPS when accessing a remote server. The UI hides the saved key after you save it.

### Troubleshooting

- **Discord error 4000 — Client ID is Invalid:** copy your actual Discord Application ID from the Discord Developer Portal. The default example ID may no longer represent a working application. Do not paste a bot token.
- **StoryGraph / Playwright executable missing:** quit the app and remove the directory `%LOCALAPPDATA%\\GoodreadsRPC\\discordrpc-playwright` on Windows (or `discordrpc-playwright` under the platform cache directory on macOS/Linux), then relaunch. New builds automatically re-extract when the archive hash changes or the browser is missing.
- **Audiobookshelf setup error:** enter an http(s) server URL, a valid API key, and the exact user ID. Audiobookshelf API keys are scoped to the selected user. An admin key can inspect online sessions; a non-admin key can read its own sessions and may detect recently open playback sessions through `/api/session/:id`. Playback in offline players cannot be detected until they sync with the server.
- Logs: `gr_rpc_log.txt` beside `app_config.json`, under `%APPDATA%\\GoodreadsRPC` (Windows), `~/Library/Application Support/GoodreadsRPC` (macOS), or `~/.config/GoodreadsRPC` (Linux).

### Notes on website scraping

Goodreads and StoryGraph do not offer a supported modern public API for this specific use case. The app tries book links, semantic selectors and JSON-LD structured data so a cosmetic CSS change is less likely to break parsing. StoryGraph uses a headless browser for JavaScript-rendered pages and may require a login cookie. Anti-bot controls, private profiles or major website changes can still prevent automated access; no scraper can be guaranteed permanently UI-change-proof.

### Supported desktop targets

The repository includes packaging for Windows x64, macOS Intel/Apple Silicon, and Linux x64. GitHub Actions builds these operating systems; actual Discord desktop availability, GUI libraries and server permissions must still be validated on target machines.

## Requirements

- Node.js 14+
- Discord installed and running
- Active Goodreads or StoryGraph account

## License

MIT
