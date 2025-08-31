import time
from flask import Flask, jsonify, request
import json
import threading
import signal
import os
import sys
import re
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

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

DEFAULT_CONFIG = {
    "goodreads_id": "your_goodreads_id_here",
    "discord_app_id": "1356666997760462859", 
    "current_isbn": None,
    "minimizeToTray": True,
    "startOnStartup": False,
    "update_interval": 60,
    "startByDefault": False
}

def log(message):
    try:
        logPath = os.path.join(os.path.expanduser("~"), ".config", "gr_rpc_log.txt")
        os.makedirs(os.path.dirname(logPath), exist_ok=True)
        with open(logPath, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    except Exception:
        pass

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

CONFIG = load_config()

currentBook = None
currentIsbn = CONFIG.get("current_isbn")
goodreadsId = CONFIG.get("goodreads_id")
books = {}

statusInfo = {
    "status": ["Idle"],
    "message": [None],
    "lastUpdated": [None]
}

@app.errorhandler(Exception)
def handle_unhandled_error(e):
    # Global safety net
    return safeJsonifyError(e, code=500, where="GlobalHandler")

@app.route("/api/startup/enable", methods=["POST"])
def enable_startup():
    try:
        updateStatus("Info", "Updating startup preference")
        log("Updating startup preference.")
        import platform
        if platform.system() != "Windows":
            return jsonify({"error": "Startup shortcut only supported on Windows"}), 400
        try:
            from win32com.client import Dispatch
        except Exception as e:
            return safeJsonifyError(e, 500, "enable_startup(win32com)")
        startupDir = os.path.join(os.getenv('APPDATA'), "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
        shortcutPath = os.path.join(startupDir, "GoodreadsRPC.lnk")
        scriptPath = os.path.realpath(sys.argv[0])

        startOnStartup = bool(CONFIG.get("startOnStartup"))
        if startOnStartup:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcutPath)
            shortcut.Targetpath = scriptPath
            shortcut.WorkingDirectory = os.path.dirname(scriptPath)
            shortcut.IconLocation = scriptPath
            shortcut.save()
            updateStatus("Active", "Startup enabled")
        else:
            if os.path.exists(shortcutPath):
                os.remove(shortcutPath)
            updateStatus("Active", "Startup disabled")
        return jsonify({"message": "Startup preference updated."})
    except Exception as e:
        return safeJsonifyError(e, 500, "enable_startup")

# region scraper
def sanitizeCover(url):
    try:
        if not url:
            return None
        # remove size suffixes
        return re.sub(r'\._[A-Z0-9]+_(?=\.(?:jpg|jpeg|png))', '', url, flags=re.IGNORECASE)
    except Exception:
        return url

def safeText(node):
    return node.get_text(strip=True) if node else None

def get_books():
    global goodreadsId
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

        soup = BeautifulSoup(response.text, 'html.parser')
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

                # Fallback key if isbn is missing
                isbn = isbnVal if isbnVal else f"noisbn-{title}-{author}"

                found[isbn] = {
                    "isbn": isbn,
                    "title": title,
                    "author": author,
                    "coverArt": coverArt,
                    "startDate": startDate
                }
            except Exception as rowErr:
                log(f"Failed to parse a book row: {rowErr}")
                updateStatus("Error", f"Failed to parse a book row: {rowErr}")

        if not found:
            updateStatus("Error", "Parsed 0 books")
            log("Parsed 0 books.")
            return None

        updateStatus("Active", f"Fetched {len(found)} books")
        return found
    except Exception as e:
        updateStatus("Error", f"Error fetching books: {e}")
        log(f"Error fetching books: {e}")
        return None

@app.route("/api/scraper/get_books", methods=["GET"])
def scraper_get_books():
    try:
        global currentBook, currentIsbn, books
        with booksLock:
            books = get_books()
            if books:
                log(f"Books fetched: {len(books)} found.")
                # Keep selection if still valid otherwise pick first
                if currentIsbn and currentIsbn in books:
                    currentBook = books[currentIsbn]
                else:
                    currentBook = next(iter(books.values()))
                    currentIsbn = currentBook["isbn"]
                init_event.set()
                updateStatus("Active", f"Books ready (current: {currentIsbn})")
                return jsonify(books, currentIsbn), 200
            else:
                updateStatus("Error", "No books found")
                log("No books found.")
                return jsonify({"error": "No books found."}), 404
    except Exception as e:
        return safeJsonifyError(e, 500, "scraper_get_books")

# region API Endpoints
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

@app.route("/status", methods=["GET"])
def status():
    try:
        log("Status endpoint called.")
        updateStatus("Info", "Status polled")
        return jsonify({"status": "Flask is running!"})
    except Exception as e:
        return safeJsonifyError(e, 500, "status")

@app.route("/api/thread", methods=["POST"])
def thread():
    try:
        log("Thread endpoint called.")
        threadId = threading.get_ident()
        updateStatus("Info", f"Thread ID reported: {threadId}")
        return jsonify({"thread_id": threadId})
    except Exception as e:
        return safeJsonifyError(e, 500, "thread")

@app.route("/api/pid", methods=["GET"])
def pid():
    try:
        log("PID endpoint called.")
        updateStatus("Info", f"PID reported: {os.getpid()}")
        return jsonify({"pid": os.getpid()})
    except Exception as e:
        return safeJsonifyError(e, 500, "pid")

@app.route("/api/getStartByDefault", methods=["GET"])
def get_start_by_default():
    try:
        log("Get start by default endpoint called.")
        val = bool(CONFIG.get("startByDefault", False))
        updateStatus("Info", f"startByDefault={val}")
        return jsonify({"startByDefault": val})
    except Exception as e:
        return safeJsonifyError(e, 500, "get_start_by_default")

# region Config
@app.route("/api/config", methods=["GET"])
def get_config():
    try:
        log("Get config endpoint called.")
        with configLock:
            cfg = dict(CONFIG)
        updateStatus("Info", "Config served")
        return jsonify(cfg)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_config")

@app.route("/api/config", methods=["POST"])
def update_config():
    try:
        log("Update config endpoint called.")
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
        log("Save config endpoint called.")
        updatedConfig = request.get_json(silent=True) or {}
        with configLock:
            CONFIG.update(updatedConfig)
        save_config_internal()
        updateStatus("Active", "Config saved")
        return jsonify({"message": "Config saved successfully."})
    except Exception as e:
        return safeJsonifyError(e, 500, "save_config")

def save_config_internal():
    try:
        log("Internal save config called.")
        path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
        with configLock:
            cfg = CONFIG
        tmpPath = path + ".tmp"
        with open(tmpPath, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        os.replace(tmpPath, path)
    except Exception as e:
        updateStatus("Error", f"Failed to save config: {e}")
        log(f"Failed to save config: {e}")

@app.route("/api/book/select", methods=["POST"])
def select_book():
    try:
        log("Select book endpoint called.")
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
        log("Get current book endpoint called.")
        updateStatus("Info", "Current book requested")
        return jsonify(currentBook)
    except Exception as e:
        return safeJsonifyError(e, 500, "get_current_book")

# region Status
@app.route("/api/status", methods=["GET"])
def get_status():
    try:
        log("Get status endpoint called.")
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

# region Presence
@app.route("/api/presence/initialize", methods=["POST"])
def presence_initialize():
    try:
        log("Presence initialize endpoint called.")
        global presenceThread
        if presenceThread is None or not presenceThread.is_alive():
            presenceThread = threading.Thread(target=run_presence, daemon=True, name="PresenceThread")
            presenceThread.start()
            updateStatus("Active", "Presence thread initialized")
            return jsonify({"message": "Discord presence initialized."})
        else:
            updateStatus("Info", "Presence thread already initialized")
            return jsonify({"message": "Discord presence already initialized."})
    except Exception as e:
        return safeJsonifyError(e, 500, "presence_initialize")

@app.route("/api/presence/start", methods=["POST"])
def presence_start():
    try:
        log("Presence start endpoint called.")
        global presenceThread, currentBook, books, currentIsbn
        should_run_event.set()
        with booksLock:
            scraped = get_books()
            if not scraped:
                updateStatus("Error", "No books found to start presence")
                return jsonify({"error": "No books found."}), 404
            books = scraped
            if not currentBook:
                currentBook = next(iter(books.values()))
                currentIsbn = currentBook["isbn"]
                with configLock:
                    CONFIG["current_isbn"] = currentIsbn
                save_config_internal()
        init_event.set()
        if presenceThread is None or not presenceThread.is_alive():
            log("Starting presence thread.")
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
        log("Presence stop endpoint called.")
        should_run_event.clear()
        updateStatus("Active", "Presence loop stop requested")
        return jsonify({"message": "Presence loop stopped."})
    except Exception as e:
        return safeJsonifyError(e, 500, "presence_stop")

@app.route("/api/presence/status", methods=["GET"])
def presence_status():
    try:
        log("Presence status endpoint called.")
        running = is_running_event.is_set()
        shouldRun = should_run_event.is_set()
        initialized = init_event.is_set()
        threadAlive = presenceThread.is_alive() if presenceThread else False
        updateStatus("Info", f"Presence status r:{running} s:{shouldRun} i:{initialized} t:{threadAlive}")
        return jsonify({
            "running": running,
            "should_run": shouldRun,
            "initialized": initialized,
            "thread_alive": threadAlive
        })
    except Exception as e:
        return safeJsonifyError(e, 500, "presence_status")

def run_presence():
    global currentBook, goodreadsId, is_running_event, should_run_event, init_event
    log("Presence thread started.")
    try:
        from pypresence import Presence
    except Exception as e:
        updateStatus("Error", f"pypresence import failed: {e}")
        log(f"pypresence not available: {e}")
        return

    try:
        init_event.wait(timeout=10)  # don't wait forever
        if not init_event.is_set():
            updateStatus("Error", "Presence init timed out")
            log("Presence init_event wait timed out.")
            return

        discordAppId = None
        with configLock:
            discordAppId = CONFIG.get("discord_app_id")
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
                    book = currentBook
                    if book:
                        startTs = None
                        try:
                            if book.get("startDate"):
                                startTs = int(time.mktime(time.strptime(book["startDate"], "%b %d, %Y")))
                        except Exception:
                            startTs = None

                        largeImage = book.get("coverArt") or "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/nophoto/book/111x148._SX50_.png"

                        presence.update(
                            details=book.get("title") or "Unknown Title",
                            state=f"by {book.get('author') or 'Unknown Author'}",
                            large_image=largeImage,
                            large_text="Reading via Goodreads",
                            start=startTs,
                            buttons=[{
                                "label": "View Goodreads",
                                "url": f"https://www.goodreads.com/review/list/{goodreadsId}?shelf=currently-reading"
                            }]
                        )
                        updateStatus("Active", f"Presence updated for '{book.get('title')}'")
                    else:
                        updateStatus("Info", "No current book to update")
                    interval = 15
                    try:
                        with configLock:
                            interval = int(CONFIG.get("update_interval", 15)) or 15
                    except Exception:
                        interval = 15
                    time.sleep(max(5, min(600, interval)))
                except Exception as loopErr:
                    error = str(loopErr)
                    updateStatus("Error", f"Presence loop error: {error}")
                    log(f"Error updating presence: {error}")
                    # Try to clear and reconnect
                    try:
                        presence.clear()
                        presence.close()
                    except Exception as clearErr:
                        log(f"Failed to clear presence: {clearErr}")
                    # attempt reconnect
                    try:
                        presence = Presence(discordAppId)
                        presence.connect()
                        updateStatus("Active", "Presence reconnected")
                    except Exception as reconnectErr:
                        updateStatus("Error", f"Reconnect failed: {reconnectErr}")
                        log(f"Reconnect failed: {reconnectErr}")
                        time.sleep(10)
                        # keep loop alive; don't crash
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
        # Absolutely never let presence thread crash the process
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
