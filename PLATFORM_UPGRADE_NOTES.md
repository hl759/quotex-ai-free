# Platform Upgrade Notes

## Summary

This upgrade keeps the original Alpha Hive Binary Options intelligence and wraps it in a platform architecture suitable for a hybrid operating model:

- **Binary Options:** manual signal desk only
- **Binance Futures:** automated execution path
- **Self-Optimization:** shared journal and adaptive risk controls
- **Full-stack delivery:** Flask API backend + Next.js dashboard

## Main engineering decisions

1. **Preserve, do not replace**
   - The legacy binary reasoning core remains intact.
   - New services are added around it.

2. **Separate signal from execution**
   - Binary tab never executes trades.
   - Futures execution is isolated inside the backend.

3. **Backend-only secrets**
   - API keys are accepted by the backend and held in a process-local vault.
   - Production recommendation remains environment variables or external secret manager.

4. **Shared adaptive intelligence**
   - Both engines continue to feed the self-optimization layer.
   - Risk, confidence, and leverage are adjusted conservatively.

## Practical result

You now have:

- a preserved binary engine for manual use
- a futures execution stack with signed Binance requests
- a polling dashboard with two main tabs
- deployment scaffolding for local Docker or split frontend/backend deployment
