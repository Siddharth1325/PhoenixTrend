# PhoenixTrend implementation status

## Implemented in this package
- Premium Blazor shell and responsive PhoenixTrend visual system
- Home command center and 5Y/MAX chart workstation
- REST market/chart/intelligence/discovery/strategies/automations/trade/positions/analytics/activity APIs
- Market WebSocket stream
- Strategy contract + 9 working rule-based strategy modules
- TradeIntent model
- Risk Engine with buying power, position value, max positions, daily-loss and stop validation
- MANUAL / CONTROLLED / AUTOMATIC policy separation
- Paper Broker adapter
- Auditable trade-intent, risk-decision and fill events
- Position-management service hooks for stop/target/trailing logic
- Automation service
- Persistence with SQLAlchemy (SQLite local, PostgreSQL in Docker)
- Docker Compose for API/PostgreSQL/Redis
- Backend tests for core safety boundary
- Production hardening checklist

## Requires provider configuration before real-money production
- Licensed real-time/historical market-data provider
- Broker/venue credentials and broker-specific adapter
- Options chains/Greeks data provider
- Social/news feeds
- SEC insider and institutional filing ingestion
- Authentication/SSO and user/tenant authorization
- Durable event queue, HA workers, reconciliation and operational monitoring
- Compliance/legal review appropriate to intended users/jurisdictions

## Deliberate safety default
The included execution adapter is paper-only. This prevents an unconfigured build from placing real-money orders.
