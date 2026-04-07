from __future__ import annotations

import os
import tempfile

import pytest

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ALPHA_HIVE_DB_PATH", os.path.join(tmp, "state.db"))
        monkeypatch.setenv("ALPHA_HIVE_DATA_DIR", tmp)
        yield
