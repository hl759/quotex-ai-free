from __future__ import annotations

import uuid

def new_uid(prefix: str = "ah") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
