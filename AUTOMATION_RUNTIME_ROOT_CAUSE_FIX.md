# Automation Runtime Root Cause Fix

The asset automation runtimes were resolving internal services using module names such as `backend.app.broker` and `backend.app.services.*`.

The Docker image starts Uvicorn as `app.main:app` with the backend directory as the Python import root. In that runtime, `backend.app.*` is not importable. `BaseAssetAutomation._resolve_service()` silently returned `None`, so Stocks, Options, Crypto and ETF capability checks concluded that the configured broker did not support order execution. The master endpoint still returned HTTP 200 because the child runtime returned a BLOCKED status rather than raising.

Fixes:
- `_resolve_service()` now supports both `backend.app.*` and `app.*` module layouts.
- Asset automation broker resolution now includes the actual exported `alpaca_broker` singleton.
- Verified with a connected mock broker state that Stocks, Options, Crypto and ETFs transition to `RUNNING` and remain running after the event loop yields.
- Python compile validation passes.
