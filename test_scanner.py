import unittest
from unittest.mock import patch

from scanner import MarketScanner


class DummyDataManager:
    def __init__(self):
        self.last_provider_used = {}

    def get_candles(self, asset, interval='1min', outputsize=50):
        self.last_provider_used[asset] = 'binance'
        return [
            {'datetime': '2026-01-01 00:00:00', 'open': '100', 'high': '101', 'low': '99', 'close': '100.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:01:00', 'open': '100.5', 'high': '102', 'low': '100', 'close': '101.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:02:00', 'open': '101.5', 'high': '103', 'low': '101', 'close': '102.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:03:00', 'open': '102.5', 'high': '104', 'low': '102', 'close': '103.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:04:00', 'open': '103.5', 'high': '105', 'low': '103', 'close': '104.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:05:00', 'open': '104.5', 'high': '106', 'low': '104', 'close': '105.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:06:00', 'open': '105.5', 'high': '107', 'low': '105', 'close': '106.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:07:00', 'open': '106.5', 'high': '108', 'low': '106', 'close': '107.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:08:00', 'open': '107.5', 'high': '109', 'low': '107', 'close': '108.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:09:00', 'open': '108.5', 'high': '110', 'low': '108', 'close': '109.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:10:00', 'open': '109.5', 'high': '111', 'low': '109', 'close': '110.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:11:00', 'open': '110.5', 'high': '112', 'low': '110', 'close': '111.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:12:00', 'open': '111.5', 'high': '113', 'low': '111', 'close': '112.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:13:00', 'open': '112.5', 'high': '114', 'low': '112', 'close': '113.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:14:00', 'open': '113.5', 'high': '115', 'low': '113', 'close': '114.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:15:00', 'open': '114.5', 'high': '116', 'low': '114', 'close': '115.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:16:00', 'open': '115.5', 'high': '117', 'low': '115', 'close': '116.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:17:00', 'open': '116.5', 'high': '118', 'low': '116', 'close': '117.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:18:00', 'open': '117.5', 'high': '119', 'low': '117', 'close': '118.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:19:00', 'open': '118.5', 'high': '120', 'low': '118', 'close': '119.5', 'volume': '1'},
            {'datetime': '2026-01-01 00:20:00', 'open': '119.5', 'high': '121', 'low': '119', 'close': '120.5', 'volume': '1'},
        ]


class DummyLearning:
    def should_filter_asset(self, asset):
        return False


class ScannerSmokeTest(unittest.TestCase):
    def test_scan_one_enriches_provider_metadata(self):
        scanner = MarketScanner(DummyDataManager(), DummyLearning())
        row = scanner._scan_one('BTCUSDT')
        self.assertEqual(row['provider'], 'binance')
        self.assertIn('provider_trust_score', row)
        self.assertEqual(row['market_type'], 'crypto')
        self.assertIn('provider_trust_score', row['indicators'])


if __name__ == '__main__':
    unittest.main()
