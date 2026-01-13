import json
import os
import re
import signal
import sys
import threading
import time

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

presenceThread = None
statusLock = threading.Lock()
configLock = threading.Lock()
booksLock = threading.Lock()

# Events
init_event = threading.Event()
is_running_event = threading.Event()
should_run_event = threading.Event()

import os
import sys
import zipfile


def setPlaywrightBrowserPathForPyinstaller():
    """
    If we're running from a PyInstaller build:
      - Extract bundled playwright-browsers.zip to a writable per-user cache dir
      - Point PLAYWRIGHT_BROWSERS_PATH at that extracted directory
    This works on macOS/Linux/Windows.
    """
    if not (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")):
        return

    extractedRoot = sys._MEIPASS

    # The zip will be bundled at: <_MEIPASS>/playwright-browsers.zip
    bundledZipPath = os.path.join(extractedRoot, "playwright-browsers.zip")
    if not os.path.exists(bundledZipPath):
        # If you choose not to use zip on Windows later, this is fine.
        return

    # Per-user cache location (writable)
    if sys.platform == "win32":
        baseCacheDir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        baseCacheDir = os.path.join(os.path.expanduser("~"), "Library", "Caches")
    else:
        baseCacheDir = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")

    targetDir = os.path.join(baseCacheDir, "discordrpc-playwright-browsers")

    # Use a marker file so we only unzip once
    markerPath = os.path.join(targetDir, ".extracted-ok")

    if not os.path.exists(markerPath):
        os.makedirs(targetDir, exist_ok=True)

        # Clean partial extracts if any
        # (optional but helps if extraction is interrupted)
        try:
            for rootDir, dirNames, fileNames in os.walk(targetDir):
                for fileName in fileNames:
                    if fileName != ".extracted-ok":
                        pass
        except Exception:
            pass

        with zipfile.ZipFile(bundledZipPath, "r") as zipRef:
            zipRef.extractall(targetDir)

        with open(markerPath, "w", encoding="utf-8") as f:
            f.write("ok")

    # IMPORTANT: Playwright expects PLAYWRIGHT_BROWSERS_PATH to point at the directory
    # that CONTAINS the browser folders (chromium-XXXX, firefox-XXXX, etc).
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = targetDir

setPlaywrightBrowserPathForPyinstaller()

DEFAULT_CONFIG = {
    "goodreads_id": "your_goodreads_id_here",
    "discord_app_id": "1356666997760462859",
    "storygraph_username": "your_storygraph_username_here",
    "current_isbn": None,
    "minimizeToTray": True,
    "startOnStartup": False,
    "update_interval": 60,
    "startByDefault": False,
    "platform": "goodreads"
}

def log(message):
    try:
        logPath = os.path.join(os.path.expanduser("~"), ".config", "gr_rpc_log.txt")
        os.makedirs(os.path.dirname(logPath), exist_ok=True)
        with open(logPath, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    except Exception:
        pass

statusInfo = {
    "status": ["Idle"],
    "message": [None],
    "lastUpdated": [None]
}

def updateStatus(status, message=None):
    """Thread-safe status updater consumed by /api/status."""
    ts = time.time()
    with statusLock:
        statusInfo["status"].append(status)
        statusInfo["message"].append(message)
        statusInfo["lastUpdated"].append(ts)

def safeJsonifyError(e, code=500, where="unknown"):
    msg = f"{type(e).__name__}: {e}"
    log(f"[{where}] ERROR: {msg}")
    updateStatus("Error", f"[{where}] {msg}")
    return jsonify({"error": msg}), code

def load_config():
    global CONFIG
    try:
        path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            changed = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
                    changed = True

            with configLock:
                CONFIG = cfg

            if changed:
                save_config_internal()

            log(f"Config loaded from {path}")
        else:
            with configLock:
                CONFIG = DEFAULT_CONFIG.copy()
            save_config_internal()
            log(f"Config created at {path}")

        return CONFIG
    except Exception as e:
        with configLock:
            CONFIG = DEFAULT_CONFIG.copy()
        updateStatus("Error", f"Failed to load config, using defaults: {e}")
        log(f"Failed to load config, using defaults: {e}")
        return CONFIG

def save_config_internal():
    try:
        path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with configLock:
            cfg = dict(CONFIG)

        tmpPath = path + ".tmp"
        with open(tmpPath, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        os.replace(tmpPath, path)
    except Exception as e:
        updateStatus("Error", f"Failed to save config: {e}")
        log(f"Failed to save config: {e}")

CONFIG = load_config()

# Current selection state (protected by booksLock)
currentBook = None
currentIsbn = CONFIG.get("current_isbn")
books = {}

@app.errorhandler(Exception)
def handle_unhandled_error(e):
    return safeJsonifyError(e, code=500, where="GlobalHandler")

# -------------------------
# StoryGraph helpers
# -------------------------
def extractStorygraphBookId(bookUrl):
    if not bookUrl:
        return None
    match = re.search(r"/books/([0-9a-fA-F-]{36})", bookUrl)
    return match.group(1) if match else None

def parseStorygraphStartedDate(containerDiv):
    if not containerDiv:
        return None
    allText = containerDiv.get_text(" ", strip=True)
    match = re.search(r"\bStarted\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b", allText)
    return match.group(1) if match else None

# -------------------------
# Common scraping helpers
# -------------------------
def sanitizeCover(url):
    try:
        if not url:
            return None
        return re.sub(r'\._[A-Z0-9]+_(?=\.(?:jpg|jpeg|png))', '', url, flags=re.IGNORECASE)
    except Exception:
        return url

def safeText(node):
    return node.get_text(strip=True) if node else None

def getPlatformConfigSnapshot():
    """
    Read platform + IDs from CONFIG safely.
    Returns a dict snapshot so we don't keep grabbing locks everywhere.
    """
    with configLock:
        snapshot = {
            "platform": (CONFIG.get("platform") or "goodreads").lower(),
            "goodreads_id": (CONFIG.get("goodreads_id") or "").strip(),
            "storygraph_username": (CONFIG.get("storygraph_username") or "").strip(),
            "discord_app_id": (CONFIG.get("discord_app_id") or "").strip(),
            "update_interval": CONFIG.get("update_interval", 60),
        }
    return snapshot

def get_books():
    cfg = getPlatformConfigSnapshot()
    platform = cfg["platform"]

    if platform == "goodreads":
        goodreadsId = cfg["goodreads_id"]
        try:
            if not goodreadsId:
                updateStatus("Error", "Goodreads ID missing")
                log("Goodreads ID missing in config.")
                return None

            url = f"https://www.goodreads.com/review/list/{goodreadsId}?shelf=currently-reading"
            headers = {"User-Agent": "Mozilla/5.0"}

            updateStatus("Info", f"Fetching books from {url}")
            log(f"Fetching books from {url}")

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                msg = f"Failed to fetch books: {response.status_code} {response.reason}"
                updateStatus("Error", msg)
                log(msg)
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            bookTable = soup.find("table", {"id": "books"})
            if not bookTable:
                updateStatus("Error", "No book table found")
                log("No book table found in the response.")
                return None

            rows = bookTable.find_all("tr", {"id": lambda x: x and x.startswith("review_")})
            if not rows:
                updateStatus("Error", "No book rows found")
                log("No book rows found in the table.")
                return None

            found = {}
            for row in rows:
                try:
                    titleCell = row.find("td", class_="field title")
                    authorCell = row.find("td", class_="field author")
                    coverCell = row.find("td", class_="field cover")
                    dateCell = row.find("td", class_="field date_started")
                    isbnCell = row.find("td", class_="field isbn")

                    title = safeText(titleCell.find("a") if titleCell else None) or "Unknown Title"
                    author = safeText(authorCell.find("a") if authorCell else None) or "Unknown Author"
                    coverArt = sanitizeCover((coverCell.find("img")["src"] if coverCell and coverCell.find("img") else None))

                    startSpan = dateCell.find("span", class_="date_started_value") if dateCell else None
                    startDate = safeText(startSpan)

                    isbnVal = None
                    if isbnCell:
                        valDiv = isbnCell.find("div", class_="value")
                        txt = safeText(valDiv)
                        if txt:
                            isbnVal = txt

                    isbn = isbnVal if isbnVal else f"noisbn-{title}-{author}"

                    found[isbn] = {
                        "isbn": isbn,
                        "title": title,
                        "author": author,
                        "coverArt": coverArt,
                        "startDate": startDate,
                        "platform": "goodreads",
                        "bookUrl": f"https://www.goodreads.com/review/list/{goodreadsId}?shelf=currently-reading"
                    }
                except Exception as rowErr:
                    log(f"Failed to parse a book row: {rowErr}")
                    updateStatus("Error", f"Failed to parse a book row: {rowErr}")

            if not found:
                updateStatus("Error", "Parsed 0 books")
                log("Parsed 0 books.")
                return None

            updateStatus("Active", f"Fetched {len(found)} books (Goodreads)")
            return found

        except Exception as e:
            updateStatus("Error", f"Error fetching books: {e}")
            log(f"Error fetching books: {e}")
            return None

    elif platform == "storygraph":
        storygraphUsername = cfg["storygraph_username"]
        try:
            if not storygraphUsername:
                updateStatus("Error", "StoryGraph username missing")
                log("StoryGraph username missing in config.")
                return None

            url = f"https://app.thestorygraph.com/currently-reading/{storygraphUsername}"

            # Pull cookie from config if present
            rememberUserToken = ""
            with configLock:
                rememberUserToken = (CONFIG.get("storygraph_remember_user_token") or "").strip()

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://app.thestorygraph.com/",
                "Connection": "keep-alive",
            }

            updateStatus("Info", f"Fetching books from {url}")
            log(f"Fetching books from {url}")

            response = requests.get(url, headers=headers, timeout=10)

            htmlText = None

            if response.status_code == 200:
                htmlText = response.text
            elif response.status_code == 403:
                # Fall back to browser-rendered HTML (bypasses the anti-bot 403)
                updateStatus("Info", "StoryGraph blocked requests (403). Using headless browser...")
                log("StoryGraph returned 403; falling back to Playwright...")

                import time as timeModule

                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)

                    context = browser.new_context(
                        viewport={"width": 1280, "height": 720},
                        user_agent=headers["User-Agent"],
                    )

                    # If cookie provided, set it before navigation
                    if rememberUserToken:
                        context.add_cookies([{
                            "name": "remember_user_token",
                            "value": rememberUserToken,
                            "domain": "app.thestorygraph.com",
                            "path": "/",
                            "httpOnly": True,
                            "secure": True,
                            "sameSite": "Lax",
                        }])

                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=30000)

                    # Scroll until page stops growing (lazy-loading)
                    scrollPauseSeconds = 2
                    maxScrolls = 60

                    lastHeight = page.evaluate("document.body.scrollHeight")
                    scrollCount = 0

                    while True:
                        scrollCount += 1
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        timeModule.sleep(scrollPauseSeconds)

                        newHeight = page.evaluate("document.body.scrollHeight")
                        if newHeight == lastHeight:
                            break

                        lastHeight = newHeight
                        if scrollCount >= maxScrolls:
                            break

                    htmlText = page.content()
                    browser.close()
            else:
                msg = f"Failed to fetch books: {response.status_code} {response.reason}"
                updateStatus("Error", msg)
                log(msg)
                return None

            if not htmlText:
                updateStatus("Error", "Failed to fetch StoryGraph HTML")
                log("Failed to fetch StoryGraph HTML (empty).")
                return None

            soup = BeautifulSoup(htmlText, "html.parser")

            # Your existing selector (may be brittle, but keep it for now)
            bookDivs = soup.select("div.grid.grid-cols-12.gap-4.p-4")
            if not bookDivs:
                updateStatus("Error", "No book divs found")
                log("No book divs found in the StoryGraph HTML.")
                return None

            found = {}
            for bookDiv in bookDivs:
                try:
                    titleLink = bookDiv.select_one('h3 a[href^="/books/"]')
                    bookHref = titleLink.get("href") if titleLink else None
                    bookId = extractStorygraphBookId(bookHref)

                    title = safeText(titleLink) or "Unknown Title"

                    authorLink = bookDiv.select_one('a[href^="/authors/"]')
                    author = safeText(authorLink) or "Unknown Author"

                    coverImg = bookDiv.select_one("img")
                    coverArt = coverImg.get("src") if coverImg else None

                    startDate = parseStorygraphStartedDate(bookDiv)

                    bookKey = bookId if bookId else f"nobookid-{title}-{author}"

                    found[bookKey] = {
                        "isbn": bookKey,  # keep API field name stable for the UI
                        "bookId": bookId,
                        "title": title,
                        "author": author,
                        "coverArt": coverArt,
                        "startDate": startDate,
                        "platform": "storygraph",
                        # FIXED: use correct domain
                        "bookUrl": f"https://app.thestorygraph.com{bookHref}" if bookHref else url
                    }
                except Exception as rowErr:
                    log(f"Failed to parse a StoryGraph book block: {rowErr}")
                    updateStatus("Error", f"Failed to parse a StoryGraph book block: {rowErr}")

            if not found:
                updateStatus("Error", "Parsed 0 StoryGraph books")
                log("Parsed 0 StoryGraph books.")
                return None

            updateStatus("Active", f"Fetched {len(found)} books (StoryGraph)")
            return found

        except Exception as e:
            updateStatus("Error", f"Error fetching books: {e}")
            log(f"Error fetching books: {e}")
            return None

    else:
        updateStatus("Error", f"Unknown platform: {platform}")
        log(f"Unknown platform: {platform}")
        return None


@app.route("/api/scraper/get_books", methods=["GET"])
def scraper_get_books():
    try:
        global currentBook, currentIsbn, books

        with booksLock:
            scraped = get_books()
            books = scraped or {}

            if not books:
                updateStatus("Error", "No books found")
                log("No books found.")
                return jsonify({"error": "No books found."}), 404

            # Keep current selection if still valid
            if currentIsbn and currentIsbn in books:
                currentBook = books[currentIsbn]
            else:
                currentBook = next(iter(books.values()))
                currentIsbn = currentBook["isbn"]
                # Persist selection so UI stays consistent across restarts
                with configLock:
                    CONFIG["current_isbn"] = currentIsbn
                save_config_internal()

            init_event.set()
            updateStatus("Active", f"Books ready (current: {currentIsbn})")

            # Keep response format exactly as your UI expects: [books, currentIsbn]
            return jsonify([books, currentIsbn]), 200

    except Exception as e:
        return safeJsonifyError(e, 500, "scraper_get_books")

# -------------------------
# Basic endpoints
# -------------------------
@app.route("/api/hello")
def hello():
    try:
        log("Hello endpoint called.")
        updateStatus("Info", "Hello ping")
        return jsonify({"message": "Hello from Flask!"})
    except Exception as e:
        return safeJsonifyError(e, 500, "hello")

@app.route("/shutdown", methods=["POST"])
def shutdown():
    try:
        log("Shutdown endpoint called.")
        updateStatus("Info", "Shutdown requested")
        pid = os.getpid()
        threading.Thread(target=lambda: os.kill(pid, signal.SIGTERM), daemon=True).start()
        return jsonify({"message": "Flask shutting down..."})
    except Exception as e:
        return safeJsonifyError(e, 500, "shutdown")

@app.route("/api/getStartByDefault", methods=["GET"])
def get_start_by_default():
    try:
        val = bool(CONFIG.get("startByDefault", False))
        updateStatus("Info", f"startByDefault={val}")
        return jsonify({"startByDefault": val})
    except Exception as e:
        return safeJsonifyError(e, 500, "get_start_by_default")

# -------------------------
# Config endpoints
# -------------------------
@app.route("/api/config", methods=["GET"])
def get_config():
    try:
        with configLock:
            cfg = dict(CONFIG)
        updateStatus("Info", "Config served")
        return jsonify(cfg)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_config")

@app.route("/api/config", methods=["POST"])
def update_config():
    try:
        data = request.get_json(silent=True) or {}
        with configLock:
            CONFIG.update(data)
        updateStatus("Active", "Config updated (unsaved)")
        return jsonify({"message": "Config updated successfully."})
    except Exception as e:
        return safeJsonifyError(e, 500, "update_config")

@app.route("/api/config/save", methods=["POST"])
def save_config():
    try:
        updatedConfig = request.get_json(silent=True) or {}
        with configLock:
            CONFIG.update(updatedConfig)
        save_config_internal()
        updateStatus("Active", "Config saved")
        return jsonify({"message": "Config saved successfully."})
    except Exception as e:
        return safeJsonifyError(e, 500, "save_config")

# -------------------------
# Book select endpoints
# -------------------------
@app.route("/api/book/select", methods=["POST"])
def select_book():
    try:
        global currentIsbn, currentBook, books
        data = request.get_json(silent=True) or {}
        isbn = data.get("isbn")

        with booksLock:
            if isbn and isbn in books:
                currentIsbn = isbn
                currentBook = books[isbn]
                with configLock:
                    CONFIG["current_isbn"] = isbn
                save_config_internal()
                updateStatus("Active", f"Book selected: {isbn}")
                return jsonify({"message": "Book selected."})
            else:
                updateStatus("Error", f"Invalid ISBN selection: {isbn}")
                return jsonify({"error": "Invalid ISBN."}), 400

    except Exception as e:
        return safeJsonifyError(e, 500, "select_book")

@app.route("/api/book/current", methods=["GET"])
def get_current_book():
    try:
        updateStatus("Info", "Current book requested")
        return jsonify(currentBook)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_current_book")

# -------------------------
# Status endpoint
# -------------------------
@app.route("/api/status", methods=["GET"])
def get_status():
    try:
        with statusLock:
            tempStatusInfo = {
                "status": list(statusInfo["status"]),
                "message": list(statusInfo["message"]),
                "lastUpdated": list(statusInfo["lastUpdated"])
            }
            statusInfo["status"].clear()
            statusInfo["message"].clear()
            statusInfo["lastUpdated"].clear()
            statusInfo["status"].append("Idle")
            statusInfo["message"].append(None)
            statusInfo["lastUpdated"].append(None)
        return jsonify(tempStatusInfo)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_status")

# -------------------------
# Presence endpoints
# -------------------------
@app.route("/api/presence/start", methods=["POST"])
def presence_start():
    try:
        global presenceThread, currentBook, books, currentIsbn

        should_run_event.set()

        with booksLock:
            scraped = get_books()
            if not scraped:
                updateStatus("Error", "No books found to start presence")
                return jsonify({"error": "No books found."}), 404

            books = scraped

            # Ensure we have a current book
            if (not currentIsbn) or (currentIsbn not in books):
                currentBook = next(iter(books.values()))
                currentIsbn = currentBook["isbn"]
                with configLock:
                    CONFIG["current_isbn"] = currentIsbn
                save_config_internal()
            else:
                currentBook = books[currentIsbn]

        init_event.set()

        if presenceThread is None or not presenceThread.is_alive():
            presenceThread = threading.Thread(target=run_presence, daemon=True, name="PresenceThread")
            presenceThread.start()
            updateStatus("Active", "Presence thread started")
            return jsonify({"message": "Presence thread started."})
        else:
            updateStatus("Info", "Presence thread already running")
            return jsonify({"message": "Presence thread already running."})

    except Exception as e:
        return safeJsonifyError(e, 500, "presence_start")

@app.route("/api/presence/stop", methods=["POST"])
def presence_stop():
    try:
        should_run_event.clear()
        updateStatus("Active", "Presence loop stop requested")
        return jsonify({"message": "Presence loop stopped."})
    except Exception as e:
        return safeJsonifyError(e, 500, "presence_stop")

def run_presence():
    global currentBook, is_running_event, should_run_event, init_event

    log("Presence thread started.")
    try:
        from pypresence import Presence
    except Exception as e:
        updateStatus("Error", f"pypresence import failed: {e}")
        log(f"pypresence not available: {e}")
        return

    try:
        init_event.wait(timeout=10)
        if not init_event.is_set():
            updateStatus("Error", "Presence init timed out")
            log("Presence init_event wait timed out.")
            return

        cfg = getPlatformConfigSnapshot()
        discordAppId = cfg["discord_app_id"]
        if not discordAppId:
            updateStatus("Error", "Discord App ID missing")
            log("Discord App ID missing from config.")
            return

        presence = Presence(discordAppId)
        try:
            presence.connect()
        except Exception as e:
            updateStatus("Error", f"Discord connect failed: {e}")
            log(f"Failed to connect to Discord: {e}")
            return

        is_running_event.set()
        updateStatus("Active", "Discord presence connected")
        log("Discord presence connected.")

        try:
            while should_run_event.is_set():
                try:
                    # re-read config each loop so switching platform works without restarting the backend
                    cfg = getPlatformConfigSnapshot()
                    platform = cfg["platform"]
                    goodreadsId = cfg["goodreads_id"]
                    storygraphUsername = cfg["storygraph_username"]

                    book = currentBook

                    if book:
                        startTs = None
                        try:
                            if book.get("startDate"):
                                # Both platforms use "Jan 13, 2026" style in your parsing
                                startTs = int(time.mktime(time.strptime(book["startDate"], "%b %d, %Y")))
                        except Exception:
                            startTs = None

                        largeImage = book.get("coverArt") or "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/nophoto/book/111x148._SX50_.png"

                        if platform == "storygraph":
                            largeText = "Reading via StoryGraph"
                            buttonUrl = book.get("bookUrl") or f"https://storygraph.com/currently-reading/{storygraphUsername}"
                            buttonLabel = "View on StoryGraph"
                        else:
                            largeText = "Reading via Goodreads"
                            buttonUrl = f"https://www.goodreads.com/review/list/{goodreadsId}?shelf=currently-reading"
                            buttonLabel = "View Goodreads"

                        presence.update(
                            details=book.get("title") or "Unknown Title",
                            state=f"by {book.get('author') or 'Unknown Author'}",
                            large_image=largeImage,
                            large_text=largeText,
                            start=startTs,
                            buttons=[{
                                "label": buttonLabel,
                                "url": buttonUrl
                            }]
                        )

                        updateStatus("Active", f"Presence updated for '{book.get('title')}'")
                    else:
                        updateStatus("Info", "No current book to update")

                    interval = 60
                    try:
                        interval = int(cfg.get("update_interval", 60)) or 60
                    except Exception:
                        interval = 60

                    time.sleep(max(5, min(600, interval)))

                except Exception as loopErr:
                    error = str(loopErr)
                    updateStatus("Error", f"Presence loop error: {error}")
                    log(f"Error updating presence: {error}")

                    try:
                        presence.clear()
                        presence.close()
                    except Exception as clearErr:
                        log(f"Failed to clear presence: {clearErr}")

                    # attempt reconnect
                    try:
                        cfg = getPlatformConfigSnapshot()
                        discordAppId = cfg["discord_app_id"]
                        presence = Presence(discordAppId)
                        presence.connect()
                        updateStatus("Active", "Presence reconnected")
                    except Exception as reconnectErr:
                        updateStatus("Error", f"Reconnect failed: {reconnectErr}")
                        log(f"Reconnect failed: {reconnectErr}")
                        time.sleep(10)
                        continue

        finally:
            log("Presence loop exiting.")
            is_running_event.clear()
            try:
                presence.clear()
                presence.close()
                updateStatus("Info", "Presence cleared on exit")
            except Exception as e:
                log(f"Failed to clear presence on exit: {e}")
                updateStatus("Error", f"Failed to clear presence on exit: {e}")

    except Exception as e:
        log(f"Presence thread fatal: {e}")
        updateStatus("Error", f"Presence fatal: {e}")
        is_running_event.clear()

def run():
    try:
        app.run(host="localhost", port=5000)
    except Exception as e:
        log(f"Flask runtime error: {e}")
        updateStatus("Error", f"Flask runtime error: {e}")

if __name__ == "__main__":
    run()
