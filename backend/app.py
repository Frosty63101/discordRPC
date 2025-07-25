from flask import Flask, jsonify
import threading

app = Flask(__name__)

@app.route("/api/hello")
def hello():
    return jsonify({"message": "Hello from Flask!"})

def run():
    app.run(host="localhost", port=5000)

if __name__ == "__main__":
    run()
