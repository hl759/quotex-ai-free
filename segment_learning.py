from __future__ import annotations

def segment_key(asset: str, direction: str, regime: str, specialist: str, provider: str, market_type: str, hour_bucket: str, setup_quality: str) -> str:
    return "|".join([
        asset or "unknown",
        direction or "unknown",
        regime or "unknown",
        specialist or "unknown",
        provider or "unknown",
        market_type or "unknown",
        hour_bucket or "unknown",
        setup_quality or "unknown",
    ])
