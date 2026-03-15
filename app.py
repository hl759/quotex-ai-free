import threading
import time
from flask import Flask, jsonify
from scanner import MarketScanner
from signal_engine import SignalEngine
from data_manager import DataManager
from learning_engine import LearningEngine

app = Flask(__name__)

data_manager = DataManager()
scanner = MarketScanner(data_manager)
signal_engine = SignalEngine()
learning = LearningEngine()

latest_signals = []

def scanner_loop():
    global latest_signals
    while True:
        try:
            market_data = scanner.scan_assets()
            signals = signal_engine.generate_signals(market_data)
            if signals:
                latest_signals = signals
                learning.update_stats(signals)
                print("Signals:", signals, flush=True)
            else:
                print("No signals this cycle", flush=True)
        except Exception as e:
            print(f"Scanner error: {e}", flush=True)
        time.sleep(60)

@app.route("/health")
def health():
    return {"status": "NEXUS v8 running"}

@app.route("/signals")
def signals():
    return jsonify(latest_signals)

thread = threading.Thread(target=scanner_loop, daemon=True)
thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
