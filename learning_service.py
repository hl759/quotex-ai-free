from __future__ import annotations

from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine

class LearningService:
    def __init__(self):
        self.learning = LearningEngine()
        self.specialists = SpecialistReputationEngine()

    def snapshot(self):
        return {
            "learning": self.learning.memory,
            "specialists": self.specialists.snapshot(limit=50),
        }
