from __future__ import annotations

from alpha_hive.core.ids import new_uid

class ContextMemoryEngine:
    def register_context(self, asset: str, regime: str, provider: str, specialist: str) -> str:
        return new_uid(f"ctx-{asset.lower()}-{specialist}")
