# Hybrid Self-Optimizing Upgrade

## Added modules

- `binary_options_module.py`
- `futures_module.py`
- `self_optimization_engine.py`
- `hybrid_mode_router.py`

## New routes

- `GET/POST /mode`
- `GET /hybrid/snapshot`
- `GET/POST /hybrid/run-scan`
- `GET /binary/analyze`
- `GET /futures/analyze`
- `POST /futures/execute`
- `POST /futures/close-report`

## Compatibility

Legacy routes and the original binary scan loop remain intact.
The hybrid layer was added alongside the existing architecture so the current binary workflow is preserved.
