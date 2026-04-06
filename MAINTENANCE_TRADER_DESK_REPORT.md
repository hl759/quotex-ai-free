# Maintenance + Trader Desk Review Report

## Current architecture
- `app.py` orchestrates scanner loop, persistence, snapshot/UI routes, and result registration.
- `scanner.py` pulls candles via `data_manager.py`, computes indicators, and forwards asset candidates into `decision_engine.py`.
- `decision_engine.py` fuses strategy/context/capital/risk/council logic into one master decision.
- `signal_engine.py` mirrors the master decision into a single signal payload.
- `learning_engine.py`, `journal_manager.py`, `edge_audit.py`, `memory_engine.py`, and related modules maintain adaptive memory.
- `state_store.py` and `storage_governance_engine.py` handle durability/governance.

## Strongest parts
- Clear hierarchy: Decision is the master and Signals mirror it.
- Rich multi-layer desk logic: context, capital, risk, council, memory, edge guard.
- Good defensive philosophy already present.

## Highest risks found
1. `state_store.py` pruning/vacuum methods were not attached to `StateStore`.
2. `app.py` bundled all HTML/CSS/JS inline, increasing maintenance risk.
3. Breakout/rejection/timing logic was directionally good but too permissive for M1 binary execution.
4. Provider fallback trust was not being priced into the decision strongly enough.
5. Learning memory was too coarse (mostly asset-level).

## Ranked changes applied
1. Fixed `StateStore` governance methods.
2. Moved UI into `templates/index.html` while preserving Flask/Render runtime.
3. Made scanner concurrency configurable via `SCANNER_MAX_WORKERS`.
4. Added safer HTTP session reuse with light retries in `data_manager.py`.
5. Tightened indicator quality model for breakout/rejection/timing.
6. Tightened decision scoring with trader-style execution filters.
7. Added segmented learning memory (asset/hour/regime/strategy/direction/provider/market_type).
8. Added `.gitignore`, safer dependency ranges, and smoke tests.

## Validation
- `python -m compileall .` ✅
- `python -m unittest discover -s tests -v` ✅
- Direct `import app` was not validated here because Flask is not installed in this sandbox.
