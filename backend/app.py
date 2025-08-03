import time
from flask import Flask, jsonify, request
import json
import threading
import signal
import os
import pypresence
import re
import requests
from bs4 import BeautifulSoup
import importlib.util
import importlib.machinery
import py_compile

def load_or_compile_module(filePath, moduleName="custom_module"):
    if not os.path.isfile(filePath):
        log(f"[WARN] Custom module {filePath} not found.")
        return None

    try:
        compiledPath = importlib.util.cache_from_source(filePath)
        if not os.path.exists(compiledPath) or os.path.getmtime(compiledPath) < os.path.getmtime(filePath):
            py_compile.compile(filePath, cfile=compiledPath)
            log(f"[INFO] Compiled {filePath} to {compiledPath}")
    except Exception as e:
        log(f"[ERROR] Compilation failed: {e}")
        return None

    try:
        loader = importlib.machinery.SourcelessFileLoader(moduleName, compiledPath)
        spec = importlib.util.spec_from_loader(moduleName, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        log(f"[INFO] Loaded custom module from {compiledPath}")
        return module
    except Exception as e:
        log(f"[ERROR] Failed to load module: {e}")
        return None

app = Flask(__name__)

presenceThread = None

# Events
init_event = threading.Event()
is_running_event = threading.Event()
should_run_event = threading.Event()

DEFAULT_CONFIG = {
    "goodreads_id": "your_goodreads_id_here",
    "discord_app_id": "your_discord_app_id_here",
    "current_isbn": None,
    "minimizeToTray": True,
    "startOnStartup": False,
    "update_interval": 60,
    "startByDefault": False,
    "presence_template": {
        "details": "{title}",
        "state": "by {author}",
        "large_image": "{coverArt}",
        "large_text": "Reading via Goodreads",
        "start": "{startTimestamp}",
        "buttons": [{
            "label": "View Goodreads",
            "url": "https://www.goodreads.com/review/list/{goodreads_id}?shelf=currently-reading"
        }]
    },
    "custom_vars": {
        "username": "DefaultUser",
        "appName": "GoodreadsRPC"
    }
}

def resolve_template(template, context):
    """
    Recursively replaces placeholders in a dictionary, list, or string
    using the given context dictionary.
    """
    if isinstance(template, dict):
        return {k: resolve_template(v, context) for k, v in template.items()}
    elif isinstance(template, list):
        return [resolve_template(i, context) for i in template]
    elif isinstance(template, str):
        try:
            return template.format(**context)
        except KeyError as e:
            log(f"[WARN] Missing template variable: {e}")
            return template
    else:
        return template  # leave unchanged


def log(message):
    try:
        log_path = os.path.join(os.path.expanduser("~"), ".config", "gr_rpc_log.txt")
        with open(log_path, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    except Exception:
        pass


def load_config():
    global CONFIG
    # load from cross platform safe json config file stored somewhere in user directory
    path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            CONFIG = json.load(f)
        log(f"Config loaded from {path}")
    else:
        CONFIG = DEFAULT_CONFIG.copy()
        with open(path, "w") as f:
            json.dump(CONFIG, f)
        log(f"Config created at {path}")

    return CONFIG

CONFIG = load_config()

current_book = None
current_isbn = CONFIG.get("current_isbn")
goodreads_id = CONFIG.get("goodreads_id")
discord_app_id = CONFIG.get("discord_app_id")
books = {}
statusInfo = {
    "status": ["Idle"],
    "message": [None],
    "lastUpdated": [None]
}

customScraper = None
custom_path = os.path.join(os.path.expanduser("~"), ".config", "custom_scraper.py")
customScraper = load_or_compile_module(custom_path, "custom_scraper")

@app.route("/api/startup/enable", methods=["POST"])
def enable_startup():
    try:
        log("Updating startup preference.")
        import platform
        if platform.system() != "Windows":
            return jsonify({"error": "Startup shortcut only supported on Windows"}), 400
        from win32com.client import Dispatch
        startup_dir = os.path.join(os.getenv('APPDATA'), "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
        shortcut_path = os.path.join(startup_dir, "GoodreadsRPC.lnk")
        script_path = os.path.realpath(sys.argv[0])

        if CONFIG.get("startOnStartup"):
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = script_path
            shortcut.WorkingDirectory = os.path.dirname(script_path)
            shortcut.IconLocation = script_path
            shortcut.save()
        else:
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
        return jsonify({"message": "Startup preference updated."})
    except Exception as e:
        log(f"Error updating startup preference: {e}")
        return jsonify({"error": str(e)}), 500

#region scraper
def get_books():
    global current_book, goodreads_id
    if goodreads_id:
        url = f"https://www.goodreads.com/review/list/{goodreads_id}?shelf=currently-reading"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        log(f"Fetching books from {url}")
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            log(f"Failed to fetch books: {response.status_code} {response.reason}")
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        bookTable = soup.find("table", {"id": "books"})
        if not bookTable:
            log("No book table found in the response.")
            return None
        rows = bookTable.find_all("tr", {"id": lambda x: x and x.startswith("review_")})
        if not rows:
            log("No book rows found in the table.")
            return None
        books = {}
        for row in rows:
            log("Processing book row.")
            title = row.find("td", class_="field title").find("a").get_text(strip=True)
            author = row.find("td", class_="field author").find("a").get_text(strip=True)
            coverArt = row.find("td", class_="field cover").find("img")["src"]
            coverArt = re.sub(r'\._[A-Z0-9]+_(?=\.(jpg|jpeg|png))', '', coverArt, flags=re.IGNORECASE)
            startDateSpan = row.find("td", class_="field date_started").find("span", class_="date_started_value")
            startDate = startDateSpan.get_text(strip=True) if startDateSpan else None
            isbn = row.find("td", class_="field isbn").find("div", class_="value").get_text(strip=True) if row.find("td", class_="field isbn").find("div", class_="value").get_text(strip=True) else f"noisbn-{title}-{author}"
            books[isbn] = { "isbn": isbn, "title": title, "author": author, "coverArt": coverArt, "startDate": startDate }
        return books
    except Exception as e:
        log(f"Error fetching books: {e}")
        return None

@app.route("/api/scraper/get_books", methods=["GET"])
def scraper_get_books():
    global current_book, current_isbn
    global books
    books = customScraper.get_books() if customScraper and hasattr(customScraper, "get_books") else get_books()
    if books:
        log(f"Books fetched: {len(books)} found.")
        if current_isbn and current_isbn in books:
            current_book = books[current_isbn]
        else:
            current_book = next(iter(books.values()))
            current_isbn = current_book["isbn"]
        init_event.set()
        return jsonify(books, current_isbn), 200
    else:
        log("No books found.")
        return jsonify({"error": "No books found."}), 404

#region API Endpoints
@app.route("/api/hello")
def hello():
    log("Hello endpoint called.")
    return jsonify({"message": "Hello from Flask!"})

@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("Shutdown endpoint called.")
    pid = os.getpid()
    threading.Thread(target=lambda: os.kill(pid, signal.SIGTERM)).start()
    return jsonify({"message": "Flask shutting down..."})

@app.route("/status", methods=["GET"])
def status():
    log("Status endpoint called.")
    return jsonify({"status": "Flask is running!"})

@app.route("/api/thread", methods=["POST"])
def thread():
    log("Thread endpoint called.")
    thread_id = threading.get_ident()
    return jsonify({"thread_id": thread_id})

@app.route("/api/pid", methods=["GET"])
def pid():
    log("PID endpoint called.")
    return jsonify({"pid": os.getpid()})

@app.route("/api/getStartByDefault", methods=["GET"])
def get_start_by_default():
    log("Get start by default endpoint called.")
    return jsonify({"startByDefault": CONFIG.get("startByDefault", False)})

#region Config
@app.route("/api/config", methods=["GET"])
def get_config():
    log("Get config endpoint called.")
    return jsonify(CONFIG)

@app.route("/api/config", methods=["POST"])
def update_config():
    log("Update config endpoint called.")
    global CONFIG
    data = request.json
    CONFIG.update(data)
    return jsonify({"message": "Config updated successfully."})

@app.route("/api/config/save", methods=["POST"])
def save_config():
    log("Save config endpoint called.")
    global CONFIG
    updated_config = request.json
    CONFIG.update(updated_config)
    path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
    with open(path, "w") as f:
        json.dump(CONFIG, f, indent=4)
    return jsonify({"message": "Config saved successfully."})

@app.route("/api/book/select", methods=["POST"])
def select_book():
    log("Select book endpoint called.")
    global current_isbn, current_book, books
    data = request.json
    isbn = data.get("isbn")
    if isbn and isbn in books:
        current_isbn = isbn
        current_book = books[isbn]
        CONFIG["current_isbn"] = isbn
        save_config_internal()
        return jsonify({"message": "Book selected."})
    else:
        return jsonify({"error": "Invalid ISBN."}), 400

def save_config_internal():
    log("Internal save config called.")
    path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
    with open(path, "w") as f:
        json.dump(CONFIG, f, indent=4)

@app.route("/api/book/current", methods=["GET"])
def get_current_book():
    log("Get current book endpoint called.")
    return jsonify(current_book)

#region Status
@app.route("/api/status", methods=["GET"])
def get_status():
    log("Get status endpoint called.")
    global statusInfo
    tempStatusInfo = statusInfo.copy()
    statusInfo = {
        "status": ["Idle"],
        "message": [None],
        "lastUpdated": [None]
    }
    return jsonify(tempStatusInfo)

#region Presence
@app.route("/api/presence/initialize", methods=["POST"])
def presence_initialize():
    log("Presence initialize endpoint called.")
    global presenceThread
    if presenceThread is None:
        custom_run = getattr(customScraper, "run_presence", None)
        presenceThread = threading.Thread(target=custom_run if callable(custom_run) else run_presence, daemon=True)
        presenceThread.start()
    return jsonify({"message": "Discord presence initialized."})

@app.route("/api/presence/start", methods=["POST"])
def presence_start():
    log("Presence start endpoint called.")
    global presenceThread, should_run_event, is_running_event, init_event, current_book, books, current_isbn
    should_run_event.set()
    books = customScraper.get_books() if customScraper and hasattr(customScraper, "get_books") else get_books()
    if not books:
        log("No books found.")
        return jsonify({"error": "No books found."}), 404
    if not current_book:
        current_book = next(iter(books.values()))
        current_isbn = current_book["isbn"]
        CONFIG["current_isbn"] = current_isbn
        save_config_internal()
    init_event.set()
    if presenceThread is None or not presenceThread.is_alive():
        log("Starting presence thread.")
        custom_run = getattr(customScraper, "run_presence", None)
        presenceThread = threading.Thread(target=custom_run if callable(custom_run) else run_presence, daemon=True)
        presenceThread.start()
        return jsonify({"message": "Presence thread started."})
    else:
        return jsonify({"message": "Presence thread already running."})


@app.route("/api/presence/stop", methods=["POST"])
def presence_stop():
    log("Presence stop endpoint called.")
    should_run_event.clear()
    return jsonify({"message": "Presence loop stopped."})

@app.route("/api/presence/status", methods=["GET"])
def presence_status():
    log("Presence status endpoint called.")
    return jsonify({
        "running": is_running_event.is_set(),
        "should_run": should_run_event.is_set(),
        "initialized": init_event.is_set(),
        "thread_alive": presenceThread.is_alive() if presenceThread else False
    })

@app.route("/api/custom_script", methods=["GET"])
def get_custom_script():
    try:
        path = os.path.expanduser("~/.config/custom_scraper.py")
        with open(path, "r") as f:
            return f.read(), 200
    except Exception as e:
        return f"# Error loading file: {e}", 500

@app.route("/api/custom_script", methods=["POST"])
def save_custom_script():
    try:
        content = request.data.decode("utf-8")
        path = os.path.expanduser("~/.config/custom_scraper.py")
        with open(path, "w") as f:
            f.write(content)
        return jsonify({"message": "Saved"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_presence():
    global current_book, goodreads_id, is_running_event, should_run_event, init_event, statusInfo
    log("Presence thread started.")
    try:
        from pypresence import Presence
    except ImportError:
        log("pypresence not installed.")
        return

    init_event.wait()  # wait for at least one book to be scraped
    if not is_running_event.is_set():
        discord_app_id = CONFIG.get("discord_app_id")
        if not discord_app_id:
            log("Discord App ID missing from config.")
            return

        presence = Presence(discord_app_id)
        try:
            presence.connect()
        except Exception as e:
            log(f"Failed to connect to Discord: {e}")
            return

        is_running_event.set()
        log("Discord presence connected.")

        try:
            while should_run_event.is_set():
                if current_book:
                    try:
                        log(f"Updating presence for book: {current_book['title']}")
                        context = {
                            "title": current_book.get("title"),
                            "author": current_book.get("author"),
                            "coverArt": current_book.get("coverArt"),
                            "startDate": current_book.get("startDate"),
                            "startTimestamp": int(time.mktime(time.strptime(current_book["startDate"], "%b %d, %Y"))) if current_book.get("startDate") else None,
                            "isbn": current_book.get("isbn"),
                            "goodreads_id": goodreads_id
                        }
                        context.update(CONFIG.get("custom_vars", {}))
                        template = resolve_template(CONFIG.get("presence_template", {}), context)
                        presence.update(**template)
                        statusInfo["status"].append("Active")
                        statusInfo["message"].append("Presence updated successfully.")
                    except Exception as e:
                        log(f"Error updating presence: {e}")
                        error = str(e)
                        statusInfo["status"].append("Error")
                        statusInfo["message"].append(error)
                        statusInfo["lastUpdated"].append(time.time())

                        try:
                            log(f"Error updating presence: {error}")
                            presence.clear()
                            presence.close()
                        except:
                            log("Failed to clear presence.")

                        # attempt reconnect
                        try:
                            log(f"Reconnecting presence due to error: {error}")
                            presence = Presence(discord_app_id)
                            presence.connect()
                        except Exception as reconnectError:
                            log(f"Reconnect failed: {reconnectError}")
                            statusInfo["status"].append("Error")
                            statusInfo["message"].append(f"Reconnect failed: {reconnectError}")
                            statusInfo["lastUpdated"].append(time.time())
                            time.sleep(10)
                            continue
                time.sleep(CONFIG.get("update_interval", 15))
        finally:
            log("Presence loop exiting.")
            is_running_event.clear()
            try:
                log("Clearing presence on exit.")
                presence.clear()
                presence.close()
            except:
                log("Failed to clear presence on exit.")
                pass

def run():
    app.run(host="localhost", port=5000)

if __name__ == "__main__":
    run()
