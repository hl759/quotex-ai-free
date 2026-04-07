from alpha_hive.learning.learning_engine import LearningEngine

def test_learning_engine_updates_segments():
    engine = LearningEngine()
    engine.register_outcome("BTCUSDT", "CALL", "trend", "trend", "binance", "crypto", "10:00", "favoravel", "WIN")
    adj = engine.segment_adjustment("BTCUSDT", "CALL", "trend", "trend", "binance", "crypto", "10:00", "favoravel")
    assert "proof_state" in adj
