
# discordRPC

A Discord Rich Presence application that displays your current reading activity from Goodreads and StoryGraph.

## Features

- Display current book from Goodreads
- Display current book from StoryGraph
- Real-time Discord Rich Presence updates
- Automatic synchronization

## Installation

### From Release

1. Download the latest release from the [Releases](https://github.com/Frosty63101/discordRPC/releases) page
2. Extract the archive
3. Run the executable
4. Configure your credentials (see [Configuration](#configuration))

### From Source

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
    npx @electron/packager . DiscordRPC --platform=win32 --arch=x64 --out=dist --overwrite --prune=true
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
    npx electron-packager . DiscordRPC --platform=darwin --arch=x64 --out=dist --overwrite --prune=true
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
    npx electron-packager . DiscordRPC --platform=darwin --arch=arm64 --out=dist --overwrite --prune=true
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
    npx electron-packager . DiscordRPC --platform=linux --arch=x64 --out=dist --overwrite --prune=true
    ```

9. Your app is now in `dist/DiscordRPC-linux-x64/`

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

## Requirements

- Node.js 14+
- Discord installed and running
- Active Goodreads or StoryGraph account

## License

MIT
