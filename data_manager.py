
import requests
import time
from config import MAX_DAILY_CREDITS, TIMEFRAME

class DataManager:

    def __init__(self):
        self.cache = {}
        self.credits = 0

    def get_candles(self, symbol):

        if self.credits >= MAX_DAILY_CREDITS:
            return None

        if symbol in self.cache:
            return self.cache[symbol]

        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={TIMEFRAME}&outputsize=50"

        try:
            r = requests.get(url)
            data = r.json()

            if "values" not in data:
                return None

            candles = data["values"]
            self.cache[symbol] = candles
            self.credits += 1

            return candles

        except:
            return None
