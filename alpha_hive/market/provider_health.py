from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List

@dataclass
class ProviderHealth:
    provider: str
    success_count: int = 0
    failure_count: int = 0
    last_error: str = ""

    def mark_success(self) -> None:
        self.success_count += 1

    def mark_failure(self, error: str = "") -> None:
        self.failure_count += 1
        self.last_error = error[:200]

    def score(self) -> float:
        total = self.success_count + self.failure_count
        if total <= 0:
            return 0.5
        return round(self.success_count / total, 3)

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["score"] = self.score()
        return payload

class ProviderHealthRegistry:
    def __init__(self):
        self._state: Dict[str, ProviderHealth] = {}

    def get(self, provider: str) -> ProviderHealth:
        if provider not in self._state:
            self._state[provider] = ProviderHealth(provider=provider)
        return self._state[provider]

    def mark_success(self, provider: str) -> None:
        self.get(provider).mark_success()

    def mark_failure(self, provider: str, error: str = "") -> None:
        self.get(provider).mark_failure(error)

    def snapshot(self) -> List[Dict[str, object]]:
        return [item.to_dict() for item in self._state.values()]
