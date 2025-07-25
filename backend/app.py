from flask import Flask, jsonify, request
import threading

app = Flask(__name__)

@app.route("/api/hello")
def hello():
    return jsonify({"message": "Hello from Flask!"})

@app.route("/shutdown", methods=["POST"])
def shutdown():
    shutdownFunc = request.environ.get('werkzeug.server.shutdown')
    if shutdownFunc is None:
        return jsonify({"error": "Not running with the Werkzeug Server"}), 500
    shutdownFunc()
    return jsonify({"message": "Shutting down Flask..."})

def run():
    app.run(host="localhost", port=5000)

if __name__ == "__main__":
    run()
