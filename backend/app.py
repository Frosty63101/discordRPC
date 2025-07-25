from flask import Flask, jsonify, request
import threading
import signal
import os

app = Flask(__name__)

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

def run():
    app.run(host="localhost", port=5000)

if __name__ == "__main__":
    run()
