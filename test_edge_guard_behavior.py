import unittest
from unittest.mock import patch

from edge_guard import EdgeGuardEngine


class EdgeGuardBehaviorTests(unittest.TestCase):
    @patch('edge_guard.EdgeAuditEngine.compute_report')
    @patch('edge_guard.EdgeAuditEngine.load_ledger')
    def test_strong_setup_keeps_cautela_during_severe_recent_drift(self, mock_load_ledger, mock_report):
        mock_load_ledger.return_value = []
        mock_report.return_value = {
            'summary': {
                'total': 18,
                'expectancy_r': -0.08,
                'profit_factor': 0.94,
                'winrate': 51.0,
                'breakeven_winrate': 55.0,
                'posterior_prob_edge': 0.46,
            },
            'recent_20': {
                'total': 20,
                'expectancy_r': -0.09,
                'profit_factor': 0.96,
                'posterior_prob_edge': 0.48,
            },
            'recent_12': {
                'total': 12,
                'expectancy_r': -0.18,
                'profit_factor': 0.81,
                'posterior_prob_edge': 0.26,
            },
            'top_assets': [],
            'weak_assets': [],
            'top_regimes': [],
            'top_strategies': [],
            'top_hours': [],
        }
        engine = EdgeGuardEngine()
        guard = engine.evaluate(
            asset='BTCUSDT',
            regime='mixed',
            strategy_name='trend_aligned',
            analysis_time='10:30',
            proposed_decision='ENTRADA_FORTE',
            proposed_score=4.6,
            proposed_confidence=82,
        )
        self.assertEqual(guard.get('execution_permission'), 'CAUTELA_OPERAVEL')
        self.assertFalse(guard.get('hard_block'))
        self.assertGreater(guard.get('stake_multiplier', 0.0), 0.0)


if __name__ == '__main__':
    unittest.main()
