# backend/app/main.py

from __future__ import annotations

import asyncio
import json
import uuid

from typing import Any, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from sqlalchemy import select

from .broker import alpaca_broker
from .automations import asset_automations, get_asset_automation
from .config import settings
from .db import AuditEvent, SessionLocal, init_db

from .domain import (
    AccountState,
    AlpacaConnectRequest,
    EngineModeRequest,
    ExecutionMode,
    ManualOrderRequest,
    Side,
    TradeIntent,
)

from .engines import (
    AutomaticEngine,
    ManualEngine,
    StrategyPicker,
)

from .services.analytics import analytics_service
from .services.arena import arena_service
from .services.automation import automation_engine
from .services.auth import AuthError, auth_service
from .services.decision_engine import decision_engine
from .services.discovery import discovery_service
from .services.execution import execution_service
from .services.intelligence import intelligence_service
from .services.live_market import live_market_service
from .services.market import market_service
from .services.market_safety import market_safety_service
from .services.news import news_service
from .services.positions import position_engine
from .services.strategy_management import strategy_management_service


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title=settings.app_name,
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# AUTHENTICATION
# ============================================================

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    username: str = Field(default="", max_length=80)
    display_name: str = Field(default="", max_length=160)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "").strip()

    if not header.lower().startswith("bearer "):
        return None

    token = header[7:].strip()

    return token or None


_PUBLIC_API_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/health",
    "/health",
}


@app.middleware("http")
async def require_application_auth(
    request: Request,
    call_next,
):
    # Browser CORS preflight requests must not require application
    # authentication. CORSMiddleware is responsible for validating
    # and answering the preflight request.
    if request.method.upper() == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    if (
        not path.startswith("/api/")
        or path in _PUBLIC_API_PATHS
        or path.startswith("/api/docs")
        # Arena is a virtual Phoenix Coins simulation. The page itself is
        # protected by the Blazor auth guard, but its polling/action API must
        # not invalidate the user's application session. Keeping these routes
        # outside the global API middleware also matches their player_id based
        # server-authoritative design.
        or path.startswith("/api/arena/")
    ):
        return await call_next(request)

    token = _bearer_token(request)

    user = auth_service.authenticate(token)

    if user is None:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Authentication required",
            },
        )

    request.state.user = user

    return await call_next(request)


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    try:
        result = auth_service.register(
            email=req.email,
            username=req.username,
            display_name=req.display_name,
            password=req.password,
        )

    except AuthError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "token": result.token,
        "expires_at": result.expires_at,
        "user": result.user,
    }


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    try:
        result = auth_service.login(
            email=req.email,
            password=req.password,
        )

    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
        ) from exc

    return {
        "token": result.token,
        "expires_at": result.expires_at,
        "user": result.user,
    }


@app.get("/api/auth/me")
def auth_me(request: Request):
    return request.state.user


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    auth_service.logout(
        _bearer_token(request)
    )

    return {
        "ok": True,
    }


# ============================================================
# ENGINES
# ============================================================

strategy_picker = StrategyPicker()

manual_engine = ManualEngine(
    strategy_picker
)

automatic_engine = AutomaticEngine(
    strategy_picker,
    execution_service,
    market_safety_service,
)


# ============================================================
# API REQUEST MODELS
# ============================================================

class ArenaBetRequest(BaseModel):
    player_id: str = Field(
        min_length=1,
        max_length=64,
    )

    player_name: str = Field(
        default="Phoenix Trader",
        max_length=32,
    )

    amount: int = Field(
        ge=100,
        le=2500,
    )


class ArenaPlayerRequest(BaseModel):
    player_id: str = Field(
        min_length=1,
        max_length=64,
    )

    player_name: str = Field(
        default="Phoenix Trader",
        max_length=32,
    )


class AnalyzeRequest(BaseModel):
    symbol: str
    force: bool = False


class ManualAnalyzeRequest(BaseModel):
    symbol: str
    strategy: Optional[str] = None


class AutoStartRequest(BaseModel):
    strategy: Optional[str] = None
    auto_select_strategy: bool = True


class AutoCycleRequest(BaseModel):
    symbol: str

    quantity: float = Field(
        gt=0
    )

    strategy: Optional[str] = None
    automation_id: Optional[str] = None


class AutomationCreateRequest(BaseModel):
    name: str

    symbols: list[str] = Field(
        default_factory=list
    )

    strategy: Optional[str] = None

    auto_select_strategy: bool = True

    max_position_value: float = Field(
        default=2500.0,
        gt=0,
    )

    enabled: bool = False

    asset_class: str = "stocks"

    trading_style: str = "intraday"

    capital_allocation: Optional[float] = Field(
        default=None,
        gt=0,
    )

    max_daily_loss: Optional[float] = Field(
        default=None,
        gt=0,
    )

    max_open_positions: Optional[int] = Field(
        default=None,
        gt=0,
    )

    allow_long: bool = True
    allow_short: bool = False


class AutomationUpdateRequest(BaseModel):
    name: Optional[str] = None

    symbols: Optional[list[str]] = None

    strategy: Optional[str] = None

    auto_select_strategy: Optional[bool] = None

    max_position_value: Optional[float] = Field(
        default=None,
        gt=0,
    )

    asset_class: Optional[str] = None

    trading_style: Optional[str] = None

    capital_allocation: Optional[float] = Field(
        default=None,
        gt=0,
    )

    max_daily_loss: Optional[float] = Field(
        default=None,
        gt=0,
    )

    max_open_positions: Optional[int] = Field(
        default=None,
        gt=0,
    )

    allow_long: Optional[bool] = None
    allow_short: Optional[bool] = None


class StrategyConfigurationRequest(BaseModel):
    configuration: dict[str, Any] = Field(
        default_factory=dict
    )

    replace: bool = False


class CustomStrategyRequest(BaseModel):
    name: str
    base_strategy: str

    configuration: dict[str, Any] = Field(
        default_factory=dict
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup() -> None:
    init_db()

    automation_engine.initialize_database_state()

    execution_service.broker = alpaca_broker

    await arena_service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    try:
        await automation_engine.stop_all_runtimes()
        await _stop_all_asset_automations()

    except Exception:
        pass

    try:
        automatic_engine.stop()

    except Exception:
        pass

    try:
        await arena_service.stop()

    except Exception:
        pass


# ============================================================
# ARENA
# ============================================================

@app.get("/api/arena/state")
async def arena_state(
    player_id: str = "local-player",
    player_name: str = "Phoenix Trader",
):
    return await arena_service.snapshot(
        player_id,
        player_name,
    )


@app.post("/api/arena/bet")
async def arena_bet(
    request: ArenaBetRequest,
):
    try:
        return await arena_service.place_bet(
            request.player_id,
            request.player_name,
            request.amount,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/api/arena/cancel")
async def arena_cancel(
    request: ArenaPlayerRequest,
):
    try:
        return await arena_service.cancel_bet(
            request.player_id,
            request.player_name,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/api/arena/cashout")
async def arena_cashout(
    request: ArenaPlayerRequest,
):
    try:
        return await arena_service.cash_out(
            request.player_id,
            request.player_name,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ============================================================
# ACCOUNT STATE
# ============================================================

def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _portfolio_metrics() -> dict[str, Any]:
    """Build real account metrics from Alpaca account + portfolio history."""
    account = alpaca_broker.account()
    positions = alpaca_broker.positions()

    equity = _finite_number(account.get("equity"))
    last_equity = _finite_number(account.get("last_equity"))
    buying_power = _finite_number(account.get("buying_power"))
    cash = _finite_number(account.get("cash"))
    portfolio_value = _finite_number(account.get("portfolio_value"))

    daily_pnl = (
        equity - last_equity
        if equity is not None and last_equity is not None
        else None
    )

    history: dict[str, Any] | None = None
    try:
        history = alpaca_broker.portfolio_history(period="1M", timeframe="1D")
    except Exception:
        # Account/positions are still authoritative even when the broker's
        # optional history endpoint is temporarily unavailable.
        history = None

    equity_series: list[float] = []
    timestamps: list[Any] = []
    if isinstance(history, dict):
        raw_equity = history.get("equity")
        raw_timestamps = history.get("timestamp")
        if isinstance(raw_equity, list):
            for value in raw_equity:
                parsed = _finite_number(value)
                if parsed is not None:
                    equity_series.append(parsed)
        if isinstance(raw_timestamps, list):
            timestamps = raw_timestamps

    weekly_pnl: float | None = None
    if equity_series:
        current = equity if equity is not None else equity_series[-1]
        # Daily broker history gives us an actual observed week baseline.
        baseline_index = max(0, len(equity_series) - 6)
        baseline = equity_series[baseline_index]
        weekly_pnl = current - baseline

    gross_exposure = sum(
        abs(value)
        for value in (
            _finite_number(position.get("market_value"))
            for position in positions
        )
        if value is not None
    )

    max_drawdown_percent: float | None = None
    total_return_percent: float | None = None
    if len(equity_series) >= 2 and equity_series[0] > 0:
        total_return_percent = (
            (equity_series[-1] - equity_series[0]) / equity_series[0] * 100.0
        )
        peak = equity_series[0]
        max_dd = 0.0
        for value in equity_series:
            peak = max(peak, value)
            if peak > 0:
                max_dd = max(max_dd, (peak - value) / peak * 100.0)
        max_drawdown_percent = max_dd

    return {
        "account": account,
        "positions": positions,
        "equity": equity,
        "last_equity": last_equity,
        "buying_power": buying_power,
        "cash": cash,
        "portfolio_value": portfolio_value,
        "daily_pnl": daily_pnl,
        "weekly_pnl": weekly_pnl,
        "gross_exposure": gross_exposure,
        "equity_history": equity_series,
        "timestamps": timestamps,
        "max_drawdown_percent": max_drawdown_percent,
        "total_return_percent": total_return_percent,
    }


def account_state() -> AccountState:
    if not alpaca_broker.status().get("connected"):
        raise HTTPException(status_code=400, detail="Connect Alpaca first.")

    metrics = _portfolio_metrics()
    account = metrics["account"]

    return AccountState(
        buying_power=metrics["buying_power"],
        daily_pnl=metrics["daily_pnl"],
        weekly_pnl=metrics["weekly_pnl"],
        open_positions=len(metrics["positions"]),
        gross_exposure=metrics["gross_exposure"],
        equity=metrics["equity"],
        cash=metrics["cash"],
        portfolio_value=metrics["portfolio_value"],
        account_status=str(account.get("status") or "") or None,
        trading_blocked=account.get("trading_blocked"),
        account_blocked=account.get("account_blocked"),
        trade_suspended_by_user=account.get("trade_suspended_by_user"),
        source="alpaca",
    )


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "engine": "PhoenixTrend",
        "broker": alpaca_broker.status(),
        "market": market_service.status(),
        "intelligence": intelligence_service.status(),
        "automatic": automatic_engine.status(),
    }


# ============================================================
# MARKET
# ============================================================

@app.get("/api/market/{symbol}")
def quote(
    symbol: str,
):
    return market_service.quote(
        symbol
    )


@app.get("/api/chart/{symbol}")
def chart(
    symbol: str,
    range: str = "3M",
    timeframe: str = "1D",
):
    return market_service.bars(
        symbol,
        range,
        timeframe,
    )


@app.get("/api/chart/{symbol}/latest")
def chart_latest(
    symbol: str,
    timeframe: str = "1M",
):
    return market_service.latest_bar(
        symbol,
        timeframe,
    )


@app.get("/api/chart/{symbol}/levels")
def chart_levels(
    symbol: str,
    range: str = "6M",
    timeframe: str = "1D",
    lookback: int = 120,
):
    safe_lookback = max(
        10,
        min(
            int(
                lookback
            ),
            1000,
        ),
    )

    return market_service.support_resistance(
        symbol,
        range,
        timeframe,
        safe_lookback,
    )


@app.get("/api/chart/{symbol}/events")
def chart_events(
    symbol: str,
    range: str = "5Y",
):
    return market_service.corporate_events(
        symbol,
        range,
    )


@app.get("/api/market-context/{symbol}")
def context(
    symbol: str,
):
    market = market_service.context(
        symbol
    )

    return {
        key: value
        for key, value
        in market.items()
        if key != "bars"
    }


# ============================================================
# DECISION ENGINE
# ============================================================

@app.post("/api/analyze")
def analyze(
    req: AnalyzeRequest,
):
    return decision_engine.analyze(
        req.symbol,
        req.force,
    )


@app.get("/api/analyze/{symbol}")
def analyze_symbol(
    symbol: str,
    force: bool = False,
):
    return decision_engine.analyze(
        symbol,
        force,
    )


# ============================================================
# PATTERNS
# ============================================================

@app.get("/api/patterns/{symbol}")
def patterns(
    symbol: str,
):
    decision = decision_engine.analyze(
        symbol
    )

    return {
        "symbol": symbol.upper(),
        "patterns": decision[
            "patterns"
        ],
        "market": decision[
            "market"
        ],
    }


# ============================================================
# STRATEGY SELECTION
# ============================================================

@app.get(
    "/api/strategy-selection/{symbol}"
)
def strategy_selection(
    symbol: str,
):
    decision = decision_engine.analyze(
        symbol
    )

    selection = (
        decision.get(
            "selection"
        )
        or {}
    )

    return {
        "symbol": symbol.upper(),

        "action": decision.get(
            "action",
            "HOLD",
        ),

        "confidence": decision.get(
            "confidence",
            0.0,
        ),

        "selected_strategy": decision.get(
            "strategy"
        ),

        "selected": decision.get(
            "selected"
        ),

        "ranking": selection.get(
            "ranked",
            [],
        ),

        "adaptive": decision.get(
            "adaptive"
        ),

        "automatic_execution_safe": decision.get(
            "automatic_execution_safe",
            False,
        ),
    }


# ============================================================
# DISCOVERY
# ============================================================

@app.get("/api/discover")
def discover(
    symbols: str = "NVDA,AAPL,MSFT",
):
    requested_symbols = [
        symbol.strip()
        for symbol
        in symbols.split(",")
        if symbol.strip()
    ]

    return discovery_service.scan(
        requested_symbols
    )


@app.get(
    "/api/discover/category/{category}"
)
def discover_category(
    category: str,
    symbols: str | None = None,
):
    requested_symbols = None

    if symbols:
        requested_symbols = [
            symbol.strip()
            for symbol
            in symbols.split(",")
            if symbol.strip()
        ]

    try:
        return discovery_service.scan_category(
            category,
            requested_symbols,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/discover/unusual-activity"
)
def discover_unusual_activity(
    symbols: str | None = None,
    min_ratio: float = 1.5,
    limit: int = 20,
):
    requested_symbols = None

    if symbols:
        requested_symbols = [
            symbol.strip()
            for symbol
            in symbols.split(",")
            if symbol.strip()
        ]

    return discovery_service.unusual_activity(
        requested_symbols,
        min_ratio=min_ratio,
        limit=limit,
    )


# ============================================================
# INTELLIGENCE
# ============================================================

@app.get(
    "/api/intelligence/{symbol}"
)
def intelligence(
    symbol: str,
):
    return intelligence_service.snapshot(
        symbol
    )


# ============================================================
# NEWS
# ============================================================

@app.get(
    "/api/news/{symbol}"
)
def news(
    symbol: str,
    limit: int = 20,
):
    return news_service.for_symbol(
        symbol,
        limit,
    )


# ============================================================
# STRATEGIES
# ============================================================

@app.get("/api/strategies")
def strategies():
    catalog = strategy_picker.catalog()

    output: list[
        dict[str, Any]
    ] = []

    for item in catalog:
        row = dict(
            item
        )

        name = str(
            row.get(
                "name"
            )
            or row.get(
                "strategy"
            )
            or ""
        ).strip()

        row[
            "performance"
        ] = (
            analytics_service.strategy(
                name
            )
            if name
            else None
        )

        output.append(
            row
        )

    for custom in (
        strategy_management_service
        .custom_list()
    ):
        row = dict(
            custom
        )

        name = str(
            row.get(
                "name"
            )
            or row.get(
                "strategy"
            )
            or ""
        ).strip()

        row[
            "performance"
        ] = (
            analytics_service.strategy(
                name
            )
            if name
            else None
        )

        output.append(
            row
        )

    return output


@app.post(
    "/api/strategies/custom"
)
def create_custom_strategy(
    req: CustomStrategyRequest,
):
    try:
        return (
            strategy_management_service
            .create_custom(
                req.name,
                req.base_strategy,
                req.configuration,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.delete(
    "/api/strategies/custom/{strategy_name}"
)
def delete_custom_strategy(
    strategy_name: str,
):
    try:
        (
            strategy_management_service
            .delete_custom(
                strategy_name
            )
        )

        return {
            "deleted": True,
            "strategy": strategy_name,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/strategies/{strategy_name}"
)
def strategy_detail(
    strategy_name: str,
):
    try:
        custom = (
            strategy_management_service
            .custom_get(
                strategy_name
            )
        )

        detail = (
            custom
            if custom is not None
            else (
                strategy_management_service
                .get(
                    strategy_name
                )
            )
        )

        wanted = strategy_picker.resolve_name(
            strategy_name
        )

        performance = analytics_service.strategy(
            wanted
        )

        return {
            **detail,
            "performance": performance,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/strategies/{strategy_name}/performance"
)
def strategy_performance(
    strategy_name: str,
):
    try:
        wanted = strategy_picker.resolve_name(
            strategy_name
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    performance = analytics_service.strategy(
        wanted
    )

    if performance is not None:
        return performance

    return {
        "strategy": wanted,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "win_rate": None,
        "realized_pnl": None,
        "gross_profit": None,
        "gross_loss": None,
        "profit_factor": None,
        "average_trade": None,
        "average_win": None,
        "average_loss": None,
        "largest_win": None,
        "largest_loss": None,
        "total_return": None,
        "source": "persisted trade_records",
    }


@app.post(
    "/api/strategies/{strategy_name}/enable"
)
def enable_strategy(
    strategy_name: str,
):
    try:
        custom = (
            strategy_management_service
            .custom_get(
                strategy_name
            )
        )

        if custom is not None:
            return (
                strategy_management_service
                .set_custom_enabled(
                    strategy_name,
                    True,
                )
            )

        return (
            strategy_management_service
            .enable(
                strategy_name
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/strategies/{strategy_name}/disable"
)
def disable_strategy(
    strategy_name: str,
):
    try:
        custom = (
            strategy_management_service
            .custom_get(
                strategy_name
            )
        )

        if custom is not None:
            return (
                strategy_management_service
                .set_custom_enabled(
                    strategy_name,
                    False,
                )
            )

        return (
            strategy_management_service
            .disable(
                strategy_name
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.put(
    "/api/strategies/{strategy_name}/configuration"
)
def configure_strategy(
    strategy_name: str,
    req: StrategyConfigurationRequest,
):
    try:
        custom = (
            strategy_management_service
            .custom_get(
                strategy_name
            )
        )

        if custom is not None:
            return (
                strategy_management_service
                .update_custom_configuration(
                    strategy_name,
                    req.configuration,
                )
            )

        return (
            strategy_management_service
            .update_configuration(
                strategy_name,
                req.configuration,
                replace=req.replace,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.delete(
    "/api/strategies/{strategy_name}/configuration"
)
def reset_strategy_configuration(
    strategy_name: str,
):
    try:
        custom = (
            strategy_management_service
            .custom_get(
                strategy_name
            )
        )

        if custom is not None:
            return (
                strategy_management_service
                .reset_custom_configuration(
                    strategy_name
                )
            )

        return (
            strategy_management_service
            .reset_configuration(
                strategy_name
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# ============================================================
# AUTOMATIONS
# ============================================================

@app.get(
    "/api/automations"
)
def automations():
    return automation_engine.list()


@app.get(
    "/api/automations/runtime"
)
def automation_runtimes():
    return automation_engine.runtime_list()


@app.post(
    "/api/automations"
)
def create_automation(
    req: AutomationCreateRequest,
):
    try:
        return automation_engine.create(
            name=req.name,
            symbols=req.symbols,
            strategy=req.strategy,
            auto_select_strategy=(
                req.auto_select_strategy
            ),
            max_position_value=(
                req.max_position_value
            ),
            enabled=req.enabled,
            asset_class=req.asset_class,
            trading_style=req.trading_style,
            capital_allocation=(
                req.capital_allocation
            ),
            max_daily_loss=(
                req.max_daily_loss
            ),
            max_open_positions=(
                req.max_open_positions
            ),
            allow_long=req.allow_long,
            allow_short=req.allow_short,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/update"
)
def update_automation(
    automation_id: str,
    req: AutomationUpdateRequest,
):
    try:
        return automation_engine.update(
            automation_id,
            name=req.name,
            symbols=req.symbols,
            strategy=req.strategy,
            auto_select_strategy=(
                req.auto_select_strategy
            ),
            max_position_value=(
                req.max_position_value
            ),
            asset_class=req.asset_class,
            trading_style=req.trading_style,
            capital_allocation=(
                req.capital_allocation
            ),
            max_daily_loss=(
                req.max_daily_loss
            ),
            max_open_positions=(
                req.max_open_positions
            ),
            allow_long=req.allow_long,
            allow_short=req.allow_short,
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/enable"
)
def enable_automation(
    automation_id: str,
):
    try:
        return automation_engine.enable(
            automation_id
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/disable"
)
def disable_automation(
    automation_id: str,
):
    try:
        return automation_engine.disable(
            automation_id
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/pause"
)
def pause_automation(
    automation_id: str,
):
    try:
        return (
            automation_engine
            .pause_entries(
                automation_id
            )
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/resume"
)
def resume_automation(
    automation_id: str,
):
    try:
        return (
            automation_engine
            .resume_entries(
                automation_id
            )
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/start"
)
async def start_automation_runtime(
    automation_id: str,
):
    try:
        return await (
            automation_engine
            .start_runtime(
                automation_id
            )
        )

    except (
        KeyError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/stop"
)
async def stop_automation_runtime(
    automation_id: str,
):
    try:
        return await (
            automation_engine
            .stop_runtime(
                automation_id
            )
        )

    except (
        KeyError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automations/{automation_id}/emergency-stop"
)
async def emergency_stop_automation(
    automation_id: str,
):
    try:
        return await (
            automation_engine
            .emergency_stop(
                automation_id
            )
        )

    except (
        KeyError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# ============================================================
# AUTOMATION MASTER ENGINE + ASSET SECTIONS
# ============================================================

def _automation_capabilities() -> dict[
    str,
    dict[str, Any],
]:
    broker_status = alpaca_broker.status()

    connected = bool(
        broker_status.get(
            "connected"
        )
    )

    raw: dict[str, Any] = {}

    capability_fn = getattr(
        alpaca_broker,
        "capabilities",
        None,
    )

    if callable(
        capability_fn
    ):
        try:
            value = capability_fn()

            if isinstance(
                value,
                dict,
            ):
                raw = value

        except Exception:
            raw = {}

    def supported(
        *keys: str,
    ) -> bool:
        for key in keys:
            value = raw.get(
                key
            )

            if isinstance(
                value,
                bool,
            ):
                return value

            if (
                isinstance(
                    value,
                    dict,
                )
                and isinstance(
                    value.get(
                        "supported"
                    ),
                    bool,
                )
            ):
                return bool(
                    value[
                        "supported"
                    ]
                )

        return False

    disconnected_reason = (
        None
        if connected
        else "Broker disconnected"
    )

    return {
        "stocks": {
            "asset_class": "stocks",
            "supported": (
                connected
                and (
                    supported(
                        "EQUITY",
                        "equity",
                        "stocks",
                    )
                    or not raw
                )
            ),
            "reason": (
                disconnected_reason
                if not connected
                else (
                    None
                    if (
                        supported(
                            "EQUITY",
                            "equity",
                            "stocks",
                        )
                        or not raw
                    )
                    else (
                        "Connected broker does not report "
                        "Stock automatic-order support"
                    )
                )
            ),
        },

        "options": {
            "asset_class": "options",
            "supported": (
                connected
                and supported(
                    "OPTION",
                    "option",
                    "options",
                )
            ),
            "reason": (
                disconnected_reason
                if not connected
                else (
                    None
                    if supported(
                        "OPTION",
                        "option",
                        "options",
                    )
                    else (
                        "Connected broker does not report "
                        "Options automatic-order support"
                    )
                )
            ),
        },

        "crypto": {
            "asset_class": "crypto",
            "supported": (
                connected
                and supported(
                    "CRYPTO",
                    "crypto",
                )
            ),
            "reason": (
                disconnected_reason
                if not connected
                else (
                    None
                    if supported(
                        "CRYPTO",
                        "crypto",
                    )
                    else (
                        "Connected broker does not report "
                        "Crypto automatic-order support"
                    )
                )
            ),
        },

        "etfs": {
            "asset_class": "etfs",
            "supported": (
                connected
                and (
                    supported(
                        "ETF",
                        "etf",
                        "etfs",
                    )
                    or supported(
                        "EQUITY",
                        "equity",
                    )
                )
            ),
            "reason": (
                disconnected_reason
                if not connected
                else (
                    None
                    if (
                        supported(
                            "ETF",
                            "etf",
                            "etfs",
                        )
                        or supported(
                            "EQUITY",
                            "equity",
                        )
                    )
                    else (
                        "Connected broker does not report "
                        "ETF automatic-order support"
                    )
                )
            ),
        },

        "forex": {
            "asset_class": "forex",
            "supported": (
                connected
                and supported(
                    "FOREX",
                    "forex",
                    "fx",
                )
            ),
            "reason": (
                disconnected_reason
                if not connected
                else (
                    None
                    if supported(
                        "FOREX",
                        "forex",
                        "fx",
                    )
                    else (
                        "Connected broker does not report "
                        "Forex automatic-order support"
                    )
                )
            ),
        },

        "bonds": {
            "asset_class": "bonds",
            "supported": (
                connected
                and supported(
                    "BOND",
                    "bond",
                    "bonds",
                )
            ),
            "reason": (
                disconnected_reason
                if not connected
                else (
                    None
                    if supported(
                        "BOND",
                        "bond",
                        "bonds",
                    )
                    else (
                        "Connected broker does not report "
                        "Bond automatic-order support"
                    )
                )
            ),
        },
    }


async def _start_enabled_asset_automations() -> dict[str, Any]:
    started: list[str] = []
    already_running: list[str] = []
    skipped: list[dict[str, str]] = []
    for section in automation_engine.section_list():
        asset_class = str(section.get("asset_class") or "").strip().lower()
        if not section.get("enabled"):
            continue
        runtime = get_asset_automation(asset_class)
        if runtime is None:
            skipped.append({"asset_class": asset_class, "reason": "No asset automation runtime is implemented"})
            continue
        try:
            if runtime.is_running():
                already_running.append(asset_class)
                continue
            result = await runtime.start()
            if bool(result.get("is_running")):
                started.append(asset_class)
            else:
                skipped.append({"asset_class": asset_class, "reason": str(result.get("blocked_reason") or result.get("last_error") or result.get("state") or "Runtime did not start")})
        except Exception as exc:
            skipped.append({"asset_class": asset_class, "reason": str(exc)})
    return {"started": started, "already_running": already_running, "skipped": skipped}


async def _stop_all_asset_automations(*, emergency: bool = False) -> dict[str, Any]:
    stopped: list[str] = []
    errors: list[dict[str, str]] = []
    for asset_class, runtime in asset_automations.items():
        try:
            if not runtime.is_running():
                continue
            if emergency:
                await runtime.emergency_stop("Master automation emergency stop")
            else:
                await runtime.stop(drain=True, reason="Master automation engine stopped")
            stopped.append(asset_class)
        except Exception as exc:
            errors.append({"asset_class": asset_class, "reason": str(exc)})
    return {"stopped": stopped, "errors": errors}


def _asset_runtime_snapshot(asset_class: str) -> dict[str, Any] | None:
    runtime = get_asset_automation(asset_class)
    if runtime is None:
        return None
    try:
        return runtime.status(include_candidates=False, include_positions=False, include_decisions=False, include_events=False)
    except Exception as exc:
        return {"asset_class": asset_class, "is_running": False, "state": "ERROR", "last_error": str(exc)}


@app.get(
    "/api/automation/engine/status"
)
def automation_engine_status():
    status = (
        automation_engine
        .engine_status()
    )

    status[
        "broker_connected"
    ] = bool(
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    )

    status[
        "automation_enabled"
    ] = bool(
        settings.automation_enabled
    )

    status[
        "capabilities"
    ] = _automation_capabilities()

    return status


@app.post(
    "/api/automation/engine/start"
)
async def automation_engine_start():
    if not settings.automation_enabled:
        raise HTTPException(
            status_code=403,
            detail=(
                "Automatic trading is disabled."
            ),
        )

    if not (
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Connect Alpaca first.",
        )

    if automation_engine.engine_status().get("emergency_stop"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Emergency Stop is active."
            ),
        )

    result = await automation_engine.start_enabled_sections()
    result["asset_runtimes"] = await _start_enabled_asset_automations()
    result["sections"] = automation_sections()
    result["running_asset_sections"] = sum(1 for section in result["sections"] if int(section.get("running_automations") or 0) > 0)
    return result


@app.post(
    "/api/automation/engine/stop"
)
async def automation_engine_stop():
    result = await automation_engine.stop_all_runtimes()
    result["asset_runtimes"] = await _stop_all_asset_automations()
    result["sections"] = automation_sections()
    return result


@app.post(
    "/api/automation/engine/emergency-stop"
)
async def automation_engine_emergency_stop():
    automation_engine.activate_master_emergency_stop()

    result = await automation_engine.stop_all_runtimes()
    result["asset_runtimes"] = await _stop_all_asset_automations(emergency=True)

    result[
        "state"
    ] = "EMERGENCY_STOP"

    return result


@app.post(
    "/api/automation/engine/clear-emergency-stop"
)
def automation_engine_clear_emergency_stop():
    return (
        automation_engine
        .clear_master_emergency_stop()
    )


@app.get(
    "/api/automation/activity"
)
def automation_asset_activity():
    """Live telemetry from the real asset-class automation runtimes."""
    rows: list[dict[str, Any]] = []
    for asset_class, runtime in asset_automations.items():
        try:
            status = runtime.status(
                include_candidates=True,
                include_positions=False,
                include_decisions=True,
                include_events=True,
            )
        except Exception as exc:
            rows.append({
                "asset_class": asset_class,
                "state": "ERROR",
                "action": "ERROR",
                "message": str(exc),
            })
            continue

        events = status.get("events") or []
        decisions = status.get("decisions") or []
        candidates = status.get("candidates") or []

        # Prefer concrete runtime events. Newest first.
        for event in reversed(events[-40:]):
            data = event.get("data") or {}
            rows.append({
                "id": event.get("event_id"),
                "timestamp": event.get("timestamp"),
                "asset_class": asset_class,
                "symbol": event.get("symbol") or data.get("symbol"),
                "strategy": data.get("strategy"),
                "action": data.get("action") or data.get("decision") or event.get("event_type"),
                "state": event.get("event_type") or status.get("state"),
                "message": event.get("message"),
                "runtime_state": status.get("state"),
            })

        # If a running runtime has not emitted an event yet, expose its current
        # scan/monitor state instead of pretending there is no runtime.
        if status.get("is_running") and not events:
            candidate = candidates[0] if candidates else {}
            decision = decisions[-1] if decisions else {}
            rows.append({
                "id": f"{asset_class}-runtime",
                "timestamp": status.get("last_scan_at") or status.get("started_at"),
                "asset_class": asset_class,
                "symbol": decision.get("symbol") or candidate.get("symbol"),
                "strategy": decision.get("strategy") or candidate.get("strategy"),
                "action": decision.get("action") or candidate.get("decision") or "SCANNING",
                "state": candidate.get("state") or "MONITORING",
                "message": "Automatic asset runtime is active",
                "runtime_state": status.get("state"),
            })

    rows.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    return rows[:100]


@app.get(
    "/api/automation/capabilities"
)
def automation_capabilities():
    return _automation_capabilities()


@app.get(
    "/api/automation/sections"
)
def automation_sections():
    caps = _automation_capabilities()

    result: list[
        dict[str, Any]
    ] = []

    for asset_section in (
        automation_engine
        .section_list()
    ):
        merged = dict(
            asset_section
        )

        merged.update(
            caps.get(
                asset_section[
                    "asset_class"
                ],
                {},
            )
        )

        runtime_status = _asset_runtime_snapshot(asset_section["asset_class"])
        if runtime_status is not None:
            merged["asset_runtime"] = runtime_status
            if bool(runtime_status.get("is_running")):
                merged["running_automations"] = max(1, int(merged.get("running_automations") or 0))

        result.append(
            merged
        )

    return result


@app.get(
    "/api/automation/sections/{asset_class}"
)
def automation_section(
    asset_class: str,
):
    try:
        asset_section = (
            automation_engine
            .section_state(
                asset_class
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    asset_section.update(
        _automation_capabilities().get(
            asset_section[
                "asset_class"
            ],
            {},
        )
    )

    runtime_status = _asset_runtime_snapshot(asset_section["asset_class"])
    if runtime_status is not None:
        asset_section["asset_runtime"] = runtime_status
        if bool(runtime_status.get("is_running")):
            asset_section["running_automations"] = max(1, int(asset_section.get("running_automations") or 0))

    return asset_section


@app.post(
    "/api/automation/sections/{asset_class}/enable"
)
async def enable_automation_section(
    asset_class: str,
):
    normalized = (
        automation_engine
        ._normalize_asset_class(
            asset_class
        )
    )

    caps = _automation_capabilities()

    capability = caps.get(
        normalized
    )

    if capability is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Unknown automation section"
            ),
        )

    if not capability.get(
        "supported",
        False,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                capability.get(
                    "reason"
                )
                or (
                    "Asset section is "
                    "unavailable"
                )
            ),
        )

    try:
        result = (
            automation_engine
            .set_section_enabled(
                normalized,
                True,
            )
        )

        runtime = get_asset_automation(
            normalized
        )

        if runtime is not None:
            master_running = bool(automation_engine.engine_status().get("master_enabled"))
            if master_running:
                result["runtime"] = await runtime.start()
            else:
                result["runtime"] = {
                    "asset_class": normalized,
                    "state": "ARMED",
                    "is_running": False,
                    "message": "Section enabled. Runtime will start when the master automation engine starts.",
                }

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automation/sections/{asset_class}/disable"
)
async def disable_automation_section(
    asset_class: str,
):
    try:
        result = await (
            automation_engine
            .disable_section(
                asset_class
            )
        )

        runtime = get_asset_automation(
            asset_class
        )

        if runtime is not None:
            result[
                "runtime"
            ] = await runtime.stop()

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# ============================================================
# ALPACA BROKER
# ============================================================

@app.post(
    "/api/broker/alpaca/connect"
)
def connect(
    req: AlpacaConnectRequest,
):
    if (
        not req.paper
        and not settings.allow_live_trading
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Live trading is disabled "
                "by configuration."
            ),
        )

    try:
        return alpaca_broker.connect(
            req.api_key,
            req.secret_key,
            req.paper,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Alpaca connection failed: "
                f"{exc}"
            ),
        ) from exc


@app.post(
    "/api/broker/disconnect"
)
def disconnect():
    automatic_engine.stop()

    return alpaca_broker.disconnect()


@app.get(
    "/api/broker/status"
)
def broker_status():
    return alpaca_broker.status()


@app.get(
    "/api/broker/account"
)
def broker_account():
    if not (
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Connect Alpaca first.",
        )

    metrics = _portfolio_metrics()
    account = dict(metrics["account"])
    account["day_pnl"] = metrics["daily_pnl"]
    account["daily_pnl"] = metrics["daily_pnl"]
    account["weekly_pnl"] = metrics["weekly_pnl"]
    account["gross_exposure"] = metrics["gross_exposure"]
    if metrics["last_equity"] not in (None, 0) and metrics["daily_pnl"] is not None:
        account["day_pnl_percent"] = metrics["daily_pnl"] / metrics["last_equity"] * 100.0
    else:
        account["day_pnl_percent"] = None
    return account


@app.get(
    "/api/broker/positions"
)
def broker_positions():
    if not (
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Connect Alpaca first.",
        )

    return alpaca_broker.positions()


@app.get("/api/broker/orders")
def broker_orders():
    if not alpaca_broker.status().get("connected"):
        raise HTTPException(status_code=400, detail="Connect Alpaca first.")
    return alpaca_broker.open_orders()


# ============================================================
# ENGINE STATUS
# ============================================================

@app.get(
    "/api/engine/status"
)
def engine_status():
    return {
        "mode": (
            "automatic"
            if automatic_engine.enabled
            else "manual"
        ),
        "manual": manual_engine.status(),
        "automatic": automatic_engine.status(),
    }


@app.post(
    "/api/engine/mode"
)
def engine_mode(
    req: EngineModeRequest,
):
    if req.mode == "manual":
        automatic_engine.stop()

    else:
        if not (
            alpaca_broker
            .status()
            .get(
                "connected"
            )
        ):
            raise HTTPException(
                status_code=400,
                detail="Connect Alpaca first.",
            )

        try:
            automatic_engine.start(
                auto_select=True
            )

        except RuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

    return engine_status()

# ============================================================
# EXECUTION STATUS
# ============================================================

@app.get("/api/execution/status")
def execution_status():
    return execution_service.status()


# ============================================================
# MANUAL ENGINE
# ============================================================

@app.post(
    "/api/manual/analyze"
)
async def manual_analyze(
    req: ManualAnalyzeRequest,
):
    if not req.strategy:
        return decision_engine.analyze(
            req.symbol
        )

    market = market_service.context(
        req.symbol
    )

    return await manual_engine.analyze(
        strategy_name=req.strategy,
        symbol=req.symbol,
        market_data=market,
    )


@app.post(
    "/api/manual/order"
)
async def manual_order(
    req: ManualOrderRequest,
):
    if automatic_engine.emergency_stop:
        raise HTTPException(
            status_code=409,
            detail=(
                "Emergency Stop is active."
            ),
        )

    if not (
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Connect Alpaca first.",
        )

    market = market_service.quote(
        req.symbol
    )

    intent = TradeIntent(
        intent_id=(
            "ti_"
            + uuid.uuid4().hex[:12]
        ),
        symbol=req.symbol.upper(),
        side=(
            Side.BUY
            if req.side == "buy"
            else Side.SELL
        ),
        qty=req.qty,
        reference_price=float(
            market[
                "price"
            ]
        ),
        strategy="MANUAL",
        execution_mode=(
            ExecutionMode.MANUAL
        ),
        order_type=req.order_type,
        time_in_force=req.time_in_force,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
    )

    return await execution_service.process(
        intent,
        account_state(),
        False,
        True,
    )


# ============================================================
# AUTOMATIC ENGINE
# ============================================================

@app.post(
    "/api/automatic/start"
)
def auto_start(
    req: AutoStartRequest,
):
    if not settings.automation_enabled:
        raise HTTPException(
            status_code=403,
            detail=(
                "Automatic trading "
                "is disabled."
            ),
        )

    if not (
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Connect Alpaca first.",
        )

    try:
        return automatic_engine.start(
            req.strategy,
            req.auto_select_strategy,
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/automatic/stop"
)
def auto_stop():
    return automatic_engine.stop()


@app.post(
    "/api/automatic/run-cycle"
)
async def auto_cycle(
    req: AutoCycleRequest,
):
    if not (
        alpaca_broker
        .status()
        .get(
            "connected"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Connect Alpaca first.",
        )

    market = market_service.context(
        req.symbol
    )

    try:
        return await automatic_engine.process(
            symbol=req.symbol,
            market_data=market,
            quantity=req.quantity,
            account=account_state(),
            strategy_name=req.strategy,
            automation_enabled=(
                settings.automation_enabled
            ),
            automation_id=(
                req.automation_id
            ),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ============================================================
# AUTOMATIC CONTROLS
# ============================================================

@app.post(
    "/api/control/pause-new-entries"
)
def pause():
    return (
        automatic_engine
        .pause_new_entries()
    )


@app.post(
    "/api/control/resume-new-entries"
)
def resume():
    try:
        return (
            automatic_engine
            .resume_new_entries()
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/control/emergency-stop"
)
def emergency():
    return (
        automatic_engine
        .activate_emergency_stop()
    )


@app.post(
    "/api/control/clear-emergency-stop"
)
def clear_emergency():
    return (
        automatic_engine
        .clear_emergency_stop()
    )


# ============================================================
# POSITIONS
# ============================================================

@app.get(
    "/api/positions"
)
def positions():
    return position_engine.list()


# ============================================================
# ANALYTICS
# ============================================================

@app.get(
    "/api/analytics"
)
def analytics():
    summary = analytics_service.summary()
    result = dict(summary)
    result["total_pnl"] = summary.get("realized_pnl")
    result["equity_curve"] = analytics_service.equity_curve()
    drawdown = analytics_service.drawdown()
    result["realized_pnl_drawdown"] = drawdown.get("max_realized_pnl_drawdown")

    if alpaca_broker.status().get("connected"):
        try:
            metrics = _portfolio_metrics()
            history = metrics["equity_history"]
            if history:
                result["equity_curve"] = [
                    {"equity": value, "source": "alpaca_portfolio_history"}
                    for value in history
                ]
            result["max_drawdown"] = metrics["max_drawdown_percent"]
            result["total_return"] = metrics["total_return_percent"]
            result["day_pnl"] = metrics["daily_pnl"]
            result["weekly_pnl"] = metrics["weekly_pnl"]
            result["source"] = "alpaca + persisted trade_records"
        except Exception:
            result["max_drawdown"] = None
    else:
        result["max_drawdown"] = None

    return result


# ============================================================
# ACTIVITY
# ============================================================

@app.get(
    "/api/activity"
)
def activity(
    limit: int = 100,
):
    safe_limit = max(
        1,
        min(
            limit,
            500,
        ),
    )

    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(
                    AuditEvent
                )
                .order_by(
                    AuditEvent.id.desc()
                )
                .limit(
                    safe_limit
                )
            ).all()
        )

        result = []

        for row in rows:
            try:
                detail = json.loads(
                    row.detail
                )

            except (
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                detail = {
                    "raw": row.detail
                }

            result.append(
                {
                    "id": row.id,
                    "type": row.event_type,
                    "entityId": row.entity_id,
                    "detail": detail,
                    "createdAt": row.created_at,
                }
            )

        return result


# ============================================================
# CHART WEBSOCKET HELPERS
# ============================================================

async def _ws_chart_yahoo_polling(
    ws: WebSocket,
    symbol: str,
    timeframe: str,
) -> None:
    last_candle_signature = None

    await ws.send_json(
        {
            "type": "live_status",
            "symbol": symbol,
            "timeframe": timeframe.upper(),
            "provider": "yahoo-finance",
            "provider_mode": "polled",
            "real_time_stream": False,
            "simulated": False,
            "status": "connected",
        }
    )

    while True:
        try:
            candle = (
                market_service
                .latest_bar(
                    symbol,
                    timeframe,
                )
            )

            candle_signature = (
                candle.get(
                    "time"
                ),
                candle.get(
                    "open"
                ),
                candle.get(
                    "high"
                ),
                candle.get(
                    "low"
                ),
                candle.get(
                    "close"
                ),
                candle.get(
                    "volume"
                ),
            )

            if (
                candle_signature
                != last_candle_signature
            ):
                await ws.send_json(
                    {
                        "type": "candle",
                        "symbol": symbol,
                        "timeframe": timeframe.upper(),
                        "provider": "yahoo-finance",
                        "provider_mode": "polled",
                        "real_time_stream": False,
                        "simulated": False,
                        "candle": candle,
                    }
                )

                last_candle_signature = (
                    candle_signature
                )

            await asyncio.sleep(
                2.0
            )

        except WebSocketDisconnect:
            raise

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            await ws.send_json(
                {
                    "type": "error",
                    "symbol": symbol,
                    "provider": "yahoo-finance",
                    "message": str(exc),
                }
            )

            await asyncio.sleep(
                5.0
            )


async def _ws_chart_alpaca_stream(
    ws: WebSocket,
    symbol: str,
    timeframe: str,
) -> None:
    stream_fn = getattr(
        live_market_service,
        "stream_bars",
        None,
    )

    if not callable(
        stream_fn
    ):
        await _ws_chart_yahoo_polling(
            ws,
            symbol,
            timeframe,
        )

        return

    await ws.send_json(
        {
            "type": "live_status",
            "symbol": symbol,
            "timeframe": timeframe.upper(),
            "provider": "alpaca",
            "provider_mode": "stream",
            "real_time_stream": True,
            "simulated": False,
            "status": "connected",
        }
    )

    try:
        stream = stream_fn(
            symbol,
            timeframe,
        )

        async for candle in stream:
            await ws.send_json(
                {
                    "type": "candle",
                    "symbol": symbol,
                    "timeframe": timeframe.upper(),
                    "provider": "alpaca",
                    "provider_mode": "stream",
                    "real_time_stream": True,
                    "simulated": False,
                    "candle": candle,
                }
            )

    except WebSocketDisconnect:
        raise

    except asyncio.CancelledError:
        raise

    except Exception:
        await _ws_chart_yahoo_polling(
            ws,
            symbol,
            timeframe,
        )


# ============================================================
# CHART WEBSOCKET
# ============================================================

@app.websocket(
    "/ws/chart/{symbol}"
)
async def chart_websocket(
    ws: WebSocket,
    symbol: str,
    timeframe: str = "1M",
):
    await ws.accept()

    symbol = symbol.strip().upper()

    try:
        status = (
            live_market_service
            .status()
        )

        provider = str(
            status.get(
                "provider"
            )
            or ""
        ).lower()

        connected = bool(
            status.get(
                "connected"
            )
        )

        if (
            connected
            and "alpaca" in provider
        ):
            await _ws_chart_alpaca_stream(
                ws,
                symbol,
                timeframe,
            )

        else:
            await _ws_chart_yahoo_polling(
                ws,
                symbol,
                timeframe,
            )

    except WebSocketDisconnect:
        return

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        try:
            await ws.send_json(
                {
                    "type": "error",
                    "symbol": symbol,
                    "message": str(exc),
                }
            )

        except Exception:
            pass

        try:
            await ws.close()

        except Exception:
            pass


# ============================================================
# MARKET WEBSOCKET
# ============================================================

@app.websocket(
    "/ws/market"
)
async def market_websocket(
    ws: WebSocket,
):
    await ws.accept()

    symbols: list[str] = [
        "AAPL",
    ]

    try:
        while True:
            payload = []

            for symbol in symbols:
                try:
                    quote_data = (
                        market_service
                        .quote(
                            symbol
                        )
                    )

                    payload.append(
                        quote_data
                    )

                except Exception:
                    continue

            await ws.send_json(
                {
                    "type": "market",
                    "symbols": payload,
                }
            )

            await asyncio.sleep(
                2.0
            )

    except WebSocketDisconnect:
        return

    except asyncio.CancelledError:
        raise

    except Exception:
        try:
            await ws.close()

        except Exception:
            pass