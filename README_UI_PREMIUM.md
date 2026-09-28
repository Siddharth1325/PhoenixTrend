# PhoenixTrend Premium UI — Approved Build

This package keeps the existing FastAPI Phoenix Engine backend intact and replaces the placeholder frontend pages with a full Blazor WebAssembly implementation matching the approved PhoenixTrend visual direction.

## Included pages
Login, Broker Connection, Home, Markets, Discover, Charts, Strategies, Automations, Trade, Portfolio, Risk, Phoenix AI, Activity, Analytics and Settings.

## Backend wiring
The frontend `Services/PhoenixApi.cs` is the single API gateway for the UI. It connects the screens to the existing backend endpoints for health, market data, charts, analysis, discovery, intelligence, news, strategies, automations, broker status/account/positions, engine status, manual analysis/orders, automatic engine control, positions, analytics and activity.

The UI intentionally shows polished fallback/demo values when an optional live data source or broker is unavailable. Money-moving actions still go through the existing backend execution and risk path; the browser never bypasses the backend risk/execution architecture.

## Run with Docker
From the package root:

```bash
docker compose up --build
```

Open `http://localhost:8080`. The frontend calls the backend on `http://localhost:8000` as configured in `frontend/PhoenixTrend.Web/wwwroot/appsettings.json`.

## Run locally
Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend/PhoenixTrend.Web
dotnet run
```

## Main frontend files
- `Shared/MainLayout.razor` — premium shell, navigation, top market strip and backend status.
- `Pages/*.razor` — complete page layouts.
- `Components/*` — reusable panels, metrics and chart primitives.
- `Services/PhoenixApi.cs` — backend integration.
- `wwwroot/css/phoenixtrend.css` — complete high-end visual system with enlarged typography and responsive rules.
- `wwwroot/js/phoenix-premium.js` — interaction/motion layer.
- `wwwroot/assets/phoenixtrend-logo.png` — supplied PhoenixTrend logo.
- `wwwroot/assets/phoenix-mountain-horizontal.png` — approved horizontal mountain/phoenix artwork.
- `wwwroot/assets/phoenix-mountain-water-vertical.png` — approved vertical mountain/water artwork without the bird.
- `wwwroot/assets/approved-ui/` — approved/generated UI reference renders retained with the package.

## UI design rules
The shell uses a fixed cinematic sidebar, mountain/phoenix banner, obsidian/navy glass cards, Phoenix orange/gold interaction accents, emerald positive data, red risk/loss data and slightly larger typography than the original prototype. The UI is designed primarily for desktop trading workstations and remains usable down to approximately 1180px wide.
