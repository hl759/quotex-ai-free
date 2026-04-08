from __future__ import annotations

from datetime import datetime, timedelta, timezone

BRAZIL_TZ = timezone(timedelta(hours=-3))

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def now_brazil() -> datetime:
    return datetime.now(BRAZIL_TZ)
