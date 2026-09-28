# PhoenixTrend Arena / Phoenix Flight

Integrated into the existing PhoenixTrend package without replacing existing pages, trading services, strategies, layouts, or broker execution code.

## Added
- `frontend/PhoenixTrend.Web/Pages/Arena.razor`
- `frontend/PhoenixTrend.Web/wwwroot/css/pages/arena.css` (premium glass UI; scoped under `.arena-page`)
- `frontend/PhoenixTrend.Web/wwwroot/js/pages/arena.js` (server-synced animation/client)
- `frontend/PhoenixTrend.Web/wwwroot/assets/arena/*`
- `backend/app/services/arena.py` (isolated server-authoritative virtual-coin round engine)
- Arena API endpoints in `backend/app/main.py`
- Arena sidebar navigation entry in `Shared/MainLayout.razor`
- Arena CSS registration in `wwwroot/index.html`

## Behavior
The backend commits a random crash multiplier before each countdown. The frontend polls server state and renders the multiplier/flight. The SVG trail and Phoenix use the exact same calculated endpoint, so the line terminates at the bird instead of extending ahead of it. Bet, cancel, and cash-out requests are validated on the backend.

Phoenix Coins are virtual-only. The Arena service does not call Alpaca, execution_service, AutomaticEngine, ManualEngine, or any brokerage endpoint.

## Run
Use the existing project workflow:

```powershell
docker compose up --build
```

Then open the existing PhoenixTrend UI and select **Arena** in the sidebar.

## Validation performed in this environment
- Python syntax compilation passed for `backend/app/main.py` and `backend/app/services/arena.py`.
- Arena service smoke test passed for startup, state, place-bet, balance debit, cancel-bet, and balance refund.
- The CSS contains over 1,000 lines and is scoped to the Arena page.
- This environment does not have the .NET SDK or Docker installed, so the final Blazor/Docker compilation could not be executed here. The existing Dockerfile remains unchanged.

## Production note
The round engine is server-authoritative, but player identity currently uses a browser-generated Arena player ID because this project package does not contain an authenticated user identity provider. Before public deployment, bind `player_id` to the authenticated PhoenixTrend account on the backend and persist Arena balances/round ledgers in PostgreSQL rather than process memory.
