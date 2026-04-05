
    # Architecture Overview

    ## Core principles

    1. Preserve the Binary Options intelligence.
    2. Separate signal generation from order execution.
    3. Share learning and risk telemetry across both engines.
    4. Keep secrets backend-only.

    ## Layers

    ### Legacy intelligence layer

    Existing modules remain the reasoning core:

    - scanner
    - indicators
    - decision_engine
    - signal_engine
    - learning_engine
    - self_optimization_engine

    ### Platform layer

    - `core/runtime.py` wires the legacy engines into a service runtime.
    - `services/binance_futures_client.py` encapsulates signed REST calls.
    - `services/execution_service.py` transforms an approved plan into exchange orders.
    - `services/futures_bot_service.py` manages the automated loop.
    - `api/routes/*` exposes a dashboard-ready API surface.
    - `ui/` consumes the API and renders the desk.

    ## Binary Options flow

    `scanner -> indicators -> decision_engine -> signal_engine -> dashboard`

    This branch remains manual-only.

    ## Futures flow

    `scanner -> futures_module -> execution_service -> binance_client -> exchange`

    The self-optimization engine can soften or harden risk, confidence floors, and leverage without replacing the base confluence logic.
