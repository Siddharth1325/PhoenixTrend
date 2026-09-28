# PhoenixTrend — Trading Automation Universe

PhoenixTrend is a full-stack reference implementation of the approved product architecture:
market data → discovery/intelligence → strategy → TradeIntent → risk → execution policy → broker → positions → analytics/audit.

## What is included
- FastAPI backend with REST + WebSockets
- Strategy framework with Momentum, Breakout, VWAP, ORB, Gap & Go, Swing Trend, Pullback, Mean Reversion and Trend Following
- TradeIntent, risk gate, manual/controlled/automatic execution modes
- Paper broker adapter and deterministic simulated fills
- Position management hooks for stop/target/trailing logic
- Automation engine and scheduler loop
- Market-data + historical chart API with generated demo bars out of the box
- Intelligence/discovery services with explicit provenance/freshness fields
- PostgreSQL-ready SQLAlchemy models; SQLite default for easy local startup
- Redis-ready cache/pubsub interface with in-memory fallback
- Activity/audit logging and analytics endpoints
- Blazor WebAssembly frontend shell with premium PhoenixTrend styling
- Lightweight Charts integration for TradingView-like candlesticks/volume/crosshair/zoom
- Dockerfiles + docker-compose
- Pytest suite for the critical risk/execution separation

## Important production note
This package is a runnable engineering foundation, not a promise of investment performance. Strategies must be backtested, paper-traded and monitored before any live-broker use. The included broker is paper-only by default.

## Quick start — backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```
Open http://localhost:8080/docs

## Quick start — frontend
```bash
cd frontend/PhoenixTrend.Web
 dotnet run
```
Set `ApiBaseUrl` in `wwwroot/appsettings.json` if needed.

## Docker
```bash
docker compose up --build
```

## Safety model
A strategy never sends an order directly to a broker. All execution follows:
`Strategy -> TradeIntent -> RiskEngine -> ExecutionPolicy -> BrokerAdapter`.

Default execution mode is PAPER. Live broker adapters are intentionally stubs until credentials, venue-specific capability checks, idempotency, reconciliation, compliance controls and explicit user authorization are configured.
