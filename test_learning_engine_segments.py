import tempfile
import unittest
from unittest.mock import patch


class LearningEngineSegmentTests(unittest.TestCase):
    def test_segment_adjustment_appears_after_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('storage_paths.DATA_DIR', tmp), patch('learning_engine.DATA_DIR', tmp), patch('learning_engine.STATE_FILE', f'{tmp}/alpha_hive_learning.json'):
                from importlib import reload
                import learning_engine
                reload(learning_engine)
                engine = learning_engine.LearningEngine()
                signal = {
                    'asset': 'BTCUSDT',
                    'signal': 'CALL',
                    'regime': 'mixed',
                    'strategy_name': 'trend_aligned',
                    'analysis_time': '14:00',
                    'provider': 'binance',
                    'market_type': 'crypto',
                }
                for _ in range(7):
                    engine.register_result(signal, {'result': 'WIN'})
                for _ in range(3):
                    engine.register_result(signal, {'result': 'LOSS'})
                adj = engine.get_segment_adjustment(
                    asset='BTCUSDT',
                    direction='CALL',
                    regime='mixed',
                    strategy_name='trend_aligned',
                    analysis_time='14:10',
                    provider='binance',
                    market_type='crypto',
                )
                self.assertNotEqual(adj['proof_state'], 'building')
                self.assertGreaterEqual(adj['score_boost'], 0.0)
                self.assertGreater(adj['trades'], 0)


if __name__ == '__main__':
    unittest.main()
