
from flask import Flask, jsonify
from core.scanner import MarketScanner
from core.signal_engine import SignalEngine
from data.data_manager import DataManager
from learning.learning_engine import LearningEngine

app = Flask(__name__)

data_manager = DataManager()
scanner = MarketScanner(data_manager)
signal_engine = SignalEngine()
learning = LearningEngine()

@app.route("/scan-markets")
def scan_markets():
    market_data = scanner.scan_assets()
    signals = signal_engine.generate_signals(market_data)
    learning.update_stats(signals)
    return jsonify(signals)

@app.route("/health")
def health():
    return {"status":"NEXUS v7 running"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
