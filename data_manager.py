import time
import requests
from config import MAX_DAILY_CREDITS, MAX_PER_MINUTE, TIMEFRAME

class DataManager:
    def __init__(self):
        self.cache = {}
        self.credits_today = 0
        self.requests_minute = 0
        self.minute_start = time.time()

    def allow_request(self):
        if self.credits_today >= MAX_DAILY_CREDITS:
            return False
        if time.time() - self.minute_start > 60:
            self.minute_start = time.time()
            self.requests_minute = 0
        if self.requests_minute >= MAX_PER_MINUTE:
            return False
        return True

    def get_candles(self, symbol):
        if symbol in self.cache:
            return self.cache[symbol]
        if not self.allow_request():
            return None

        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={TIMEFRAME}&outputsize=50"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            if "values" not in data:
                return None
            candles = data["values"]
            self.cache[symbol] = candles
            self.credits_today += 1
            self.requests_minute += 1
            return candles
        except Exception:
            return None
            
