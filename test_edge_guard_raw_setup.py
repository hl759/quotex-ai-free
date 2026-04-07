import unittest

from edge_guard import EdgeGuardEngine


class EdgeGuardRawSetupTests(unittest.TestCase):
    def test_strong_raw_setup_avoids_hard_block_on_severe_recent(self):
        guard = EdgeGuardEngine()
        guard.audit.compute_report = lambda: {
            'summary': {'total': 40, 'expectancy_r': -0.02, 'profit_factor': 0.98, 'winrate': 54.0, 'breakeven_winrate': 50.0, 'posterior_prob_edge': 0.56},
            'recent_20': {'total': 14, 'expectancy_r': -0.07, 'profit_factor': 0.92, 'posterior_prob_edge': 0.46},
            'recent_16': {'total': 16, 'expectancy_r': -0.22, 'profit_factor': 0.80, 'posterior_prob_edge': 0.22},
            'top_assets': [],
            'weak_assets': [],
            'top_regimes': [],
            'top_strategies': [],
            'top_hours': [],
        }
        result = guard.evaluate(
            asset='BTCUSDT',
            regime='mixed',
            strategy_name='trend_aligned',
            analysis_time='14:00',
            proposed_decision='OBSERVAR',
            proposed_score=4.8,
            proposed_confidence=84,
            setup_operable_raw=True,
            setup_strong_raw=True,
            structural_score_raw=4.8,
            structural_direction_raw='PUT',
            structural_quality_raw='premium',
        )
        self.assertFalse(result['hard_block'])
        self.assertEqual(result['execution_permission'], 'CAUTELA_OPERAVEL')


if __name__ == '__main__':
    unittest.main()
