from config import ASSETS
from indicators import IndicatorEngine

class MarketScanner:

    def __init__(self, data_manager):
        self.data = data_manager
        self.indicators = IndicatorEngine()

    def scan_assets(self):

        results = []

        for asset in ASSETS:

            candles = self.data.get_candles(asset)

            if not candles:
                continue

            indicators = self.indicators.calculate(candles)

            results.append({
                "asset": asset,
                "candles": candles,
                "indicators": indicators
            })

        return results
