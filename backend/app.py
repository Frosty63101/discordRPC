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
    "update_interval": 60
}

def load_config():
    global CONFIG
    # load from cross platform safe json config file stored somewhere in user directory
    path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            CONFIG = json.load(f)
    else:
        CONFIG = DEFAULT_CONFIG.copy()
        with open(path, "w") as f:
            json.dump(CONFIG, f)
    
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

#region scraper
def get_books():
    global current_book, goodreads_id
    if goodreads_id:
        url = f"https://www.goodreads.com/review/list/{goodreads_id}?shelf=currently-reading"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        bookTable = soup.find("table", {"id": "books"})
        if not bookTable:
            return None
        rows = bookTable.find_all("tr", {"id": lambda x: x and x.startswith("review_")})
        if not rows:
            return None
        books = {}
        for row in rows:
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
        return None

@app.route("/api/scraper/get_books", methods=["GET"])
def scraper_get_books():
    global current_book, current_isbn
    global books
    books = get_books()
    if books:
        if current_isbn and current_isbn in books:
            current_book = books[current_isbn]
        else:
            current_book = next(iter(books.values()))
            current_isbn = current_book["isbn"]
        init_event.set()
        return jsonify(books, current_isbn), 200
    else:
        return jsonify({"error": "No books found."}), 404

#region API Endpoints
@app.route("/api/hello")
def hello():
    return jsonify({"message": "Hello from Flask!"})

@app.route("/shutdown", methods=["POST"])
def shutdown():
    pid = os.getpid()
    threading.Thread(target=lambda: os.kill(pid, signal.SIGTERM)).start()
    return jsonify({"message": "Flask shutting down..."})

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "Flask is running!"})

@app.route("/api/thread", methods=["POST"])
def thread():
    thread_id = threading.get_ident()
    return jsonify({"thread_id": thread_id})

@app.route("/api/pid", methods=["GET"])
def pid():
    return jsonify({"pid": os.getpid()})

#region Config
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(CONFIG)

@app.route("/api/config", methods=["POST"])
def update_config():
    global CONFIG
    data = request.json
    CONFIG.update(data)
    return jsonify({"message": "Config updated successfully."})

@app.route("/api/config/save", methods=["POST"])
def save_config():
    global CONFIG
    updated_config = request.json
    CONFIG.update(updated_config)
    path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
    with open(path, "w") as f:
        json.dump(CONFIG, f)
    return jsonify({"message": "Config saved successfully."})

@app.route("/api/book/select", methods=["POST"])
def select_book():
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
    path = os.path.join(os.path.expanduser("~"), ".config", "app_config.json")
    with open(path, "w") as f:
        json.dump(CONFIG, f)

@app.route("/api/book/current", methods=["GET"])
def get_current_book():
    return jsonify(current_book)

#region Status
@app.route("/api/status", methods=["GET"])
def get_status():
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
    global presenceThread
    if presenceThread is None:
        presenceThread = threading.Thread(target=run_presence)
        presenceThread.start()
    return jsonify({"message": "Discord presence initialized."})

@app.route("/api/presence/start", methods=["POST"])
def presence_start():
    should_run_event.set()
    return jsonify({"message": "Presence loop started."})

@app.route("/api/presence/stop", methods=["POST"])
def presence_stop():
    should_run_event.clear()
    return jsonify({"message": "Presence loop stopped."})


def run_presence():
    # if the init_event is set then run, otherwise wait for it to be set
    init_event.wait()
    if not is_running_event.is_set():
        # Start the Discord presence
        discord_app_id = CONFIG.get("discord_app_id")
        if not discord_app_id:
            print("Client ID not found in config.")
        presence = pypresence.Presence(discord_app_id)
        presence.connect()
        is_running_event.set()
        while should_run_event.is_set():
            if current_book:
                try:
                    presence.update(
                        details=current_book["title"],
                        state=f"by {current_book['author'] if current_book['author'] else 'Unknown Author'}",
                        large_image=current_book["coverArt"] or "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/nophoto/book/111x148._SX50_.png",
                        large_text="Reading via Goodreads",
                        start=int(time.mktime(time.strptime(current_book["startDate"], "%b %d, %Y"))) if current_book["startDate"] else None,
                        buttons=[{
                            "label": "View Goodreads",
                            "url": f"https://www.goodreads.com/review/list/{goodreads_id}?shelf=currently-reading"
                        }]
                    )
                    statusInfo["status"].append("Active")
                    statusInfo["message"].append("Presence updated successfully.")
                except Exception as e:
                    error_message = str(e).lower()
                    if "pipe" in error_message or "closed" in error_message or isinstance(e, (ConnectionResetError, BrokenPipeError, OSError)):
                        statusInfo["status"].append("Error")
                        statusInfo["message"].append(error_message)
                        statusInfo["lastUpdated"].append(time.time())
                        try:
                            presence.close()
                        except Exception:
                            statusInfo["status"].append("Error")
                            statusInfo["message"].append("Failed to close presence connection.")
                            statusInfo["lastUpdated"].append(time.time())
                            pass
                        try:
                            presence = pypresence.Presence(discord_app_id)
                            presence.connect()
                            presence.update(
                                details=current_book["title"],
                                state=f"by {current_book['author'] if current_book['author'] else 'Unknown Author'}",
                                large_image=current_book["cover"] or "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/nophoto/book/111x148._SX50_.png",
                                large_text="Reading via Goodreads",
                                start=int(time.mktime(time.strptime(current_book["start"], "%b %d, %Y"))) if current_book["start"] else None,
                                buttons=[{
                                    "label": "View Goodreads",
                                    "url": f"https://www.goodreads.com/review/list/{goodreads_id}?shelf=currently-reading"
                                }]
                            )
                            statusInfo["status"].append("Reconnected")
                            statusInfo["message"].append("Reconnected successfully.")
                            statusInfo["lastUpdated"].append(time.time())
                        except Exception as reconnectError:
                            statusInfo["status"].append("Error")
                            statusInfo["message"].append(f"Reconnection failed: {str(reconnectError)}")
                            statusInfo["lastUpdated"].append(time.time())
                            time.sleep(10)
                            continue
                time.sleep(CONFIG.get("update_interval", 15))
    else:
        return jsonify({"message": "Discord presence is already running."})

def run():
    app.run(host="localhost", port=5000)

if __name__ == "__main__":
    run()
