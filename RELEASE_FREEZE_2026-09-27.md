# PhoenixTrend Production Freeze Candidate — 2026-09-27

Implemented scope:
- Sidebar consolidated: TradeDesk, no Manual Trade/Activity/Analytics standalone nav entries.
- Official PhoenixTrend logo used as enlarged illuminated sidebar emblem; no regenerated logo.
- Existing TradeDesk chart, indicators and fullscreen logic preserved.
- TradeDesk manual order controls wired directly to `/api/manual/analyze` and `/api/manual/order`.
- Market/Limit/Stop/Stop-Limit mappings, quantity validation, required price validation, confirmation, broker-state gating and post-order position refresh included.
- Fixed frontend manual-order payload contract to send `qty`, matching backend `ManualOrderRequest`.
- Added symbol search that loads the selected symbol into the existing TradeDesk chart/workspace.
- `/trade` retained only as compatibility redirect to TradeDesk.
- Portfolio hub now exposes Overview / Activity / Analytics; standalone sidebar entries removed. Compatibility routes retained.
- Phoenix AI renamed to Trady AI in visible UI.
- Trady AI redesigned with exact user-supplied Earth image, Phosphor icons, StockLogo usage, live market snapshot, quick actions, capabilities and existing AI conversation/backend logic.
- Existing Automations implementation left unchanged.
- Existing compact Broker button left unchanged.

Validation performed in build workspace:
- Python backend source compiles with `python -m compileall -q app`.
- Backend pytest: 13 tests pass. 3 legacy HTTP strategy tests expect unauthenticated 200 responses and now receive 401 because production authentication middleware protects `/api/*`; this behavior predates this freeze and matches the application's current auth design.
- .NET SDK is not installed in the artifact workspace, so final Razor compilation must be validated by the included Docker/.NET build on the user's machine.

Freeze rule:
- Treat this package as the baseline after a successful local `docker compose build --no-cache` and smoke test.
