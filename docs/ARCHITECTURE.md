# Architecture

## Immutable execution boundary
`Strategy -> Signal -> TradeIntent -> RiskEngine -> ExecutionPolicy -> BrokerAdapter`.
No strategy module imports a broker adapter.

## Execution modes
- MANUAL: analysis only
- CONTROLLED: risk-approved intent waits for human approval
- AUTOMATIC: risk-approved intent may be routed automatically inside pre-authorized limits

## Real data adapters still required before production
The repository contains interfaces/demo providers for market, social, news, SEC/insider, institutional and broker data. Configure licensed/authorized providers and validate venue entitlements before production use.

## Production hardening checklist
Authentication/OIDC, per-user RBAC, encrypted secrets, broker OAuth/key vault, durable queues, exactly-once/idempotent order routing, reconciliation, corporate actions, exchange calendars, partial fills, cancel/replace, stale-price rejection, circuit breakers, metrics/tracing, HA workers, PITR backups, immutable audit storage, strategy versioning, live/paper environment isolation and compliance review.
