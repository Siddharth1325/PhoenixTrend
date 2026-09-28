# PhoenixTrend Backend V3 — Pattern + Strategy Decision Engine

The frontend/UI in this package is preserved. This update is backend-focused.

## Decision path

Market snapshot -> indicators -> chart-pattern detector -> all registered strategies -> strategy ranking -> bounded Adaptive Composite (only when useful) -> BUY/SELL/HOLD -> risk -> execution.

## Low-latency design

- One normalized market snapshot per symbol.
- 15-second decision cache by default.
- Pattern recognition and strategy scoring are local deterministic Python calculations.
- No LLM/API model call is placed in the buy/sell critical path.
- Market HTTP results are cached briefly to avoid repeated network calls.

## Pattern families currently detected

- Resistance breakout
- Support breakdown
- Bull trend / bear trend
- Trend pullback
- Double top / double bottom approximation
- Volatility compression
- Bull flag / bear flag approximation

The engine also evaluates EMA20/EMA50, RSI, MACD, ATR, Bollinger Bands, VWAP and volume ratio.

## Adaptive Composite

"Create own strategy" does NOT generate arbitrary executable code. PhoenixTrend can compose a temporary auditable rule profile from approved indicators/pattern evidence. This keeps decisions deterministic and inspectable.

## Safety

Automatic execution remains blocked while the current Yahoo-based market context reports `automatic_execution_safe = false`. This is deliberate. Configure an execution-grade, freshness-verified provider before enabling unattended real-money execution.

## Key endpoints

- `GET /api/analyze/{symbol}` — complete decision
- `GET /api/patterns/{symbol}` — chart patterns
- `GET /api/strategy-selection/{symbol}` — strategy ranking + adaptive result
- `POST /api/manual/analyze` — manual analysis
- `POST /api/automatic/start` — start auto engine with automatic or pinned strategy selection
- `POST /api/automatic/run-cycle` — one guarded automatic cycle

## Validation performed

- Python compileall: passed
- Backend pytest suite: 4 passed
- FastAPI import smoke test: passed
