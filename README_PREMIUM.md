# PhoenixTrend Premium — Dual Engine Build

This package is a PhoenixTrend-native build, not a Rudhra skin.

## Core execution model
- Strategy Picker: shared strategy library.
- Manual Engine: user selects strategy/symbol, reviews the setup and explicitly submits each order.
- Automatic Engine: user selects a strategy and starts/stops automation; broker execution is gated by connection/risk controls.
- Alpaca credentials: entered from Settings UI and held only in backend process memory in this development build. They are not baked into Docker images or committed to files.
- Default broker choice in the UI is Alpaca Paper Trading.

## Run
From the package root:

    docker compose down --remove-orphans
    docker compose build --no-cache
    docker compose up -d
    docker compose ps

Frontend: http://localhost:8080/login
Backend Swagger: http://localhost:8000/docs

If an older PhoenixTrend container already owns port 8080, stop/remove that old container before starting this package.

## UI assets
The approved PhoenixTrend logo, Earth/market artwork and Phoenix/mountain artwork are included as source assets. The supplied page screenshots are visual references only and are not embedded as page backgrounds.

## Production note
The included login is a development UI flow, not production identity. Before live deployment, add real identity/session management, encrypted secret storage, durable engine state, broker webhooks, stronger order/risk validation, rate limiting and production observability.
