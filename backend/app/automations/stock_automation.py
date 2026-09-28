from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .base_automation import (
    ACTION_BUY,
    ACTION_HOLD,
    ACTION_SELL,
    CANDIDATE_BLOCKED,
    CANDIDATE_SKIPPED,
    BaseAssetAutomation,
    CandidateRuntime,
    DecisionRuntime,
    normalize_symbol,
    safe_bool,
    safe_float,
    safe_int,
    serialize_value,
)


logger = logging.getLogger(__name__)


# =============================================================================
# STOCK CONSTANTS
# =============================================================================

STOCK_ASSET_CLASS = "stocks"

DEFAULT_STOCK_SCAN_INTERVAL_SECONDS = 30.0
DEFAULT_STOCK_MONITOR_INTERVAL_SECONDS = 3.0
DEFAULT_STOCK_UNIVERSE_REFRESH_SECONDS = 600.0

DEFAULT_STOCK_CANDIDATE_LIMIT = 20

DEFAULT_HOLD_RECHECK_SECONDS = 10.0
DEFAULT_STALE_CANDIDATE_SECONDS = 180.0

DEFAULT_MINIMUM_PRICE = 0.01
DEFAULT_MAXIMUM_PRICE = 1_000_000.0

DEFAULT_MAX_SPREAD_PCT = 5.0

DEFAULT_MINIMUM_VOLUME = 0
DEFAULT_MINIMUM_AVERAGE_VOLUME = 0
DEFAULT_MINIMUM_RELATIVE_VOLUME = 0.0
DEFAULT_MINIMUM_LIQUIDITY_SCORE = 0.0

DEFAULT_MAX_POSITION_FRACTION = 0.10
DEFAULT_MAX_STOCK_EXPOSURE_FRACTION = 0.60

STOCK_CAPABILITY_KEYS = (
    "stocks",
    "stock",
    "equities",
    "equity",
    "us_equities",
)

STOCK_MARKET_DATA_CAPABILITY_KEYS = (
    "stock_market_data",
    "equity_market_data",
    "stock_quotes",
    "equity_quotes",
    "stocks_market_data",
)

STOCK_ORDER_CAPABILITY_KEYS = (
    "stock_orders",
    "stock_trading",
    "equity_orders",
    "equity_trading",
    "stocks_trading",
)

SYMBOL_KEYS = (
    "symbol",
    "ticker",
    "asset",
    "instrument",
)

PRICE_KEYS = (
    "price",
    "last",
    "last_price",
    "current_price",
    "market_price",
    "mark",
    "mark_price",
)

BID_KEYS = (
    "bid",
    "bid_price",
    "best_bid",
)

ASK_KEYS = (
    "ask",
    "ask_price",
    "best_ask",
)

OPEN_KEYS = (
    "open",
    "day_open",
    "session_open",
)

HIGH_KEYS = (
    "high",
    "day_high",
    "session_high",
)

LOW_KEYS = (
    "low",
    "day_low",
    "session_low",
)

PREVIOUS_CLOSE_KEYS = (
    "previous_close",
    "prev_close",
    "prior_close",
)

CHANGE_KEYS = (
    "change_pct",
    "percent_change",
    "price_change_pct",
    "day_change_pct",
)

VOLUME_KEYS = (
    "volume",
    "day_volume",
    "current_volume",
)

AVERAGE_VOLUME_KEYS = (
    "average_volume",
    "avg_volume",
    "average_daily_volume",
    "adv",
)

RELATIVE_VOLUME_KEYS = (
    "relative_volume",
    "relative_volume_ratio",
    "rvol",
    "volume_ratio",
)

LIQUIDITY_KEYS = (
    "liquidity",
    "liquidity_score",
)

VOLATILITY_KEYS = (
    "volatility",
    "volatility_pct",
    "atr_pct",
)

MARKET_CAP_KEYS = (
    "market_cap",
    "market_capitalization",
)

TRADABLE_KEYS = (
    "tradable",
    "is_tradable",
    "tradeable",
)

BUYABLE_KEYS = (
    "buyable",
    "can_buy",
)

SELLABLE_KEYS = (
    "sellable",
    "can_sell",
)

SHORTABLE_KEYS = (
    "shortable",
    "can_short",
)

FRACTIONABLE_KEYS = (
    "fractionable",
    "fractional",
    "supports_fractional",
)

MARGINABLE_KEYS = (
    "marginable",
    "margin_eligible",
)

STATUS_KEYS = (
    "status",
    "asset_status",
    "trading_status",
)

EXCHANGE_KEYS = (
    "exchange",
    "primary_exchange",
    "venue",
)

NAME_KEYS = (
    "name",
    "company_name",
    "description",
)

CURRENCY_KEYS = (
    "currency",
    "quote_currency",
)

MIN_ORDER_KEYS = (
    "min_order_size",
    "minimum_order",
    "minimum_quantity",
    "min_qty",
)

QTY_INCREMENT_KEYS = (
    "quantity_increment",
    "qty_increment",
    "step_size",
)

PRICE_INCREMENT_KEYS = (
    "price_increment",
    "tick_size",
    "minimum_price_increment",
)

SOURCE_KEYS = (
    "source",
    "provider",
    "feed",
    "data_source",
)

AS_OF_KEYS = (
    "as_of",
    "timestamp",
    "updated_at",
    "time",
)

ACTIVE_STATUS_VALUES = {
    "ACTIVE",
    "OPEN",
    "TRADING",
    "TRADEABLE",
    "TRADABLE",
    "ENABLED",
}


# =============================================================================
# HELPERS
# =============================================================================


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, Mapping):
        return dict(value.items())

    if hasattr(value, "model_dump"):
        try:
            result = value.model_dump()

            if isinstance(result, Mapping):
                return dict(result)
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            result = value.dict()

            if isinstance(result, Mapping):
                return dict(result)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        except Exception:
            pass

    return {}


def _first(
    payload: Mapping[str, Any] | None,
    keys: Iterable[str],
    default: Any = None,
) -> Any:
    if not payload:
        return default

    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]

    return default


def _mid_price(
    bid: float | None,
    ask: float | None,
) -> float | None:
    if bid is None or ask is None:
        return None

    if bid <= 0.0 or ask <= 0.0:
        return None

    if ask < bid:
        return None

    return (bid + ask) / 2.0


def _spread_pct(
    bid: float | None,
    ask: float | None,
) -> float | None:
    midpoint = _mid_price(
        bid,
        ask,
    )

    if midpoint is None:
        return None

    return (
        (ask - bid)
        / midpoint
        * 100.0
    )


def _status_is_active(
    value: Any,
) -> bool | None:
    if value is None:
        return None

    text = str(value).strip().upper()

    if not text:
        return None

    if text in ACTIVE_STATUS_VALUES:
        return True

    if text in {
        "INACTIVE",
        "HALTED",
        "CLOSED",
        "DISABLED",
        "DELISTED",
        "SUSPENDED",
        "NOT_TRADABLE",
    }:
        return False

    return None


# =============================================================================
# STOCK DOMAIN MODELS
# =============================================================================


@dataclass
class StockInstrumentSnapshot:
    symbol: str

    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    status: str | None = None

    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None

    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None

    volume: float | None = None
    average_volume: float | None = None
    relative_volume: float | None = None

    liquidity_score: float | None = None
    volatility: float | None = None
    market_cap: float | None = None

    tradable: bool | None = None
    buyable: bool | None = None
    sellable: bool | None = None
    shortable: bool | None = None
    fractionable: bool | None = None
    marginable: bool | None = None

    minimum_order: float | None = None
    quantity_increment: float | None = None
    price_increment: float | None = None

    source: str | None = None
    as_of: str | None = None

    raw: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "symbol": self.symbol,
                "name": self.name,
                "exchange": self.exchange,
                "currency": self.currency,
                "status": self.status,
                "price": self.price,
                "bid": self.bid,
                "ask": self.ask,
                "spread_pct": self.spread_pct,
                "open_price": self.open_price,
                "high_price": self.high_price,
                "low_price": self.low_price,
                "previous_close": self.previous_close,
                "change_pct": self.change_pct,
                "volume": self.volume,
                "average_volume": self.average_volume,
                "relative_volume": self.relative_volume,
                "liquidity_score": self.liquidity_score,
                "volatility": self.volatility,
                "market_cap": self.market_cap,
                "tradable": self.tradable,
                "buyable": self.buyable,
                "sellable": self.sellable,
                "shortable": self.shortable,
                "fractionable": self.fractionable,
                "marginable": self.marginable,
                "minimum_order": self.minimum_order,
                "quantity_increment": self.quantity_increment,
                "price_increment": self.price_increment,
                "source": self.source,
                "as_of": self.as_of,
                "raw": self.raw,
            }
        )


@dataclass
class StockValidationResult:
    valid: bool

    reason: str | None = None

    warnings: list[str] = field(
        default_factory=list
    )

    snapshot: StockInstrumentSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "valid": self.valid,
                "reason": self.reason,
                "warnings": list(
                    self.warnings
                ),
                "snapshot": (
                    self.snapshot.to_dict()
                    if self.snapshot is not None
                    else None
                ),
            }
        )


@dataclass
class StockRuntimeMetrics:
    capability_checks: int = 0
    capability_blocks: int = 0

    metadata_requests: int = 0
    metadata_failures: int = 0

    quote_requests: int = 0
    quote_failures: int = 0

    validations: int = 0
    validation_failures: int = 0

    price_blocks: int = 0
    spread_blocks: int = 0
    liquidity_blocks: int = 0
    volume_blocks: int = 0
    tradability_blocks: int = 0
    status_blocks: int = 0

    buy_blocks: int = 0
    sell_blocks: int = 0
    short_blocks: int = 0

    execution_blocks: int = 0

    position_quote_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            self.__dict__
        )


# =============================================================================
# STOCK AUTOMATION
# =============================================================================


class StockAutomation(BaseAssetAutomation):
    """
    PhoenixTrend U.S. equity automation runtime.

    Broad discovery remains delegated to the shared universe and market
    scanner services so this runtime does not hardcode winning symbols.

    The shared BaseAssetAutomation owns the intelligence pipeline:

        Universe
        -> Scanner
        -> Candidate Ranking
        -> Structural Patterns
        -> Candlestick Patterns
        -> Support / Resistance
        -> Trendlines / Channels
        -> Indicators
        -> Market Regime
        -> Strategy Mapping
        -> Strategy Selector
        -> Decision Engine
        -> BUY / SELL / HOLD
        -> Market Safety
        -> Risk
        -> Automatic Execution
        -> Position Monitoring
        -> Performance / Audit

    This class adds stock-specific market-data validation, tradability,
    liquidity, spread, execution constraints and position enrichment.
    """

    asset_class = STOCK_ASSET_CLASS

    scan_interval_seconds = (
        DEFAULT_STOCK_SCAN_INTERVAL_SECONDS
    )

    monitor_interval_seconds = (
        DEFAULT_STOCK_MONITOR_INTERVAL_SECONDS
    )

    universe_refresh_seconds = (
        DEFAULT_STOCK_UNIVERSE_REFRESH_SECONDS
    )

    candidate_limit = (
        DEFAULT_STOCK_CANDIDATE_LIMIT
    )

    hold_recheck_seconds = (
        DEFAULT_HOLD_RECHECK_SECONDS
    )

    stale_candidate_seconds = (
        DEFAULT_STALE_CANDIDATE_SECONDS
    )

    max_concurrent_analysis = 8
    max_concurrent_executions = 2

    minimum_price = (
        DEFAULT_MINIMUM_PRICE
    )

    maximum_price = (
        DEFAULT_MAXIMUM_PRICE
    )

    max_bid_ask_spread_pct = (
        DEFAULT_MAX_SPREAD_PCT
    )

    minimum_volume = (
        DEFAULT_MINIMUM_VOLUME
    )

    minimum_average_volume = (
        DEFAULT_MINIMUM_AVERAGE_VOLUME
    )

    minimum_relative_volume = (
        DEFAULT_MINIMUM_RELATIVE_VOLUME
    )

    minimum_liquidity_score = (
        DEFAULT_MINIMUM_LIQUIDITY_SCORE
    )

    maximum_position_fraction = (
        DEFAULT_MAX_POSITION_FRACTION
    )

    maximum_stock_exposure_fraction = (
        DEFAULT_MAX_STOCK_EXPOSURE_FRACTION
    )

    require_real_market_data = True
    require_execution_capability = True
    require_tradable_flag = True

    allow_automatic_entries = True

    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        super().__init__()

        self.stock_metrics = (
            StockRuntimeMetrics()
        )

        self._instrument_cache: dict[
            str,
            StockInstrumentSnapshot,
        ] = {}

        self._instrument_cache_lock = (
            asyncio.Lock()
        )

        self._capability_cache: (
            dict[str, Any] | None
        ) = None

        self._capability_checked_at: (
            str | None
        ) = None

    # =========================================================================
    # SERVICE RESOLUTION
    # =========================================================================

    def _broker_service(
        self,
    ) -> Any | None:
        return self._resolve_service(
            "backend.app.broker",
            (
                "alpaca_broker",
                "broker",
                "broker_service",
                "broker_client",
            ),
        )

    def _market_service(
        self,
    ) -> Any | None:
        return self._resolve_service(
            "backend.app.services.market",
            (
                "market_service",
                "market",
            ),
        )

    def _live_market_service(
        self,
    ) -> Any | None:
        return self._resolve_service(
            "backend.app.services.live_market",
            (
                "live_market_service",
                "live_market",
            ),
        )

    # =========================================================================
    # CAPABILITY GATING
    # =========================================================================

    async def capability_snapshot(
        self,
    ) -> dict[str, Any]:
        self.stock_metrics.capability_checks += 1

        base = (
            await super().capability_snapshot()
        )

        if not base.get(
            "supported",
            False,
        ):
            self.stock_metrics.capability_blocks += 1

            result = {
                **base,
                "asset_class": self.asset_class,
                "supported": False,
                "market_data_supported": False,
                "execution_supported": False,
                "reason": (
                    base.get("reason")
                    or (
                        "Configured provider does not "
                        "advertise stock support"
                    )
                ),
                "checked_at": _utc_now(),
            }

            self._capability_cache = result
            self._capability_checked_at = (
                result["checked_at"]
            )

            return result

        broker_capabilities = (
            await self._broker_capabilities()
        )

        general_stock_support = (
            self._capability_value(
                broker_capabilities,
                STOCK_CAPABILITY_KEYS,
            )
        )

        market_data_supported = (
            self._capability_value(
                broker_capabilities,
                STOCK_MARKET_DATA_CAPABILITY_KEYS,
            )
        )

        execution_supported = (
            self._capability_value(
                broker_capabilities,
                STOCK_ORDER_CAPABILITY_KEYS,
            )
        )

        if market_data_supported is None:
            market_data_supported = (
                general_stock_support
            )

        if execution_supported is None:
            execution_supported = (
                general_stock_support
            )

        if market_data_supported is None:
            market_data_supported = bool(
                base.get(
                    "supported",
                    False,
                )
            )

        if execution_supported is None:
            execution_supported = False

        supported = bool(
            base.get(
                "supported",
                False,
            )
            and market_data_supported
        )

        reason: str | None = None

        if not market_data_supported:
            supported = False

            reason = (
                "Configured provider does not "
                "expose stock market data"
            )

        elif (
            self.require_execution_capability
            and not execution_supported
        ):
            supported = False

            reason = (
                "Configured broker does not "
                "support stock order execution"
            )

        if not supported:
            self.stock_metrics.capability_blocks += 1

        result = {
            **base,
            "asset_class": self.asset_class,
            "supported": supported,
            "market_data_supported": bool(
                market_data_supported
            ),
            "execution_supported": bool(
                execution_supported
            ),
            "general_stock_support": (
                general_stock_support
            ),
            "reason": reason,
            "checked_at": _utc_now(),
        }

        self._capability_cache = result
        self._capability_checked_at = (
            result["checked_at"]
        )

        return result

    async def _broker_capabilities(
        self,
    ) -> dict[str, Any]:
        broker = self._broker_service()

        if broker is None:
            return {}

        for method_name in (
            "capabilities",
            "get_capabilities",
            "trading_capabilities",
            "broker_capabilities",
        ):
            method = getattr(
                broker,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            try:
                if asyncio.iscoroutinefunction(
                    method
                ):
                    result = await method()
                else:
                    result = (
                        await asyncio.to_thread(
                            method
                        )
                    )

                return _mapping(
                    result
                )

            except Exception as exc:
                logger.debug(
                    "Stock capability call failed "
                    "using %s: %s",
                    method_name,
                    exc,
                )

        raw = getattr(
            broker,
            "capabilities",
            None,
        )

        if isinstance(
            raw,
            Mapping,
        ):
            return dict(
                raw
            )

        return {}

    def _capability_value(
        self,
        capabilities: Mapping[str, Any],
        keys: Iterable[str],
    ) -> bool | None:
        if not capabilities:
            return None

        normalized = {
            str(key).strip().lower(): value
            for key, value
            in capabilities.items()
        }

        for key in keys:
            lookup = str(
                key
            ).strip().lower()

            if lookup not in normalized:
                continue

            value = normalized[
                lookup
            ]

            if isinstance(
                value,
                Mapping,
            ):
                nested = _first(
                    value,
                    (
                        "supported",
                        "enabled",
                        "available",
                        "tradable",
                    ),
                )

                if nested is not None:
                    return safe_bool(
                        nested
                    )

            return safe_bool(
                value
            )

        assets = normalized.get(
            "assets"
        )

        if isinstance(
            assets,
            Mapping,
        ):
            normalized_assets = {
                str(key).strip().lower(): value
                for key, value
                in assets.items()
            }

            for key in keys:
                lookup = str(
                    key
                ).strip().lower()

                if lookup not in normalized_assets:
                    continue

                value = normalized_assets[
                    lookup
                ]

                if isinstance(
                    value,
                    Mapping,
                ):
                    nested = _first(
                        value,
                        (
                            "supported",
                            "enabled",
                            "available",
                            "tradable",
                        ),
                    )

                    if nested is not None:
                        return safe_bool(
                            nested
                        )

                return safe_bool(
                    value
                )

        return None

    # =========================================================================
    # UNIVERSE
    # =========================================================================

    def universe(
        self,
    ) -> list[str]:
        raw = (
            super().universe()
        )

        result: list[str] = []
        seen: set[str] = set()

        for raw_symbol in raw:
            symbol = normalize_symbol(
                raw_symbol
            )

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(
                symbol
            )

            result.append(
                symbol
            )

        return result

    async def filter_universe(
        self,
        symbols: list[str],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for raw_symbol in symbols:
            symbol = normalize_symbol(
                raw_symbol
            )

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(
                symbol
            )

            result.append(
                symbol
            )

        return result

    # =========================================================================
    # FLEXIBLE PROVIDER INVOCATION
    # =========================================================================

    async def _try_service_methods(
        self,
        service: Any,
        method_names: Iterable[str],
        symbol: str,
        **extra: Any,
    ) -> Any | None:
        for method_name in method_names:
            method = getattr(
                service,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            variants = [
                (
                    (symbol,),
                    {},
                ),
                (
                    (symbol,),
                    extra,
                ),
                (
                    (),
                    {
                        "symbol": symbol,
                        **extra,
                    },
                ),
            ]

            for args, kwargs in variants:
                try:
                    if asyncio.iscoroutinefunction(
                        method
                    ):
                        result = await method(
                            *args,
                            **kwargs,
                        )
                    else:
                        result = (
                            await asyncio.to_thread(
                                method,
                                *args,
                                **kwargs,
                            )
                        )

                    if result is not None:
                        return result

                except TypeError:
                    continue

                except Exception as exc:
                    logger.debug(
                        "Stock service call %s.%s "
                        "failed for %s: %s",
                        service.__class__.__name__,
                        method_name,
                        symbol,
                        exc,
                    )

                    break

        return None

    # =========================================================================
    # INSTRUMENT METADATA
    # =========================================================================

    async def _fetch_stock_metadata(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.stock_metrics.metadata_requests += 1

        broker = (
            self._broker_service()
        )

        if broker is not None:
            result = (
                await self._try_service_methods(
                    broker,
                    (
                        "get_stock",
                        "stock",
                        "get_equity",
                        "equity",
                        "get_asset",
                        "asset",
                        "instrument",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        market = (
            self._market_service()
        )

        if market is not None:
            result = (
                await self._try_service_methods(
                    market,
                    (
                        "stock_metadata",
                        "equity_metadata",
                        "asset",
                        "instrument",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        self.stock_metrics.metadata_failures += 1

        return {}

    # =========================================================================
    # QUOTES
    # =========================================================================

    async def _fetch_stock_quote(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.stock_metrics.quote_requests += 1

        live_market = (
            self._live_market_service()
        )

        if live_market is not None:
            result = (
                await self._try_service_methods(
                    live_market,
                    (
                        "stock_snapshot",
                        "equity_snapshot",
                        "latest_snapshot",
                        "snapshot",
                        "latest_quote",
                        "quote",
                        "get_quote",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        market = (
            self._market_service()
        )

        if market is not None:
            result = (
                await self._try_service_methods(
                    market,
                    (
                        "stock_snapshot",
                        "equity_snapshot",
                        "snapshot",
                        "latest_quote",
                        "quote",
                        "get_quote",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        broker = (
            self._broker_service()
        )

        if broker is not None:
            result = (
                await self._try_service_methods(
                    broker,
                    (
                        "get_stock_quote",
                        "stock_quote",
                        "get_equity_quote",
                        "equity_quote",
                        "get_quote",
                        "quote",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        self.stock_metrics.quote_failures += 1

        return {}

    # =========================================================================
    # STOCK SNAPSHOT
    # =========================================================================

    async def instrument_snapshot(
        self,
        symbol: str,
        *,
        force: bool = False,
    ) -> StockInstrumentSnapshot:
        symbol = normalize_symbol(
            symbol
        )

        if not symbol:
            raise ValueError(
                "Stock symbol is required"
            )

        if not force:
            cached = (
                self._instrument_cache.get(
                    symbol
                )
            )

            if cached is not None:
                return cached

        metadata_task = asyncio.create_task(
            self._fetch_stock_metadata(
                symbol
            )
        )

        quote_task = asyncio.create_task(
            self._fetch_stock_quote(
                symbol
            )
        )

        metadata, quote = (
            await asyncio.gather(
                metadata_task,
                quote_task,
            )
        )

        combined: dict[str, Any] = {}

        combined.update(
            metadata
        )

        combined.update(
            quote
        )

        snapshot = (
            self._build_snapshot(
                symbol,
                combined,
                metadata=metadata,
                quote=quote,
            )
        )

        async with self._instrument_cache_lock:
            self._instrument_cache[
                symbol
            ] = snapshot

        return snapshot

    def _build_snapshot(
        self,
        symbol: str,
        payload: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any],
        quote: Mapping[str, Any],
    ) -> StockInstrumentSnapshot:
        bid = safe_float(
            _first(
                payload,
                BID_KEYS,
            )
        )

        ask = safe_float(
            _first(
                payload,
                ASK_KEYS,
            )
        )

        price = safe_float(
            _first(
                payload,
                PRICE_KEYS,
            )
        )

        if price is None:
            price = _mid_price(
                bid,
                ask,
            )

        volume = safe_float(
            _first(
                payload,
                VOLUME_KEYS,
            )
        )

        average_volume = safe_float(
            _first(
                payload,
                AVERAGE_VOLUME_KEYS,
            )
        )

        relative_volume = safe_float(
            _first(
                payload,
                RELATIVE_VOLUME_KEYS,
            )
        )

        if (
            relative_volume is None
            and volume is not None
            and average_volume is not None
            and average_volume > 0.0
        ):
            relative_volume = (
                volume
                / average_volume
            )

        tradable_raw = _first(
            payload,
            TRADABLE_KEYS,
        )

        buyable_raw = _first(
            payload,
            BUYABLE_KEYS,
        )

        sellable_raw = _first(
            payload,
            SELLABLE_KEYS,
        )

        shortable_raw = _first(
            payload,
            SHORTABLE_KEYS,
        )

        fractionable_raw = _first(
            payload,
            FRACTIONABLE_KEYS,
        )

        marginable_raw = _first(
            payload,
            MARGINABLE_KEYS,
        )

        source = _first(
            payload,
            SOURCE_KEYS,
        )

        as_of = _first(
            payload,
            AS_OF_KEYS,
        )

        return StockInstrumentSnapshot(
            symbol=symbol,
            name=(
                str(
                    _first(
                        payload,
                        NAME_KEYS,
                    )
                )
                if _first(
                    payload,
                    NAME_KEYS,
                )
                is not None
                else None
            ),
            exchange=(
                str(
                    _first(
                        payload,
                        EXCHANGE_KEYS,
                    )
                )
                if _first(
                    payload,
                    EXCHANGE_KEYS,
                )
                is not None
                else None
            ),
            currency=(
                str(
                    _first(
                        payload,
                        CURRENCY_KEYS,
                    )
                ).upper()
                if _first(
                    payload,
                    CURRENCY_KEYS,
                )
                is not None
                else None
            ),
            status=(
                str(
                    _first(
                        payload,
                        STATUS_KEYS,
                    )
                )
                if _first(
                    payload,
                    STATUS_KEYS,
                )
                is not None
                else None
            ),
            price=price,
            bid=bid,
            ask=ask,
            spread_pct=_spread_pct(
                bid,
                ask,
            ),
            open_price=safe_float(
                _first(
                    payload,
                    OPEN_KEYS,
                )
            ),
            high_price=safe_float(
                _first(
                    payload,
                    HIGH_KEYS,
                )
            ),
            low_price=safe_float(
                _first(
                    payload,
                    LOW_KEYS,
                )
            ),
            previous_close=safe_float(
                _first(
                    payload,
                    PREVIOUS_CLOSE_KEYS,
                )
            ),
            change_pct=safe_float(
                _first(
                    payload,
                    CHANGE_KEYS,
                )
            ),
            volume=volume,
            average_volume=average_volume,
            relative_volume=relative_volume,
            liquidity_score=safe_float(
                _first(
                    payload,
                    LIQUIDITY_KEYS,
                )
            ),
            volatility=safe_float(
                _first(
                    payload,
                    VOLATILITY_KEYS,
                )
            ),
            market_cap=safe_float(
                _first(
                    payload,
                    MARKET_CAP_KEYS,
                )
            ),
            tradable=(
                safe_bool(
                    tradable_raw
                )
                if tradable_raw is not None
                else None
            ),
            buyable=(
                safe_bool(
                    buyable_raw
                )
                if buyable_raw is not None
                else None
            ),
            sellable=(
                safe_bool(
                    sellable_raw
                )
                if sellable_raw is not None
                else None
            ),
            shortable=(
                safe_bool(
                    shortable_raw
                )
                if shortable_raw is not None
                else None
            ),
            fractionable=(
                safe_bool(
                    fractionable_raw
                )
                if fractionable_raw is not None
                else None
            ),
            marginable=(
                safe_bool(
                    marginable_raw
                )
                if marginable_raw is not None
                else None
            ),
            minimum_order=safe_float(
                _first(
                    payload,
                    MIN_ORDER_KEYS,
                )
            ),
            quantity_increment=safe_float(
                _first(
                    payload,
                    QTY_INCREMENT_KEYS,
                )
            ),
            price_increment=safe_float(
                _first(
                    payload,
                    PRICE_INCREMENT_KEYS,
                )
            ),
            source=(
                str(
                    source
                )
                if source is not None
                else None
            ),
            as_of=(
                str(
                    as_of
                )
                if as_of is not None
                else None
            ),
            raw={
                "metadata": serialize_value(
                    metadata
                ),
                "quote": serialize_value(
                    quote
                ),
            },
        )

    # =========================================================================
    # STOCK VALIDATION
    # =========================================================================

    async def validate_stock_instrument(
        self,
        symbol: str,
    ) -> StockValidationResult:
        self.stock_metrics.validations += 1

        symbol = normalize_symbol(
            symbol
        )

        if not symbol:
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Stock symbol is missing"
                ),
            )

        try:
            snapshot = (
                await self.instrument_snapshot(
                    symbol,
                    force=True,
                )
            )

        except Exception as exc:
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    f"Stock market-data validation failed: {exc}"
                ),
            )

        warnings: list[str] = []

        if (
            self.require_real_market_data
            and snapshot.price is None
            and snapshot.bid is None
            and snapshot.ask is None
        ):
            self.stock_metrics.price_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "No real stock price or quote "
                    "is available"
                ),
                snapshot=snapshot,
            )

        if snapshot.price is not None:
            if (
                snapshot.price
                < self.minimum_price
            ):
                self.stock_metrics.price_blocks += 1
                self.stock_metrics.validation_failures += 1

                return StockValidationResult(
                    valid=False,
                    reason=(
                        "Stock price is below the "
                        "configured minimum"
                    ),
                    snapshot=snapshot,
                )

            if (
                snapshot.price
                > self.maximum_price
            ):
                self.stock_metrics.price_blocks += 1
                self.stock_metrics.validation_failures += 1

                return StockValidationResult(
                    valid=False,
                    reason=(
                        "Stock price is above the "
                        "configured maximum"
                    ),
                    snapshot=snapshot,
                )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.stock_metrics.spread_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Stock bid/ask spread exceeds "
                    f"{self.max_bid_ask_spread_pct:.4f}%"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.volume is not None
            and snapshot.volume
            < self.minimum_volume
        ):
            self.stock_metrics.volume_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Stock volume is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.average_volume is not None
            and snapshot.average_volume
            < self.minimum_average_volume
        ):
            self.stock_metrics.volume_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Stock average volume is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.relative_volume is not None
            and snapshot.relative_volume
            < self.minimum_relative_volume
        ):
            self.stock_metrics.volume_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Stock relative volume is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.liquidity_score is not None
            and snapshot.liquidity_score
            < self.minimum_liquidity_score
        ):
            self.stock_metrics.liquidity_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Stock liquidity score is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        status_active = (
            _status_is_active(
                snapshot.status
            )
        )

        if status_active is False:
            self.stock_metrics.status_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Provider reports the stock "
                    "instrument as inactive"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_tradable_flag
            and snapshot.tradable is False
        ):
            self.stock_metrics.tradability_blocks += 1
            self.stock_metrics.validation_failures += 1

            return StockValidationResult(
                valid=False,
                reason=(
                    "Broker marks this stock "
                    "as non-tradable"
                ),
                snapshot=snapshot,
            )

        if snapshot.tradable is None:
            warnings.append(
                "Provider did not return an explicit "
                "stock tradable flag"
            )

        if snapshot.bid is None:
            warnings.append(
                "Stock bid is unavailable"
            )

        if snapshot.ask is None:
            warnings.append(
                "Stock ask is unavailable"
            )

        if snapshot.volume is None:
            warnings.append(
                "Stock volume is unavailable"
            )

        if snapshot.average_volume is None:
            warnings.append(
                "Stock average volume is unavailable"
            )

        if snapshot.relative_volume is None:
            warnings.append(
                "Stock relative volume is unavailable"
            )

        if snapshot.liquidity_score is None:
            warnings.append(
                "Stock liquidity score is unavailable"
            )

        return StockValidationResult(
            valid=True,
            warnings=warnings,
            snapshot=snapshot,
        )

    async def validate_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> tuple[
        bool,
        str | None,
    ]:
        valid, reason = (
            await super().validate_candidate(
                candidate
            )
        )

        if not valid:
            self.stock_metrics.validation_failures += 1

            return (
                valid,
                reason,
            )

        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "supported",
            False,
        ):
            self.stock_metrics.validation_failures += 1

            return (
                False,
                capability.get(
                    "reason"
                )
                or (
                    "Stock automation capability "
                    "is unavailable"
                ),
            )

        validation = (
            await self.validate_stock_instrument(
                candidate.symbol
            )
        )

        if not validation.valid:
            return (
                False,
                validation.reason,
            )

        if validation.snapshot is not None:
            candidate.scanner_payload[
                "stock"
            ] = (
                validation.snapshot.to_dict()
            )

        if validation.warnings:
            candidate.scanner_payload[
                "stock_warnings"
            ] = list(
                validation.warnings
            )

        return (
            True,
            None,
        )

    # =========================================================================
    # CANDIDATE PREPARATION
    # =========================================================================

    async def prepare_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> CandidateRuntime:
        candidate = (
            await super().prepare_candidate(
                candidate
            )
        )

        symbol = normalize_symbol(
            candidate.symbol
        )

        if not symbol:
            candidate.state = (
                CANDIDATE_BLOCKED
            )

            return candidate

        snapshot = (
            self._instrument_cache.get(
                symbol
            )
        )

        if snapshot is None:
            snapshot = (
                await self.instrument_snapshot(
                    symbol,
                    force=True,
                )
            )

        candidate.scanner_payload[
            "asset_class"
        ] = self.asset_class

        candidate.scanner_payload[
            "instrument_type"
        ] = "stock"

        candidate.scanner_payload[
            "symbol"
        ] = symbol

        candidate.scanner_payload[
            "stock"
        ] = snapshot.to_dict()

        self._merge_stock_fields(
            candidate.scanner_payload,
            snapshot,
        )

        return candidate

    def _merge_stock_fields(
        self,
        payload: dict[str, Any],
        snapshot: StockInstrumentSnapshot,
    ) -> None:
        if snapshot.price is not None:
            payload.setdefault(
                "price",
                snapshot.price,
            )

        if snapshot.bid is not None:
            payload.setdefault(
                "bid",
                snapshot.bid,
            )

        if snapshot.ask is not None:
            payload.setdefault(
                "ask",
                snapshot.ask,
            )

        if snapshot.spread_pct is not None:
            payload.setdefault(
                "spread_pct",
                snapshot.spread_pct,
            )

        if snapshot.volume is not None:
            payload.setdefault(
                "volume",
                snapshot.volume,
            )

        if snapshot.average_volume is not None:
            payload.setdefault(
                "average_volume",
                snapshot.average_volume,
            )

        if snapshot.relative_volume is not None:
            payload.setdefault(
                "relative_volume",
                snapshot.relative_volume,
            )

        if snapshot.change_pct is not None:
            payload.setdefault(
                "change_pct",
                snapshot.change_pct,
            )

        if snapshot.liquidity_score is not None:
            payload.setdefault(
                "liquidity_score",
                snapshot.liquidity_score,
            )

        if snapshot.volatility is not None:
            payload.setdefault(
                "volatility",
                snapshot.volatility,
            )

        if snapshot.market_cap is not None:
            payload.setdefault(
                "market_cap",
                snapshot.market_cap,
            )

        if snapshot.exchange is not None:
            payload.setdefault(
                "exchange",
                snapshot.exchange,
            )

    # =========================================================================
    # SCANNING
    # =========================================================================

    async def before_scan(
        self,
    ) -> None:
        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "supported",
            False,
        ):
            raise RuntimeError(
                capability.get(
                    "reason"
                )
                or (
                    "Stock automation capability "
                    "is unavailable"
                )
            )

    async def after_scan(
        self,
        result: Mapping[str, Any],
    ) -> None:
        candidates = (
            result.get(
                "candidates",
                [],
            )
        )

        await self._emit_event(
            "STOCK_SCAN_COMPLETED",
            message=(
                "Stock scan completed"
            ),
            data={
                "candidate_count": (
                    len(candidates)
                    if isinstance(
                        candidates,
                        list,
                    )
                    else 0
                ),
                "universe_size": (
                    len(
                        self.universe()
                    )
                ),
            },
        )

    async def scan_market(
        self,
    ) -> dict[str, Any]:
        await self.before_scan()

        result = (
            await super().scan_market()
        )

        candidates = (
            result.get(
                "candidates",
                [],
            )
        )

        validated: list[
            dict[str, Any]
        ] = []

        if isinstance(
            candidates,
            list,
        ):
            semaphore = asyncio.Semaphore(
                max(
                    1,
                    self.max_concurrent_analysis,
                )
            )

            async def validate_one(
                raw_candidate: Any,
            ) -> dict[str, Any] | None:
                payload = _mapping(
                    raw_candidate
                )

                symbol = normalize_symbol(
                    _first(
                        payload,
                        SYMBOL_KEYS,
                    )
                )

                if not symbol:
                    return None

                async with semaphore:
                    validation = (
                        await self.validate_stock_instrument(
                            symbol
                        )
                    )

                if not validation.valid:
                    return None

                snapshot = (
                    validation.snapshot
                )

                if snapshot is None:
                    return None

                payload[
                    "symbol"
                ] = symbol

                payload[
                    "asset_class"
                ] = self.asset_class

                payload[
                    "instrument_type"
                ] = "stock"

                payload[
                    "stock"
                ] = snapshot.to_dict()

                self._merge_stock_fields(
                    payload,
                    snapshot,
                )

                if validation.warnings:
                    payload[
                        "warnings"
                    ] = list(
                        validation.warnings
                    )

                return payload

            tasks = [
                asyncio.create_task(
                    validate_one(
                        raw_candidate
                    )
                )
                for raw_candidate
                in candidates
            ]

            if tasks:
                processed = (
                    await asyncio.gather(
                        *tasks,
                        return_exceptions=True,
                    )
                )

                for item in processed:
                    if isinstance(
                        item,
                        BaseException,
                    ):
                        logger.debug(
                            "Stock candidate validation "
                            "failed: %s",
                            item,
                        )

                        continue

                    if item is not None:
                        validated.append(
                            item
                        )

        result = dict(
            result
        )

        result[
            "candidates"
        ] = validated[
            : self.candidate_limit
        ]

        result[
            "count"
        ] = len(
            result[
                "candidates"
            ]
        )

        result[
            "asset_class"
        ] = self.asset_class

        result[
            "instrument_type"
        ] = "stock"

        await self.after_scan(
            result
        )

        return result

    # =========================================================================
    # EXECUTION VALIDATION
    # =========================================================================

    async def prepare_execution(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> tuple[
        CandidateRuntime,
        DecisionRuntime,
    ]:
        candidate, decision = (
            await super().prepare_execution(
                candidate,
                decision,
            )
        )

        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "execution_supported",
            False,
        ):
            self.stock_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Configured broker does not "
                "support stock execution"
            )

            return (
                candidate,
                decision,
            )

        symbol = normalize_symbol(
            candidate.symbol
        )

        if not symbol:
            self.stock_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Stock symbol is missing"
            )

            return (
                candidate,
                decision,
            )

        snapshot = (
            self._instrument_cache.get(
                symbol
            )
        )

        if snapshot is None:
            snapshot = (
                await self.instrument_snapshot(
                    symbol,
                    force=True,
                )
            )

        if snapshot.tradable is False:
            self.stock_metrics.tradability_blocks += 1
            self.stock_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker marks the selected stock "
                "as non-tradable"
            )

            return (
                candidate,
                decision,
            )

        status_active = (
            _status_is_active(
                snapshot.status
            )
        )

        if status_active is False:
            self.stock_metrics.status_blocks += 1
            self.stock_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Selected stock is not in an "
                "active tradable state"
            )

            return (
                candidate,
                decision,
            )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.stock_metrics.spread_blocks += 1
            self.stock_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Current stock spread exceeds "
                "the configured threshold"
            )

            return (
                candidate,
                decision,
            )

        if (
            decision.action == ACTION_BUY
            and snapshot.buyable is False
        ):
            self.stock_metrics.buy_blocks += 1
            self.stock_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker does not allow BUY orders "
                f"for {symbol}"
            )

            return (
                candidate,
                decision,
            )

        if (
            decision.action == ACTION_SELL
        ):
            can_sell = (
                await self._can_sell_stock(
                    symbol,
                    snapshot,
                )
            )

            if not can_sell:
                self.stock_metrics.sell_blocks += 1
                self.stock_metrics.short_blocks += 1
                self.stock_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    "SELL decision cannot be executed "
                    "because no owned/open position "
                    "was confirmed and the broker "
                    "did not confirm shortability"
                )

                return (
                    candidate,
                    decision,
                )

        decision.analysis.setdefault(
            "stock",
            snapshot.to_dict(),
        )

        decision.analysis[
            "asset_class"
        ] = self.asset_class

        decision.analysis[
            "instrument_type"
        ] = "stock"

        decision.analysis[
            "execution_constraints"
        ] = {
            "symbol": symbol,
            "price": (
                snapshot.price
            ),
            "bid": (
                snapshot.bid
            ),
            "ask": (
                snapshot.ask
            ),
            "spread_pct": (
                snapshot.spread_pct
            ),
            "tradable": (
                snapshot.tradable
            ),
            "buyable": (
                snapshot.buyable
            ),
            "sellable": (
                snapshot.sellable
            ),
            "shortable": (
                snapshot.shortable
            ),
            "fractionable": (
                snapshot.fractionable
            ),
            "marginable": (
                snapshot.marginable
            ),
            "minimum_order": (
                snapshot.minimum_order
            ),
            "quantity_increment": (
                snapshot.quantity_increment
            ),
            "price_increment": (
                snapshot.price_increment
            ),
            "maximum_position_fraction": (
                self.maximum_position_fraction
            ),
            "maximum_stock_exposure_fraction": (
                self.maximum_stock_exposure_fraction
            ),
        }

        return (
            candidate,
            decision,
        )

    async def _can_sell_stock(
        self,
        symbol: str,
        snapshot: StockInstrumentSnapshot,
    ) -> bool:
        if await self.has_open_position(
            symbol
        ):
            return True

        if snapshot.sellable is False:
            return False

        return (
            snapshot.shortable is True
        )

    # =========================================================================
    # DECISION HANDLING
    # =========================================================================

    async def handle_decision(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> None:
        if decision.blocked:
            self.metrics.execution_blocks += 1

            await self._emit_event(
                "STOCK_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    decision.block_reason
                    or (
                        "Stock execution blocked"
                    )
                ),
                data=(
                    decision.to_dict()
                ),
            )

            return

        if (
            decision.action
            == ACTION_HOLD
        ):
            await self._emit_event(
                "STOCK_HOLD",
                symbol=candidate.symbol,
                message=(
                    f"{candidate.symbol} remains "
                    "under stock monitoring"
                ),
                data={
                    "confidence": (
                        decision.confidence
                    ),
                    "strategy": (
                        decision.strategy
                    ),
                    "pattern": (
                        decision.pattern
                    ),
                    "regime": (
                        decision.regime
                    ),
                },
            )

            return

        if decision.action not in {
            ACTION_BUY,
            ACTION_SELL,
        }:
            candidate.state = (
                CANDIDATE_SKIPPED
            )

            await self._emit_event(
                "STOCK_DECISION_SKIPPED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    "Unsupported stock decision "
                    f"{decision.action}"
                ),
            )

            return

        await super().handle_decision(
            candidate,
            decision,
        )

    # =========================================================================
    # POSITION MONITORING
    # =========================================================================

    async def monitor_position(
        self,
        position: Any,
    ) -> None:
        await super().monitor_position(
            position
        )

        symbol = normalize_symbol(
            getattr(
                position,
                "symbol",
                None,
            )
        )

        if not symbol:
            return

        try:
            snapshot = (
                await self.instrument_snapshot(
                    symbol,
                    force=True,
                )
            )

        except Exception as exc:
            self.stock_metrics.position_quote_failures += 1

            await self._emit_event(
                "STOCK_POSITION_QUOTE_FAILED",
                severity="WARNING",
                symbol=symbol,
                message=str(
                    exc
                ),
            )

            return

        if snapshot.price is not None:
            position.current_price = (
                snapshot.price
            )

            quantity = safe_float(
                getattr(
                    position,
                    "quantity",
                    None,
                )
            )

            entry_price = safe_float(
                getattr(
                    position,
                    "entry_price",
                    None,
                )
            )

            side = str(
                getattr(
                    position,
                    "side",
                    "",
                )
                or ""
            ).strip().upper()

            if (
                quantity is not None
                and entry_price is not None
                and entry_price > 0.0
            ):
                direction = (
                    -1.0
                    if side in {
                        "SHORT",
                        "SELL",
                    }
                    else 1.0
                )

                price_delta = (
                    snapshot.price
                    - entry_price
                )

                pnl = (
                    price_delta
                    * quantity
                    * direction
                )

                pnl_pct = (
                    price_delta
                    / entry_price
                    * 100.0
                    * direction
                )

                position.unrealized_pl = (
                    pnl
                )

                position.unrealized_pl_pct = (
                    pnl_pct
                )

        position.raw = {
            **_mapping(
                getattr(
                    position,
                    "raw",
                    {},
                )
            ),
            "stock": (
                snapshot.to_dict()
            ),
        }

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            await self._emit_event(
                "STOCK_SPREAD_WARNING",
                severity="WARNING",
                symbol=symbol,
                message=(
                    f"{symbol} spread exceeds "
                    "the configured threshold"
                ),
                data={
                    "spread_pct": (
                        snapshot.spread_pct
                    ),
                    "threshold": (
                        self.max_bid_ask_spread_pct
                    ),
                },
            )

        status_active = (
            _status_is_active(
                snapshot.status
            )
        )

        if status_active is False:
            await self._emit_event(
                "STOCK_STATUS_WARNING",
                severity="WARNING",
                symbol=symbol,
                message=(
                    f"{symbol} is no longer reported "
                    "as actively tradable"
                ),
                data={
                    "status": (
                        snapshot.status
                    ),
                },
            )

    # =========================================================================
    # STATUS
    # =========================================================================

    def status(
        self,
        *,
        include_candidates: bool = True,
        include_positions: bool = True,
        include_decisions: bool = True,
        include_events: bool = False,
    ) -> dict[str, Any]:
        payload = (
            super().status(
                include_candidates=(
                    include_candidates
                ),
                include_positions=(
                    include_positions
                ),
                include_decisions=(
                    include_decisions
                ),
                include_events=(
                    include_events
                ),
            )
        )

        payload[
            "stock_runtime"
        ] = {
            "metrics": (
                self.stock_metrics.to_dict()
            ),
            "capability": (
                serialize_value(
                    self._capability_cache
                )
            ),
            "capability_checked_at": (
                self._capability_checked_at
            ),
            "cached_instruments": (
                len(
                    self._instrument_cache
                )
            ),
            "configuration": {
                "minimum_price": (
                    self.minimum_price
                ),
                "maximum_price": (
                    self.maximum_price
                ),
                "max_bid_ask_spread_pct": (
                    self.max_bid_ask_spread_pct
                ),
                "minimum_volume": (
                    self.minimum_volume
                ),
                "minimum_average_volume": (
                    self.minimum_average_volume
                ),
                "minimum_relative_volume": (
                    self.minimum_relative_volume
                ),
                "minimum_liquidity_score": (
                    self.minimum_liquidity_score
                ),
                "maximum_position_fraction": (
                    self.maximum_position_fraction
                ),
                "maximum_stock_exposure_fraction": (
                    self.maximum_stock_exposure_fraction
                ),
                "require_real_market_data": (
                    self.require_real_market_data
                ),
                "require_execution_capability": (
                    self.require_execution_capability
                ),
                "require_tradable_flag": (
                    self.require_tradable_flag
                ),
            },
        }

        return payload

    # =========================================================================
    # DIAGNOSTICS
    # =========================================================================

    async def diagnostics(
        self,
    ) -> dict[str, Any]:
        capability = (
            await self.capability_snapshot()
        )

        raw_universe = (
            self.universe()
        )

        universe = (
            await self.filter_universe(
                raw_universe
            )
        )

        sample_validation: list[
            dict[str, Any]
        ] = []

        for symbol in universe[:5]:
            try:
                validation = (
                    await self.validate_stock_instrument(
                        symbol
                    )
                )

                sample_validation.append(
                    {
                        "symbol": symbol,
                        **validation.to_dict(),
                    }
                )

            except Exception as exc:
                sample_validation.append(
                    {
                        "symbol": symbol,
                        "valid": False,
                        "reason": str(
                            exc
                        ),
                    }
                )

        return {
            "asset_class": (
                self.asset_class
            ),
            "capability": (
                capability
            ),
            "universe_size": (
                len(
                    universe
                )
            ),
            "sample_validation": (
                sample_validation
            ),
            "status": (
                self.status(
                    include_candidates=False,
                    include_positions=False,
                    include_decisions=False,
                    include_events=False,
                )
            ),
            "timestamp": (
                _utc_now()
            ),
        }

    async def clear_instrument_cache(
        self,
    ) -> None:
        async with self._instrument_cache_lock:
            self._instrument_cache.clear()


stock_automation = StockAutomation()