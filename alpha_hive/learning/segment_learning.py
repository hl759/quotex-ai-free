from __future__ import annotations

from typing import Any, Dict

EXTRA_CONTEXT_KEYS = (
    "trend_m1",
    "trend_m5",
    "multi_tf_conflict",
    "breakout_quality",
    "rejection_quality",
    "explosive_expansion",
    "late_entry_risk",
    "is_sideways",
    "trend_quality_signal",
    "consensus_quality",
)


def _normalize_context_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "1" if value else "0"
    text = str(value).strip()
    return text or "unknown"


def segment_key(
    asset: str,
    direction: str,
    regime: str,
    specialist: str,
    provider: str,
    market_type: str,
    hour_bucket: str,
    setup_quality: str,
    extra_context: Dict[str, Any] | None = None,
) -> str:
    parts = [
        asset or "unknown",
        direction or "unknown",
        regime or "unknown",
        specialist or "unknown",
        provider or "unknown",
        market_type or "unknown",
        hour_bucket or "unknown",
        setup_quality or "unknown",
    ]
    if extra_context:
        for key in EXTRA_CONTEXT_KEYS:
            if key in extra_context:
                parts.append(f"{key}={_normalize_context_value(extra_context.get(key))}")
    return "|".join(parts)
