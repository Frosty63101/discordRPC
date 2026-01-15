import json
import logging
import os
import re
import shutil
import signal
import sys
import threading
import time
import zipfile
from logging.handlers import RotatingFileHandler

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

presenceThread = None

statusLock = threading.Lock()
configLock = threading.Lock()
booksLock = threading.Lock()
booksCacheLock = threading.Lock()

init_event = threading.Event()
is_running_event = threading.Event()
should_run_event = threading.Event()

stopSleepEvent = threading.Event()

booksCache = {"timestamp": 0, "platform": None, "data": None}

statusInfo = {"status": ["Idle"], "message": [None], "lastUpdated": [None]}

DEFAULT_CONFIG = {
    "goodreads_id": "your_goodreads_id_here",
    "discord_app_id": "1356666997760462859",
    "storygraph_username": "your_storygraph_username_here",
    "storygraph_remember_user_token": "PASTE_VALUE_HERE",
    "current_isbn": None,
    "minimizeToTray": True,
    "startOnStartup": False,
    "update_interval": 60,
    "startByDefault": False,
    "platform": "goodreads",
}

CONFIG = {}


def getAppDataDir(appName: str) -> str:
    if sys.platform == "win32":
        baseDir = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(baseDir, appName)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", appName)
    baseDir = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(baseDir, appName)


def getCacheDir(appName: str) -> str:
    if sys.platform == "win32":
        baseDir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(baseDir, appName)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches", appName)
    baseDir = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(baseDir, appName)


appDataDir = getAppDataDir("GoodreadsRPC")
cacheDir = getCacheDir("GoodreadsRPC")
os.makedirs(appDataDir, exist_ok=True)
os.makedirs(cacheDir, exist_ok=True)

configPath = os.path.join(appDataDir, "app_config.json")
logPath = os.path.join(appDataDir, "gr_rpc_log.txt")


def setupLogger() -> logging.Logger:
    logger = logging.getLogger("GoodreadsRPC")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    handler = RotatingFileHandler(
        logPath,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setupLogger()


def updateStatus(status: str, message: str | None = None) -> None:
    ts = time.time()
    with statusLock:
        statusInfo["status"].append(status)
        statusInfo["message"].append(message)
        statusInfo["lastUpdated"].append(ts)


def logInfo(message: str, uiStatus: str | None = None) -> None:
    logger.info(message)
    if uiStatus:
        updateStatus(uiStatus, message)


def logWarning(message: str, uiStatus: str | None = None) -> None:
    logger.warning(message)
    if uiStatus:
        updateStatus(uiStatus, message)


def logError(message: str, uiStatus: str | None = None, exc: Exception | None = None) -> None:
    if exc is not None:
        logger.exception(message)
    else:
        logger.error(message)
    if uiStatus:
        updateStatus(uiStatus, message)


def safeJsonifyError(e: Exception, code: int = 500, where: str = "unknown"):
    msg = f"[{where}] {type(e).__name__}: {e}"
    logError(msg, uiStatus="Error", exc=e)
    return jsonify({"error": msg}), code


def buildHttpSession() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


httpSession = buildHttpSession()


def findBundledPlaywrightZip(meipassDir: str) -> str | None:
    directPath = os.path.join(meipassDir, "playwright-browsers.zip")
    if os.path.isfile(directPath):
        return directPath
    if os.path.isdir(directPath):
        nestedPath = os.path.join(directPath, "playwright-browsers.zip")
        if os.path.isfile(nestedPath):
            return nestedPath
        for rootDir, _, fileNames in os.walk(directPath):
            for fileName in fileNames:
                if fileName.lower() == "playwright-browsers.zip":
                    return os.path.join(rootDir, fileName)
    return None


def setPlaywrightBrowserPathForPyinstaller() -> None:
    if not (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")):
        return

    meipassDir = sys._MEIPASS
    bundledZipInMeipass = findBundledPlaywrightZip(meipassDir)
    if not bundledZipInMeipass or not os.path.exists(bundledZipInMeipass):
        logWarning("Playwright zip not found in bundle; StoryGraph may fail.", uiStatus="Info")
        return

    playwrightCacheDir = os.path.join(cacheDir, "discordrpc-playwright")
    extractedBrowsersDir = os.path.join(playwrightCacheDir, "browsers")
    markerPath = os.path.join(playwrightCacheDir, ".extracted-ok")
    cachedZipPath = os.path.join(playwrightCacheDir, "playwright-browsers.zip")

    os.makedirs(playwrightCacheDir, exist_ok=True)

    if not os.path.exists(markerPath):
        if os.path.exists(extractedBrowsersDir):
            shutil.rmtree(extractedBrowsersDir, ignore_errors=True)
        os.makedirs(extractedBrowsersDir, exist_ok=True)

        shutil.copy2(bundledZipInMeipass, cachedZipPath)
        with zipfile.ZipFile(cachedZipPath, "r") as zipRef:
            zipRef.extractall(extractedBrowsersDir)

        with open(markerPath, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))

        logInfo("Extracted Playwright browsers to cache.", uiStatus="Info")

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = extractedBrowsersDir


setPlaywrightBrowserPathForPyinstaller()


def load_config() -> dict:
    global CONFIG
    try:
        if os.path.exists(configPath):
            with open(configPath, "r", encoding="utf-8") as f:
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

            logInfo("Config loaded.", uiStatus="Info")
        else:
            with configLock:
                CONFIG = DEFAULT_CONFIG.copy()
            save_config_internal()
            logInfo("Config created.", uiStatus="Info")

        return CONFIG
    except Exception as e:
        with configLock:
            CONFIG = DEFAULT_CONFIG.copy()
        logError(f"Failed to load config; using defaults: {e}", uiStatus="Error", exc=e)
        return CONFIG


def save_config_internal() -> None:
    try:
        with configLock:
            cfg = dict(CONFIG)

        tmpPath = configPath + ".tmp"
        with open(tmpPath, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        os.replace(tmpPath, configPath)
    except Exception as e:
        logError(f"Failed to save config: {e}", uiStatus="Error", exc=e)


CONFIG = load_config()


def normalizeConfigUpdateKeys(updateDict: dict) -> dict:
    normalized = dict(updateDict or {})
    if "currentIsbn" in normalized and "current_isbn" not in normalized:
        normalized["current_isbn"] = normalized["currentIsbn"]
    if "currentISBN" in normalized and "current_isbn" not in normalized:
        normalized["current_isbn"] = normalized["currentISBN"]
    if "storygraphRememberUserToken" in normalized and "storygraph_remember_user_token" not in normalized:
        normalized["storygraph_remember_user_token"] = normalized["storygraphRememberUserToken"]
    return normalized


def clampConfigValues(cfg: dict) -> dict:
    cleaned = dict(cfg)

    platformValue = (cleaned.get("platform") or "goodreads").lower().strip()
    if platformValue not in ("goodreads", "storygraph"):
        platformValue = "goodreads"
    cleaned["platform"] = platformValue

    try:
        intervalValue = int(cleaned.get("update_interval", 60))
    except Exception:
        intervalValue = 60
    cleaned["update_interval"] = max(5, min(600, intervalValue))

    for boolKey in ("minimizeToTray", "startOnStartup", "startByDefault"):
        if boolKey in cleaned:
            cleaned[boolKey] = bool(cleaned[boolKey])

    for strKey in ("goodreads_id", "discord_app_id", "storygraph_username", "storygraph_remember_user_token", "current_isbn"):
        if strKey in cleaned and cleaned[strKey] is not None:
            cleaned[strKey] = str(cleaned[strKey]).strip()

    return cleaned


currentBook = None
currentIsbn = None
books = {}


def applyConfigToRuntimeState() -> None:
    global currentIsbn, currentBook
    with configLock:
        currentIsbn = CONFIG.get("current_isbn")

    with booksLock:
        if currentIsbn and currentIsbn in books:
            currentBook = books[currentIsbn]
        else:
            currentBook = None


applyConfigToRuntimeState()


@app.errorhandler(Exception)
def handle_unhandled_error(e: Exception):
    return safeJsonifyError(e, code=500, where="GlobalHandler")


def cleanText(textValue: str | None) -> str:
    if not textValue:
        return ""
    return " ".join(textValue.split()).strip()


def sanitizeCover(url: str | None) -> str | None:
    try:
        if not url:
            return None
        return re.sub(r"\._[A-Z0-9]+_(?=\.(?:jpg|jpeg|png))", "", url, flags=re.IGNORECASE)
    except Exception:
        return url


def safeText(node) -> str | None:
    return node.get_text(strip=True) if node else None


def getPlatformConfigSnapshot() -> dict:
    with configLock:
        snapshot = {
            "platform": (CONFIG.get("platform") or "goodreads").lower(),
            "goodreads_id": (CONFIG.get("goodreads_id") or "").strip(),
            "storygraph_username": (CONFIG.get("storygraph_username") or "").strip(),
            "discord_app_id": (CONFIG.get("discord_app_id") or "").strip(),
            "update_interval": CONFIG.get("update_interval", 60),
        }
    return snapshot


def parseStoryGraphCurrentReadsHtml(htmlText: str) -> list[dict]:
    soup = BeautifulSoup(htmlText, "html.parser")
    parsedBooks = []
    bookPanes = soup.select("div.book-pane[data-book-id]")

    for bookPane in bookPanes:
        bookId = (bookPane.get("data-book-id") or "").strip()

        titleLink = bookPane.select_one('h3 a[href^="/books/"]')
        title = titleLink.get_text(strip=True) if titleLink else None
        bookPath = titleLink.get("href") if titleLink else None

        authorLink = bookPane.select_one('a[href^="/authors/"]')
        author = authorLink.get_text(strip=True) if authorLink else None

        seriesLinks = bookPane.select('p a[href^="/series/"]')
        seriesName = seriesLinks[0].get_text(strip=True) if len(seriesLinks) >= 1 else None
        seriesNumber = seriesLinks[1].get_text(strip=True) if len(seriesLinks) >= 2 else None

        coverImg = bookPane.select_one("img")
        coverUrl = coverImg.get("src") if coverImg else None

        startedDate = None
        for pTag in bookPane.select("p"):
            textValue = pTag.get_text(" ", strip=True)
            if "Started " in textValue:
                startedDate = textValue.split("Started ", 1)[1].strip()
                break

        parsedBooks.append(
            {
                "bookId": bookId,
                "title": title,
                "author": author,
                "bookPath": bookPath,
                "coverUrl": coverUrl,
                "startedDate": startedDate,
                "seriesName": seriesName,
                "seriesNumber": seriesNumber,
            }
        )

    return parsedBooks


def chooseStableBookKey(storygraphBook: dict) -> str:
    bookId = (storygraphBook.get("bookId") or "").strip()
    if bookId:
        return f"sg-{bookId}"
    title = (storygraphBook.get("title") or "unknown").strip()
    author = (storygraphBook.get("author") or "unknown").strip()
    return f"sg-noid-{title}-{author}".lower()


def normalizeStorygraphBooksToDict(storygraphBooksList: list[dict]) -> dict:
    normalized = {}
    for book in (storygraphBooksList or []):
        stableKey = chooseStableBookKey(book)

        bookPath = (book.get("bookPath") or "").strip()
        if bookPath.startswith("/"):
            fullBookUrl = f"https://app.thestorygraph.com{bookPath}"
        else:
            fullBookUrl = bookPath or None

        normalized[stableKey] = {
            "isbn": stableKey,
            "title": book.get("title") or "Unknown Title",
            "author": book.get("author") or "Unknown Author",
            "coverArt": sanitizeCover(book.get("coverUrl")),
            "startDate": book.get("startedDate"),
            "platform": "storygraph",
            "bookUrl": fullBookUrl,
            "bookId": book.get("bookId"),
            "series": book.get("seriesName"),
            "seriesNumber": book.get("seriesNumber"),
        }
    return normalized


def get_books() -> dict | None:
    cfg = getPlatformConfigSnapshot()
    platform = cfg["platform"]

    if platform == "goodreads":
        goodreadsId = cfg["goodreads_id"]
        if not goodreadsId:
            logWarning("Goodreads ID missing.", uiStatus="Error")
            return None

        url = f"https://www.goodreads.com/review/list/{goodreadsId}?shelf=currently-reading"
        headers = {"User-Agent": "Mozilla/5.0"}

        logInfo(f"Fetching Goodreads currently-reading for user {goodreadsId}.", uiStatus="Info")

        try:
            response = httpSession.get(url, headers=headers, timeout=10)
        except Exception as e:
            logError(f"Goodreads request failed: {e}", uiStatus="Error", exc=e)
            return None

        if response.status_code != 200:
            logError(f"Goodreads fetch failed: {response.status_code} {response.reason}", uiStatus="Error")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        bookTable = soup.find("table", {"id": "books"})
        if not bookTable:
            logError("Goodreads page parsed but no books table found.", uiStatus="Error")
            return None

        rows = bookTable.find_all("tr", {"id": lambda x: x and x.startswith("review_")})
        if not rows:
            logWarning("Goodreads books table found but no review rows.", uiStatus="Error")
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
                coverArt = sanitizeCover(
                    (coverCell.find("img")["src"] if coverCell and coverCell.find("img") else None)
                )

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
                    "bookUrl": url,
                }
            except Exception as rowErr:
                logWarning(f"Failed to parse a Goodreads row: {rowErr}")

        if not found:
            logWarning("Goodreads parse succeeded but produced 0 books.", uiStatus="Error")
            return None

        logInfo(f"Fetched {len(found)} book(s) from Goodreads.", uiStatus="Active")
        return found

    if platform == "storygraph":
        storygraphUsername = cfg["storygraph_username"]
        if not storygraphUsername:
            logWarning("StoryGraph username missing.", uiStatus="Error")
            return None

        url = f"https://app.thestorygraph.com/currently-reading/{storygraphUsername}"

        with configLock:
            rememberUserToken = (CONFIG.get("storygraph_remember_user_token") or "").strip()

        logInfo(f"Fetching StoryGraph currently-reading for user {storygraphUsername}.", uiStatus="Info")

        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            logError(f"Playwright import failed: {e}", uiStatus="Error", exc=e)
            return None

        htmlText = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                )

                if rememberUserToken and rememberUserToken != "PASTE_VALUE_HERE":
                    context.add_cookies(
                        [
                            {
                                "name": "remember_user_token",
                                "value": rememberUserToken,
                                "domain": "app.thestorygraph.com",
                                "path": "/",
                                "httpOnly": True,
                                "secure": True,
                                "sameSite": "Lax",
                            }
                        ]
                    )

                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if "/users/sign_in" in page.url:
                    logWarning(
                        "StoryGraph requires login or list is private. Add remember_user_token or make profile public.",
                        uiStatus="Error",
                    )
                    browser.close()
                    return None

                page.wait_for_timeout(1500)
                for _ in range(10):
                    page.mouse.wheel(0, 2000)
                    time.sleep(0.5)

                htmlText = page.content()
                browser.close()

        except Exception as e:
            logError(f"StoryGraph Playwright fetch failed: {e}", uiStatus="Error", exc=e)
            return None

        if not htmlText:
            logWarning("StoryGraph fetch returned empty HTML.", uiStatus="Error")
            return None

        storygraphList = parseStoryGraphCurrentReadsHtml(htmlText)
        if not storygraphList:
            logWarning("StoryGraph parsed 0 books.", uiStatus="Error")
            return None

        normalizedDict = normalizeStorygraphBooksToDict(storygraphList)
        if not normalizedDict:
            logWarning("StoryGraph normalize produced 0 books.", uiStatus="Error")
            return None

        logInfo(f"Fetched {len(normalizedDict)} book(s) from StoryGraph.", uiStatus="Active")
        return normalizedDict

    logError(f"Unknown platform: {platform}", uiStatus="Error")
    return None


def getBooksCached(ttlSeconds: int = 60) -> dict | None:
    cfg = getPlatformConfigSnapshot()
    platform = cfg["platform"]
    now = time.time()

    with booksCacheLock:
        if (
            booksCache["data"] is not None
            and booksCache["platform"] == platform
            and (now - booksCache["timestamp"]) < ttlSeconds
        ):
            return booksCache["data"]

    scraped = get_books()
    with booksCacheLock:
        booksCache["timestamp"] = now
        booksCache["platform"] = platform
        booksCache["data"] = scraped
    return scraped


@app.route("/api/hello")
def hello():
    try:
        updateStatus("Info", "Hello ping")
        return jsonify({"message": "Hello from Flask!"})
    except Exception as e:
        return safeJsonifyError(e, 500, "hello")


@app.route("/api/health", methods=["GET"])
def health():
    try:
        cfg = getPlatformConfigSnapshot()
        with statusLock:
            lastStatus = statusInfo["status"][-1] if statusInfo["status"] else None
            lastMessage = statusInfo["message"][-1] if statusInfo["message"] else None
            lastUpdated = statusInfo["lastUpdated"][-1] if statusInfo["lastUpdated"] else None

        data = {
            "ok": True,
            "platform": cfg["platform"],
            "presenceRequested": should_run_event.is_set(),
            "presenceRunning": is_running_event.is_set(),
            "playwrightBrowsersPath": os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
            "lastStatus": lastStatus,
            "lastMessage": lastMessage,
            "lastUpdated": lastUpdated,
        }
        return jsonify(data), 200
    except Exception as e:
        return safeJsonifyError(e, 500, "health")


@app.route("/api/scraper/get_books", methods=["GET"])
def scraper_get_books():
    try:
        global currentBook, currentIsbn, books

        with booksLock:
            scraped = getBooksCached()
            books = scraped or {}

            if not books:
                updateStatus("Error", "No books found.")
                return jsonify({"error": "No books found."}), 404

            if currentIsbn and currentIsbn in books:
                currentBook = books[currentIsbn]
            else:
                currentBook = next(iter(books.values()))
                currentIsbn = currentBook["isbn"]
                with configLock:
                    CONFIG["current_isbn"] = currentIsbn
                save_config_internal()

            init_event.set()
            updateStatus("Active", f"Books ready (current: {currentIsbn})")
            return jsonify([books, currentIsbn]), 200

    except Exception as e:
        return safeJsonifyError(e, 500, "scraper_get_books")


@app.route("/api/scraper/refresh", methods=["POST"])
def scraper_refresh():
    try:
        with booksCacheLock:
            booksCache["timestamp"] = 0
            booksCache["platform"] = None
            booksCache["data"] = None
        updateStatus("Info", "Books cache cleared")
        logInfo("Books cache cleared.", uiStatus=None)
        return jsonify({"message": "Cache cleared."}), 200
    except Exception as e:
        return safeJsonifyError(e, 500, "scraper_refresh")


@app.route("/shutdown", methods=["POST"])
def shutdown():
    try:
        updateStatus("Info", "Shutdown requested")
        logInfo("Shutdown requested.", uiStatus=None)
        pid = os.getpid()
        threading.Thread(target=lambda: os.kill(pid, signal.SIGTERM), daemon=True).start()
        return jsonify({"message": "Flask shutting down..."})
    except Exception as e:
        return safeJsonifyError(e, 500, "shutdown")


@app.route("/api/getStartByDefault", methods=["GET"])
def get_start_by_default():
    try:
        with configLock:
            val = bool(CONFIG.get("startByDefault", False))
        return jsonify({"startByDefault": val})
    except Exception as e:
        return safeJsonifyError(e, 500, "get_start_by_default")


@app.route("/api/config", methods=["GET"])
def get_config():
    try:
        with configLock:
            cfg = dict(CONFIG)
        return jsonify(cfg)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_config")


@app.route("/api/config", methods=["POST"])
def update_config():
    try:
        data = request.get_json(silent=True) or {}
        data = clampConfigValues(normalizeConfigUpdateKeys(data))

        with configLock:
            CONFIG.update(data)

        applyConfigToRuntimeState()

        updateStatus("Active", "Config updated (unsaved)")
        logInfo("Config updated (unsaved).", uiStatus=None)
        return jsonify({"message": "Config updated successfully.", "currentIsbn": currentIsbn, "current_isbn": currentIsbn})
    except Exception as e:
        return safeJsonifyError(e, 500, "update_config")


@app.route("/api/config/save", methods=["POST"])
def save_config():
    try:
        updatedConfig = request.get_json(silent=True) or {}
        updatedConfig = clampConfigValues(normalizeConfigUpdateKeys(updatedConfig))

        with configLock:
            CONFIG.update(updatedConfig)

        save_config_internal()
        applyConfigToRuntimeState()

        updateStatus("Active", "Config saved")
        logInfo("Config saved.", uiStatus=None)
        return jsonify({"message": "Config saved successfully.", "currentIsbn": currentIsbn, "current_isbn": currentIsbn})
    except Exception as e:
        return safeJsonifyError(e, 500, "save_config")


@app.route("/api/book/select", methods=["POST"])
def select_book():
    try:
        global currentIsbn, currentBook, books
        data = request.get_json(silent=True) or {}
        isbn = (data.get("isbn") or "").strip()

        with booksLock:
            if isbn and isbn in books:
                currentIsbn = isbn
                currentBook = books[isbn]
                with configLock:
                    CONFIG["current_isbn"] = isbn
                save_config_internal()
                updateStatus("Active", "Book selected")
                logInfo(f"Book selected: {isbn}", uiStatus=None)
                return jsonify({"message": "Book selected.", "currentIsbn": currentIsbn, "current_isbn": currentIsbn})

        updateStatus("Error", "Invalid ISBN.")
        return jsonify({"error": "Invalid ISBN."}), 400

    except Exception as e:
        return safeJsonifyError(e, 500, "select_book")


@app.route("/api/book/current", methods=["GET"])
def get_current_book():
    try:
        return jsonify(currentBook)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_current_book")


@app.route("/api/status", methods=["GET"])
def get_status():
    try:
        with statusLock:
            tempStatusInfo = {
                "status": list(statusInfo["status"]),
                "message": list(statusInfo["message"]),
                "lastUpdated": list(statusInfo["lastUpdated"]),
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


@app.route("/api/presence/test", methods=["POST"])
def presence_test():
    try:
        from pypresence import Presence
        cfg = getPlatformConfigSnapshot()
        discordAppId = cfg["discord_app_id"]

        if not discordAppId:
            return jsonify({"ok": False, "error": "Discord App ID missing"}), 400

        p = Presence(discordAppId)
        p.connect()
        p.close()
        updateStatus("Info", "Discord RPC test success")
        logger.info("Discord RPC test success.")
        return jsonify({"ok": True, "message": "Connected to Discord RPC successfully."}), 200

    except Exception as e:
        return safeJsonifyError(e, 500, "presence_test")


@app.route("/api/presence/start", methods=["POST"])
def presence_start():
    try:
        global presenceThread, currentBook, books, currentIsbn

        should_run_event.set()

        with booksLock:
            scraped = getBooksCached()
            if not scraped:
                updateStatus("Error", "No books found.")
                return jsonify({"error": "No books found."}), 404

            books = scraped

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
            updateStatus("Active", "Presence started")
            logInfo("Presence thread started.", uiStatus=None)
            return jsonify({"message": "Presence thread started."})

        updateStatus("Info", "Presence already running")
        return jsonify({"message": "Presence thread already running."})

    except Exception as e:
        return safeJsonifyError(e, 500, "presence_start")


@app.route("/api/presence/stop", methods=["POST"])
def presence_stop():
    try:
        should_run_event.clear()
        stopSleepEvent.set()
        stopSleepEvent.clear()
        updateStatus("Active", "Presence stop requested")
        logInfo("Presence stop requested.", uiStatus=None)
        return jsonify({"message": "Presence loop stopped."})
    except Exception as e:
        return safeJsonifyError(e, 500, "presence_stop")


def run_presence():
    global currentBook

    logInfo("Presence thread running.", uiStatus="Info")

    try:
        from pypresence import Presence
    except Exception as e:
        logError(f"pypresence import failed: {e}", uiStatus="Error", exc=e)
        return

    try:
        init_event.wait(timeout=10)
        if not init_event.is_set():
            logWarning("Presence init timed out.", uiStatus="Error")
            return

        cfg = getPlatformConfigSnapshot()
        discordAppId = cfg["discord_app_id"]
        if not discordAppId:
            logWarning("Discord App ID missing.", uiStatus="Error")
            return

        presence = Presence(discordAppId)
        try:
            presence.connect()
        except Exception as e:
            logError(f"Discord connect failed: {e}", uiStatus="Error", exc=e)
            return

        is_running_event.set()
        updateStatus("Active", "Discord presence connected")
        logger.info("Discord presence connected.")

        try:
            while should_run_event.is_set():
                cfg = getPlatformConfigSnapshot()
                platform = cfg["platform"]
                goodreadsId = cfg["goodreads_id"]
                storygraphUsername = cfg["storygraph_username"]

                with booksLock:
                    book = currentBook

                if book:
                    startTs = None
                    try:
                        if book.get("startDate"):
                            startTs = int(time.mktime(time.strptime(book["startDate"], "%b %d, %Y")))
                    except Exception:
                        startTs = None

                    largeImage = "book"
                    largeText = "Reading"
                    buttonUrl = None
                    buttonLabel = None

                    if platform == "storygraph":
                        largeText = "Reading via StoryGraph"
                        buttonUrl = book.get("bookUrl") or f"https://app.thestorygraph.com/currently-reading/{storygraphUsername}"
                        buttonLabel = "View on StoryGraph"
                    else:
                        largeText = "Reading via Goodreads"
                        buttonUrl = f"https://www.goodreads.com/review/list/{goodreadsId}?shelf=currently-reading"
                        buttonLabel = "View Goodreads"

                    try:
                        presence.update(
                            details=book.get("title") or "Unknown Title",
                            state=f"by {book.get('author') or 'Unknown Author'}",
                            large_image=largeImage,
                            large_text=largeText,
                            start=startTs,
                            buttons=[{"label": buttonLabel, "url": buttonUrl}] if buttonUrl and buttonLabel else None,
                        )
                        updateStatus("Active", f"Presence updated: {book.get('title') or 'Unknown Title'}")
                    except Exception as updateErr:
                        logError(f"Presence update failed: {updateErr}", uiStatus="Error", exc=updateErr)
                else:
                    updateStatus("Info", "No current book selected")

                try:
                    interval = int(cfg.get("update_interval", 60)) or 60
                except Exception:
                    interval = 60

                waitSeconds = max(5, min(600, interval))
                stopSleepEvent.wait(timeout=waitSeconds)

        finally:
            is_running_event.clear()
            try:
                presence.clear()
                presence.close()
            except Exception:
                pass
            updateStatus("Info", "Presence cleared")
            logger.info("Presence cleared.")

    except Exception as e:
        logError(f"Presence fatal: {e}", uiStatus="Error", exc=e)
        is_running_event.clear()


def run():
    try:
        logInfo("Flask server starting.", uiStatus="Info")
        app.run(host="localhost", port=5000)
    except Exception as e:
        logError(f"Flask runtime error: {e}", uiStatus="Error", exc=e)


if __name__ == "__main__":
    run()
